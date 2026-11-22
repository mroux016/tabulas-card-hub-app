from __future__ import annotations
# ==============================================================================
# Core/compute_backend.py - UNIFIED GPU / CPU COMPUTE ACCELERATION LAYER
# Supports:
#   - Win #1: RapidOCR ONNX Runtime GPU (DirectML for AMD/Intel/NVIDIA + CUDA)
#   - Win #3: OpenCV OpenCL (cv2.UMat) GPU acceleration for high-DPI filters
#   - Guardrails: 100% automatic CPU fallback + multi-worker VRAM slot limiter
#   - Foundation: Shared ONNX session factory + Phase-B resident inference hook
# ==============================================================================
import contextlib
import inspect
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

__version__ = "0.24.0-beta.42"
__last_updated__ = "2026-11-21 02:45:00"

from Core.config import COMPUTE_SETTINGS_FILE, GPU_WORKER_CLAIMS_FILE, ensure_directories

DEFAULT_COMPUTE_SETTINGS = {
    "compute_mode": "auto",  # "auto" | "directml" | "cuda" | "cpu"
    "preferred_gpu_device_id": -1,  # -1 = Auto (always prefer discrete GPU / highest dedicated VRAM)
    "enable_ocr_gpu": True,
    "enable_opencl_cv": True,
    "enable_neural_embeddings": True,
    "max_concurrent_gpu_workers": 2,
    "phase_b_shared_inference_server": False,
    "phase_b_endpoint_url": "http://127.0.0.1:5055",
}

GPU_USING_JOB_TYPES = {
    "scan_ingest",
    "reidentify_batch",
    "regrade_batch",
    "regrade_inventory",
    "reprocess_inventory_skus",
    "reprocess_batch_cards",
    "fix_card_rotations",
    "build_neural_index",
}

_SETTINGS_LOCK = threading.Lock()
_OCR_LOCK = threading.Lock()
_ORT_PATCH_LOCK = threading.Lock()

_CACHED_HW_PROBE: Optional[dict] = None
_CACHED_OCR_ENGINE = None
_CACHED_OCR_PROVIDER = "CPUExecutionProvider"
_PROCESS_FORCED_CPU = False
_PROCESS_CLAIMED_GPU = False
_OPENCL_ACTIVE_FOR_PROCESS = False


# ==============================================================================
# SETTINGS PERSISTENCE
# ==============================================================================
def load_compute_settings() -> dict:
    ensure_directories()
    out = dict(DEFAULT_COMPUTE_SETTINGS)
    if COMPUTE_SETTINGS_FILE.exists():
        try:
            raw = json.loads(COMPUTE_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                for k in DEFAULT_COMPUTE_SETTINGS:
                    if k in raw:
                        out[k] = raw[k]
        except Exception:
            pass
    out["compute_mode"] = str(out.get("compute_mode") or "auto").strip().lower()
    if out["compute_mode"] not in ("auto", "directml", "cuda", "cpu"):
        out["compute_mode"] = "auto"
    out["enable_ocr_gpu"] = bool(out.get("enable_ocr_gpu", True))
    out["enable_opencl_cv"] = bool(out.get("enable_opencl_cv", True))
    out["enable_neural_embeddings"] = bool(out.get("enable_neural_embeddings", True))
    try:
        out["preferred_gpu_device_id"] = max(-1, min(15, int(out.get("preferred_gpu_device_id", -1))))
    except Exception:
        out["preferred_gpu_device_id"] = -1
    try:
        out["max_concurrent_gpu_workers"] = max(1, min(8, int(out.get("max_concurrent_gpu_workers", 2))))
    except Exception:
        out["max_concurrent_gpu_workers"] = 2
    out["phase_b_shared_inference_server"] = bool(out.get("phase_b_shared_inference_server", False))
    return out


def save_compute_settings(updates: dict) -> dict:
    global _CACHED_OCR_ENGINE, _CACHED_HW_PROBE, _PROCESS_FORCED_CPU
    with _SETTINGS_LOCK:
        curr = load_compute_settings()
        if isinstance(updates, dict):
            for k in DEFAULT_COMPUTE_SETTINGS:
                if k in updates:
                    curr[k] = updates[k]
        curr["compute_mode"] = str(curr.get("compute_mode") or "auto").strip().lower()
        if curr["compute_mode"] not in ("auto", "directml", "cuda", "cpu"):
            curr["compute_mode"] = "auto"
        try:
            curr["preferred_gpu_device_id"] = max(-1, min(15, int(curr.get("preferred_gpu_device_id", -1))))
        except Exception:
            curr["preferred_gpu_device_id"] = -1
        curr["enable_ocr_gpu"] = bool(curr.get("enable_ocr_gpu", True))
        curr["enable_opencl_cv"] = bool(curr.get("enable_opencl_cv", True))
        curr["enable_neural_embeddings"] = bool(curr.get("enable_neural_embeddings", True))
        curr["max_concurrent_gpu_workers"] = max(1, min(8, int(curr.get("max_concurrent_gpu_workers", 2))))
        try:
            COMPUTE_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_p = COMPUTE_SETTINGS_FILE.with_suffix(".tmp")
            tmp_p.write_text(json.dumps(curr, indent=2), encoding="utf-8")
            os.replace(str(tmp_p), str(COMPUTE_SETTINGS_FILE))
        except Exception:
            pass
    _PROCESS_FORCED_CPU = False
    _CACHED_HW_PROBE = None
    with _OCR_LOCK:
        _CACHED_OCR_ENGINE = None
    try:
        from Core.neural_vision import reset_neural_engine_cache
        reset_neural_engine_cache()
    except Exception:
        pass
    configure_opencv_opencl(settings=curr)
    return curr


# ==============================================================================
# NATIVE WIN32 PID LIVENESS & MULTI-WORKER VRAM SLOT GUARDRAIL
# ==============================================================================
def _is_pid_alive_fast(pid: int) -> bool:
    try:
        pid_i = int(pid or 0)
        if pid_i <= 0:
            return False
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid_i)
            if not h:
                return ctypes.GetLastError() == 5
            try:
                code = ctypes.c_ulong()
                if k32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return code.value == 259
                return True
            finally:
                k32.CloseHandle(h)
        os.kill(pid_i, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _read_and_prune_gpu_claims() -> dict[str, dict]:
    ensure_directories()
    claims: dict[str, dict] = {}
    if GPU_WORKER_CLAIMS_FILE.exists():
        try:
            raw = json.loads(GPU_WORKER_CLAIMS_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                now_t = time.time()
                for pid_s, meta in raw.items():
                    if not isinstance(meta, dict):
                        continue
                    pid_i = int(pid_s) if str(pid_s).isdigit() else 0
                    claimed_at = float(meta.get("claimed_at", 0.0) or 0.0)
                    # Prune dead PIDs or stale claims older than 12 hours
                    if pid_i > 0 and _is_pid_alive_fast(pid_i) and (now_t - claimed_at) < 43200:
                        claims[str(pid_i)] = meta
        except Exception:
            pass
    return claims


def _write_gpu_claims(claims: dict[str, dict]):
    try:
        GPU_WORKER_CLAIMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_p = GPU_WORKER_CLAIMS_FILE.with_name(f"{GPU_WORKER_CLAIMS_FILE.name}.{os.getpid()}.tmp")
        tmp_p.write_text(json.dumps(claims, indent=2), encoding="utf-8")
        os.replace(str(tmp_p), str(GPU_WORKER_CLAIMS_FILE))
    except Exception:
        pass


def claim_gpu_worker_slot(job_type: str = "vision") -> tuple[bool, int, int]:
    """
    Claims a VRAM slot for the current worker process if below `max_concurrent_gpu_workers`.
    Returns `(granted, active_count, max_allowed)`.
    """
    global _PROCESS_CLAIMED_GPU
    cfg = load_compute_settings()
    max_gpu = int(cfg.get("max_concurrent_gpu_workers", 2))
    my_pid = str(os.getpid())
    claims = _read_and_prune_gpu_claims()
    if my_pid in claims:
        _PROCESS_CLAIMED_GPU = True
        return True, len(claims), max_gpu
    if len(claims) >= max_gpu:
        _PROCESS_CLAIMED_GPU = False
        return False, len(claims), max_gpu
    claims[my_pid] = {
        "pid": os.getpid(),
        "job_type": str(job_type or "vision"),
        "claimed_at": time.time(),
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_gpu_claims(claims)
    _PROCESS_CLAIMED_GPU = True
    return True, len(claims), max_gpu


def release_gpu_worker_slot():
    global _PROCESS_CLAIMED_GPU
    my_pid = str(os.getpid())
    claims = _read_and_prune_gpu_claims()
    if my_pid in claims:
        claims.pop(my_pid, None)
        _write_gpu_claims(claims)
    _PROCESS_CLAIMED_GPU = False


def get_active_gpu_worker_claims() -> list[dict]:
    claims = _read_and_prune_gpu_claims()
    return list(claims.values())


# ==============================================================================
# HARDWARE PROBE (WINDOWS GPU + 64-BIT VRAM + ONNX PROVIDERS + OPENCV OPENCL)
# ==============================================================================
def _probe_dxgi_adapters() -> list[dict]:
    """
    Enumerates Windows DXGI hardware adapters via `dxgi.dll` (`IDXGIFactory1::EnumAdapters1`)
    so every `device_id` (`0, 1, 2...`) matches `onnxruntime-directml`'s `DmlExecutionProvider`
    `device_id` 1-to-1! Classifies each adapter as `dGPU` vs `iGPU` using exact 64-bit
    `DedicatedVideoMemory` and excludes software renderers (`Microsoft Basic Render Driver`).
    """
    import re
    if os.name != "nt":
        return []
    adapters: list[dict] = []
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class _LUID(ctypes.Structure):
            _fields_ = [
                ("LowPart", wintypes.DWORD),
                ("HighPart", wintypes.LONG),
            ]

        class _DXGI_ADAPTER_DESC1(ctypes.Structure):
            _fields_ = [
                ("Description", ctypes.c_wchar * 128),
                ("VendorId", ctypes.c_uint),
                ("DeviceId", ctypes.c_uint),
                ("SubSysId", ctypes.c_uint),
                ("Revision", ctypes.c_uint),
                ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", _LUID),
                ("Flags", ctypes.c_uint),
            ]

        dxgi = ctypes.windll.dxgi
        dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        dxgi.CreateDXGIFactory1.restype = ctypes.c_long

        iid_factory1 = _GUID(
            0x770AAE78,
            0xF26F,
            0x4DBA,
            (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
        )
        factory_ptr = ctypes.c_void_p()
        if dxgi.CreateDXGIFactory1(ctypes.byref(iid_factory1), ctypes.byref(factory_ptr)) != 0 or not factory_ptr.value:
            return []

        factory_vtbl = ctypes.cast(factory_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        enum_adapters1 = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(factory_vtbl[12])
        release_fn_t = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        get_desc1_t = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_DXGI_ADAPTER_DESC1))
        release_factory = release_fn_t(factory_vtbl[2])

        try:
            for idx in range(16):
                adapter_ptr = ctypes.c_void_p()
                hr = enum_adapters1(factory_ptr, idx, ctypes.byref(adapter_ptr))
                if hr != 0 or not adapter_ptr.value:
                    break
                try:
                    a_vtbl = ctypes.cast(adapter_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
                    get_desc1 = get_desc1_t(a_vtbl[10])
                    release_adapter = release_fn_t(a_vtbl[2])
                    desc = _DXGI_ADAPTER_DESC1()
                    if get_desc1(adapter_ptr, ctypes.byref(desc)) == 0:
                        is_software = bool(desc.Flags & 2) or (desc.VendorId == 0x1414)
                        name_s = str(desc.Description or "").strip()
                        if is_software or not name_s or "microsoft basic" in name_s.lower():
                            release_adapter(adapter_ptr)
                            continue
                        low = name_s.lower()
                        vendor = (
                            "AMD" if (desc.VendorId == 0x1002 or "amd" in low or "radeon" in low) else
                            "NVIDIA" if (desc.VendorId == 0x10DE or "nvidia" in low or "geforce" in low or "rtx" in low or "gtx" in low) else
                            "Intel" if (desc.VendorId == 0x8086 or "intel" in low or "arc" in low or "iris" in low or "uhd" in low) else
                            "Other"
                        )
                        ded_bytes = int(desc.DedicatedVideoMemory or 0)
                        shr_bytes = int(desc.SharedSystemMemory or 0)
                        vram_gb = round(ded_bytes / (1024.0 ** 3), 2)
                        shared_gb = round(shr_bytes / (1024.0 ** 3), 2)

                        is_igpu_name = bool(re.search(r"radeon\s*\(tm\)\s*graphics\b|uhd\s*graphics|hd\s*graphics|iris|integrated", low))
                        is_dgpu_name = bool(re.search(r"\brx\s*\d|\brtx\s*\d|\bgtx\s*\d|\barc\s*[ab]\d|radeon\s*pro|quadro|titan", low))
                        if vram_gb >= 2.5 or (is_dgpu_name and not is_igpu_name):
                            is_discrete = True
                        elif is_igpu_name:
                            is_discrete = False
                        else:
                            is_discrete = vram_gb >= 1.5

                        adapters.append({
                            "device_id": idx,
                            "name": name_s,
                            "vendor": vendor,
                            "vendor_id": hex(desc.VendorId),
                            "vram_gb": vram_gb,
                            "dedicated_vram_bytes": ded_bytes,
                            "shared_mem_gb": shared_gb,
                            "is_discrete": is_discrete,
                            "adapter_type": "dGPU" if is_discrete else "iGPU",
                            "driver_version": "",
                            "status": "OK",
                        })
                    release_adapter(adapter_ptr)
                except Exception:
                    pass
        finally:
            release_factory(factory_ptr)
    except Exception:
        return []
    return adapters


def resolve_target_gpu_device(
    settings: Optional[dict] = None,
    adapters: Optional[list[dict]] = None,
) -> tuple[int, dict]:
    """
    Resolves the exact DXGI `device_id` to steer DirectML/CUDA onto:
      - If `preferred_gpu_device_id >= 0` and present in hardware adapters -> uses that adapter.
      - Default (`-1`, Auto) -> ALWAYS prioritizes the discrete GPU (`dGPU`) with the highest
        dedicated VRAM (e.g. RX 9070 XT 16 GB over Ryzen iGPU 512 MB)!
    """
    cfg = settings or load_compute_settings()
    dxgi_list = adapters if adapters is not None else _probe_dxgi_adapters()
    if not dxgi_list:
        return 0, {"device_id": 0, "name": "Default GPU #0", "vendor": "Unknown", "vram_gb": 0.0, "is_discrete": True, "adapter_type": "GPU"}

    pref_id = int(cfg.get("preferred_gpu_device_id", -1))
    if pref_id >= 0:
        for ad in dxgi_list:
            if int(ad.get("device_id", -1)) == pref_id:
                return pref_id, ad

    ranked = sorted(
        dxgi_list,
        key=lambda a: (
            1 if a.get("is_discrete") else 0,
            int(a.get("dedicated_vram_bytes", 0)),
            1 if a.get("vendor") in ("NVIDIA", "AMD") else 0,
        ),
        reverse=True,
    )
    best = ranked[0]
    return int(best["device_id"]), best


def _probe_windows_gpus() -> list[dict]:
    """
    Detects installed Windows GPUs via PowerShell CIM + 64-bit registry `qwMemorySize`
    so modern AMD Radeon / NVIDIA GPUs with >4 GB VRAM report their true VRAM size.
    """
    gpus: list[dict] = []
    if os.name != "nt":
        return gpus
    ps_script = r"""
$regVram = @{}
try {
  Get-ItemProperty -Path 'HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction SilentlyContinue | ForEach-Object {
    $desc = $_.DriverDesc
    $qw = $_.'HardwareInformation.qwMemorySize'
    if ($desc -and $qw) {
      if ($qw -is [byte[]]) {
        if ($qw.Length -ge 8) { $bytes = [BitConverter]::ToUInt64($qw, 0) }
        elseif ($qw.Length -ge 4) { $bytes = [BitConverter]::ToUInt32($qw, 0) }
        else { $bytes = 0 }
      } else {
        $bytes = [uint64]$qw
      }
      if ($bytes -gt 0) { $regVram[$desc] = $bytes }
    }
  }
} catch {}
$list = @()
Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object {
  $n = [string]$_.Name
  if (-not $n -or $n -match 'Microsoft Basic|Remote Display|Virtual') { return }
  $vramBytes = if ($regVram.ContainsKey($n)) { $regVram[$n] } else { [uint64]$_.AdapterRAM }
  $list += [PSCustomObject]@{
    name = $n
    driver_version = [string]$_.DriverVersion
    vram_gb = [math]::Round($vramBytes / 1GB, 2)
    status = [string]$_.Status
  }
}
$list | ConvertTo-Json -Compress
"""
    try:
        cf = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=cf,
        )
        raw = (res.stdout or "").strip()
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    name_s = str(item["name"]).strip()
                    low = name_s.lower()
                    vendor = (
                        "AMD" if ("amd" in low or "radeon" in low) else
                        "NVIDIA" if ("nvidia" in low or "geforce" in low or "rtx" in low or "gtx" in low) else
                        "Intel" if ("intel" in low or "arc" in low or "iris" in low or "uhd" in low) else
                        "Other"
                    )
                    gpus.append({
                        "name": name_s,
                        "vendor": vendor,
                        "vram_gb": float(item.get("vram_gb") or 0.0),
                        "driver_version": str(item.get("driver_version") or "").strip(),
                        "status": str(item.get("status") or "OK").strip(),
                    })
    except Exception:
        pass
    # Sort discrete GPUs with larger VRAM first
    gpus.sort(key=lambda g: (0 if g["vendor"] in ("AMD", "NVIDIA") else 1, -g["vram_gb"]))
    return gpus


def _probe_onnxruntime_info() -> dict:
    info = {
        "installed": False,
        "version": "",
        "package_flavor": "none",
        "available_providers": [],
        "has_cuda": False,
        "has_directml": False,
        "has_cpu": False,
    }
    try:
        import importlib.metadata as ilm
        for pkg_name in ("onnxruntime-directml", "onnxruntime-gpu", "onnxruntime"):
            try:
                v = ilm.version(pkg_name)
                if v:
                    info["package_flavor"] = pkg_name
                    break
            except Exception:
                continue
    except Exception:
        pass

    try:
        import onnxruntime as ort
        provs = list(ort.get_available_providers() or [])
        info["installed"] = True
        info["version"] = str(getattr(ort, "__version__", ""))
        info["available_providers"] = provs
        info["has_cuda"] = "CUDAExecutionProvider" in provs
        info["has_directml"] = "DmlExecutionProvider" in provs
        info["has_cpu"] = "CPUExecutionProvider" in provs
    except Exception:
        pass
    return info


def _probe_opencv_opencl_info() -> dict:
    info = {
        "have_opencl": False,
        "use_opencl": False,
        "device_name": "",
        "vendor": "",
        "global_mem_gb": 0.0,
        "driver_version": "",
    }
    try:
        have_ocl = bool(cv2.ocl.haveOpenCL())
        info["have_opencl"] = have_ocl
        if have_ocl:
            cfg = load_compute_settings()
            want_ocl = (cfg["compute_mode"] != "cpu") and bool(cfg["enable_opencl_cv"])
            cv2.ocl.setUseOpenCL(want_ocl)
            info["use_opencl"] = bool(cv2.ocl.useOpenCL())
            dev = cv2.ocl.Device.getDefault()
            if dev is not None:
                info["device_name"] = str(dev.name() or "").strip()
                info["vendor"] = str(dev.vendorName() or "").strip()
                info["driver_version"] = str(dev.driverVersion() or "").strip()
                try:
                    mem_b = int(dev.globalMemSize() or 0)
                    info["global_mem_gb"] = round(mem_b / (1024.0 ** 3), 2)
                except Exception:
                    pass
    except Exception:
        pass
    return info


def resolve_target_onnx_provider(
    settings: Optional[dict] = None,
    ort_info: Optional[dict] = None,
    purpose: str = "ocr",
) -> str:
    """Resolves the active ONNX Execution Provider according to the user's mode, purpose ('ocr' vs 'neural'), and hardware cascade."""
    if _PROCESS_FORCED_CPU:
        return "CPUExecutionProvider"
    cfg = settings or load_compute_settings()
    mode = str(cfg.get("compute_mode") or "auto").lower()
    if mode == "cpu":
        return "CPUExecutionProvider"
    p_norm = str(purpose or "ocr").strip().lower()
    if p_norm == "neural":
        if not cfg.get("enable_neural_embeddings", True):
            return "CPUExecutionProvider"
    else:
        if not cfg.get("enable_ocr_gpu", True):
            return "CPUExecutionProvider"

    oi = ort_info or _probe_onnxruntime_info()
    if mode == "directml":
        return "DmlExecutionProvider" if oi.get("has_directml") else "CPUExecutionProvider"
    if mode == "cuda":
        return "CUDAExecutionProvider" if oi.get("has_cuda") else "CPUExecutionProvider"

    # Auto cascade: CUDA -> DirectML -> CPU
    if oi.get("has_cuda"):
        return "CUDAExecutionProvider"
    if oi.get("has_directml"):
        return "DmlExecutionProvider"
    return "CPUExecutionProvider"


def probe_system_hardware(force_refresh: bool = False) -> dict:
    """
    Runs a full non-destructive hardware & acceleration probe across Windows GPUs,
    ONNX Runtime providers (DirectML/CUDA/CPU), OpenCV OpenCL, VRAM worker slots,
    and Step-3 Neural Vision readiness.
    """
    global _CACHED_HW_PROBE
    if _CACHED_HW_PROBE is not None and not force_refresh:
        # Refresh dynamic fields (settings, claims, neural models) cheaply
        settings = load_compute_settings()
        claims = get_active_gpu_worker_claims()
        res = dict(_CACHED_HW_PROBE)
        res["settings"] = settings
        res["active_ocr_provider"] = resolve_target_onnx_provider(settings, res.get("onnxruntime"))
        res["active_gpu_workers"] = claims
        res["active_gpu_worker_count"] = len(claims)
        res["opencl"] = _probe_opencv_opencl_info()
        try:
            from Core.neural_vision import get_neural_foundation_status
            res["neural_foundation"] = get_neural_foundation_status()
        except Exception:
            res["neural_foundation"] = {}
        return res

    settings = load_compute_settings()
    dxgi_adapters = _probe_dxgi_adapters()
    gpus = dxgi_adapters if dxgi_adapters else _probe_windows_gpus()
    sel_dev_id, sel_gpu = resolve_target_gpu_device(settings=settings, adapters=dxgi_adapters)
    ort_info = _probe_onnxruntime_info()
    ocl_info = _probe_opencv_opencl_info()
    active_prov = resolve_target_onnx_provider(settings, ort_info)
    claims = get_active_gpu_worker_claims()

    primary_gpu = sel_gpu if dxgi_adapters else (
        gpus[0] if gpus else {
            "device_id": 0, "name": ocl_info.get("device_name") or "CPU Only",
            "vendor": "Unknown", "vram_gb": ocl_info.get("global_mem_gb", 0.0),
            "is_discrete": False, "adapter_type": "CPU", "driver_version": ocl_info.get("driver_version", ""),
        }
    )
    needs_directml_install = bool(
        os.name == "nt"
        and len(gpus) > 0
        and not ort_info.get("has_directml")
        and not ort_info.get("has_cuda")
    )

    neural_status = {}
    try:
        from Core.neural_vision import get_neural_foundation_status
        neural_status = get_neural_foundation_status()
    except Exception:
        pass

    probe_out = {
        "probed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform": sys.platform,
        "python_exe": sys.executable,
        "cpu_count": os.cpu_count() or 1,
        "gpus": gpus,
        "dxgi_adapters": dxgi_adapters,
        "selected_gpu_device_id": sel_dev_id,
        "selected_gpu": primary_gpu,
        "primary_gpu": primary_gpu,
        "onnxruntime": ort_info,
        "opencl": ocl_info,
        "settings": settings,
        "active_ocr_provider": active_prov,
        "gpu_ocr_ready": active_prov in ("DmlExecutionProvider", "CUDAExecutionProvider"),
        "needs_directml_install": needs_directml_install,
        "active_gpu_workers": claims,
        "active_gpu_worker_count": len(claims),
        "neural_foundation": neural_status,
        "phase_b_status": "Planned (Phase A VRAM Guardrails Active; SharedInferenceClient Ready)",
    }
    _CACHED_HW_PROBE = probe_out
    return probe_out


# ==============================================================================
# WIN #1: ACCELERATED RAPIDOCR ENGINE (DIRECTML / CUDA + ZERO-BREAKAGE CPU FALLBACK)
# ==============================================================================
@contextlib.contextmanager
def _scoped_onnx_provider_injection(target_provider: str, device_id: Optional[int] = None):
    """
    Safely intercepts `onnxruntime.InferenceSession` ONLY during `RapidOCR()` initialization
    so all RapidOCR sub-models bind to the exact discrete GPU (`device_id`) on `DmlExecutionProvider`
    or `CUDAExecutionProvider` instead of defaulting to iGPU #0!
    """
    import onnxruntime as ort

    resolved_dev_id = int(device_id) if device_id is not None else resolve_target_gpu_device()[0]
    orig_cls = ort.InferenceSession

    class _TabulasAcceleratedOrtSession(orig_cls):
        def __init__(self, path_or_bytes, sess_options=None, providers=None, provider_options=None, **kwargs):
            opts = sess_options if sess_options is not None else ort.SessionOptions()
            if target_provider == "DmlExecutionProvider":
                opts.enable_mem_pattern = False
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            desired = [target_provider, "CPUExecutionProvider"]
            desired_opts = [{"device_id": resolved_dev_id}, {}]
            try:
                super().__init__(path_or_bytes, sess_options=opts, providers=desired, provider_options=desired_opts, **kwargs)
            except Exception:
                super().__init__(path_or_bytes, sess_options=sess_options, providers=["CPUExecutionProvider"], **kwargs)

    with _ORT_PATCH_LOCK:
        ort.InferenceSession = _TabulasAcceleratedOrtSession
        try:
            yield
        finally:
            ort.InferenceSession = orig_cls


def _inspect_rapidocr_active_providers(ocr_engine) -> list[str]:
    provs: list[str] = []
    for attr in ("text_det", "text_cls", "text_rec", "text_detector", "text_classifier", "text_recognizer"):
        comp = getattr(ocr_engine, attr, None)
        if comp is None:
            continue
        infer_obj = getattr(comp, "infer", comp)
        sess = getattr(infer_obj, "session", None)
        if sess is not None and hasattr(sess, "get_providers"):
            try:
                for p in sess.get_providers():
                    if p not in provs:
                        provs.append(p)
            except Exception:
                pass
    return provs


def get_accelerated_rapidocr(log_cb: Optional[Callable[[str], None]] = None, force_cpu: bool = False):
    """
    Returns a cached RapidOCR engine accelerated with `DmlExecutionProvider` (AMD/Intel/NVIDIA)
    or `CUDAExecutionProvider` (NVIDIA) with automatic warmup verification and instant CPU fallback.
    """
    global _CACHED_OCR_ENGINE, _CACHED_OCR_PROVIDER, _PROCESS_FORCED_CPU

    if not force_cpu and _CACHED_OCR_ENGINE is not None:
        return _CACHED_OCR_ENGINE

    with _OCR_LOCK:
        if not force_cpu and _CACHED_OCR_ENGINE is not None:
            return _CACHED_OCR_ENGINE

        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception:
            return None

        cfg = load_compute_settings()
        target_prov = "CPUExecutionProvider" if (force_cpu or _PROCESS_FORCED_CPU) else resolve_target_onnx_provider(cfg)

        # Enforce multi-worker VRAM slot guardrail before allocating GPU memory
        if target_prov != "CPUExecutionProvider" and not _PROCESS_CLAIMED_GPU:
            granted, active_cnt, max_allowed = claim_gpu_worker_slot("ocr_vision")
            if not granted:
                if log_cb:
                    log_cb(
                        f"⚠️ GPU worker slots full ({active_cnt}/{max_allowed}) — "
                        "falling back to CPU for this worker to protect VRAM."
                    )
                target_prov = "CPUExecutionProvider"

        # Try GPU-accelerated RapidOCR initialization first
        if target_prov in ("DmlExecutionProvider", "CUDAExecutionProvider"):
            try:
                sig_params = set(inspect.signature(RapidOCR.__init__).parameters.keys())
                init_kwargs = {}
                if target_prov == "DmlExecutionProvider":
                    for k_dml in ("use_dml", "det_use_dml", "cls_use_dml", "rec_use_dml"):
                        if k_dml in sig_params:
                            init_kwargs[k_dml] = True
                elif target_prov == "CUDAExecutionProvider":
                    for k_cu in ("use_cuda", "det_use_cuda", "cls_use_cuda", "rec_use_cuda"):
                        if k_cu in sig_params:
                            init_kwargs[k_cu] = True

                dev_id_ocr, dev_info_ocr = resolve_target_gpu_device(cfg)
                with _scoped_onnx_provider_injection(target_prov, device_id=dev_id_ocr):
                    eng = RapidOCR(**init_kwargs)

                # Smoke-test GPU inference on a tiny synthetic patch to catch driver/VRAM errors immediately
                dummy = np.full((64, 160, 3), 245, dtype=np.uint8)
                cv2.putText(dummy, "TOPPS 2026", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
                eng(dummy)

                active_provs = _inspect_rapidocr_active_providers(eng)
                used_gpu = target_prov in active_provs
                _CACHED_OCR_ENGINE = eng
                _CACHED_OCR_PROVIDER = target_prov if used_gpu else (active_provs[0] if active_provs else "CPUExecutionProvider")
                if log_cb:
                    log_cb(
                        f"⚡ RapidOCR initialized on {_CACHED_OCR_PROVIDER} "
                        f"[DXGI #{dev_id_ocr}: {dev_info_ocr.get('name', 'GPU')} ({dev_info_ocr.get('adapter_type', 'GPU')})]"
                    )
                return _CACHED_OCR_ENGINE
            except Exception as gpu_err:
                _PROCESS_FORCED_CPU = True
                release_gpu_worker_slot()
                if log_cb:
                    log_cb(f"⚠️ GPU OCR init failed ({target_prov}: {gpu_err}) — falling back cleanly to CPU.")

        # Guaranteed 100% identical CPU fallback
        try:
            eng_cpu = RapidOCR()
            _CACHED_OCR_ENGINE = eng_cpu
            _CACHED_OCR_PROVIDER = "CPUExecutionProvider"
            if log_cb:
                log_cb("🖥️ RapidOCR initialized on CPUExecutionProvider.")
            return _CACHED_OCR_ENGINE
        except Exception:
            return None


def demote_to_cpu_on_error(exc: Exception, log_cb: Optional[Callable[[str], None]] = None):
    """Demotes the current process safely to CPU if a GPU/DirectML/OOM error ever fires mid-batch."""
    global _PROCESS_FORCED_CPU, _CACHED_OCR_ENGINE, _CACHED_OCR_PROVIDER, _OPENCL_ACTIVE_FOR_PROCESS
    already_cpu = _PROCESS_FORCED_CPU
    _PROCESS_FORCED_CPU = True
    _OPENCL_ACTIVE_FOR_PROCESS = False
    with _OCR_LOCK:
        _CACHED_OCR_ENGINE = None
        _CACHED_OCR_PROVIDER = "CPUExecutionProvider"
    try:
        cv2.ocl.setUseOpenCL(False)
    except Exception:
        pass
    release_gpu_worker_slot()
    if not already_cpu and log_cb:
        log_cb(f"⚠️ GPU runtime error ({exc}) — automatically switched to CPU fallback; continuing batch with zero data loss.")


def get_active_ocr_provider_name() -> str:
    return _CACHED_OCR_PROVIDER


# ==============================================================================
# SHARED ONNX SESSION FACTORY (FOUNDATION FOR WINS #2 & #4)
# ==============================================================================
def create_onnx_session(model_path: Path, prefer_gpu: bool = True, purpose: str = "neural"):
    """
    Unified ONNX Runtime session factory used by `Core/neural_vision.py` (Wins #2 & #4).
    Automatically steers DirectML / CUDA onto the discrete GPU (`dGPU`) via exact DXGI
    `device_id` (`provider_options=[{"device_id": dev_id}, {}]`) with 100% safe CPU fallback.
    """
    import onnxruntime as ort

    m_path = Path(model_path)
    if not m_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {m_path}")

    cfg = load_compute_settings()
    target = resolve_target_onnx_provider(cfg, purpose=purpose) if prefer_gpu else "CPUExecutionProvider"

    if target in ("DmlExecutionProvider", "CUDAExecutionProvider") and not _PROCESS_CLAIMED_GPU:
        granted, _, _ = claim_gpu_worker_slot(job_type=f"onnx_{purpose}")
        if not granted:
            target = "CPUExecutionProvider"

    if target in ("DmlExecutionProvider", "CUDAExecutionProvider"):
        try:
            dev_id, dev_info = resolve_target_gpu_device(cfg)
            opts = ort.SessionOptions()
            if target == "DmlExecutionProvider":
                opts.enable_mem_pattern = False
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            sess = ort.InferenceSession(
                str(m_path),
                sess_options=opts,
                providers=[target, "CPUExecutionProvider"],
                provider_options=[{"device_id": int(dev_id)}, {}],
            )
            used_p = sess.get_providers()[0] if sess.get_providers() else target
            if used_p != "CPUExecutionProvider":
                gpu_lbl = f"{used_p} [DXGI #{dev_id}: {dev_info.get('name', 'dGPU')} ({dev_info.get('adapter_type', 'dGPU')})]"
                return sess, gpu_lbl
            return sess, used_p
        except Exception:
            pass

    sess_cpu = ort.InferenceSession(str(m_path), providers=["CPUExecutionProvider"])
    return sess_cpu, "CPUExecutionProvider"


# ==============================================================================
# WIN #3: OPENCV OPENCL (cv2.UMat) GPU-ACCELERATED HIGH-DPI IMAGE PIPELINES
# ==============================================================================
def configure_opencv_opencl(settings: Optional[dict] = None, log_cb: Optional[Callable[[str], None]] = None) -> bool:
    """Enables or disables OpenCV OpenCL (`cv2.UMat`) according to user settings & hardware support."""
    global _OPENCL_ACTIVE_FOR_PROCESS
    cfg = settings or load_compute_settings()
    want_ocl = (
        not _PROCESS_FORCED_CPU
        and cfg.get("compute_mode") != "cpu"
        and bool(cfg.get("enable_opencl_cv", True))
    )
    try:
        if want_ocl and cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(True)
            _OPENCL_ACTIVE_FOR_PROCESS = bool(cv2.ocl.useOpenCL())
        else:
            cv2.ocl.setUseOpenCL(False)
            _OPENCL_ACTIVE_FOR_PROCESS = False
    except Exception:
        _OPENCL_ACTIVE_FOR_PROCESS = False
    return _OPENCL_ACTIVE_FOR_PROCESS


def _should_use_umat(img_np: np.ndarray, min_pixels: int = 240_000) -> bool:
    """Only offload to OpenCL GPU when array size exceeds PCIe transfer break-even threshold."""
    return (
        _OPENCL_ACTIVE_FOR_PROCESS
        and not _PROCESS_FORCED_CPU
        and img_np is not None
        and img_np.ndim >= 2
        and (int(img_np.shape[0]) * int(img_np.shape[1])) >= min_pixels
    )


def opencl_highpass_and_cross_weave(gray_f32: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Win #3 GPU-accelerated Canvas weave micro-texture pipeline:
    Uploads `gray_f32` to `cv2.UMat` once, executes GaussianBlur + high-pass + Sobel X/Y +
    cross-weave minimum on GPU, and downloads results once (with instant CPU fallback).
    """
    if _should_use_umat(gray_f32, min_pixels=200_000):
        try:
            u_gray = cv2.UMat(gray_f32)
            u_blur = cv2.GaussianBlur(u_gray, (7, 7), 1.4)
            u_hp = cv2.subtract(u_gray, u_blur)
            u_hp_abs = cv2.absdiff(u_gray, u_blur)
            u_gx = cv2.Sobel(u_hp, cv2.CV_32F, 1, 0, ksize=3)
            u_gy = cv2.Sobel(u_hp, cv2.CV_32F, 0, 1, ksize=3)
            blur_np = u_blur.get()
            hp_abs_np = u_hp_abs.get()
            gx_np = np.abs(u_gx.get())
            gy_np = np.abs(u_gy.get())
            return blur_np, hp_abs_np, np.minimum(gx_np, gy_np)
        except Exception:
            pass

    blur_macro = cv2.GaussianBlur(gray_f32, (7, 7), 1.4)
    hp = gray_f32 - blur_macro
    hp_abs = np.abs(hp)
    hp_gx = np.abs(cv2.Sobel(hp, cv2.CV_32F, 1, 0, ksize=3))
    hp_gy = np.abs(cv2.Sobel(hp, cv2.CV_32F, 0, 1, ksize=3))
    return blur_macro, hp_abs, np.minimum(hp_gx, hp_gy)


def opencl_clahe_enhance(rgb_np: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Win #3 GPU-accelerated grayscale + CLAHE enhancement for 1600px Tier-3 OCR re-reads."""
    if _should_use_umat(rgb_np, min_pixels=240_000):
        try:
            u_rgb = cv2.UMat(rgb_np)
            u_gray = cv2.cvtColor(u_rgb, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(6, 6))
            u_eq = clahe.apply(u_gray)
            u_eq_rgb = cv2.cvtColor(u_eq, cv2.COLOR_GRAY2RGB)
            return u_eq.get(), u_eq_rgb.get()
        except Exception:
            pass

    b_gray = cv2.cvtColor(rgb_np, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(6, 6))
    b_eq = clahe.apply(b_gray)
    b_eq_rgb = cv2.cvtColor(b_eq, cv2.COLOR_GRAY2RGB)
    return b_eq, b_eq_rgb


def opencl_surface_gradients(gray_u8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Win #3 GPU-accelerated 600 DPI Sobel magnitude + Laplacian for pre-grading & surface checks."""
    if _should_use_umat(gray_u8, min_pixels=240_000):
        try:
            u_g = cv2.UMat(gray_u8)
            u_sx = cv2.Sobel(u_g, cv2.CV_32F, 1, 0, ksize=3)
            u_sy = cv2.Sobel(u_g, cv2.CV_32F, 0, 1, ksize=3)
            u_mag = cv2.magnitude(u_sx, u_sy)
            u_lap = cv2.Laplacian(u_g, cv2.CV_32F, ksize=3)
            return u_mag.get(), np.abs(u_lap.get())
        except Exception:
            pass

    sx = cv2.Sobel(gray_u8, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray_u8, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(sx, sy), np.abs(cv2.Laplacian(gray_u8, cv2.CV_32F, ksize=3))


# ==============================================================================
# WORKER LIFECYCLE HOOK (CALLED BY cli.py FOR VISION JOBS)
# ==============================================================================
def init_worker_compute_backend(job_type: str = "", log_cb: Optional[Callable[[str], None]] = None) -> dict:
    """
    Initializes GPU worker slot reservation, OpenCV OpenCL, and logs the active compute backend
    at the start of vision-heavy background jobs (`scan_ingest`, `reprocess_*`, `regrade_*`, `fix_card_rotations`).
    """
    cfg = load_compute_settings()
    if str(job_type or "") not in GPU_USING_JOB_TYPES:
        return {"gpu_worker": False, "provider": "CPUExecutionProvider", "opencl": False}

    use_ocl = configure_opencv_opencl(settings=cfg, log_cb=log_cb)
    target_prov = resolve_target_onnx_provider(cfg)
    granted = False
    if target_prov != "CPUExecutionProvider":
        granted, act_c, max_c = claim_gpu_worker_slot(job_type=job_type)
        if not granted:
            target_prov = "CPUExecutionProvider"
            if log_cb:
                log_cb(f"⚠️ GPU VRAM Guardrail: {act_c}/{max_c} GPU workers active — running '{job_type}' on CPU.")

    if log_cb:
        dev_id_w, dev_info_w = resolve_target_gpu_device(cfg)
        ocl_txt = "OpenCL GPU (cv2.UMat)" if use_ocl else "CPU NumPy"
        gpu_tag = f" [DXGI #{dev_id_w}: {dev_info_w.get('name', 'GPU')} ({dev_info_w.get('adapter_type', 'GPU')})]" if target_prov != "CPUExecutionProvider" else ""
        log_cb(
            f"⚡ Compute Backend Active: Provider={target_prov}{gpu_tag} | High-DPI Filters={ocl_txt} "
            f"(mode={cfg.get('compute_mode')}, VRAM guard={cfg.get('max_concurrent_gpu_workers')} max GPU workers)"
        )
    return {"gpu_worker": granted, "provider": target_prov, "opencl": use_ocl}


# ==============================================================================
# LIVE CPU VS GPU MICRO-BENCHMARK
# ==============================================================================
def run_compute_benchmark() -> dict:
    """
    Benchmarks Win #3 (600 DPI 1500x2100 image filters: CPU vs. OpenCL UMat) and
    Win #1 (RapidOCR: CPU vs. Active GPU Provider) on synthetic card-sized tensors.
    """
    results = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "opencl_cpu_ms": None,
        "opencl_gpu_ms": None,
        "opencl_speedup": None,
        "ocr_cpu_ms": None,
        "ocr_gpu_ms": None,
        "ocr_gpu_provider": "CPUExecutionProvider",
        "ocr_speedup": None,
        "notes": [],
    }

    # 1. Win #3 Benchmark: 600 DPI card filter pipeline (1500 x 2100 x 8 runs)
    synth_gray = np.random.randint(30, 230, (2100, 1500), dtype=np.uint8)
    synth_f32 = synth_gray.astype(np.float32)

    t0 = time.perf_counter()
    for _ in range(6):
        b = cv2.GaussianBlur(synth_f32, (7, 7), 1.4)
        hp = synth_f32 - b
        gx = cv2.Sobel(hp, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(hp, cv2.CV_32F, 0, 1, ksize=3)
        _ = cv2.Laplacian(synth_f32, cv2.CV_32F, ksize=3)
        _ = cv2.magnitude(gx, gy)
    cpu_cv_ms = ((time.perf_counter() - t0) / 6.0) * 1000.0
    results["opencl_cpu_ms"] = round(cpu_cv_ms, 1)

    if cv2.ocl.haveOpenCL():
        try:
            prev_ocl = cv2.ocl.useOpenCL()
            cv2.ocl.setUseOpenCL(True)
            # Warmup OpenCL kernel compilation once
            u0 = cv2.UMat(synth_f32)
            _ = cv2.GaussianBlur(u0, (7, 7), 1.4).get()
            t1 = time.perf_counter()
            for _ in range(6):
                ug = cv2.UMat(synth_f32)
                ub = cv2.GaussianBlur(ug, (7, 7), 1.4)
                uhp = cv2.subtract(ug, ub)
                ugx = cv2.Sobel(uhp, cv2.CV_32F, 1, 0, ksize=3)
                ugy = cv2.Sobel(uhp, cv2.CV_32F, 0, 1, ksize=3)
                ulap = cv2.Laplacian(ug, cv2.CV_32F, ksize=3)
                umag = cv2.magnitude(ugx, ugy)
                _ = ulap.get()
                _ = umag.get()
            gpu_cv_ms = ((time.perf_counter() - t1) / 6.0) * 1000.0
            cv2.ocl.setUseOpenCL(prev_ocl)
            results["opencl_gpu_ms"] = round(gpu_cv_ms, 1)
            results["opencl_speedup"] = round(cpu_cv_ms / max(0.1, gpu_cv_ms), 2)
        except Exception as e:
            results["notes"].append(f"OpenCL benchmark skipped: {e}")
    else:
        results["notes"].append("OpenCL device not available in OpenCV.")

    # 2. Win #1 Benchmark: RapidOCR on synthetic card-back text image (900 x 1250)
    card_img = np.full((1250, 900, 3), 242, dtype=np.uint8)
    sample_lines = [
        "121  SERIES ONE  AARON JUDGE  OF",
        "NEW YORK YANKEES  HT: 6'7\"  WT: 282  BATS: R  THROWS: R",
        "MAJOR LEAGUE BATTING RECORD",
        "2025 NYY  158  559  122  180  36  1  58  144  .322",
        "THE TOPPS COMPANY, INC. OFFICIALLY LICENSED MLBPA CMP098412",
    ]
    for i_ln, txt_ln in enumerate(sample_lines):
        cv2.putText(card_img, txt_ln, (40, 120 + i_ln * 110), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (25, 25, 25), 2)

    try:
        from rapidocr_onnxruntime import RapidOCR
        eng_cpu = RapidOCR()
        eng_cpu(card_img)  # warmup
        t_c0 = time.perf_counter()
        for _ in range(3):
            eng_cpu(card_img)
        ocr_cpu_ms = ((time.perf_counter() - t_c0) / 3.0) * 1000.0
        results["ocr_cpu_ms"] = round(ocr_cpu_ms, 1)

        ort_info = _probe_onnxruntime_info()
        gpu_prov = "CUDAExecutionProvider" if ort_info.get("has_cuda") else ("DmlExecutionProvider" if ort_info.get("has_directml") else "")
        if gpu_prov:
            dev_id_b, dev_info_b = resolve_target_gpu_device()
            results["ocr_gpu_provider"] = f"{gpu_prov} (DXGI #{dev_id_b}: {dev_info_b.get('name', 'dGPU')})"
            with _scoped_onnx_provider_injection(gpu_prov, device_id=dev_id_b):
                eng_gpu = RapidOCR()
            eng_gpu(card_img)  # warmup
            t_g0 = time.perf_counter()
            for _ in range(3):
                eng_gpu(card_img)
            ocr_gpu_ms = ((time.perf_counter() - t_g0) / 3.0) * 1000.0
            results["ocr_gpu_ms"] = round(ocr_gpu_ms, 1)
            results["ocr_speedup"] = round(ocr_cpu_ms / max(0.1, ocr_gpu_ms), 2)
        else:
            results["notes"].append("Install onnxruntime-directml to enable DirectML GPU OCR on AMD/Intel/NVIDIA Windows GPUs.")
    except Exception as e:
        results["notes"].append(f"RapidOCR benchmark note: {e}")

    # 3. Win #2 Benchmark: DINOv2-small Batch-16 Deep Visual Embeddings (DirectML / CUDA vs CPU)
    try:
        from Core.neural_vision import benchmark_dinov2_gpu_vs_cpu
        results["dinov2"] = benchmark_dinov2_gpu_vs_cpu(batch_size=16)
    except Exception as e:
        results["dinov2"] = {"installed": False, "note": str(e)}

    return results


# ==============================================================================
# PHASE-B ARCHITECTURE STUB: SHARED RESIDENT INFERENCE CLIENT
# ==============================================================================
class SharedInferenceClient:
    """
    Phase-B architectural interface stub: when a resident GPU inference service is enabled
    in the future, all 8 parallel worker subprocesses can route OCR & neural embedding requests
    through this client to share a single loaded GPU model in VRAM with automatic micro-batching.
    """

    def __init__(self, endpoint_url: Optional[str] = None):
        cfg = load_compute_settings()
        self.enabled = bool(cfg.get("phase_b_shared_inference_server", False))
        self.endpoint_url = str(endpoint_url or cfg.get("phase_b_endpoint_url") or "http://127.0.0.1:5055")

    def is_available(self) -> bool:
        return False
