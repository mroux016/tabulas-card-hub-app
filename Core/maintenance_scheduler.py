from __future__ import annotations
# ==============================================================================
# Core/maintenance_scheduler.py - LOCAL-FIRST MAINTENANCE SCHEDULER
# ==============================================================================
# Persists schedule state in `Data/maintenance_schedule.json` via
# `interprocess_file_lock` + `atomic_write_text`, evaluates due tasks,
# respects active worker slots / stop-signal flags (deferring cleanly when busy),
# and executes local maintenance jobs (neural index sync, master checklist rollup,
# learned set priors refresh, and housekeeping/hygiene).
# ==============================================================================

import csv
import json
import os
import re
import shutil
import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from Core.config import (
    ARCHIVE_LOGS_DIR,
    CACHE_DIR,
    CHECKLIST_PATH,
    DAILY_LOGS_ROOT,
    DATA_DIR,
    DOWNLOADED_FILES_DIR,
    INVENTORY_FILE,
    LEARNED_SET_PRIORS_FILE,
    LOGS_DIR,
    MAINTENANCE_SCHEDULE_FILE,
    REPORTS_DIR,
    atomic_write_text,
    interprocess_file_lock,
)

__version__ = "0.25.0-beta.6"

TASK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "neural_index_sync": {
        "task_id": "neural_index_sync",
        "label": "Neural Embedding Cache & Visual Index Rebuild",
        "description": "Incremental sync of newly downloaded TCDB reference images into DINOv2 neural embedding & visual indexes.",
        "default_enabled": False,
        "default_cron_or_interval": "daily",
        "default_time_of_day": "02:30",
    },
    "master_checklist_rollup": {
        "task_id": "master_checklist_rollup",
        "label": "Master Checklist & Template Rollup",
        "description": "Rebuilds Master_Checklist.csv and syncs Front/Back download flags from Set_Checklists and Reference_Library.",
        "default_enabled": False,
        "default_cron_or_interval": "daily",
        "default_time_of_day": "03:00",
    },
    "learned_set_priors_refresh": {
        "task_id": "learned_set_priors_refresh",
        "label": "Learned Set Priors Refresh",
        "description": "Rebuilds learned_set_priors.json from grading_feedback_log.jsonl across 3-tier set/subset/format hierarchy.",
        "default_enabled": False,
        "default_cron_or_interval": "daily",
        "default_time_of_day": "03:30",
    },
    "housekeeping_hygiene": {
        "task_id": "housekeeping_hygiene",
        "label": "Housekeeping & Hygiene",
        "description": "Prunes logs > 30 days, clears stale driver_fixing.lock & orphaned temp files, and verifies CSV/JSON integrity.",
        "default_enabled": False,
        "default_cron_or_interval": "daily",
        "default_time_of_day": "04:00",
    },
}

_VALID_INTERVALS = {"daily", "weekly", "hourly", "every_6h", "every_12h"}
_DAEMON_LOCK = threading.Lock()
_DAEMON_STARTED = False
_DAEMON_STOP_EVENT = threading.Event()


def _default_task_entry(task_id: str) -> dict[str, Any]:
    meta = TASK_DEFINITIONS[task_id]
    return {
        "task_id": task_id,
        "label": meta["label"],
        "description": meta["description"],
        "enabled": bool(meta["default_enabled"]),
        "cron_or_interval": meta["default_cron_or_interval"],
        "time_of_day": meta["default_time_of_day"],
        "last_run": "",
        "last_status": "idle",
        "last_message": "",
        "deferred_count": 0,
    }


def build_default_schedule() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": {tid: _default_task_entry(tid) for tid in TASK_DEFINITIONS},
    }


def _normalize_time_of_day(raw: Any, fallback: str = "03:00") -> str:
    s = str(raw or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not m:
        return fallback
    hh = max(0, min(23, int(m.group(1))))
    mm = max(0, min(59, int(m.group(2))))
    return f"{hh:02d}:{mm:02d}"


def _normalize_interval(raw: Any, fallback: str = "daily") -> str:
    s = str(raw or "").strip().lower()
    if s in _VALID_INTERVALS:
        return s
    if s.startswith("interval:"):
        try:
            mins = max(5, int(s.split(":", 1)[1]))
            return f"interval:{mins}"
        except Exception:
            return fallback
    return fallback


def _normalize_schedule_dict(raw: Any) -> dict[str, Any]:
    base = build_default_schedule()
    if not isinstance(raw, dict):
        return base
    raw_tasks = raw.get("tasks") if isinstance(raw.get("tasks"), dict) else {}
    for tid in TASK_DEFINITIONS:
        entry = base["tasks"][tid]
        src = raw_tasks.get(tid)
        if isinstance(src, dict):
            entry["enabled"] = bool(src.get("enabled", entry["enabled"]))
            entry["cron_or_interval"] = _normalize_interval(
                src.get("cron_or_interval"), entry["cron_or_interval"]
            )
            entry["time_of_day"] = _normalize_time_of_day(
                src.get("time_of_day"), entry["time_of_day"]
            )
            entry["last_run"] = str(src.get("last_run") or "")
            entry["last_status"] = str(src.get("last_status") or "idle")
            entry["last_message"] = str(src.get("last_message") or "")
            try:
                entry["deferred_count"] = max(0, int(src.get("deferred_count") or 0))
            except Exception:
                entry["deferred_count"] = 0
    if raw.get("updated_at"):
        base["updated_at"] = str(raw.get("updated_at"))
    return base


def _resolve_schedule_path(schedule_path: Optional[Path] = None) -> Path:
    return Path(schedule_path) if schedule_path is not None else MAINTENANCE_SCHEDULE_FILE


def load_maintenance_schedule(schedule_path: Optional[Path] = None) -> dict[str, Any]:
    """Loads `Data/maintenance_schedule.json` safely under interprocess lock."""
    path = _resolve_schedule_path(schedule_path)
    lock_path = path.with_suffix(".json.lock")
    with interprocess_file_lock(lock_path):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                return _normalize_schedule_dict(data)
            except Exception:
                pass
        default_cfg = build_default_schedule()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(default_cfg, indent=2), encoding="utf-8")
        return default_cfg


def save_maintenance_schedule(
    cfg: dict[str, Any],
    schedule_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Atomically persists `Data/maintenance_schedule.json` under interprocess lock."""
    path = _resolve_schedule_path(schedule_path)
    lock_path = path.with_suffix(".json.lock")
    norm = _normalize_schedule_dict(cfg)
    norm["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with interprocess_file_lock(lock_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(norm, indent=2), encoding="utf-8")
    return norm


def update_maintenance_schedule(
    updates: dict[str, Any],
    schedule_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Merges UI/API task configuration updates into `maintenance_schedule.json`."""
    path = _resolve_schedule_path(schedule_path)
    lock_path = path.with_suffix(".json.lock")
    with interprocess_file_lock(lock_path):
        if path.exists():
            try:
                curr = _normalize_schedule_dict(json.loads(path.read_text(encoding="utf-8-sig")))
            except Exception:
                curr = build_default_schedule()
        else:
            curr = build_default_schedule()

        task_updates = updates.get("tasks") if isinstance(updates.get("tasks"), dict) else updates
        if isinstance(task_updates, dict):
            for tid, patch in task_updates.items():
                if tid not in curr["tasks"] or not isinstance(patch, dict):
                    continue
                t = curr["tasks"][tid]
                if "enabled" in patch:
                    t["enabled"] = bool(patch["enabled"])
                if "cron_or_interval" in patch:
                    t["cron_or_interval"] = _normalize_interval(patch["cron_or_interval"], t["cron_or_interval"])
                if "time_of_day" in patch:
                    t["time_of_day"] = _normalize_time_of_day(patch["time_of_day"], t["time_of_day"])

        curr["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(curr, indent=2), encoding="utf-8")
        return curr


def is_worker_pool_busy(
    busy_checker: Optional[Callable[[], tuple[bool, str]]] = None,
) -> tuple[bool, str]:
    """
    Returns `(True, reason)` if any worker slot (`slot_1`..`slot_8` or parallel subslots)
    is currently running or a stop-signal flag is active.
    """
    if busy_checker is not None:
        return busy_checker()

    try:
        if LOGS_DIR.exists():
            for flag in LOGS_DIR.glob("stop_signal*.flag"):
                return True, f"Stop signal active ({flag.name})"
    except Exception:
        pass

    try:
        import cli

        lanes_state = cli.get_all_lanes_state()
        for lane_key, st in (lanes_state or {}).items():
            if isinstance(st, dict) and str(st.get("status") or "").upper() == "RUNNING":
                job_title = st.get("title") or st.get("job_type") or "Active job"
                return True, f"{lane_key}: {job_title}"
    except Exception:
        pass

    return False, ""


def _parse_iso_dt(val: str) -> Optional[datetime]:
    s = str(val or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            continue
    return None


def is_task_due(task_cfg: dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Evaluates whether an enabled maintenance task is due at `now`."""
    if not task_cfg or not bool(task_cfg.get("enabled")):
        return False

    ref_now = now or datetime.now()
    interval = _normalize_interval(task_cfg.get("cron_or_interval"), "daily")
    time_str = _normalize_time_of_day(task_cfg.get("time_of_day"), "03:00")
    hh, mm = (int(x) for x in time_str.split(":"))
    last_dt = _parse_iso_dt(task_cfg.get("last_run", ""))

    if interval == "hourly":
        return last_dt is None or (ref_now - last_dt) >= timedelta(hours=1)
    if interval == "every_6h":
        return last_dt is None or (ref_now - last_dt) >= timedelta(hours=6)
    if interval == "every_12h":
        return last_dt is None or (ref_now - last_dt) >= timedelta(hours=12)
    if interval.startswith("interval:"):
        mins = max(5, int(interval.split(":", 1)[1]))
        return last_dt is None or (ref_now - last_dt) >= timedelta(minutes=mins)
    if interval == "weekly":
        scheduled_today = ref_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if ref_now < scheduled_today:
            return False
        return last_dt is None or (ref_now - last_dt) >= timedelta(days=7)

    # Default: daily at `time_of_day`
    scheduled_today = ref_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if ref_now < scheduled_today:
        return False
    if last_dt is None:
        return True
    return last_dt < scheduled_today


def _run_housekeeping_hygiene(
    keep_logs_days: int = 30,
    daily_logs_dir: Optional[Path] = None,
    reports_dir: Optional[Path] = None,
    archive_logs_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    lock_dirs: Optional[list[Path]] = None,
    json_files: Optional[list[Path]] = None,
    csv_files: Optional[list[Path]] = None,
) -> dict[str, Any]:
    """
    Prunes daily logs & reports older than `keep_logs_days`, removes stale
    `driver_fixing.lock` & orphaned temp files, and checks CSV/JSON integrity.
    """
    d_logs = Path(daily_logs_dir) if daily_logs_dir is not None else DAILY_LOGS_ROOT
    r_dir = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    arc_dir = (
        Path(archive_logs_dir)
        if archive_logs_dir is not None
        else (ARCHIVE_LOGS_DIR if daily_logs_dir is None else None)
    )
    c_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    da_dir = Path(data_dir) if data_dir is not None else DATA_DIR

    cutoff_dt = datetime.now() - timedelta(days=keep_logs_days)
    cutoff_ymd = cutoff_dt.strftime("%Y%m%d")
    cutoff_ep = cutoff_dt.timestamp()

    pruned_logs = 0
    if d_logs.exists():
        for entry in sorted(d_logs.iterdir()):
            if entry.is_dir() and re.fullmatch(r"\d{8}", entry.name) and entry.name < cutoff_ymd:
                try:
                    if arc_dir is not None:
                        dst = arc_dir / f"{entry.name[:4]}-{entry.name[4:6]}" / entry.name
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if dst.exists():
                            shutil.rmtree(dst, ignore_errors=True)
                        shutil.move(str(entry), str(dst))
                    else:
                        shutil.rmtree(entry, ignore_errors=True)
                    pruned_logs += 1
                except Exception:
                    pass

    pruned_reports = 0
    if r_dir.exists():
        for rf in list(r_dir.iterdir()):
            if rf.is_file():
                try:
                    if rf.stat().st_mtime < cutoff_ep:
                        if arc_dir is not None:
                            dst_r = arc_dir / "Reports" / rf.name
                            dst_r.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(rf), str(dst_r))
                        else:
                            rf.unlink(missing_ok=True)
                        pruned_reports += 1
                except Exception:
                    pass

    # Clear stale driver_fixing.lock files
    removed_driver_locks = 0
    if lock_dirs is not None:
        stale_cutoff = time.time() - 120.0
        for ld in lock_dirs:
            lp = Path(ld) / "driver_fixing.lock"
            if lp.exists():
                try:
                    if lp.stat().st_mtime < stale_cutoff:
                        lp.unlink(missing_ok=True)
                        removed_driver_locks += 1
                except Exception:
                    pass
    else:
        try:
            from Core.scraper_engine import cleanup_stale_driver_locks

            removed_driver_locks = int(cleanup_stale_driver_locks(max_age_seconds=120) or 0)
        except Exception:
            if DOWNLOADED_FILES_DIR.exists():
                lp = DOWNLOADED_FILES_DIR / "driver_fixing.lock"
                if lp.exists() and lp.stat().st_mtime < (time.time() - 120.0):
                    lp.unlink(missing_ok=True)
                    removed_driver_locks += 1

    # Remove orphaned *.tmp files & stale bg_job_payload_*.json (> 24h)
    removed_temps = 0
    temp_cutoff = time.time() - 86400.0
    for scan_root in (c_dir, da_dir):
        if not scan_root.exists():
            continue
        for f in scan_root.rglob("*.tmp"):
            try:
                if f.is_file() and f.stat().st_mtime < temp_cutoff:
                    f.unlink(missing_ok=True)
                    removed_temps += 1
            except Exception:
                pass
    sys_cache_dir = c_dir / "System" if (c_dir / "System").exists() else c_dir
    if sys_cache_dir.exists():
        for pf in sys_cache_dir.glob("bg_job_payload_*.json"):
            try:
                if pf.is_file() and pf.stat().st_mtime < temp_cutoff:
                    pf.unlink(missing_ok=True)
                    removed_temps += 1
            except Exception:
                pass

    # Verify CSV/JSON integrity
    integrity_errors: list[str] = []
    checked_files = 0
    target_jsons = json_files if json_files is not None else [MAINTENANCE_SCHEDULE_FILE, LEARNED_SET_PRIORS_FILE]
    for jp in target_jsons:
        jpath = Path(jp)
        if not jpath.exists():
            continue
        checked_files += 1
        try:
            json.loads(jpath.read_text(encoding="utf-8-sig"))
        except Exception as e:
            integrity_errors.append(f"{jpath.name}: {e}")

    target_csvs = csv_files if csv_files is not None else [INVENTORY_FILE, CHECKLIST_PATH]
    for cp in target_csvs:
        cpath = Path(cp)
        if not cpath.exists():
            continue
        checked_files += 1
        try:
            with open(cpath, "r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, None)
                if not header:
                    integrity_errors.append(f"{cpath.name}: empty header")
        except Exception as e:
            integrity_errors.append(f"{cpath.name}: {e}")

    summary = (
        f"Pruned {pruned_logs} log dir(s) & {pruned_reports} report(s), "
        f"cleared {removed_driver_locks} stale driver lock(s) & {removed_temps} orphan temp(s), "
        f"verified {checked_files} data file(s)"
    )
    if integrity_errors:
        summary += f" ({len(integrity_errors)} integrity issue(s): {'; '.join(integrity_errors[:3])})"

    return {
        "ok": len(integrity_errors) == 0,
        "pruned_logs": pruned_logs,
        "pruned_reports": pruned_reports,
        "removed_driver_locks": removed_driver_locks,
        "removed_temps": removed_temps,
        "checked_files": checked_files,
        "integrity_errors": integrity_errors,
        "message": summary,
    }


def _default_task_runner(task_id: str) -> tuple[bool, str]:
    if task_id == "neural_index_sync":
        from Core.neural_vision import build_or_update_neural_embedding_index

        try:
            res = build_or_update_neural_embedding_index(force_rebuild=False, upgrade_legacy=True)
            indexed = int((res or {}).get("newly_embedded", (res or {}).get("indexed", 0)) or 0)
            skipped = int((res or {}).get("skipped_cached", 0) or 0)
            return True, f"Synced neural index (newly_embedded={indexed}, skipped_cached={skipped})."
        except RuntimeError as e:
            if "not installed" in str(e).lower():
                return True, f"Skipped neural index sync: {e}"
            raise

    if task_id == "master_checklist_rollup":
        from Core.scraper_engine import sync_set_library_download_status

        res = sync_set_library_download_status(rebuild_master_checklist=True)
        sets_cnt = int((res or {}).get("updated_sets", 0) or 0)
        return True, f"Master Checklist rollup complete ({sets_cnt} set(s) synced)."

    if task_id == "learned_set_priors_refresh":
        from Core.vision_grader import rebuild_learned_set_priors

        res = rebuild_learned_set_priors()
        tiers = (res or {}).get("counts") or {}
        return True, f"Refreshed learned_set_priors.json ({tiers or 'complete'})."

    if task_id == "housekeeping_hygiene":
        res = _run_housekeeping_hygiene()
        return bool(res.get("ok")), str(res.get("message") or "Housekeeping complete.")

    raise ValueError(f"Unknown maintenance task_id: {task_id}")


def run_maintenance_task(
    task_id: str,
    schedule_path: Optional[Path] = None,
    manual: bool = False,
    respect_idle_guard: bool = True,
    task_runner: Optional[Callable[[str], tuple[bool, str]]] = None,
    busy_checker: Optional[Callable[[], tuple[bool, str]]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Executes a single maintenance task with idle-guard deferral and atomic state persistence.
    """
    if task_id not in TASK_DEFINITIONS:
        return {"success": False, "status": "error", "message": f"Unknown task_id: {task_id}"}

    ref_now = now or datetime.now()
    now_str = ref_now.strftime("%Y-%m-%d %H:%M:%S")
    cfg = load_maintenance_schedule(schedule_path)
    t_entry = cfg["tasks"][task_id]

    if respect_idle_guard:
        busy, reason = is_worker_pool_busy(busy_checker=busy_checker)
        if busy:
            t_entry["last_status"] = "deferred"
            t_entry["deferred_count"] = int(t_entry.get("deferred_count") or 0) + 1
            t_entry["last_message"] = f"Deferred at {now_str} (worker busy: {reason})"
            saved = save_maintenance_schedule(cfg, schedule_path)
            return {
                "success": False,
                "deferred": True,
                "status": "deferred",
                "task_id": task_id,
                "message": t_entry["last_message"],
                "schedule": saved,
            }

    runner = task_runner or _default_task_runner
    try:
        ok, msg = runner(task_id)
        t_entry["last_run"] = now_str
        t_entry["last_status"] = "ok" if ok else "error"
        t_entry["last_message"] = f"{'[Manual] ' if manual else ''}{msg}".strip()
        if ok:
            t_entry["deferred_count"] = 0
    except Exception as exc:
        ok = False
        t_entry["last_run"] = now_str
        t_entry["last_status"] = "error"
        t_entry["last_message"] = f"{'[Manual] ' if manual else ''}Error: {exc}"

    saved = save_maintenance_schedule(cfg, schedule_path)
    return {
        "success": bool(ok),
        "deferred": False,
        "status": t_entry["last_status"],
        "task_id": task_id,
        "message": t_entry["last_message"],
        "schedule": saved,
    }


def tick_maintenance_scheduler(
    schedule_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    busy_checker: Optional[Callable[[], tuple[bool, str]]] = None,
    task_runner: Optional[Callable[[str], tuple[bool, str]]] = None,
) -> list[dict[str, Any]]:
    """Checks all enabled tasks in `maintenance_schedule.json` and runs due ones when idle."""
    ref_now = now or datetime.now()
    cfg = load_maintenance_schedule(schedule_path)
    results: list[dict[str, Any]] = []
    for tid in TASK_DEFINITIONS:
        t_cfg = cfg["tasks"].get(tid, {})
        if not is_task_due(t_cfg, now=ref_now):
            continue
        res = run_maintenance_task(
            tid,
            schedule_path=schedule_path,
            manual=False,
            respect_idle_guard=True,
            task_runner=task_runner,
            busy_checker=busy_checker,
            now=ref_now,
        )
        results.append(res)
        if res.get("deferred"):
            # Worker pool is busy; remaining due tasks also defer cleanly on this tick
            continue
    return results


def start_maintenance_scheduler_daemon(poll_seconds: int = 60) -> bool:
    """Starts the singleton background maintenance scheduler thread."""
    global _DAEMON_STARTED
    with _DAEMON_LOCK:
        if _DAEMON_STARTED:
            return False
        _DAEMON_STARTED = True

    interval = max(10, int(poll_seconds or 60))

    def _loop():
        # Short initial delay so startup cache prewarm finishes first
        if _DAEMON_STOP_EVENT.wait(timeout=min(15, interval)):
            return
        while not _DAEMON_STOP_EVENT.is_set():
            try:
                tick_maintenance_scheduler()
            except Exception:
                pass
            if _DAEMON_STOP_EVENT.wait(timeout=interval):
                break

    t = threading.Thread(target=_loop, name="tabulas-maintenance-scheduler", daemon=True)
    t.start()
    return True
