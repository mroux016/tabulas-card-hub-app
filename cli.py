from __future__ import annotations
# ==============================================================================
# cli.py - 6-SILO MULTI-PROCESS BACKGROUND WORKER, SAME-SILO QUEUE / PARALLEL
# ENGINE, UNIFIED SCHEDULED ACTIVITIES MANAGER & COMMAND-LINE RUNNER
# ==============================================================================
import argparse
import ast
import csv
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

__version__ = "0.24.0-beta.45"
__last_updated__ = "2026-11-21 15:05:00"

_DEFAULT_HUB_DIR = r"C:\Tabulas Card Hub" if os.path.exists(r"C:\Tabulas Card Hub") else r"D:\OneDrive\Pictures\Cards"
_ROOT_DIR = Path(os.environ.get("CARDS_BASE_DIR", _DEFAULT_HUB_DIR))
for _sp in (_ROOT_DIR / "App", _ROOT_DIR):
    if _sp.exists() and str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

from Core.config import (
    APP_DIR,
    APP_RELEASE_STAGE,
    APP_RELEASE_VERSION,
    ARCHIVE_DIR,
    ARCHIVE_LOGS_DIR,
    BASE_DIR,
    CHECKLIST_PATH,
    DAILY_LOGS_ROOT,
    LOGS_DIR,
    REFERENCE_TEMPLATES_DIR,
    REPORTS_DIR,
    REVIEWED_CARDS_DIR,
    RUNTIME_CONFIG,
    SET_CHECKLISTS_DIR,
    SET_LIBRARY_CACHE_DIR,
    SET_LIBRARY_ROOT,
    TABULAS_VENV_PYTHON,
    UNPROCESSED_CARDS_DIR,
    atomic_write_text,
    ensure_directories,
    get_daily_log_dir,
    inspect_all_module_versions,
    sanitize_filename_part,
)
from Core.rate_learner import get_rate_learner
from Core.compute_backend import init_worker_compute_backend, probe_system_hardware, release_gpu_worker_slot
from Core.neural_vision import build_or_update_neural_embedding_index, download_dinov2_small_model
from Core.database import (
    find_unarchived_scan_batches,
    load_inventory_df,
    load_master_checklist,
    save_inventory_df,
)
from Core.market_engine import (
    refresh_dugout_vault_grading_tiers,
    refresh_inventory_market_valuations,
)
from Core.sales_engine import (
    generate_card_listing_copy,
    load_listing_drafts_df,
    save_listing_drafts_df,
)
from Core.scraper_engine import (
    archive_existing_checklists_for_clean_slate,
    crawl_tcdb_master_set_directory,
    load_schedule_config,
    load_tracked_sets,
    mode_download_all_catalog_images,
    mode_checklist_and_images_card_by_card,
    mode_image_update_pipeline,
    mode_missing_back_audit,
    mode_scraping_pipeline,
    repair_corrupted_checklists_and_processed_cards,
    clean_reference_library_names,
    repair_tcdb_set_directory,
    deduplicate_tracked_sets_and_directory,
    resume_saved_run,
    run_breakninja_pipeline,
    run_tcdb_checklist_pipeline,
    set_log_callback,
    set_progress_callback,
    sync_set_library_download_status,
)
from Core.vision_grader import (
    fix_card_rotations_and_regrade,
    index_set_templates_and_reviewed_cards,
    process_single_batch,
    regrade_batch_cards,
    regrade_inventory_cards,
    reidentify_batch_cards,
    reprocess_batch_cards_list,
    reprocess_inventory_skus,
)

# 8-Slot Dynamic Parallel Process Pool (Up to 8 concurrent processes; unused workers hidden in UI!)
PROCESS_LANES = {
    "slot_1": {"name": "Worker Slot 1", "short_name": "Worker 1", "icon": "⚡", "port": 8501},
    "slot_2": {"name": "Worker Slot 2", "short_name": "Worker 2", "icon": "⚡", "port": 8502},
    "slot_3": {"name": "Worker Slot 3", "short_name": "Worker 3", "icon": "⚡", "port": 8503},
    "slot_4": {"name": "Worker Slot 4", "short_name": "Worker 4", "icon": "⚡", "port": 8504},
    "slot_5": {"name": "Worker Slot 5", "short_name": "Worker 5", "icon": "⚡", "port": 8505},
    "slot_6": {"name": "Worker Slot 6", "short_name": "Worker 6", "icon": "⚡", "port": 8506},
    "slot_7": {"name": "Worker Slot 7", "short_name": "Worker 7", "icon": "⚡", "port": 8507},
    "slot_8": {"name": "Worker Slot 8", "short_name": "Worker 8", "icon": "⚡", "port": 8508},
}

JOB_TYPE_ICON_MAP = {
    "scan_ingest": "📥",
    "reidentify_batch": "🧠",
    "regrade_batch": "🔄",
    "regrade_inventory": "🔄",
    "reprocess_inventory_skus": "🔄",
    "reprocess_batch_cards": "🔄",
    "fix_card_rotations": "↻",
    "install_directml": "⚡",
    "download_dinov2_model": "📥",
    "build_neural_index": "🧬",
    "commit_batches": "🎉",
    "tcdb_scrape": "🕷️",
    "tcdb_download_all_images": "📥",
    "tcdb_checklist_and_images": "⚡",
    "tcdb_upgrade": "✨",
    "tcdb_missing_back": "🔎",
    "tcdb_resume": "▶️",
    "tcdb_checklist_scrape": "🏛️",
    "repair_checklists": "🔧",
    "clean_reference_library": "🗂️",
    "deduplicate_tracked_sets": "🧹",
    "sync_set_library_status": "🔄",
    "rebuild_feature_cache": "🧠",
    "repair_tcdb_directory": "📊",
    "crawl_tcdb_directory": "🌐",
    "refresh_market_valuations": "💰",
    "batch_generate_listings": "✍️",
    "system_startup": "🛠️",
    "system_maintenance": "🛠️",
    "system_update": "🚀",
}

# ONLY TCDB web scrapers serialize against each other (respecting TCDB's ~25 req/min Cloudflare rate limit).
# Everything else — including non-TCDB scrapers (SportsCardsPro, Dugout Vault, MLB StatsAPI, Wikipedia),
# Scan Ingestion, Card Reprocessing, Pre-Grading, Local Repairs/Syncs, and System Maintenance — runs in parallel!
TCDB_RATE_LIMITED_JOB_TYPES = {
    "tcdb_scrape",
    "tcdb_download_all_images",
    "tcdb_checklist_and_images",
    "tcdb_upgrade",
    "tcdb_missing_back",
    "tcdb_resume",
    "tcdb_checklist_scrape",
    "crawl_tcdb_directory",
}
HEAVY_TCDB_JOB_TYPES = TCDB_RATE_LIMITED_JOB_TYPES

_SLOT_DISPATCH_LOCK = threading.Lock()


def _is_tcdb_rate_limited_job(job_type: str, payload: Optional[dict] = None, title: str = "") -> bool:
    """Returns True ONLY for jobs that actively scrape TCDB web endpoints (rate-limited by Cloudflare)."""
    jt = str(job_type or "").strip()
    if jt in TCDB_RATE_LIMITED_JOB_TYPES:
        return True
    if jt == "repair_tcdb_directory":
        if isinstance(payload, dict) and "fetch_missing_image_pct" in payload:
            return bool(payload.get("fetch_missing_image_pct", False))
        t_low = str(title or "").lower()
        return ("backfill" in t_low) or ("live" in t_low) or ("viewall" in t_low)
    return False

JOB_TYPE_TO_LANE = {k: "slot_1" for k in JOB_TYPE_ICON_MAP}

ACTIVE_JOB_STATE_FILE = LOGS_DIR / "active_job_state.json"
ACTIVE_JOB_LOG_FILE = LOGS_DIR / "active_job_terminal.log"
RUN_LOGS_DIR = LOGS_DIR
TASK_LOGS_DIR = LOGS_DIR


def get_task_log_file(job_type: str) -> Path:
    """
    Creates a timestamped verbose log file inside `C:\\Tabulas Card Hub\\Logs\\Logs\\YYYYMMDD\\`.
    """
    ensure_directories()
    day_dir = get_daily_log_dir()
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_jt = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(job_type or "general_task")).strip("_") or "general_task"
    return day_dir / f"{ts_str}_{safe_jt}.log"


def clear_lane_monitor_log(lane: str = "slot_1") -> bool:
    """Clears the Live Monitor screen log (`job_log_<lane>.log`) without touching permanent per-process logs."""
    ensure_directories()
    log_f = get_lane_log_file(lane)
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_f.write_text(f"[{ts}] --- Monitor cleared ---\n", encoding="utf-8")
        return True
    except Exception:
        return False


def list_run_log_files(limit: int = 50) -> list[dict]:
    """Lists all verbose process log files directly in `C:\\Tabulas Card Hub\\Logs` sorted newest-first."""
    ensure_directories()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    candidates = [p for p in LOGS_DIR.glob("*.log") if p.is_file()]
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates[:limit]:
        try:
            st = p.stat()
            rel = p.relative_to(LOGS_DIR).as_posix()
            out.append({
                "name": p.name,
                "relPath": rel,
                "fullPath": str(p),
                "sizeKb": round(st.st_size / 1024.0, 1),
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception:
            continue
    return out
UNIFIED_SCHEDULES_FILE = LOGS_DIR / "unified_schedules_registry.json"
WINDOWS_MARKET_TASK_NAME = "Tabulas_Daily_Market_Valuation_Job"
MAX_PARALLEL_SLOTS_PER_LANE = 4

SCHEDULED_PIPELINE_CATALOG = {
    "auto_checklists": {
        "label": "🏛️ TCDB Master Checklist Builder (With TCDB_CIDs)",
        "cli_flag": "--auto-checklists",
        "default_task_name": "Tabulas_Scheduled_Checklist_Build_Job",
        "lane": "set_scraper",
        "job_type": "tcdb_checklist_scrape",
    },
    "auto_scrape": {
        "label": "🕷️ TCDB Set Template Image Scraper",
        "cli_flag": "--auto-scrape",
        "default_task_name": "Tabulas_Scheduled_Pipeline_Job",
        "lane": "set_scraper",
        "job_type": "tcdb_scrape",
    },
    "auto_upgrade": {
        "label": "🔄 TCDB High-Res Image Upgrade",
        "cli_flag": "--auto-upgrade",
        "default_task_name": "Tabulas_Scheduled_HighRes_Upgrade_Job",
        "lane": "set_scraper",
        "job_type": "tcdb_upgrade",
    },
    "auto_market": {
        "label": "💰 Market Comps & Dugout Vault Grading Tiers Refresh",
        "cli_flag": "--auto-market",
        "default_task_name": "Tabulas_Daily_Market_Valuation_Job",
        "lane": "market_analytics",
        "job_type": "refresh_market_valuations",
    },
    "auto_directory": {
        "label": "🌐 TCDB All-Sports Master Set Directory Crawler",
        "cli_flag": "--auto-directory",
        "default_task_name": "Tabulas_Scheduled_Directory_Crawl_Job",
        "lane": "set_browser",
        "job_type": "crawl_tcdb_directory",
    },
    "process_scans": {
        "label": "🔍 Incoming_Scans PDF Batch Auto-Ingestion",
        "cli_flag": "--process-scans",
        "default_task_name": "Tabulas_Scheduled_Scan_Ingest_Job",
        "lane": "ingest_inventory",
        "job_type": "scan_ingest",
    },
}


def base_lane_from_slot(lane_or_slot: str) -> str:
    s = str(lane_or_slot or "slot_1").strip()
    base = s.split("__p", 1)[0]
    return base if base in PROCESS_LANES else "slot_1"


def _is_slot_currently_busy(slot_key: str) -> tuple[bool, dict]:
    """
    Checks whether `slot_key` is busy by trusting `get_active_job_state()` (which already
    enforces Win32 PID liveness + startup grace + 18s heartbeat grace) AND checking any pending queue.
    """
    st = get_active_job_state(lane=slot_key)
    if st.get("status") == "RUNNING":
        return True, st
    if len(load_lane_job_queue(slot_key)) > 0:
        return True, st
    return False, st


def _find_running_heavy_tcdb_slot() -> tuple[Optional[str], int]:
    """Returns `(slot_key, pid)` if any worker slot is currently running a TCDB rate-limited scraper."""
    for sk in PROCESS_LANES.keys():
        st = get_active_job_state(lane=sk)
        if st.get("status") == "RUNNING":
            if _is_tcdb_rate_limited_job(st.get("job_type", ""), title=st.get("title", "")):
                return sk, int(st.get("pid", 0))
    return None, 0


def _pick_first_idle_slot(preferred: Optional[str] = None) -> Optional[str]:
    """Returns the first genuinely idle worker slot across `slot_1` .. `slot_8`."""
    order = list(PROCESS_LANES.keys())
    if preferred and preferred in PROCESS_LANES:
        order = [preferred] + [s for s in order if s != preferred]
    for sk in order:
        is_busy, _ = _is_slot_currently_busy(sk)
        if not is_busy:
            return sk
    return None


def resolve_job_lane(job_type: str, explicit_lane: Optional[str] = None) -> str:
    if explicit_lane and str(explicit_lane).strip() in PROCESS_LANES:
        return str(explicit_lane).strip()
    idle = _pick_first_idle_slot()
    return idle or "slot_1"


def get_lane_state_file(lane: str) -> Path:
    s = str(lane or "slot_1").strip()
    base = base_lane_from_slot(s)
    suffix = s if s.startswith(base + "__p") else base
    return LOGS_DIR / f"job_state_{suffix}.json"


def get_lane_log_file(lane: str) -> Path:
    s = str(lane or "slot_1").strip()
    base = base_lane_from_slot(s)
    suffix = s if s.startswith(base + "__p") else base
    return LOGS_DIR / f"job_log_{suffix}.log"


def get_lane_queue_file(lane: str) -> Path:
    base = base_lane_from_slot(lane)
    return LOGS_DIR / f"job_queue_{base}.json"


def load_lane_job_queue(lane: str) -> list[dict]:
    ensure_directories()
    q_file = get_lane_queue_file(lane)
    if not q_file.exists():
        return []
    try:
        data = json.loads(q_file.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_lane_job_queue(lane: str, queue_list: list[dict]) -> list[dict]:
    ensure_directories()
    get_lane_queue_file(lane).write_text(json.dumps(queue_list, indent=2), encoding="utf-8")
    return queue_list


def enqueue_job_for_lane(job_type: str, title: str, payload: dict, lane: Optional[str] = None) -> dict:
    base_lane = base_lane_from_slot(resolve_job_lane(job_type, lane))
    curr_q = load_lane_job_queue(base_lane)
    q_item = {
        "queue_id": f"Q-{int(time.time() * 1000)}-{len(curr_q) + 1}",
        "lane": base_lane,
        "job_type": job_type,
        "title": title,
        "payload": payload,
        "queued_at": datetime.now().strftime("%H:%M:%S"),
    }
    curr_q.append(q_item)
    save_lane_job_queue(base_lane, curr_q)
    append_job_log(f"[QUEUED #{len(curr_q)}] '{title}' added to {PROCESS_LANES[base_lane]['short_name']} queue.", lane=base_lane)
    return q_item


def remove_queued_job(lane: str, queue_id: str) -> list[dict]:
    base_lane = base_lane_from_slot(lane)
    curr_q = load_lane_job_queue(base_lane)
    return save_lane_job_queue(base_lane, [item for item in curr_q if str(item.get("queue_id")) != str(queue_id)])


def clear_lane_job_queue(lane: str):
    save_lane_job_queue(base_lane_from_slot(lane), [])


def _default_idle_state(lane: str) -> dict:
    base_lane = base_lane_from_slot(lane)
    lane_meta = PROCESS_LANES.get(base_lane) or next(iter(PROCESS_LANES.values()))
    return {
        "lane": base_lane,
        "base_lane": base_lane,
        "status": "IDLE",
        "job_type": "none",
        "job_icon": lane_meta.get("icon", "⚡"),
        "process_name": "",
        "title": f"{lane_meta['short_name']}: Idle",
        "current": 0,
        "total": 1,
        "percent": 0,
        "current_item": "Ready",
        "updated_epoch": 0.0,
        "elapsed_seconds": 0.0,
        "eta_seconds": None,
        "updated_at": "",
        "pid": 0,
        "error_msg": "",
    }


def append_job_log(msg: str, lane: str = "slot_1", run_log_file: Optional[Path] = None):
    ensure_directories()
    clean = str(msg).rstrip("\r\n")
    if not clean:
        return
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {clean}\n"
    targets = [get_lane_log_file(lane), ACTIVE_JOB_LOG_FILE]
    if run_log_file is not None:
        targets.append(Path(run_log_file))
    for lf in targets:
        try:
            lf.parent.mkdir(parents=True, exist_ok=True)
            with open(lf, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


def get_all_lanes_state() -> dict[str, dict]:
    out = {}
    for lane_key in PROCESS_LANES.keys():
        primary = get_active_job_state(lane=lane_key)
        
        # Build clean primitives-only copies for parallel workers to prevent JSON circular references
        safe_primary = {k: v for k, v in primary.items() if k != "parallel_workers"}
        slots = [safe_primary]
        
        for s_idx in range(2, MAX_PARALLEL_SLOTS_PER_LANE + 1):
            slot_key = f"{lane_key}__p{s_idx}"
            if get_lane_state_file(slot_key).exists():
                st_s = get_active_job_state(lane=slot_key)
                if st_s.get("status") == "RUNNING" or (time.time() - float(st_s.get("updated_epoch", 0.0)) < 180.0):
                    clean_slot = {k: v for k, v in st_s.items() if k != "parallel_workers"}
                    slots.append(clean_slot)
                    
        running_slots = [s for s in slots if s.get("status") == "RUNNING"]
        primary["parallel_workers"] = slots
        primary["running_workers_count"] = len(running_slots)
        primary["queued_jobs"] = load_lane_job_queue(lane_key)
        out[lane_key] = primary
    return out


def get_active_job_logs(max_lines: int = 500, lane: Optional[str] = None) -> str:
    ensure_directories()
    log_f = get_lane_log_file(lane) if lane else ACTIVE_JOB_LOG_FILE
    if not log_f.exists():
        return "No log output recorded for this lane yet."
    try:
        lines = log_f.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:]) if lines else "Log is empty."
    except Exception as e:
        return f"Error reading log: {e}"


def stop_active_job(lane: Optional[str] = None) -> bool:
    state = get_active_job_state(lane=lane)
    target_lane = state.get("lane", lane or "slot_1")
    pid = int(state.get("pid", 0))
    if pid > 0 and _is_pid_running(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=6)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    write_job_state("STOPPED", state.get("job_type", "none"), state.get("title", "Stopped"), current=0, total=1, current_item="Stopped by user.", pid=0, lane=target_lane)
    append_job_log("🛑 Job stopped by user.", lane=target_lane)
    return True


def _find_available_parallel_slot(base_lane: str) -> str:
    b_lane = base_lane_from_slot(base_lane)
    primary = get_active_job_state(lane=b_lane)
    if primary.get("status") != "RUNNING" or not _is_pid_running(int(primary.get("pid", 0))):
        return b_lane
    for s_idx in range(2, MAX_PARALLEL_SLOTS_PER_LANE + 1):
        slot_key = f"{b_lane}__p{s_idx}"
        st_s = get_active_job_state(lane=slot_key)
        if st_s.get("status") != "RUNNING" or not _is_pid_running(int(st_s.get("pid", 0))):
            return slot_key
    return f"{b_lane}__p2"


def _is_any_slot_running_in_lane(base_lane: str) -> tuple[bool, int]:
    """Returns (is_busy, running_pid) if primary or any parallel worker slot in `base_lane` is active."""
    b_lane = base_lane_from_slot(base_lane)
    slots = [b_lane] + [f"{b_lane}__p{i}" for i in range(2, MAX_PARALLEL_SLOTS_PER_LANE + 1)]
    for sk in slots:
        st = get_active_job_state(lane=sk)
        if st.get("status") == "RUNNING":
            pid = int(st.get("pid", 0))
            if pid > 0 and _is_pid_running(pid):
                return True, pid
    return False, 0


def start_or_queue_background_job(
    job_type: str,
    title: str,
    payload: dict,
    lane: Optional[str] = None,
    execution_mode: str = "queue",
    is_queued_continuation: bool = False,
) -> dict:
    """
    Dynamic 6-Slot Parallel Worker Pool Dispatcher (`slot_1` .. `slot_6`):
      - Runs up to 6 independent background processes simultaneously!
      - Heavy TCDB checklist/image jobs (`HEAVY_TCDB_JOB_TYPES`) automatically queue behind any
        active heavy TCDB job so they never collide on Set_Checklists CSVs or rate limits.
      - Fast `ViewAll.cfm` Directory/Img% crawls, Scan Ingestion, Market Comps, Batch Listings,
        and System Maintenance automatically grab any free slot and run in parallel!
      - Discreet new tasks clear their slot's Live Monitor screen (`job_log_<slot>.log`) while
        queued continuations append cleanly. All output logs to `Logs\\Logs\\YYYYMMDD\\`.
    """
    ensure_directories()
    task_log_file = get_task_log_file(job_type)

    with _SLOT_DISPATCH_LOCK:
        # 1. ONLY TCDB web scrapers serialize behind each other (to respect TCDB's ~25 req/min rate limit).
        #    Every other process (non-TCDB scrapers, reprocessing, scan ingestion, pre-grading, local tools)
        #    bypasses this gate and immediately claims the first available idle parallel worker!
        if _is_tcdb_rate_limited_job(job_type, payload=payload, title=title) and not is_queued_continuation:
            heavy_slot, heavy_pid = _find_running_heavy_tcdb_slot()
            if heavy_slot is not None:
                enqueue_job_for_lane(job_type, title, payload, lane=heavy_slot)
                q_len = len(load_lane_job_queue(heavy_slot))
                append_job_log(
                    f"[QUEUED #{q_len} behind active TCDB scraper on {heavy_slot}] '{title}' waiting for PID {heavy_pid}.",
                    lane=heavy_slot,
                    run_log_file=task_log_file,
                )
                return {
                    "pid": heavy_pid,
                    "queued": True,
                    "queuePosition": q_len,
                    "lane": heavy_slot,
                    "taskLogFile": str(task_log_file),
                }

        # 2. Pick the first genuinely idle parallel worker across slot_1 .. slot_8
        explicit_s = str(lane or "").strip()
        preferred_s = explicit_s if explicit_s in PROCESS_LANES else None
        if is_queued_continuation and preferred_s:
            # Queued continuation already owns its assigned slot whose previous job just finished
            idle_slot = preferred_s
        else:
            idle_slot = _pick_first_idle_slot(preferred=preferred_s)

        if idle_slot is None:
            # All 8 parallel worker slots are genuinely busy -> queue onto the shortest-queue slot
            least_slot = min(PROCESS_LANES.keys(), key=lambda sk: len(load_lane_job_queue(sk)))
            st_busy = get_active_job_state(lane=least_slot)
            active_pid = int(st_busy.get("pid", 0))
            enqueue_job_for_lane(job_type, title, payload, lane=least_slot)
            q_len = len(load_lane_job_queue(least_slot))
            append_job_log(
                f"[QUEUED #{q_len} — All 8 Parallel Workers Busy] '{title}' queued on {least_slot}.",
                lane=least_slot,
                run_log_file=task_log_file,
            )
            return {
                "pid": active_pid,
                "queued": True,
                "queuePosition": q_len,
                "lane": least_slot,
                "taskLogFile": str(task_log_file),
            }

        target_slot = idle_slot
        base_lane = idle_slot

        lane_log_file = get_lane_log_file(target_slot)
        now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header_line = (
            f"========================================================================\n"
            f"=== [{PROCESS_LANES[base_lane]['short_name']}] {title} | Task: {job_type} | Started: {now_s} ===\n"
            f"=== Auto-Saved Verbose Log: {task_log_file} ===\n"
            f"=== Payload: {json.dumps(payload, default=str)[:800]} ===\n"
            f"========================================================================\n"
        )
        lane_write_mode = "a" if is_queued_continuation else "w"
        with open(lane_log_file, lane_write_mode, encoding="utf-8") as lf:
            if is_queued_continuation:
                lf.write("\n")
            lf.write(header_line)
        with open(task_log_file, "a", encoding="utf-8") as tf:
            tf.write("\n" + header_line)

        payload_file = LOGS_DIR / f"bg_job_payload_{target_slot}_{int(time.time()*1000)}.json"
        payload_file.write_text(
            json.dumps(
                {
                    "lane": target_slot,
                    "base_lane": base_lane,
                    "job_type": job_type,
                    "title": title,
                    "payload": payload,
                    "run_log_file": str(task_log_file),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        worker_python = str(TABULAS_VENV_PYTHON) if TABULAS_VENV_PYTHON.exists() else sys.executable
        cli_exe_path = (APP_DIR / "cli.py") if (APP_DIR / "cli.py").exists() else (BASE_DIR / "cli.py")
        cmd = [worker_python, "-u", str(cli_exe_path), "--bg-job", str(payload_file)]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0

        env = os.environ.copy()
        env["CARDS_BASE_DIR"] = str(BASE_DIR)
        env["TABULAS_SET_LIBRARY_DIR"] = str(SET_LIBRARY_ROOT)
        env["TABULAS_ARCHIVE_DIR"] = str(ARCHIVE_DIR)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        launch_ep = time.time()
        est_total = max(1, int(payload.get("estimated_total", 1)))
        write_job_state(
            "RUNNING",
            job_type,
            title,
            current=0,
            total=est_total,
            current_item=f"Launching worker -> {task_log_file.name}",
            start_epoch=launch_ep,
            pid=0,
            lane=target_slot,
        )

        log_fh = open(task_log_file, "a", encoding="utf-8")
        try:
            proc = subprocess.Popen(cmd, cwd=str(BASE_DIR), stdout=log_fh, stderr=log_fh, creationflags=creation_flags, env=env)
        finally:
            log_fh.close()

        # Attach child PID only if child has not already written newer progress or finished
        cur_st = get_active_job_state(lane=target_slot)
        if (
            cur_st.get("status") == "RUNNING"
            and int(cur_st.get("pid", 0)) == 0
            and abs(float(cur_st.get("start_epoch", 0.0)) - launch_ep) < 1.0
        ):
            write_job_state(
                "RUNNING",
                job_type,
                title,
                current=0,
                total=est_total,
                current_item=f"Starting PID {proc.pid} -> {task_log_file.name}",
                start_epoch=launch_ep,
                pid=proc.pid,
                lane=target_slot,
            )
        return {
            "pid": proc.pid,
            "queued": False,
            "queuePosition": 0,
            "lane": target_slot,
            "taskLogFile": str(task_log_file),
        }


def start_background_job(
    job_type: str,
    title: str,
    payload: dict,
    lane: Optional[str] = None,
    execution_mode: str = "queue",
    is_queued_continuation: bool = False,
) -> int:
    res = start_or_queue_background_job(
        job_type=job_type,
        title=title,
        payload=payload,
        lane=lane,
        execution_mode=execution_mode,
        is_queued_continuation=is_queued_continuation,
    )
    return int(res.get("pid", 0))


def _query_windows_task_status(task_name: str) -> tuple[str, str]:
    """Queries live OS status and Next Run Time from Windows Task Scheduler via schtasks."""
    if os.name != "nt" or not task_name:
        return "Local Registry Only", "—"
    try:
        res = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=6,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return "Not Registered in OS", "—"
        reader = csv.reader(io.StringIO(res.stdout.strip()))
        row = next(reader, None)
        if row and len(row) >= 3:
            next_run = str(row[1]).strip() or "—"
            os_stat = str(row[2]).strip() or "Ready"
            icon = "🟢" if os_stat.lower() in ("ready", "running") else "⏸️"
            return f"{icon} {os_stat}", next_run
    except Exception:
        pass
    return "Not Registered in OS", "—"


def load_all_scheduled_jobs(query_live_os_status: bool = True) -> list[dict]:
    ensure_directories()
    if not UNIFIED_SCHEDULES_FILE.exists():
        legacy_sched = SET_LIBRARY_CACHE_DIR / "unified_schedules_registry.json"
        if legacy_sched.exists():
            try:
                UNIFIED_SCHEDULES_FILE.write_text(legacy_sched.read_text(encoding="utf-8-sig"), encoding="utf-8")
            except Exception:
                pass
    jobs = []
    if UNIFIED_SCHEDULES_FILE.exists():
        try:
            loaded = json.loads(UNIFIED_SCHEDULES_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                jobs = loaded
        except Exception:
            jobs = []

    if query_live_os_status and os.name == "nt":
        for j in jobs:
            t_name = str(j.get("Task_Name") or "").strip()
            if t_name:
                os_stat, next_run = _query_windows_task_status(t_name)
                j["OS_Status"] = os_stat
                j["Next_Run"] = next_run
    return jobs


def save_and_sync_all_scheduled_jobs(jobs_list: list[dict]) -> tuple[list[dict], list[str]]:
    ensure_directories()
    prev_jobs = load_all_scheduled_jobs(query_live_os_status=False)
    prev_task_names = {str(j.get("Task_Name") or "").strip() for j in prev_jobs if str(j.get("Task_Name") or "").strip()}

    worker_py = str(TABULAS_VENV_PYTHON) if TABULAS_VENV_PYTHON.exists() else sys.executable
    cli_script = str((APP_DIR / "cli.py") if (APP_DIR / "cli.py").exists() else (BASE_DIR / "cli.py"))
    sync_msgs: list[str] = []
    new_task_names: set[str] = set()
    cleaned_jobs: list[dict] = []

    for idx, j in enumerate(jobs_list or [], 1):
        p_mode = str(j.get("Pipeline_Mode") or "auto_scrape").strip()
        cat_meta = SCHEDULED_PIPELINE_CATALOG.get(p_mode, SCHEDULED_PIPELINE_CATALOG["auto_scrape"])
        t_name = re.sub(r"[^A-Za-z0-9_\-]", "_", str(j.get("Task_Name") or f"{cat_meta['default_task_name']}_{idx}").strip())
        freq = str(j.get("Frequency") or "DAILY").strip().upper()
        if freq not in ("DAILY", "WEEKLY", "HOURLY", "MONTHLY", "ONCE"):
            freq = "DAILY"
        t_24h = str(j.get("Time_24h") or "03:00").strip()
        if not re.match(r"^\d{1,2}:\d{2}$", t_24h):
            t_24h = "03:00"
        elif len(t_24h) == 4:
            t_24h = "0" + t_24h
        enabled = bool(j.get("Enabled", False))
        new_task_names.add(t_name)

        os_stat = "⏸️ Disabled"
        next_run = "—"
        if os.name == "nt":
            if enabled:
                task_cmd = f'"{worker_py}" "{cli_script}" {cat_meta["cli_flag"]}'
                cmd = ["schtasks", "/Create", "/F", "/SC", freq, "/TN", t_name, "/TR", task_cmd, "/ST", t_24h]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    os_stat, next_run = _query_windows_task_status(t_name)
                    sync_msgs.append(f"✅ Synced '{t_name}' ({freq} @ {t_24h})")
                else:
                    err_s = (res.stderr or res.stdout or "Unknown schtasks error").strip()
                    os_stat = f"⚠️ Sync Error"
                    sync_msgs.append(f"⚠️ Failed '{t_name}': {err_s[:120]}")
            else:
                subprocess.run(["schtasks", "/Delete", "/TN", t_name, "/F"], capture_output=True, text=True, timeout=6)
                sync_msgs.append(f"⏸️ Disabled/Removed OS task '{t_name}'")

        cleaned_jobs.append({
            "Schedule_ID": str(j.get("Schedule_ID") or f"SCHED-{idx:03d}").strip(),
            "Task_Name": t_name,
            "Pipeline_Mode": p_mode,
            "Activity_Label": str(j.get("Activity_Label") or cat_meta["label"]).strip(),
            "Frequency": freq,
            "Time_24h": t_24h,
            "Enabled": enabled,
            "OS_Status": os_stat,
            "Next_Run": next_run,
            "Notes": str(j.get("Notes") or "").strip(),
        })

    # Delete any Windows tasks that were removed from the schedule list
    if os.name == "nt":
        for removed_tn in sorted(prev_task_names - new_task_names):
            subprocess.run(["schtasks", "/Delete", "/TN", removed_tn, "/F"], capture_output=True, text=True, timeout=6)
            sync_msgs.append(f"🗑️ Deleted removed OS task '{removed_tn}'")

    UNIFIED_SCHEDULES_FILE.write_text(json.dumps(cleaned_jobs, indent=2), encoding="utf-8")
    return cleaned_jobs, sync_msgs or [f"Saved {len(cleaned_jobs)} scheduled job(s)."]


def run_startup_maintenance(keep_logs_days: int = 30, keep_recent_updates: int = 5, lane: Optional[str] = None) -> dict:
    """
    Runs startup & periodic housekeeping cleanly on an idle worker slot:
      1. Archives daily log folders (`Logs\\Logs\\YYYYMMDD\\`) & reports older than 30 days to `F:\\Tabulas Archive\\Logs\\`.
      2. Archives older update packages & snapshots beyond the 5 most recent to `F:\\Tabulas Archive\\Updates\\`.
      3. Cleans orphaned RUNNING states (dead PIDs) & stale `bg_job_payload_*.json` files.
    """
    ensure_directories()
    start_ep = time.time()
    log_file = get_task_log_file("system_startup")
    explicit_lane = str(lane or "").strip()
    if explicit_lane and explicit_lane in PROCESS_LANES:
        sys_slot = explicit_lane
    else:
        sys_slot = _pick_first_idle_slot(preferred="slot_8") or "slot_8"
        clear_lane_monitor_log(sys_slot)

    def _sys_log(msg: str, cur: int, tot: int):
        append_job_log(msg, lane=sys_slot, run_log_file=log_file)
        write_job_state("RUNNING", "system_startup", "System Maintenance & Housekeeping", current=cur, total=tot, current_item=msg, start_epoch=start_ep, pid=os.getpid(), lane=sys_slot)

    _sys_log("🛠️ Running Tabulas System Maintenance...", 0, 3)

    # Self-heal any accidentally double-nested folders inside Reference_Library\ (from v0.24.0-beta.1..3)
    rescued_nested_imgs = 0
    for nested_name, real_target in (
        ("Reference_Library", REFERENCE_TEMPLATES_DIR),
        ("_My_Collection", REVIEWED_CARDS_DIR),
        ("Unprocessed_Cards", UNPROCESSED_CARDS_DIR),
    ):
        nested_dir = REFERENCE_TEMPLATES_DIR / nested_name
        if nested_dir.exists() and nested_dir.is_dir():
            try:
                if nested_dir.resolve() != real_target.resolve():
                    for f_item in list(nested_dir.rglob("*")):
                        if f_item.is_file():
                            rel_p = f_item.relative_to(nested_dir)
                            dst_p = real_target / rel_p
                            dst_p.parent.mkdir(parents=True, exist_ok=True)
                            if not dst_p.exists():
                                shutil.move(str(f_item), str(dst_p))
                                rescued_nested_imgs += 1
                            else:
                                f_item.unlink()
                    shutil.rmtree(nested_dir, ignore_errors=True)
            except Exception as heal_e:
                append_job_log(f"[!] Nested library cleanup note ({nested_name}): {heal_e}", lane=sys_slot, run_log_file=log_file)
    if rescued_nested_imgs > 0:
        append_job_log(
            f"🩹 Rescued {rescued_nested_imgs:,} image(s) from nested Reference_Library\\ into {REFERENCE_TEMPLATES_DIR} and removed stray folders.",
            lane=sys_slot,
            run_log_file=log_file,
        )

    archived_log_dirs = 0
    archived_reports = 0
    cutoff_dt = datetime.now() - timedelta(days=keep_logs_days)
    cutoff_ymd = cutoff_dt.strftime("%Y%m%d")

    if DAILY_LOGS_ROOT.exists():
        for d in sorted(DAILY_LOGS_ROOT.iterdir()):
            if d.is_dir() and re.fullmatch(r"\d{8}", d.name) and d.name < cutoff_ymd:
                dst_d = ARCHIVE_LOGS_DIR / f"{d.name[:4]}-{d.name[4:6]}" / d.name
                try:
                    dst_d.parent.mkdir(parents=True, exist_ok=True)
                    if dst_d.exists():
                        shutil.rmtree(dst_d, ignore_errors=True)
                    shutil.move(str(d), str(dst_d))
                    archived_log_dirs += 1
                except Exception:
                    pass

    if REPORTS_DIR.exists():
        cutoff_ep = cutoff_dt.timestamp()
        for rf in list(REPORTS_DIR.iterdir()):
            if rf.is_file() and rf.stat().st_mtime < cutoff_ep:
                dst_r = ARCHIVE_LOGS_DIR / "Reports" / rf.name
                try:
                    dst_r.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(rf), str(dst_r))
                    archived_reports += 1
                except Exception:
                    pass
    _sys_log(f"Archived {archived_log_dirs} old log folder(s) & {archived_reports} report(s) (> {keep_logs_days}d) -> {ARCHIVE_LOGS_DIR}", 1, 3)

    archived_pkgs, archived_snaps = 0, 0
    try:
        import updater
        upd_arc = updater.archive_old_updates(keep_recent=keep_recent_updates)
        archived_pkgs = int(upd_arc.get("archived_packages", 0))
        archived_snaps = int(upd_arc.get("archived_snapshots", 0))
    except Exception as e:
        append_job_log(f"[!] Update archiving skipped: {e}", lane=sys_slot, run_log_file=log_file)
    _sys_log(f"Update retention (keep {keep_recent_updates}): archived {archived_pkgs} package(s) & {archived_snaps} snapshot(s) -> F:\\Tabulas Archive\\Updates", 2, 3)

    cleaned_payloads = 0
    cleaned_orphans = 0
    now_ep = time.time()
    for pf in list(LOGS_DIR.glob("bg_job_payload_*.json")):
        try:
            if now_ep - pf.stat().st_mtime > 1800:
                pf.unlink()
                cleaned_payloads += 1
        except Exception:
            pass
    for lk in PROCESS_LANES.keys():
        if lk == sys_slot:
            continue
        sf = get_lane_state_file(lk)
        if sf.exists():
            try:
                st_d = json.loads(sf.read_text(encoding="utf-8"))
                if st_d.get("status") == "RUNNING" and not _is_pid_running(int(st_d.get("pid", 0))):
                    st_d["status"] = "IDLE"
                    st_d["current_item"] = "Cleaned orphaned state on startup"
                    sf.write_text(json.dumps(st_d, indent=2), encoding="utf-8")
                    cleaned_orphans += 1
            except Exception:
                pass

    # Retire obsolete one-time-use scripts to F:\Tabulas Archive\Legacy_Cleanup\Retired_Scripts\
    retired_scripts_cnt = 0
    retired_dst_dir = ARCHIVE_DIR / "Legacy_Cleanup" / "Retired_Scripts"
    obsolete_names = (
        "migrate_set_library.py",
        "migrate_to_tabulas_hub.py",
        "reorganize_tabulas_workspace.py",
        "server.js",
        "api_server.py",
        "cleanup_and_init.py",
        "File_List.py",
    )
    for search_root in (BASE_DIR, APP_DIR, APP_DIR / "Tools"):
        if not search_root.exists():
            continue
        for fname in obsolete_names:
            cand_f = search_root / fname
            if cand_f.exists() and cand_f.is_file():
                try:
                    retired_dst_dir.mkdir(parents=True, exist_ok=True)
                    dst_f = retired_dst_dir / fname
                    if dst_f.exists():
                        dst_f.unlink()
                    shutil.move(str(cand_f), str(dst_f))
                    retired_scripts_cnt += 1
                except Exception:
                    pass
    tools_dir_cand = APP_DIR / "Tools"
    if tools_dir_cand.exists() and tools_dir_cand.is_dir():
        try:
            if not any(tools_dir_cand.iterdir()):
                tools_dir_cand.rmdir()
        except Exception:
            pass
    if retired_scripts_cnt > 0:
        append_job_log(
            f"🧹 Retired {retired_scripts_cnt} obsolete one-time script(s) -> {retired_dst_dir}",
            lane=sys_slot,
            run_log_file=log_file,
        )

    summary = f"System maintenance complete: {archived_log_dirs} log dir(s), {archived_pkgs} update(s), {archived_snaps} snapshot(s) archived; {cleaned_orphans} orphan(s) cleared."
    append_job_log(f"✅ {summary}", lane=sys_slot, run_log_file=log_file)
    write_job_state("COMPLETED", "system_startup", "System Maintenance & Housekeeping", current=3, total=3, current_item=summary, start_epoch=start_ep, pid=0, lane=sys_slot)
    return {
        "archived_log_dirs": archived_log_dirs,
        "archived_reports": archived_reports,
        "archived_packages": archived_pkgs,
        "archived_snapshots": archived_snaps,
        "cleaned_payloads": cleaned_payloads,
        "cleaned_orphans": cleaned_orphans,
        "log_file": str(log_file),
        "message": summary,
    }


def _is_pid_running(pid: int) -> bool:
    """
    Zero-subprocess Win32 native PID liveness check (`OpenProcess` + `GetExitCodeProcess`).
    Completes in <0.05ms and never times out or throws PermissionError under heavy CPU load.
    """
    try:
        pid_i = int(pid or 0)
        if pid_i <= 0:
            return False
        if os.name == "nt":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            k32 = ctypes.windll.kernel32
            handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_i)
            if not handle:
                err = ctypes.GetLastError()
                # ERROR_ACCESS_DENIED (5) means process exists under elevated/protected token
                return err == 5
            try:
                exit_code = ctypes.c_ulong()
                if k32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True
            finally:
                k32.CloseHandle(handle)
        os.kill(pid_i, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _atomic_write_json_file(target_path: Path, data: dict):
    """Writes JSON atomically via unique PID+thread `.tmp` + retry `os.replace()` so UI pollers never read a torn 0-byte file."""
    try:
        atomic_write_text(target_path, json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_active_job_state(lane: Optional[str] = None) -> dict:
    """Transient-lock-resilient job state reader with 20s startup grace window (prevents phantom Idle flickers)."""
    ensure_directories()
    raw_lane = str(lane or "slot_1").strip()
    base_lane = base_lane_from_slot(raw_lane)
    clean_lane = raw_lane if raw_lane.startswith(base_lane + "__p") else base_lane
    sf = get_lane_state_file(clean_lane)
    if not sf.exists():
        return _default_idle_state(clean_lane)

    state = None
    for attempt in range(3):
        try:
            raw = sf.read_text(encoding="utf-8-sig")
            if raw.strip():
                state = json.loads(raw)
                break
        except Exception:
            time.sleep(0.025 * (attempt + 1))

    if not isinstance(state, dict):
        return _default_idle_state(clean_lane)

    if state.get("status") == "RUNNING":
        now_t = time.time()
        s_ep = float(state.get("start_epoch", now_t))
        upd_ep = float(state.get("updated_epoch", s_ep))
        pid_val = int(state.get("pid", 0))
        in_startup_grace = (now_t - s_ep) < 20.0
        recently_beat = (now_t - upd_ep) < 18.0
        if pid_val > 0 and not _is_pid_running(pid_val) and not in_startup_grace and not recently_beat:
            state["status"] = "INTERRUPTED"
            state["pid"] = 0
            state["current_item"] = "Worker exited unexpectedly."
            _atomic_write_json_file(sf, state)
        else:
            state["elapsed_seconds"] = round(max(0.0, now_t - s_ep), 1)
            if state.get("sub_start_epoch"):
                state["sub_elapsed_seconds"] = round(max(0.0, now_t - float(state["sub_start_epoch"])), 1)
    return state


def write_job_state(
    status: str,
    job_type: str,
    title: str,
    current: int = 0,
    total: int = 1,
    current_item: str = "",
    start_epoch: Optional[float] = None,
    pid: int = 0,
    error_msg: str = "",
    lane: str = "slot_1",
    sub_current: int = 0,
    sub_total: int = 0,
    sub_label: str = "",
    sub_start_epoch: Optional[float] = None,
    active_set_name: str = "",
    set_index: int = 0,
    total_sets: int = 0,
    completed_subsets: int = 0,
    total_subsets: int = 0,
    completed_cards: int = 0,
    total_cards: int = 0,
    cards_per_sec: float = 0.0,
    eta_override: Optional[float] = None,
    sub_eta_override: Optional[float] = None,
    percent_override: Optional[float] = None,
):
    """Atomic job state writer preventing half-written JSON reads by the live UI poller."""
    ensure_directories()
    now_ep = time.time()
    s_ep = float(start_epoch or now_ep)
    elapsed = max(0.0, now_ep - s_ep)
    tot = max(1, int(total))
    cur = min(tot, max(0, int(current)))
    if status == "COMPLETED":
        pct = 100
    elif percent_override is not None:
        pct = min(99, max(0, int(round(float(percent_override)))))
    else:
        pct = min(99, int(round(100.0 * cur / tot)))

    eta_sec = eta_override
    if eta_sec is None and status == "RUNNING" and cur > 0 and tot > cur and elapsed > 0.5:
        eta_sec = round((elapsed / float(cur)) * float(tot - cur), 1)

    sub_tot = max(0, int(sub_total))
    sub_cur = min(sub_tot, max(0, int(sub_current))) if sub_tot > 0 else 0
    sub_pct = (100 if status == "COMPLETED" else min(99, int(round(100.0 * sub_cur / sub_tot)))) if sub_tot > 0 else 0
    sub_elapsed_val = round(max(0.0, now_ep - float(sub_start_epoch)), 1) if sub_start_epoch else 0.0
    sub_eta_sec = sub_eta_override
    if sub_eta_sec is None and status == "RUNNING" and sub_tot > sub_cur > 0 and sub_start_epoch:
        if sub_elapsed_val > 0.3:
            sub_eta_sec = round((sub_elapsed_val / float(sub_cur)) * float(sub_tot - sub_cur), 1)

    state_payload = {
        "lane": lane,
        "base_lane": base_lane_from_slot(lane),
        "status": status,
        "job_type": job_type,
        "job_icon": JOB_TYPE_ICON_MAP.get(str(job_type), "⚡"),
        "process_name": title,
        "title": title,
        "current": cur,
        "total": tot,
        "percent": pct,
        "active_set_name": str(active_set_name or "")[:120],
        "set_index": int(set_index or 0),
        "total_sets": int(total_sets or 0),
        "completed_subsets": int(completed_subsets or 0),
        "total_subsets": int(total_subsets or 0),
        "completed_cards": int(completed_cards or 0),
        "total_cards": int(total_cards or 0),
        "cards_per_sec": round(float(cards_per_sec or 0.0), 3),
        "current_item": str(current_item)[:180],
        "start_epoch": s_ep,
        "updated_epoch": now_ep,
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": eta_sec,
        "sub_current": sub_cur,
        "sub_total": sub_tot,
        "sub_percent": sub_pct,
        "sub_name": str(sub_label)[:120],
        "sub_label": str(sub_label)[:120],
        "sub_start_epoch": float(sub_start_epoch) if sub_start_epoch else None,
        "sub_elapsed_seconds": sub_elapsed_val,
        "sub_eta_seconds": sub_eta_sec,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pid": int(pid),
        "error_msg": str(error_msg),
    }
    _atomic_write_json_file(get_lane_state_file(lane), state_payload)
    _atomic_write_json_file(ACTIVE_JOB_STATE_FILE, state_payload)


def _fmt_vis_pct(rec: dict) -> str:
    try:
        v = float(str(rec.get("Template_Similarity") or "0"))
        return f"{int(round(v * 100.0))}%" if v > 0 else "N/A"
    except Exception:
        return "N/A"


def run_background_job_from_file(payload_path: Path):
    payload_path = Path(payload_path)
    if not payload_path.exists():
        return
    try:
        job_spec = json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception:
        return
    finally:
        try:
            payload_path.unlink()
        except Exception:
            pass

    target_lane = str(job_spec.get("lane") or "slot_1")
    job_type = str(job_spec.get("job_type") or "task")
    title = str(job_spec.get("title") or job_type)
    payload = dict(job_spec.get("payload") or {})
    run_log_file_str = str(job_spec.get("run_log_file") or "").strip()
    run_log_path = Path(run_log_file_str) if run_log_file_str else None
    start_ep = time.time()
    my_pid = os.getpid()
    learner = get_rate_learner()
    state_tracker = {
        "current": 0,
        "total": max(1, int(payload.get("estimated_total", 1))),
        "active_set_name": "",
        "active_set_key": "",
        "set_index": 0,
        "total_sets": 0,
        "completed_subsets": 0,
        "total_subsets": 0,
        "completed_cards": 0,
        "total_cards": 0,
        "est_remaining_dl_cards": None,
        "sub_current": 0,
        "sub_total": 0,
        "sub_label": "",
        "sub_start_epoch": None,
        "mode_key": "",
        "structured_active": False,
    }

    def _structured_progress_cb(ev: dict):
        state_tracker["structured_active"] = True
        for k in (
            "active_set_name", "active_set_key", "set_index", "total_sets",
            "completed_subsets", "total_subsets", "completed_cards", "total_cards",
            "est_remaining_dl_cards", "sub_current", "sub_total", "sub_start_epoch", "mode_key",
        ):
            if k in ev and ev[k] is not None:
                state_tracker[k] = ev[k]
        if ev.get("sub_name") is not None:
            state_tracker["sub_label"] = str(ev["sub_name"])

        tot_cards = int(state_tracker["total_cards"] or 0)
        comp_cards = int(state_tracker["completed_cards"] or 0)
        tot_subs = max(1, int(state_tracker["total_subsets"] or 1))
        comp_subs = int(state_tracker["completed_subsets"] or 0)
        s_cur = int(state_tracker["sub_current"] or 0)
        s_tot = max(1, int(state_tracker["sub_total"] or 1))
        now_ep = time.time()
        run_el = max(0.0, now_ep - start_ep)
        sub_el = max(0.0, now_ep - float(state_tracker["sub_start_epoch"])) if state_tracker["sub_start_epoch"] else 0.0
        mk_str = str(state_tracker["mode_key"] or "checklist_and_images")

        if tot_cards > 0:
            overall_pct = min(99.5, (float(comp_cards) / float(tot_cards)) * 100.0)
            t1_eta, t2_eta, cps = learner.estimate_card_based_etas(
                mode_key=mk_str,
                completed_cards=comp_cards,
                total_cards=tot_cards,
                run_elapsed_sec=run_el,
                sub_current=s_cur,
                sub_total=int(state_tracker["sub_total"] or 0),
                sub_elapsed_sec=sub_el,
                active_set_key=str(state_tracker["active_set_key"] or ""),
                est_remaining_dl_cards=state_tracker["est_remaining_dl_cards"],
            )
            cur_primary, tot_primary = comp_cards, tot_cards
        else:
            frac_sub = min(1.0, float(s_cur) / float(s_tot)) if state_tracker["sub_total"] else 0.0
            overall_pct = min(99.5, ((float(comp_subs) + frac_sub) / float(tot_subs)) * 100.0)
            t1_eta, t2_eta = learner.estimate_learning_etas(
                mode_key=mk_str,
                completed_subsets=comp_subs,
                total_subsets=tot_subs,
                run_elapsed_sec=run_el,
                sub_current=s_cur,
                sub_total=int(state_tracker["sub_total"] or 0),
                sub_elapsed_sec=sub_el,
            )
            cps = 0.0
            cur_primary, tot_primary = comp_subs, tot_subs

        write_job_state(
            "RUNNING",
            job_type,
            title,
            current=cur_primary,
            total=tot_primary,
            current_item=str(ev.get("current_item") or ""),
            start_epoch=start_ep,
            pid=my_pid,
            lane=target_lane,
            sub_current=s_cur,
            sub_total=int(state_tracker["sub_total"] or 0),
            sub_label=state_tracker["sub_label"],
            sub_start_epoch=state_tracker["sub_start_epoch"],
            active_set_name=str(state_tracker["active_set_name"] or ""),
            set_index=int(state_tracker["set_index"] or 0),
            total_sets=int(state_tracker["total_sets"] or 0),
            completed_subsets=comp_subs,
            total_subsets=tot_subs,
            completed_cards=comp_cards,
            total_cards=tot_cards,
            cards_per_sec=cps,
            eta_override=t1_eta,
            sub_eta_override=t2_eta,
            percent_override=overall_pct,
        )

    def _worker_log_cb(msg: str):
        raw_s = str(msg)
        append_job_log(raw_s, lane=target_lane, run_log_file=run_log_path)
        if state_tracker["structured_active"]:
            return
        m_prog = re.search(r"\[(\d+)\s*/\s*(\d+)\]", raw_s)
        if m_prog:
            c_i, t_i = int(m_prog.group(1)), int(m_prog.group(2))
            if t_i >= c_i > 0:
                is_indented_sub = raw_s.startswith("  ") or raw_s.lstrip().startswith("↳")
                if is_indented_sub:
                    if state_tracker["sub_total"] != t_i or c_i <= 1:
                        state_tracker["sub_start_epoch"] = time.time()
                    state_tracker["sub_current"] = c_i
                    state_tracker["sub_total"] = t_i
                    state_tracker["sub_label"] = raw_s.strip()[:90]
                else:
                    state_tracker["current"] = c_i
                    state_tracker["total"] = max(1, t_i)
                    state_tracker["sub_current"] = 0
                    state_tracker["sub_total"] = 0
                    state_tracker["sub_label"] = ""
                    state_tracker["sub_start_epoch"] = None
        write_job_state(
            "RUNNING", job_type, title, current=state_tracker["current"], total=state_tracker["total"],
            current_item=raw_s.strip()[:160], start_epoch=start_ep, pid=my_pid, lane=target_lane,
            sub_current=state_tracker["sub_current"], sub_total=state_tracker["sub_total"],
            sub_label=state_tracker["sub_label"], sub_start_epoch=state_tracker["sub_start_epoch"],
        )

    write_job_state(
        "RUNNING", job_type, title,
        current=0, total=state_tracker["total"], current_item="Worker active...",
        start_epoch=start_ep, pid=my_pid, lane=target_lane,
    )
    _hb_stop = threading.Event()

    def _heartbeat_loop():
        sf_hb = get_lane_state_file(target_lane)
        while not _hb_stop.wait(5.0):
            try:
                if sf_hb.exists():
                    st_now = json.loads(sf_hb.read_text(encoding="utf-8-sig"))
                    if st_now.get("status") == "RUNNING" and int(st_now.get("pid", 0)) in (my_pid, 0):
                        now_h = time.time()
                        st_now["pid"] = my_pid
                        st_now["updated_epoch"] = now_h
                        st_now["elapsed_seconds"] = round(max(0.0, now_h - float(st_now.get("start_epoch", start_ep))), 1)
                        st_now["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        _atomic_write_json_file(sf_hb, st_now)
            except Exception:
                pass

    threading.Thread(target=_heartbeat_loop, name=f"hb-{target_lane}", daemon=True).start()

    set_log_callback(_worker_log_cb)
    set_progress_callback(_structured_progress_cb)

    # Initialize GPU acceleration (DirectML/CUDA OCR + OpenCL UMat) & claim VRAM guardrail slot for vision jobs
    init_worker_compute_backend(job_type=job_type, log_cb=_worker_log_cb)

    try:
        if job_type in ("system_startup", "system_maintenance"):
            run_startup_maintenance(lane=target_lane)
        elif job_type == "scan_ingest":
            _worker_log_cb(f"🔍 Batch Scan Processor worker initialized (PID {my_pid}). Discovering incoming PDF batches...")
            if "enable_cardsight_fallback" in payload:
                RUNTIME_CONFIG["enable_cardsight_fallback"] = bool(payload.get("enable_cardsight_fallback", True))
            target_batch_names = set(payload.get("batch_names") or [])
            discovered = find_unarchived_scan_batches()
            batches_to_run = [(b_n, b_d, b_p) for b_n, b_d, b_p in discovered if not target_batch_names or b_n in target_batch_names]

            if not batches_to_run:
                _worker_log_cb("⚠️ No matching PDF scan batches found in Incoming_Scans. Nothing to ingest.")
            else:
                from Core.config import BATCHES_DIR
                # Pre-check existing batch manifests so completed batches are skipped and ETA reflects true remaining PDFs
                active_batches_to_run = []
                total_remaining_pdfs = 0
                for b_n, b_d, b_p in batches_to_run:
                    b_out_dir = BATCHES_DIR / sanitize_filename_part(b_n)
                    b_man = b_out_dir / "Batch_Inventory_Manifest.csv"
                    b_cp = b_out_dir / ".processed_pdfs.json"
                    rem_est = len(b_p)
                    if b_man.exists():
                        try:
                            b_df_chk = pd.read_csv(b_man, dtype=str, keep_default_na=False)
                            done_rows = int((b_df_chk["SKU"].astype(str).str.strip() != "").sum()) if "SKU" in b_df_chk.columns else len(b_df_chk)
                            if b_cp.exists():
                                cp_m = json.loads(b_cp.read_text(encoding="utf-8-sig"))
                                if isinstance(cp_m, dict):
                                    rem_est = sum(1 for p in b_p if p.name.lower() not in {str(k).lower() for k in cp_m.keys()})
                                else:
                                    rem_est = max(0, len(b_p) - done_rows)
                            else:
                                rem_est = max(0, len(b_p) - done_rows)
                        except Exception:
                            rem_est = len(b_p)
                    if rem_est == 0 and b_man.exists():
                        _worker_log_cb(
                            f"⏭️ [SKIP COMPLETE BATCH] '{b_n}': All {len(b_p):,} PDF(s) already in Batch_Inventory_Manifest.csv — skipping!"
                        )
                    else:
                        active_batches_to_run.append((b_n, b_d, b_p, rem_est))
                        total_remaining_pdfs += rem_est

                batches_to_run = [(x[0], x[1], x[2]) for x in active_batches_to_run]
                total_pdfs_all = max(1, total_remaining_pdfs)
                locked_set_arg = str(payload.get("locked_set") or "").strip()
                locked_sub_arg = str(payload.get("locked_subset") or "").strip()
                _worker_log_cb(
                    f"📂 Active batch(es) to ingest/resume: {len(batches_to_run)} ({total_remaining_pdfs:,} remaining PDFs) | "
                    f"Locked Set: {locked_set_arg or 'Auto'} | Locked Subset: {locked_sub_arg or 'Auto'}"
                )

                # Fast-load individual Set Checklist CSV when a Set is pre-selected (<0.2s vs full Master Checklist!)
                chk_target_path = CHECKLIST_PATH
                if locked_set_arg:
                    cand_set_csv = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(locked_set_arg)}.csv"
                    if cand_set_csv.exists():
                        chk_target_path = cand_set_csv
                _worker_log_cb(f"📚 Loading checklist from {chk_target_path.name}...")
                t_chk = time.time()
                root_df, parallels_map, ordinary_roots, print_run_map = load_master_checklist(chk_target_path)
                _worker_log_cb(f"  ✅ Checklist ready ({len(root_df):,} unique card roots in {time.time() - t_chk:.2f}s).")

                _worker_log_cb("🗂️ Fast-indexing Reference Library & Collection image paths (lazy on-demand vectors)...")
                template_catalog, reviewed_by_card, reviewed_parallels = index_set_templates_and_reviewed_cards(
                    REFERENCE_TEMPLATES_DIR,
                    REVIEWED_CARDS_DIR,
                    locked_set=locked_set_arg or None,
                    lazy_vectors=True,
                    log_cb=_worker_log_cb,
                )

                total_b = len(batches_to_run)
                cards_done_all = 0
                state_tracker["total"] = max(1, total_pdfs_all)

                for b_idx, (b_name, b_dir, b_pdfs) in enumerate(batches_to_run, 1):
                    batch_t0 = time.time()
                    _worker_log_cb(f"🚀 Batch {b_idx}/{total_b}: '{b_name}' ({len(b_pdfs):,} PDFs) — Starting OCR & Pre-Grading...")

                    def _on_scan_card(c_i: int, t_i: int, rec: dict, _bn=b_name, _bi=b_idx, _bt0=batch_t0):
                        nonlocal cards_done_all
                        cards_done_all += 1
                        tot_all_dyn = max(total_pdfs_all, cards_done_all)
                        rev_badge = " | 🚩 Review" if str(rec.get("Needs_Review", "")).lower() == "true" else ""
                        vis_pct_str = _fmt_vis_pct(rec)
                        card_line = (
                            f"[{c_i}/{t_i}] SKU {rec.get('SKU','')} — {rec.get('Set','')} {rec.get('Card_Number','')} "
                            f"{rec.get('Player','')} [{rec.get('Subset_Parallel','Base')}] | "
                            f"PSA {rec.get('Est_PSA','')} / BGS {rec.get('Est_BGS','')} | OCR {rec.get('OCR_Confidence','0')} | Vis {vis_pct_str}{rev_badge}"
                        )
                        append_job_log(f"  {card_line}", lane=target_lane, run_log_file=run_log_path)
                        now_ep = time.time()
                        run_el = max(0.1, now_ep - start_ep)
                        b_el = max(0.1, now_ep - _bt0)
                        cps = round(cards_done_all / run_el, 3)
                        t1_eta = round((run_el / float(cards_done_all)) * max(0, tot_all_dyn - cards_done_all), 1)
                        t2_eta = round((b_el / float(max(1, c_i))) * max(0, t_i - c_i), 1)
                        write_job_state(
                            "RUNNING",
                            job_type,
                            title,
                            current=cards_done_all,
                            total=tot_all_dyn,
                            current_item=card_line,
                            start_epoch=start_ep,
                            pid=my_pid,
                            lane=target_lane,
                            sub_current=c_i,
                            sub_total=t_i,
                            sub_label=_bn,
                            sub_start_epoch=_bt0,
                            active_set_name=str(rec.get("Set") or locked_set_arg or _bn),
                            set_index=_bi,
                            total_sets=total_b,
                            completed_cards=cards_done_all,
                            total_cards=tot_all_dyn,
                            cards_per_sec=cps,
                            eta_override=t1_eta,
                            sub_eta_override=t2_eta,
                            percent_override=min(99.5, (float(cards_done_all) / float(tot_all_dyn)) * 100.0),
                        )

                    process_single_batch(
                        batch_name=b_name,
                        source_folder=b_dir,
                        pdf_files=b_pdfs,
                        root_df=root_df,
                        parallels_map=parallels_map,
                        ordinary_roots=ordinary_roots,
                        print_run_map=print_run_map,
                        template_catalog=template_catalog,
                        reviewed_by_card=reviewed_by_card,
                        reviewed_parallels=reviewed_parallels,
                        parallel_heavy_mode=bool(payload.get("parallel_heavy_mode", False)),
                        default_raw_price=float(payload.get("default_raw_price", 1.00)),
                        locked_set=locked_set_arg or None,
                        locked_subset=locked_sub_arg or None,
                        auto_split_flatbed=bool(payload.get("auto_split_flatbed", True)),
                        flatbed_flip_mode=str(payload.get("flatbed_flip_mode", "auto")),
                        progress_callback=_on_scan_card,
                        log_cb=_worker_log_cb,
                    )
                    _worker_log_cb(f"✅ Completed batch '{b_name}' in {round(time.time() - batch_t0, 1)}s!")
        elif job_type == "reidentify_batch":
            reidentify_batch_cards(
                batch_dir=Path(payload.get("batch_dir", "")),
                target_mode=str(payload.get("target_mode", "flagged_and_suspect")),
                selected_skus=payload.get("selected_skus") or [],
                locked_set=payload.get("locked_set") or None,
                locked_subset=payload.get("locked_subset") or None,
                log_cb=_worker_log_cb,
                progress_callback=lambda c_i, t_i, rec: _worker_log_cb(
                    f"[{c_i}/{t_i}] Re-Identified SKU {rec.get('SKU','')} — {rec.get('Set','')} {rec.get('Card_Number','')} "
                    f"{rec.get('Player','')} [{rec.get('Subset_Parallel','Base')}] | OCR {rec.get('OCR_Confidence','0')} | "
                    f"Vis {_fmt_vis_pct(rec)}"
                    f"{' | 🚩 Review' if str(rec.get('Needs_Review','')).lower() == 'true' else ''}"
                ),
            )
        elif job_type == "regrade_batch":
            regrade_batch_cards(
                batch_dir=Path(payload.get("batch_dir", "")),
                regenerate_corner_sheets=bool(payload.get("regenerate_corner_sheets", True)),
                log_cb=_worker_log_cb,
                progress_callback=lambda c_i, t_i, rec: _worker_log_cb(
                    f"[{c_i}/{t_i}] Re-Graded Batch SKU {rec.get('SKU','')} — PSA {rec.get('Est_PSA','')} / BGS {rec.get('Est_BGS','')} ({rec.get('Player','')})"
                ),
            )
        elif job_type == "regrade_inventory":
            regrade_inventory_cards(
                regenerate_corner_sheets=bool(payload.get("regenerate_corner_sheets", True)),
                log_cb=_worker_log_cb,
                progress_callback=lambda c_i, t_i, rec: _worker_log_cb(
                    f"[{c_i}/{t_i}] Re-Graded SKU {rec.get('SKU','')} — PSA {rec.get('Est_PSA','')} / BGS {rec.get('Est_BGS','')} ({rec.get('Player','')})"
                ),
            )
        elif job_type == "reprocess_inventory_skus":
            reprocess_inventory_skus(
                skus=payload.get("skus") or [],
                locked_set=payload.get("locked_set") or None,
                locked_subset=payload.get("locked_subset") or None,
                regrade_too=bool(payload.get("regrade_too", True)),
                log_cb=_worker_log_cb,
                progress_callback=lambda c_i, t_i, rec: _worker_log_cb(
                    f"[{c_i}/{t_i}] Reprocessed Inventory SKU {rec.get('SKU','')} — {rec.get('Set','')} #{rec.get('Card Number','')} "
                    f"{rec.get('Player','')} [{rec.get('Subset','Base')}] | OCR {rec.get('OCR_Confidence','0')} | Vis {_fmt_vis_pct(rec)}"
                ),
            )
        elif job_type == "reprocess_batch_cards":
            reprocess_batch_cards_list(
                batch_dir=Path(payload.get("batch_dir", "")),
                skus=payload.get("skus") or [],
                locked_set=payload.get("locked_set") or None,
                locked_subset=payload.get("locked_subset") or None,
                regrade_too=bool(payload.get("regrade_too", True)),
                log_cb=_worker_log_cb,
                progress_callback=lambda c_i, t_i, rec: _worker_log_cb(
                    f"[{c_i}/{t_i}] Reprocessed Batch SKU {rec.get('SKU','')} — {rec.get('Set','')} {rec.get('Card_Number','')} "
                    f"{rec.get('Player','')} [{rec.get('Subset_Parallel','Base')}] | OCR {rec.get('OCR_Confidence','0')} | Vis {_fmt_vis_pct(rec)}"
                ),
            )
        elif job_type == "fix_card_rotations":
            fix_card_rotations_and_regrade(
                scope=str(payload.get("scope") or "all"),
                set_filter=str(payload.get("set_filter") or "").strip() or None,
                dry_run=bool(payload.get("dry_run", False)),
                log_cb=_worker_log_cb,
                progress_callback=lambda c_i, t_i, info: _worker_log_cb(
                    f"[{c_i}/{t_i}] Rotation Check ({info.get('scope_label','')}) — SKU {info.get('SKU','')} "
                    f"{info.get('Player','')} | Fixed so far: {info.get('impacted', 0)}"
                ),
            )
        elif job_type == "install_directml":
            _worker_log_cb("[1/3] Checking current ONNX Runtime installation...")
            py_exe = sys.executable
            _worker_log_cb(f"  Python environment: {py_exe}")
            _worker_log_cb("[2/3] Swapping CPU onnxruntime -> onnxruntime-directml (AMD/Intel/NVIDIA Windows DirectML)...")
            for pip_args in (
                [py_exe, "-m", "pip", "uninstall", "-y", "onnxruntime", "onnxruntime-gpu"],
                [py_exe, "-m", "pip", "install", "--upgrade", "onnxruntime-directml"],
            ):
                p_res = subprocess.run(pip_args, capture_output=True, text=True)
                for ln in (p_res.stdout or "").splitlines():
                    if ln.strip():
                        _worker_log_cb(f"  {ln.strip()}")
                for ln in (p_res.stderr or "").splitlines():
                    if ln.strip() and "WARNING" not in ln.upper():
                        _worker_log_cb(f"  [pip] {ln.strip()}")
                if p_res.returncode != 0 and "install" in pip_args:
                    raise RuntimeError(f"pip install onnxruntime-directml failed (exit {p_res.returncode})")
            _worker_log_cb("[3/3] Verifying DirectML GPU provider...")
            chk_cmd = [py_exe, "-c", "import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())"]
            v_res = subprocess.run(chk_cmd, capture_output=True, text=True)
            _worker_log_cb(f"  ✅ Verified ONNX Runtime: {(v_res.stdout or '').strip()}")
            probe_system_hardware(force_refresh=True)
        elif job_type == "download_dinov2_model":
            download_dinov2_small_model(
                force_redownload=bool(payload.get("force_redownload", False)),
                log_cb=_worker_log_cb,
                progress_callback=lambda cur_p, tot_p, msg: _worker_log_cb(f"[{cur_p}/{tot_p}] {msg}"),
            )
            probe_system_hardware(force_refresh=True)
        elif job_type == "build_neural_index":
            build_or_update_neural_embedding_index(
                set_filter=str(payload.get("set_filter") or "").strip() or None,
                batch_size=int(payload.get("batch_size", 32)),
                force_rebuild=bool(payload.get("force_rebuild", False)),
                log_cb=_worker_log_cb,
                progress_callback=lambda cur_i, tot_i, msg: _worker_log_cb(f"[{cur_i}/{tot_i}] {msg}"),
            )
            probe_system_hardware(force_refresh=True)
        elif job_type == "commit_batches":
            from Core.config import BATCHES_DIR
            from Core.database import commit_batch_to_inventory_v2

            batch_names = [str(n).strip() for n in (payload.get("batch_names") or []) if str(n or "").strip()]
            move_imgs = bool(payload.get("move_images", True))
            if not batch_names:
                raise RuntimeError("No batch name(s) provided to commit_batches worker.")

            # Pre-count cards across all selected batches for exact Tier-1 overall progress & ETA
            valid_batches: list[tuple[str, Path, int]] = []
            total_cards_all = 0
            for bn in batch_names:
                b_dir = BATCHES_DIR / bn
                man_p = b_dir / "Batch_Inventory_Manifest.csv"
                if not b_dir.exists() or not man_p.exists():
                    _worker_log_cb(f"⚠️ Skipping missing batch '{bn}' ({b_dir}).")
                    continue
                try:
                    cnt_b = len(pd.read_csv(man_p, dtype=str, keep_default_na=False))
                except Exception:
                    cnt_b = 1
                valid_batches.append((bn, b_dir, max(1, cnt_b)))
                total_cards_all += max(1, cnt_b)

            if not valid_batches:
                raise RuntimeError("None of the selected batches have a valid Batch_Inventory_Manifest.csv.")

            total_batches_cnt = len(valid_batches)
            total_cards_all = max(1, total_cards_all)
            state_tracker["total"] = total_cards_all
            state_tracker["total_cards"] = total_cards_all
            cards_done_all = 0
            committed_batches_ok = 0

            _worker_log_cb(
                f"🎉 Starting Commit to Inventory across {total_batches_cnt} batch(es) "
                f"({total_cards_all:,} total card(s) | move_and_archive={move_imgs})..."
            )

            for b_idx, (bn, b_dir, b_est) in enumerate(valid_batches, 1):
                b_t0 = time.time()
                batch_cards_done = 0

                def _on_commit_card(c_i: int, t_i: int, rec: dict, _bn=bn, _bi=b_idx, _bt0=b_t0):
                    nonlocal cards_done_all, batch_cards_done
                    cards_done_all += 1
                    batch_cards_done = c_i
                    tot_dyn = max(total_cards_all, cards_done_all)
                    state_tracker["current"] = cards_done_all
                    state_tracker["completed_cards"] = cards_done_all
                    state_tracker["total_cards"] = tot_dyn

                    if c_i <= 3 or c_i % 25 == 0 or c_i == t_i:
                        line_c = (
                            f"[{c_i}/{t_i}] Moving SKU {rec.get('SKU','')} — {rec.get('Set','')} "
                            f"#{rec.get('Card Number','')} {rec.get('Player','')} [{rec.get('Subset','Base')}]"
                        )
                        append_job_log(f"  {line_c}", lane=target_lane, run_log_file=run_log_path)
                    else:
                        line_c = (
                            f"[{c_i}/{t_i}] SKU {rec.get('SKU','')} — {rec.get('Player','')} [{rec.get('Subset','Base')}]"
                        )

                    if c_i == 1 or c_i % 5 == 0 or c_i == t_i:
                        now_ep = time.time()
                        run_el = max(0.1, now_ep - start_ep)
                        b_el = max(0.1, now_ep - _bt0)
                        cps = round(cards_done_all / run_el, 3)
                        t1_eta = round((run_el / float(cards_done_all)) * max(0, tot_dyn - cards_done_all), 1)
                        t2_eta = round((b_el / float(max(1, c_i))) * max(0, t_i - c_i), 1)
                        write_job_state(
                            "RUNNING",
                            job_type,
                            title,
                            current=cards_done_all,
                            total=tot_dyn,
                            current_item=line_c,
                            start_epoch=start_ep,
                            pid=my_pid,
                            lane=target_lane,
                            sub_current=c_i,
                            sub_total=t_i,
                            sub_label=_bn,
                            sub_start_epoch=_bt0,
                            active_set_name=f"Batch {_bi}/{total_batches_cnt}: {_bn}",
                            set_index=_bi,
                            total_sets=total_batches_cnt,
                            completed_cards=cards_done_all,
                            total_cards=tot_dyn,
                            cards_per_sec=cps,
                            eta_override=t1_eta,
                            sub_eta_override=t2_eta,
                            percent_override=min(99.0, (float(cards_done_all) / float(tot_dyn)) * 96.0),
                        )

                def _on_commit_log(msg_s: str, _bn=bn, _bi=b_idx, _bt0=b_t0, _btot=b_est):
                    append_job_log(str(msg_s), lane=target_lane, run_log_file=run_log_path)
                    now_ep = time.time()
                    run_el = max(0.1, now_ep - start_ep)
                    tot_dyn = max(total_cards_all, cards_done_all)
                    write_job_state(
                        "RUNNING",
                        job_type,
                        title,
                        current=cards_done_all,
                        total=tot_dyn,
                        current_item=str(msg_s).strip()[:175],
                        start_epoch=start_ep,
                        pid=my_pid,
                        lane=target_lane,
                        sub_current=min(_btot, batch_cards_done),
                        sub_total=_btot,
                        sub_label=_bn,
                        sub_start_epoch=_bt0,
                        active_set_name=f"Batch {_bi}/{total_batches_cnt}: {_bn}",
                        set_index=_bi,
                        total_sets=total_batches_cnt,
                        completed_cards=cards_done_all,
                        total_cards=tot_dyn,
                        cards_per_sec=round(cards_done_all / run_el, 3) if cards_done_all > 0 else 0.0,
                        percent_override=min(99.0, (float(cards_done_all) / float(tot_dyn)) * 98.0),
                    )

                res_one = commit_batch_to_inventory_v2(
                    b_dir,
                    move_images_and_archive=move_imgs,
                    progress_callback=_on_commit_card,
                    log_cb=_on_commit_log,
                )
                if res_one.get("success"):
                    committed_batches_ok += 1
                else:
                    _worker_log_cb(f"⚠️ Failed committing batch '{bn}': {res_one.get('error')}")

            if committed_batches_ok == 0:
                raise RuntimeError("No batches were successfully committed.")
            _worker_log_cb(
                f"🎉 Commit Complete: Committed {cards_done_all:,} card(s) across {committed_batches_ok}/{total_batches_cnt} batch(es) to Inventory.csv!"
            )
        elif job_type == "rebuild_feature_cache":
            _worker_log_cb("🧠 Rebuilding Reference Library & Collection lazy feature index cache (.pkl)...")
            index_set_templates_and_reviewed_cards(
                REFERENCE_TEMPLATES_DIR,
                REVIEWED_CARDS_DIR,
                force_rebuild=True,
                lazy_vectors=True,
                log_cb=_worker_log_cb,
            )
            _worker_log_cb("✅ Feature cache rebuild complete!")
        elif job_type == "deduplicate_tracked_sets":
            _worker_log_cb("🧹 Starting Tracked Sets & TCDB Directory Deduplication and Uniform Naming Cleanup...")
            deduplicate_tracked_sets_and_directory()
        elif job_type == "tcdb_scrape":
            mode_scraping_pipeline(
                target_queue=payload.get("target_queue"),
                cooldown_seconds=int(payload.get("cooldown_seconds", 5)),
                download_all_cataloged=True,
                incremental=bool(payload.get("incremental", True)),
                force_refresh=bool(payload.get("force_refresh", False)),
            )
        elif job_type == "tcdb_download_all_images":
            mode_download_all_catalog_images(target_queue=payload.get("target_queue"))
        elif job_type == "tcdb_checklist_and_images":
            mode_checklist_and_images_card_by_card(
                target_queue=payload.get("target_queue") or payload.get("selected_tcdb_sets"),
                clean_slate_reset=bool(payload.get("clean_slate_reset", False)),
                cooldown_seconds=int(payload.get("cooldown_seconds", 5)),
                incremental=bool(payload.get("incremental", True)),
                force_refresh=bool(payload.get("force_refresh", False)),
            )
        elif job_type == "tcdb_upgrade":
            mode_image_update_pipeline(target_queue=payload.get("target_queue"))
        elif job_type == "tcdb_missing_back":
            mode_missing_back_audit(target_queue=payload.get("target_queue"))
        elif job_type == "tcdb_resume":
            resume_saved_run()
        elif job_type == "tcdb_checklist_scrape":
            run_tcdb_checklist_pipeline(
                selected_tcdb_sets=payload.get("selected_tcdb_sets"),
                clean_slate_reset=bool(payload.get("clean_slate_reset", False)),
                incremental=bool(payload.get("incremental", True)),
                force_refresh=bool(payload.get("force_refresh", False)),
            )
        elif job_type == "repair_checklists":
            repair_corrupted_checklists_and_processed_cards()
        elif job_type == "clean_reference_library":
            clean_reference_library_names(dry_run=bool(payload.get("dry_run", False)))
        elif job_type == "repair_tcdb_directory":
            repair_tcdb_set_directory(
                fetch_missing_image_pct=bool(payload.get("fetch_missing_image_pct", False)),
                max_live_fetches=int(payload.get("max_live_fetches", 120)),
            )
        elif job_type == "sync_set_library_status":
            sync_set_library_download_status(rebuild_master_checklist=True)
        elif job_type == "crawl_tcdb_directory":
            crawl_tcdb_master_set_directory(
                sports=payload.get("sports") or ["Baseball", "Football", "Basketball"],
                start_year=int(payload.get("start_year", 2020)),
                end_year=int(payload.get("end_year", datetime.now().year)),
                fetch_set_image_pct=bool(payload.get("fetch_set_image_pct", True)),
                max_image_pct_fetches=int(payload.get("max_image_pct_fetches", 150)),
            )
        elif job_type == "refresh_market_valuations":
            inv_df = load_inventory_df()
            _worker_log_cb(
                f"💰 Starting Market Valuation & Grading Tiers Refresh across {len(inv_df):,} inventory SKU(s) "
                f"(live_comps={bool(payload.get('fetch_live_web_comps', True))}, tiers={bool(payload.get('refresh_grading_tiers', True))})..."
            )
            updated_inv, new_alerts, val_summary = refresh_inventory_market_valuations(
                inv_df,
                fetch_live_web_comps=bool(payload.get("fetch_live_web_comps", True)),
                refresh_grading_tiers=bool(payload.get("refresh_grading_tiers", True)),
                progress_callback=lambda c_i, t_i, msg: _worker_log_cb(f"[{c_i}/{t_i}] {msg}"),
            )
            save_inventory_df(updated_inv)
            _worker_log_cb(
                f"✅ Saved updated valuations for {len(updated_inv):,} cards | "
                f"Raw=${val_summary.get('Total_Raw_Value', 0):,.2f} | Optimal EV=${val_summary.get('Total_Optimal_EV', 0):,.2f} | "
                f"New Alerts: {len(new_alerts)}"
            )
        elif job_type == "batch_generate_listings":
            inv_df = load_inventory_df()
            curr_drafts = load_listing_drafts_df()
            existing_draft_skus = set(curr_drafts["SKU_or_Lot_ID"].astype(str).str.strip()) if not curr_drafts.empty else set()

            scope = str(payload.get("scope") or "for_sale").strip().lower()
            target_skus = set(str(s).strip() for s in (payload.get("skus") or []) if str(s).strip())
            set_filter = str(payload.get("set_name") or "").strip()
            batch_filter = str(payload.get("source_batch") or "").strip()
            content_opts = payload.get("content_options") if isinstance(payload.get("content_options"), dict) else None
            custom_set_blurb = str(payload.get("custom_set_blurb") or "").strip() or None
            force_web_ref = bool(payload.get("force_refresh_bio", False))
            platform_target = str(payload.get("platform") or "eBay & CollX").strip()

            if target_skus:
                rows_to_gen = inv_df[inv_df["SKU"].astype(str).isin(target_skus)].copy()
            else:
                rows_to_gen = inv_df[inv_df["Status"] != "Sold"].copy()
                if scope in ("for_sale", "unlisted", "missing_drafts"):
                    rows_to_gen = rows_to_gen[~rows_to_gen["Hold_Tag"].astype(str).str.contains("Personal Collection", case=False, na=False)]
                if scope == "unlisted":
                    rows_to_gen = rows_to_gen[rows_to_gen["Status"].astype(str).str.strip().str.lower() == "in stock"]
                elif scope == "missing_drafts":
                    rows_to_gen = rows_to_gen[~rows_to_gen["SKU"].astype(str).str.strip().isin(existing_draft_skus)]
                elif scope == "set" and set_filter and set_filter != "All Sets":
                    rows_to_gen = rows_to_gen[rows_to_gen["Set"].astype(str).str.strip() == set_filter]
                elif scope == "batch" and batch_filter and batch_filter != "All Batches":
                    rows_to_gen = rows_to_gen[rows_to_gen["Source_Batch"].astype(str).str.strip() == batch_filter]

            _worker_log_cb(
                f"✍️ Starting Scoped Batch Listing Writer (scope={scope}, cards={len(rows_to_gen):,}, platform={platform_target})..."
            )
            new_drafts = []
            tot_gen = max(1, len(rows_to_gen))
            for idx_g, (_, r) in enumerate(rows_to_gen.iterrows(), 1):
                c_dict = r.to_dict()
                copy_res = generate_card_listing_copy(
                    c_dict,
                    platform=platform_target,
                    force_web_refresh=force_web_ref,
                    content_options=content_opts,
                    custom_set_blurb=custom_set_blurb,
                )
                _worker_log_cb(
                    f"[{idx_g}/{tot_gen}] Drafted SKU {c_dict.get('SKU','')} (${copy_res.get('Recommended_Price','')}) — {copy_res.get('SEO_Title_80Char','')}"
                )
                new_drafts.append({
                    "Draft_ID": f"DRF-{c_dict.get('SKU')}",
                    "Listing_Type": "Single Card",
                    "SKU_or_Lot_ID": str(c_dict.get("SKU", "")),
                    "Set": str(c_dict.get("Set", "")),
                    "Subset": str(c_dict.get("Subset", "Base")),
                    "Card_Number": str(c_dict.get("Card Number", "")),
                    "Player_or_Bundle": str(c_dict.get("Player", "")),
                    "Team": str(c_dict.get("Team", "")),
                    "Quantity": "1",
                    "Recommended_Price": copy_res["Recommended_Price"],
                    "Platform_Target": platform_target,
                    "SEO_Title_80Char": copy_res["SEO_Title_80Char"],
                    "Description_Body": copy_res["Description_Body"],
                    "Front_File": str(c_dict.get("Front_File", "")),
                    "Back_File": str(c_dict.get("Back_File", "")),
                    "Created_At": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                if idx_g % 25 == 0 and new_drafts:
                    nd_df = pd.DataFrame(new_drafts)
                    curr_drafts = save_listing_drafts_df(nd_df if curr_drafts.empty else pd.concat([curr_drafts, nd_df], ignore_index=True))
                    new_drafts = []
            if new_drafts:
                nd_df = pd.DataFrame(new_drafts)
                save_listing_drafts_df(nd_df if curr_drafts.empty else pd.concat([curr_drafts, nd_df], ignore_index=True))
            _worker_log_cb(f"✅ Completed Batch Listing Writer ({len(rows_to_gen):,} draft(s) saved to Listing_Drafts.csv).")
        else:
            raise ValueError(f"Unsupported background job_type: '{job_type}'")

        total_el_s = round(max(0.0, time.time() - start_ep), 1)
        el_m, el_sec = divmod(int(total_el_s), 60)
        el_h, el_m = divmod(el_m, 60)
        el_fmt = f"{el_h}:{el_m:02d}:{el_sec:02d}" if el_h > 0 else f"{el_m:02d}:{el_sec:02d}"
        write_job_state(
            "COMPLETED",
            job_type,
            title,
            current=state_tracker["total"],
            total=state_tracker["total"],
            current_item=f"Completed in {el_fmt}!",
            start_epoch=start_ep,
            pid=0,
            lane=target_lane,
            completed_cards=int(state_tracker.get("completed_cards") or 0),
            total_cards=int(state_tracker.get("total_cards") or 0),
        )
        append_job_log(f"FINISHED [OK]: {title} (PID {my_pid}) | Elapsed: {el_fmt} ({total_el_s}s).", lane=target_lane, run_log_file=run_log_path)
    except Exception as e:
        tb_str = traceback.format_exc()
        append_job_log(f"ERROR [EXCEPTION]: {e}\n{tb_str}", lane=target_lane, run_log_file=run_log_path)
        write_job_state("FAILED", job_type, title, current=state_tracker["current"], total=state_tracker["total"], current_item=f"Error: {e}", start_epoch=start_ep, pid=0, error_msg=str(e), lane=target_lane)
    finally:
        _hb_stop.set()
        release_gpu_worker_slot()
        set_log_callback(None)
        set_progress_callback(None)
        base_lane = base_lane_from_slot(target_lane)
        pending_q = load_lane_job_queue(base_lane)
        if pending_q:
            next_item = pending_q.pop(0)
            save_lane_job_queue(base_lane, pending_q)
            append_job_log(
                f"⏭️ Starting next queued task in {PROCESS_LANES[base_lane]['short_name']}: {next_item.get('title')}",
                lane=base_lane,
                run_log_file=run_log_path,
            )
            start_background_job(
                job_type=str(next_item.get("job_type", "task")),
                title=str(next_item.get("title", "Queued Task")),
                payload=dict(next_item.get("payload", {})),
                lane=base_lane,
                execution_mode="queue",
                is_queued_continuation=True,
            )


def main():
    parser = argparse.ArgumentParser(description="Tabulas Card Management Hub CLI & Background Worker")
    parser.add_argument("--version", "--check-versions", action="store_true", dest="check_versions")
    parser.add_argument("--bg-job", type=str)
    parser.add_argument("--startup-maintenance", action="store_true")
    parser.add_argument("--auto-scrape", action="store_true")
    parser.add_argument("--download-all-images", action="store_true")
    parser.add_argument("--auto-upgrade", action="store_true")
    parser.add_argument("--auto-checklists", action="store_true")
    parser.add_argument("--sync-library-status", action="store_true")
    parser.add_argument("--auto-directory", action="store_true")
    parser.add_argument("--auto-market", action="store_true")
    parser.add_argument("--process-scans", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if args.check_versions:
        print(f"=== Tabulas Card Management Hub — Release {APP_RELEASE_VERSION} ({APP_RELEASE_STAGE}) ===")
        for r in inspect_all_module_versions():
            print(f"  {r['Status']:<22} | {r['Module']:<24} | Loaded: {r['Loaded Version']:<15} | Disk: {r['Disk Version']:<15}")
        return
    if args.bg_job:
        run_background_job_from_file(Path(args.bg_job))
        return
    if args.startup_maintenance:
        res = run_startup_maintenance()
        print(f"[System Maintenance] {res['message']}")
        return
    if args.auto_checklists:
        run_tcdb_checklist_pipeline()
        return
    if args.download_all_images:
        mode_download_all_catalog_images()
        return
    if args.auto_scrape:
        mode_scraping_pipeline()
        return
    if args.auto_upgrade:
        mode_image_update_pipeline()
        return
    if args.sync_library_status:
        sync_set_library_download_status(rebuild_master_checklist=True)
        return
    if args.auto_directory:
        crawl_tcdb_master_set_directory()
        return
    if args.auto_market:
        inv_df = load_inventory_df()
        updated_inv, _, _ = refresh_inventory_market_valuations(inv_df, fetch_live_web_comps=True, refresh_grading_tiers=True)
        save_inventory_df(updated_inv)
        return
    if args.process_scans:
        discovered = find_unarchived_scan_batches()
        if not discovered:
            print("[Scan Ingest] No unarchived scanner PDF batches found in Incoming_Scans.")
            return
        root_df, parallels_map, ordinary_roots, print_run_map = load_master_checklist(CHECKLIST_PATH)
        template_catalog, reviewed_by_card, reviewed_parallels = index_set_templates_and_reviewed_cards(
            REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR
        )
        for b_name, b_dir, b_pdfs in discovered:
            print(f"[Scan Ingest] Processing '{b_name}' ({len(b_pdfs)} PDFs)...")
            process_single_batch(
                batch_name=b_name,
                source_folder=b_dir,
                pdf_files=b_pdfs,
                root_df=root_df,
                parallels_map=parallels_map,
                ordinary_roots=ordinary_roots,
                print_run_map=print_run_map,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                reviewed_parallels=reviewed_parallels,
            )
        return
    if args.resume:
        resume_saved_run()
        return

    parser.print_help()
    print("\nTip: Launch the Tabulas Card Management Hub desktop app via `python App/launch_tabulas_hub.py`.")


if __name__ == "__main__":
    main()