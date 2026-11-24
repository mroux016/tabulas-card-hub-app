from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import requests

import Core.config as cfg

_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_SPAWNED_WIREPROXY_PIDS: set[int] = set()
_PIDS_LOCK = threading.Lock()
_LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1"}
_TRACE_URL = "https://1.1.1.1/cdn-cgi/trace"


def normalize_proxy_url(proxy_url: str) -> str:
    """Normalizes a proxy URL string, defaulting scheme to `http://` when omitted."""
    raw = str(proxy_url or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw


def _parse_proxy_host_port(proxy_url: str) -> tuple[str, int, str]:
    norm = normalize_proxy_url(proxy_url)
    if not norm:
        return ("", 0, "http")
    parsed = urlparse(norm)
    host = str(parsed.hostname or "").strip()
    port = int(parsed.port or 0)
    scheme = (parsed.scheme or "http").lower()
    return (host, port, scheme)


def is_localhost_proxy(proxy_url: str) -> bool:
    """Returns True when `proxy_url` targets a loopback interface (`127.0.0.1`, `localhost`, `::1`)."""
    host, _, _ = _parse_proxy_host_port(proxy_url)
    return host.lower() in _LOCALHOST_HOSTS


def _tcp_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    if not host or port <= 0:
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout)):
            return True
    except Exception:
        return False


def discover_wireproxy_configs(proxy_dir: Optional[str | Path] = None) -> dict:
    """
    Dynamically scans `proxy_dir` (defaults to `Core.config.PROXY_DIR`) for `wireproxy.exe`
    and all `wp*.conf` files, parsing each file's `BindAddress` and `WGConfig` target into
    `http(s)/socks5://<host>:<port> -> conf_path`.
    """
    pdir = Path(proxy_dir) if proxy_dir is not None else Path(cfg.PROXY_DIR)
    exe_path = pdir / "wireproxy.exe"
    proxies: dict[str, str] = {}
    configs: dict[str, dict] = {}

    if pdir.is_dir():
        for conf_path in sorted(pdir.glob("wp*.conf")):
            if not conf_path.is_file():
                continue
            try:
                text = conf_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            current_section = ""
            wg_config = ""
            entries: list[tuple[str, str]] = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1].strip().lower()
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key_low = key.strip().lower()
                val_clean = val.split("#", 1)[0].split(";", 1)[0].strip().strip('"').strip("'")
                if key_low == "wgconfig":
                    wg_config = val_clean
                elif key_low == "bindaddress" and val_clean:
                    scheme = "socks5" if "socks" in current_section else "http"
                    entries.append((scheme, val_clean))

            for scheme, bind_addr in entries:
                proxy_url = normalize_proxy_url(f"{scheme}://{bind_addr}")
                if not proxy_url:
                    continue
                proxies[proxy_url] = str(conf_path)
                configs[proxy_url] = {
                    "proxy_url": proxy_url,
                    "conf_path": str(conf_path),
                    "bind_address": bind_addr,
                    "wg_config": wg_config,
                    "scheme": scheme,
                }

    return {
        "proxy_dir": str(pdir),
        "exe_path": str(exe_path) if exe_path.is_file() else "",
        "proxies": proxies,
        "configs": configs,
    }


def kill_wireproxy_processes() -> bool:
    """
    Cleanly terminates running `wireproxy.exe` instances on Windows (via `taskkill /F /IM wireproxy.exe`
    with `CREATE_NO_WINDOW`) and any tracked spawned PIDs.
    """
    ok = True
    is_win = sys.platform.startswith("win")
    if is_win:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "wireproxy.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
                timeout=10,
                check=False,
            )
        except Exception:
            ok = False

    with _PIDS_LOCK:
        pids = list(_SPAWNED_WIREPROXY_PIDS)
        _SPAWNED_WIREPROXY_PIDS.clear()

    if not is_win:
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    return ok


def launch_wireproxy_config(
    exe_path: str | Path,
    conf_path: str | Path,
    proxy_dir: str | Path,
) -> dict:
    """
    Validates `conf_path` syntax (`wireproxy.exe -c <conf> -n`) and starts `wireproxy.exe -c <conf>`
    detached in the background with `CREATE_NO_WINDOW` and `cwd=proxy_dir`.
    """
    exe_s = str(exe_path or "").strip()
    conf_s = str(conf_path or "").strip()
    cwd_s = str(proxy_dir or Path(conf_s).parent)
    if not exe_s or not conf_s:
        return {"ok": False, "pid": None, "conf_path": conf_s, "error": "Missing wireproxy executable or config path"}

    is_win = sys.platform.startswith("win")
    check_flags = _CREATE_NO_WINDOW if is_win else 0
    spawn_flags = (_CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP) if is_win else 0

    try:
        chk = subprocess.run(
            [exe_s, "-c", conf_s, "-n"],
            cwd=cwd_s,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=check_flags,
            check=False,
        )
        if int(getattr(chk, "returncode", 0) or 0) != 0:
            err_msg = (chk.stderr or chk.stdout or f"exit code {chk.returncode}").strip()
            return {
                "ok": False,
                "pid": None,
                "conf_path": conf_s,
                "error": f"Config syntax check failed: {err_msg.splitlines()[0]}",
            }
    except Exception as e:
        return {
            "ok": False,
            "pid": None,
            "conf_path": conf_s,
            "error": f"Config syntax check error: {str(e).splitlines()[0]}",
        }

    try:
        proc = subprocess.Popen(
            [exe_s, "-c", conf_s],
            cwd=cwd_s,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=spawn_flags,
        )
        pid = getattr(proc, "pid", None)
        if pid is not None:
            with _PIDS_LOCK:
                _SPAWNED_WIREPROXY_PIDS.add(int(pid))
        return {"ok": True, "pid": pid, "conf_path": conf_s, "error": ""}
    except Exception as e:
        return {
            "ok": False,
            "pid": None,
            "conf_path": conf_s,
            "error": f"Failed to start wireproxy: {str(e).splitlines()[0]}",
        }


def validate_proxy(proxy_url: str, timeout: float = 6.0) -> dict:
    """
    Performs a quick TCP reachability check followed by a lightweight `https://1.1.1.1/cdn-cgi/trace`
    request through `proxy_url`. Returns `{proxy, ok, ip, colo, loc, latency_ms, error}`.
    """
    norm_url = normalize_proxy_url(proxy_url)
    host, port, _ = _parse_proxy_host_port(norm_url)
    t0 = time.time()
    if not norm_url or not host or port <= 0:
        return {
            "proxy": norm_url or str(proxy_url or ""),
            "ok": False,
            "ip": "",
            "colo": "",
            "loc": "",
            "latency_ms": 0,
            "error": "Invalid proxy URL",
        }

    if not _tcp_port_open(host, port, timeout=min(2.0, max(0.3, float(timeout or 6.0)))):
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "proxy": norm_url,
            "ok": False,
            "ip": "",
            "colo": "",
            "loc": "",
            "latency_ms": elapsed_ms,
            "error": f"TCP port unreachable ({host}:{port})",
        }

    try:
        resp = requests.get(
            _TRACE_URL,
            proxies={"http": norm_url, "https": norm_url},
            timeout=float(timeout or 6.0),
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        code = int(getattr(resp, "status_code", 0) or 0)
        if code != 200:
            return {
                "proxy": norm_url,
                "ok": False,
                "ip": "",
                "colo": "",
                "loc": "",
                "latency_ms": elapsed_ms,
                "error": f"Trace HTTP {code}",
            }

        kv: dict[str, str] = {}
        for line in str(getattr(resp, "text", "") or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        ip = kv.get("ip", "")
        colo = kv.get("colo", "")
        loc = kv.get("loc", "")
        if not ip:
            return {
                "proxy": norm_url,
                "ok": False,
                "ip": "",
                "colo": colo,
                "loc": loc,
                "latency_ms": elapsed_ms,
                "error": "Trace response missing ip",
            }
        return {
            "proxy": norm_url,
            "ok": True,
            "ip": ip,
            "colo": colo,
            "loc": loc,
            "latency_ms": elapsed_ms,
            "error": "",
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        err_line = (str(e) or type(e).__name__).splitlines()[0]
        return {
            "proxy": norm_url,
            "ok": False,
            "ip": "",
            "colo": "",
            "loc": "",
            "latency_ms": elapsed_ms,
            "error": err_line,
        }


def _dedupe_pool(configured_pool: Iterable[str] | str | None) -> list[str]:
    if configured_pool is None:
        return []
    raw_items = (
        re.split(r"[\r\n,;]+", configured_pool)
        if isinstance(configured_pool, str)
        else list(configured_pool)
    )
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        norm = normalize_proxy_url(str(item or ""))
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _match_configs_for_proxies(local_proxies: list[str], discovered_proxies: dict[str, str]) -> dict[str, str]:
    """Matches configured localhost proxy URLs to discovered `wp*.conf` paths by URL or host:port."""
    matched: dict[str, str] = {}
    by_host_port: dict[tuple[str, int], str] = {}
    for d_url, d_conf in discovered_proxies.items():
        h, p, _ = _parse_proxy_host_port(d_url)
        if h and p > 0:
            by_host_port[(h.lower(), p)] = d_conf

    for lp in local_proxies:
        if lp in discovered_proxies:
            matched[lp] = discovered_proxies[lp]
            continue
        h, p, _ = _parse_proxy_host_port(lp)
        hp_key = (h.lower(), p)
        if hp_key in by_host_port:
            matched[lp] = by_host_port[hp_key]

    if not matched and discovered_proxies:
        return dict(discovered_proxies)
    return matched


def ensure_proxies_ready(
    configured_pool: Iterable[str] | str | None,
    proxy_dir: Optional[str | Path] = None,
    force_relaunch: bool = False,
    validate_timeout: float = 6.0,
    startup_wait_s: float = 5.0,
) -> dict:
    """
    Ensures configured localhost `wireproxy` proxies are running and healthy.
    Returns `{healthy_proxies: [...], results: [...], relaunched: bool}` so callers
    route traffic only through verified-working proxies.
    """
    pool = _dedupe_pool(configured_pool)
    local_proxies = [p for p in pool if is_localhost_proxy(p)]
    if not local_proxies:
        return {"healthy_proxies": list(pool), "results": [], "relaunched": False}

    results: list[dict] = []
    relaunched = False

    if not force_relaunch:
        results = [validate_proxy(p, timeout=validate_timeout) for p in local_proxies]
        if all(r.get("ok") for r in results):
            return {"healthy_proxies": list(pool), "results": results, "relaunched": False}

    healthy_local = {r["proxy"] for r in results if r.get("ok")}
    unhealthy_local = [p for p in local_proxies if p not in healthy_local]
    should_kill = bool(force_relaunch or not healthy_local)

    disc = discover_wireproxy_configs(proxy_dir=proxy_dir)
    exe_path = disc.get("exe_path", "")
    all_matched = _match_configs_for_proxies(local_proxies, disc.get("proxies", {}))

    if should_kill:
        to_launch = all_matched
    else:
        healthy_confs = {all_matched[p] for p in healthy_local if p in all_matched}
        to_launch = {
            p: c
            for p, c in all_matched.items()
            if p in unhealthy_local and c not in healthy_confs
        }

    if exe_path and to_launch:
        if should_kill:
            kill_wireproxy_processes()
            time.sleep(0.25)
        launched_urls: list[str] = []
        seen_confs: set[str] = set()
        for p_url, conf_path in to_launch.items():
            if conf_path in seen_confs:
                launched_urls.append(p_url)
                continue
            seen_confs.add(conf_path)
            launch_res = launch_wireproxy_config(exe_path, conf_path, disc["proxy_dir"])
            if launch_res.get("ok"):
                launched_urls.append(p_url)
        relaunched = True

        deadline = time.time() + max(0.0, float(startup_wait_s or 5.0))
        wait_urls = launched_urls or (local_proxies if should_kill else [])
        targets = [_parse_proxy_host_port(u)[:2] for u in wait_urls]
        while targets and time.time() < deadline:
            if all(_tcp_port_open(h, port, timeout=0.4) for h, port in targets if h and port > 0):
                break
            time.sleep(0.25)

    results = [validate_proxy(p, timeout=validate_timeout) for p in local_proxies]
    ok_map = {r["proxy"]: bool(r.get("ok")) for r in results}
    healthy_proxies = [p for p in pool if (not is_localhost_proxy(p)) or ok_map.get(p, False)]
    return {
        "healthy_proxies": healthy_proxies,
        "results": results,
        "relaunched": relaunched,
    }


def get_proxies_status(configured_pool: Iterable[str] | str | None, timeout: float = 6.0) -> dict:
    """Validates every proxy in `configured_pool` without killing or launching processes."""
    pool = _dedupe_pool(configured_pool)
    results = [validate_proxy(p, timeout=timeout) for p in pool]
    healthy = [r["proxy"] for r in results if r.get("ok")]
    return {"healthy_proxies": healthy, "results": results}
