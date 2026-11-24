from __future__ import annotations
# ==============================================================================
# Core/scraper_engine.py - PHASE 2 SINGLE-PASS ASYNC + STEALTH TCDB CHECKLIST
# & TEMPLATE SCRAPER (WITH TCDB_CID, FULL FRONT/BACK DOWNLOAD & LIBRARY STATUS)
# ==============================================================================
import asyncio
import atexit
import csv
import hashlib
import inspect
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Union
from urllib.parse import quote, urljoin

import pandas as pd
import requests

__version__ = "0.25.0-beta.1"
__last_updated__ = "2026-11-21 18:45:00"

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from curl_cffi import requests as cffi_requests
    from curl_cffi.requests import AsyncSession as CffiAsyncSession
except ImportError:
    cffi_requests = None
    CffiAsyncSession = None

try:
    from seleniumbase import SB
except ImportError:
    SB = None

from Core.config import (
    ARCHIVE_CHECKLISTS_DIR,
    ARCHIVE_DIR,
    BASE_DIR,
    BN_TRACKING_FILE,
    CACHE_CATALOGS_DIR,
    CACHE_CHECKPOINTS_DIR,
    CHECKLIST_BACKUP_PATH,
    CHECKLIST_CACHE_FILE,
    CHECKLIST_COLUMNS,
    CHECKLIST_DIR,
    CHECKLIST_PATH,
    DEAD_BACKS_CACHE_PATH,
    DEAD_FRONTS_CACHE_PATH,
    DOWNLOADED_FILES_DIR,
    INVENTORY_DIR,
    IS_REORGANIZED_V24,
    LOGS_DIR,
    MASTER_DIRECTORY_CSV_FILE,
    REFERENCE_TEMPLATES_DIR,
    REPORTS_DIR,
    RESUME_FILE,
    SET_ALIAS_MAP,
    SET_CART_JSON_FILE,
    SET_CHECKLISTS_DIR,
    SET_LIBRARY_CACHE_DIR,
    TABULAS_VENV_PYTHON,
    TCDB_STANDARD_GLOSSARY,
    TRACKING_FILE,
    atomic_write_bytes,
    atomic_write_text,
    build_template_image_filename,
    build_template_image_filenames,
    canonical_set_key,
    canonical_subset_key,
    ensure_directories,
    format_print_run,
    interprocess_file_lock,
    norm,
    normalize_numeric_tcdb_cid,
    parse_unified_card_filename,
    sanitize_filename_part,
    strip_accents,
)
from Core.rate_learner import get_rate_learner

SCRAPER_ENGINE_VERSION = f"v{__version__}"
BASE_URL = "https://www.tcdb.com"

# Legacy compatibility symbol only — Download_Level has been removed; all sets download 100% of available images
DOWNLOAD_LEVELS = ("Full",)
DEAD_BACKS_TTL_DAYS = 30
DEAD_FRONTS_TTL_DAYS = 14
CHECKPOINT_SCHEMA_VERSION = 1

TCDB_SPORT_CODES = {
    "Baseball": 1,
    "Football": 2,
    "Basketball": 3,
    "Hockey": 4,
    "Soccer": 5,
    "Racing": 6,
    "Wrestling": 7,
    "MMA": 8,
    "Golf": 9,
}

# Guardrail: earliest year each sport has card sets on TCDB (prevents wasted crawl requests on non-existent years)
SPORT_FIRST_CARD_YEAR = {
    "Baseball": 1880,
    "Football": 1894,
    "Hockey": 1910,
    "Golf": 1926,
    "Basketball": 1948,
    "Racing": 1954,
    "Wrestling": 1954,
    "Soccer": 1958,
    "MMA": 2008,
}

ERA_BUCKETS = (
    "2026",
    "2025",
    "2024",
    "2020-2023",
    "2010-2019",
    "2000-2009",
    "1990-1999",
    "1980-1989",
    "Vintage (<1980)",
)

MASTER_DIRECTORY_FILE = MASTER_DIRECTORY_CSV_FILE
SET_CART_FILE = SET_CART_JSON_FILE
SCHEDULE_CONFIG_FILE = LOGS_DIR / "pipeline_schedule_config.json"
DEAD_BACKS_CACHE_FILE = DEAD_BACKS_CACHE_PATH
DEAD_FRONTS_CACHE_FILE = DEAD_FRONTS_CACHE_PATH

WINDOWS_TASK_NAME = "Tabulas_Scheduled_Pipeline_Job"
WINDOWS_DIR_TASK_NAME = "Tabulas_Scheduled_Directory_Crawl_Job"

MASTER_DIRECTORY_COLUMNS = [
    "SID",
    "Year",
    "Era",
    "Sport",
    "Set_Name",
    "Manufacturer",
    "Category",
    "Image_Pct",
    "Folder_Name",
    "TCDB_URL",
    "Last_Crawled",
]

MASTER_DOWNLOAD_LIST: list[dict] = []
RUN_METRICS: dict = {
    "total_checklists_evaluated": 0,
    "total_images_downloaded": 0,
    "total_images_upgraded": 0,
    "sets": {},
}

IMAGE_CARD_JITTER_MIN_S = 3.5
IMAGE_CARD_JITTER_MAX_S = 7.5
IMAGE_BREATHER_EVERY_CARDS = 500
IMAGE_BREATHER_MIN_S = 180.0
IMAGE_BREATHER_MAX_S = 300.0
DEFAULT_MAX_CARDS_PER_RUN = 4000
CLOUDFLARE_COOLDOWN_SCHEDULE_S = (900.0, 1800.0, 3600.0)

_LOG_CALLBACK: Optional[Callable[[str], None]] = None
_PROGRESS_CALLBACK: Optional[Callable[[dict], None]] = None
_STOP_CHECK_CALLBACK: Optional[Callable[[], bool]] = None
_PAUSE_CHECK_CALLBACK: Optional[Callable[[], bool]] = None
_PAUSE_STATE_CALLBACK: Optional[Callable[[bool, str], None]] = None

DEFAULT_MAX_CLEARANCE_FAILURES = 3
DEFAULT_PREFLIGHT_IMAGE_URL = "https://www.tcdb.com/Images/Large/Baseball/100/100-1Fr.jpg"


def set_log_callback(cb: Optional[Callable[[str], None]]):
    global _LOG_CALLBACK
    _LOG_CALLBACK = cb


def set_progress_callback(cb: Optional[Callable[[dict], None]]):
    global _PROGRESS_CALLBACK
    _PROGRESS_CALLBACK = cb


def set_stop_check_callback(cb: Optional[Callable[[], bool]]):
    global _STOP_CHECK_CALLBACK
    _STOP_CHECK_CALLBACK = cb


def set_pause_check_callback(cb: Optional[Callable[[], bool]]):
    global _PAUSE_CHECK_CALLBACK
    _PAUSE_CHECK_CALLBACK = cb


def set_pause_state_callback(cb: Optional[Callable[[bool, str], None]]):
    global _PAUSE_STATE_CALLBACK
    _PAUSE_STATE_CALLBACK = cb


def is_stop_requested() -> bool:
    if _STOP_CHECK_CALLBACK is not None:
        try:
            return bool(_STOP_CHECK_CALLBACK())
        except Exception:
            return False
    return False


def is_pause_requested() -> bool:
    if _PAUSE_CHECK_CALLBACK is not None:
        try:
            return bool(_PAUSE_CHECK_CALLBACK())
        except Exception:
            return False
    return False


def request_auto_pause(reason: str):
    msg = str(reason or "Auto-paused by scraper").strip()
    if _PAUSE_STATE_CALLBACK is not None:
        try:
            _PAUSE_STATE_CALLBACK(True, msg)
        except Exception:
            pass
    log_msg(f"⏸️ [AUTO-PAUSED] {msg}")
    emit_progress(current_item=msg)


def wait_if_paused(
    poll_interval: float = 0.5,
    sleep_fn: Callable[[float], None] = time.sleep,
    reason: str = "",
) -> bool:
    """
    Cooperatively pauses the calling worker while `is_pause_requested()` is True.
    Returns True if not paused or resumed cleanly; returns False if stop was requested.
    """
    if is_stop_requested():
        return False
    if not is_pause_requested():
        return True

    pause_msg = str(reason or "Paused by user — click Resume to continue").strip()
    if _PAUSE_STATE_CALLBACK is not None:
        try:
            _PAUSE_STATE_CALLBACK(True, pause_msg)
        except Exception:
            pass
    log_msg(f"⏸️ Worker paused ({pause_msg}). Waiting for Resume or Stop...")
    emit_progress(current_item=pause_msg)

    interval = max(0.05, float(poll_interval))
    while is_pause_requested():
        if is_stop_requested():
            log_msg("🛑 Stop requested while paused; exiting cleanly.")
            return False
        sleep_fn(interval)

    if is_stop_requested():
        return False
    if _PAUSE_STATE_CALLBACK is not None:
        try:
            _PAUSE_STATE_CALLBACK(False, "")
        except Exception:
            pass
    log_msg("▶️ Worker resumed!")
    return True


def emit_progress(**kwargs):
    if _PROGRESS_CALLBACK is not None:
        try:
            _PROGRESS_CALLBACK(kwargs)
        except Exception:
            pass


def log_msg(msg: str):
    clean = str(msg).rstrip("\r\n")
    if not clean:
        return
    if _LOG_CALLBACK is not None:
        try:
            _LOG_CALLBACK(clean)
            return
        except Exception:
            pass
    try:
        print(clean, flush=True)
    except Exception:
        print(clean.encode("ascii", errors="replace").decode("ascii"), flush=True)


def trim_clean(val) -> str:
    if val is None:
        return ""
    s = strip_accents(str(val))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_tcdb_sid(url: str) -> str:
    m = re.search(r"/sid/(\d+)", str(url or ""), re.IGNORECASE)
    return m.group(1) if m else ""


def canonicalize_checklist_set_title(set_name: str) -> str:
    """
    Uniform Set Naming Policy across checklists, tracked_sets.json, and tcdb_master_set_directory.csv:
      - Unifies 'Allen Ginter', 'Allen and Ginter', 'Allen & Ginter', 'A&G' -> 'Allen & Ginter'
      - Unifies '&' compounds ('Stars & Stripes', 'Black & White', 'Gold & Black', 'Pro & College')
      - Strips duplicate leading years ('2025 2025 Topps' -> '2025 Topps') and duplicate trailing sports
      - Restores season spans ('2025-26') and standard hyphenated terms ('8-Bit', 'X-Fractor')
    """
    clean = trim_clean(str(set_name or "").replace("_", " "))
    if not clean:
        return ""
    clean = _restore_season_years_and_hyphenated_terms(clean)
    clean = re.sub(r"^((?:19|20)\d{2}(?:-\d{2})?)\s+\1\b", r"\1", clean)
    clean = re.sub(r"\bAllen\s*(?:&|and|\+)?\s*Ginter(?:'s)?\b", "Allen & Ginter", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bTopps\s+A&G\b", "Topps Allen & Ginter", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bStars\s+and\s+Stripes\b", "Stars & Stripes", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bBlack\s+and\s+White\b", "Black & White", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bGold\s+and\s+Black\b", "Gold & Black", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bRed\s+White\s+and\s+Blue\b", "Red, White & Blue", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bPro\s+and\s+College\b", "Pro & College", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bSeries\s+One\b", "Series 1", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bSeries\s+Two\b", "Series 2", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(Baseball|Football|Basketball|Hockey|Soccer|Racing|Wrestling|MMA|Golf)\s+\1\b", r"\1", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*&\s*", " & ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" -_")

    n_key = norm(clean)
    if n_key in SET_ALIAS_MAP:
        return SET_ALIAS_MAP[n_key]
    return clean


def canonicalize_set_folder_name(set_name: str, sport: str = "", year: str = "") -> str:
    """
    Produces a uniform filesystem folder name matching the uniform naming policy, e.g.:
      '2025 Topps Allen Ginter' + 'Baseball' -> '2025_Topps_Allen_&_Ginter_Baseball'
      '2025 Topps Allen and Ginter Baseball' -> '2025_Topps_Allen_&_Ginter_Baseball'
    """
    title = canonicalize_checklist_set_title(set_name)
    yr_clean = str(year or "").strip()
    sp_clean = str(sport or "").strip()

    if yr_clean and not re.match(r"^(?:19|20)\d{2}", title):
        title = f"{yr_clean} {title}".strip()
    if sp_clean and sp_clean.lower() not in title.lower():
        title = f"{title} {sp_clean}".strip()

    title = canonicalize_checklist_set_title(title)
    return sanitize_filename_part(title)


def _is_placeholder_team_checklist_name(player_str: str) -> bool:
    p_up = trim_clean(player_str).upper()
    return (
        not p_up
        or p_up in ("CHECKLIST TEAM CARD", "TEAM CHECKLIST", "TEAM CARD", "CHECKLIST")
        or p_up.startswith("CHECKLIST TEAM CARD")
        or bool(re.match(r"^CHECKLIST\s*[:\-–]?\s*(?:\d+\s*[-–]\s*\d+)?$", p_up))
    )


def _is_league_leaders_title(player_str: str) -> bool:
    p_up = trim_clean(player_str).upper()
    return bool(
        "LEADERS" in p_up
        and (
            re.match(r"^(19|20)\d{2}\s+(AL|NL|MLB|AMERICAN\s+LEAGUE|NATIONAL\s+LEAGUE)\b", p_up)
            or "LEAGUE LEADERS" in p_up
            or any(
                k in p_up
                for k in (
                    "HOME RUN LEADERS",
                    "RUNS BATTED IN LEADERS",
                    "RBI LEADERS",
                    "BATTING AVERAGE LEADERS",
                    "BATTING LEADERS",
                    "EARNED RUN AVERAGE LEADERS",
                    "ERA LEADERS",
                    "STRIKEOUT LEADERS",
                    "WINS LEADERS",
                    "SAVES LEADERS",
                    "STOLEN BASE LEADERS",
                    "HITS LEADERS",
                )
            )
        )
    )


def format_checklist_team_card_player(player_str: str, team_str: str) -> str:
    p_clean = trim_clean(player_str)
    t_clean = trim_clean(team_str)
    if _is_placeholder_team_checklist_name(p_clean):
        if t_clean and t_clean.upper() not in ("NO TEAM", "UNKNOWN", "NAN", "NONE"):
            return t_clean.split("/")[0].strip()
    return p_clean


# ==============================================================================
# 0B. STEALTH BROWSER CLEARANCE + ADAPTIVE ASYNC RATE CONTROLLER
# ==============================================================================
class StealthBrowserError(Exception):
    pass


class CloudflareEdgeBlockPaused(Exception):
    """Raised when Cloudflare /Images/ rate-limiting persists across all circuit-breaker cooldowns or stop is requested."""
    pass


def cleanup_stale_driver_locks(
    max_age_seconds: float = 0.0,
    extra_dirs: Optional[list[Path]] = None,
) -> list[Path]:
    """
    Removes stale SeleniumBase `driver_fixing.lock` files across candidate `downloaded_files`
    directories so a crashed stealth-browser launch never blocks future retries.
    """
    removed: list[Path] = []
    candidate_dirs = [
        Path.cwd() / "downloaded_files",
        BASE_DIR / "downloaded_files",
        DOWNLOADED_FILES_DIR,
    ]
    if extra_dirs:
        candidate_dirs.extend(extra_dirs)

    seen: set[str] = set()
    now = time.time()
    for d in candidate_dirs:
        try:
            lock_path = Path(d) / "driver_fixing.lock"
            key = str(lock_path.resolve()) if lock_path.exists() else str(lock_path)
            if key in seen:
                continue
            seen.add(key)
            if lock_path.exists() and lock_path.is_file():
                if max_age_seconds > 0:
                    age = now - float(lock_path.stat().st_mtime)
                    if age < max_age_seconds:
                        continue
                try:
                    os.chmod(lock_path, stat.S_IWRITE)
                except Exception:
                    pass
                lock_path.unlink(missing_ok=True)
                removed.append(lock_path)
        except Exception:
            continue
    return removed


_TRACKED_DRIVER_PIDS: set[int] = set()
_TRACKED_DRIVER_PIDS_LOCK = threading.Lock()
_TRACKED_TEMP_PROFILE_DIRS: set[str] = set()
_TRACKED_TEMP_PROFILE_DIRS_LOCK = threading.Lock()


def cleanup_tracked_temp_profiles():
    with _TRACKED_TEMP_PROFILE_DIRS_LOCK:
        dirs_to_clean = list(_TRACKED_TEMP_PROFILE_DIRS)
        _TRACKED_TEMP_PROFILE_DIRS.clear()
    remaining: list[str] = []
    for d in dirs_to_clean:
        try:
            if d and Path(d).exists():
                shutil.rmtree(d, ignore_errors=True)
                if Path(d).exists():
                    remaining.append(d)
        except Exception:
            pass
    if remaining:
        with _TRACKED_TEMP_PROFILE_DIRS_LOCK:
            _TRACKED_TEMP_PROFILE_DIRS.update(remaining)


atexit.register(cleanup_tracked_temp_profiles)


def register_driver_pid(pid: Optional[int]):
    try:
        pid_i = int(pid or 0)
        if pid_i > 0:
            with _TRACKED_DRIVER_PIDS_LOCK:
                _TRACKED_DRIVER_PIDS.add(pid_i)
    except Exception:
        pass


def unregister_driver_pid(pid: Optional[int]):
    try:
        pid_i = int(pid or 0)
        if pid_i > 0:
            with _TRACKED_DRIVER_PIDS_LOCK:
                _TRACKED_DRIVER_PIDS.discard(pid_i)
    except Exception:
        pass


def cleanup_orphaned_drivers():
    with _TRACKED_DRIVER_PIDS_LOCK:
        pids_to_kill = list(_TRACKED_DRIVER_PIDS)
        _TRACKED_DRIVER_PIDS.clear()
    for pid in pids_to_kill:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    cleanup_stale_driver_locks()
    cleanup_tracked_temp_profiles()


def sanitize_header_value(val):
    if not isinstance(val, str):
        return val
    return quote(strip_accents(val), safe=":/?=&%-")


def preflight_probe_tcdb_images(
    req_session,
    test_image_url: str = "",
    timeout: float = 15.0,
    allow_404_as_ok: bool = False,
    user_agent: str = "",
    cookies: Optional[dict] = None,
) -> dict:
    """
    Lightweight Pre-Flight Probe verifying that the active session's `cf_clearance` cookie,
    exact User-Agent, and egress path can reach `/Images/Large/...` without a Cloudflare 403 block.
    Distinguishes: `200_ok`, `403_cf_block`, `503_origin_overload`, `404_not_found`, and `timeout`.
    """
    probe_url = str(test_image_url or DEFAULT_PREFLIGHT_IMAGE_URL).strip()
    active_cookies: dict[str, str] = {}
    if isinstance(cookies, dict) and cookies:
        active_cookies = {str(k): str(v) for k, v in cookies.items() if v is not None}
    else:
        cookies_obj = getattr(req_session, "cookies", None)
        try:
            if isinstance(cookies_obj, dict):
                active_cookies = {str(k): str(v) for k, v in cookies_obj.items() if v is not None}
            elif cookies_obj is not None:
                if hasattr(cookies_obj, "get_dict"):
                    active_cookies = {str(k): str(v) for k, v in cookies_obj.get_dict().items() if v is not None}
                else:
                    for c in cookies_obj:
                        c_name = getattr(c, "name", None)
                        c_val = getattr(c, "value", None)
                        if c_name is not None and c_val is not None:
                            active_cookies[str(c_name)] = str(c_val)
        except Exception:
            active_cookies = {}
    has_cf_clearance = bool(active_cookies.get("cf_clearance"))

    headers_obj = getattr(req_session, "headers", None) or {}
    ua = ""
    try:
        ua = str(user_agent or headers_obj.get("User-Agent") or headers_obj.get("user-agent") or "").strip()
    except Exception:
        ua = str(user_agent or "").strip()

    probe_headers: dict[str, str] = {"Referer": BASE_URL + "/"}
    if ua:
        probe_headers["User-Agent"] = ua

    accepts_cookies = False
    try:
        sig = inspect.signature(req_session.get)
        params = sig.parameters
        accepts_cookies = ("cookies" in params) or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except Exception:
        accepts_cookies = False

    t0 = time.time()
    try:
        get_kwargs: dict = {"headers": probe_headers, "timeout": timeout}
        if accepts_cookies and active_cookies:
            get_kwargs["cookies"] = active_cookies
        res = req_session.get(probe_url, **get_kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)
        code = int(getattr(res, "status_code", 0) or 0)
        ct = str((getattr(res, "headers", None) or {}).get("Content-Type", "")).lower()
        body_head = str(getattr(res, "text", "") or "")[:600]

        if code == 200 and ("image" in ct or ("Just a moment..." not in body_head and "cf-browser-verification" not in body_head)):
            msg = f"[PREFLIGHT OK] /Images/Large/ returned HTTP 200 ({elapsed_ms}ms, cf_clearance={has_cf_clearance})"
            log_msg(f"  ✅ {msg}")
            return {
                "ok": True,
                "status_code": 200,
                "classification": "200_ok",
                "url": probe_url,
                "has_cf_clearance": has_cf_clearance,
                "user_agent": ua,
                "elapsed_ms": elapsed_ms,
                "message": msg,
            }
        if code == 403 or (code == 200 and ("Just a moment..." in body_head or "cf-browser-verification" in body_head)):
            msg = "[PREFLIGHT BLOCKED: /Images/Large/ returned HTTP 403]"
            log_msg(f"  🛡️ {msg}")
            return {
                "ok": False,
                "status_code": 403,
                "classification": "403_cf_block",
                "url": probe_url,
                "has_cf_clearance": has_cf_clearance,
                "user_agent": ua,
                "elapsed_ms": elapsed_ms,
                "message": msg,
            }
        if code == 503:
            msg = f"[PREFLIGHT DEGRADED: /Images/Large/ returned HTTP 503 Origin-Overload ({elapsed_ms}ms)]"
            log_msg(f"  ⚠️ {msg}")
            return {
                "ok": False,
                "status_code": 503,
                "classification": "503_origin_overload",
                "url": probe_url,
                "has_cf_clearance": has_cf_clearance,
                "user_agent": ua,
                "elapsed_ms": elapsed_ms,
                "message": msg,
            }
        if code == 404:
            msg = f"[PREFLIGHT 404] /Images/Large/ probe asset returned HTTP 404 (CF edge reachable, {elapsed_ms}ms)"
            log_msg(f"  ℹ️ {msg}")
            return {
                "ok": bool(allow_404_as_ok),
                "status_code": 404,
                "classification": "404_not_found",
                "url": probe_url,
                "has_cf_clearance": has_cf_clearance,
                "user_agent": ua,
                "elapsed_ms": elapsed_ms,
                "message": msg,
            }
        msg = f"[PREFLIGHT WARN: /Images/Large/ returned HTTP {code} ({elapsed_ms}ms)]"
        log_msg(f"  ⚠️ {msg}")
        return {
            "ok": False,
            "status_code": code,
            "classification": f"http_{code}",
            "url": probe_url,
            "has_cf_clearance": has_cf_clearance,
            "user_agent": ua,
            "elapsed_ms": elapsed_ms,
            "message": msg,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        err_s = str(e) or type(e).__name__
        err_low = err_s.lower()
        is_to = isinstance(e, TimeoutError) or ("timed out" in err_low) or ("timeout" in err_low) or ("(28)" in err_low)
        cls = "timeout" if is_to else "network_error"
        msg = (
            f"[PREFLIGHT TIMEOUT: /Images/Large/ timed out ({elapsed_ms}ms)]"
            if is_to
            else f"[PREFLIGHT ERROR: /Images/Large/ failed ({err_s.splitlines()[0]})]"
        )
        log_msg(f"  ⚠️ {msg}")
        return {
            "ok": False,
            "status_code": 0,
            "classification": cls,
            "url": probe_url,
            "has_cf_clearance": has_cf_clearance,
            "user_agent": ua,
            "elapsed_ms": elapsed_ms,
            "message": msg,
        }


def connect_session(
    existing_session=None,
    max_attempts: int = 5,
    target_domain: str = BASE_URL,
    clearance_timeout_s: float = 20.0,
    run_preflight: bool = True,
    preflight_image_url: str = "",
    rotate_profile: bool = False,
    max_clearance_failures: int = DEFAULT_MAX_CLEARANCE_FAILURES,
    require_image_probe: Optional[bool] = None,
):
    """
    Launches SeleniumBase UC mode to clear Cloudflare on `target_domain`, extracts
    `cf_clearance` cookies and User-Agent, and injects them into `curl_cffi.requests.Session`.
    Waits explicitly up to `clearance_timeout_s` (default 20s) for real TCDB page readiness
    (stopping early as soon as ready), preserves healthy cookies/profile unless recovering
    from failure, runs a `/Images/Large/` pre-flight probe, and auto-pauses after
    `max_clearance_failures` consecutive clearance/preflight failures.
    """
    log_msg(f"🚀 Launching Stealth Browser to clear Cloudflare ({target_domain})...")

    if SB is None:
        log_msg("  [!] SeleniumBase (SB) not installed — using curl_cffi TLS session.")
        if existing_session is not None:
            return existing_session
        if cffi_requests is not None:
            return cffi_requests.Session(impersonate="chrome120")
        return requests.Session()

    if require_image_probe is not None:
        effective_require_image_probe = bool(require_image_probe)
    elif existing_session is not None and hasattr(existing_session, "_require_image_probe"):
        effective_require_image_probe = bool(getattr(existing_session, "_require_image_probe"))
    else:
        effective_require_image_probe = True

    consecutive_clearance_failures = 0
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        if is_stop_requested():
            raise CloudflareEdgeBlockPaused("Cancelled during stealth browser launch")
        if not wait_if_paused(reason="Paused before stealth browser launch"):
            raise CloudflareEdgeBlockPaused("Stopped while paused during stealth browser launch")

        use_fresh_profile = bool(rotate_profile or attempt > 1)
        temp_profile_dir: Optional[str] = None
        try:
            cleanup_orphaned_drivers()
            time.sleep(1.5)

            session_pids: list[int] = []
            sb_kwargs: dict = {"uc": True, "window_size": "800,1000"}
            if use_fresh_profile:
                temp_profile_dir = tempfile.mkdtemp(prefix="tcdb_uc_prof_")
                with _TRACKED_TEMP_PROFILE_DIRS_LOCK:
                    _TRACKED_TEMP_PROFILE_DIRS.add(temp_profile_dir)
                sb_kwargs["user_data_dir"] = temp_profile_dir
                log_msg("  🔄 Rotating to fresh isolated Stealth Browser profile for recovery...")

            clearance_ready = False
            cookies: dict[str, str] = {}
            ua = ""
            try:
                with SB(**sb_kwargs) as sb:
                    try:
                        svc = getattr(getattr(sb, "driver", None), "service", None)
                        svc_proc = getattr(svc, "process", None)
                        if svc_proc and getattr(svc_proc, "pid", None):
                            session_pids.append(int(svc_proc.pid))
                            register_driver_pid(svc_proc.pid)
                        br_pid = getattr(getattr(sb, "driver", None), "browser_pid", None)
                        if br_pid:
                            session_pids.append(int(br_pid))
                            register_driver_pid(br_pid)
                    except Exception:
                        pass

                    sb.uc_open_with_reconnect(target_domain, 5)
                    max_wait = max(1.0, float(clearance_timeout_s or 20.0))
                    log_msg(f"⏳ Waiting up to {int(round(max_wait))}s for explicit TCDB Cloudflare clearance (Attempt {attempt}/{max_attempts})...")
                    wait_t0 = time.time()
                    while (time.time() - wait_t0) < max_wait:
                        if is_stop_requested():
                            raise CloudflareEdgeBlockPaused("Cancelled during Cloudflare clearance wait")
                        if not wait_if_paused(reason="Paused during Cloudflare clearance wait"):
                            raise CloudflareEdgeBlockPaused("Stopped while paused during Cloudflare clearance")
                        try:
                            if sb.driver.window_handles:
                                sb.driver.switch_to.window(sb.driver.window_handles[-1])
                            cur_cookies = {c["name"]: c["value"] for c in (sb.driver.get_cookies() or [])}
                            title_s = str(getattr(sb.driver, "title", "") or "")
                            src_head = str(getattr(sb.driver, "page_source", "") or "")[:1200]
                            ready_state = str(sb.driver.execute_script("return document.readyState;") or "")
                            is_cf_page = (
                                "just a moment" in title_s.lower()
                                or "cf-browser-verification" in src_head.lower()
                                or "just a moment..." in src_head.lower()
                            )
                            has_clearance = bool(cur_cookies.get("cf_clearance"))
                            if not is_cf_page and (has_clearance or (ready_state in ("interactive", "complete") and len(src_head) > 100)):
                                clearance_ready = True
                                elapsed_c = time.time() - wait_t0
                                log_msg(f"  ✅ TCDB page ready in {elapsed_c:.1f}s (cf_clearance={has_clearance}).")
                                break
                        except CloudflareEdgeBlockPaused:
                            raise
                        except Exception:
                            pass
                        sb.sleep(1.0)

                    if sb.driver.window_handles:
                        sb.driver.switch_to.window(sb.driver.window_handles[-1])

                    cookies = {cookie["name"]: cookie["value"] for cookie in (sb.driver.get_cookies() or [])}
                    ua = sb.driver.execute_script("return navigator.userAgent;")
            finally:
                for spid in session_pids:
                    unregister_driver_pid(spid)
                if temp_profile_dir:
                    shutil.rmtree(temp_profile_dir, ignore_errors=True)
                    if not Path(temp_profile_dir).exists():
                        with _TRACKED_TEMP_PROFILE_DIRS_LOCK:
                            _TRACKED_TEMP_PROFILE_DIRS.discard(temp_profile_dir)

            if not clearance_ready and not cookies.get("cf_clearance"):
                raise RuntimeError(f"Cloudflare clearance timed out after {int(round(max_wait))}s")

            if existing_session is not None:
                if use_fresh_profile:
                    existing_session.cookies.clear()
                existing_session.headers.update({"User-Agent": ua})
                existing_session.cookies.update(cookies)
                target_sess = existing_session
            else:
                target_sess = cffi_requests.Session(impersonate="chrome120") if cffi_requests is not None else requests.Session()
                target_sess.headers.update({"User-Agent": ua})
                target_sess.cookies.update(cookies)

            try:
                setattr(target_sess, "_require_image_probe", effective_require_image_probe)
            except Exception:
                pass

            if run_preflight and effective_require_image_probe:
                probe = preflight_probe_tcdb_images(
                    target_sess,
                    test_image_url=preflight_image_url,
                    allow_404_as_ok=True,
                    user_agent=ua,
                    cookies=cookies,
                )
                if probe.get("classification") == "403_cf_block":
                    raise RuntimeError(probe.get("message") or "Pre-flight /Images/Large/ returned HTTP 403")
            elif run_preflight and not effective_require_image_probe:
                log_msg("  ℹ️ Skipping /Images/Large/ pre-flight gate (checklist/HTML-only mode; require_image_probe=False).")

            if existing_session is not None:
                log_msg("✅ Cloudflare session refreshed in-place!")
            else:
                log_msg("✅ Cloudflare clearance acquired!")
            return target_sess

        except CloudflareEdgeBlockPaused:
            raise
        except Exception as e:
            consecutive_clearance_failures += 1
            err_line = str(e).splitlines()[0] if str(e) else "Unknown Error"
            cleanup_orphaned_drivers()
            if consecutive_clearance_failures >= max(1, int(max_clearance_failures or DEFAULT_MAX_CLEARANCE_FAILURES)):
                pause_msg = (
                    f"Auto-paused after {consecutive_clearance_failures} clearance failures — "
                    f"switch VPN node or clear CAPTCHA, then click Resume"
                )
                request_auto_pause(pause_msg)
                if _PAUSE_CHECK_CALLBACK is not None and is_pause_requested():
                    resumed = wait_if_paused(reason=pause_msg)
                    if resumed:
                        consecutive_clearance_failures = 0
                        rotate_profile = True
                        attempt = 0
                        continue
                raise CloudflareEdgeBlockPaused(pause_msg)

            wait_s = 4 * attempt
            log_msg(f"  ⚠️ Stealth browser handshake failed ({err_line}). Retrying in {wait_s}s ({attempt}/{max_attempts})...")
            time.sleep(wait_s)

    raise StealthBrowserError("Failed to establish Stealth Browser session after maximum retries.")


class CloudflareImageCircuitBreaker:
    """
    Guards TCDB image downloads against Cloudflare edge 403/429 death loops:
      - Allows at most 1 stealth-browser re-auth attempt per block burst.
      - If the very next request after re-auth still returns 403 (or 429 exhausts),
        trips exponential cooldowns (15m -> 30m -> 60m) polling stop signals every 2s.
      - After 3 failed cooldowns, raises `CloudflareEdgeBlockPaused` cleanly.
    """

    def __init__(
        self,
        cooldown_schedule: tuple[float, ...] = CLOUDFLARE_COOLDOWN_SCHEDULE_S,
        stop_poll_interval: float = 2.0,
        stop_check: Optional[Callable[[], bool]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        reauth_fn: Optional[Callable[..., object]] = None,
    ):
        self.cooldown_schedule = tuple(float(x) for x in cooldown_schedule)
        self.stop_poll_interval = max(0.05, float(stop_poll_interval))
        self.stop_check = stop_check
        self.sleep_fn = sleep_fn
        self.reauth_fn = reauth_fn
        self.consecutive_blocks = 0
        self.reauth_attempted_in_burst = False
        self.awaiting_post_reauth_probe = False
        self.cooldown_stage = 0
        self.total_reauths = 0
        self.total_cooldowns = 0
        self.tripped_pause = False

    def _is_stopped(self) -> bool:
        if self.stop_check is not None:
            try:
                if self.stop_check():
                    return True
            except Exception:
                pass
        return is_stop_requested()

    def record_success(self):
        self.consecutive_blocks = 0
        self.reauth_attempted_in_burst = False
        self.awaiting_post_reauth_probe = False
        self.cooldown_stage = 0

    def interruptible_sleep(self, seconds: float, reason: str = "") -> bool:
        if not wait_if_paused(poll_interval=self.stop_poll_interval, sleep_fn=self.sleep_fn, reason=reason):
            return False
        remaining = max(0.0, float(seconds))
        while remaining > 0.0:
            if self._is_stopped():
                if reason:
                    log_msg(f"🛑 Stop requested during {reason}; exiting cleanly.")
                return False
            if is_pause_requested():
                if not wait_if_paused(poll_interval=self.stop_poll_interval, sleep_fn=self.sleep_fn, reason=reason):
                    return False
            chunk = min(self.stop_poll_interval, remaining)
            self.sleep_fn(chunk)
            remaining -= chunk
        return not self._is_stopped()

    def handle_block(self, status_code: int, url: str, req_session) -> str:
        self.consecutive_blocks += 1

        if status_code == 403 and not self.reauth_attempted_in_burst:
            self.reauth_attempted_in_burst = True
            self.awaiting_post_reauth_probe = True
            self.total_reauths += 1
            log_msg(
                f"  🛡️ [HTTP 403 Circuit Breaker] Burst #{self.consecutive_blocks} on {url} — "
                f"Running single stealth-browser re-auth attempt (1/1)..."
            )
            reauth_callable = self.reauth_fn or connect_session
            reauth_callable(existing_session=req_session, target_domain=BASE_URL)
            if not self.interruptible_sleep(3.0, reason="post-reauth settle"):
                raise CloudflareEdgeBlockPaused("Cancelled during Cloudflare re-auth")
            return "retry"

        self.awaiting_post_reauth_probe = False
        if self.cooldown_stage >= len(self.cooldown_schedule):
            self.tripped_pause = True
            msg = "Cloudflare /Images/ rate-limit active — paused safely"
            log_msg(
                f"🛑 {msg} (HTTP {status_code} persisted after {len(self.cooldown_schedule)} cooldowns: "
                f"{' -> '.join(f'{int(s // 60)}m' for s in self.cooldown_schedule)})."
            )
            emit_progress(current_item=msg)
            raise CloudflareEdgeBlockPaused(msg)

        wait_s = self.cooldown_schedule[self.cooldown_stage]
        self.cooldown_stage += 1
        self.total_cooldowns += 1
        wait_mins = wait_s / 60.0
        log_msg(
            f"🛑 [Cloudflare Edge Block Circuit Breaker] HTTP {status_code} persisted on {url}. "
            f"Sleeping {wait_mins:.1f}m (cooldown {self.cooldown_stage}/{len(self.cooldown_schedule)})..."
        )
        emit_progress(
            current_item=f"⏸️ Cloudflare /Images/ cooldown ({wait_mins:.0f}m, stage {self.cooldown_stage}/{len(self.cooldown_schedule)})..."
        )
        if not self.interruptible_sleep(wait_s, reason=f"Cloudflare cooldown {self.cooldown_stage}/{len(self.cooldown_schedule)}"):
            raise CloudflareEdgeBlockPaused("Cancelled during Cloudflare cooldown")
        return "retry"


class AdaptiveRateController:
    """
    Shared concurrency and adaptive rate controller for async TCDB HTML & image fetches:
      - Enforces bounded concurrency (`html_concurrency=3`, `img_concurrency=6`)
      - Applies global cooldown pause if any worker hits HTTP 429 or Cloudflare 403
      - Gradually speeds up on consecutive HTTP 200 responses.
    """

    def __init__(self, html_concurrency: int = 3, img_concurrency: int = 6, min_interval: float = 0.28):
        self.html_sem = asyncio.Semaphore(html_concurrency)
        self.img_sem = asyncio.Semaphore(img_concurrency)
        self.interval = min_interval
        self.min_interval = min_interval
        self.max_interval = 4.0
        self.pause_until = 0.0
        self.success_streak = 0
        self._lock = asyncio.Lock()

    async def wait_turn(self, is_image: bool = False):
        now = time.time()
        if self.pause_until > now:
            await asyncio.sleep(self.pause_until - now)
        async with self._lock:
            delay = self.interval * (0.45 if is_image else 1.0)
            await asyncio.sleep(delay)

    def record_success(self):
        self.success_streak += 1
        if self.success_streak >= 15 and self.interval > self.min_interval:
            self.interval = max(self.min_interval, self.interval * 0.90)
            self.success_streak = 0

    def record_throttle(self, pause_sec: float = 25.0):
        self.success_streak = 0
        self.interval = min(self.max_interval, self.interval * 1.65 + 0.35)
        self.pause_until = max(self.pause_until, time.time() + pause_sec)


def safe_get(
    req_session,
    url: str,
    headers: Optional[dict] = None,
    retries: int = 4,
    timeout: int = 30,
    silent_404: bool = False,
    max_403_retries: Optional[int] = None,
    status_out: Optional[dict] = None,
    circuit_breaker: Optional[CloudflareImageCircuitBreaker] = None,
):
    """
    Adaptive rate-aware HTTP GET sharing the unified `tcdb_domain` sliding-window bucket:
      - Separates HTTP 429 retries (up to 5 window-aware retries) from normal retries.
      - Supports `max_403_retries=1` for optional pages like `Errors.cfm` so disabled
        pages never loop Stealth Browser launches.
      - Supports `status_out` for strict HTTP status reporting and `circuit_breaker`
        for Cloudflare /Images/ 403/429 edge-block protection.
    """
    clean_url = quote(str(url), safe=":/?=&%-")
    clean_headers = {k: sanitize_header_value(v) for k, v in (headers or {}).items()}
    learner = get_rate_learner()
    ep_key = learner.classify_tcdb_endpoint(clean_url)

    def _record_status(code: int, err: str = ""):
        if isinstance(status_out, dict):
            status_out["status_code"] = int(code)
            status_out["error"] = err

    net_attempt = 0
    rl_attempt = 0
    cf_403_attempt = 0
    max_rl_retries = 5

    while net_attempt < retries:
        if is_stop_requested():
            raise CloudflareEdgeBlockPaused("Cancelled during HTTP fetch")
        if not wait_if_paused(reason="Paused before HTTP fetch"):
            raise CloudflareEdgeBlockPaused("Stopped while paused during HTTP fetch")
        learner.wait_before_request(ep_key)
        t0 = time.time()
        try:
            res = req_session.get(clean_url, headers=clean_headers or None, timeout=timeout)
            elapsed_ms = int((time.time() - t0) * 1000)

            if res.status_code == 200:
                ct = str(res.headers.get("Content-Type", "")).lower()
                if "image" not in ct:
                    txt_head = (res.text or "")[:600]
                    if "Just a moment..." in txt_head or "cf-browser-verification" in txt_head:
                        _record_status(403, "cf_challenge_200")
                        learner.record_cf_challenge(ep_key)
                        if circuit_breaker is not None:
                            action = circuit_breaker.handle_block(403, clean_url, req_session)
                            if action == "retry":
                                continue
                            return None
                        net_attempt += 1
                        log_msg(f"  🛡️ [HTTP 200 CF-Challenge | {elapsed_ms}ms] {clean_url} — Refreshing session ({net_attempt}/{retries})")
                        connect_session(
                            existing_session=req_session,
                            target_domain=BASE_URL,
                            require_image_probe=bool(getattr(req_session, "_require_image_probe", "/Images/" in clean_url)),
                        )
                        time.sleep(3)
                        continue
                _record_status(200, "")
                learner.record_success(ep_key, elapsed_ms=elapsed_ms, status_code=200)
                if circuit_breaker is not None:
                    circuit_breaker.record_success()
                return res
            elif res.status_code == 404:
                _record_status(404, "404")
                learner.record_success(ep_key, elapsed_ms=elapsed_ms, status_code=404)
                if circuit_breaker is not None:
                    circuit_breaker.record_success()
                if not silent_404:
                    log_msg(f"  [HTTP 404 Not Found | {elapsed_ms}ms] {clean_url}")
                return None
            elif res.status_code == 403:
                _record_status(403, "403")
                learner.record_cf_challenge(ep_key)
                if circuit_breaker is not None:
                    action = circuit_breaker.handle_block(403, clean_url, req_session)
                    if action == "retry":
                        continue
                    return None
                net_attempt += 1
                cf_403_attempt += 1
                if max_403_retries is not None and cf_403_attempt > max_403_retries:
                    log_msg(f"  ℹ️ [HTTP 403 Guard | {elapsed_ms}ms] {clean_url} still 403 after {max_403_retries} refresh(es) — skipping optional page.")
                    return None
                log_msg(f"  🛡️ [HTTP 403 Forbidden | {elapsed_ms}ms] {clean_url} — Re-authenticating Cloudflare ({net_attempt}/{retries})")
                connect_session(
                    existing_session=req_session,
                    target_domain=BASE_URL,
                    require_image_probe=bool(getattr(req_session, "_require_image_probe", "/Images/" in clean_url)),
                )
                time.sleep(3)
                continue
            elif res.status_code == 429:
                _record_status(429, "429")
                rl_attempt += 1
                ra_hdr = res.headers.get("Retry-After") if hasattr(res, "headers") else None
                wait_time, learn_note = learner.record_rate_limit(ep_key, retry_after_header=ra_hdr)
                log_msg(
                    f"  🛑 [HTTP 429 Rate Limit | {elapsed_ms}ms] {clean_url} — "
                    f"Window-aware cooldown {wait_time:.0f}s ({rl_attempt}/{max_rl_retries}) | 🧠 {learn_note}"
                )
                if rl_attempt >= max_rl_retries:
                    if circuit_breaker is not None:
                        action = circuit_breaker.handle_block(429, clean_url, req_session)
                        if action == "retry":
                            rl_attempt = 0
                            continue
                    log_msg(f"  ❌ [HTTP 429 Exhausted] Giving up on {clean_url} after {max_rl_retries} rate-limit retries.")
                    return None
                time.sleep(wait_time)
                continue
            elif res.status_code in (500, 502, 503, 504):
                _record_status(res.status_code, f"http_{res.status_code}")
                net_attempt += 1
                log_msg(f"  ⚠️ [HTTP {res.status_code} Server Error | {elapsed_ms}ms] {clean_url} — Retry ({net_attempt}/{retries})")
                if net_attempt < retries:
                    time.sleep(12 * net_attempt)
                    continue
                return None
            else:
                _record_status(res.status_code, f"http_{res.status_code}")
                net_attempt += 1
                log_msg(f"  ⚠️ [HTTP {res.status_code} | {elapsed_ms}ms] {clean_url} — Attempt ({net_attempt}/{retries})")
                if net_attempt < retries:
                    time.sleep(8 * net_attempt)
        except (StealthBrowserError, CloudflareEdgeBlockPaused):
            raise
        except Exception as e:
            err_line = str(e).splitlines()[0] if str(e) else type(e).__name__
            _record_status(0, err_line)
            net_attempt += 1
            elapsed_ms = int((time.time() - t0) * 1000)
            log_msg(f"  🔌 [Conn Error | {elapsed_ms}ms] {clean_url} ({net_attempt}/{retries}): {err_line}")
            if net_attempt == 3:
                connect_session(
                    existing_session=req_session,
                    target_domain=BASE_URL,
                    require_image_probe=bool(getattr(req_session, "_require_image_probe", "/Images/" in clean_url)),
                )
            elif net_attempt < retries:
                time.sleep(6 * net_attempt)
            else:
                return None
    return None


def decode_html_response(resp) -> str:
    if resp is None or not getattr(resp, "content", None):
        return ""
    for enc in ("utf-8", "cp1252", "latin1"):
        try:
            return resp.content.decode(enc)
        except Exception:
            continue
    return str(getattr(resp, "text", "") or "")


def is_valid_image_payload(content: Optional[bytes]) -> bool:
    if not content or len(content) < 512:
        return False
    if content[:20].lstrip().startswith(b"<"):
        return False
    return True


def _is_college_section_heading(tag_el) -> bool:
    if tag_el is None or not hasattr(tag_el, "find_all_previous"):
        return False
    for prev in tag_el.find_all_previous(["h1", "h2", "h3", "h4", "strong", "b"], limit=3):
        txt = trim_clean(prev.get_text(" ", strip=True)).upper()
        if txt in ("COLLEGE", "COLLEGIATE"):
            return True
    return False


def _add_tag(tags_list: list[str], t_raw: str, print_run: str = ""):
    t_up = str(t_raw or "").strip().upper()
    if not t_up:
        return
    if t_up in ("AU", "AUTO", "AUTOGRAPH", "AUTOGRAPHED"):
        canon = "Auto"
    elif t_up in ("MEM", "REL", "RELIC", "MEMORABILIA"):
        canon = "Mem"
    elif t_up.startswith("SN") and len(t_up) > 2 and t_up[2:].isdigit():
        canon = f"#/{t_up[2:]}"
    elif re.match(r"^#/\d+$", t_up) or t_up == "1/1":
        canon = t_up
    elif print_run and t_up in ("SN", "SERIAL"):
        canon = f"#/{format_print_run(print_run)}"
    else:
        canon = t_up

    if canon not in tags_list:
        tags_list.append(canon)


def format_attributes_column(tags: list[str], paren_players: str = "") -> str:
    if not tags and not paren_players:
        return ""
    out_parts = []
    attached_players = False
    for t in tags:
        if t in ("LL", "CPC") and paren_players and not attached_players:
            out_parts.append(f"{t} [{paren_players}]")
            attached_players = True
        else:
            out_parts.append(t)
    if paren_players and not attached_players:
        out_parts.append(f"CPC [{paren_players}]")
    return ", ".join(out_parts)


def _restore_season_years_and_hyphenated_terms(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"\b(19\d{2}|20\d{2})\s+(\d{2})\b", r"\1-\2", s)
    s = re.sub(r"\b8\s+Bit\b", "8-Bit", s, flags=re.IGNORECASE)
    s = re.sub(r"\bX\s+Fractor\b", "X-Fractor", s, flags=re.IGNORECASE)
    s = re.sub(r"\bA\s*&\s*G\b", "A&G", s, flags=re.IGNORECASE)
    s = re.sub(r"\bA\s+and\s+G\b", "A&G", s, flags=re.IGNORECASE)
    s = re.sub(r"\bDie\s+Cut\b", "Die-Cut", s, flags=re.IGNORECASE)
    s = re.sub(r"\bMini\s+Diamond\b", "Mini-Diamond", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAll\s+Star\b", "All-Star", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAll\s+Time\b", "All-Time", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNon\s+Sport\b", "Non-Sport", s, flags=re.IGNORECASE)
    s = re.sub(r"\bTri\s+Color\b", "Tri-Color", s, flags=re.IGNORECASE)
    s = re.sub(r"\bOne\s+of\s+One\b", "One-of-One", s, flags=re.IGNORECASE)
    s = re.sub(r"\bA\s+G\s+(Back|Man\s+Back|Mini|No\s+Number|Logo)\b", r"A&G \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bA\s+G$", "A&G", s, flags=re.IGNORECASE)
    return s


# ==============================================================================
# 1. TRACKED SETS REGISTRY, STAGED SET CART & MASTER SET DIRECTORY ENGINE
# ==============================================================================
def normalize_download_level(level_val: Optional[str] = None, set_hint: str = "") -> str:
    """Legacy shim retained for backwards compatibility — every tracked set archives 100% of available images."""
    return "Full"


_EXPLICIT_MANUFACTURER_PATTERNS: list[tuple[str, str]] = [
    (r"\bO-Pee-Chee\b|\bOPC\b", "O-Pee-Chee"),
    (r"\bBowman\b", "Bowman"),
    (r"\bTopps\b|\bBazooka\b|\bMerlin\b|\bMatch\s+Attax\b|\bTurbo\s+Attax\b", "Topps"),
    (r"\bPanini\b", "Panini"),
    (r"\bUpper\s+Deck\b|\bUD\s+(?:Choice|Reserve|Authentics|Icons|Premier|Black|Ice)\b", "Upper Deck"),
    (r"\bDonruss\b", "Donruss"),
    (r"\bFleer\b", "Fleer"),
    (r"\bSkyBox\b|\bMetal\s+Universe\b", "SkyBox"),
    (r"\bLeaf\b", "Leaf"),
    (r"\bScore\b", "Score"),
    (r"\bWild\s+Card\b", "Wild Card"),
    (r"\bONIT\b", "ONIT Athlete"),
    (r"\bSage\b", "Sage"),
    (r"\bPress\s+Pass\b", "Press Pass"),
    (r"\bTriStar\b|\bTri-Star\b", "TriStar"),
    (r"\bOnyx\b", "Onyx"),
    (r"\bHistoric\s+Autographs\b", "Historic Autographs"),
    (r"\bJersey\s+Fusion\b", "Jersey Fusion"),
    (r"\bSuper\s+Break\b", "Super Break"),
    (r"\bKeepsake\b", "Keepsake"),
    (r"\bFutera\b", "Futera"),
    (r"\bParkside\b", "Parkside"),
    (r"\bSportkings\b", "Sportkings"),
    (r"\bPro\s+Set\b", "Pro Set"),
    (r"\bPacific\b", "Pacific"),
    (r"\bPinnacle\b", "Pinnacle"),
    (r"\bPlayoff\b", "Playoff"),
    (r"\bClassic\b", "Classic"),
    (r"\bCollector'?s\s+Edge\b", "Collector's Edge"),
    (r"\bAction\s+Packed\b", "Action Packed"),
    (r"\bParkhurst\b", "Parkhurst"),
    (r"\bIn\s+The\s+Game\b|\bITG\b", "In The Game"),
    (r"\bPresident'?s\s+Choice\b", "President's Choice"),
    (r"\bRittenhouse\b", "Rittenhouse"),
    (r"\bCryptozoic\b", "Cryptozoic"),
    (r"\bChampions\s+Deck\b", "Champions Deck"),
    (r"\bFanatics\b", "Fanatics"),
    (r"\bPieces\s+of\s+the\s+Past\b", "Pieces of the Past"),
    (r"\bChoice\s+Marketing\b|\bGrandstand\b|\bMulti-Ad\b|\bTeam\s+Best\b|\bJust\s+Minors\b", "Minor League / Regional"),
]

_SUBBRAND_MANUFACTURER_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(Prizm|Select|Mosaic|Optic|Contenders|Chronicles|National\s+Treasures|Immaculate|Flawless|"
        r"Spectra|Obsidian|Origins|Phoenix|Certified|Absolute|Prestige|Illusions|Playbook|Noir|"
        r"Court\s+Kings|NBA\s+Hoops|Hoops|Revolution|Crown\s+Royale|Photogenic|Recon|Eminence|"
        r"One\s+and\s+One|Zenith|Rookies\s*&\s*Stars|Gold\s+Standard|Limited|Encased|Impeccable|"
        r"Plates\s*&\s*Patches|Adrenalyn|Panini\s+Instant)\b",
        "Panini",
    ),
    (
        r"\b(SP\s+Authentic|SP\s+Game\s+Used|SP\s+Signature|SPx|Artifacts|Allure|The\s+Cup|Stature|"
        r"Synergy|Black\s+Diamond|Goodwin\s+Champions|Exquisite|Credentials|Trilogy|Clear\s+Cut|"
        r"Engrained|Tim\s+Hortons|SkyBox\s+Metal)\b",
        "Upper Deck",
    ),
    (
        r"\b(Allen\s*&\s*Ginter|Stadium\s+Club|Gypsy\s+Queen|Triple\s+Threads|Museum\s+Collection|"
        r"Tier\s+One|Definitive|Dynasty|Luminaries|Transcendent|Big\s+League|Opening\s+Day|"
        r"Pro\s+Debut|Cosmic\s+Chrome|Logofractor|Eccellenza|Lights\s+Out|Resurgence|Inception|"
        r"Tribute|Pristine|Finest|Heritage|Archives|Gallery)\b",
        "Topps",
    ),
]


def _infer_manufacturer(set_title: str, url: str = "", existing_mfg: str = "", category: str = "") -> str:
    """Accurately infers card manufacturer from set title & URL without falsely defaulting unknown brands to Topps."""
    combined = f"{set_title} {url}".replace("_", " ").replace("-", " ")
    for pat, mfg_name in _EXPLICIT_MANUFACTURER_PATTERNS:
        if re.search(pat, combined, re.IGNORECASE):
            return mfg_name
    for pat, mfg_name in _SUBBRAND_MANUFACTURER_PATTERNS:
        if re.search(pat, combined, re.IGNORECASE):
            return mfg_name
    ex_clean = str(existing_mfg or "").strip()
    if ex_clean and ex_clean.lower() not in ("topps", "unknown", "none", "nan"):
        return ex_clean
    cat_low = str(category or "").lower()
    if any(k in cat_low for k in ("college", "team issue", "stadium giveaway", "sga", "promo")) or any(
        k in combined.lower() for k in ("sga", "juco", "world series", "community college")
    ):
        return "Team / School Issue"
    return "Other"


_CANONICAL_TCDB_SECTIONS = {
    "major releases": "Major Releases",
    "major release": "Major Releases",
    "box sets": "Box Sets",
    "box / factory set": "Box Sets",
    "college": "College",
    "collegiate / nil": "College",
    "college summer league": "College Summer League",
    "japanese league": "Japanese League",
    "minor league": "Minor League",
    "minor league / draft": "Minor League",
    "oddball": "Oddball",
    "stickers / oddball": "Oddball",
    "on-demand": "On-Demand",
    "online exclusive": "On-Demand",
    "promo": "Promo",
    "stadium giveaway (sga)": "Stadium Giveaway (SGA)",
    "team issues": "Team Issues",
    "team issue / promo": "Team Issues",
    "regional / food": "Regional / Food",
    "regional / retail": "Regional / Food",
    "international": "International",
    "repack / memorabilia": "Repack / Memorabilia",
}


def _infer_set_category(set_title: str, sport: str = "", section_heading: str = "", existing_cat: str = "") -> str:
    """
    Preserves TCDB's exact official `<h3 class='site'>` section heading from `ViewAll.cfm`
    when present, and uses disciplined keyword classification for offline rows.
    """
    sec_raw = trim_clean(section_heading)
    if sec_raw:
        sec_low = sec_raw.lower()
        if sec_low in _CANONICAL_TCDB_SECTIONS:
            return _CANONICAL_TCDB_SECTIONS[sec_low]
        if len(sec_raw) <= 40 and not re.match(r"^\d{4}$", sec_raw):
            return sec_raw

    ex_raw = trim_clean(existing_cat)
    if ex_raw and ex_raw.lower() in _CANONICAL_TCDB_SECTIONS:
        return _CANONICAL_TCDB_SECTIONS[ex_raw.lower()]

    low = f" {set_title} ".lower()
    if any(k in low for k in (" topps now", " panini instant", " on-demand", " project 70", " project 2020", " living set", " topps x ", " online exclusive")):
        return "On-Demand"
    if any(k in low for k in (" sga", " stadium giveaway")):
        return "Stadium Giveaway (SGA)"
    if any(k in low for k in (" onit", " bowman u ", " bowman university", " collegiate", " university", " ncaa", " juco", " college", " champions deck")):
        return "College"
    if any(k in low for k in (" pro debut", " minor league", " heritage minor", " milb")):
        return "Minor League"
    if any(k in low for k in (" npb", " japan", " bbm ", " calbee ")):
        return "Japanese League"
    if any(k in low for k in (" factory set", " box set", " boxed set", " complete set", " super box")):
        return "Box Sets"
    if any(k in low for k in (" team set", " team issue")):
        return "Team Issues"
    if any(k in low for k in (" promo", " national convention", " vip ", " preview", " fanatics fest")):
        return "Promo"
    if any(k in low for k in (" sticker", " album", " decal", " stamp", " coin", " oddball")):
        return "Oddball"
    if any(k in low for k in (" jersey fusion", " super break", " keepsake", " repack", " pieces of the past", " historic autographs", " president's choice")):
        return "Repack / Memorabilia"

    if ex_raw and ex_raw.lower() not in ("main set", "unknown", "none", ""):
        return ex_raw
    return "Major Releases"


def _infer_sport_year_mfg(folder_or_title: str, url: str = "") -> tuple[str, str, str]:
    combined = f"{folder_or_title} {url}".replace("_", " ")
    yr_m = re.search(r"\b((?:19|20)\d{2}(?:-\d{2})?)\b", combined)
    yr = yr_m.group(1) if yr_m else str(datetime.now().year)

    low = combined.lower()
    sport = "Baseball"
    for sp_k in TCDB_SPORT_CODES.keys():
        if sp_k.lower() in low:
            sport = sp_k
            break
    if "/football" in low or "nfl" in low or "resurgence" in low:
        sport = "Football"
    elif "/basketball" in low or "nba" in low or "wnba" in low:
        sport = "Basketball"
    elif "/hockey" in low or "nhl" in low or "o-pee-chee" in low or "parkhurst" in low:
        sport = "Hockey"
    elif "/racing" in low or "formula 1" in low or "f1" in low or "nascar" in low or "eccellenza" in low or "lights out" in low:
        sport = "Racing"
    elif "/soccer" in low or "mls" in low or "uefa" in low or "fifa" in low or "merlin" in low:
        sport = "Soccer"

    mfg = _infer_manufacturer(folder_or_title, url)
    return sport, yr, mfg


def load_tracked_sets_meta(prioritize: bool = True) -> dict[str, dict]:
    ensure_directories()
    raw_data = {}
    if TRACKING_FILE.exists():
        try:
            with open(TRACKING_FILE, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                raw_data = loaded
            elif isinstance(loaded, list):
                for item in loaded:
                    if isinstance(item, dict) and item.get("TCDB_URL"):
                        u = str(item["TCDB_URL"]).strip()
                        raw_data[u] = {
                            "folder_name": str(item.get("Folder_Name") or item.get("folder_name") or "").strip(),
                            "download_level": str(item.get("Download_Level") or item.get("download_level") or "Standard"),
                            "sport": str(item.get("Sport") or item.get("sport") or "Baseball"),
                            "year": str(item.get("Year") or item.get("year") or ""),
                            "manufacturer": str(item.get("Manufacturer") or item.get("manufacturer") or "Topps"),
                            "last_scraped": str(item.get("Last_Scraped") or item.get("last_scraped") or ""),
                        }
        except Exception:
            raw_data = {}

    normalized: dict[str, dict] = {}
    for url_k, val in raw_data.items():
        u = str(url_k).strip()
        if not u:
            continue
        if isinstance(val, str):
            fn = val.strip().replace(" ", "_")
            sp, yr, mfg = _infer_sport_year_mfg(fn, u)
            normalized[u] = {
                "folder_name": fn,
                "sport": sp,
                "year": yr,
                "manufacturer": mfg,
                "checklist_source": "Auto",
                "checklist_set_name": canonicalize_checklist_set_title(fn),
                "last_scraped": "",
                "last_upgraded": "",
            }
        elif isinstance(val, dict):
            fn = str(val.get("folder_name") or val.get("Folder_Name") or "Tracked_Set").strip().replace(" ", "_")
            sp_def, yr_def, mfg_def = _infer_sport_year_mfg(fn, u)
            normalized[u] = {
                "folder_name": fn,
                "sport": str(val.get("sport") or sp_def).strip(),
                "year": str(val.get("year") or yr_def).strip(),
                "manufacturer": str(val.get("manufacturer") or mfg_def).strip(),
                "checklist_source": str(val.get("checklist_source") or "Auto").strip(),
                "checklist_set_name": str(val.get("checklist_set_name") or canonicalize_checklist_set_title(fn)).strip(),
                "last_scraped": str(val.get("last_scraped") or "").strip(),
                "last_upgraded": str(val.get("last_upgraded") or "").strip(),
            }

    if not prioritize:
        return normalized

    def _prio_key(item_kv: tuple[str, dict]) -> tuple[int, str, str]:
        _, m = item_kv
        ls = str(m.get("last_scraped") or "").strip()
        never_flag = 0 if (not ls or ls.upper() == "NEVER") else 1
        return (never_flag, ls, m.get("folder_name", ""))

    return dict(sorted(normalized.items(), key=_prio_key))


def load_tracked_sets() -> dict[str, str]:
    meta = load_tracked_sets_meta(prioritize=True)
    return {u: m["folder_name"] for u, m in meta.items()}


def save_all_tracked_sets(tracked_dict: dict[str, dict]) -> dict[str, dict]:
    ensure_directories()
    existing = load_tracked_sets_meta(prioritize=False)
    merged = {}
    for u, m in tracked_dict.items():
        u_clean = str(u).strip()
        if not u_clean:
            continue
        prev = existing.get(u_clean, {})
        if isinstance(m, str):
            fn = m.strip().replace(" ", "_")
            sp, yr, mfg = _infer_sport_year_mfg(fn, u_clean)
            merged[u_clean] = {
                "folder_name": fn,
                "sport": prev.get("sport", sp),
                "year": prev.get("year", yr),
                "manufacturer": prev.get("manufacturer", mfg),
                "checklist_source": prev.get("checklist_source", "Auto"),
                "checklist_set_name": canonicalize_checklist_set_title(fn),
                "last_scraped": prev.get("last_scraped", ""),
                "last_upgraded": prev.get("last_upgraded", ""),
            }
        else:
            fn = str(m.get("folder_name") or prev.get("folder_name") or "Set").strip().replace(" ", "_")
            sp, yr, mfg = _infer_sport_year_mfg(fn, u_clean)
            merged[u_clean] = {
                "folder_name": fn,
                "sport": str(m.get("sport") or prev.get("sport") or sp).strip(),
                "year": str(m.get("year") or prev.get("year") or yr).strip(),
                "manufacturer": str(m.get("manufacturer") or prev.get("manufacturer") or mfg).strip(),
                "checklist_source": str(m.get("checklist_source") or prev.get("checklist_source") or "Auto").strip(),
                "checklist_set_name": str(m.get("checklist_set_name") or canonicalize_checklist_set_title(fn)).strip(),
                "last_scraped": str(m.get("last_scraped") if "last_scraped" in m else prev.get("last_scraped", "")).strip(),
                "last_upgraded": str(m.get("last_upgraded") if "last_upgraded" in m else prev.get("last_upgraded", "")).strip(),
            }
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    return merged


def load_set_cart() -> list[dict]:
    ensure_directories()
    if not SET_CART_FILE.exists():
        return []
    try:
        with open(SET_CART_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_set_cart(cart_items: list[dict]) -> list[dict]:
    ensure_directories()
    cleaned = []
    seen_urls = set()
    for item in cart_items or []:
        if not isinstance(item, dict):
            continue
        u = str(item.get("TCDB_URL") or "").strip()
        if not u or u in seen_urls:
            continue
        seen_urls.add(u)
        fn = str(item.get("Folder_Name") or item.get("Set_Name") or "Tracked_Set").strip().replace(" ", "_")
        cleaned.append({
            "Set_Name": str(item.get("Set_Name") or fn.replace("_", " ")).strip(),
            "Folder_Name": fn,
            "Sport": str(item.get("Sport") or "Baseball").strip(),
            "Year": str(item.get("Year") or "").strip(),
            "Manufacturer": str(item.get("Manufacturer") or "Topps").strip(),
            "TCDB_URL": u,
        })
    with open(SET_CART_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)
    return cleaned


def add_sets_to_cart(new_items: list[dict]) -> list[dict]:
    return save_set_cart(load_set_cart() + (new_items or []))


def clear_set_cart():
    save_set_cart([])


def commit_set_cart_to_tracked(auto_search_breakninja: bool = False) -> dict:
    cart = load_set_cart()
    if not cart:
        return {"committed_count": 0}
    trk = load_tracked_sets_meta(prioritize=False)
    added = 0
    for item in cart:
        u = str(item.get("TCDB_URL") or "").strip()
        fn = str(item.get("Folder_Name") or "").strip().replace(" ", "_")
        if not u or not fn:
            continue
        trk[u] = {
            "folder_name": fn,
            "sport": str(item.get("Sport") or "Baseball").strip(),
            "year": str(item.get("Year") or "").strip(),
            "manufacturer": str(item.get("Manufacturer") or "Topps").strip(),
            "checklist_source": "Auto",
            "checklist_set_name": canonicalize_checklist_set_title(fn),
            "last_scraped": trk.get(u, {}).get("last_scraped", ""),
            "last_upgraded": trk.get(u, {}).get("last_upgraded", ""),
        }
        added += 1
    save_all_tracked_sets(trk)
    clear_set_cart()
    return {"committed_count": added}


# ==============================================================================
# 2. TCDB MASTER SET DIRECTORY LOADER, FILTER & CRAWLER
# ==============================================================================
def _year_to_era_bucket(year_str: str, reference_year: Optional[int] = None) -> str:
    """
    Dynamically assigns a set year to an auto-updating Era bucket based on the current
    calendar/sports year:
      - Individual tabs for upcoming + 3 most recent calendar years (e.g. '2026', '2025', '2024')
      - Current-decade remainder (e.g. '2020-2023')
      - Prior decades ('2010-2019', '2000-2009', '1990-1999', '1980-1989')
      - Everything older than 1980 combined cleanly into 'Pre-1980'.
    """
    ref_yr = int(reference_year or datetime.now().year)
    m = re.search(r"(18\d{2}|19\d{2}|20\d{2})", str(year_str or ""))
    if not m:
        dec_s = (ref_yr // 10) * 10
        dec_e = ref_yr - 3
        return f"{dec_s}-{dec_e}" if dec_e > dec_s else str(dec_s)
    y = int(m.group(1))
    if y >= ref_yr - 2:
        return str(y)
    cur_dec_start = (ref_yr // 10) * 10
    if y >= cur_dec_start:
        cur_dec_end = ref_yr - 3
        return f"{cur_dec_start}-{cur_dec_end}" if cur_dec_end > cur_dec_start else str(cur_dec_start)
    if y >= 1980:
        dec = (y // 10) * 10
        return f"{dec}-{dec + 9}"
    return "Pre-1980"


def _era_bucket_sort_key(era_label: str) -> int:
    s = str(era_label or "").strip()
    if s.lower().startswith("pre-") or "vintage" in s.lower():
        return 0
    nums = [int(n) for n in re.findall(r"\d{4}", s)]
    return max(nums) if nums else 1


def _format_image_pct(raw_val) -> str:
    """Formats a raw percentage into '0%', '0.4%' (for 0 < v < 1), or '84%'..'100%'."""
    s = str(raw_val or "").strip()
    if not s:
        return ""
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return ""
    v = max(0.0, min(100.0, float(m.group(1))))
    if v == 0.0:
        return "0%"
    if v < 1.0:
        return f"{v:.1f}%"
    return f"{int(round(v))}%"


def _build_local_image_pct_lookup() -> dict[str, str]:
    """Builds `{canonical_set_key: 'XX%'}` from cached `rate_learner.set_stats` for instant 0-HTTP backfill."""
    out: dict[str, str] = {}
    try:
        summary = get_rate_learner().get_dashboard_summary()
        for ss in summary.get("setStats") or []:
            tot = int(ss.get("total_cards", 0) or 0)
            im = int(ss.get("imaged_cards_on_tcdb", 0) or 0)
            if tot > 0 and im >= 0:
                pct_s = f"{int(round(100.0 * min(tot, im) / float(tot)))}%"
                out[canonical_set_key(ss.get("set_name") or ss.get("set_key") or "")] = pct_s
    except Exception:
        pass
    return out


def _normalize_and_deduplicate_directory_df(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Applies the uniform naming policy, accurate Manufacturer & Category classification,
    local `Image_Pct` backfill, and SID/canonical-name deduplication to `TCDB_Set_Directory.csv`.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=MASTER_DIRECTORY_COLUMNS), 0

    before_cnt = len(df)
    work = df.copy()
    for c in MASTER_DIRECTORY_COLUMNS:
        if c not in work.columns:
            work[c] = ""

    local_pct_map = _build_local_image_pct_lookup()
    cleaned_rows = []
    seen_sids: set[str] = set()
    seen_canon_keys: set[tuple[str, str, str]] = set()

    work["_has_img_pct"] = work["Image_Pct"].astype(str).str.strip().apply(lambda x: 1 if x else 0)
    work["_url_len"] = work["TCDB_URL"].astype(str).str.len()
    work = work.sort_values(by=["_has_img_pct", "_url_len"], ascending=[False, False])

    for _, r in work.iterrows():
        u = str(r.get("TCDB_URL") or "").strip()
        sid_s = str(r.get("SID") or "").strip() or extract_tcdb_sid(u)
        sp_s = str(r.get("Sport") or "Baseball").strip() or "Baseball"
        yr_s = str(r.get("Year") or "").strip()
        raw_name = str(r.get("Set_Name") or r.get("Folder_Name") or "").strip()
        if not raw_name:
            continue

        canon_name = canonicalize_checklist_set_title(raw_name)
        if yr_s and not re.match(r"^(?:19|20)\d{2}", canon_name):
            canon_name = f"{yr_s} {canon_name}".strip()
        if not yr_s:
            m_yr = re.search(r"\b((?:19|20)\d{2}(?:-\d{2})?)\b", canon_name)
            yr_s = m_yr.group(1) if m_yr else str(datetime.now().year)

        canon_folder = canonicalize_set_folder_name(canon_name, sport=sp_s, year=yr_s)
        c_set_key = canonical_set_key(canon_name)
        canon_key = (yr_s, sp_s.lower(), c_set_key)

        if sid_s and sid_s in seen_sids:
            continue
        if canon_key in seen_canon_keys:
            continue

        if sid_s:
            seen_sids.add(sid_s)
        seen_canon_keys.add(canon_key)

        cat_fixed = _infer_set_category(canon_name, sport=sp_s, existing_cat=str(r.get("Category") or ""))
        mfg_fixed = _infer_manufacturer(canon_name, url=u, existing_mfg=str(r.get("Manufacturer") or ""), category=cat_fixed)
        img_pct = _format_image_pct(r.get("Image_Pct")) or local_pct_map.get(c_set_key, "") or local_pct_map.get(canonical_set_key(canon_folder), "")

        cleaned_rows.append({
            "SID": sid_s,
            "Year": yr_s,
            "Era": _year_to_era_bucket(yr_s),
            "Sport": sp_s,
            "Set_Name": canon_name,
            "Manufacturer": mfg_fixed,
            "Category": cat_fixed,
            "Image_Pct": img_pct,
            "Folder_Name": canon_folder,
            "TCDB_URL": u,
            "Last_Crawled": str(r.get("Last_Crawled") or datetime.now().strftime("%Y-%m-%d")).strip(),
        })

    out_df = pd.DataFrame(cleaned_rows, columns=MASTER_DIRECTORY_COLUMNS)
    if not out_df.empty:
        out_df = out_df.sort_values(by=["Year", "Sport", "Set_Name"], ascending=[False, True, True]).reset_index(drop=True)
    removed = max(0, before_cnt - len(out_df))
    return out_df, removed


def load_tcdb_master_directory() -> pd.DataFrame:
    ensure_directories()
    if not MASTER_DIRECTORY_FILE.exists():
        trk = load_tracked_sets_meta(prioritize=False)
        rows = []
        for u, m in trk.items():
            sid_s = extract_tcdb_sid(u)
            yr_s = str(m.get("year") or "2026")
            sp_s = m.get("sport", "Baseball")
            s_name = canonicalize_checklist_set_title(m.get("folder_name", "").replace("_", " "))
            rows.append({
                "SID": sid_s,
                "Year": yr_s,
                "Era": _year_to_era_bucket(yr_s),
                "Sport": sp_s,
                "Set_Name": s_name,
                "Manufacturer": m.get("manufacturer", "Topps"),
                "Category": "Main Set",
                "Image_Pct": "100%",
                "Folder_Name": canonicalize_set_folder_name(s_name, sport=sp_s, year=yr_s),
                "TCDB_URL": u,
                "Last_Crawled": datetime.now().strftime("%Y-%m-%d"),
            })
        df, _ = _normalize_and_deduplicate_directory_df(pd.DataFrame(rows, columns=MASTER_DIRECTORY_COLUMNS))
        df.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")
        return df
    try:
        raw_df = pd.read_csv(MASTER_DIRECTORY_FILE, dtype=str, keep_default_na=False)
        clean_df, removed_cnt = _normalize_and_deduplicate_directory_df(raw_df)
        if removed_cnt > 0:
            clean_df.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")
        return clean_df[MASTER_DIRECTORY_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=MASTER_DIRECTORY_COLUMNS)


def deduplicate_tracked_sets_and_directory() -> dict:
    """
    Cleans up `tracked_sets.json` and `tcdb_master_set_directory.csv`:
      1. Enforces the uniform naming policy ('Allen Ginter' / 'Allen and Ginter' -> 'Allen & Ginter').
      2. Deduplicates tracked sets sharing the same TCDB SID OR canonical (Sport, Set_Name),
         keeping the highest-priority entry (most recently scraped, highest Download_Level, clean URL).
      3. Deduplicates and normalizes `tcdb_master_set_directory.csv` in the same pass.
    """
    ensure_directories()
    raw_meta = load_tracked_sets_meta(prioritize=False)
    before_tracked = len(raw_meta)

    level_rank = {"Full": 3, "Extended": 2, "Standard": 1}

    def _score_entry(url: str, m: dict) -> tuple:
        ls = str(m.get("last_scraped") or "").strip()
        has_scraped = 1 if (ls and ls.upper() != "NEVER") else 0
        lvl_r = level_rank.get(normalize_download_level(m.get("download_level"), ""), 1)
        has_amp_url = 1 if "allen-&-ginter" in url.lower() else 0
        return (has_scraped, ls, lvl_r, has_amp_url, len(url))

    by_sid: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    no_sid_items: list[tuple[str, dict]] = []
    for u, m in raw_meta.items():
        sid_s = extract_tcdb_sid(u)
        if sid_s:
            by_sid[sid_s].append((u, m))
        else:
            no_sid_items.append((u, m))

    winners_phase1: list[tuple[str, dict]] = []
    removed_items: list[str] = []

    for sid_s, group in by_sid.items():
        group.sort(key=lambda kv: _score_entry(kv[0], kv[1]), reverse=True)
        winners_phase1.append(group[0])
        for dup_u, dup_m in group[1:]:
            removed_items.append(f"{dup_m.get('folder_name', dup_u)} (duplicate SID {sid_s})")

    winners_phase1.extend(no_sid_items)

    by_canon: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
    for u, m in winners_phase1:
        sp = str(m.get("sport") or "Baseball").strip()
        raw_fn = str(m.get("folder_name") or "").strip()
        canon_title = canonicalize_checklist_set_title(raw_fn)
        canon_key = (sp.lower(), canonical_set_key(canon_title))
        by_canon[canon_key].append((u, m))

    final_tracked: dict[str, dict] = {}
    renamed_count = 0

    for _, grp in by_canon.items():
        grp.sort(key=lambda kv: _score_entry(kv[0], kv[1]), reverse=True)
        win_u, win_m = grp[0]
        for dup_u, dup_m in grp[1:]:
            removed_items.append(f"{dup_m.get('folder_name', dup_u)} (duplicate set name)")

        sp = str(win_m.get("sport") or "Baseball").strip() or "Baseball"
        yr = str(win_m.get("year") or "").strip()
        old_fn = str(win_m.get("folder_name") or "").strip()
        new_fn = canonicalize_set_folder_name(old_fn, sport=sp, year=yr)
        new_chk_title = canonicalize_checklist_set_title(new_fn)
        if new_fn != old_fn:
            renamed_count += 1

        best_scraped = max([str(x[1].get("last_scraped") or "") for x in grp])
        best_upgraded = max([str(x[1].get("last_upgraded") or "") for x in grp])

        final_tracked[win_u] = {
            "folder_name": new_fn,
            "sport": sp,
            "year": yr or _infer_sport_year_mfg(new_fn, win_u)[1],
            "manufacturer": str(win_m.get("manufacturer") or _infer_sport_year_mfg(new_fn, win_u)[2]).strip(),
            "checklist_source": str(win_m.get("checklist_source") or "Auto").strip(),
            "checklist_set_name": new_chk_title,
            "last_scraped": best_scraped,
            "last_upgraded": best_upgraded,
        }

    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(final_tracked, f, indent=2)

    dir_before, dir_after, dir_removed = 0, 0, 0
    if MASTER_DIRECTORY_FILE.exists():
        try:
            raw_dir = pd.read_csv(MASTER_DIRECTORY_FILE, dtype=str, keep_default_na=False)
            dir_before = len(raw_dir)
            clean_dir, dir_removed = _normalize_and_deduplicate_directory_df(raw_dir)
            clean_dir.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")
            dir_after = len(clean_dir)
        except Exception:
            pass

    removed_tracked = max(0, before_tracked - len(final_tracked))
    if removed_items:
        for rm_i, rm_desc in enumerate(removed_items[:40], 1):
            log_msg(f"  [Dedup {rm_i}/{len(removed_items)}] Removed duplicate: {rm_desc}")
    log_msg(
        f"🧹 Tracked Sets & Directory Cleanup Complete: Tracked Sets {before_tracked} -> {len(final_tracked)} "
        f"({removed_tracked} duplicates removed, {renamed_count} standardized to uniform naming) | "
        f"Directory {dir_before:,} -> {dir_after:,} ({dir_removed:,} duplicates removed)."
    )
    return {
        "before_tracked": before_tracked,
        "after_tracked": len(final_tracked),
        "removed_tracked": removed_tracked,
        "renamed_tracked": renamed_count,
        "directory_before": dir_before,
        "directory_after": dir_after,
        "removed_directory": dir_removed,
        "removed_items": removed_items[:50],
    }


def get_dynamic_browser_tabs(dir_df: pd.DataFrame) -> list[dict]:
    if dir_df is None or dir_df.empty:
        return []
    ref_yr = datetime.now().year
    eras_series = dir_df["Year"].apply(lambda y: _year_to_era_bucket(y, reference_year=ref_yr))
    counts = eras_series.value_counts().to_dict()
    sorted_eras = sorted(counts.keys(), key=_era_bucket_sort_key, reverse=True)
    return [
        {"key": f"era_{era}", "label": f"{era} ({int(counts[era]):,})", "type": "era", "value": era}
        for era in sorted_eras
        if int(counts[era]) > 0
    ]


def filter_directory_by_tab_spec(dir_df: pd.DataFrame, tab_spec: dict) -> pd.DataFrame:
    if dir_df is None or dir_df.empty:
        return pd.DataFrame(columns=MASTER_DIRECTORY_COLUMNS)
    if tab_spec.get("type") == "era":
        return dir_df[dir_df["Era"] == tab_spec.get("value")].copy()
    return dir_df.copy()


def _extract_image_pct_from_soup_or_node(el) -> str:
    """Extracts a TCDB set image coverage percentage ('0%'..'100%') from a ViewAll row or ViewSet page."""
    if el is None:
        return ""
    try:
        # 1. Bootstrap progress-bar attributes (TCDB uses aria-valuenow or style="width: 78%")
        for pb in el.find_all(attrs={"role": "progressbar"}) + el.find_all(class_=re.compile(r"progress-bar", re.IGNORECASE)):
            aria_v = pb.get("aria-valuenow")
            if aria_v is not None and str(aria_v).strip() != "":
                return _format_image_pct(aria_v)
            st_attr = str(pb.get("style") or "")
            m_w = re.search(r"width\s*:\s*(\d+(?:\.\d+)?)\s*%", st_attr, re.IGNORECASE)
            if m_w:
                return _format_image_pct(m_w.group(1))
            pb_txt = trim_clean(pb.get_text(" ", strip=True))
            m_pt = re.search(r"(\d+(?:\.\d+)?)\s*%", pb_txt)
            if m_pt:
                return _format_image_pct(m_pt.group(1))

        # 2. Textual patterns on ViewSet.cfm ('Images: 78.4%', '78% of cards have images', '450 / 600 images')
        txt = trim_clean(el.get_text(" ", strip=True))
        for pat in (
            r"(?:images?|scans?|photos?)\s*(?:uploaded|available|coverage)?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*%",
            r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s+cards\s+have\s+images|imaged|images|complete)",
            r"(\d+(?:\.\d+)?)\s*%\s*$",
        ):
            m = re.search(pat, txt, re.IGNORECASE)
            if m:
                return _format_image_pct(m.group(1))

        m_frac = re.search(r"([\d,]+)\s*(?:of|/)\s*([\d,]+)\s*(?:cards?\s+have\s+)?images?", txt, re.IGNORECASE)
        if m_frac:
            n1 = int(m_frac.group(1).replace(",", ""))
            n2 = int(m_frac.group(2).replace(",", ""))
            if n2 > 0 and n1 <= n2:
                return _format_image_pct((100.0 * n1) / float(n2))
    except Exception:
        pass
    return ""


def _fetch_live_set_image_pct(req_session, viewset_url: str) -> str:
    """Fetches a set's TCDB `ViewSet.cfm` page and extracts its live Image_Pct ('0%'..'100%')."""
    if not viewset_url or BeautifulSoup is None:
        return ""
    resp = safe_get(req_session, viewset_url, silent_404=True, max_403_retries=1)
    if not resp:
        return ""
    html = decode_html_response(resp)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return _extract_image_pct_from_soup_or_node(soup)


_DIR_IMG_PCT_CACHE = {"mtime": -1.0, "by_sid": {}, "by_key": {}}


def _get_directory_image_pct(set_url: str = "", chk_title: str = "") -> Optional[float]:
    """Fast mtime-cached lookup of a set's `Image_Pct` (0.0..100.0) from `TCDB_Set_Directory.csv`."""
    if not MASTER_DIRECTORY_FILE.exists():
        return None
    try:
        mt = MASTER_DIRECTORY_FILE.stat().st_mtime
        if _DIR_IMG_PCT_CACHE["mtime"] != mt:
            by_sid, by_key = {}, {}
            df_d = pd.read_csv(MASTER_DIRECTORY_FILE, dtype=str, keep_default_na=False)
            for _, r in df_d.iterrows():
                raw_p = str(r.get("Image_Pct") or "").strip()
                if not raw_p:
                    continue
                m = re.search(r"(\d+(?:\.\d+)?)", raw_p)
                if not m:
                    continue
                val = max(0.0, min(100.0, float(m.group(1))))
                sid_s = str(r.get("SID") or "").strip() or extract_tcdb_sid(str(r.get("TCDB_URL") or ""))
                if sid_s:
                    by_sid[sid_s] = val
                s_n = str(r.get("Set_Name") or "").strip()
                if s_n:
                    by_key[canonical_set_key(s_n)] = val
            _DIR_IMG_PCT_CACHE.update({"mtime": mt, "by_sid": by_sid, "by_key": by_key})

        sid_q = extract_tcdb_sid(set_url)
        if sid_q and sid_q in _DIR_IMG_PCT_CACHE["by_sid"]:
            return _DIR_IMG_PCT_CACHE["by_sid"][sid_q]
        if chk_title:
            ck = canonical_set_key(chk_title)
            if ck in _DIR_IMG_PCT_CACHE["by_key"]:
                return _DIR_IMG_PCT_CACHE["by_key"][ck]
    except Exception:
        pass
    return None


def _parse_tcdb_viewall_page(html: str, sport: str, year_str: str) -> list[dict]:
    """
    Single-Pass HTML Parser for `ViewAll.cfm/sp/{Sport}/year/{Year}`:
      - Reads TCDB's exact official `<h3 class="site">` Category heading above every `<ul>`
        ('Major Releases', 'Box Sets', 'College', 'College Summer League', 'Japanese League',
         'Minor League', 'Oddball', 'On-Demand', 'Promo', 'Stadium Giveaway (SGA)', 'Team Issues').
      - Extracts exact `Image_Pct` directly from `ViewAll.cfm` with ZERO extra HTTP calls:
          * `<a href="/ViewSet.cfm/..." title="90.9% of images added">` -> `'91%'` (or `'0%'` for `0.0%`)
          * No `title` + sibling `<a href="/Gallery.cfm/...">` icon in the same `<li>` -> `'100%'`!
    """
    if not html or BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    today_s = datetime.now().strftime("%Y-%m-%d")
    records: list[dict] = []
    seen_sids: set[str] = set()

    # Walk `<h3 class="site">` -> following `<ul>` pairs first for 100% accurate section binding
    h3_sections = soup.find_all("h3", class_="site")
    section_pairs: list[tuple[str, object]] = []
    if h3_sections:
        for h3 in h3_sections:
            sec_title = trim_clean(h3.get_text(" ", strip=True))
            ul_el = h3.find_next_sibling("ul")
            if ul_el is not None:
                section_pairs.append((sec_title, ul_el))
    if not section_pairs:
        section_pairs.append(("", soup))

    for sec_heading, container in section_pairs:
        for a in container.find_all("a", href=re.compile(r"/ViewSet\.cfm/sid/\d+", re.IGNORECASE)):
            href = str(a.get("href") or "").strip()
            sid_m = re.search(r"/sid/(\d+)", href)
            if not sid_m:
                continue
            sid_str = sid_m.group(1)
            if sid_str in seen_sids:
                continue
            set_title = trim_clean(a.get_text(" ", strip=True))
            if not set_title or len(set_title) < 3:
                continue
            seen_sids.add(sid_str)

            full_url = urljoin(BASE_URL, href)
            canon_title = canonicalize_checklist_set_title(
                f"{year_str} {set_title}" if not set_title.startswith(str(year_str)) else set_title
            )

            # Extract exact Image_Pct directly from ViewAll.cfm anchor title or sibling Gallery icon!
            img_pct = ""
            title_attr = trim_clean(a.get("title") or "")
            m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*images\s*added", title_attr, re.IGNORECASE)
            if m_pct:
                img_pct = _format_image_pct(m_pct.group(1))
            else:
                li_parent = a.find_parent("li") or a.parent
                if li_parent is not None:
                    has_gallery = bool(
                        li_parent.find("a", href=re.compile(r"/Gallery\.cfm/sid/", re.IGNORECASE))
                        or li_parent.find("i", class_=re.compile(r"fa-images", re.IGNORECASE))
                    )
                    if has_gallery:
                        img_pct = "100%"

            cat_inf = _infer_set_category(canon_title, sport=sport, section_heading=sec_heading)
            mfg_inf = _infer_manufacturer(canon_title, url=full_url, category=cat_inf)
            fn = canonicalize_set_folder_name(canon_title, sport=sport, year=str(year_str))

            records.append({
                "SID": sid_str,
                "Year": str(year_str),
                "Era": _year_to_era_bucket(str(year_str)),
                "Sport": sport,
                "Set_Name": canon_title,
                "Manufacturer": mfg_inf,
                "Category": cat_inf,
                "Image_Pct": img_pct,
                "Folder_Name": fn,
                "TCDB_URL": full_url,
                "Last_Crawled": today_s,
            })

    return records


def repair_tcdb_set_directory(fetch_missing_image_pct: bool = False, max_live_fetches: int = 120) -> dict:
    """
    Repairs `TCDB_Set_Directory.csv` with full verbose step-by-step logging:
      1. Fixes misclassified Manufacturers & Categories, enforces uniform naming & Pre-1980 Era.
      2. When `fetch_missing_image_pct=True`, uses the ultra-fast `ViewAll.cfm` single-page parser
         (1 request per Sport+Year instead of 1 request per Set!) to backfill exact TCDB Categories
         and exact `Image_Pct` (`0%`..`100%`) across hundreds/thousands of sets in parallel!
    """
    ensure_directories()
    t0 = time.time()
    log_msg(f"🔧 Loading TCDB Set Directory from {MASTER_DIRECTORY_FILE}...")
    raw_df = pd.read_csv(MASTER_DIRECTORY_FILE, dtype=str, keep_default_na=False) if MASTER_DIRECTORY_FILE.exists() else load_tcdb_master_directory()
    before_cnt = len(raw_df)
    log_msg(f"[1/2] Inspecting & normalizing {before_cnt:,} directory rows (Manufacturers, Categories, Uniform Names & Local Img %)...")
    clean_df, dup_rm = _normalize_and_deduplicate_directory_df(raw_df)
    clean_df.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")

    live_updated = 0
    if fetch_missing_image_pct and not clean_df.empty:
        # Group unique (Sport, Year) pairs in newest-first order — 1 ViewAll.cfm page refreshes ALL sets for that Sport+Year!
        pair_counts = (
            clean_df.groupby(["Sport", "Year"], sort=False)
            .size()
            .reset_index(name="cnt")
            .sort_values(by=["Year", "cnt"], ascending=[False, False])
        )
        pairs_to_fetch = [
            (str(r["Sport"]).strip(), str(r["Year"]).strip())
            for _, r in pair_counts.iterrows()
            if str(r["Sport"]).strip() and re.fullmatch(r"\d{4}", str(r["Year"]).strip())
        ]
        if int(max_live_fetches or 0) > 0:
            pairs_to_fetch = pairs_to_fetch[: int(max_live_fetches)]

        existing_by_sid = {str(r["SID"]): r.to_dict() for _, r in clean_df.iterrows() if str(r.get("SID", "")).strip()}
        log_msg(
            f"📊 Fast ViewAll.cfm Img % & Category Backfill across {len(pairs_to_fetch)} (Sport, Year) pages "
            f"(100x faster than per-set ViewSet requests)..."
        )
        sess = connect_session(target_domain=BASE_URL, require_image_probe=False)
        try:
            tot_p = len(pairs_to_fetch)
            for p_idx, (sp, yr_s) in enumerate(pairs_to_fetch, 1):
                sp_code = TCDB_SPORT_CODES.get(sp, 1)
                va_url = f"{BASE_URL}/ViewAll.cfm/sp/{quote(sp)}/year/{yr_s}?sp={sp_code}"
                resp = safe_get(sess, va_url, silent_404=True)
                html = decode_html_response(resp)
                parsed_recs = _parse_tcdb_viewall_page(html, sport=sp, year_str=yr_s)
                for rec in parsed_recs:
                    sid_k = rec["SID"]
                    if sid_k in existing_by_sid:
                        if rec["Image_Pct"]:
                            existing_by_sid[sid_k]["Image_Pct"] = rec["Image_Pct"]
                        if rec["Category"]:
                            existing_by_sid[sid_k]["Category"] = rec["Category"]
                        if rec["Manufacturer"]:
                            existing_by_sid[sid_k]["Manufacturer"] = rec["Manufacturer"]
                        existing_by_sid[sid_k]["Last_Crawled"] = rec["Last_Crawled"]
                    else:
                        existing_by_sid[sid_k] = rec
                    live_updated += 1
                pct_100 = sum(1 for r in parsed_recs if r["Image_Pct"] == "100%")
                pct_0 = sum(1 for r in parsed_recs if r["Image_Pct"] == "0%")
                log_msg(
                    f"[{p_idx}/{tot_p}] {yr_s} {sp}: parsed {len(parsed_recs):,} sets "
                    f"(100%={pct_100}, partial={len(parsed_recs) - pct_100 - pct_0}, 0%={pct_0})"
                )
                if p_idx % 5 == 0 or p_idx == tot_p:
                    clean_df, _ = _normalize_and_deduplicate_directory_df(
                        pd.DataFrame(list(existing_by_sid.values()), columns=MASTER_DIRECTORY_COLUMNS)
                    )
                    clean_df.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")
        finally:
            cleanup_orphaned_drivers()

    mfg_top = clean_df["Manufacturer"].value_counts().head(6).to_dict() if not clean_df.empty else {}
    cat_top = clean_df["Category"].value_counts().head(6).to_dict() if not clean_df.empty else {}
    log_msg(f"  + Top Manufacturers: {', '.join(f'{k}={v:,}' for k, v in mfg_top.items())}")
    log_msg(f"  + Top Categories: {', '.join(f'{k}={v:,}' for k, v in cat_top.items())}")

    with_pct = int((clean_df["Image_Pct"].astype(str).str.strip() != "").sum()) if not clean_df.empty else 0
    msg = (
        f"Updated TCDB_Set_Directory.csv ({before_cnt:,} -> {len(clean_df):,} sets in {time.time() - t0:.1f}s; "
        f"{dup_rm:,} dupes removed; {with_pct:,} sets have exact Image_Pct, {live_updated:,} refreshed live)."
    )
    log_msg(f"✅ {msg}")
    return {
        "before_count": before_cnt,
        "after_count": len(clean_df),
        "duplicates_removed": dup_rm,
        "with_image_pct": with_pct,
        "live_image_pct_updated": live_updated,
        "message": msg,
    }


def crawl_tcdb_master_set_directory(
    sports: Optional[list[str]] = None,
    start_year: int = 2020,
    end_year: Optional[int] = None,
    fetch_set_image_pct: bool = True,
    max_image_pct_fetches: int = 150,
) -> pd.DataFrame:
    """
    Single-Pass TCDB Master Set Directory Crawler:
    Extracts every set's exact official `<h3 class="site">` Category, accurate Brand/Manufacturer,
    uniform Folder Name, AND exact `Image_Pct` (`0%`..`100%`) directly from each `ViewAll.cfm`
    page in a single HTTP request per `(Sport, Year)`.
    """
    ensure_directories()
    resolved_end_yr = int(end_year) if end_year else datetime.now().year
    resolved_start_yr = min(int(start_year), resolved_end_yr)
    sports_to_crawl = sports or ["Baseball", "Football", "Basketball"]
    curr_df = load_tcdb_master_directory()
    existing_by_sid = {str(r["SID"]): r.to_dict() for _, r in curr_df.iterrows() if r.get("SID")}
    local_pct_map = _build_local_image_pct_lookup()

    # Apply Sport Inception-Year Guardrails so we never crawl years before a sport had cards on TCDB
    valid_ranges_by_sport: dict[str, tuple[int, int]] = {}
    total_valid_pages = 0
    skipped_guardrail_pages = 0
    for sp in sports_to_crawl:
        min_valid_yr = int(SPORT_FIRST_CARD_YEAR.get(sp, 1880))
        eff_start = max(resolved_start_yr, min_valid_yr)
        if eff_start > resolved_start_yr:
            skipped_guardrail_pages += min(resolved_end_yr + 1, eff_start) - resolved_start_yr
        if eff_start <= resolved_end_yr:
            valid_ranges_by_sport[sp] = (eff_start, resolved_end_yr)
            total_valid_pages += resolved_end_yr - eff_start + 1

    if skipped_guardrail_pages > 0:
        log_msg(
            f"🛡️ Sport Inception-Year Guardrail active: skipped {skipped_guardrail_pages:,} impossible pre-inception "
            f"(Sport, Year) page(s) — crawling {total_valid_pages:,} valid page(s)."
        )

    if total_valid_pages <= 0:
        log_msg("⚠️ No valid (Sport, Year) pages fall within TCDB sport inception guardrails.")
        return curr_df

    sess = connect_session(target_domain=BASE_URL, require_image_probe=False)
    total_steps = max(1, total_valid_pages)
    step_i = 0

    try:
        for sp in sports_to_crawl:
            if sp not in valid_ranges_by_sport:
                continue
            eff_start_sp, eff_end_sp = valid_ranges_by_sport[sp]
            sp_code = TCDB_SPORT_CODES.get(sp, 1)
            for yr in range(eff_end_sp, eff_start_sp - 1, -1):
                step_i += 1
                url = f"{BASE_URL}/ViewAll.cfm/sp/{quote(sp)}/year/{yr}?sp={sp_code}"
                log_msg(f"[{step_i}/{total_steps}] Crawling TCDB {yr} {sp} directory -> {url}")
                resp = safe_get(sess, url)
                html = decode_html_response(resp)
                if not html or BeautifulSoup is None:
                    continue
                parsed_recs = _parse_tcdb_viewall_page(html, sport=sp, year_str=str(yr))
                for rec in parsed_recs:
                    sid_str = rec["SID"]
                    if not rec["Image_Pct"]:
                        prev_pct = str((existing_by_sid.get(sid_str) or {}).get("Image_Pct") or "").strip()
                        rec["Image_Pct"] = prev_pct or local_pct_map.get(canonical_set_key(rec["Set_Name"]), "")
                    existing_by_sid[sid_str] = rec

                pct_100 = sum(1 for r in parsed_recs if r["Image_Pct"] == "100%")
                pct_0 = sum(1 for r in parsed_recs if r["Image_Pct"] == "0%")
                log_msg(
                    f"  + {yr} {sp}: {len(parsed_recs):,} sets parsed directly from ViewAll.cfm "
                    f"(100%={pct_100}, partial={len(parsed_recs) - pct_100 - pct_0}, 0%={pct_0})"
                )
                if step_i % 5 == 0 and existing_by_sid:
                    chk_df, _ = _normalize_and_deduplicate_directory_df(
                        pd.DataFrame(list(existing_by_sid.values()), columns=MASTER_DIRECTORY_COLUMNS)
                    )
                    chk_df.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")
    finally:
        cleanup_orphaned_drivers()

    raw_out_df = pd.DataFrame(list(existing_by_sid.values()), columns=MASTER_DIRECTORY_COLUMNS)
    out_df, dup_rm = _normalize_and_deduplicate_directory_df(raw_out_df)
    out_df.to_csv(MASTER_DIRECTORY_FILE, index=False, encoding="utf-8-sig")
    log_msg(f"✅ Saved {len(out_df):,} unique uniform-named sets to {MASTER_DIRECTORY_FILE} ({dup_rm} duplicate(s) removed)")
    return out_df


# ==============================================================================
# 3. UNIFIED TCDB CHECKLIST + CID + FRONT/BACK IMAGE PARSER & CATALOGER
# ==============================================================================
_GENERIC_TCDB_NAV_LABELS = {
    "", "checklist", "overview", "gallery", "forum", "collection", "prices",
    "add cards", "packaging", "insert", "inserts", "parallel", "parallels",
    "view", "print", "buy/sell",
}

_TCDB_GLOSSARY_SUFFIX_RE = re.compile(
    r"(?:\s+|\b)(?:RC|CPC|LL|TC|FS|ASR|SP|SSP|VAR|ERR|COR|UER|HOF|AS|PRO|DP|FDP|EXCH|AU|AUTO|MEM|REL|SN\d*|\d+/\d+|1/1)+\s*$",
    re.IGNORECASE,
)


def _resolve_tcdb_set_urls(viewset_url: str) -> dict[str, str]:
    u = str(viewset_url).strip()
    m = re.search(r"/sid/(\d+)(?:/([^/?#]+))?", u, re.IGNORECASE)
    if not m:
        return {"checklist": u, "inserts": u, "errors": u, "sid": ""}
    sid = m.group(1)
    slug = m.group(2) or ""
    suffix = f"/sid/{sid}/{slug}" if slug else f"/sid/{sid}"
    return {
        "sid": sid,
        "checklist": f"{BASE_URL}/Checklist.cfm{suffix}",
        "inserts": f"{BASE_URL}/Inserts.cfm{suffix}",
        "errors": f"{BASE_URL}/Errors.cfm{suffix}",
    }


def clean_tcdb_subset_title(raw_title: str, checklist_set_name: str = "", url_slug: str = "") -> str:
    t = trim_clean(str(raw_title or "").replace("_", " "))
    if t.lower() in _GENERIC_TCDB_NAV_LABELS or re.match(r"^page\s*\d+$", t, re.IGNORECASE):
        t = ""

    if not t and url_slug:
        slug_clean = trim_clean(url_slug.replace("---", " | ").replace("-", " "))
        t = slug_clean.split("|")[-1].strip() if "|" in slug_clean else slug_clean

    if not t:
        return ""

    t = re.sub(r"\s+Checklist$", "", t, flags=re.IGNORECASE).strip()
    t = _restore_season_years_and_hyphenated_terms(t)

    if t.upper() in ("BASE", "BASE SET", "MAIN SET"):
        return "Base"

    set_full = _restore_season_years_and_hyphenated_terms(trim_clean(str(checklist_set_name or "").replace("_", " ")))
    set_base = re.sub(
        r"\b(Baseball|Football|Basketball|Hockey|Soccer|Racing|Wrestling|MMA|Golf)\b",
        "",
        set_full,
        flags=re.IGNORECASE,
    ).strip()

    if " - " in t:
        left_part, right_part = t.split(" - ", 1)
        if (
            re.match(r"^(19|20)\d{2}(?:-\d{2})?\b", left_part)
            or (set_base and norm(set_base) in norm(left_part))
            or (set_full and norm(set_full) in norm(left_part))
        ) and right_part.strip():
            t = right_part.strip()

    if set_base and len(t) > len(set_base) + 1:
        set_base_alt = set_base.replace("&", "and")
        set_full_alt = set_full.replace("&", "and")
        candidates = [
            set_full,
            set_full_alt,
            set_base,
            set_base_alt,
            set_base.replace(" & ", " "),
            re.sub(r"-", " ", set_base),
        ]
        for pref_cand in candidates:
            pref_clean = _restore_season_years_and_hyphenated_terms(trim_clean(pref_cand))
            if not pref_clean:
                continue
            pat = rf"^{re.escape(pref_clean)}\s*[-–:]?\s+"
            stripped = re.sub(pat, "", t, flags=re.IGNORECASE).strip(" -–:")
            if stripped and stripped.lower() != t.lower():
                t = stripped
                break

    t = _restore_season_years_and_hyphenated_terms(t)
    if t.upper() in ("BASE", "BASE SET", "MAIN SET"):
        return "Base"
    return "" if t.lower() in _GENERIC_TCDB_NAV_LABELS else t


def _extract_subset_title_from_checklist_soup(soup: BeautifulSoup, checklist_set_name: str = "") -> str:
    for tag_name in ("h1", "h3", "h4", "title"):
        for el in soup.find_all(tag_name):
            txt = trim_clean(el.get_text(" ", strip=True))
            if not txt:
                continue
            if "|" in txt:
                txt = txt.split("|")[0].strip()
            cleaned = clean_tcdb_subset_title(txt, checklist_set_name=checklist_set_name)
            if cleaned and norm(cleaned) != norm(checklist_set_name):
                return cleaned
    return ""


# Non-baseball profession / occupation suffixes that TCDB appends to Allen & Ginter / non-sport cards
_UNAMBIGUOUS_OCCUPATIONS = (
    r"Stand-Up\s+Comedian", r"Voice\s+Actor", r"Voice\s+Actress", r"Film\s+Director", r"Movie\s+Director",
    r"Film\s+Producer", r"Music\s+Producer", r"Record\s+Producer", r"TV\s+Personality", r"Media\s+Personality",
    r"Reality\s+TV\s+Star", r"Social\s+Media\s+(?:Star|Personality|Influencer)", r"Talk\s+Show\s+Host",
    r"Game\s+Show\s+Host", r"TV\s+Host", r"Radio\s+Host", r"Podcast\s+Host", r"Celebrity\s+Chef",
    r"Pastry\s+Chef", r"Competitive\s+Eater", r"Pro\s+Wrestler", r"MMA\s+Fighter", r"Martial\s+Artist",
    r"Lead\s+Guitarist", r"Rhythm\s+Guitarist", r"Lead\s+Vocalist", r"Singer-Songwriter", r"Hip-Hop\s+Artist",
    r"Fashion\s+Designer", r"Olympic\s+Gold\s+Medalist", r"Gold\s+Medalist", r"World\s+Champion",
    r"Hall\s+of\s+Famer", r"Tennis\s+Player", r"Poker\s+Player", r"Chess\s+(?:Player|Grandmaster)",
    r"Basketball\s+Player", r"Football\s+Player", r"Hockey\s+Player", r"Soccer\s+Player",
    r"Softball\s+Player", r"Volleyball\s+Player", r"Lacrosse\s+Player", r"Rugby\s+Player",
    r"Comedian", r"Actor", r"Actress", r"Rapper", r"Songwriter", r"Musician", r"Bassist", r"Guitarist",
    r"Drummer", r"Vocalist", r"Keyboardist", r"Pianist", r"Violinist", r"Cellist", r"Saxophonist",
    r"Trumpeter", r"Percussionist", r"Screenwriter", r"Playwright", r"Novelist", r"Author", r"Journalist",
    r"Columnist", r"Broadcaster", r"Sportscaster", r"Announcer", r"Commentator", r"Podcaster",
    r"YouTuber", r"Streamer", r"Influencer", r"Magician", r"Illusionist", r"Chef", r"Restaurateur",
    r"Sommelier", r"Bartender", r"Barista", r"Skateboarder", r"Snowboarder", r"Surfer", r"Swimmer",
    r"Gymnast", r"Sprinter", r"Boxer", r"Wrestler", r"Golfer", r"Astronaut", r"Scientist", r"Physicist",
    r"Chemist", r"Biologist", r"Botanist", r"Paleontologist", r"Archaeologist", r"Historian",
    r"Entrepreneur", r"Philanthropist", r"Activist", r"Politician", r"Senator", r"Governor",
    r"Cartoonist", r"Illustrator", r"Photographer", r"Sculptor", r"Choreographer", r"Dancer",
    r"Architect", r"Veterinarian", r"Zookeeper", r"Firefighter", r"Stuntman", r"Stuntwoman",
    r"Ventriloquist", r"Acrobat", r"Entertainer", r"Performer", r"Supermodel", r"Olympian",
    r"DJ", r"Beatboxer", r"Impersonator", r"Puppeteer", r"Composer", r"Conductor", r"Filmmaker",
)

# Secondary occupation words (like Singer, Producer, Director, Writer, Painter, Baker, Driver, Judge)
# that are ONLY stripped when Team == NO TEAM AND either (a) separated by a comma/slash with another
# occupation, OR (b) preceded by at least 2 name words (protecting Aaron Judge, Brady Singer, Mike Judge, etc.)
_NO_TEAM_SECONDARY_OCCUPATIONS = (
    r"Singer", r"Producer", r"Director", r"Writer", r"Host", r"Artist", r"Poet", r"Model",
    r"Painter", r"Driver", r"Racer", r"Jockey", r"Skater", r"Skier", r"Runner", r"Cyclist",
    r"Coach", r"Umpire", r"Referee", r"Doctor", r"Professor", r"Lawyer", r"Attorney", r"Judge",
    r"Mayor", r"President", r"Founder", r"CEO", r"Designer", r"Creator", r"Gamer", r"Bowler",
    r"Archer", r"Fencer", r"Rower", r"Sailor", r"Baker", r"Explorer", r"Inventor", r"Engineer",
    r"Critic", r"Reporter", r"Anchor", r"Analyst", r"Narrator", r"Mascot", r"Band",
)

_UNAMBIGUOUS_OCC_RE = re.compile(
    r"(?:[\s,/&\-]+)\b(?:" + "|".join(_UNAMBIGUOUS_OCCUPATIONS) + r")\b\s*$",
    re.IGNORECASE,
)
_SECONDARY_OCC_RE = re.compile(
    r"(?:[\s,/&\-]+)\b(?:" + "|".join(_NO_TEAM_SECONDARY_OCCUPATIONS) + r")\b\s*$",
    re.IGNORECASE,
)
_INLINE_ERR_NOTE_RE = re.compile(r"\s+\b(UER|ERR|COR)\s*[:\-–].*$", re.IGNORECASE)
_INLINE_GLOSSARY_TAIL_RE = re.compile(
    r"\s+\b(AU|AUTO|MEM|REL|SN\s*\d+|#/\d+|1/1)\b(.*)$"
)


def _strip_inline_tags_errors_and_occupations(
    raw_player: str,
    team_str: str = "",
) -> tuple[str, list[str], str]:
    """
    Cleans TCDB player names while extracting embedded metadata:
      - 'Cy Young UER: Should be 749 Complete Games' -> ('Cy Young', ['UER'], '')
      - 'Garrett Nickelsen AU, SN99 Bassist'         -> ('Garrett Nickelsen', ['Auto', '#/99'], '99')
      - 'David Spade Comedian, Actor'                -> ('David Spade', [], '')
      - 'Nelly Rapper'                               -> ('Nelly', [], '')
      - 'Anne Hathaway Actress'                      -> ('Anne Hathaway', [], '')
    Strictly protects real player surnames (Aaron Judge, Brady Singer, Andrew Painter, Dusty Baker, Mike Judge).
    """
    s = trim_clean(raw_player)
    if not s:
        return "", [], ""

    extracted_tags: list[str] = []
    extracted_pr = ""

    # 1. Strip UER:/ERR:/COR: error descriptions
    m_err = _INLINE_ERR_NOTE_RE.search(s)
    if m_err:
        _add_tag(extracted_tags, m_err.group(1).upper())
        cand = s[: m_err.start()].strip(" ,.-;:")
        if len(cand) >= 2:
            s = cand

    # 2. Strip mid-string case-sensitive AU / MEM / SN99 / 1/1 + trailing occupation/band notes
    m_gl = _INLINE_GLOSSARY_TAIL_RE.search(s)
    if m_gl:
        head = s[: m_gl.start()].strip(" ,.-;:")
        tail_all = f"{m_gl.group(1)} {m_gl.group(2)}"
        if len(head) >= 2:
            m_sn = re.search(r"\bSN\s*(\d+)\b|#/\s*(\d+)\b", tail_all, re.IGNORECASE)
            if m_sn:
                extracted_pr = str(int(m_sn.group(1) or m_sn.group(2)))
                _add_tag(extracted_tags, f"#/{extracted_pr}", extracted_pr)
            elif "1/1" in tail_all:
                extracted_pr = "1"
                _add_tag(extracted_tags, "1/1", "1")
            if re.search(r"\b(AU|AUTO)\b", tail_all):
                _add_tag(extracted_tags, "Auto", extracted_pr)
            if re.search(r"\b(MEM|REL)\b", tail_all):
                _add_tag(extracted_tags, "Mem", extracted_pr)
            s = head

    # 3. Iteratively strip trailing non-baseball profession/occupation descriptors
    is_no_team = not str(team_str or "").strip() or str(team_str).strip().upper() in ("NO TEAM", "UNKNOWN", "NONE", "NAN")
    stripped_unambiguous_once = False

    for _ in range(5):
        m_u = _UNAMBIGUOUS_OCC_RE.search(s)
        if m_u:
            head = s[: m_u.start()].strip(" ,/-&")
            if len(head) >= 2 and head.lower() not in ("the", "a", "an"):
                s = head
                stripped_unambiguous_once = True
                continue

        # Only consider secondary occupation words if Team == NO TEAM AND (2+ words remain OR paired with another occupation)
        if is_no_team:
            m_sec = _SECONDARY_OCC_RE.search(s)
            if m_sec:
                head = s[: m_sec.start()].strip(" ,/-&")
                head_words = [w for w in head.split() if w]
                if len(head_words) >= 2 or (stripped_unambiguous_once and len(head) >= 2):
                    s = head
                    continue
        break

    # 4. Final glossary suffix cleanup
    prev = None
    while s and s != prev:
        prev = s
        s = _TCDB_GLOSSARY_SUFFIX_RE.sub("", s).strip(" ,.-")

    return s, extracted_tags, extracted_pr


def _clean_tcdb_card_subject_title(raw_subject: str, team_str: str = "") -> str:
    s = trim_clean(raw_subject)
    if not s:
        return ""
    if "(" in s:
        before_paren = s.split("(", 1)[0].strip()
        if len(before_paren) >= 3 and not before_paren.isdigit():
            s = before_paren
    cleaned, _, _ = _strip_inline_tags_errors_and_occupations(s, team_str=team_str)
    return cleaned


TRUE_2026_TOPPS_BASE_CARDS: dict[str, tuple[str, str]] = {
    "1": ("Aaron Judge", "New York Yankees"),
    "2": ("Daulton Varsho", "Toronto Blue Jays"),
    "11": ("National League Leaders RBI", "Philadelphia Phillies/New York Mets"),
    "34": ("Kansas City Royals", "Kansas City Royals"),
    "38": ("American League Leaders HRs", "Seattle Mariners/New York Yankees/Tampa Bay Rays"),
    "47": ("Arizona Diamondbacks", "Arizona Diamondbacks"),
    "52": ("It Takes Two", "New York Mets"),
    "84": ("National League Leaders HRs", "Philadelphia Phillies/Los Angeles Dodgers/New York Mets"),
    "89": ("Houston Astros", "Houston Astros"),
    "107": ("Milwaukee Brewers", "Milwaukee Brewers"),
    "113": ("Toronto Blue Jays", "Toronto Blue Jays"),
    "117": ("National League Leaders Wins", "Milwaukee Brewers/Philadelphia Phillies/San Francisco Giants"),
    "118": ("Hopping to It", "Atlanta Braves"),
    "122": ("New-Age Athletics", "Athletics"),
    "130": ("American League Leaders Wins", "New York Yankees/Boston Red Sox"),
    "151": ("National League Leaders Avg", "Philadelphia Phillies/Chicago Cubs/Los Angeles Dodgers"),
    "197": ("Cool Crushers", "Philadelphia Phillies"),
    "198": ("Boston Red Sox", "Boston Red Sox"),
    "203": ("National League Leaders ERA", "Pittsburgh Pirates/Los Angeles Dodgers/Philadelphia Phillies"),
    "211": ("American League Leaders RBI", "Seattle Mariners/New York Yankees/Cleveland Guardians"),
    "256": ("Los Angeles Dodgers", "Los Angeles Dodgers"),
    "258": ("Texas Rangers", "Texas Rangers"),
    "262": ("Detroit Tigers", "Detroit Tigers"),
    "295": ("Philadelphia Phillies", "Philadelphia Phillies"),
    "302": ("Bronx Buddies", "New York Yankees"),
    "327": ("American League Leaders ERA", "Detroit Tigers/Houston Astros/Boston Red Sox"),
    "491": ("Minnesota Twins", "Minnesota Twins"),
    "499": ("D.C. Dudes", "Washington Nationals"),
    "553": ("All Smiles", "Cincinnati Reds"),
    "576": ("Beantown Buds", "Boston Red Sox"),
    "605": ("Dirt Dynamos", "San Diego Padres"),
    "628": ("New York Yankees", "New York Yankees"),
    "640": ("Atlanta Braves", "Atlanta Braves"),
}


def extract_tcdb_id_from_url_or_href(thumb_url: str = "", card_href: str = "") -> str:
    """Extracts the canonical numeric TCDB CID from a ViewCard href or thumbnail URL."""
    if card_href:
        m_cid = re.search(r"/cid/(\d+)", str(card_href), re.IGNORECASE)
        if m_cid:
            return m_cid.group(1)
    if thumb_url:
        m_th = re.search(r"_([a-zA-Z0-9_]+)Thumb", str(thumb_url), re.IGNORECASE)
        if m_th:
            base_id = re.sub(r"(Bk|Fr|Rep)$", "", m_th.group(1), flags=re.IGNORECASE)
            return normalize_numeric_tcdb_cid(base_id)
        m_lg = re.search(r"-(\d+)(?:Rep)?(?:Fr|Bk)\.jpe?g", str(thumb_url), re.IGNORECASE)
        if m_lg:
            return m_lg.group(1)
    return "0"


def _extract_title_from_viewcard_href(card_href: str, card_num: str = "") -> str:
    """
    Extracts the card title directly from TCDB's card-number ViewCard.cfm URL slug, e.g.:
      '/ViewCard.cfm/sid/585448/cid/33567907/2026-Topps-52-It-Takes-Two' -> 'It Takes Two'
      '/ViewCard.cfm/sid/595149/cid/37837487/2026-Topps-Blue-Rainbow-Foil-499-D.C.-Dudes' -> 'D.C. Dudes'
    """
    from urllib.parse import unquote
    raw_u = str(card_href or "").split("?")[0].split("#")[0].strip()
    if not raw_u:
        return ""
    m_slug = re.search(r"/cid/\d+/(.+)$", raw_u, re.IGNORECASE)
    if not m_slug:
        return ""
    slug = unquote(m_slug.group(1)).strip("/")
    if not slug:
        return ""

    cn_clean = re.sub(r"[^A-Za-z0-9\-]+", "-", str(card_num or "").strip().lstrip("#")).strip("-")
    title_part = ""
    if cn_clean:
        matches = list(re.finditer(rf"-{re.escape(cn_clean)}-(.+)$", slug, re.IGNORECASE))
        if matches:
            title_part = matches[-1].group(1)
    if not title_part:
        return ""

    title_str = title_part.replace("---", " - ").replace("--", " - ").replace("-", " ")
    title_str = _restore_season_years_and_hyphenated_terms(trim_clean(title_str))
    return _clean_tcdb_card_subject_title(title_str)


def transform_thumb_to_large_urls(thumb_url: str, side: str = "Fr") -> dict[str, str]:
    """Transforms a TCDB thumbnail URL into its High-Res R-Tier (`RepFr`/`RepBk`) and S-Tier (`Fr`/`Bk`) URLs."""
    full_thumb = str(thumb_url or "").strip()
    if not full_thumb:
        return {"rep": "", "std": ""}
    if not full_thumb.startswith("http"):
        full_thumb = urljoin(BASE_URL, full_thumb)
    url = re.sub(r"/Images/(Thumbs|Cards)/", "/Images/Large/", full_thumb, flags=re.IGNORECASE)
    match = re.search(r"_([a-zA-Z0-9_]+)Thumb", url, flags=re.IGNORECASE)
    if match:
        base_id = re.sub(r"(Bk|Fr|Rep)$", "", match.group(1), flags=re.IGNORECASE)
        rep_url = re.sub(
            r"_[a-zA-Z0-9_]+Thumb[a-zA-Z0-9]*\.jpe?g$",
            f"-{base_id}Rep{side}.jpg",
            url,
            flags=re.IGNORECASE,
        )
        std_url = re.sub(
            r"_[a-zA-Z0-9_]+Thumb[a-zA-Z0-9]*\.jpe?g$",
            f"-{base_id}{side}.jpg",
            url,
            flags=re.IGNORECASE,
        )
        return {"rep": rep_url, "std": std_url}
    url_std = re.sub(r"(Fr|Bk|Rep)\.jpe?g$", f"{side}.jpg", url, flags=re.IGNORECASE)
    url_rep = re.sub(r"(Fr|Bk|Rep)\.jpe?g$", f"Rep{side}.jpg", url, flags=re.IGNORECASE)
    return {"rep": url_rep, "std": url_std}


_VARIATION_NOTE_RE = re.compile(
    r"\b(Batting|Running|Pitching|Throwing|Fielding|Sliding|Celebrating|Smiling|Pointing|"
    r"Helmet\s+On|Helmet\s+Off|No\s+Helmet|Sunglasses|Horizontal|Vertical|Action\s+Variation|"
    r"Image\s+Variation|Photo\s+Variation|Throwback|SSP\s+Variation|SP\s+Variation)\b",
    re.IGNORECASE,
)


def _extract_subject_title_and_variation_from_tr(
    tr,
    card_num: str,
    primary_viewcard_title: str,
    person_names: list[str],
) -> tuple[str, str, str]:
    """
    Extracts `(subject_title, paren_players_str, variation_descriptor)` from a TCDB checklist `<tr>`:
      1. Handles unlinked League Leaders titles ('2025 AL Pitching Wins Leaders', 'National League Leaders RBI')
         even when TCDB does not wrap the title in a Person.cfm link.
      2. Handles Combo Player Cards ('Hopping to It', 'Bronx Buddies', 'All Smiles', 'New-Age Athletics')
         where the card title is followed by `(Player 1 / Player 2)` or listed alongside multiple Person.cfm links,
         preventing the row from ever falling back to the Team Name!
      3. Detects explicit variation descriptors in parentheses or notes (e.g. 'Shohei Ohtani (Running)' vs '(Batting)'
         in 2025 Topps Chrome) so multiple variations of the same card number get distinct Subset names.
    """
    has_parent_fn = hasattr(tr, "find_parent")
    own_tds = [td for td in tr.find_all("td") if not has_parent_fn or td.find_parent("tr") is tr]

    subject_td_title = ""
    paren_players_str = ""
    variation_note = ""

    # Locate the TD cell containing the card number so we can inspect the subject TD cells immediately after it
    cnum_td_idx = -1
    for idx_td, td in enumerate(own_tds):
        td_t = trim_clean(td.get_text(" ", strip=True))
        if td_t == card_num and card_num:
            cnum_td_idx = idx_td
            break

    candidate_tds = own_tds[cnum_td_idx + 1 :] if cnum_td_idx >= 0 else own_tds

    if cnum_td_idx < 0 and card_num:
        for idx_td, td in enumerate(own_tds):
            vc_a = td.find("a", href=re.compile(r"ViewCard\.cfm", re.IGNORECASE))
            if vc_a and trim_clean(vc_a.get_text(" ", strip=True)) == card_num:
                cnum_td_idx = idx_td
                break
        if cnum_td_idx >= 0:
            candidate_tds = own_tds[cnum_td_idx + 1 :]

    for td in candidate_tds:
        # Extract text while excluding Team.cfm, Glossary.cfm, and Card-Number ViewCard.cfm anchors
        # so unlinked CPC/LL titles (e.g., "It Takes Two") are preserved even if sharing a cell with Team/Glossary links
        excluded_anchor_ids = set()
        for a_el in td.find_all("a"):
            if has_parent_fn and a_el.find_parent("td") is not td:
                continue
            h_low = str(a_el.get("href") or "").lower()
            a_txt = trim_clean(a_el.get_text(" ", strip=True))
            if "team.cfm" in h_low or "glossary.cfm" in h_low or (card_num and a_txt == card_num):
                excluded_anchor_ids.add(id(a_el))

        text_chunks = []
        for node in td.descendants:
            if isinstance(node, str) and type(node).__name__ not in ("Comment", "Script", "Stylesheet", "Doctype"):
                parent_a = node.find_parent("a") if hasattr(node, "find_parent") else None
                if parent_a is not None and id(parent_a) in excluded_anchor_ids:
                    continue
                s_chunk = trim_clean(node)
                if s_chunk:
                    text_chunks.append(s_chunk)

        td_txt = trim_clean(" ".join(text_chunks))
        if not td_txt or td_txt == card_num or len(td_txt) <= 2:
            continue
        if td_txt.lower() in ("add", "view", "edit", "buy", "sell"):
            continue

        # Check for parenthesized content: either (Player 1 / Player 2) or variation note like (Running) / (Batting)
        for m_par in re.finditer(r"\(([^)]+)\)", td_txt):
            inside_p = trim_clean(m_par.group(1))
            if not inside_p:
                continue
            if "/" in inside_p:
                paren_players_str = " / ".join([p.strip() for p in inside_p.split("/") if p.strip()])
            elif _VARIATION_NOTE_RE.search(inside_p):
                variation_note = inside_p
            elif len(person_names) == 1 and inside_p.lower() != person_names[0].lower() and len(inside_p) <= 32:
                # Secondary descriptor on a single-player card (e.g. pose/variation note)
                if not any(g in inside_p.upper() for g in ("RC", "ASR", "LL", "CPC", "TC", "FS", "SP", "SSP", "VAR", "HOF")):
                    variation_note = inside_p

        cand_before = _clean_tcdb_card_subject_title(td_txt.split("(", 1)[0])
        if len(cand_before) >= 3 and cand_before != card_num and not cand_before.isdigit():
            subject_td_title = cand_before
            break

    if not paren_players_str and len(person_names) >= 2:
        paren_players_str = " / ".join(person_names)

    return subject_td_title, paren_players_str, variation_note


def parse_tcdb_checklist_table_rows(
    soup: BeautifulSoup,
    subset_name: str = "Base",
    current_url: str = "",
    page_num: int = 1,
) -> list[dict]:
    """
    Single-Pass Parser: Extracts complete 11-column checklist rows INCLUDING:
      - `TCDB_CID` (exact numeric CID from `/ViewCard.cfm/sid/.../cid/{CID}`)
      - Authentic League Leaders (`LL [Player1 / Player2]`) & Combo Card (`CPC [Player1 / Player2]`) titles
      - Automatic Variation disambiguation when multiple rows share a Card Number on the same checklist page
      - `TCDB_Image_Status` (`Front & Back on TCDB`, `Front Only on TCDB`, `No Image on TCDB`)
    """
    extracted = []
    seen_cids = set()
    nno_counter = 0
    sub_clean = trim_clean(subset_name) or "Base"

    for tr in soup.find_all("tr"):
        has_parent_fn = hasattr(tr, "find_parent")
        card_links = [
            a
            for a in tr.find_all("a", href=re.compile(r"ViewCard\.cfm", re.IGNORECASE))
            if not has_parent_fn or a.find_parent("tr") is tr
        ]
        if not card_links:
            continue

        primary_href = str(card_links[0].get("href", "")).strip()
        cid_str = extract_tcdb_id_from_url_or_href(card_href=primary_href)
        dedup_key = cid_str if cid_str != "0" else primary_href
        if dedup_key in seen_cids:
            continue
        seen_cids.add(dedup_key)

        # Inspect <img> tags in this row for Front & Back thumbnails
        front_thumb_url, back_thumb_url, img_alt = "", "", ""
        for img in tr.find_all("img"):
            if has_parent_fn and img.find_parent("tr") is not tr:
                continue
            src = str(img.get("data-original") or img.get("data-src") or img.get("src") or "").strip()
            if not src or any(
                x in src.lower()
                for x in (
                    "tcdblogo", "addimage", "addcard", "placeholder", "clear", "spacer",
                    "default", "noimage", "nophoto", "nofront", "noback", "missing", "blank",
                )
            ):
                continue
            if "/Images/" in src:
                full_src = src if src.startswith("http") else urljoin(BASE_URL, src)
                if re.search(r"(?:Thumb3|BkThumb|RepBk|Bk\.(?:jpe?g|png|gif))", full_src, re.IGNORECASE):
                    back_thumb_url = full_src
                elif not front_thumb_url:
                    front_thumb_url = full_src
                    img_alt = trim_clean(img.get("alt", ""))

        if cid_str == "0" and (front_thumb_url or back_thumb_url):
            cid_str = extract_tcdb_id_from_url_or_href(thumb_url=front_thumb_url or back_thumb_url)

        if front_thumb_url and back_thumb_url:
            img_status = "Front & Back on TCDB"
        elif front_thumb_url:
            img_status = "Front Only on TCDB"
        elif back_thumb_url:
            img_status = "Back Only on TCDB"
        else:
            img_status = "No Image on TCDB"

        text_card_links = [
            trim_clean(a.get_text(" ", strip=True))
            for a in card_links
            if trim_clean(a.get_text(" ", strip=True))
            and not trim_clean(a.get_text(" ", strip=True)).lower().startswith(("view", "add", "image", "buy"))
        ]
        card_num = text_card_links[0] if text_card_links else ""
        primary_viewcard_title = _clean_tcdb_card_subject_title(
            text_card_links[1] if len(text_card_links) >= 2 else ""
        )

        person_links = [
            pa
            for pa in tr.find_all("a", href=re.compile(r"Person\.cfm", re.IGNORECASE))
            if not has_parent_fn or pa.find_parent("tr") is tr
        ]
        person_names = []
        for pa in person_links:
            ptxt = _clean_tcdb_card_subject_title(pa.get_text(" ", strip=True))
            if ptxt and ptxt not in person_names:
                person_names.append(ptxt)

        subject_td_title, paren_players_str, variation_note = _extract_subject_title_and_variation_from_tr(
            tr, card_num, primary_viewcard_title, person_names
        )

        team_links = [
            ta
            for ta in tr.find_all("a", href=re.compile(r"Team\.cfm", re.IGNORECASE))
            if not has_parent_fn or ta.find_parent("tr") is tr
        ]
        teams = []
        for ta in team_links:
            t_txt = trim_clean(ta.get_text(" ", strip=True))
            if not t_txt:
                t_img = ta.find("img")
                if t_img:
                    t_txt = trim_clean(t_img.get("title") or t_img.get("alt") or "")
            if t_txt and t_txt not in teams:
                teams.append(t_txt)

        full_tr_text = trim_clean(tr.get_text(" ", strip=True))
        print_run = ""
        sn_match = re.search(r"\bSN\s*(\d+)\b", full_tr_text, re.IGNORECASE)
        if sn_match:
            print_run = str(int(sn_match.group(1)))
        elif re.search(r"\b1/1\b", full_tr_text):
            print_run = "1"

        tags: list[str] = []
        for ga in tr.find_all("a", href=re.compile(r"Glossary\.cfm", re.IGNORECASE)):
            if has_parent_fn and ga.find_parent("tr") is not tr:
                continue
            g_txt = trim_clean(ga.get_text(" ", strip=True))
            if g_txt:
                _add_tag(tags, g_txt, print_run)

        for g_code in ("RC", "ASR", "LL", "CPC", "TC", "FS", "SP", "SSP", "VAR", "HOF", "AS", "ERR", "UER", "COR"):
            if re.search(rf"\b{g_code}\b", full_tr_text):
                _add_tag(tags, g_code, print_run)
        if re.search(r"\b(AU|AUTO|AUTOGRAPH)\b", full_tr_text, re.IGNORECASE):
            _add_tag(tags, "Auto", print_run)
        if re.search(r"\b(MEM|REL|RELIC)\b", full_tr_text, re.IGNORECASE):
            _add_tag(tags, "Mem", print_run)
        if print_run:
            _add_tag(tags, f"SN{print_run}" if print_run != "1" else "1/1", print_run)

        team_str = "/".join(teams) if teams else "NO TEAM"

        href_slug_title = _extract_title_from_viewcard_href(primary_href, card_num)
        is_cpc_or_ll_tag = ("CPC" in tags) or ("LL" in tags)

        # Resolve Player / Card Title:
        # 1. For single-person cards (not LL/CPC), prefer the exact <a href="Person.cfm"> anchor text
        #    whenever the cell text starts with that person's name (excludes trailing occupations like
        #    'Comedian, Actor', 'Rapper', 'Actress', 'AU, SN99 Bassist', or 'UER: ...').
        # 2. Otherwise use TCDB's unlinked TD text / ViewCard hyperlink slug (protecting LL & CPC titles).
        player_str = ""
        if (
            len(person_names) == 1
            and not is_cpc_or_ll_tag
            and not _is_league_leaders_title(subject_td_title)
            and (
                not subject_td_title
                or subject_td_title.lower().startswith(person_names[0].lower())
                or norm(subject_td_title).startswith(norm(person_names[0]))
            )
        ):
            player_str = person_names[0]
        elif (
            subject_td_title
            and not _is_placeholder_team_checklist_name(subject_td_title)
            and not (is_cpc_or_ll_tag and team_str != "NO TEAM" and norm(subject_td_title) == norm(team_str))
        ):
            player_str = subject_td_title
        elif (
            primary_viewcard_title
            and not _is_placeholder_team_checklist_name(primary_viewcard_title)
            and not (is_cpc_or_ll_tag and team_str != "NO TEAM" and norm(primary_viewcard_title) == norm(team_str))
        ):
            player_str = primary_viewcard_title
        elif (
            href_slug_title
            and not _is_placeholder_team_checklist_name(href_slug_title)
            and not (is_cpc_or_ll_tag and team_str != "NO TEAM" and norm(href_slug_title) == norm(team_str))
        ):
            player_str = href_slug_title
        elif person_names:
            player_str = "/".join(person_names)
        elif primary_viewcard_title:
            player_str = primary_viewcard_title

        if player_str:
            p_stripped, extra_tags_p, extra_pr_p = _strip_inline_tags_errors_and_occupations(player_str, team_str=team_str)
            if p_stripped:
                player_str = p_stripped
            if extra_pr_p and not print_run:
                print_run = extra_pr_p
            for et in extra_tags_p:
                _add_tag(tags, et, print_run)

        if (not card_num or not player_str) and img_alt and "#" in img_alt:
            m_alt = re.search(r"#([A-Za-z0-9\-]+)\s+(.*)$", img_alt)
            if m_alt:
                if not card_num:
                    card_num = m_alt.group(1).strip()
                if not player_str and m_alt.group(2).strip():
                    player_str = _clean_tcdb_card_subject_title(m_alt.group(2).strip())

        is_ll_card = ("LL" in tags) or _is_league_leaders_title(player_str) or _is_league_leaders_title(full_tr_text)
        is_cpc_card = ("CPC" in tags) or (
            bool(subject_td_title)
            and bool(paren_players_str)
            and not is_ll_card
            and norm(subject_td_title) != norm(paren_players_str)
        )

        if is_ll_card:
            _add_tag(tags, "LL", print_run)
            if not player_str or player_str.upper() == "NO TEAM":
                # Extract League Leaders title from full_tr_text if the cell had no anchor tag
                m_ll_txt = re.search(
                    r"((?:19|20)\d{2}\s+(?:AL|NL|MLB|American\s+League|National\s+League)\s+[A-Za-z\s]+?Leaders|"
                    r"(?:American|National)\s+League\s+Leaders\s+[A-Za-z0-9\s]+?)(?:\(|\bLL\b|$)",
                    full_tr_text,
                    re.IGNORECASE,
                )
                if m_ll_txt:
                    player_str = _clean_tcdb_card_subject_title(m_ll_txt.group(1))
                elif paren_players_str:
                    player_str = f"League Leaders ({paren_players_str})"
                else:
                    player_str = "League Leaders"
        elif is_cpc_card:
            _add_tag(tags, "CPC", print_run)
            # Never allow a Combo Player Card to be tagged TC or overwritten with a team name
            tags = [t for t in tags if t != "TC"]
            if not player_str or (team_str != "NO TEAM" and norm(player_str) == norm(team_str)):
                if href_slug_title and norm(href_slug_title) != norm(team_str):
                    player_str = href_slug_title
                elif paren_players_str:
                    player_str = paren_players_str.replace(" / ", "/")
        else:
            if not player_str and team_str != "NO TEAM":
                player_str = team_str.split("/")[0].strip()
                _add_tag(tags, "TC", print_run)
            else:
                was_placeholder = _is_placeholder_team_checklist_name(player_str)
                player_str = format_checklist_team_card_player(player_str, team_str)
                if was_placeholder:
                    _add_tag(tags, "TC", print_run)

        if not card_num and not player_str:
            continue

        if not card_num or card_num.upper() in ("NNO", "0", "TBD", "-"):
            nno_counter += 1
            sub_words = [
                w
                for w in re.findall(r"[A-Za-z0-9]+", sub_clean)
                if w.upper() not in ("THE", "OF", "AND", "CARDS", "REDEMPTIONS", "REDEMPTION")
            ]
            sub_pref = "".join(w[0].upper() for w in sub_words[:3]) or "NNO"
            card_num = f"{sub_pref}-{nno_counter}"

        # Disambiguate Variation rows (e.g. 2025 Topps Chrome #1 Shohei Ohtani VAR / Running)
        row_subset = sub_clean
        if ("VAR" in tags or variation_note) and "VARIATION" not in row_subset.upper():
            if variation_note:
                row_subset = (
                    f"Base Image Variation ({variation_note})"
                    if row_subset.upper() in ("BASE", "BASE SET")
                    else f"{row_subset} Variation ({variation_note})"
                )

        attr_str = format_attributes_column(tags, paren_players=paren_players_str)

        extracted.append({
            "Subset": row_subset,
            "Card Number": card_num.lstrip("#"),
            "Player": player_str,
            "Team": team_str,
            "Print Run": print_run,
            "Attributes": attr_str,
            "TCDB_CID": cid_str if cid_str != "0" else "",
            "Front_Downloaded": "No",
            "Back_Downloaded": "No",
            "TCDB_Image_Status": img_status,
            "_front_thumb": front_thumb_url,
            "_back_thumb": back_thumb_url,
            "_front_tier_hint": ("R" if "rep" in front_thumb_url.lower() else ("S" if front_thumb_url else "")),
            "_back_tier_hint": ("R" if "rep" in back_thumb_url.lower() else ("S" if back_thumb_url else "")),
            "_referer": current_url,
            "_page_num": page_num,
        })

    return extracted


# ==============================================================================
# 4. UNIFIED DOWNLOAD STATUS TRACKER (SYNC CHECKLISTS + CATALOGS IN ONE PLACE)
# ==============================================================================
def _catalog_dir() -> Path:
    return CACHE_CATALOGS_DIR if IS_REORGANIZED_V24 else SET_LIBRARY_CACHE_DIR


def load_catalog(set_folder_name: str) -> dict:
    ensure_directories()
    fname = f"{sanitize_filename_part(set_folder_name)}_catalog.json"
    for cand_dir in (_catalog_dir(), SET_LIBRARY_CACHE_DIR):
        path = cand_dir / fname
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def save_catalog(set_folder_name: str, catalog: dict):
    ensure_directories()
    target_dir = _catalog_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{sanitize_filename_part(set_folder_name)}_catalog.json"
    try:
        with interprocess_file_lock(path.with_suffix(".json.lock")):
            atomic_write_text(path, json.dumps(catalog, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_dead_backs_cache() -> dict[str, float]:
    """Loads `tcdb_dead_backs_cache.json` and auto-prunes entries older than `DEAD_BACKS_TTL_DAYS`."""
    ensure_directories()
    if not DEAD_BACKS_CACHE_FILE.exists():
        return {}
    try:
        raw = json.loads(DEAD_BACKS_CACHE_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return {}
        cutoff = time.time() - (DEAD_BACKS_TTL_DAYS * 86400.0)
        return {str(k): float(v) for k, v in raw.items() if float(v or 0) >= cutoff}
    except Exception:
        return {}


def save_dead_backs_cache(cache_dict: dict[str, float]):
    ensure_directories()
    try:
        atomic_write_text(DEAD_BACKS_CACHE_FILE, json.dumps(cache_dict, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_dead_fronts_cache() -> dict[str, float]:
    """Loads `tcdb_dead_fronts_cache.json` and auto-prunes entries older than `DEAD_FRONTS_TTL_DAYS`."""
    ensure_directories()
    if not DEAD_FRONTS_CACHE_FILE.exists():
        return {}
    try:
        raw = json.loads(DEAD_FRONTS_CACHE_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return {}
        cutoff = time.time() - (DEAD_FRONTS_TTL_DAYS * 86400.0)
        return {str(k): float(v) for k, v in raw.items() if float(v or 0) >= cutoff}
    except Exception:
        return {}


def save_dead_fronts_cache(cache_dict: dict[str, float]):
    ensure_directories()
    try:
        atomic_write_text(DEAD_FRONTS_CACHE_FILE, json.dumps(cache_dict, indent=2), encoding="utf-8")
    except Exception:
        pass


def checkpoint_file_path(set_name_or_key: str) -> Path:
    return CACHE_CHECKPOINTS_DIR / f"{sanitize_filename_part(set_name_or_key)}_checkpoint.json"


def load_set_checkpoint(set_name_or_key: str, alt_folder_name: str = "") -> dict:
    """Loads per-set subset-level validation checkpoint JSON."""
    ensure_directories()
    candidates = [checkpoint_file_path(set_name_or_key)]
    if alt_folder_name and sanitize_filename_part(alt_folder_name) != sanitize_filename_part(set_name_or_key):
        candidates.append(checkpoint_file_path(alt_folder_name))
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    data.setdefault("schema_version", CHECKPOINT_SCHEMA_VERSION)
                    data.setdefault("subsets", {})
                    return data
            except Exception:
                pass
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "set_key": sanitize_filename_part(set_name_or_key),
        "set_name": str(set_name_or_key),
        "subsets": {},
    }


def save_set_checkpoint(set_name_or_key: str, checkpoint: dict):
    ensure_directories()
    try:
        CACHE_CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint["schema_version"] = CHECKPOINT_SCHEMA_VERSION
        atomic_write_text(checkpoint_file_path(set_name_or_key), json.dumps(checkpoint, indent=2), encoding="utf-8")
    except Exception:
        pass


def compute_subset_rows_checksum(rows: list[dict]) -> str:
    """
    Computes a canonical SHA-256 checksum over sorted
    `(Card Number, TCDB_CID, Player, canonical_subset_key)` tuples so harmless row
    reordering never triggers false re-scrapes.
    """
    tuples_list = []
    for r in rows or []:
        cnum = str(r.get("Card Number") or "").strip().lstrip("#")
        cid = str(r.get("TCDB_CID") or "").strip()
        if cid == "0":
            cid = ""
        plr = str(r.get("Player") or "").strip()
        sub_k = canonical_subset_key(str(r.get("Subset") or "Base").strip() or "Base")
        tuples_list.append((cnum, cid, plr, sub_k))
    tuples_list.sort()
    payload = json.dumps(tuples_list, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_subset_name_for_diff(subset_name: str) -> str:
    """
    Normalizes subset names consistently for live TCDB vs local CSV/checkpoint comparison:
    - strips accents and lowercases
    - normalizes `&` -> ` and `, `_`/`-` -> spaces, collapses whitespace
    - maps common Base aliases to `base`
    """
    s = strip_accents(str(subset_name or "Base")).lower().strip()
    s = s.replace("&", " and ").replace("_", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s in (
        "",
        "base",
        "base set",
        "base rookie",
        "base rookies",
        "base veteran",
        "base veterans",
        "base veteran combos",
        "base rookie debut",
    ):
        return "base"
    if s.startswith("base ") and not s.startswith("base paper"):
        s = s[5:].strip()
    return s or "base"


def _lookup_local_subset_rows(local_rows_by_key: dict[str, list[dict]], sub_label: str) -> list[dict]:
    if not local_rows_by_key:
        return []
    sub_k = canonical_subset_key(sub_label)
    if sub_k in local_rows_by_key:
        return local_rows_by_key[sub_k]
    target_norm = normalize_subset_name_for_diff(sub_label)
    for k_loc, rows_loc in local_rows_by_key.items():
        if normalize_subset_name_for_diff(k_loc) == target_norm:
            return rows_loc
        if rows_loc and normalize_subset_name_for_diff(str(rows_loc[0].get("Subset") or "")) == target_norm:
            return rows_loc
    return []


def _load_local_set_csv_rows_by_subset(
    chk_title: str,
    folder_name: str = "",
) -> tuple[dict[str, list[dict]], dict[str, str], Optional[Path]]:
    """
    Reads `Set_Checklists/<Set>.csv` and groups rows by `canonical_subset_key(Subset)`.
    Returns `(rows_by_canon_key, display_name_by_canon_key, csv_path_used)`.
    """
    rows_by_key: dict[str, list[dict]] = defaultdict(list)
    names_by_key: dict[str, str] = {}
    candidates = [
        SET_CHECKLISTS_DIR / f"{sanitize_filename_part(chk_title)}.csv",
    ]
    if folder_name:
        candidates.append(SET_CHECKLISTS_DIR / f"{sanitize_filename_part(folder_name)}.csv")
    csv_p = next((p for p in candidates if p.exists()), None)
    if not csv_p:
        return dict(rows_by_key), names_by_key, None
    try:
        df = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
        if df.empty or "Subset" not in df.columns:
            return dict(rows_by_key), names_by_key, csv_p
        for rec in df.to_dict(orient="records"):
            sub_disp = str(rec.get("Subset") or "Base").strip() or "Base"
            sub_k = canonical_subset_key(sub_disp)
            rows_by_key[sub_k].append(rec)
            names_by_key.setdefault(sub_k, sub_disp)
    except Exception:
        pass
    return dict(rows_by_key), names_by_key, csv_p


def _try_bootstrap_subset_checkpoint(
    checkpoint: dict,
    sid_key: str,
    subset_url: str,
    subset_label: str,
    expected_cards: int,
    local_rows: list[dict],
    is_base: bool = False,
) -> Optional[dict]:
    """
    Existing-CSV Bootstrap: When `<set>_checkpoint.json` lacks `sid_key`, checks if
    `Set_Checklists/<Set>.csv` already has `len(local_rows) == expected_cards` (> 0)
    with populated `TCDB_CID`s, and seeds the checkpoint entry as `"complete"`.
    """
    if expected_cards <= 0 or not local_rows or len(local_rows) != expected_cards:
        return None
    populated_cids = sum(
        1 for r in local_rows
        if str(r.get("TCDB_CID") or "").strip() not in ("", "0", "nan", "None")
    )
    if populated_cids == 0 or (populated_cids < len(local_rows) and populated_cids < int(len(local_rows) * 0.95)):
        return None

    imaged_f = sum(
        1 for r in local_rows
        if "front" in str(r.get("TCDB_Image_Status") or "").lower()
    )
    imaged_b = sum(
        1 for r in local_rows
        if "back" in str(r.get("TCDB_Image_Status") or "").lower()
        and "no back" not in str(r.get("TCDB_Image_Status") or "").lower()
    )
    entry = {
        "subset_name": str(subset_label),
        "subset_url": str(subset_url),
        "is_base": bool(is_base),
        "expected_cards": int(expected_cards),
        "tcdb_reported_count": int(expected_cards),
        "scraped_cards": len(local_rows),
        "local_deduped_count": len(local_rows),
        "imaged_fronts_on_tcdb": imaged_f,
        "imaged_backs_on_tcdb": imaged_b,
        "rows_sha256": compute_subset_rows_checksum(local_rows),
        "status": "complete",
        "bootstrapped_from_csv": True,
        "last_verified_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    checkpoint.setdefault("subsets", {})[str(sid_key)] = entry
    return entry


def _index_existing_set_dir_by_cid(set_dir: Path) -> dict[tuple[str, str], Path]:
    """Pre-indexes all existing `.jpg` files in `set_dir` by `(numeric_TCDB_CID, 'F'|'B')` for 0ms skips & local renames."""
    idx_map: dict[tuple[str, str], Path] = {}
    if not set_dir.exists():
        return idx_map
    for p in set_dir.glob("*.jpg"):
        parsed = parse_unified_card_filename(p.name)
        if parsed and parsed.get("is_template") and parsed.get("cid"):
            cid_n = normalize_numeric_tcdb_cid(parsed["cid"])
            if cid_n and cid_n != "0":
                idx_map[(cid_n, parsed["side"])] = p
    return idx_map


def _check_or_rename_existing_cid_file(
    disk_cid_index: dict[tuple[str, str], Path],
    cid: str,
    side: str,
    expected_path: Path,
) -> Optional[str]:
    """
    Returns `'Skip(Exists)'` if `expected_path` exists, `'Skip(Renamed)'` if an earlier-named
    file for the same `(cid, side)` was renamed in-place to `expected_path`, or `None` if missing.
    """
    if expected_path.exists():
        disk_cid_index[(cid, side)] = expected_path
        return "Skip(Exists)"
    existing_p = disk_cid_index.get((cid, side))
    if existing_p is not None and existing_p.exists():
        try:
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            existing_p.replace(expected_path)
            disk_cid_index[(cid, side)] = expected_path
            return "Skip(Renamed)"
        except Exception:
            return "Skip(Exists)"
    return None


def sync_set_library_download_status(
    target_set_name: Optional[str] = None,
    rebuild_master_checklist: bool = True,
) -> dict:
    """
    Single Source of Truth Tracker:
    Scans `D:\\Tabulas Set Library` for all `[Set]_[Subset]_[#CardNumber]_[Player]_[TCDB{CID}]_{F|B}.jpg`
    images on disk and updates `Front_Downloaded` ('Yes'/'No') and `Back_Downloaded` ('Yes'/'No')
    directly in `Checklists/Set_Checklists/<Set>.csv`, `Checklists/Master_Checklist.csv`, and
    `D:\\Tabulas Set Library\\logs\\<Set>_catalog.json`!
    """
    ensure_directories()
    t_sync0 = time.time()
    downloaded_by_cid_side: set[tuple[str, str]] = set()
    downloaded_by_design_side: set[tuple[str, str, str, str]] = set()

    log_msg(f"🔄 Scanning Reference Library images on disk ({REFERENCE_TEMPLATES_DIR})...")
    scanned_jpgs = 0
    if REFERENCE_TEMPLATES_DIR.exists():
        for img_p in REFERENCE_TEMPLATES_DIR.rglob("*.jpg"):
            scanned_jpgs += 1
            parsed = parse_unified_card_filename(img_p.name)
            if not parsed or not parsed.get("is_template"):
                continue
            side = parsed["side"]
            cid_num = normalize_numeric_tcdb_cid(parsed.get("cid", ""))
            if cid_num and cid_num != "0":
                downloaded_by_cid_side.add((cid_num, side))
            s_key = canonical_set_key(parsed["set"])
            sub_c = canonical_subset_key(parsed["subset"], parsed["set"])
            cn_n = norm(parsed["card_number"])
            downloaded_by_design_side.add((s_key, sub_c, cn_n, side))
    log_msg(
        f"  🗂️ Scanned {scanned_jpgs:,} .jpg file(s) in {time.time() - t_sync0:.2f}s "
        f"({len(downloaded_by_cid_side):,} CID-side pairs indexed)."
    )

    csv_files = sorted(SET_CHECKLISTS_DIR.glob("*.csv")) if SET_CHECKLISTS_DIR.exists() else []
    total_csvs = len(csv_files)
    updated_sets = 0
    total_rows = 0
    fronts_yes = 0
    backs_yes = 0
    missing_backs_cnt = 0
    dfs_all = []

    for csv_idx, csv_p in enumerate(csv_files, 1):
        try:
            df = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
            if df.empty:
                continue
            for col in CHECKLIST_COLUMNS:
                if col not in df.columns:
                    df[col] = ""

            set_title = canonicalize_checklist_set_title(df["Set"].iloc[0] if "Set" in df.columns else csv_p.stem)
            if target_set_name and canonical_set_key(set_title) != canonical_set_key(target_set_name):
                dfs_all.append(df[CHECKLIST_COLUMNS])
                continue

            s_key = canonical_set_key(set_title)
            f_flags = []
            b_flags = []

            for _, r in df.iterrows():
                cid_n = normalize_numeric_tcdb_cid(r.get("TCDB_CID", ""))
                sub_c = canonical_subset_key(r.get("Subset", "Base"), set_title)
                cn_n = norm(str(r.get("Card Number", "")).lstrip("#"))

                has_f = (
                    (cid_n != "0" and (cid_n, "F") in downloaded_by_cid_side)
                    or ((s_key, sub_c, cn_n, "F") in downloaded_by_design_side)
                )
                has_b = (
                    (cid_n != "0" and (cid_n, "B") in downloaded_by_cid_side)
                    or ((s_key, sub_c, cn_n, "B") in downloaded_by_design_side)
                )

                f_flags.append("Yes" if has_f else "No")
                b_flags.append("Yes" if has_b else "No")
                total_rows += 1
                if has_f:
                    fronts_yes += 1
                    if not has_b:
                        missing_backs_cnt += 1
                if has_b:
                    backs_yes += 1

            df["Front_Downloaded"] = f_flags
            df["Back_Downloaded"] = b_flags
            df = df[CHECKLIST_COLUMNS]
            with interprocess_file_lock(csv_p.with_suffix(".csv.lock")):
                atomic_write_bytes(
                    csv_p,
                    lambda tmp_p: df.to_csv(tmp_p, index=False, encoding="utf-8-sig"),
                )

            # Sync exact per-set card counts & downloaded image totals into the ETA telemetry cache
            try:
                sub_counts = {str(k): int(v) for k, v in df["Subset"].value_counts().items() if str(k).strip()}
                base_cnt_s = int(sum(v for k, v in sub_counts.items() if k.upper() in ("BASE", "BASE SET")))
                imaged_tcdb_s = int(df["TCDB_Image_Status"].astype(str).str.contains("Front", case=False, na=False).sum()) if "TCDB_Image_Status" in df.columns else 0
                f_set_cnt = sum(1 for x in f_flags if x == "Yes")
                b_set_cnt = sum(1 for x in b_flags if x == "Yes")
                get_rate_learner().update_set_stats(
                    set_key=sanitize_filename_part(set_title),
                    set_name=set_title,
                    total_cards=len(df),
                    base_cards=base_cnt_s,
                    total_subsets=len(sub_counts),
                    imaged_cards_on_tcdb=imaged_tcdb_s,
                    fronts_downloaded=f_set_cnt,
                    backs_downloaded=b_set_cnt,
                    subset_card_counts=sub_counts,
                    force_save=False,
                )
            except Exception:
                pass

            dfs_all.append(df)
            updated_sets += 1
            if not target_set_name:
                f_set_now = sum(1 for x in f_flags if x == "Yes")
                b_set_now = sum(1 for x in b_flags if x == "Yes")
                log_msg(
                    f"[{csv_idx}/{total_csvs}] Synced '{set_title}' ({len(df):,} rows) -> "
                    f"Fronts: {f_set_now:,} | Backs: {b_set_now:,}"
                )
        except Exception as e:
            log_msg(f"[{csv_idx}/{total_csvs}] [!] Sync error on {csv_p.name}: {e}")
            continue

    if rebuild_master_checklist and dfs_all:
        log_msg(f"📦 Rebuilding Master_Checklist.csv from {len(dfs_all)} set checklist(s)...")
        master_df = pd.concat(dfs_all, ignore_index=True).drop_duplicates(
            subset=["Set", "Subset", "Card Number", "Player", "TCDB_CID"], keep="first"
        )
        with interprocess_file_lock(CHECKLIST_PATH.with_suffix(".csv.lock")):
            atomic_write_bytes(
                CHECKLIST_PATH,
                lambda tmp_p: master_df[CHECKLIST_COLUMNS].to_csv(tmp_p, index=False, encoding="utf-8-sig"),
            )
            try:
                atomic_write_bytes(
                    CHECKLIST_BACKUP_PATH,
                    lambda tmp_p: shutil.copy2(CHECKLIST_PATH, tmp_p),
                )
            except Exception:
                pass
        log_msg(f"  ✅ Wrote {len(master_df):,} total rows to Master_Checklist.csv in {time.time() - t_sync0:.2f}s.")

    log_msg(
        f"📊 Set Library Status Synced ({updated_sets} sets, {total_rows:,} rows): "
        f"{fronts_yes:,} Fronts downloaded, {backs_yes:,} Backs downloaded, {missing_backs_cnt:,} missing backs."
    )
    return {
        "updated_sets": updated_sets,
        "total_rows": total_rows,
        "fronts_downloaded": fronts_yes,
        "backs_downloaded": backs_yes,
        "missing_backs": missing_backs_cnt,
    }


# ==============================================================================
# 5. SINGLE-PASS ASYNC + STEALTH CHECKLIST & TEMPLATE SCRAPER ENGINE
# ==============================================================================
def _normalize_attributes_string(attr_raw: str, print_run_clean: str = "") -> str:
    """Normalizes Attributes tokens (SN99 -> #/99, 1/1, Auto, Mem) without duplicating tags."""
    s = trim_clean(attr_raw)
    s = re.sub(r"\bSN\s*(\d+)\b", r"#/\1", s, flags=re.IGNORECASE)
    if print_run_clean:
        pr_tok = "1/1" if print_run_clean == "1" else f"#/{print_run_clean}"
        s = re.sub(r"\bSN\b", pr_tok, s, flags=re.IGNORECASE)
    else:
        pr_tok = ""

    parts = [p.strip() for p in s.split(",") if p.strip()]
    deduped = []
    for p in parts:
        p_up = p.upper()
        if p_up in ("AU", "AUTO", "AUTOGRAPH", "AUTOGRAPHED"):
            tok = "Auto"
        elif p_up in ("MEM", "REL", "RELIC", "MEMORABILIA"):
            tok = "Mem"
        else:
            tok = p
        if tok not in deduped:
            deduped.append(tok)

    if pr_tok and pr_tok not in deduped:
        deduped.append(pr_tok)
    return ", ".join(deduped)


def apply_excel_formulas_and_combine(
    raw_rows: list[dict],
    set_name: str,
    stats_out: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Canonicalizes and repairs checklist rows in O(N) time:
      1. Canonicalizes Set title & cleans Subset prefixes (stripping parent Set prefix, restoring 2025-26, 8-Bit, X-Fractor, A&G).
      2. Normalizes Card Number (strip #, deterministic NNO numbering) and Print Run (numeric).
      3. Deduplicates pagination duplicates by TCDB_CID BEFORE variation disambiguation.
      4. Restores Team Cards (TC), League Leaders (LL), Combo Player Cards (CPC), and TRUE_2026_TOPPS_BASE_CARDS ground-truth titles.
      5. Disambiguates genuine Variation rows (VAR or distinct TCDB_CID on the same Card Number) in O(N) using precomputed counts.
      6. Formats all serial tags as #/N or 1/1 (never SN99).
    """
    if not raw_rows:
        return pd.DataFrame(columns=CHECKLIST_COLUMNS)

    stats = stats_out if isinstance(stats_out, dict) else {}
    for k in ("subsets_cleaned", "players_repaired", "attrs_normalized", "variations_disambiguated"):
        stats.setdefault(k, 0)

    canon_set = canonicalize_checklist_set_title(set_name)
    df = pd.DataFrame(raw_rows)
    df["Set"] = canon_set
    for col in CHECKLIST_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].map(trim_clean)

    # Filter out pure generic nav junk rows
    df = df[~df["Subset"].str.lower().isin(("insert", "inserts", "checklist", "overview"))].copy()
    if df.empty:
        return pd.DataFrame(columns=CHECKLIST_COLUMNS)

    # 1. Clean Subset names (strip parent set prefix, restore hyphens & A&G)
    cleaned_subs = []
    for raw_sub in df["Subset"]:
        c_sub = clean_tcdb_subset_title(raw_sub, checklist_set_name=canon_set) or "Base"
        if c_sub != raw_sub:
            stats["subsets_cleaned"] += 1
        cleaned_subs.append(c_sub)
    df["Subset"] = cleaned_subs

    # 2. Normalize TCDB_CID, Download Status, Card Number & Print Run
    df["TCDB_CID"] = df["TCDB_CID"].map(lambda x: normalize_numeric_tcdb_cid(x) if str(x).strip() else "")
    df["TCDB_CID"] = df["TCDB_CID"].replace("0", "")
    df["Front_Downloaded"] = df["Front_Downloaded"].replace("", "No")
    df["Back_Downloaded"] = df["Back_Downloaded"].replace("", "No")
    df["Print Run"] = df["Print Run"].map(format_print_run)

    unnumbered_counters: dict[str, int] = defaultdict(int)
    fixed_cnums = []
    for sub_v, cn_v in zip(df["Subset"], df["Card Number"]):
        cn_clean = str(cn_v or "").strip().lstrip("#")
        if not cn_clean or cn_clean.upper() in ("0", "NNO", "NONE", "NAN", "TBD", "-"):
            unnumbered_counters[sub_v] += 1
            idx_u = unnumbered_counters[sub_v]
            sub_words = [
                w for w in re.findall(r"[A-Za-z0-9]+", sub_v)
                if w.upper() not in ("THE", "OF", "AND", "CARDS", "REDEMPTIONS", "REDEMPTION")
            ]
            sub_pref = "".join(w[0].upper() for w in sub_words[:3]) or "NNO"
            cn_clean = f"{sub_pref}-{idx_u}"
        fixed_cnums.append(cn_clean)
    df["Card Number"] = fixed_cnums

    # 3. Deduplicate true identical rows FIRST (by TCDB_CID when present) so pagination repeats aren't mistaken for Variations
    df["_has_cid"] = df["TCDB_CID"].apply(lambda x: 1 if x != "" else 0)
    df["_has_pr"] = df["Print Run"].apply(lambda x: 1 if x != "" else 0)
    df = df.sort_values(by=["_has_cid", "_has_pr"], ascending=[False, False]).reset_index(drop=True)

    with_cid = df[df["TCDB_CID"] != ""].drop_duplicates(subset=["Set", "TCDB_CID"], keep="first")
    no_cid = df[df["TCDB_CID"] == ""].drop_duplicates(subset=["Set", "Subset", "Card Number", "Player", "Team", "Attributes"], keep="first")
    df = pd.concat([with_cid, no_cid], ignore_index=True).drop(columns=["_has_cid", "_has_pr"])

    # 4. Repair Player Titles, Team Cards (TC), League Leaders (LL), Combo Cards (CPC), and Attributes (#/N)
    is_2026_topps = (canon_set == "2026 Topps Baseball")
    _single_player_2026_cnums = {"1", "2"}

    # Identify Base & Base-Parallel subsets dynamically so numeric insert subsets are NEVER overwritten
    base_family_subsets: set[str] = {"BASE", "BASE SET"}
    if is_2026_topps:
        sub_numeric_counts: dict[str, int] = defaultdict(int)
        for s_item, cn_item in zip(df["Subset"], df["Card Number"]):
            if str(cn_item).isdigit() and 1 <= int(cn_item) <= 700:
                sub_numeric_counts[str(s_item).strip().upper()] += 1
        _base_par_keywords = (
            "FOIL", "HOLO", "DIAMANTE", "SPRING TRAINING", "GOLDEN MIRROR", "INDEPENDENCE DAY",
            "MOTHER'S DAY", "FATHER'S DAY", "MEMORIAL DAY", "VINTAGE STOCK", "CLEAR", "ACETATE",
            "CANVAS", "TRUE PHOTO", "PRINTING PLATE", "FIRST CARD", "SANDGLITTER", "WOOD",
            "CRACKLEBOARD", "FANATICS", "MEIJER", "WALMART", "TARGET", "COMPANION", "TEAM COLOR",
            "CONFETTI", "SUPERFRACTOR", "FOILFRACTOR", "CHROME", "REFRACTOR", "BASE ",
        )
        _insert_excl_keywords = (
            "AUTOGRAPH", "RELIC", "PATCH", "JERSEY", "ALL ACES", "HOME FIELD", "HEAVY LUMBER",
            "STARS OF MLB", "GREATEST HITS", "CALL TO THE HALL", "1990", "1991", "1989",
            "TOPPS NOW", "TRAINING GROUNDS", "FIRST PITCH", "CACTUS LEAGUE", "GRAPEFRUIT",
        )
        for s_up, num_cnt in sub_numeric_counts.items():
            if s_up in ("BASE", "BASE SET") or s_up.startswith("BASE "):
                base_family_subsets.add(s_up)
            elif num_cnt >= 100 and not any(ex in s_up for ex in _insert_excl_keywords):
                base_family_subsets.add(s_up)
            elif num_cnt >= 15 and any(kw in s_up for kw in _base_par_keywords) and not any(ex in s_up for ex in _insert_excl_keywords):
                base_family_subsets.add(s_up)

    repaired_players = []
    repaired_teams = []
    repaired_attrs = []

    repaired_prs = []
    for sub_v, cn_v, plr_v, tm_v, pr_v, attr_v in zip(
        df["Subset"], df["Card Number"], df["Player"], df["Team"], df["Print Run"], df["Attributes"]
    ):
        p_orig = str(plr_v or "").strip()
        t_orig = str(tm_v or "").strip()
        a_orig = str(attr_v or "").strip()
        pr_clean = str(pr_v or "").strip()

        p_clean, p_extra_tags, p_extra_pr = _strip_inline_tags_errors_and_occupations(p_orig, team_str=t_orig)
        p_clean = p_clean or p_orig
        t_clean = t_orig
        a_clean = a_orig
        if p_extra_pr and not pr_clean:
            pr_clean = p_extra_pr
        if p_extra_tags:
            for pt in p_extra_tags:
                if pt.upper() not in a_clean.upper():
                    a_clean = f"{a_clean}, {pt}".strip(", ")

        # Extract any bracketed players [Player 1 / Player 2]
        m_br = re.search(r"\[([^\]]+)\]", a_clean)
        bracket_players = m_br.group(1).strip() if m_br else ""

        # Apply exact 2026 Topps Baseball ground-truth titles ONLY to Base & verified Base Parallel rows
        is_base_family_row = str(sub_v or "Base").strip().upper() in base_family_subsets
        if is_2026_topps and is_base_family_row and cn_v in TRUE_2026_TOPPS_BASE_CARDS:
            gt_title, gt_team = TRUE_2026_TOPPS_BASE_CARDS[cn_v]
            if norm(p_clean) != norm(gt_title):
                # Preserve existing player names inside bracket if this is an LL or CPC card
                if "/" in p_clean and not bracket_players and cn_v not in _single_player_2026_cnums:
                    bracket_players = " / ".join(x.strip() for x in p_clean.split("/") if x.strip())
                p_clean = gt_title
                if not t_clean or t_clean.upper() == "NO TEAM":
                    t_clean = gt_team
                if cn_v in _single_player_2026_cnums:
                    # Single-player base cards (#1 Aaron Judge, #2 Daulton Varsho) must NOT receive CPC/TC tags
                    base_tags = [t.strip() for t in re.sub(r"\[[^\]]*\]", "", a_clean).split(",") if t.strip() and t.strip().upper() not in ("TC", "CPC")]
                    a_clean = format_attributes_column(base_tags)
                elif _is_league_leaders_title(gt_title):
                    a_clean = format_attributes_column(
                        list(dict.fromkeys([t.strip() for t in re.sub(r"\[[^\]]*\]", "", a_clean).split(",") if t.strip()] + ["LL"])),
                        paren_players=bracket_players,
                    )
                elif norm(gt_title) == norm(gt_team):
                    a_clean = format_attributes_column(
                        list(dict.fromkeys([t.strip() for t in re.sub(r"\[[^\]]*\]", "", a_clean).split(",") if t.strip()] + ["TC"]))
                    )
                else:
                    base_tags = [t.strip() for t in re.sub(r"\[[^\]]*\]", "", a_clean).split(",") if t.strip() and t.strip().upper() != "TC"]
                    if "CPC" not in [x.upper() for x in base_tags]:
                        base_tags.append("CPC")
                    a_clean = format_attributes_column(base_tags, paren_players=bracket_players)

        # General Team Card placeholder repair ('Checklist Team Card' -> Team Name + TC)
        if _is_placeholder_team_checklist_name(p_clean):
            p_clean = format_checklist_team_card_player(p_clean, t_clean)
            if p_clean and not re.search(r"\bTC\b", a_clean, re.IGNORECASE):
                a_clean = f"{a_clean}, TC".strip(", ")

        # General League Leaders repair
        if re.search(r"\bLL\b", a_clean, re.IGNORECASE) or _is_league_leaders_title(p_clean):
            if not re.search(r"\bLL\b", a_clean, re.IGNORECASE):
                a_clean = format_attributes_column(
                    list(dict.fromkeys([t.strip() for t in re.sub(r"\[[^\]]*\]", "", a_clean).split(",") if t.strip()] + ["LL"])),
                    paren_players=bracket_players,
                )
            if not p_clean or p_clean.upper() in ("NO TEAM", "UNKNOWN", "UNKNOWN PLAYER"):
                p_clean = f"League Leaders ({bracket_players})" if bracket_players else f"League Leaders #{cn_v}"

        # General Combo Player Card repair (never let CPC be tagged TC or overwritten with Team Name)
        if re.search(r"\bCPC\b", a_clean, re.IGNORECASE):
            a_clean = re.sub(r"\bTC\b\s*,?\s*", "", a_clean).strip(" ,")
            if bracket_players and (not p_clean or norm(p_clean) == norm(t_clean) or p_clean.upper() == "NO TEAM"):
                p_clean = bracket_players.replace(" / ", "/")

        # Normalize SN99 -> #/99 and sync Print Run into Attributes
        a_norm = _normalize_attributes_string(a_clean, pr_clean)

        if p_clean != p_orig:
            stats["players_repaired"] += 1
        if a_norm != a_orig:
            stats["attrs_normalized"] += 1

        repaired_players.append(p_clean)
        repaired_teams.append(t_clean or "NO TEAM")
        repaired_prs.append(pr_clean)
        repaired_attrs.append(a_norm)

    df["Player"] = repaired_players
    df["Team"] = repaired_teams
    df["Print Run"] = repaired_prs
    df["Attributes"] = repaired_attrs

    # 5. O(N) Variation Disambiguation (keeps non-VAR row as Base, moves VAR / 2nd+ distinct CID to Variation Subset)
    key_total_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for s_v, sub_v, cn_v in zip(df["Set"], df["Subset"], df["Card Number"]):
        key_total_counts[(s_v, sub_v, cn_v)] += 1

    # Sort non-VAR rows first within each (Set, Subset, Card Number) so Base stays Base and VAR becomes Variation
    df["_is_var_sort"] = df["Attributes"].apply(lambda a: 1 if re.search(r"\b(VAR|SSP|SP)\b", str(a or "").upper()) else 0)
    df = df.sort_values(by=["_is_var_sort"], ascending=[True]).drop(columns=["_is_var_sort"]).reset_index(drop=True)

    seen_sc_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    disambiguated_subsets = []
    for s_v, sub_v, cn_v, attr_v in zip(df["Set"], df["Subset"], df["Card Number"], df["Attributes"]):
        key_sc = (s_v, sub_v, cn_v)
        seen_sc_counts[key_sc] += 1
        occ_idx = seen_sc_counts[key_sc]
        tot_for_key = key_total_counts[key_sc]
        has_var_tag = bool(re.search(r"\b(VAR|SSP)\b", str(attr_v or "").upper()))

        if tot_for_key > 1 and occ_idx > 1 and "VARIATION" not in sub_v.upper():
            if sub_v.upper() in ("BASE", "BASE SET"):
                sub_new = "Base Image Variation" if occ_idx == 2 else f"Base Image Variation #{occ_idx - 1}"
            else:
                sub_new = f"{sub_v} Variation" if occ_idx == 2 else f"{sub_v} Variation #{occ_idx - 1}"
            stats["variations_disambiguated"] += 1
            disambiguated_subsets.append(sub_new)
        elif tot_for_key > 1 and has_var_tag and "VARIATION" not in sub_v.upper():
            sub_new = "Base Image Variation" if sub_v.upper() in ("BASE", "BASE SET") else f"{sub_v} Variation"
            stats["variations_disambiguated"] += 1
            disambiguated_subsets.append(sub_new)
        else:
            disambiguated_subsets.append(sub_v)
    df["Subset"] = disambiguated_subsets

    def unique_join(series):
        seen = []
        for val in series:
            v = str(val).strip()
            if v and v not in seen:
                seen.append(v)
        real_vals = [x for x in seen if x.upper() != "NO TEAM"]
        joined_list = real_vals if real_vals else seen
        if len(joined_list) > 4:
            return joined_list[0]
        return "/".join(joined_list)

    def first_non_empty(series):
        for val in series:
            if str(val).strip() != "":
                return str(val).strip()
        return ""

    grp_sizes = df.groupby(["Set", "Subset", "Card Number"])["Player"].transform("nunique")
    normal_df = df[grp_sizes <= 4].copy()
    overflow_df = df[grp_sizes > 4].copy()

    if not overflow_df.empty:
        ov_cnums = []
        ov_counts: dict[tuple[str, str], int] = defaultdict(int)
        for s_v, sub_v, cn_v in zip(overflow_df["Set"], overflow_df["Subset"], overflow_df["Card Number"]):
            ov_counts[(s_v, sub_v)] += 1
            ov_cnums.append(f"{cn_v}-{ov_counts[(s_v, sub_v)]}")
        overflow_df["Card Number"] = ov_cnums

    combined_input = pd.concat([normal_df, overflow_df], ignore_index=True) if not overflow_df.empty else normal_df

    grouped = (
        combined_input.groupby(["Set", "Subset", "Card Number"], sort=False, as_index=False)
        .agg({
            "Player": unique_join,
            "Team": unique_join,
            "Print Run": first_non_empty,
            "Attributes": first_non_empty,
            "TCDB_CID": first_non_empty,
            "Front_Downloaded": first_non_empty,
            "Back_Downloaded": first_non_empty,
            "TCDB_Image_Status": first_non_empty,
        })
    )

    grouped = grouped[CHECKLIST_COLUMNS]
    grouped["_num_sort"] = pd.to_numeric(grouped["Card Number"], errors="coerce").fillna(999999)
    grouped = (
        grouped.sort_values(by=["_num_sort", "Card Number", "Subset", "Player"])
        .drop(columns=["_num_sort"])
        .reset_index(drop=True)
    )
    return grouped


def _merge_set_checklist_into_master(set_df: pd.DataFrame, checklist_set_name: str, replace_set_cleanly: bool = True):
    if set_df is None or set_df.empty:
        return
    ensure_directories()
    checklist_set_name = canonicalize_checklist_set_title(checklist_set_name)
    set_df = set_df.copy()
    set_df["Set"] = checklist_set_name
    for col in CHECKLIST_COLUMNS:
        if col not in set_df.columns:
            set_df[col] = ""
    set_csv_path = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(checklist_set_name)}.csv"
    set_df = set_df[CHECKLIST_COLUMNS]
    with interprocess_file_lock(set_csv_path.with_suffix(".csv.lock")):
        atomic_write_bytes(
            set_csv_path,
            lambda tmp_p: set_df.to_csv(tmp_p, index=False, encoding="utf-8-sig"),
        )

    with interprocess_file_lock(CHECKLIST_PATH.with_suffix(".csv.lock")):
        merged_master = None
        if CHECKLIST_PATH.exists() and CHECKLIST_PATH.stat().st_size > 0:
            master_df = None
            last_read_err = None
            for attempt in range(4):
                try:
                    master_df = pd.read_csv(CHECKLIST_PATH, dtype=str, keep_default_na=False)
                    break
                except Exception as read_err:
                    last_read_err = read_err
                    time.sleep(0.08 * (attempt + 1))

            if master_df is None and CHECKLIST_BACKUP_PATH.exists() and CHECKLIST_BACKUP_PATH.stat().st_size > 0:
                try:
                    master_df = pd.read_csv(CHECKLIST_BACKUP_PATH, dtype=str, keep_default_na=False)
                    log_msg(f"  [!] Master_Checklist.csv read locked ({last_read_err}); recovered other sets from Master_Checklist_Backup.csv.")
                except Exception:
                    master_df = None

            if master_df is None:
                # Never wipe Master_Checklist.csv with a single set on transient read/lock error.
                # Try safe rebuild from all Set_Checklists/*.csv; abort master write if any other set CSV fails to load.
                rebuilt_parts = []
                rebuild_ok = True
                for other_csv in sorted(SET_CHECKLISTS_DIR.glob("*.csv")):
                    if other_csv.resolve() == set_csv_path.resolve():
                        continue
                    try:
                        part_df = pd.read_csv(other_csv, dtype=str, keep_default_na=False)
                        for col in CHECKLIST_COLUMNS:
                            if col not in part_df.columns:
                                part_df[col] = ""
                        part_df["Set"] = part_df["Set"].map(canonicalize_checklist_set_title)
                        part_df = part_df[part_df["Set"] != checklist_set_name][CHECKLIST_COLUMNS]
                        if not part_df.empty:
                            rebuilt_parts.append(part_df)
                    except Exception:
                        rebuild_ok = False
                        break
                if rebuild_ok:
                    rebuilt_parts.append(set_df)
                    merged_master = pd.concat(rebuilt_parts, ignore_index=True)
                    log_msg(f"  [!] Rebuilt Master_Checklist.csv safely from {len(rebuilt_parts)} set checklist CSV(s) after transient read error ({last_read_err}).")
                else:
                    log_msg(f"  [!] Skipped Master_Checklist.csv overwrite to prevent data loss (transient read error: {last_read_err}). Set CSV saved safely: {set_csv_path.name}")
                    return
            else:
                for col in CHECKLIST_COLUMNS:
                    if col not in master_df.columns:
                        master_df[col] = ""
                master_df["Set"] = master_df["Set"].map(canonicalize_checklist_set_title)
                other_sets_df = master_df[master_df["Set"] != checklist_set_name][CHECKLIST_COLUMNS].copy()
                merged_master = pd.concat([other_sets_df, set_df], ignore_index=True) if not other_sets_df.empty else set_df
        else:
            merged_master = set_df

        atomic_write_bytes(
            CHECKLIST_PATH,
            lambda tmp_p: merged_master[CHECKLIST_COLUMNS].to_csv(tmp_p, index=False, encoding="utf-8-sig"),
        )
        try:
            atomic_write_bytes(
                CHECKLIST_BACKUP_PATH,
                lambda tmp_p: shutil.copy2(CHECKLIST_PATH, tmp_p),
            )
        except Exception:
            pass


def _update_catalog_from_parsed_rows(
    catalog: dict,
    checklist_set_name: str,
    parsed_rows: list[dict],
):
    """
    Populates `<set_folder>_catalog.json` with complete card metadata (`card_number`, `player`,
    `team`, `print_run`, `attributes`, `url_rep_front`, `url_std_front`, `url_rep_back`, `url_std_back`,
    `front_file`, `back_file`) so `migrate_set_library.py` and `mode_download_all_catalog_images()`
    have 100% accurate metadata for every `TCDB_CID`.
    """
    for r in parsed_rows:
        cid = str(r.get("TCDB_CID") or "").strip()
        if not cid or cid == "0":
            continue
        sub_name = str(r.get("Subset") or "Base").strip() or "Base"
        cnum = str(r.get("Card Number") or "0").strip().lstrip("#")
        plr = str(r.get("Player") or "Unknown Player").strip()

        if sub_name not in catalog or not isinstance(catalog[sub_name], dict):
            catalog[sub_name] = {}

        f_fname, b_fname = build_template_image_filenames(checklist_set_name, sub_name, cnum, plr, cid)
        f_thumb = str(r.get("_front_thumb") or "").strip()
        b_thumb = str(r.get("_back_thumb") or "").strip()
        f_urls = transform_thumb_to_large_urls(f_thumb, "Fr") if f_thumb else {}
        b_urls = transform_thumb_to_large_urls(b_thumb, "Bk") if b_thumb else {}
        f_hint = str(r.get("_front_tier_hint") or ("R" if "rep" in f_thumb.lower() else ("S" if f_thumb else ""))).strip()
        b_hint = str(r.get("_back_tier_hint") or ("R" if "rep" in b_thumb.lower() else ("S" if b_thumb else ""))).strip()

        prev_entry = catalog[sub_name].get(cid, {})
        if not isinstance(prev_entry, dict):
            prev_entry = {}

        catalog[sub_name][cid] = {
            "cid": cid,
            "card_number": cnum,
            "player": plr,
            "team": str(r.get("Team") or "").strip(),
            "print_run": str(r.get("Print Run") or "").strip(),
            "attributes": str(r.get("Attributes") or "").strip(),
            "front_file": f_fname,
            "back_file": b_fname,
            "url_rep_front": f_urls.get("rep", prev_entry.get("url_rep_front", "")),
            "url_std_front": f_urls.get("std", prev_entry.get("url_std_front", "")),
            "url_rep_back": b_urls.get("rep", prev_entry.get("url_rep_back", "")),
            "url_std_back": b_urls.get("std", prev_entry.get("url_std_back", "")),
            "front_thumb": f_thumb or prev_entry.get("front_thumb", ""),
            "back_thumb": b_thumb or prev_entry.get("back_thumb", ""),
            "front_tier_hint": f_hint or prev_entry.get("front_tier_hint", ""),
            "back_tier_hint": b_hint or prev_entry.get("back_tier_hint", ""),
            "referer": str(r.get("_referer") or prev_entry.get("referer", "")),
            "subset_url": str(r.get("_subset_url") or r.get("_referer") or prev_entry.get("subset_url", "")),
            "page_num": int(r.get("_page_num") or prev_entry.get("page_num") or 1),
            "image_source": str(r.get("_image_source") or prev_entry.get("image_source") or "parsed"),
            "front": prev_entry.get("front"),
            "back": prev_entry.get("back"),
        }


def _extract_total_cards_from_checklist_soup(soup: BeautifulSoup, page1_rows_count: int, max_pages: int) -> int:
    """Extracts the exact total card count of a subset from TCDB's Checklist.cfm Page 1 HTML."""
    if max_pages <= 1:
        return max(0, int(page1_rows_count))
    try:
        txt = soup.get_text(" ", strip=True)
        for pat in (
            r"(?:showing|cards?)\s+1\s*[-–to]+\s*\d+\s+of\s+([\d,]+)",
            r"\b1\s*[-–]\s*\d+\s+of\s+([\d,]+)\b",
            r"\b([\d,]+)\s+cards?\s+in\s+(?:this\s+)?(?:set|checklist)\b",
            r"\bTotal\s+Cards?\s*:\s*([\d,]+)\b",
        ):
            m = re.search(pat, txt, re.IGNORECASE)
            if m:
                val = int(m.group(1).replace(",", ""))
                if page1_rows_count <= val <= max_pages * max(120, page1_rows_count + 20):
                    return val
    except Exception:
        pass
    per_page = max(1, int(page1_rows_count or 100))
    return (max_pages - 1) * per_page + max(1, per_page // 2)


_BASE_PARALLEL_HINT_KEYWORDS = (
    "foil", "gold", "silver", "blue", "red", "green", "orange", "purple", "pink", "black",
    "platinum", "aqua", "yellow", "camo", "rainbow", "sandglitter", "holo", "diamante",
    "vintage stock", "clear", "holiday", "true photo", "variation", "variations",
    "printing plate", "independence day", "mother's day", "father's day", "memorial day",
    "spring training", "golden mirror", "first card", "crackle", "confetti", "refractor",
    "fractor", "prizm", "chrome", "sepia", "wave", "lava", "shimmer", "mojo", "ice",
    "sparkle", "mini", "wood", "canvas", "acetate", "glossy", "tiffany", "parallel",
    "team color", "companion", "superfractor", "foilfractor",
)
_STANDALONE_INSERT_EXCL_KEYWORDS = (
    "autograph", "relic", "patch", "jersey", "memorabilia", "all aces", "home field",
    "heavy lumber", "stars of mlb", "greatest hits", "call to the hall", "topps now",
    "first pitch", "training grounds", "big ticket",
)


def _is_likely_base_parallel_name(subset_name: str) -> bool:
    s_low = str(subset_name or "").strip().lower()
    if not s_low or s_low in ("base", "base set"):
        return False
    if any(ex in s_low for ex in _STANDALONE_INSERT_EXCL_KEYWORDS):
        return False
    return s_low.startswith("base ") or any(kw in s_low for kw in _BASE_PARALLEL_HINT_KEYWORDS)


def _dedupe_physical_parent_cards(rows: list[dict], sort_by_cid: bool = False) -> list[dict]:
    """Deduplicates parent rows to 1 entry per physical TCDB_CID (keeping multiline/LL cards 1-to-1)."""
    deduped: list[dict] = []
    seen_cids: set[str] = set()
    for r in rows or []:
        cid_s = normalize_numeric_tcdb_cid(r.get("TCDB_CID", ""))
        if not cid_s or cid_s == "0" or not cid_s.isdigit():
            continue
        if cid_s in seen_cids:
            continue
        seen_cids.add(cid_s)
        deduped.append(r)
    if sort_by_cid and deduped:
        deduped.sort(key=lambda r: int(normalize_numeric_tcdb_cid(r.get("TCDB_CID", "")) or 0))
    return deduped


def _resolve_parallel_parent_subset(
    subset_label: str,
    parent_cards_by_key: dict[str, tuple[str, list[dict]]],
    expected_cards: int = 0,
) -> tuple[Optional[str], list[dict]]:
    """
    Resolves a candidate parallel subset to its scraped/local parent subset
    (covering both Base parallels and Insert parallels).
    """
    cand_norm = normalize_subset_name_for_diff(subset_label)
    cand_canon = canonical_subset_key(subset_label)
    if cand_norm == "base":
        return None, []

    best_insert: Optional[tuple[int, str, list[dict]]] = None
    for p_canon, (p_disp, p_cards) in parent_cards_by_key.items():
        if p_canon == cand_canon or len(p_cards) < 3:
            continue
        p_norm = normalize_subset_name_for_diff(p_disp)
        if not p_norm or p_norm == "base":
            continue
        if cand_norm.startswith(p_norm + " ") and cand_norm[len(p_norm) + 1:].strip():
            if best_insert is None or len(p_norm) > best_insert[0]:
                best_insert = (len(p_norm), p_disp, p_cards)
    if best_insert is not None:
        return best_insert[1], best_insert[2]

    base_entry = parent_cards_by_key.get(canonical_subset_key("Base"))
    if base_entry and len(base_entry[1]) >= 3:
        if expected_cards == len(base_entry[1]) or expected_cards <= 0 or _is_likely_base_parallel_name(subset_label):
            return base_entry[0], base_entry[1]

    return None, []


def _try_strict_cid_interpolation(
    resolved_subset: str,
    base_chk_url: str,
    rows_p1: list[dict],
    rows_last: list[dict],
    parent_cards: list[dict],
    page_size: int,
    existing_local_by_cid: Optional[dict[str, dict]] = None,
) -> tuple[Optional[list[dict]], str, str]:
    """
    Validates strict contiguity & boundary order against `parent_cards` and synthesizes
    middle rows if all guardrails pass. Returns `(rows_or_None, reason_code, detail)`.
    """
    n_parent = len(parent_cards)
    if n_parent < 3 or len(rows_p1) < 2 or len(rows_last) < 2 or (len(rows_p1) + len(rows_last)) >= n_parent:
        return None, "cid_gap", f"insufficient boundary rows vs count={n_parent}"

    cids_p1: list[int] = []
    for r in rows_p1:
        c_s = normalize_numeric_tcdb_cid(r.get("TCDB_CID", ""))
        if not c_s or not c_s.isdigit() or int(c_s) <= 0:
            return None, "cid_gap", f"non-numeric CID vs count={n_parent}"
        cids_p1.append(int(c_s))

    cids_last: list[int] = []
    for r in rows_last:
        c_s = normalize_numeric_tcdb_cid(r.get("TCDB_CID", ""))
        if not c_s or not c_s.isdigit() or int(c_s) <= 0:
            return None, "cid_gap", f"non-numeric CID vs count={n_parent}"
        cids_last.append(int(c_s))

    first_cid = cids_p1[0]
    last_cid = cids_last[-1]
    span = last_cid - first_cid + 1

    # Guardrail 4: Page 1 and Last Page rows themselves are strictly monotonic
    if not (
        all(cids_p1[i] == cids_p1[i - 1] + 1 for i in range(1, len(cids_p1)))
        and all(cids_last[i] == cids_last[i - 1] + 1 for i in range(1, len(cids_last)))
    ):
        return None, "cid_gap", f"span={span} vs count={n_parent}"

    # Guardrail 1: Zero CID gaps across entire subset
    if span != n_parent:
        return None, "cid_gap", f"span={span} vs count={n_parent}"

    # Guardrails 2 & 3: Boundary card numbers & second/penultimate CID spot checks
    def _norm_cn(row: dict) -> str:
        return str(row.get("Card Number") or "").strip().lstrip("#").upper()

    if not (
        _norm_cn(rows_p1[0]) == _norm_cn(parent_cards[0])
        and _norm_cn(rows_last[-1]) == _norm_cn(parent_cards[-1])
        and cids_p1[1] == first_cid + 1
        and _norm_cn(rows_p1[1]) == _norm_cn(parent_cards[1])
        and cids_last[-2] == last_cid - 1
        and _norm_cn(rows_last[-2]) == _norm_cn(parent_cards[-2])
    ):
        return None, "order_mismatch", "boundary card numbers differ from parent"

    boundary_prs = {
        str(r.get("Print Run") or "").strip()
        for r in (rows_p1 + rows_last)
        if str(r.get("Print Run") or "").strip()
    }
    uniform_pr = next(iter(boundary_prs)) if len(boundary_prs) == 1 else ""
    sep = "&" if "?" in base_chk_url else "?"
    local_map = existing_local_by_cid or {}

    middle_rows: list[dict] = []
    for idx in range(len(rows_p1), n_parent - len(rows_last)):
        p_row = parent_cards[idx]
        cid_s = str(first_cid + idx)
        pg_num = (idx // max(1, page_size)) + 1
        ref_u = f"{base_chk_url}{sep}PageIndex={pg_num}"
        prev_loc = local_map.get(cid_s) or {}
        front_dl = str(prev_loc.get("Front_Downloaded") or "").strip() or "No"
        back_dl = str(prev_loc.get("Back_Downloaded") or "").strip() or "No"
        img_stat = str(prev_loc.get("TCDB_Image_Status") or "").strip() or "Interpolated (Unchecked)"

        middle_rows.append({
            "Subset": resolved_subset,
            "Card Number": str(p_row.get("Card Number") or "").strip().lstrip("#"),
            "Player": str(p_row.get("Player") or "").strip(),
            "Team": str(p_row.get("Team") or "").strip(),
            "Print Run": uniform_pr or str(p_row.get("Print Run") or "").strip(),
            "Attributes": str(p_row.get("Attributes") or "").strip(),
            "TCDB_CID": cid_s,
            "Front_Downloaded": front_dl,
            "Back_Downloaded": back_dl,
            "TCDB_Image_Status": img_stat,
            "_front_thumb": "",
            "_back_thumb": "",
            "_front_tier_hint": "",
            "_back_tier_hint": "",
            "_referer": ref_u,
            "_subset_url": base_chk_url,
            "_page_num": pg_num,
            "_image_source": "interpolated",
        })

    combined = list(rows_p1) + middle_rows + list(rows_last)
    return combined, "interpolated", f"{n_parent} cards, CID {first_cid}..{last_cid}"


def _scrape_tcdb_subset_checklist_pages(
    req_session,
    base_chk_url: str,
    subset_name: str,
    checklist_set_name: str = "",
    card_callback: Optional[Callable[[dict], None]] = None,
    page_info_callback: Optional[Callable[[int, int, int], None]] = None,
    prefetched_page1_html: Optional[str] = None,
    known_subset_total: int = 0,
    start_page: int = 1,
    parent_cards: Optional[list[dict]] = None,
    existing_local_by_cid: Optional[dict[str, dict]] = None,
    interpolation_stats_out: Optional[dict] = None,
) -> list[dict]:
    all_rows = []
    page_idx = max(1, int(start_page))
    est_max_pages = 1
    hard_max_pages = 200
    seen_page_cids: set[str] = set()
    prefetched_pages: dict[int, str] = {}
    resolved_subset = clean_tcdb_subset_title(subset_name, checklist_set_name=checklist_set_name) or subset_name

    can_interpolate = bool(parent_cards and len(parent_cards) >= 3 and page_idx == 1)
    if can_interpolate and known_subset_total > 0 and known_subset_total != len(parent_cards):
        log_msg(f"      [FALLBACK: count_mismatch] {resolved_subset} (parallel={known_subset_total} vs parent={len(parent_cards)})")
        if isinstance(interpolation_stats_out, dict):
            interpolation_stats_out["reason"] = "count_mismatch"
        can_interpolate = False

    while page_idx <= hard_max_pages:
        page_url = (
            base_chk_url
            if page_idx == 1
            else f"{base_chk_url}{'&' if '?' in base_chk_url else '?'}PageIndex={page_idx}"
        )
        if page_idx == 1 and prefetched_page1_html:
            html_body = prefetched_page1_html
            log_msg(f"      [Cache Hit] Reusing pre-scanned Page 1 HTML for '{resolved_subset}' -> {page_url}")
        elif page_idx in prefetched_pages:
            html_body = prefetched_pages.pop(page_idx)
            log_msg(f"      [Cache Hit] Reusing pre-fetched Page {page_idx} HTML for '{resolved_subset}' -> {page_url}")
        else:
            log_msg(f"      [HTTP GET] Subset '{resolved_subset}' Page {page_idx}/{max(est_max_pages, page_idx)} -> {page_url}")
            res = safe_get(req_session, page_url, silent_404=True)
            if not res or (page_idx > 1 and hasattr(res, "url") and res.url and "PageIndex" not in str(res.url)):
                log_msg(f"      [Page Stop] End of pagination for '{resolved_subset}' at page {page_idx}.")
                break
            html_body = decode_html_response(res)

        soup = BeautifulSoup(html_body, "html.parser")
        if page_idx == 1 and (not resolved_subset or resolved_subset.lower() in ("insert", "inserts", "parallel")):
            hdr_sub = _extract_subset_title_from_checklist_soup(soup, checklist_set_name=checklist_set_name)
            if hdr_sub:
                resolved_subset = hdr_sub

        # Parse pagination links on EVERY page: treat Page 1's max_pages strictly as an
        # ETA/progress hint so truncated TCDB pagination bars never cut off large subsets early.
        detected_link_max = page_idx
        has_next_page_link = False
        for a_p in soup.find_all("a", href=re.compile(r"PageIndex=(\d+)", re.IGNORECASE)):
            href_p = str(a_p.get("href", ""))
            m_p = re.search(r"PageIndex=(\d+)", href_p, re.IGNORECASE)
            if m_p:
                p_num_link = int(m_p.group(1))
                detected_link_max = max(detected_link_max, p_num_link)
                txt_p = trim_clean(a_p.get_text(" ", strip=True)).lower()
                if p_num_link == page_idx + 1 or txt_p in ("next", ">", "»", "next >", "next »"):
                    has_next_page_link = True
        est_max_pages = max(est_max_pages, min(hard_max_pages, detected_link_max))

        rows_p = parse_tcdb_checklist_table_rows(
            soup,
            subset_name=resolved_subset or "Base",
            current_url=page_url,
            page_num=page_idx,
        )
        if not rows_p:
            log_msg(f"      [Parse] 0 card rows found on '{resolved_subset}' Page {page_idx}; stopping subset.")
            break

        # Guard against TCDB returning the last page repeatedly when PageIndex exceeds bounds
        page_cids = {str(r.get("TCDB_CID") or "").strip() for r in rows_p if str(r.get("TCDB_CID") or "").strip()}
        if page_idx > 1 and page_cids and page_cids.issubset(seen_page_cids):
            log_msg(f"      [Page Stop] Duplicate card rows detected on '{resolved_subset}' Page {page_idx}; stopping subset.")
            break
        seen_page_cids.update(page_cids)

        for r_item in rows_p:
            r_item["_subset_url"] = base_chk_url

        if can_interpolate and page_idx == 1:
            if est_max_pages <= 1 and not has_next_page_link:
                can_interpolate = False
            else:
                page_size = len(rows_p)
                expected_last_page = (len(parent_cards) + page_size - 1) // page_size
                target_last_page = max(est_max_pages, expected_last_page)
                reported_total = (
                    known_subset_total
                    if known_subset_total > 0
                    else _extract_total_cards_from_checklist_soup(soup, len(rows_p), target_last_page)
                )
                if reported_total != len(parent_cards):
                    log_msg(f"      [FALLBACK: count_mismatch] {resolved_subset} (parallel={reported_total} vs parent={len(parent_cards)})")
                    if isinstance(interpolation_stats_out, dict):
                        interpolation_stats_out["reason"] = "count_mismatch"
                elif target_last_page >= 3:
                    last_page_url = f"{base_chk_url}{'&' if '?' in base_chk_url else '?'}PageIndex={target_last_page}"
                    log_msg(f"      [HTTP GET] Subset '{resolved_subset}' Last Page {target_last_page}/{target_last_page} (interpolation probe) -> {last_page_url}")
                    res_last = safe_get(req_session, last_page_url, silent_404=True)
                    if res_last and (not hasattr(res_last, "url") or not res_last.url or "PageIndex" in str(res_last.url)):
                        last_html = decode_html_response(res_last)
                        prefetched_pages[target_last_page] = last_html
                        soup_last = BeautifulSoup(last_html, "html.parser")
                        last_has_next = False
                        for a_lp in soup_last.find_all("a", href=re.compile(r"PageIndex=(\d+)", re.IGNORECASE)):
                            m_lp = re.search(r"PageIndex=(\d+)", str(a_lp.get("href", "")), re.IGNORECASE)
                            if m_lp:
                                lp_num = int(m_lp.group(1))
                                lp_txt = trim_clean(a_lp.get_text(" ", strip=True)).lower()
                                if lp_num == target_last_page + 1 or lp_txt in ("next", ">", "»", "next >", "next »"):
                                    last_has_next = True
                                    break
                        rows_last = parse_tcdb_checklist_table_rows(
                            soup_last,
                            subset_name=resolved_subset or "Base",
                            current_url=last_page_url,
                            page_num=target_last_page,
                        )
                        for r_item in rows_last:
                            r_item["_subset_url"] = base_chk_url

                        if rows_last and not last_has_next:
                            combined, interp_reason, interp_detail = _try_strict_cid_interpolation(
                                resolved_subset or "Base",
                                base_chk_url,
                                rows_p,
                                rows_last,
                                parent_cards,
                                page_size,
                                existing_local_by_cid=existing_local_by_cid,
                            )
                            if combined is not None:
                                skipped_pages = max(0, target_last_page - 2)
                                if page_info_callback is not None:
                                    page_info_callback(1, target_last_page, len(combined))
                                log_msg(
                                    f"      [INTERPOLATED] {resolved_subset} "
                                    f"({len(combined)} cards, CID {combined[0]['TCDB_CID']}..{combined[-1]['TCDB_CID']}, "
                                    f"skipped {skipped_pages} middle page(s))"
                                )
                                if card_callback is not None:
                                    for c_row in combined:
                                        card_callback(c_row)
                                if isinstance(interpolation_stats_out, dict):
                                    interpolation_stats_out["interpolated"] = True
                                    interpolation_stats_out["pages_saved"] = skipped_pages
                                    interpolation_stats_out["reason"] = "interpolated"
                                return combined
                            else:
                                log_msg(f"      [FALLBACK: {interp_reason}] {resolved_subset} ({interp_detail})")
                                if isinstance(interpolation_stats_out, dict):
                                    interpolation_stats_out["reason"] = interp_reason
                        else:
                            log_msg(f"      [FALLBACK: cid_gap] {resolved_subset} (last page {target_last_page} invalid or has next page)")
                            if isinstance(interpolation_stats_out, dict):
                                interpolation_stats_out["reason"] = "cid_gap"
                    else:
                        log_msg(f"      [FALLBACK: cid_gap] {resolved_subset} (last page {target_last_page} fetch failed)")
                        if isinstance(interpolation_stats_out, dict):
                            interpolation_stats_out["reason"] = "cid_gap"
                can_interpolate = False

        if page_info_callback is not None:
            if page_idx == 1:
                est_tot = _extract_total_cards_from_checklist_soup(soup, len(rows_p), est_max_pages)
                if est_max_pages > 1 and known_subset_total >= len(rows_p):
                    est_tot = known_subset_total
                page_info_callback(page_idx, est_max_pages, max(len(rows_p), est_tot))
            elif page_idx >= est_max_pages and not has_next_page_link:
                page_info_callback(page_idx, page_idx, len(all_rows) + len(rows_p))

        log_msg(f"      [Parse] '{resolved_subset}' Page {page_idx}/{max(est_max_pages, page_idx)}: extracted {len(rows_p)} card(s).")
        if card_callback is not None:
            for c_row in rows_p:
                card_callback(c_row)
        all_rows.extend(rows_p)

        if page_idx >= est_max_pages and not has_next_page_link:
            break
        page_idx += 1

    return all_rows


def _extract_insert_card_count_from_anchor(a_tag) -> int:
    """Extracts the exact card count displayed next to an insert/parallel link on TCDB's Inserts.cfm."""
    try:
        container = a_tag.find_parent("tr") or a_tag.find_parent("li") or a_tag.parent
        if container is None:
            return 0
        row_txt = trim_clean(container.get_text(" ", strip=True))
        m_cards = re.search(r"\b([\d,]{1,6})\s*cards?\b", row_txt, re.IGNORECASE)
        if m_cards:
            val = int(m_cards.group(1).replace(",", ""))
            if 1 <= val <= 50000:
                return val
        if container.name == "tr":
            tds = [trim_clean(td.get_text(" ", strip=True)) for td in container.find_all("td")]
            for cell_txt in reversed(tds):
                if re.fullmatch(r"[\d,]{1,6}", cell_txt):
                    val = int(cell_txt.replace(",", ""))
                    if 1 <= val <= 25000 and not (1950 <= val <= 2035):
                        return val
        else:
            for m_p in re.finditer(r"\(([\d,]{1,5})\)", row_txt):
                val = int(m_p.group(1).replace(",", ""))
                if 1 <= val <= 25000 and not (1950 <= val <= 2035):
                    return val
    except Exception:
        pass
    return 0


def _fetch_inserts_index_with_counts(
    req_session,
    inserts_url: str,
    checklist_set_name: str,
) -> tuple[dict[str, tuple[str, str]], dict[str, int]]:
    """
    Fetches TCDB's `Inserts.cfm` index and returns:
      - `insert_by_sid`: `{sid: (checklist_url, clean_subset_name)}`
      - `counts_by_sid`: `{sid: exact_card_count_from_tcdb_table}`
    """
    sid_m = re.search(r"/sid/(\d+)", inserts_url)
    master_sid = sid_m.group(1) if sid_m else None
    insert_by_sid: dict[str, tuple[str, str]] = {}
    counts_by_sid: dict[str, int] = {}
    page_num = 1
    max_ins_pages = 50
    while page_num <= max_ins_pages:
        idx_url = inserts_url if page_num == 1 else f"{inserts_url}{'&' if '?' in inserts_url else '?'}PageIndex={page_num}"
        log_msg(f"  [Inserts Index] Fetching page {page_num}/{max_ins_pages} -> {idx_url}")
        res = safe_get(req_session, idx_url, silent_404=True)
        if not res or (page_num > 1 and hasattr(res, "url") and res.url and "PageIndex" not in str(res.url)):
            break
        soup = BeautifulSoup(decode_html_response(res), "html.parser")
        if page_num == 1:
            detected_p = 1
            for a_p in soup.find_all("a", href=re.compile(r"PageIndex=(\d+)", re.IGNORECASE)):
                mp = re.search(r"PageIndex=(\d+)", a_p.get("href", ""), re.IGNORECASE)
                if mp:
                    detected_p = max(detected_p, int(mp.group(1)))
            max_ins_pages = min(50, detected_p)
        found_on_p = 0
        for a in soup.find_all("a", href=True):
            href_str = str(a.get("href", ""))
            if _is_college_section_heading(a):
                continue
            m = re.search(r"/(?:ViewSet|Checklist)\.cfm/sid/(\d+)(?:/([^/?#]+))?", href_str, re.IGNORECASE)
            if m:
                sid, sub_path = m.group(1), m.group(2) or ""
                if sid == master_sid:
                    continue
                full_u = f"{BASE_URL}/Checklist.cfm/sid/{sid}/{sub_path}" if sub_path else f"{BASE_URL}/Checklist.cfm/sid/{sid}"
                t_name = clean_tcdb_subset_title(trim_clean(a.get_text(" ", strip=True)), checklist_set_name=checklist_set_name, url_slug=sub_path)
                card_cnt = _extract_insert_card_count_from_anchor(a)
                if card_cnt > 0 and card_cnt > counts_by_sid.get(sid, 0):
                    counts_by_sid[sid] = card_cnt
                if sid not in insert_by_sid:
                    insert_by_sid[sid] = (full_u, t_name)
                    found_on_p += 1
                else:
                    prev_u, prev_name = insert_by_sid[sid]
                    best_u = full_u if sub_path else prev_u
                    best_name = t_name if (t_name and (not prev_name or prev_name.lower() == "insert" or len(t_name) > len(prev_name))) else prev_name
                    insert_by_sid[sid] = (best_u, best_name)
        if found_on_p == 0 and page_num > 1:
            break
        page_num += 1
    return insert_by_sid, counts_by_sid


def _fetch_inserts_index_for_set(req_session, inserts_url: str, checklist_set_name: str) -> dict[str, tuple[str, str]]:
    ins_map, _ = _fetch_inserts_index_with_counts(req_session, inserts_url, checklist_set_name)
    return ins_map


def _inspect_local_set_card_stats(folder_name: str, chk_title: str) -> dict:
    """
    Fast local inspection of a set's existing checklist CSV, catalog JSON, and cached `set_stats`
    to determine total cards, Base card count, per-subset card counts, and already-downloaded images.
    """
    learner = get_rate_learner()
    cached = learner.get_set_stats(sanitize_filename_part(chk_title)) or learner.get_set_stats(folder_name) or {}

    info = {
        "total_cards": int(cached.get("total_cards", 0) or 0),
        "base_cards": int(cached.get("base_cards", 0) or 0),
        "total_subsets": int(cached.get("total_subsets", 0) or 0),
        "imaged_cards_on_tcdb": int(cached.get("imaged_cards_on_tcdb", 0) or 0),
        "fronts_downloaded": int(cached.get("fronts_downloaded", 0) or 0),
        "backs_downloaded": int(cached.get("backs_downloaded", 0) or 0),
        "subset_card_counts": dict(cached.get("subset_card_counts") or {}),
        "has_complete_local_checklist": False,
    }

    csv_p = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(chk_title)}.csv"
    if not csv_p.exists():
        alt_p = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(folder_name)}.csv"
        if alt_p.exists():
            csv_p = alt_p

    if csv_p.exists():
        try:
            df = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
            if not df.empty and "Subset" in df.columns:
                sub_vc = {str(k).strip() or "Base": int(v) for k, v in df["Subset"].value_counts().items()}
                base_c = sum(v for k, v in sub_vc.items() if k.upper() in ("BASE", "BASE SET"))
                f_dl = int((df.get("Front_Downloaded", pd.Series(dtype=str)).astype(str).str.lower() == "yes").sum())
                b_dl = int((df.get("Back_Downloaded", pd.Series(dtype=str)).astype(str).str.lower() == "yes").sum())
                im_tcdb = int(df.get("TCDB_Image_Status", pd.Series(dtype=str)).astype(str).str.contains("Front", case=False, na=False).sum())
                info.update({
                    "total_cards": len(df),
                    "base_cards": base_c,
                    "total_subsets": len(sub_vc),
                    "imaged_cards_on_tcdb": im_tcdb,
                    "fronts_downloaded": f_dl,
                    "backs_downloaded": b_dl,
                    "subset_card_counts": sub_vc,
                })
        except Exception:
            pass

    # Fallback to catalog JSON if CSV missing/shorter
    cat = load_catalog(folder_name)
    if cat:
        cat_subs = {str(k): len(v) for k, v in cat.items() if isinstance(v, dict) and len(v) > 0}
        cat_total = sum(cat_subs.values())
        if cat_total > info["total_cards"]:
            info["total_cards"] = cat_total
            info["total_subsets"] = len(cat_subs)
            info["base_cards"] = sum(v for k, v in cat_subs.items() if k.upper() in ("BASE", "BASE SET"))
            info["subset_card_counts"] = cat_subs

    # Consider a local checklist trustworthy if it has >= 50 cards, Base cards present, and >= 2 subsets
    if info["total_cards"] >= 50 and info["base_cards"] > 0 and info["total_subsets"] >= 2:
        info["has_complete_local_checklist"] = True

    return info


def prescan_queue_card_metrics(
    req_session,
    queue_items: list[tuple[str, str]],
    mode_key: str = "checklist_and_images",
) -> dict:
    """
    Hybrid Card-Count Pre-Scanner for Super-Accurate Tier-1 & Tier-2 Progress Bars & Learning ETAs:
      1. Reads cached/local Set_Checklists CSV + Catalog JSON + Disk downloaded counts first.
      2. Whenever a set's checklist is missing or looks way short (< 50 cards, 0 Base, or <= 1 subset),
         runs the live TCDB Pre-Scraper:
           - Fetches Base Page 1 (cached in memory -> zero wasted HTTP requests!) to get exact `base_cards`.
           - Fetches `Inserts.cfm` (reused directly for the scrape!) and extracts every insert/parallel's exact card count.
      3. Persists all discovered card counts into `Cache\\System\\adaptive_rate_learner.json` (`set_stats`).
    """
    learner = get_rate_learner()
    total_cards_all = 0
    total_subsets_all = 0
    est_remaining_dl_cards_all = 0
    prefetched_inserts: dict[str, dict[str, tuple[str, str]]] = {}
    prefetched_insert_counts: dict[str, dict[str, int]] = {}
    prefetched_base_html: dict[str, str] = {}
    per_set_metrics: dict[str, dict] = {}
    summary_parts: list[str] = []

    log_msg(f"🔎 Computing card-count metrics across {len(queue_items)} queued set(s) for accurate card-based progress & ETA...")

    for s_idx, (set_url, folder_name) in enumerate(queue_items, 1):
        chk_title = canonicalize_checklist_set_title(folder_name.replace("_", " ").strip())
        local_info = _inspect_local_set_card_stats(folder_name, chk_title)

        if mode_key in ("images_only", "upgrade", "missing_back"):
            cat = load_catalog(folder_name)
            if mode_key == "images_only":
                cat_subs = {
                    str(k): sum(
                        1 for cid_k, ent in v.items()
                        if not str(cid_k).startswith("_") and isinstance(ent, dict)
                        and (ent.get("url_rep_front") or ent.get("url_std_front"))
                    )
                    for k, v in cat.items()
                    if isinstance(v, dict)
                }
                cat_subs = {k: cnt for k, cnt in cat_subs.items() if cnt > 0}
            else:
                cat_subs = {str(k): len(v) for k, v in cat.items() if isinstance(v, dict) and len(v) > 0}
            set_cards = max(1, sum(cat_subs.values()) or local_info["total_cards"])
            set_subs = max(1, len(cat_subs) or local_info["total_subsets"])
            base_c = sum(v for k, v in cat_subs.items() if k.upper() in ("BASE", "BASE SET")) or local_info["base_cards"]
            imaged_c = sum(
                1 for cards_d in cat.values() if isinstance(cards_d, dict)
                for cid_k, ent in cards_d.items()
                if not str(cid_k).startswith("_") and isinstance(ent, dict) and (ent.get("url_rep_front") or ent.get("url_std_front"))
            ) or local_info["imaged_cards_on_tcdb"]
            dl_already = local_info["fronts_downloaded"]
            rem_dl = max(0, imaged_c - dl_already)
            per_set_metrics[set_url] = {
                "total_cards": set_cards,
                "base_cards": base_c,
                "total_subsets": set_subs,
                "subset_card_counts": cat_subs or local_info["subset_card_counts"],
                "est_remaining_dl": rem_dl,
            }
            total_cards_all += set_cards
            total_subsets_all += set_subs
            est_remaining_dl_cards_all += rem_dl
            summary_parts.append(f"{chk_title}: {set_cards:,} cards ({rem_dl:,} to dl)")
            continue

        # Checklist Only / Combined Checklists + Images
        urls = _resolve_tcdb_set_urls(set_url)
        need_prescan_base = not local_info["has_complete_local_checklist"]

        base_c = local_info["base_cards"]
        if need_prescan_base:
            log_msg(f"  [Pre-Scan {s_idx}/{len(queue_items)}] Checklist missing/short for '{chk_title}' — pre-scanning Base Page 1 + Inserts...")
            res_b1 = safe_get(req_session, urls["checklist"], silent_404=True)
            if res_b1:
                b1_html = decode_html_response(res_b1)
                prefetched_base_html[set_url] = b1_html
                soup_b1 = BeautifulSoup(b1_html, "html.parser")
                det_p = 1
                for a_p in soup_b1.find_all("a", href=re.compile(r"PageIndex=(\d+)", re.IGNORECASE)):
                    mp = re.search(r"PageIndex=(\d+)", a_p.get("href", ""), re.IGNORECASE)
                    if mp:
                        det_p = max(det_p, int(mp.group(1)))
                b1_rows = parse_tcdb_checklist_table_rows(soup_b1, subset_name="Base", current_url=urls["checklist"], page_num=1)
                base_c = _extract_total_cards_from_checklist_soup(soup_b1, len(b1_rows), min(35, det_p))

        ins_map, ins_counts = _fetch_inserts_index_with_counts(req_session, urls["inserts"], chk_title)
        prefetched_inserts[set_url] = ins_map
        prefetched_insert_counts[set_url] = ins_counts

        known_sub_counts = dict(local_info["subset_card_counts"])
        if base_c > 0:
            known_sub_counts["Base"] = base_c

        # Combine exact parsed insert counts from TCDB Inserts.cfm with local CSV counts (fallback to median if missing)
        parsed_vals = [v for v in ins_counts.values() if v > 0]
        median_ins = int(sorted(parsed_vals)[len(parsed_vals) // 2]) if parsed_vals else max(25, min(150, base_c // 4 if base_c else 35))

        inserts_card_sum = 0
        for sid_k, (_, sub_lbl) in ins_map.items():
            clean_lbl = clean_tcdb_subset_title(sub_lbl, checklist_set_name=chk_title) or f"Subset_{sid_k}"
            cnt_i = ins_counts.get(sid_k) or known_sub_counts.get(clean_lbl) or median_ins
            ins_counts[sid_k] = int(cnt_i)
            known_sub_counts[clean_lbl] = int(cnt_i)
            inserts_card_sum += int(cnt_i)

        set_cards = max(1, (base_c or 300) + inserts_card_sum)
        if local_info["has_complete_local_checklist"] and local_info["total_cards"] > set_cards:
            set_cards = local_info["total_cards"]
        set_subs = 1 + len(ins_map)

        # Estimate how many cards still need image downloads using live TCDB Image_Pct when available!
        dir_pct = _get_directory_image_pct(set_url=set_url, chk_title=chk_title)
        if local_info["imaged_cards_on_tcdb"] > 0:
            est_imaged = local_info["imaged_cards_on_tcdb"]
        elif dir_pct is not None:
            est_imaged = int(round(set_cards * (dir_pct / 100.0)))
        else:
            est_imaged = int(set_cards * 0.25)
        rem_dl = max(0, est_imaged - local_info["fronts_downloaded"])

        learner.update_set_stats(
            set_key=sanitize_filename_part(chk_title),
            set_name=chk_title,
            total_cards=set_cards,
            base_cards=base_c or 300,
            total_subsets=set_subs,
            subset_card_counts=known_sub_counts,
            force_save=True,
        )

        per_set_metrics[set_url] = {
            "total_cards": set_cards,
            "base_cards": base_c or 300,
            "total_subsets": set_subs,
            "subset_card_counts": known_sub_counts,
            "est_remaining_dl": rem_dl,
        }
        total_cards_all += set_cards
        total_subsets_all += set_subs
        est_remaining_dl_cards_all += rem_dl
        src_tag = "Cached CSV" if local_info["has_complete_local_checklist"] else "Pre-Scanned"
        summary_parts.append(f"{chk_title}: {set_cards:,} cards ({set_subs} subs, {src_tag})")

        emit_progress(
            active_set_name=f"Pre-Scanning ({s_idx}/{len(queue_items)}): {chk_title}",
            set_index=s_idx,
            total_sets=len(queue_items),
            completed_cards=0,
            total_cards=max(1, total_cards_all),
            completed_subsets=0,
            total_subsets=max(1, total_subsets_all),
            sub_name="Pre-Scan Base & Insert Card Counts",
            sub_current=s_idx,
            sub_total=len(queue_items),
            current_item=f"{chk_title}: {set_cards:,} cards across {set_subs} subsets ({src_tag})",
            mode_key=mode_key,
            est_remaining_dl_cards=est_remaining_dl_cards_all,
        )

    total_cards_all = max(1, total_cards_all)
    total_subsets_all = max(1, total_subsets_all)
    log_msg(
        f"📊 Card Pre-Scan Complete: {total_cards_all:,} total cards across {total_subsets_all:,} subsets "
        f"in {len(queue_items)} set(s) ({' | '.join(summary_parts[:6])})"
    )
    return {
        "total_cards": total_cards_all,
        "total_subsets": total_subsets_all,
        "est_remaining_dl_cards": est_remaining_dl_cards_all,
        "prefetched_inserts": prefetched_inserts,
        "prefetched_insert_counts": prefetched_insert_counts,
        "prefetched_base_html": prefetched_base_html,
        "per_set_metrics": per_set_metrics,
    }


def prescan_total_subsets_for_queue(req_session, queue_items: list[tuple[str, str]], mode_key: str = "checklist_and_images") -> tuple[int, dict[str, dict[str, tuple[str, str]]]]:
    """Backwards-compatible wrapper over `prescan_queue_card_metrics`."""
    res = prescan_queue_card_metrics(req_session, queue_items, mode_key=mode_key)
    return int(res["total_subsets"]), res["prefetched_inserts"]


def scrape_tcdb_checklist_set(
    req_session,
    viewset_url: str,
    checklist_set_name: str,
    folder_name: str = "",
    include_inserts: bool = True,
    download_images_card_by_card: bool = False,
    set_dir: Optional[Path] = None,
    prefetched_inserts: Optional[dict[str, tuple[str, str]]] = None,
    prefetched_insert_counts: Optional[dict[str, int]] = None,
    prefetched_base_html: Optional[str] = None,
    progress_ctx: Optional[dict] = None,
    incremental: bool = True,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Single-Pass Unified Crawler:
    Scrapes Base Set, Variations/Errors, and all Inserts/Parallels/Autos/Relics from TCDB,
    extracting `TCDB_CID`, `TCDB_Image_Status`, and Front/Back image URLs in one pass.
    Supports incremental subset-level checkpointing, existing-CSV bootstrap, and
    catalog-driven image downloads for unchanged subsets.
    """
    urls = _resolve_tcdb_set_urls(viewset_url)
    cat_key = folder_name or sanitize_filename_part(checklist_set_name)
    catalog = load_catalog(cat_key)
    target_set_dir = set_dir or (REFERENCE_TEMPLATES_DIR / sanitize_filename_part(cat_key))
    if download_images_card_by_card:
        target_set_dir.mkdir(parents=True, exist_ok=True)

    mode_desc = "Checklist + Card-by-Card Images" if download_images_card_by_card else "Checklist + CIDs Only"
    log_msg(f"🏛️ Scraping TCDB ({mode_desc}) for '{checklist_set_name}' ({urls['checklist']})...")

    disk_cid_index = _index_existing_set_dir_by_cid(target_set_dir) if download_images_card_by_card else {}
    dead_backs = load_dead_backs_cache() if download_images_card_by_card else {}
    dead_fronts = load_dead_fronts_cache() if download_images_card_by_card else {}
    dead_backs_dirty = False
    dead_fronts_dirty = False
    img_circuit_breaker = CloudflareImageCircuitBreaker(stop_check=is_stop_requested) if download_images_card_by_card else None
    img_stats = {"front_dl": 0, "back_dl": 0, "front_skip": 0, "back_skip": 0, "no_back": 0, "back_only_skip": 0, "no_img": 0, "cards_seen": 0}
    overload_state = {"consecutive": 0}

    def _download_card_immediately(c_row: dict):
        nonlocal dead_backs_dirty, dead_fronts_dirty
        if not wait_if_paused(reason="Paused during card-by-card download"):
            raise CloudflareEdgeBlockPaused("Stopped while paused")
        img_stats["cards_seen"] += 1
        cid = str(c_row.get("TCDB_CID") or "").strip()
        sub_n = str(c_row.get("Subset") or "Base").strip() or "Base"
        cnum = str(c_row.get("Card Number") or "0").strip().lstrip("#")
        plr = str(c_row.get("Player") or "Unknown Player").strip()

        f_thumb = str(c_row.get("_front_thumb") or "").strip()
        b_thumb = str(c_row.get("_back_thumb") or "").strip()
        f_hint = str(c_row.get("_front_tier_hint") or ("R" if "rep" in f_thumb.lower() else ("S" if f_thumb else ""))).strip()
        b_hint = str(c_row.get("_back_tier_hint") or ("R" if "rep" in b_thumb.lower() else ("S" if b_thumb else ""))).strip()

        if not cid or cid == "0":
            img_stats["no_img"] += 1
            log_msg(f"        [Card #{cnum}] {plr} [{sub_n} | CID none] -> No TCDB image available")
            return
        if not f_thumb:
            if str(c_row.get("_image_source") or "") == "interpolated":
                f_fname, b_fname = build_template_image_filenames(checklist_set_name, sub_n, cnum, plr, cid)
                f_path = target_set_dir / f_fname
                b_path = target_set_dir / b_fname
                if _check_or_rename_existing_cid_file(disk_cid_index, cid, "F", f_path):
                    img_stats["front_skip"] += 1
                    c_row["Front_Downloaded"] = "Yes"
                if _check_or_rename_existing_cid_file(disk_cid_index, cid, "B", b_path):
                    img_stats["back_skip"] += 1
                    c_row["Back_Downloaded"] = "Yes"
                return
            if b_thumb:
                img_stats["back_only_skip"] += 1
                img_stats["no_img"] += 1
                log_msg(f"        [Card #{cnum}] {plr} [{sub_n} | CID {cid}] -> Skip(BackOnlyOnTCDB - No Front)")
            else:
                img_stats["no_img"] += 1
                log_msg(f"        [Card #{cnum}] {plr} [{sub_n} | CID {cid}] -> No TCDB image available")
            return

        # If TCDB now shows a front/back thumbnail for a previously dead-cached CID, evict it!
        if f_thumb and cid in dead_fronts:
            dead_fronts.pop(cid, None)
            dead_fronts_dirty = True
        if b_thumb and cid in dead_backs:
            dead_backs.pop(cid, None)
            dead_backs_dirty = True

        f_fname, b_fname = build_template_image_filenames(checklist_set_name, sub_n, cnum, plr, cid)
        f_path = target_set_dir / f_fname
        b_path = target_set_dir / b_fname

        f_urls = transform_thumb_to_large_urls(f_thumb, "Fr")
        b_urls = transform_thumb_to_large_urls(b_thumb, "Bk") if b_thumb else {"rep": "", "std": ""}
        referer = str(c_row.get("_referer") or urls["checklist"])

        if sub_n not in catalog or not isinstance(catalog[sub_n], dict):
            catalog[sub_n] = {}
        entry = catalog[sub_n].setdefault(cid, {
            "cid": cid, "card_number": cnum, "player": plr,
            "team": str(c_row.get("Team") or ""), "print_run": str(c_row.get("Print Run") or ""),
            "attributes": str(c_row.get("Attributes") or ""),
            "front_file": f_fname, "back_file": b_fname,
            "url_rep_front": f_urls.get("rep", ""), "url_std_front": f_urls.get("std", ""),
            "url_rep_back": b_urls.get("rep", ""), "url_std_back": b_urls.get("std", ""),
            "front_thumb": f_thumb, "back_thumb": b_thumb,
            "front_tier_hint": f_hint, "back_tier_hint": b_hint,
            "referer": referer, "subset_url": str(c_row.get("_subset_url") or referer),
            "page_num": int(c_row.get("_page_num") or 1),
        })
        entry["front_file"] = f_fname
        entry["back_file"] = b_fname
        entry["url_rep_front"] = f_urls.get("rep", "")
        entry["url_std_front"] = f_urls.get("std", "")
        if f_thumb:
            entry["front_thumb"] = f_thumb
            entry["front_tier_hint"] = f_hint
        if b_thumb:
            entry["url_rep_back"] = b_urls.get("rep", "")
            entry["url_std_back"] = b_urls.get("std", "")
            entry["back_thumb"] = b_thumb
            entry["back_tier_hint"] = b_hint

        q_f_winner = ""
        has_front = False
        f_out: dict = {}
        b_out: dict = {}
        existing_f_note = _check_or_rename_existing_cid_file(disk_cid_index, cid, "F", f_path)
        if existing_f_note:
            has_front = True
            img_stats["front_skip"] += 1
            c_row["Front_Downloaded"] = "Yes"
            f_note = existing_f_note
            if isinstance(entry.get("front"), dict):
                q_f_winner = str(entry["front"].get("quality") or "")
        elif cid in dead_fronts:
            img_stats["no_img"] += 1
            f_note = "Skip(DeadFrontCached)"
        else:
            q_f = _download_single_template_side(
                req_session,
                f_urls["rep"],
                f_urls["std"],
                referer,
                f_path,
                set_key=cat_key,
                thumb_url=f_thumb,
                preferred_tier=f_hint,
                outcome_out=f_out,
                circuit_breaker=img_circuit_breaker,
            )
            if q_f:
                has_front = True
                q_f_winner = q_f
                img_stats["front_dl"] += 1
                c_row["Front_Downloaded"] = "Yes"
                disk_cid_index[(cid, "F")] = f_path
                entry["front"] = {"quality": q_f, "file": f_fname}
                kb_f = f_path.stat().st_size / 1024.0 if f_path.exists() else 0.0
                f_note = f"{q_f}-Tier OK ({kb_f:.1f}KB)"
            elif f_out.get("confirmed_404"):
                dead_fronts[cid] = time.time()
                dead_fronts_dirty = True
                f_note = "Miss(404->Cached)"
            else:
                err_c = int(f_out.get("status_code", 0) or 0)
                f_note = f"Err(HTTP {err_c}-Uncached)" if err_c > 0 else "Err(Net-Uncached)"

        existing_b_note = _check_or_rename_existing_cid_file(disk_cid_index, cid, "B", b_path)
        if existing_b_note:
            img_stats["back_skip"] += 1
            c_row["Back_Downloaded"] = "Yes"
            b_note = existing_b_note
        elif not has_front:
            # Skip downloading orphan back images if the front image was missing/404
            img_stats["back_only_skip"] += 1
            b_note = "Skip(NoFrontImage)"
        elif not b_thumb:
            # Zero HTTP calls when TCDB checklist confirms no back image is uploaded!
            img_stats["no_back"] += 1
            b_note = "Skip(NoBackOnTCDB)"
        elif cid in dead_backs:
            img_stats["no_back"] += 1
            b_note = "Skip(DeadBackCached)"
        else:
            q_b = _download_single_template_side(
                req_session,
                b_urls["rep"],
                b_urls["std"],
                referer,
                b_path,
                set_key=cat_key,
                thumb_url=b_thumb,
                preferred_tier=b_hint or q_f_winner,
                outcome_out=b_out,
                circuit_breaker=img_circuit_breaker,
            )
            if q_b:
                img_stats["back_dl"] += 1
                c_row["Back_Downloaded"] = "Yes"
                disk_cid_index[(cid, "B")] = b_path
                entry["back"] = {"quality": q_b, "file": b_fname}
                kb_b = b_path.stat().st_size / 1024.0 if b_path.exists() else 0.0
                b_note = f"{q_b}-Tier OK ({kb_b:.1f}KB)"
            elif b_out.get("confirmed_404"):
                dead_backs[cid] = time.time()
                dead_backs_dirty = True
                b_note = "Miss(404->Cached)"
            else:
                err_c = int(b_out.get("status_code", 0) or 0)
                b_note = f"Err(HTTP {err_c}-Uncached)" if err_c > 0 else "Err(Net-Uncached)"

        if f_out.get("transient_overload") or b_out.get("transient_overload"):
            overload_state["consecutive"] += 1
            if overload_state["consecutive"] >= 3:
                log_msg("⏳ [Origin Overload Breather] 3 consecutive cards hit HTTP 503/timeout — resting 15s...")
                if img_circuit_breaker is not None:
                    img_circuit_breaker.interruptible_sleep(15.0, reason="503/timeout breather")
                else:
                    time.sleep(15.0)
                overload_state["consecutive"] = 0
        elif f_out.get("outcome") in ("ok", "404") or b_out.get("outcome") in ("ok", "404"):
            overload_state["consecutive"] = 0

        log_msg(f"        [Card #{cnum}] {plr} [{sub_n} | CID {cid}] -> Front: {f_note} | Back: {b_note}")

    def _download_missing_images_for_skipped_subset(sub_lbl: str) -> int:
        """Downloads any missing front/back images for an unchanged subset directly from catalog. Returns pending count attempted."""
        nonlocal dead_backs_dirty, dead_fronts_dirty
        if not download_images_card_by_card or not isinstance(catalog, dict):
            return 0
        target_sk = canonical_subset_key(sub_lbl)
        target_norm = normalize_subset_name_for_diff(sub_lbl)
        matched_sub_dicts = [
            cards_d for k_sub, cards_d in catalog.items()
            if isinstance(cards_d, dict) and (
                canonical_subset_key(str(k_sub)) == target_sk
                or normalize_subset_name_for_diff(str(k_sub)) == target_norm
            )
        ]
        pending_attempted = 0
        for cards_d in matched_sub_dicts:
            for cid, entry in cards_d.items():
                if str(cid).startswith("_") or not isinstance(entry, dict):
                    continue
                if not wait_if_paused(reason="Paused during skipped-subset image sync"):
                    raise CloudflareEdgeBlockPaused("Stopped while paused")
                cid_s = str(cid).strip()
                url_rep_f = str(entry.get("url_rep_front") or "")
                url_std_f = str(entry.get("url_std_front") or "")
                url_rep_b = str(entry.get("url_rep_back") or "")
                url_std_b = str(entry.get("url_std_back") or "")
                if not (url_rep_f or url_std_f):
                    continue
                cnum = str(entry.get("card_number") or "0").strip().lstrip("#")
                plr = str(entry.get("player") or "Unknown Player").strip()
                f_fname = str(entry.get("front_file") or "")
                b_fname = str(entry.get("back_file") or "")
                if not f_fname or not b_fname:
                    f_fname, b_fname = build_template_image_filenames(checklist_set_name, sub_lbl, cnum, plr, cid_s)
                f_path = target_set_dir / f_fname
                b_path = target_set_dir / b_fname
                referer = str(entry.get("referer") or urls["checklist"])

                q_f_winner = ""
                has_front = False
                if _check_or_rename_existing_cid_file(disk_cid_index, cid_s, "F", f_path):
                    has_front = True
                    img_stats["front_skip"] += 1
                    if isinstance(entry.get("front"), dict):
                        q_f_winner = str(entry["front"].get("quality") or "")
                elif cid_s in dead_fronts:
                    img_stats["no_img"] += 1
                else:
                    pending_attempted += 1
                    f_out: dict = {}
                    q_f = _download_single_template_side(
                        req_session, url_rep_f, url_std_f, referer, f_path,
                        set_key=cat_key,
                        thumb_url=str(entry.get("front_thumb") or ""),
                        preferred_tier=str(entry.get("front_tier_hint") or ""),
                        outcome_out=f_out,
                        circuit_breaker=img_circuit_breaker,
                    )
                    if q_f:
                        has_front = True
                        q_f_winner = q_f
                        img_stats["front_dl"] += 1
                        disk_cid_index[(cid_s, "F")] = f_path
                        entry["front"] = {"quality": q_f, "file": f_fname}
                        if p_ctx.get("est_remaining_dl_cards") is not None:
                            p_ctx["est_remaining_dl_cards"] = max(0, int(p_ctx["est_remaining_dl_cards"]) - 1)
                    elif f_out.get("confirmed_404"):
                        dead_fronts[cid_s] = time.time()
                        dead_fronts_dirty = True

                if _check_or_rename_existing_cid_file(disk_cid_index, cid_s, "B", b_path):
                    img_stats["back_skip"] += 1
                elif has_front and (url_rep_b or url_std_b) and cid_s not in dead_backs:
                    pending_attempted += 1
                    b_out: dict = {}
                    q_b = _download_single_template_side(
                        req_session, url_rep_b, url_std_b, referer, b_path,
                        set_key=cat_key,
                        thumb_url=str(entry.get("back_thumb") or ""),
                        preferred_tier=str(entry.get("back_tier_hint") or q_f_winner),
                        outcome_out=b_out,
                        circuit_breaker=img_circuit_breaker,
                    )
                    if q_b:
                        img_stats["back_dl"] += 1
                        disk_cid_index[(cid_s, "B")] = b_path
                        entry["back"] = {"quality": q_b, "file": b_fname}
                    elif b_out.get("confirmed_404"):
                        dead_backs[cid_s] = time.time()
                        dead_backs_dirty = True
        return pending_attempted

    set_t0 = time.time()
    p_ctx = progress_ctx if isinstance(progress_ctx, dict) else {
        "set_index": 1, "total_sets": 1, "completed_cards": 0, "total_cards": 500,
        "completed_subsets": 0, "total_subsets": 1, "est_remaining_dl_cards": None,
        "mode_key": "checklist_and_images" if download_images_card_by_card else "checklist_only",
    }
    mode_key_cur = str(p_ctx.get("mode_key") or ("checklist_and_images" if download_images_card_by_card else "checklist_only"))
    learner = get_rate_learner()
    set_stats_key = sanitize_filename_part(checklist_set_name)
    known_sub_counts = dict((p_ctx.get("active_set_subset_counts") or {}))
    set_cards_processed = 0

    def _run_subset_with_telemetry(
        sub_url: str,
        sub_lbl: str,
        expected_cards: int = 0,
        pre_page1_html: Optional[str] = None,
        parent_cards: Optional[list[dict]] = None,
        existing_local_by_cid: Optional[dict[str, dict]] = None,
        interpolation_stats_out: Optional[dict] = None,
    ) -> list[dict]:
        nonlocal set_cards_processed
        sub_t0 = time.time()
        init_sub_tot = max(1, int(expected_cards or known_sub_counts.get(sub_lbl, 0) or 100))
        sub_state = {"done": 0, "total": init_sub_tot, "pre_est": int(expected_cards or known_sub_counts.get(sub_lbl, 0) or 0), "name": sub_lbl}
        before_dl_f = img_stats["front_dl"]
        before_skip_f = img_stats["front_skip"] + img_stats["no_img"]

        def _on_page_info(page_i: int, max_p: int, est_sub_total: int):
            if est_sub_total > 0:
                prev_tot = sub_state["total"]
                sub_state["total"] = max(sub_state["done"], int(est_sub_total))
                # Dynamically reconcile Tier-1 total_cards when live subset card count refines the pre-scan estimate
                if sub_state["pre_est"] > 0:
                    delta = sub_state["total"] - prev_tot
                    if delta != 0:
                        p_ctx["total_cards"] = max(int(p_ctx.get("completed_cards", 0)) + 1, int(p_ctx.get("total_cards", 1)) + delta)

        def _card_progress_wrapper(c_row: dict):
            nonlocal set_cards_processed
            sub_state["done"] += 1
            set_cards_processed += 1
            p_ctx["completed_cards"] = int(p_ctx.get("completed_cards", 0)) + 1
            if sub_state["done"] > sub_state["total"]:
                diff_ov = sub_state["done"] - sub_state["total"]
                sub_state["total"] = sub_state["done"]
                p_ctx["total_cards"] = max(p_ctx["completed_cards"], int(p_ctx.get("total_cards", 1)) + diff_ov)
            sub_state["name"] = str(c_row.get("Subset") or sub_lbl).strip() or sub_lbl
            dl_before = img_stats["front_dl"]
            if download_images_card_by_card:
                _download_card_immediately(c_row)
                if img_stats["front_dl"] > dl_before and p_ctx.get("est_remaining_dl_cards") is not None:
                    p_ctx["est_remaining_dl_cards"] = max(0, int(p_ctx["est_remaining_dl_cards"]) - 1)
            emit_progress(
                active_set_name=checklist_set_name,
                active_set_key=set_stats_key,
                set_index=p_ctx.get("set_index", 1),
                total_sets=p_ctx.get("total_sets", 1),
                completed_cards=p_ctx["completed_cards"],
                total_cards=max(p_ctx["completed_cards"], int(p_ctx.get("total_cards", 1))),
                completed_subsets=p_ctx.get("completed_subsets", 0),
                total_subsets=max(1, p_ctx.get("total_subsets", 1)),
                sub_name=sub_state["name"],
                sub_current=sub_state["done"],
                sub_total=sub_state["total"],
                sub_start_epoch=sub_t0,
                current_item=f"[Card #{c_row.get('Card Number','')}] {c_row.get('Player','')} [{sub_state['name']} | CID {c_row.get('TCDB_CID','')}]",
                mode_key=mode_key_cur,
                est_remaining_dl_cards=p_ctx.get("est_remaining_dl_cards"),
            )

        emit_progress(
            active_set_name=checklist_set_name,
            active_set_key=set_stats_key,
            set_index=p_ctx.get("set_index", 1),
            total_sets=p_ctx.get("total_sets", 1),
            completed_cards=int(p_ctx.get("completed_cards", 0)),
            total_cards=max(1, int(p_ctx.get("total_cards", 1))),
            completed_subsets=p_ctx.get("completed_subsets", 0),
            total_subsets=max(1, p_ctx.get("total_subsets", 1)),
            sub_name=sub_lbl,
            sub_current=0,
            sub_total=sub_state["total"],
            sub_start_epoch=sub_t0,
            current_item=f"Loading {sub_lbl}...",
            mode_key=mode_key_cur,
            est_remaining_dl_cards=p_ctx.get("est_remaining_dl_cards"),
        )
        rows_out = _scrape_tcdb_subset_checklist_pages(
            req_session,
            sub_url,
            subset_name=sub_lbl,
            checklist_set_name=checklist_set_name,
            card_callback=_card_progress_wrapper,
            page_info_callback=_on_page_info,
            prefetched_page1_html=pre_page1_html,
            known_subset_total=sub_state["pre_est"],
            parent_cards=parent_cards,
            existing_local_by_cid=existing_local_by_cid,
            interpolation_stats_out=interpolation_stats_out,
        )
        # Reconcile any remaining gap between estimated subset total and actual extracted rows
        actual_sub_cards = len(rows_out)
        if sub_state["total"] != actual_sub_cards and sub_state["pre_est"] > 0:
            delta_end = actual_sub_cards - sub_state["total"]
            p_ctx["total_cards"] = max(int(p_ctx.get("completed_cards", 0)), int(p_ctx.get("total_cards", 1)) + delta_end)

        p_ctx["completed_subsets"] = int(p_ctx.get("completed_subsets", 0)) + 1
        sub_dl_cards = max(0, img_stats["front_dl"] - before_dl_f)
        sub_skip_cards = max(0, (img_stats["front_skip"] + img_stats["no_img"]) - before_skip_f)
        learner.record_subset_duration(
            mode_key_cur,
            time.time() - sub_t0,
            card_count=actual_sub_cards,
            downloaded_cards=sub_dl_cards,
            skipped_cards=sub_skip_cards,
        )
        emit_progress(
            active_set_name=checklist_set_name,
            active_set_key=set_stats_key,
            set_index=p_ctx.get("set_index", 1),
            total_sets=p_ctx.get("total_sets", 1),
            completed_cards=int(p_ctx.get("completed_cards", 0)),
            total_cards=max(int(p_ctx.get("completed_cards", 0)), int(p_ctx.get("total_cards", 1))),
            completed_subsets=p_ctx["completed_subsets"],
            total_subsets=max(p_ctx["completed_subsets"], p_ctx.get("total_subsets", 1)),
            sub_name=sub_state["name"],
            sub_current=actual_sub_cards,
            sub_total=max(1, actual_sub_cards),
            sub_start_epoch=sub_t0,
            current_item=f"Completed {sub_state['name']} ({actual_sub_cards:,} cards)",
            mode_key=mode_key_cur,
            est_remaining_dl_cards=p_ctx.get("est_remaining_dl_cards"),
        )
        return rows_out

    checkpoint = load_set_checkpoint(checklist_set_name, alt_folder_name=cat_key) if (incremental and not force_refresh) else {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "set_key": set_stats_key,
        "set_name": checklist_set_name,
        "subsets": {},
    }
    checkpoint["set_sid"] = extract_tcdb_sid(viewset_url)
    checkpoint["viewset_url"] = viewset_url
    local_rows_by_key, _, _ = _load_local_set_csv_rows_by_subset(checklist_set_name, folder_name=cat_key)
    subset_rows_store: dict[str, list[dict]] = {}
    if incremental and not force_refresh and local_rows_by_key:
        for sk_loc, rows_loc in local_rows_by_key.items():
            subset_rows_store[sk_loc] = list(rows_loc)

    subsets_skipped = 0
    subsets_fetched = 0
    subsets_interpolated = 0
    pages_saved_by_interpolation = 0
    changed_since_flush = 0
    set_csv_checkpoint = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(canonicalize_checklist_set_title(checklist_set_name))}.csv"

    parent_cards_pool: dict[str, tuple[str, list[dict]]] = {}

    def _register_parent_subset(sub_name: str, rows_list: list[dict], from_csv: bool = False):
        if not rows_list:
            return
        deduped = _dedupe_physical_parent_cards(rows_list, sort_by_cid=from_csv)
        if len(deduped) >= 3:
            disp = str(rows_list[0].get("Subset") or sub_name).strip() or sub_name
            parent_cards_pool[canonical_subset_key(disp)] = (disp, deduped)

    if local_rows_by_key:
        for _sk_loc, _rows_loc in local_rows_by_key.items():
            if _rows_loc:
                _register_parent_subset(str(_rows_loc[0].get("Subset") or _sk_loc), _rows_loc, from_csv=True)

    def _subset_is_complete_and_unchanged(
        sid_key: str,
        sub_url: str,
        sub_label: str,
        expected_cards: int,
        is_base: bool = False,
    ) -> tuple[bool, list[dict], str, str]:
        local_rows = _lookup_local_subset_rows(local_rows_by_key, sub_label)
        if not incremental or force_refresh:
            return False, [], "force_refresh", f"local={len(local_rows)}, tcdb={expected_cards}"
        if not local_rows:
            return False, [], "missing_locally", f"local=0 vs tcdb={expected_cards}"
        cp_entry = (checkpoint.get("subsets") or {}).get(str(sid_key))
        if cp_entry is None and local_rows:
            cp_entry = _try_bootstrap_subset_checkpoint(
                checkpoint, str(sid_key), sub_url, sub_label, expected_cards, local_rows, is_base=is_base
            )
            if cp_entry is not None:
                save_set_checkpoint(checklist_set_name, checkpoint)
        if not isinstance(cp_entry, dict) or cp_entry.get("status") != "complete":
            if expected_cards > 0 and len(local_rows) != expected_cards:
                return False, [], "count_mismatch", f"local_raw={len(local_rows)} vs tcdb={expected_cards}"
            return False, [], "missing_checkpoint", f"local={len(local_rows)}, tcdb={expected_cards}"

        saved_tcdb_reported = int(cp_entry.get("tcdb_reported_count") or cp_entry.get("expected_cards") or 0)
        saved_deduped = int(cp_entry.get("local_deduped_count") or cp_entry.get("scraped_cards") or 0)
        count_matches = (
            expected_cards <= 0
            or len(local_rows) == expected_cards
            or (
                saved_tcdb_reported > 0
                and saved_tcdb_reported == expected_cards
                and (saved_deduped <= 0 or len(local_rows) == saved_deduped)
            )
        )
        if not count_matches:
            return False, [], "count_mismatch", f"local_raw={len(local_rows)} vs tcdb={expected_cards}"
        if compute_subset_rows_checksum(local_rows) != cp_entry.get("rows_sha256"):
            return False, [], "checksum_changed", f"local={len(local_rows)}, tcdb={expected_cards}"
        reported_disp = expected_cards or saved_tcdb_reported or len(local_rows)
        return True, local_rows, "unchanged", f"local={len(local_rows)}, tcdb_reported={reported_disp}"

    def _record_subset_checkpoint(sid_key: str, sub_url: str, sub_label: str, expected_cards: int, rows_list: list[dict], is_base: bool = False):
        imaged_f = sum(1 for r in rows_list if "front" in str(r.get("TCDB_Image_Status") or "").lower())
        imaged_b = sum(1 for r in rows_list if "back" in str(r.get("TCDB_Image_Status") or "").lower() and "no back" not in str(r.get("TCDB_Image_Status") or "").lower())
        tcdb_rep = int(expected_cards or len(rows_list))
        checkpoint.setdefault("subsets", {})[str(sid_key)] = {
            "subset_name": str(sub_label),
            "subset_url": str(sub_url),
            "is_base": bool(is_base),
            "expected_cards": tcdb_rep,
            "tcdb_reported_count": tcdb_rep,
            "scraped_cards": len(rows_list),
            "local_deduped_count": len(rows_list),
            "imaged_fronts_on_tcdb": imaged_f,
            "imaged_backs_on_tcdb": imaged_b,
            "rows_sha256": compute_subset_rows_checksum(rows_list),
            "status": "complete",
            "bootstrapped_from_csv": False,
            "last_verified_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_set_checkpoint(checklist_set_name, checkpoint)

    base_sid = extract_tcdb_sid(urls["checklist"]) or "base"
    base_expected = int(p_ctx.get("active_set_base_cards") or known_sub_counts.get("Base", 0) or 0)
    base_skip_t0 = time.time()
    base_skip, local_base_rows, base_reason, base_detail = _subset_is_complete_and_unchanged(base_sid, urls["checklist"], "Base", base_expected, is_base=True)
    if base_skip:
        subsets_skipped += 1
        p_ctx["completed_subsets"] = int(p_ctx.get("completed_subsets", 0)) + 1
        p_ctx["completed_cards"] = int(p_ctx.get("completed_cards", 0)) + len(local_base_rows)
        subset_rows_store[canonical_subset_key("Base")] = local_base_rows
        _register_parent_subset("Base", local_base_rows, from_csv=True)
        pend_imgs = _download_missing_images_for_skipped_subset("Base") if download_images_card_by_card else 0
        learner.record_subset_duration(mode_key_cur, time.time() - base_skip_t0, card_count=len(local_base_rows), was_skipped=True)
        if pend_imgs > 0:
            log_msg(f"  [QUEUE: new_images] Base ({pend_imgs} pending image(s); {base_detail})")
        else:
            log_msg(f"  [SKIP] Base ({base_detail})")
    else:
        log_msg(f"  [QUEUE: {base_reason}] Base ({base_detail})")
        subsets_fetched += 1
        base_rows = _run_subset_with_telemetry(urls["checklist"], "Base", expected_cards=base_expected, pre_page1_html=prefetched_base_html)
        subset_rows_store[canonical_subset_key("Base")] = base_rows
        if base_rows:
            _register_parent_subset("Base", base_rows, from_csv=False)
            _record_subset_checkpoint(base_sid, urls["checklist"], "Base", base_expected or len(base_rows), base_rows, is_base=True)
            changed_since_flush += 1
        log_msg(f"  + Base Set: {len(base_rows)} card rows extracted (with TCDB_CIDs).")

    err_cp = checkpoint.get("errors_page") if isinstance(checkpoint.get("errors_page"), dict) else {}
    if incremental and not force_refresh and base_skip:
        if err_cp.get("status") != "complete":
            existing_err_rows = local_rows_by_key.get(canonical_subset_key("Base Variation"), [])
            checkpoint["errors_page"] = {
                "url": urls["errors"],
                "card_count": len(existing_err_rows),
                "status": "complete",
                "bootstrapped_from_csv": True,
                "last_verified_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_set_checkpoint(checklist_set_name, checkpoint)
        log_msg("  [SKIP-UNCHANGED] Variations / Errors: verified from checkpoint/CSV.")
    else:
        err_res = safe_get(req_session, urls["errors"], silent_404=True, max_403_retries=1)
        if err_res:
            soup_err = BeautifulSoup(decode_html_response(err_res), "html.parser")
            err_rows = parse_tcdb_checklist_table_rows(soup_err, subset_name="Base Variation", current_url=urls["errors"], page_num=1)
            if err_rows:
                if download_images_card_by_card:
                    for er in err_rows:
                        _download_card_immediately(er)
                subset_rows_store[canonical_subset_key("Base Variation")] = err_rows
                log_msg(f"  + Variations / Errors: {len(err_rows)} rows extracted.")
            checkpoint["errors_page"] = {
                "url": urls["errors"],
                "card_count": len(err_rows),
                "status": "complete",
                "last_verified_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_set_checkpoint(checklist_set_name, checkpoint)
        else:
            checkpoint["errors_page"] = {
                "url": urls["errors"],
                "card_count": 0,
                "status": "complete",
                "last_verified_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_set_checkpoint(checklist_set_name, checkpoint)

    if include_inserts:
        if prefetched_inserts is not None:
            insert_by_sid = prefetched_inserts
            ins_counts_map = prefetched_insert_counts or {}
        else:
            insert_by_sid, ins_counts_map = _fetch_inserts_index_with_counts(req_session, urls["inserts"], checklist_set_name)
            p_ctx["total_subsets"] = max(p_ctx.get("total_subsets", 1), p_ctx.get("completed_subsets", 1) + len(insert_by_sid))
        if insert_by_sid:
            log_msg(f"  📑 Processing {len(insert_by_sid)} TCDB Insert/Parallel/Auto/Relic checklists for '{checklist_set_name}'.")
            flush_every = 5 if download_images_card_by_card else 10
            for idx, (sid_k, (ins_url, sub_label)) in enumerate(insert_by_sid.items(), 1):
                if is_stop_requested() or not wait_if_paused(reason="Paused between subsets"):
                    break
                fallback_label = clean_tcdb_subset_title(sub_label, checklist_set_name=checklist_set_name) or f"Subset_{sid_k}"
                exp_ins_cards = int(ins_counts_map.get(sid_k, 0) or known_sub_counts.get(fallback_label, 0) or 0)
                sub_skip_t0 = time.time()
                sub_skip, local_sub_rows, sub_reason, sub_detail = _subset_is_complete_and_unchanged(sid_k, ins_url, fallback_label, exp_ins_cards)
                if sub_skip:
                    subsets_skipped += 1
                    p_ctx["completed_subsets"] = int(p_ctx.get("completed_subsets", 0)) + 1
                    p_ctx["completed_cards"] = int(p_ctx.get("completed_cards", 0)) + len(local_sub_rows)
                    subset_rows_store[canonical_subset_key(fallback_label)] = local_sub_rows
                    _register_parent_subset(fallback_label, local_sub_rows, from_csv=True)
                    pend_ins_imgs = _download_missing_images_for_skipped_subset(fallback_label) if download_images_card_by_card else 0
                    learner.record_subset_duration(mode_key_cur, time.time() - sub_skip_t0, card_count=len(local_sub_rows), was_skipped=True)
                    if pend_ins_imgs > 0:
                        log_msg(f"    [{idx}/{len(insert_by_sid)}] [QUEUE: new_images] {fallback_label} ({pend_ins_imgs} pending image(s); {sub_detail})")
                    else:
                        log_msg(f"    [{idx}/{len(insert_by_sid)}] [SKIP] {fallback_label} ({sub_detail})")
                    continue

                log_msg(f"    [{idx}/{len(insert_by_sid)}] [QUEUE: {sub_reason}] {fallback_label} ({sub_detail})")
                subsets_fetched += 1
                _parent_name, resolved_parent_cards = _resolve_parallel_parent_subset(
                    fallback_label,
                    parent_cards_pool,
                    expected_cards=exp_ins_cards,
                )
                sub_local_rows = _lookup_local_subset_rows(local_rows_by_key, fallback_label)
                sub_local_by_cid = {
                    normalize_numeric_tcdb_cid(r.get("TCDB_CID", "")): r
                    for r in sub_local_rows
                    if normalize_numeric_tcdb_cid(r.get("TCDB_CID", "")) not in ("", "0")
                }
                interp_stats: dict = {"interpolated": False, "pages_saved": 0, "reason": ""}
                sub_rows = _run_subset_with_telemetry(
                    ins_url,
                    fallback_label,
                    expected_cards=exp_ins_cards,
                    parent_cards=resolved_parent_cards or None,
                    existing_local_by_cid=sub_local_by_cid or None,
                    interpolation_stats_out=interp_stats,
                )
                if interp_stats.get("interpolated"):
                    subsets_interpolated += 1
                    pages_saved_by_interpolation += int(interp_stats.get("pages_saved") or 0)
                resolved_lbl = sub_rows[0]["Subset"] if sub_rows else fallback_label
                if sub_rows:
                    subset_rows_store[canonical_subset_key(resolved_lbl)] = sub_rows
                    _register_parent_subset(resolved_lbl, sub_rows, from_csv=False)
                    _record_subset_checkpoint(sid_k, ins_url, resolved_lbl, exp_ins_cards or len(sub_rows), sub_rows, is_base=False)
                    changed_since_flush += 1
                log_msg(f"    [{idx}/{len(insert_by_sid)}] {resolved_lbl}: {len(sub_rows)} rows extracted.")
                if changed_since_flush >= flush_every:
                    merged_partial = [r for rows_l in subset_rows_store.values() for r in rows_l]
                    if merged_partial:
                        _update_catalog_from_parsed_rows(catalog, checklist_set_name, merged_partial)
                        save_catalog(cat_key, catalog)
                        save_set_checkpoint(checklist_set_name, checkpoint)
                        partial_df = apply_excel_formulas_and_combine(merged_partial, checklist_set_name)
                        partial_df.to_csv(set_csv_checkpoint, index=False, encoding="utf-8-sig")
                    changed_since_flush = 0

    all_raw_rows = [r for rows_l in subset_rows_store.values() for r in rows_l]
    if not all_raw_rows:
        return pd.DataFrame(columns=CHECKLIST_COLUMNS), []

    _update_catalog_from_parsed_rows(catalog, checklist_set_name, all_raw_rows)
    save_catalog(cat_key, catalog)
    checkpoint["last_verified_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_set_checkpoint(checklist_set_name, checkpoint)
    if dead_backs_dirty:
        save_dead_backs_cache(dead_backs)
    if dead_fronts_dirty:
        save_dead_fronts_cache(dead_fronts)

    final_df = apply_excel_formulas_and_combine(all_raw_rows, checklist_set_name)
    # Reconcile checkpoint local_deduped_count & rows_sha256 against final deduped CSV rows
    # while preserving TCDB's raw reported count (`tcdb_reported_count`) so multiline/combo
    # deduplication never triggers false `count_mismatch` deep-dives on subsequent runs.
    if not final_df.empty and isinstance(checkpoint.get("subsets"), dict):
        deduped_by_canon: dict[str, list[dict]] = defaultdict(list)
        deduped_by_norm: dict[str, list[dict]] = defaultdict(list)
        for rec in final_df.to_dict(orient="records"):
            sub_disp = str(rec.get("Subset") or "Base").strip() or "Base"
            deduped_by_canon[canonical_subset_key(sub_disp)].append(rec)
            deduped_by_norm[normalize_subset_name_for_diff(sub_disp)].append(rec)
        cp_reconciled = False
        for cp_ent in checkpoint["subsets"].values():
            if not isinstance(cp_ent, dict):
                continue
            s_name = str(cp_ent.get("subset_name") or "Base")
            d_rows = deduped_by_canon.get(canonical_subset_key(s_name)) or deduped_by_norm.get(normalize_subset_name_for_diff(s_name))
            if d_rows:
                cp_ent.setdefault("tcdb_reported_count", int(cp_ent.get("expected_cards") or len(d_rows)))
                cp_ent["local_deduped_count"] = len(d_rows)
                cp_ent["rows_sha256"] = compute_subset_rows_checksum(d_rows)
                cp_reconciled = True
        if cp_reconciled:
            save_set_checkpoint(checklist_set_name, checkpoint)
    # Persist exact set-level card counts and historical run duration into the ETA cache
    try:
        sub_vc_fin = {str(k): int(v) for k, v in final_df["Subset"].value_counts().items() if str(k).strip()} if not final_df.empty else {}
        base_fin = sum(v for k, v in sub_vc_fin.items() if k.upper() in ("BASE", "BASE SET"))
        learner.update_set_stats(
            set_key=set_stats_key,
            set_name=checklist_set_name,
            total_cards=len(final_df),
            base_cards=base_fin,
            total_subsets=len(sub_vc_fin),
            subset_card_counts=sub_vc_fin,
            force_save=False,
        )
        learner.record_set_run_timing(
            set_key=set_stats_key,
            mode_key=mode_key_cur,
            duration_sec=time.time() - set_t0,
            cards_processed=max(len(final_df), set_cards_processed),
            images_downloaded=img_stats["front_dl"] + img_stats["back_dl"],
            images_skipped=img_stats["front_skip"] + img_stats["back_skip"] + img_stats["no_img"],
            set_name=checklist_set_name,
        )
    except Exception:
        pass
    if download_images_card_by_card:
        log_msg(
            f"  ✅ Combined Card-by-Card Complete for '{checklist_set_name}': {len(final_df):,} unique rows "
            f"(Subsets: {subsets_fetched} fetched, {subsets_skipped} skipped, "
            f"{subsets_interpolated} interpolated, {pages_saved_by_interpolation} page(s) saved) | "
            f"Downloaded {img_stats['front_dl']:,} Fronts, {img_stats['back_dl']:,} Backs "
            f"(Skipped existing: {img_stats['front_skip']:,}F/{img_stats['back_skip']:,}B | "
            f"Back-Only skipped: {img_stats['back_only_skip']:,} | NoBack skipped: {img_stats['no_back']:,} | No TCDB img: {img_stats['no_img']:,})."
        )
    else:
        log_msg(
            f"  ✅ TCDB Checklist Complete for '{checklist_set_name}': {len(final_df):,} unique card rows "
            f"(Subsets: {subsets_fetched} fetched, {subsets_skipped} skipped, "
            f"{subsets_interpolated} interpolated, {pages_saved_by_interpolation} page(s) saved)!"
        )
    return final_df, all_raw_rows


def run_tcdb_checklist_pipeline(
    selected_tcdb_sets: Optional[dict[str, str]] = None,
    clean_slate_reset: bool = False,
    incremental: bool = True,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Builds 11-column Set Checklists (`Set`, `Subset`, `Card Number`, `Player`, `Team`,
    `Print Run`, `Attributes`, `TCDB_CID`, `Front_Downloaded`, `Back_Downloaded`, `TCDB_Image_Status`)
    and syncs download status against `D:\\Tabulas Set Library`.
    """
    ensure_directories()
    if selected_tcdb_sets is None:
        selected_tcdb_sets = load_tracked_sets()

    if not selected_tcdb_sets:
        log_msg("[!] No tracked TCDB sets found to build checklists.")
        return pd.DataFrame(columns=CHECKLIST_COLUMNS)

    if clean_slate_reset:
        archive_existing_checklists_for_clean_slate()

    req_session = connect_session(target_domain=BASE_URL, require_image_probe=False)
    queue_items = list(selected_tcdb_sets.items())
    total = len(queue_items)
    try:
        pre = prescan_queue_card_metrics(req_session, queue_items, mode_key="checklist_only")
        p_ctx = {
            "set_index": 0,
            "total_sets": total,
            "completed_cards": 0,
            "total_cards": pre["total_cards"],
            "completed_subsets": 0,
            "total_subsets": pre["total_subsets"],
            "est_remaining_dl_cards": None,
            "mode_key": "checklist_only",
        }
        for idx, (set_url, folder_name) in enumerate(queue_items, 1):
            set_m = (pre["per_set_metrics"] or {}).get(set_url, {})
            p_ctx["set_index"] = idx
            p_ctx["active_set_base_cards"] = set_m.get("base_cards", 0)
            p_ctx["active_set_subset_counts"] = set_m.get("subset_card_counts", {})
            try:
                rem_queue = {u_r: fn_r for u_r, fn_r in queue_items[idx - 1 :]}
                atomic_write_text(
                    RESUME_FILE,
                    json.dumps({"mode": "checklist_only", "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "remaining_queue": rem_queue}, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
            chk_title = canonicalize_checklist_set_title(folder_name.replace("_", " ").strip())
            log_msg(f"[{idx}/{total}] Building TCDB Checklist + CIDs for '{chk_title}' ({set_m.get('total_cards', 0):,} est. cards)...")
            df_set, _ = scrape_tcdb_checklist_set(
                req_session,
                set_url,
                chk_title,
                folder_name=folder_name,
                include_inserts=True,
                prefetched_inserts=pre["prefetched_inserts"].get(set_url),
                prefetched_insert_counts=pre["prefetched_insert_counts"].get(set_url),
                prefetched_base_html=pre["prefetched_base_html"].get(set_url),
                progress_ctx=p_ctx,
                incremental=incremental,
                force_refresh=force_refresh,
            )
            if not df_set.empty:
                _merge_set_checklist_into_master(df_set, chk_title, replace_set_cleanly=True)
            if idx < total:
                time.sleep(1.5)
        clear_resume_state()
    finally:
        cleanup_orphaned_drivers()

    sync_set_library_download_status(rebuild_master_checklist=True)

    from Core.database import load_master_checklist
    load_master_checklist(CHECKLIST_PATH, force_reload=True)
    log_msg(f"🎉 Completed TCDB Master Checklist + CID build for {total} set(s)!")
    if CHECKLIST_PATH.exists():
        try:
            return pd.read_csv(CHECKLIST_PATH, dtype=str, keep_default_na=False)
        except Exception:
            pass
    return pd.DataFrame(columns=CHECKLIST_COLUMNS)


# ==============================================================================
# 6. UNIFIED TEMPLATE DOWNLOADER (STANDARD / EXTENDED / FULL / ALL CATALOGED)
# ==============================================================================
def _download_single_template_side(
    req_session,
    url_rep: str,
    url_std: str,
    referer: str,
    dest_path: Path,
    set_key: str = "",
    thumb_url: str = "",
    force_rep_first: bool = False,
    preferred_tier: str = "",
    outcome_out: Optional[dict] = None,
    circuit_breaker: Optional[CloudflareImageCircuitBreaker] = None,
) -> Optional[str]:
    """
    Thumbnail-Direct & Front-Tier-Aware image downloader powered by `AdaptiveRateLearner`:
      - Trusts `"rep" in thumb_url.lower()` from Card #1 (zero exploration 404s).
      - Inherits `preferred_tier` (e.g., Front's winning tier) when no thumbnail URL is available.
      - Always falls back to the alternate tier if the first probe returns 404.
      - Sets `outcome_out["confirmed_404"] = True` ONLY when every probed URL literally returned HTTP 404.
    """
    learner = get_rate_learner()
    try_rep_first = learner.should_probe_rep_first(
        set_key=set_key,
        thumb_url=thumb_url,
        force_rep_first=force_rep_first or (not bool(url_std)),
        preferred_tier=preferred_tier,
    )

    probed_codes: list[int] = []
    order = [("R", url_rep), ("S", url_std)] if try_rep_first else [("S", url_std), ("R", url_rep)]
    for tier_code, cand_url in order:
        if not cand_url:
            continue
        st: dict = {}
        res = safe_get(
            req_session,
            cand_url,
            headers={"Referer": referer},
            retries=2,
            silent_404=True,
            status_out=st,
            circuit_breaker=circuit_breaker,
        )
        if res and res.status_code == 200 and is_valid_image_payload(res.content):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(dest_path, lambda tmp_p: tmp_p.write_bytes(res.content))
            learner.record_tier_outcome(
                set_key=set_key,
                quality_tier=tier_code,
                skipped_rep_probe=(not try_rep_first and tier_code == "S"),
            )
            if isinstance(outcome_out, dict):
                outcome_out["confirmed_404"] = False
                outcome_out["status_code"] = 200
                outcome_out["outcome"] = "ok"
            return tier_code
        code = -1 if (res is not None and res.status_code == 200) else int(st.get("status_code", 0) or 0)
        err_str = str(st.get("error") or "").lower()
        is_timeout = (code == 0) or ("timed out" in err_str) or ("timeout" in err_str) or ("(28)" in err_str)
        probed_codes.append(code)
        if code in (403, 429, 503) or is_timeout:
            if isinstance(outcome_out, dict) and (code == 503 or is_timeout):
                outcome_out["transient_overload"] = True
            break

    confirmed_404 = bool(probed_codes) and all(c == 404 for c in probed_codes)
    last_code = probed_codes[-1] if probed_codes else 0
    if isinstance(outcome_out, dict):
        outcome_out["confirmed_404"] = confirmed_404
        outcome_out["status_code"] = last_code
        outcome_out["outcome"] = "404" if confirmed_404 else (f"http_{last_code}" if last_code > 0 else "network_error")
    return None


def _select_distributed_indices(total_len: int, quota: int) -> list[int]:
    if quota <= 0 or total_len <= 0:
        return []
    if total_len <= quota:
        return list(range(total_len))
    if quota == 1:
        return [0]
    return sorted(set(round(i * (total_len - 1) / (quota - 1)) for i in range(quota)))


def mode_scraping_pipeline(
    target_queue: Optional[dict[str, str]] = None,
    cooldown_seconds: int = 5,
    override_download_level: Optional[str] = None,
    download_all_cataloged: bool = True,
    incremental: bool = True,
    force_refresh: bool = False,
):
    """Unified full-archive scraper delegating directly to the smart Card-by-Card pipeline (100% of available images)."""
    mode_checklist_and_images_card_by_card(
        target_queue=target_queue,
        clean_slate_reset=False,
        cooldown_seconds=cooldown_seconds,
        incremental=incremental,
        force_refresh=force_refresh,
    )


def _count_pending_catalog_downloads(
    queue_items: list[tuple[str, str]],
    dead_backs: dict[str, float],
    dead_fronts: dict[str, float],
) -> tuple[int, int]:
    """Zero-network local pre-scan returning `(pending_fronts, pending_backs)` across `queue_items`."""
    pending_f = 0
    pending_b = 0
    for _, folder_name in queue_items:
        catalog = load_catalog(folder_name)
        set_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
        disk_idx = _index_existing_set_dir_by_cid(set_dir)
        for _, cards_dict in catalog.items():
            if not isinstance(cards_dict, dict):
                continue
            for cid, entry in cards_dict.items():
                if str(cid).startswith("_") or not isinstance(entry, dict):
                    continue
                cid_n = normalize_numeric_tcdb_cid(cid)
                has_f_url = bool(entry.get("url_rep_front") or entry.get("url_std_front"))
                has_b_url = bool(entry.get("url_rep_back") or entry.get("url_std_back"))
                if not has_f_url:
                    continue
                f_file = str(entry.get("front_file") or "")
                b_file = str(entry.get("back_file") or "")
                has_f_disk = (cid_n, "F") in disk_idx or (f_file and (set_dir / f_file).exists())
                has_b_disk = (cid_n, "B") in disk_idx or (b_file and (set_dir / b_file).exists())
                if not has_f_disk and cid_n not in dead_fronts and str(cid) not in dead_fronts:
                    pending_f += 1
                if (has_f_disk or cid_n not in dead_fronts) and has_b_url and not has_b_disk and cid_n not in dead_backs and str(cid) not in dead_backs:
                    pending_b += 1
    return pending_f, pending_b


def mode_download_all_catalog_images(
    target_queue: Optional[dict[str, str]] = None,
    max_cards_per_run: Optional[int] = DEFAULT_MAX_CARDS_PER_RUN,
    card_delay_range: tuple[float, float] = (IMAGE_CARD_JITTER_MIN_S, IMAGE_CARD_JITTER_MAX_S),
    breather_every_cards: int = IMAGE_BREATHER_EVERY_CARDS,
    breather_duration_range: tuple[float, float] = (IMAGE_BREATHER_MIN_S, IMAGE_BREATHER_MAX_S),
    circuit_breaker: Optional[CloudflareImageCircuitBreaker] = None,
):
    """
    PURE IMAGE DOWNLOADER ONLY (No checklist re-scraping):
    Reads each set's already-indexed `<set>_catalog.json` and downloads every missing
    Front (`_F.jpg`) and Back (`_B.jpg`) image directly into `D:\\Tabulas Set Library\\<Set>\\`.
    Includes strict 404-only missing caching, Cloudflare 403/429 circuit breaker,
    randomized human-like card jitter, periodic breathers, and optional per-run card cap.
    """
    ensure_directories()
    meta_map = load_tracked_sets_meta(prioritize=True)
    queue = target_queue or {u: m["folder_name"] for u, m in meta_map.items()}
    if not queue:
        log_msg("[!] No sets in queue for image download.")
        return

    queue_items = list(queue.items())
    dead_backs_pre = load_dead_backs_cache()
    dead_fronts_pre = load_dead_fronts_cache()
    pend_f, pend_b = _count_pending_catalog_downloads(queue_items, dead_backs_pre, dead_fronts_pre)
    if pend_f == 0 and pend_b == 0:
        log_msg(f"✅ [FAST-SKIP] All {len(queue_items)} queued set(s) have 0 pending catalog image downloads on disk.")
        return

    cap_note = f", cap={max_cards_per_run:,}/run" if (max_cards_per_run is not None and max_cards_per_run > 0) else ""
    log_msg(f"📥 Launching PURE Front & Back Image Download (Catalog-Only, {pend_f:,} fronts / {pend_b:,} backs pending{cap_note}) for {len(queue)} set(s)...")
    req_session = connect_session(target_domain=BASE_URL, require_image_probe=True)
    total_sets = len(queue_items)
    learner = get_rate_learner()
    cb = circuit_breaker or CloudflareImageCircuitBreaker(stop_check=is_stop_requested)

    try:
        pre = prescan_queue_card_metrics(req_session, queue_items, mode_key="images_only")
        completed_cards_all = 0
        total_cards_all = int(pre["total_cards"])
        completed_subsets_all = 0
        total_subsets_all = int(pre["total_subsets"])
        est_rem_dl_all = int(pre["est_remaining_dl_cards"])
        downloaded_cards_this_run = 0
        consecutive_overload_cards = 0
        need_card_jitter = False
        stop_run = False

        for idx, (set_url, folder_name) in enumerate(queue_items, 1):
            if stop_run or is_stop_requested() or not wait_if_paused(reason="Paused between sets"):
                break
            set_t0 = time.time()
            chk_title = canonicalize_checklist_set_title(folder_name.replace("_", " ").strip())
            set_stats_key = sanitize_filename_part(chk_title)
            set_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
            set_dir.mkdir(parents=True, exist_ok=True)
            catalog = load_catalog(folder_name)

            grouped_by_sub: list[tuple[str, list[tuple[str, dict]]]] = []
            total_cards_set = 0
            skip_back_only = 0
            for sub_name, cards_dict in catalog.items():
                if not isinstance(cards_dict, dict):
                    continue
                sub_items = []
                for cid, entry in cards_dict.items():
                    if str(cid).startswith("_") or not isinstance(entry, dict):
                        continue
                    has_front_url = bool(entry.get("url_rep_front") or entry.get("url_std_front"))
                    has_back_url = bool(entry.get("url_rep_back") or entry.get("url_std_back"))
                    if has_front_url:
                        sub_items.append((str(cid), entry))
                    elif has_back_url:
                        # Skip back-only TCDB cards (checklist row remains intact!)
                        skip_back_only += 1
                if sub_items:
                    grouped_by_sub.append((sub_name, sub_items))
                    total_cards_set += len(sub_items)

            dir_pct_dl = _get_directory_image_pct(set_url=set_url, chk_title=chk_title)
            if total_cards_set == 0:
                pct_note = " (TCDB Directory confirms 0% images)" if dir_pct_dl == 0.0 else ""
                log_msg(
                    f"[{idx}/{total_sets}] [FAST-SKIP] '{folder_name}': 0 front image URLs in catalog JSON{pct_note} "
                    f"(skipped {skip_back_only:,} back-only card(s))."
                )
                continue

            disk_cid_index = _index_existing_set_dir_by_cid(set_dir)
            dead_backs = load_dead_backs_cache()
            dead_fronts = load_dead_fronts_cache()
            dead_backs_dirty = False
            dead_fronts_dirty = False

            log_msg(
                f"[{idx}/{total_sets}] Downloading Images Only for '{folder_name}': {total_cards_set:,} front-imaged card(s) "
                f"across {len(grouped_by_sub)} subset(s) (skipped {skip_back_only:,} back-only) -> {set_dir}"
            )
            dl_f, dl_b, skip_f, skip_b, skip_noback, miss_f, miss_b = 0, 0, 0, 0, 0, 0, 0
            c_idx = 0

            try:
                for sub_name, sub_items in grouped_by_sub:
                    if stop_run:
                        break
                    sub_clean = clean_tcdb_subset_title(sub_name, checklist_set_name=chk_title) or sub_name
                    sub_t0 = time.time()
                    sub_tot = len(sub_items)
                    sub_dl_start = dl_f
                    sub_skip_start = skip_f

                    # Fast subset-level skip when all imaged cards in this subset are already on disk or dead-cached
                    sub_has_pending = False
                    for cid_chk, ent_chk in sub_items:
                        cid_chk_n = normalize_numeric_tcdb_cid(cid_chk)
                        f_f = str(ent_chk.get("front_file") or "")
                        b_f = str(ent_chk.get("back_file") or "")
                        has_f_d = (cid_chk_n, "F") in disk_cid_index or (f_f and (set_dir / f_f).exists())
                        has_b_d = (cid_chk_n, "B") in disk_cid_index or (b_f and (set_dir / b_f).exists())
                        has_b_u = bool(ent_chk.get("url_rep_back") or ent_chk.get("url_std_back"))
                        if (not has_f_d and cid_chk_n not in dead_fronts and str(cid_chk) not in dead_fronts) or (
                            has_f_d and has_b_u and not has_b_d and cid_chk_n not in dead_backs and str(cid_chk) not in dead_backs
                        ):
                            sub_has_pending = True
                            break
                    if not sub_has_pending:
                        skip_f += sub_tot
                        c_idx += sub_tot
                        completed_cards_all += sub_tot
                        completed_subsets_all += 1
                        continue

                    for sub_pos, (cid, entry) in enumerate(sub_items, 1):
                        if stop_run or is_stop_requested() or not wait_if_paused(reason="Paused during image download"):
                            stop_run = True
                            break
                        c_idx += 1
                        completed_cards_all += 1
                        total_cards_all = max(total_cards_all, completed_cards_all)

                        cnum = str(entry.get("card_number") or "0").strip().lstrip("#")
                        plr_raw = str(entry.get("player") or "Unknown Player").strip()
                        plr_clean, _, _ = _strip_inline_tags_errors_and_occupations(plr_raw, team_str=str(entry.get("team") or ""))
                        plr = plr_clean or plr_raw
                        f_fname, b_fname = build_template_image_filenames(chk_title, sub_clean, cnum, plr, cid)
                        entry["player"] = plr
                        entry["front_file"] = f_fname
                        entry["back_file"] = b_fname

                        f_path = set_dir / f_fname
                        b_path = set_dir / b_fname
                        referer = str(entry.get("referer") or set_url)
                        url_rep_f = str(entry.get("url_rep_front") or "")
                        url_std_f = str(entry.get("url_std_front") or "")
                        url_rep_b = str(entry.get("url_rep_back") or "")
                        url_std_b = str(entry.get("url_std_back") or "")
                        f_thumb_u = str(entry.get("front_thumb") or "")
                        b_thumb_u = str(entry.get("back_thumb") or "")
                        f_hint_t = str(entry.get("front_tier_hint") or "")
                        b_hint_t = str(entry.get("back_tier_hint") or "")

                        existing_f = _check_or_rename_existing_cid_file(disk_cid_index, cid, "F", f_path)
                        existing_b = _check_or_rename_existing_cid_file(disk_cid_index, cid, "B", b_path)
                        need_net_f = (
                            not existing_f
                            and cid not in dead_fronts
                            and normalize_numeric_tcdb_cid(cid) not in dead_fronts
                            and bool(url_rep_f or url_std_f)
                        )
                        need_net_b = (
                            not existing_b
                            and bool(existing_f or need_net_f)
                            and bool(url_rep_b or url_std_b)
                            and cid not in dead_backs
                            and normalize_numeric_tcdb_cid(cid) not in dead_backs
                        )
                        will_hit_network = need_net_f or need_net_b
                        if will_hit_network and need_card_jitter and card_delay_range[1] > 0:
                            jitter_s = random.uniform(float(card_delay_range[0]), float(card_delay_range[1]))
                            if not cb.interruptible_sleep(jitter_s, reason="card pacing"):
                                stop_run = True
                                break
                            need_card_jitter = False

                        q_f_winner = ""
                        has_front = False
                        card_downloaded = False
                        f_out: dict = {}
                        b_out: dict = {}
                        if existing_f:
                            has_front = True
                            skip_f += 1
                            f_status = existing_f
                            if isinstance(entry.get("front"), dict):
                                q_f_winner = str(entry["front"].get("quality") or "")
                        elif cid in dead_fronts or normalize_numeric_tcdb_cid(cid) in dead_fronts:
                            skip_noback += 1
                            f_status = "Skip(DeadFrontCached)"
                        elif url_rep_f or url_std_f:
                            q_f = _download_single_template_side(
                                req_session, url_rep_f, url_std_f, referer, f_path,
                                set_key=folder_name, thumb_url=f_thumb_u, preferred_tier=f_hint_t,
                                outcome_out=f_out, circuit_breaker=cb,
                            )
                            if q_f:
                                has_front = True
                                card_downloaded = True
                                q_f_winner = q_f
                                dl_f += 1
                                est_rem_dl_all = max(0, est_rem_dl_all - 1)
                                disk_cid_index[(cid, "F")] = f_path
                                entry["front"] = {"quality": q_f, "file": f_fname}
                                kb_f = f_path.stat().st_size / 1024.0 if f_path.exists() else 0.0
                                f_status = f"{q_f}-Tier OK ({kb_f:.1f}KB)"
                            elif f_out.get("confirmed_404"):
                                miss_f += 1
                                dead_fronts[cid] = time.time()
                                dead_fronts_dirty = True
                                f_status = "Miss(404->Cached)"
                            else:
                                err_c = int(f_out.get("status_code", 0) or 0)
                                f_status = f"Err(HTTP {err_c}-Uncached)" if err_c > 0 else "Err(Net-Uncached)"
                        else:
                            f_status = "NoURL"

                        if existing_b:
                            skip_b += 1
                            b_status = existing_b
                        elif not has_front:
                            skip_back_only += 1
                            b_status = "Skip(NoFrontImage)"
                        elif not (url_rep_b or url_std_b):
                            skip_noback += 1
                            b_status = "Skip(NoBackOnTCDB)"
                        elif cid in dead_backs or normalize_numeric_tcdb_cid(cid) in dead_backs:
                            skip_noback += 1
                            b_status = "Skip(DeadBackCached)"
                        else:
                            q_b = _download_single_template_side(
                                req_session, url_rep_b, url_std_b, referer, b_path,
                                set_key=folder_name, thumb_url=b_thumb_u, preferred_tier=b_hint_t or q_f_winner,
                                outcome_out=b_out, circuit_breaker=cb,
                            )
                            if q_b:
                                dl_b += 1
                                card_downloaded = True
                                disk_cid_index[(cid, "B")] = b_path
                                entry["back"] = {"quality": q_b, "file": b_fname}
                                kb_b = b_path.stat().st_size / 1024.0 if b_path.exists() else 0.0
                                b_status = f"{q_b}-Tier OK ({kb_b:.1f}KB)"
                            elif b_out.get("confirmed_404"):
                                miss_b += 1
                                dead_backs[cid] = time.time()
                                dead_backs_dirty = True
                                b_status = "Miss(404->Cached)"
                            else:
                                err_c = int(b_out.get("status_code", 0) or 0)
                                b_status = f"Err(HTTP {err_c}-Uncached)" if err_c > 0 else "Err(Net-Uncached)"

                        if will_hit_network:
                            need_card_jitter = True

                        if f_out.get("transient_overload") or b_out.get("transient_overload"):
                            consecutive_overload_cards += 1
                            if consecutive_overload_cards >= 3:
                                log_msg("⏳ [Origin Overload Breather] 3 consecutive cards hit HTTP 503/timeout — resting 15s...")
                                need_card_jitter = False
                                consecutive_overload_cards = 0
                                if not cb.interruptible_sleep(15.0, reason="503/timeout breather"):
                                    stop_run = True
                                    break
                        elif f_out.get("outcome") in ("ok", "404") or b_out.get("outcome") in ("ok", "404"):
                            consecutive_overload_cards = 0

                        if not f_status.startswith("Skip") or not b_status.startswith("Skip") or sub_pos == sub_tot or c_idx % 25 == 0:
                            emit_progress(
                                active_set_name=chk_title,
                                active_set_key=set_stats_key,
                                set_index=idx,
                                total_sets=total_sets,
                                completed_cards=completed_cards_all,
                                total_cards=total_cards_all,
                                completed_subsets=completed_subsets_all,
                                total_subsets=max(1, total_subsets_all),
                                sub_name=sub_clean,
                                sub_current=sub_pos,
                                sub_total=sub_tot,
                                sub_start_epoch=sub_t0,
                                current_item=f"[Card #{cnum}] {plr} [{sub_clean} | CID {cid}] -> F:{f_status} | B:{b_status}",
                                mode_key="images_only",
                                est_remaining_dl_cards=est_rem_dl_all,
                            )

                        if not f_status.startswith("Skip") or not b_status.startswith("Skip") or c_idx % 50 == 0 or c_idx == total_cards_set:
                            log_msg(f"  [{c_idx}/{total_cards_set}] #{cnum} {plr} [{sub_clean} | CID {cid}] -> Front: {f_status} | Back: {b_status}")

                        if c_idx % 50 == 0:
                            save_catalog(folder_name, catalog)
                            if dead_backs_dirty:
                                save_dead_backs_cache(dead_backs)
                                dead_backs_dirty = False
                            if dead_fronts_dirty:
                                save_dead_fronts_cache(dead_fronts)
                                dead_fronts_dirty = False

                        if card_downloaded:
                            downloaded_cards_this_run += 1
                            if max_cards_per_run is not None and max_cards_per_run > 0 and downloaded_cards_this_run >= max_cards_per_run:
                                cap_msg = f"⏸️ Reached max_cards_per_run cap ({downloaded_cards_this_run:,} downloaded cards) — stopping run cleanly."
                                log_msg(cap_msg)
                                emit_progress(current_item=cap_msg)
                                stop_run = True
                                break
                            if breather_every_cards > 0 and downloaded_cards_this_run % breather_every_cards == 0:
                                breather_s = random.uniform(float(breather_duration_range[0]), float(breather_duration_range[1]))
                                b_msg = f"☕ Human-like breather: {breather_s / 60.0:.1f}m after {downloaded_cards_this_run:,} downloaded cards..."
                                log_msg(b_msg)
                                emit_progress(current_item=b_msg)
                                need_card_jitter = False
                                if not cb.interruptible_sleep(breather_s, reason="pacing breather"):
                                    stop_run = True
                                    break

                    if not stop_run:
                        completed_subsets_all += 1
                        learner.record_subset_duration(
                            "images_only",
                            time.time() - sub_t0,
                            card_count=sub_tot,
                            downloaded_cards=max(0, dl_f - sub_dl_start),
                            skipped_cards=max(0, skip_f - sub_skip_start),
                        )
            except CloudflareEdgeBlockPaused:
                save_catalog(folder_name, catalog)
                if dead_backs_dirty:
                    save_dead_backs_cache(dead_backs)
                if dead_fronts_dirty:
                    save_dead_fronts_cache(dead_fronts)
                raise

            save_catalog(folder_name, catalog)
            if dead_backs_dirty:
                save_dead_backs_cache(dead_backs)
            if dead_fronts_dirty:
                save_dead_fronts_cache(dead_fronts)
            sync_set_library_download_status(target_set_name=chk_title, rebuild_master_checklist=True)
            learner.record_set_run_timing(
                set_key=set_stats_key,
                mode_key="images_only",
                duration_sec=time.time() - set_t0,
                cards_processed=total_cards_set,
                images_downloaded=dl_f + dl_b,
                images_skipped=skip_f + skip_b + skip_noback,
                set_name=chk_title,
            )
            if set_url in meta_map:
                meta_map[set_url]["last_scraped"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_all_tracked_sets(meta_map)
            log_msg(
                f"  ✅ Finished '{folder_name}': Downloaded {dl_f:,} Fronts & {dl_b:,} Backs | "
                f"Skipped Existing: {skip_f:,}F/{skip_b:,}B | Back-Only Skipped: {skip_back_only:,} | "
                f"NoBack/Cached Skipped: {skip_noback:,} | 404 Misses: {miss_f:,}F/{miss_b:,}B"
            )
    finally:
        cleanup_orphaned_drivers()


def mode_checklist_and_images_card_by_card(
    target_queue: Optional[dict[str, str]] = None,
    clean_slate_reset: bool = False,
    cooldown_seconds: int = 5,
    incremental: bool = True,
    force_refresh: bool = False,
):
    """
    COMBINED CARD-BY-CARD PIPELINE (Button #4):
    For each tracked set, scrapes TCDB checklist pages and immediately downloads each card's
    available Front (`_F.jpg`) and Back (`_B.jpg`) images card-by-card into `D:\\Tabulas Set Library\\<Set>\\`,
    building the 11-column checklist CSV and catalog simultaneously.
    """
    ensure_directories()
    meta_map = load_tracked_sets_meta(prioritize=True)
    queue = target_queue or {u: m["folder_name"] for u, m in meta_map.items()}
    if not queue:
        log_msg("[!] No sets in queue for Combined Checklist + Card-by-Card Image build.")
        return

    if clean_slate_reset:
        archive_existing_checklists_for_clean_slate()

    log_msg(f"⚡ Launching Combined Card-by-Card Checklist + Front/Back Image Scraper for {len(queue)} set(s)...")
    req_session = connect_session(target_domain=BASE_URL, require_image_probe=True)
    queue_items = list(queue.items())
    total_sets = len(queue_items)

    try:
        pre = prescan_queue_card_metrics(req_session, queue_items, mode_key="checklist_and_images")
        p_ctx = {
            "set_index": 0,
            "total_sets": total_sets,
            "completed_cards": 0,
            "total_cards": pre["total_cards"],
            "completed_subsets": 0,
            "total_subsets": pre["total_subsets"],
            "est_remaining_dl_cards": pre["est_remaining_dl_cards"],
            "mode_key": "checklist_and_images",
        }
        for idx, (set_url, folder_name) in enumerate(queue_items, 1):
            set_m = (pre["per_set_metrics"] or {}).get(set_url, {})
            p_ctx["set_index"] = idx
            p_ctx["active_set_base_cards"] = set_m.get("base_cards", 0)
            p_ctx["active_set_subset_counts"] = set_m.get("subset_card_counts", {})
            try:
                rem_queue = {u_r: fn_r for u_r, fn_r in queue_items[idx - 1 :]}
                RESUME_FILE.write_text(json.dumps({"mode": "checklist_and_images", "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "remaining_queue": rem_queue}, indent=2), encoding="utf-8")
            except Exception:
                pass

            chk_title = canonicalize_checklist_set_title(folder_name.replace("_", " ").strip())
            set_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
            set_dir.mkdir(parents=True, exist_ok=True)
            log_msg(f"[{idx}/{total_sets}] Combined Card-by-Card Scrape & Image Download: '{chk_title}' ({set_m.get('total_cards', 0):,} est. cards) -> {set_dir}")

            df_set, _ = scrape_tcdb_checklist_set(
                req_session,
                set_url,
                chk_title,
                folder_name=folder_name,
                include_inserts=True,
                download_images_card_by_card=True,
                set_dir=set_dir,
                prefetched_inserts=pre["prefetched_inserts"].get(set_url),
                prefetched_insert_counts=pre["prefetched_insert_counts"].get(set_url),
                prefetched_base_html=pre["prefetched_base_html"].get(set_url),
                progress_ctx=p_ctx,
                incremental=incremental,
                force_refresh=force_refresh,
            )
            if not df_set.empty:
                _merge_set_checklist_into_master(df_set, chk_title, replace_set_cleanly=True)
            sync_set_library_download_status(target_set_name=chk_title, rebuild_master_checklist=True)

            if set_url in meta_map:
                meta_map[set_url]["last_scraped"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_all_tracked_sets(meta_map)

            if idx < total_sets and cooldown_seconds > 0:
                time.sleep(max(2, int(cooldown_seconds)))
        clear_resume_state()
    finally:
        cleanup_orphaned_drivers()

    from Core.database import load_master_checklist
    load_master_checklist(CHECKLIST_PATH, force_reload=True)
    log_msg(f"🎉 Completed Combined Card-by-Card Checklist + Images for {total_sets} set(s)!")


def mode_image_update_pipeline(target_queue: Optional[dict[str, str]] = None):
    """
    FAST HTML-GUIDED HIGH-RES R-TIER UPGRADE PIPELINE:
      1. Identifies every locally-saved S-Tier `(cid, 'F'|'B')` image in `<set>_catalog.json`.
      2. Re-scans the set's TCDB checklist HTML pages (~1 request per 100 cards!) to detect
         which S-Tier CIDs now have a high-res `Rep` thumbnail uploaded on TCDB.
      3. Surgically downloads ONLY those newly upgraded `RepFr.jpg`/`RepBk.jpg` images in-place,
         checking a 3,000-card set in ~2 minutes instead of 4+ hours!
    """
    ensure_directories()
    meta_map = load_tracked_sets_meta(prioritize=True)
    queue = target_queue or {u: m["folder_name"] for u, m in meta_map.items()}
    if not queue:
        log_msg("[!] No sets in queue for High-Res R-Tier Upgrade.")
        return

    req_session = connect_session(target_domain=BASE_URL, require_image_probe=True)
    total_sets = len(queue)
    try:
        for idx, (set_url, folder_name) in enumerate(queue.items(), 1):
            chk_title = canonicalize_checklist_set_title(folder_name.replace("_", " ").strip())
            catalog = load_catalog(folder_name)
            set_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
            disk_cid_index = _index_existing_set_dir_by_cid(set_dir)

            # Collect all locally-saved S-Tier (cid, side) entries eligible for R-Tier upgrade
            s_tier_targets: dict[tuple[str, str], tuple[str, dict, Path]] = {}
            for sub_name, cards in catalog.items():
                if not isinstance(cards, dict):
                    continue
                for cid, entry in cards.items():
                    if str(cid).startswith("_") or not isinstance(entry, dict):
                        continue
                    cid_n = normalize_numeric_tcdb_cid(cid)
                    for side_key, side_code, file_key in (("front", "F", "front_file"), ("back", "B", "back_file")):
                        side_meta = entry.get(side_key)
                        if isinstance(side_meta, dict) and side_meta.get("quality") == "S":
                            target_p = disk_cid_index.get((cid_n, side_code)) or (set_dir / str(entry.get(file_key) or ""))
                            if target_p.name and target_p.exists():
                                s_tier_targets[(cid_n, side_code)] = (sub_name, entry, target_p)

            if not s_tier_targets:
                log_msg(f"[{idx}/{total_sets}] [SKIP] '{folder_name}': 0 local S-Tier images eligible for R-Tier upgrade.")
                continue

            log_msg(
                f"[{idx}/{total_sets}] 🔄 HTML-Guided High-Res Upgrade for '{folder_name}': "
                f"Checking {len(s_tier_targets):,} local S-Tier image(s) via TCDB checklist thumbnails..."
            )
            # Restrict HTML re-scan strictly to subsets that actually contain local S-Tier images
            s_tier_sub_keys = {canonical_subset_key(sub_n) for (sub_n, _, _) in s_tier_targets.values()}
            sub_urls_by_key: dict[str, str] = {}
            cp = load_set_checkpoint(chk_title, alt_folder_name=folder_name)
            for cp_ent in (cp.get("subsets") or {}).values():
                if isinstance(cp_ent, dict) and cp_ent.get("subset_url"):
                    sub_urls_by_key[canonical_subset_key(str(cp_ent.get("subset_name") or ""))] = str(cp_ent["subset_url"])
            for sub_n, cards in catalog.items():
                if not isinstance(cards, dict):
                    continue
                sk_c = canonical_subset_key(str(sub_n))
                if sk_c not in sub_urls_by_key:
                    for cid_c, ent_c in cards.items():
                        if not str(cid_c).startswith("_") and isinstance(ent_c, dict) and (ent_c.get("subset_url") or ent_c.get("referer")):
                            sub_urls_by_key[sk_c] = str(ent_c.get("subset_url") or ent_c.get("referer")).split("?")[0]
                            break

            if s_tier_sub_keys and all(sk in sub_urls_by_key for sk in s_tier_sub_keys):
                fresh_rows = []
                for sk in sorted(s_tier_sub_keys):
                    sub_lbl_orig = next((sn for (sn, _, _) in s_tier_targets.values() if canonical_subset_key(sn) == sk), sk)
                    fresh_rows.extend(_scrape_tcdb_subset_checklist_pages(req_session, sub_urls_by_key[sk], subset_name=sub_lbl_orig, checklist_set_name=chk_title))
            else:
                _, fresh_rows = scrape_tcdb_checklist_set(
                    req_session, set_url, chk_title, folder_name=folder_name, include_inserts=True, download_images_card_by_card=False
                )

            upgraded = 0
            checked_hits = 0
            for r in fresh_rows:
                cid_n = normalize_numeric_tcdb_cid(r.get("TCDB_CID") or "")
                if not cid_n or cid_n == "0":
                    continue
                referer = str(r.get("_referer") or set_url)

                for side_code, side_key, thumb_field, url_side in (
                    ("F", "front", "_front_thumb", "Fr"),
                    ("B", "back", "_back_thumb", "Bk"),
                ):
                    if (cid_n, side_code) not in s_tier_targets:
                        continue
                    if side_code == "B" and (cid_n, "F") not in disk_cid_index and not str(r.get("_front_thumb") or "").strip():
                        continue
                    checked_hits += 1
                    thumb_u = str(r.get(thumb_field) or "").strip()
                    if thumb_u and "rep" in thumb_u.lower():
                        sub_name, entry, target_p = s_tier_targets[(cid_n, side_code)]
                        rep_url = transform_thumb_to_large_urls(thumb_u, url_side).get("rep", "")
                        if rep_url:
                            q_new = _download_single_template_side(
                                req_session,
                                rep_url,
                                "",
                                referer,
                                target_p,
                                set_key=folder_name,
                                thumb_url=thumb_u,
                                force_rep_first=True,
                            )
                            if q_new == "R":
                                entry[side_key]["quality"] = "R"
                                upgraded += 1
                                kb_n = target_p.stat().st_size / 1024.0 if target_p.exists() else 0.0
                                log_msg(
                                    f"  ✨ [UPGRADED S->R] #{entry.get('card_number','')} {entry.get('player','')} "
                                    f"[{sub_name} | CID {cid_n} | {side_code}] -> {kb_n:.1f}KB"
                                )

            save_catalog(folder_name, catalog)
            if set_url in meta_map:
                meta_map[set_url]["last_upgraded"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_all_tracked_sets(meta_map)
            log_msg(
                f"  ✅ '{folder_name}' Upgrade Complete: Inspected {checked_hits:,} S-Tier image(s), "
                f"surgically upgraded {upgraded:,} to High-Res R-Tier!"
            )
    finally:
        cleanup_orphaned_drivers()


def mode_missing_back_audit(target_queue: Optional[dict[str, str]] = None):
    """
    Audits `D:\\Tabulas Set Library` and `Set_Checklists/*.csv` for any card where
    `Front_Downloaded == 'Yes'` and `Back_Downloaded == 'No'`, using `DEAD_BACKS_CACHE_FILE`
    (30-day TTL) so genuine 404 backs are never re-probed repeatedly!
    """
    ensure_directories()
    sync_set_library_download_status(rebuild_master_checklist=True)

    meta_map = load_tracked_sets_meta(prioritize=True)
    queue = target_queue or {u: m["folder_name"] for u, m in meta_map.items()}
    if not queue:
        return

    dead_backs = load_dead_backs_cache()
    dead_backs_dirty = False

    # Zero-network pre-scan: only open TCDB session if at least 1 card has a known back URL on TCDB
    eligible_total = 0
    for set_url, folder_name in queue.items():
        catalog_pre = load_catalog(folder_name)
        set_dir_pre = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
        disk_pre = _index_existing_set_dir_by_cid(set_dir_pre)
        for _, cards_p in catalog_pre.items():
            if not isinstance(cards_p, dict):
                continue
            for cid_p, ent_p in cards_p.items():
                if str(cid_p).startswith("_") or not isinstance(ent_p, dict):
                    continue
                cid_n_p = normalize_numeric_tcdb_cid(cid_p)
                f_f = str(ent_p.get("front_file") or "")
                b_f = str(ent_p.get("back_file") or "")
                has_f = (cid_n_p, "F") in disk_pre or (f_f and (set_dir_pre / f_f).exists())
                has_b = (cid_n_p, "B") in disk_pre or (b_f and (set_dir_pre / b_f).exists())
                has_b_url = bool(ent_p.get("url_rep_back") or ent_p.get("url_std_back"))
                if has_f and not has_b and b_f and has_b_url and cid_n_p not in dead_backs:
                    eligible_total += 1
    if eligible_total == 0:
        log_msg(f"✅ [FAST-SKIP] Missing Back Audit: 0 eligible cards with known TCDB back URLs across {len(queue)} set(s).")
        return

    req_session = connect_session(target_domain=BASE_URL, require_image_probe=True)
    cb = CloudflareImageCircuitBreaker(stop_check=is_stop_requested)
    try:
        for idx, (set_url, folder_name) in enumerate(queue.items(), 1):
            log_msg(f"[{idx}/{len(queue)}] Auditing Missing Back Images for '{folder_name}'...")
            catalog = load_catalog(folder_name)
            set_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
            disk_cid_index = _index_existing_set_dir_by_cid(set_dir)
            fetched_backs = 0
            cached_dead_skips = 0
            new_dead_recorded = 0

            try:
                for sub_name, cards in catalog.items():
                    if not isinstance(cards, dict):
                        continue
                    for cid, entry in cards.items():
                        if str(cid).startswith("_") or not isinstance(entry, dict):
                            continue
                        cid_n = normalize_numeric_tcdb_cid(cid)
                        f_file = str(entry.get("front_file") or "")
                        b_file = str(entry.get("back_file") or "")
                        has_front = (cid_n, "F") in disk_cid_index or (f_file and (set_dir / f_file).exists())
                        has_back = (cid_n, "B") in disk_cid_index or (b_file and (set_dir / b_file).exists())
                        if not (has_front and not has_back and b_file):
                            continue
                        if cid_n in dead_backs:
                            cached_dead_skips += 1
                            continue

                        url_rep_b = str(entry.get("url_rep_back") or "")
                        url_std_b = str(entry.get("url_std_back") or "")
                        if url_rep_b or url_std_b:
                            pref_t = str(entry.get("front", {}).get("quality") or "") if isinstance(entry.get("front"), dict) else ""
                            b_out: dict = {}
                            q_b = _download_single_template_side(
                                req_session,
                                url_rep_b,
                                url_std_b,
                                entry.get("referer", set_url),
                                set_dir / b_file,
                                set_key=folder_name,
                                thumb_url=str(entry.get("back_thumb") or ""),
                                preferred_tier=str(entry.get("back_tier_hint") or pref_t),
                                outcome_out=b_out,
                                circuit_breaker=cb,
                            )
                            if q_b:
                                entry["back"] = {"quality": q_b, "file": b_file}
                                fetched_backs += 1
                                log_msg(f"  + [BACK OK] #{entry.get('card_number','')} {entry.get('player','')} [{sub_name} | CID {cid_n}] ({q_b}-Tier)")
                            elif b_out.get("confirmed_404"):
                                dead_backs[cid_n] = time.time()
                                dead_backs_dirty = True
                                new_dead_recorded += 1
            except CloudflareEdgeBlockPaused:
                save_catalog(folder_name, catalog)
                if dead_backs_dirty:
                    save_dead_backs_cache(dead_backs)
                    dead_backs_dirty = False
                raise

            save_catalog(folder_name, catalog)
            if dead_backs_dirty:
                save_dead_backs_cache(dead_backs)
                dead_backs_dirty = False
            log_msg(
                f"  ✅ '{folder_name}': Fetched {fetched_backs:,} missing Back(s) | "
                f"Skipped {cached_dead_skips:,} dead-cached | Cached {new_dead_recorded:,} new 404 backs (30d TTL)."
            )
    finally:
        cleanup_orphaned_drivers()

    sync_set_library_download_status(rebuild_master_checklist=True)


def _format_eta_compact(seconds: float) -> str:
    sec = max(0, int(round(seconds)))
    if sec < 60:
        return f"{sec}s"
    mins, rem_s = divmod(sec, 60)
    if mins < 60:
        return f"{mins}m {rem_s}s" if rem_s else f"{mins}m"
    hrs, rem_m = divmod(mins, 60)
    return f"{hrs}h {rem_m}m" if rem_m else f"{hrs}h"


_PLAN_CACHE_LOCK = threading.RLock()
_PLAN_SET_STATS_CACHE: dict[tuple, dict] = {}
_PLAN_MODES_CANON = ("checklist_only", "checklist_and_images", "images_only", "upgrade", "missing_back")


def _stat_mtime_size(path: Optional[Path]) -> tuple[float, int]:
    if path is None:
        return 0.0, 0
    try:
        st = path.stat()
        return float(st.st_mtime), int(st.st_size)
    except Exception:
        return 0.0, 0


def _fast_index_set_dir_by_cid_scandir(set_dir: Path) -> tuple[set[tuple[str, str]], set[str]]:
    """
    Uses `os.scandir()` (zero `Path.glob()`/`rglob()` overhead) to index all `.jpg`
    reference images in `set_dir` into `(cid_side_set, filename_set)`.
    """
    cid_side_set: set[tuple[str, str]] = set()
    filenames_set: set[str] = set()
    try:
        with os.scandir(set_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                name = entry.name
                if not name.lower().endswith(".jpg"):
                    continue
                filenames_set.add(name)
                parsed = parse_unified_card_filename(name)
                if parsed and parsed.get("is_template") and parsed.get("cid"):
                    cid_side_set.add((normalize_numeric_tcdb_cid(parsed["cid"]), str(parsed.get("side") or "F").upper()))
    except Exception:
        pass
    return cid_side_set, filenames_set


def _fast_scan_set_csv_for_plan(csv_path: Optional[Path]) -> dict[str, dict]:
    """
    Lightweight `csv.reader` streamer (no `pandas.read_csv` overhead) that scans
    `Set_Checklists/*.csv` once and returns per-subset counts, populated CID counts,
    and canonical `rows_sha256` matching `compute_subset_rows_checksum()`.
    """
    if csv_path is None or not csv_path.exists():
        return {}
    by_key: dict[str, dict] = {}
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                return {}
            col_idx = {str(h).strip(): i for i, h in enumerate(header)}
            idx_sub = col_idx.get("Subset")
            if idx_sub is None:
                return {}
            idx_cnum = col_idx.get("Card Number")
            idx_plr = col_idx.get("Player")
            idx_cid = col_idx.get("TCDB_CID")

            for row in reader:
                if not row or idx_sub >= len(row):
                    continue
                sub_disp = str(row[idx_sub] or "Base").strip() or "Base"
                sk = canonical_subset_key(sub_disp)
                cnum = str(row[idx_cnum] if idx_cnum is not None and idx_cnum < len(row) else "").strip().lstrip("#")
                cid = str(row[idx_cid] if idx_cid is not None and idx_cid < len(row) else "").strip()
                if cid == "0":
                    cid = ""
                plr = str(row[idx_plr] if idx_plr is not None and idx_plr < len(row) else "").strip()

                bucket = by_key.get(sk)
                if bucket is None:
                    bucket = {"count": 0, "populated_cids": 0, "tuples": []}
                    by_key[sk] = bucket
                bucket["count"] += 1
                if cid and cid not in ("nan", "None"):
                    bucket["populated_cids"] += 1
                bucket["tuples"].append((cnum, cid, plr, sk))
    except Exception:
        return {}

    for bucket in by_key.values():
        t_list = bucket.pop("tuples", [])
        t_list.sort()
        payload = json.dumps(t_list, separators=(",", ":"), ensure_ascii=False)
        bucket["rows_sha256"] = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return by_key


def _resolve_plan_file_paths(chk_title: str, folder_name: str) -> tuple[Optional[Path], Optional[Path], Optional[Path], Path]:
    csv_p = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(chk_title)}.csv"
    if not csv_p.exists() and folder_name:
        alt_csv = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(folder_name)}.csv"
        csv_p = alt_csv if alt_csv.exists() else None
    elif not csv_p.exists():
        csv_p = None

    cp_p = checkpoint_file_path(chk_title)
    if not cp_p.exists() and folder_name:
        alt_cp = checkpoint_file_path(folder_name)
        cp_p = alt_cp if alt_cp.exists() else None
    elif not cp_p.exists():
        cp_p = None

    cat_fname = f"{sanitize_filename_part(folder_name)}_catalog.json"
    cat_p: Optional[Path] = None
    for cand_dir in (_catalog_dir(), SET_LIBRARY_CACHE_DIR):
        cand = cand_dir / cat_fname
        if cand.exists():
            cat_p = cand
            break

    set_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(folder_name)
    return csv_p, cp_p, cat_p, set_dir


def _compute_set_plan_metrics_cached(
    set_url: str,
    folder_name: str,
    chk_title: str,
    dead_backs: dict[str, float],
    dead_fronts: dict[str, float],
    dead_backs_mtime: float,
    dead_fronts_mtime: float,
    force_refresh: bool,
) -> dict:
    """
    Scans a single set's CSV, checkpoint JSON, catalog JSON, and Reference_Library folder
    ONCE and computes per-set metrics for all 5 modes (`checklist_only`, `checklist_and_images`,
    `images_only`, `upgrade`, `missing_back`), caching the result by file mtimes & sizes.
    """
    csv_p, cp_p, cat_p, set_dir = _resolve_plan_file_paths(chk_title, folder_name)
    csv_mt, csv_sz = _stat_mtime_size(csv_p)
    cp_mt, _ = _stat_mtime_size(cp_p)
    cat_mt, _ = _stat_mtime_size(cat_p)
    ref_mt, _ = _stat_mtime_size(set_dir if set_dir.exists() else None)

    cache_key = (
        folder_name,
        chk_title,
        csv_mt,
        csv_sz,
        cp_mt,
        cat_mt,
        ref_mt,
        dead_backs_mtime,
        dead_fronts_mtime,
        bool(force_refresh),
    )
    with _PLAN_CACHE_LOCK:
        cached = _PLAN_SET_STATS_CACHE.get(cache_key)
        if cached is not None:
            return cached

    cp = {} if force_refresh else load_set_checkpoint(chk_title, alt_folder_name=folder_name)
    cp_subsets = cp.get("subsets") if isinstance(cp.get("subsets"), dict) else {}
    csv_by_key = _fast_scan_set_csv_for_plan(csv_p)
    catalog = load_catalog(folder_name)
    disk_cid_side, disk_names = _fast_index_set_dir_by_cid_scandir(set_dir)

    complete_keys: set[str] = set()
    if not force_refresh:
        for cp_ent in cp_subsets.values():
            if not isinstance(cp_ent, dict):
                continue
            sk = canonical_subset_key(str(cp_ent.get("subset_name") or ""))
            loc_info = csv_by_key.get(sk)
            exp_c = int(cp_ent.get("tcdb_reported_count") or cp_ent.get("expected_cards") or 0)
            deduped_c = int(cp_ent.get("local_deduped_count") or cp_ent.get("scraped_cards") or 0)
            count_ok = (exp_c <= 0 or (loc_info and (loc_info["count"] == exp_c or (deduped_c > 0 and loc_info["count"] == deduped_c))))
            if (
                loc_info
                and cp_ent.get("status") == "complete"
                and count_ok
                and loc_info["rows_sha256"] == cp_ent.get("rows_sha256")
            ):
                complete_keys.add(sk)

        for sk, loc_info in csv_by_key.items():
            if sk in complete_keys or loc_info["count"] <= 0:
                continue
            if loc_info["populated_cids"] > 0 and loc_info["populated_cids"] >= int(loc_info["count"] * 0.95):
                complete_keys.add(sk)

    all_known_keys = set(csv_by_key.keys()) | {
        canonical_subset_key(str(k)) for k in catalog.keys() if isinstance(catalog.get(k), dict)
    }

    if not all_known_keys:
        chk_skip_subs = 0
        chk_upd_subs = 1
        chk_reqs = 3
    else:
        chk_skip_subs = len(complete_keys)
        chk_upd_subs = max(0, len(all_known_keys) - len(complete_keys))
        chk_reqs = 1 + (chk_upd_subs * 2) + (1 if force_refresh else 0)

    # Single pass over catalog to accumulate image stats for all image-aware modes
    img_disk_ok = 0
    ci_miss_f = 0
    ci_miss_b = 0
    ci_dead_skip = 0
    ci_img_reqs = 0
    mb_miss_b = 0
    mb_dead_skip = 0
    mb_reqs = 0
    upg_s_fronts = 0
    upg_s_backs = 0
    upg_s_subsets = 0

    for _, cards_d in catalog.items():
        if not isinstance(cards_d, dict):
            continue
        sub_has_s_tier = False
        for cid, ent in cards_d.items():
            if str(cid).startswith("_") or not isinstance(ent, dict):
                continue
            cid_n = normalize_numeric_tcdb_cid(cid)
            f_file = str(ent.get("front_file") or "")
            b_file = str(ent.get("back_file") or "")
            has_f_disk = (cid_n, "F") in disk_cid_side or (f_file and f_file in disk_names)
            has_b_disk = (cid_n, "B") in disk_cid_side or (b_file and b_file in disk_names)
            has_f_url = bool(ent.get("url_rep_front") or ent.get("url_std_front"))
            has_b_url = bool(ent.get("url_rep_back") or ent.get("url_std_back"))

            if has_f_disk:
                img_disk_ok += 1
            if has_b_disk:
                img_disk_ok += 1

            is_dead_f = cid_n in dead_fronts or str(cid) in dead_fronts
            is_dead_b = cid_n in dead_backs or str(cid) in dead_backs

            if has_f_url and not has_f_disk:
                if is_dead_f:
                    ci_dead_skip += 1
                else:
                    ci_miss_f += 1
                    ci_img_reqs += 1 if (ent.get("front_tier_hint") or ent.get("front_thumb")) else 2
            if (has_f_disk or (has_f_url and not is_dead_f)) and has_b_url and not has_b_disk:
                if is_dead_b:
                    ci_dead_skip += 1
                else:
                    ci_miss_b += 1
                    ci_img_reqs += 1 if (ent.get("back_tier_hint") or ent.get("back_thumb")) else 2

            if has_f_disk and not has_b_disk and has_b_url:
                if is_dead_b:
                    mb_dead_skip += 1
                else:
                    mb_miss_b += 1
                    mb_reqs += 1 if (ent.get("back_tier_hint") or ent.get("back_thumb")) else 2

            for s_key in ("front", "back"):
                s_meta = ent.get(s_key)
                if isinstance(s_meta, dict) and s_meta.get("quality") == "S":
                    sub_has_s_tier = True
                    if s_key == "front":
                        upg_s_fronts += 1
                    else:
                        upg_s_backs += 1
        if sub_has_s_tier:
            upg_s_subsets += 1

    per_mode = {
        "checklist_only": {
            "subsets_skipped": chk_skip_subs,
            "subsets_to_update": chk_upd_subs,
            "missing_fronts": 0,
            "missing_backs": 0,
            "already_on_disk": img_disk_ok,
            "dead_cached_skipped": 0,
            "estimated_requests": chk_reqs,
        },
        "checklist_and_images": {
            "subsets_skipped": chk_skip_subs,
            "subsets_to_update": chk_upd_subs,
            "missing_fronts": ci_miss_f,
            "missing_backs": ci_miss_b,
            "already_on_disk": img_disk_ok,
            "dead_cached_skipped": ci_dead_skip,
            "estimated_requests": chk_reqs + ci_img_reqs,
        },
        "images_only": {
            "subsets_skipped": 0,
            "subsets_to_update": 0,
            "missing_fronts": ci_miss_f,
            "missing_backs": ci_miss_b,
            "already_on_disk": img_disk_ok,
            "dead_cached_skipped": ci_dead_skip,
            "estimated_requests": ci_img_reqs,
        },
        "upgrade": {
            "subsets_skipped": max(0, len(all_known_keys) - upg_s_subsets),
            "subsets_to_update": upg_s_subsets,
            "missing_fronts": upg_s_fronts,
            "missing_backs": upg_s_backs,
            "already_on_disk": img_disk_ok,
            "dead_cached_skipped": 0,
            "estimated_requests": upg_s_subsets * 2,
        },
        "missing_back": {
            "subsets_skipped": 0,
            "subsets_to_update": 0,
            "missing_fronts": 0,
            "missing_backs": mb_miss_b,
            "already_on_disk": img_disk_ok,
            "dead_cached_skipped": mb_dead_skip,
            "estimated_requests": mb_reqs,
        },
    }
    res_obj = {
        "set_url": set_url,
        "folder_name": folder_name,
        "set_name": chk_title,
        "per_mode": per_mode,
    }
    with _PLAN_CACHE_LOCK:
        if len(_PLAN_SET_STATS_CACHE) >= 500:
            _PLAN_SET_STATS_CACHE.clear()
        _PLAN_SET_STATS_CACHE[cache_key] = res_obj
    return res_obj


def build_scraper_execution_plan(
    target_queue: Optional[dict[str, str]] = None,
    mode_key: str = "checklist_only",
    force_refresh: bool = False,
    all_modes: bool = False,
) -> dict:
    """
    Purely local single-pass dry-run execution planner (0 TCDB HTTP requests):
    Inspects `Set_Checklists/*.csv` (via `csv.reader`), `<set>_checkpoint.json`,
    `<set>_catalog.json`, `Reference_Library` images (via `os.scandir()`),
    `dead_backs_cache`, `dead_fronts_cache`, and `AdaptiveRateLearner` pacing once per set
    using an mtime/size-keyed in-memory cache.
    When `all_modes=True`, returns `{"plan": selected_plan, "plans_by_mode": {...}}`
    for instant zero-API mode-tab switching in the UI.
    """
    ensure_directories()
    meta_map = load_tracked_sets_meta(prioritize=True)
    queue = target_queue or {u: m["folder_name"] for u, m in meta_map.items()}
    dead_backs = load_dead_backs_cache()
    dead_fronts = load_dead_fronts_cache()
    db_mt, _ = _stat_mtime_size(DEAD_BACKS_CACHE_FILE if DEAD_BACKS_CACHE_FILE.exists() else None)
    df_mt, _ = _stat_mtime_size(DEAD_FRONTS_CACHE_FILE if DEAD_FRONTS_CACHE_FILE.exists() else None)
    learner = get_rate_learner()
    tcdb_ep = (learner._state.get("endpoints") or {}).get("tcdb_domain") or {}
    safe_rpm = max(8.0, float(tcdb_ep.get("safe_rpm", 23.5) or 23.5))

    agg = {
        mk: {
            "subsets_unchanged_skipped": 0,
            "subsets_to_update": 0,
            "missing_front_images_queued": 0,
            "missing_back_images_queued": 0,
            "already_on_disk_images": 0,
            "skipped_dead_cached": 0,
            "estimated_http_requests": 0,
            "per_set": [],
        }
        for mk in _PLAN_MODES_CANON
    }

    for set_url, folder_name in queue.items():
        chk_title = canonicalize_checklist_set_title(folder_name.replace("_", " ").strip())
        set_data = _compute_set_plan_metrics_cached(
            set_url, folder_name, chk_title,
            dead_backs, dead_fronts, db_mt, df_mt, force_refresh,
        )
        for mk in _PLAN_MODES_CANON:
            m = set_data["per_mode"][mk]
            a = agg[mk]
            a["subsets_unchanged_skipped"] += m["subsets_skipped"]
            a["subsets_to_update"] += m["subsets_to_update"]
            a["missing_front_images_queued"] += m["missing_fronts"]
            a["missing_back_images_queued"] += m["missing_backs"]
            a["already_on_disk_images"] += m["already_on_disk"]
            a["skipped_dead_cached"] += m["dead_cached_skipped"]
            a["estimated_http_requests"] += m["estimated_requests"]
            set_eta_s = (m["estimated_requests"] / safe_rpm) * 60.0 if m["estimated_requests"] > 0 else 0.0
            if mk in ("checklist_only", "checklist_and_images"):
                inc_eta_s = learner.estimate_incremental_subsets_eta(mk, m["subsets_skipped"], m["subsets_to_update"])
                if m["subsets_to_update"] == 0 and m["missing_fronts"] == 0 and m["missing_backs"] == 0:
                    set_eta_s = inc_eta_s
                else:
                    set_eta_s = max(set_eta_s, inc_eta_s) if m["missing_fronts"] == 0 and m["missing_backs"] == 0 else set_eta_s + (m["subsets_skipped"] * float(learner.get_eta_priors(mk).get("ema_sec_per_skipped_subset", 0.2)))
            a["per_set"].append({
                "set_url": set_url,
                "folder_name": folder_name,
                "set_name": chk_title,
                "subsets_skipped": m["subsets_skipped"],
                "subsets_to_update": m["subsets_to_update"],
                "missing_fronts": m["missing_fronts"],
                "missing_backs": m["missing_backs"],
                "already_on_disk": m["already_on_disk"],
                "dead_cached_skipped": m["dead_cached_skipped"],
                "estimated_requests": m["estimated_requests"],
                "estimated_eta_seconds": int(round(set_eta_s)),
                "estimated_eta_display": _format_eta_compact(set_eta_s),
                "status": "Up to date" if (m["subsets_to_update"] == 0 and m["missing_fronts"] == 0 and m["missing_backs"] == 0) else "Pending work",
            })

    plans_by_mode: dict[str, dict] = {}
    for mk in _PLAN_MODES_CANON:
        a = agg[mk]
        reqs = a["estimated_http_requests"]
        total_eta_s = sum(float(ps.get("estimated_eta_seconds", 0) or 0) for ps in a["per_set"]) if a["per_set"] else ((reqs / safe_rpm) * 60.0 if reqs > 0 else 0.0)
        plans_by_mode[mk] = {
            "mode": mk,
            "force_refresh": bool(force_refresh),
            "total_sets": len(queue),
            "subsets_unchanged_skipped": a["subsets_unchanged_skipped"],
            "subsets_to_update": a["subsets_to_update"],
            "missing_front_images_queued": a["missing_front_images_queued"],
            "missing_back_images_queued": a["missing_back_images_queued"],
            "missing_images_queued": a["missing_front_images_queued"] + a["missing_back_images_queued"],
            "already_on_disk_images": a["already_on_disk_images"],
            "skipped_dead_cached": a["skipped_dead_cached"],
            "estimated_http_requests": reqs,
            "safe_rpm": round(safe_rpm, 1),
            "estimated_eta_seconds": int(round(total_eta_s)),
            "estimated_eta_display": _format_eta_compact(total_eta_s),
            "per_set": a["per_set"],
        }
    plans_by_mode["image_update"] = plans_by_mode["upgrade"]

    norm_mode = "upgrade" if mode_key == "image_update" else (mode_key if mode_key in plans_by_mode else "checklist_only")
    selected_plan = plans_by_mode[norm_mode]
    if all_modes:
        return {"plan": selected_plan, "plans_by_mode": plans_by_mode}
    return selected_plan


# ==============================================================================
# 7. RESUME STATE, CHECKLIST CLEANER & SCHEDULE CONFIG HELPERS
# ==============================================================================
def load_resume_state() -> dict:
    if not RESUME_FILE.exists():
        return {}
    try:
        data = json.loads(RESUME_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def clear_resume_state():
    if RESUME_FILE.exists():
        try:
            RESUME_FILE.unlink()
        except Exception:
            pass


def resume_saved_run():
    state = load_resume_state()
    rem = state.get("remaining_queue") or {}
    if rem:
        mode_scraping_pipeline(target_queue=rem)
        clear_resume_state()


def run_breakninja_pipeline(selected_sets: Optional[list[str]] = None):
    run_tcdb_checklist_pipeline()


def archive_existing_checklists_for_clean_slate():
    ensure_directories()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    arc_dir = ARCHIVE_CHECKLISTS_DIR / f"Pre_TCDB_Checklists_{ts}"
    arc_dir.mkdir(parents=True, exist_ok=True)
    moved_cnt = 0
    for chk_f in (CHECKLIST_PATH, CHECKLIST_BACKUP_PATH):
        if chk_f.exists():
            shutil.move(str(chk_f), str(arc_dir / chk_f.name))
            moved_cnt += 1
    if SET_CHECKLISTS_DIR.exists():
        for p in list(SET_CHECKLISTS_DIR.glob("*.csv")):
            shutil.move(str(p), str(arc_dir / p.name))
            moved_cnt += 1
    if CHECKLIST_CACHE_FILE.exists():
        try:
            CHECKLIST_CACHE_FILE.unlink()
        except Exception:
            pass
    log_msg(f"🧹 Archived {moved_cnt} existing checklist file(s) to {arc_dir} for a clean-slate build.")
    return pd.DataFrame(columns=CHECKLIST_COLUMNS)


def repair_corrupted_checklists_and_processed_cards() -> dict:
    """
    Debugged Checklist CSV Repair Engine with detailed per-file before/after diff telemetry:
      1. Strips parent-set prefixes from Subsets and restores hyphenated terms (2025-26, 8-Bit, X-Fractor, A&G).
      2. Restores authentic League Leaders (LL), Combo Player Cards (CPC), Team Cards (TC), and 2026 Topps ground-truth titles.
      3. Disambiguates Variation (VAR) rows in O(N) time without dropping distinct TCDB_CIDs.
      4. Normalizes SN99 -> #/99 across all Attributes and syncs Front_Downloaded / Back_Downloaded against D:\\Tabulas Set Library.
      5. Clears stale checklist_cache_v22.pkl so the UI and OCR immediately load the repaired data.
    """
    ensure_directories()
    csv_files = sorted(SET_CHECKLISTS_DIR.glob("*.csv")) if SET_CHECKLISTS_DIR.exists() else []
    total_files = len(csv_files)
    fixed_rows_total = 0
    grand_stats = {
        "subsets_cleaned": 0,
        "players_repaired": 0,
        "attrs_normalized": 0,
        "variations_disambiguated": 0,
    }

    log_msg(f"🔧 Starting Checklist CSV Repair across {total_files} file(s) in {SET_CHECKLISTS_DIR}...")

    for idx, csv_p in enumerate(csv_files, 1):
        try:
            df = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
            if df.empty:
                log_msg(f"[{idx}/{total_files}] Skipping empty file: {csv_p.name}")
                continue
            set_title = canonicalize_checklist_set_title(df["Set"].iloc[0] if "Set" in df.columns else csv_p.stem)
            before_cnt = len(df)
            file_stats: dict = {}
            repaired_df = apply_excel_formulas_and_combine(df.to_dict(orient="records"), set_title, stats_out=file_stats)
            repaired_df.to_csv(csv_p, index=False, encoding="utf-8-sig")
            fixed_rows_total += len(repaired_df)

            for k in grand_stats:
                grand_stats[k] += int(file_stats.get(k, 0))

            changes_total = sum(int(file_stats.get(k, 0)) for k in grand_stats) + abs(before_cnt - len(repaired_df))
            if changes_total > 0:
                log_msg(
                    f"[{idx}/{total_files}] FIXED '{set_title}' ({before_cnt:,}->{len(repaired_df):,} rows): "
                    f"Subsets={file_stats.get('subsets_cleaned',0)}, Players={file_stats.get('players_repaired',0)}, "
                    f"Attrs(#/N)={file_stats.get('attrs_normalized',0)}, Vars={file_stats.get('variations_disambiguated',0)}"
                )
            else:
                log_msg(f"[{idx}/{total_files}] Verified '{set_title}' ({len(repaired_df):,} rows) — already clean.")
        except Exception as e:
            log_msg(f"[{idx}/{total_files}] [ERROR] Failed repairing {csv_p.name}: {e}")

    # Live TCDB Self-Healing Pass: Resolve any remaining CPC / LL rows where Player == Team (or blank)
    # by querying TCDB ViewCard.cfm ONCE per unique broken (Set, Card Number) and propagating to all parallels!
    suspect_cards_by_csv: dict[Path, dict[str, dict]] = defaultdict(dict)
    tracked_meta_rep = load_tracked_sets_meta(prioritize=False)
    sid_by_set_key: dict[str, str] = {}
    for u_t, m_t in tracked_meta_rep.items():
        m_sid = re.search(r"/sid/(\d+)", str(u_t))
        if m_sid:
            sid_by_set_key[canonical_set_key(m_t.get("checklist_set_name") or m_t.get("folder_name", ""))] = m_sid.group(1)

    for csv_p in csv_files:
        try:
            df_chk = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
            if df_chk.empty or "Attributes" not in df_chk.columns:
                continue
            s_title = canonicalize_checklist_set_title(df_chk["Set"].iloc[0] if "Set" in df_chk.columns else csv_p.stem)
            set_sid = sid_by_set_key.get(canonical_set_key(s_title), "1")
            for _, r_c in df_chk.iterrows():
                a_v = str(r_c.get("Attributes") or "")
                if not re.search(r"\b(CPC|LL)\b", a_v, re.IGNORECASE):
                    continue
                p_v = str(r_c.get("Player") or "").strip()
                t_v = str(r_c.get("Team") or "").strip()
                cn_v = str(r_c.get("Card Number") or "").strip().lstrip("#")
                cid_v = normalize_numeric_tcdb_cid(r_c.get("TCDB_CID") or "")
                is_broken_cpc_ll = (
                    not p_v
                    or p_v.upper() in ("NO TEAM", "UNKNOWN", "UNKNOWN PLAYER")
                    or p_v.startswith("League Leaders #")
                    or (t_v and t_v.upper() != "NO TEAM" and norm(p_v) == norm(t_v))
                )
                if is_broken_cpc_ll and cn_v and cid_v and cid_v != "0":
                    if cn_v not in suspect_cards_by_csv[csv_p]:
                        suspect_cards_by_csv[csv_p][cn_v] = {
                            "set_title": s_title,
                            "sid": set_sid,
                            "cid": cid_v,
                            "old_player": p_v,
                            "team": t_v,
                        }
        except Exception:
            continue

    total_suspect_unique = sum(len(v) for v in suspect_cards_by_csv.values())
    if total_suspect_unique > 0:
        log_msg(
            f"🌐 Found {total_suspect_unique} unique broken CPC/LL card(s) with Team-name/blank titles — resolving true titles from TCDB..."
        )
        req_sess = None
        try:
            req_sess = connect_session(target_domain=BASE_URL, require_image_probe=False)
            resolved_cnt = 0
            lookup_idx = 0
            for csv_p, card_map in suspect_cards_by_csv.items():
                resolved_meta_for_csv: dict[str, dict] = {}
                for cn_v, info in card_map.items():
                    lookup_idx += 1
                    vc_url = f"{BASE_URL}/ViewCard.cfm/sid/{info['sid']}/cid/{info['cid']}"
                    log_msg(f"  [{lookup_idx}/{total_suspect_unique}] Looking up {info['set_title']} #{cn_v} (CID {info['cid']})...")
                    time.sleep(0.45)
                    resp = safe_get(req_sess, vc_url, silent_404=True)
                    if not resp:
                        continue
                    resp_url = str(getattr(resp, "url", "") or vc_url)
                    html_txt = decode_html_response(resp)
                    found_title = ""

                    # 1. Parse exact card heading from ViewCard page (e.g., '#52 - It Takes Two CPC - New York Mets')
                    if html_txt and BeautifulSoup is not None:
                        soup_vc = BeautifulSoup(html_txt, "html.parser")
                        for tag_vc in soup_vc.find_all(["h4", "h3", "h1", "title"]):
                            txt_vc = trim_clean(tag_vc.get_text(" ", strip=True))
                            m_hdr = re.search(
                                rf"#{re.escape(cn_v)}\s*[-–:]?\s+(.+?)(?:\s+(?:CPC|LL|TC|SN\d+|RC|ASR|SP|SSP)\b|\s+-\s+|\s*\||$)",
                                txt_vc,
                                re.IGNORECASE,
                            )
                            if m_hdr:
                                cand_t = _clean_tcdb_card_subject_title(m_hdr.group(1))
                                if cand_t and norm(cand_t) != norm(info["team"]):
                                    found_title = cand_t
                                    break

                    # 2. Fallback to ViewCard redirected URL slug ('.../2026-Topps-52-It-Takes-Two')
                    if not found_title:
                        slug_t = _extract_title_from_viewcard_href(resp_url, cn_v)
                        if slug_t and norm(slug_t) != norm(info["team"]):
                            found_title = slug_t

                    if found_title:
                        resolved_meta_for_csv[cn_v] = {
                            "title": found_title,
                            "old_player": info["old_player"],
                            "team": info["team"],
                        }
                        resolved_cnt += 1
                        log_msg(
                            f"  + [TCDB LIVE FIX] {info['set_title']} #{cn_v}: '{info['old_player']}' -> '{found_title}'"
                        )

                if resolved_meta_for_csv:
                    df_upd = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
                    updated_rows_csv = 0
                    for r_i, row_u in df_upd.iterrows():
                        cn_u = str(row_u.get("Card Number") or "").strip().lstrip("#")
                        if cn_u not in resolved_meta_for_csv:
                            continue
                        r_meta = resolved_meta_for_csv[cn_u]
                        row_attr = str(row_u.get("Attributes") or "")
                        row_plr = str(row_u.get("Player") or "").strip()
                        row_tm = str(row_u.get("Team") or "").strip()
                        # Safety guard: only propagate to rows that are CPC/LL OR match the broken old player/team
                        is_target_row = (
                            bool(re.search(r"\b(CPC|LL)\b", row_attr, re.IGNORECASE))
                            or not row_plr
                            or (r_meta["old_player"] and norm(row_plr) == norm(r_meta["old_player"]))
                            or (r_meta["team"] and norm(row_plr) == norm(r_meta["team"]) and norm(row_tm) == norm(r_meta["team"]))
                        )
                        if is_target_row and row_plr != r_meta["title"]:
                            df_upd.at[r_i, "Player"] = r_meta["title"]
                            updated_rows_csv += 1
                    df_upd.to_csv(csv_p, index=False, encoding="utf-8-sig")
                    grand_stats["players_repaired"] += updated_rows_csv
                    log_msg(
                        f"  ✅ Propagated {len(resolved_meta_for_csv)} live TCDB title(s) across {updated_rows_csv} CPC/LL row(s) in {csv_p.name}!"
                    )
        except Exception as live_err:
            log_msg(f"  [!] Live TCDB CPC/LL resolution skipped: {live_err}")
        finally:
            if req_sess is not None:
                cleanup_orphaned_drivers()

    # Local Disk Filename Alignment Pass: Rename any already-downloaded images in D:\Tabulas Set Library
    # whose Player or Subset name was cleaned (e.g. 'David_Spade_Comedian,_Actor' -> 'David_Spade') with 0 HTTP calls!
    local_renamed_imgs = 0
    for csv_p in csv_files:
        try:
            df_rn = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
            if df_rn.empty or "TCDB_CID" not in df_rn.columns:
                continue
            s_title = canonicalize_checklist_set_title(df_rn["Set"].iloc[0] if "Set" in df_rn.columns else csv_p.stem)
            s_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(s_title)
            if not s_dir.exists():
                continue
            cid_disk_map = _index_existing_set_dir_by_cid(s_dir)
            if not cid_disk_map:
                continue
            for _, r_n in df_rn.iterrows():
                cid_n = normalize_numeric_tcdb_cid(r_n.get("TCDB_CID") or "")
                if not cid_n or cid_n == "0":
                    continue
                sub_n = str(r_n.get("Subset") or "Base").strip() or "Base"
                cn_n = str(r_n.get("Card Number") or "0").strip().lstrip("#")
                plr_n = str(r_n.get("Player") or "Unknown Player").strip()
                f_exp, b_exp = build_template_image_filenames(s_title, sub_n, cn_n, plr_n, cid_n)
                for side_c, exp_fn in (("F", f_exp), ("B", b_exp)):
                    if _check_or_rename_existing_cid_file(cid_disk_map, cid_n, side_c, s_dir / exp_fn) == "Skip(Renamed)":
                        local_renamed_imgs += 1
        except Exception:
            continue
    if local_renamed_imgs > 0:
        log_msg(f"🏷️ Renamed {local_renamed_imgs:,} existing image file(s) in {REFERENCE_TEMPLATES_DIR} to match cleaned Player/Subset names!")

    log_msg("🔄 Syncing Front_Downloaded & Back_Downloaded flags against D:\\Tabulas Set Library and rebuilding Master_Checklist.csv...")
    sync_res = sync_set_library_download_status(rebuild_master_checklist=True)

    # Purge binary checklist cache so the updated Master_Checklist.csv is loaded immediately
    if CHECKLIST_CACHE_FILE.exists():
        try:
            CHECKLIST_CACHE_FILE.unlink()
            log_msg(f"🧹 Cleared stale binary cache: {CHECKLIST_CACHE_FILE.name}")
        except Exception:
            pass

    log_msg(
        f"✅ Checklist Repair Complete ({total_files} sets, {sync_res.get('total_rows', fixed_rows_total):,} rows): "
        f"{grand_stats['subsets_cleaned']:,} subsets cleaned, {grand_stats['players_repaired']:,} player/LL/CPC/TC titles restored, "
        f"{grand_stats['attrs_normalized']:,} attributes (#/N) normalized, {grand_stats['variations_disambiguated']:,} variations disambiguated | "
        f"{sync_res.get('fronts_downloaded', 0):,} Fronts & {sync_res.get('backs_downloaded', 0):,} Backs synced."
    )
    return {
        "checklist_rows_fixed": sync_res.get("total_rows", fixed_rows_total),
        **grand_stats,
        "fronts_downloaded": sync_res.get("fronts_downloaded", 0),
        "backs_downloaded": sync_res.get("backs_downloaded", 0),
        "missing_backs": sync_res.get("missing_backs", 0),
        "batches_repaired": 0,
        "batch_cards_fixed": 0,
        "inventory_cards_fixed": 0,
        "inventory_files_renamed": 0,
    }


def clean_reference_library_names(dry_run: bool = False) -> dict:
    """
    Comprehensive Reference Library, Set Checklist & Catalog Naming Alignment Script:
      1. Standardizes `tracked_sets.json` & `TCDB_Set_Directory.csv` (Manufacturers, Categories, Uniform Names).
      2. Aligns `Set_Checklists/*.csv` filenames & `Set` columns (merging duplicate spellings like
         `2025_Topps_Allen_Ginter_Baseball.csv` -> `2025_Topps_Allen_&_Ginter_Baseball.csv`).
      3. Renames & merges all set folders inside `D:\\Tabulas Set Library\\Reference_Library\\` to their
         canonical `Folder_Name` (e.g., `2026_Topps_Finest` -> `2026_Topps_Finest_Baseball`,
         `2025_Topps_Allen__Ginter_X_Baseball` -> `2025_Topps_Allen_&_Ginter_X_Baseball`), keeping
         the largest/highest-resolution file if two folders contain the same `(TCDB_CID, Side)`.
      4. Renames every `.jpg` inside `Reference_Library\\<Set>\\` to the exact canonical
         `[Canonical_Set]_[Canonical_Subset]_[#CardNumber]_[Clean_Player]_[TCDB{CID}]_{F|B}.jpg`
         using `TCDB_CID` checklist lookups + uniform naming rules.
      5. Aligns `Cache\\Library\\Catalogs\\*_catalog.json` filenames and re-syncs `Master_Checklist.csv`.
    """
    ensure_directories()
    log_msg("=" * 72)
    log_msg(f"🗂️ REFERENCE LIBRARY FOLDER & FILENAME ALIGNMENT {'(DRY RUN)' if dry_run else '(LIVE)'}")
    log_msg(f"   Reference Library : {REFERENCE_TEMPLATES_DIR}")
    log_msg("=" * 72)

    # Step 1: Standardize Tracked Sets & TCDB_Set_Directory.csv first
    dedup_res = deduplicate_tracked_sets_and_directory() if not dry_run else {}
    dir_res = repair_tcdb_set_directory(fetch_missing_image_pct=False) if not dry_run else {}

    # Build authoritative canonical folder map from tracked_sets + directory
    canon_folder_by_key: dict[str, tuple[str, str]] = {}
    for _, m in load_tracked_sets_meta(prioritize=False).items():
        sp_m = str(m.get("sport") or "Baseball").strip()
        yr_m = str(m.get("year") or "").strip()
        fn_m = canonicalize_set_folder_name(m.get("folder_name", ""), sport=sp_m, year=yr_m)
        title_m = canonicalize_checklist_set_title(fn_m)
        canon_folder_by_key[canonical_set_key(title_m)] = (fn_m, title_m)
        no_sp = re.sub(r"\b(Baseball|Football|Basketball|Hockey|Soccer|Racing|Wrestling|MMA|Golf)\b", "", title_m, flags=re.IGNORECASE).strip()
        if no_sp:
            canon_folder_by_key.setdefault(canonical_set_key(no_sp), (fn_m, title_m))

    def _resolve_target_folder_and_title(raw_name: str) -> tuple[str, str]:
        cleaned_t = canonicalize_checklist_set_title(str(raw_name or "").replace("_", " "))
        ck = canonical_set_key(cleaned_t)
        if ck in canon_folder_by_key:
            return canon_folder_by_key[ck]
        sp_inf, yr_inf, _ = _infer_sport_year_mfg(cleaned_t)
        fn_c = canonicalize_set_folder_name(cleaned_t, sport=sp_inf, year=yr_inf)
        return fn_c, canonicalize_checklist_set_title(fn_c)

    # Step 2: Align Set_Checklists/*.csv filenames & build CID lookup map
    csvs_merged = 0
    by_cid: dict[str, tuple[str, str, str, str]] = {}
    if SET_CHECKLISTS_DIR.exists():
        csv_files = sorted(SET_CHECKLISTS_DIR.glob("*.csv"))
        for csv_p in csv_files:
            try:
                df = pd.read_csv(csv_p, dtype=str, keep_default_na=False)
                if df.empty:
                    continue
                raw_set_v = df["Set"].iloc[0] if "Set" in df.columns and str(df["Set"].iloc[0]).strip() else csv_p.stem
                target_fn, target_title = _resolve_target_folder_and_title(raw_set_v)
                target_csv = SET_CHECKLISTS_DIR / f"{target_fn}.csv"
                df["Set"] = target_title

                if not dry_run and csv_p.resolve() != target_csv.resolve():
                    if target_csv.exists():
                        df_existing = pd.read_csv(target_csv, dtype=str, keep_default_na=False)
                        combined = pd.concat([df_existing, df], ignore_index=True)
                        repaired = apply_excel_formulas_and_combine(combined.to_dict(orient="records"), target_title)
                        repaired.to_csv(target_csv, index=False, encoding="utf-8-sig")
                        csv_p.unlink()
                    else:
                        df.to_csv(target_csv, index=False, encoding="utf-8-sig")
                        csv_p.unlink()
                    csvs_merged += 1
                    log_msg(f"  [CSV] {csv_p.name} -> {target_csv.name}")

                for _, r in df.iterrows():
                    cid_n = normalize_numeric_tcdb_cid(r.get("TCDB_CID") or "")
                    if cid_n and cid_n != "0" and cid_n not in by_cid:
                        by_cid[cid_n] = (
                            target_title,
                            str(r.get("Subset") or "Base").strip() or "Base",
                            str(r.get("Card Number") or "0").strip().lstrip("#"),
                            str(r.get("Player") or "Unknown Player").strip(),
                        )
            except Exception as e:
                log_msg(f"  [!] CSV align skipped for {csv_p.name}: {e}")

    # Step 3 & 4: Align Reference_Library\<Set>\ folders AND every .jpg filename inside them
    folders_renamed = 0
    files_renamed = 0
    dupes_deduped = 0

    if REFERENCE_TEMPLATES_DIR.exists():
        set_dirs = sorted([
            d for d in REFERENCE_TEMPLATES_DIR.iterdir()
            if d.is_dir() and d.name.lower() not in ("logs", "reports", ".verified_backups", "_my_collection", "unprocessed_cards", "reference_library")
        ])
        total_dirs = len(set_dirs)
        for d_idx, s_dir in enumerate(set_dirs, 1):
            target_fn, target_title = _resolve_target_folder_and_title(s_dir.name)
            target_dir = REFERENCE_TEMPLATES_DIR / target_fn

            if s_dir.name != target_fn:
                folders_renamed += 1
                log_msg(f"[{d_idx}/{total_dirs}] 📁 Aligning folder: '{s_dir.name}' -> '{target_fn}'")
                if not dry_run:
                    if not target_dir.exists():
                        try:
                            s_dir.rename(target_dir)
                            s_dir = target_dir
                        except Exception:
                            target_dir.mkdir(parents=True, exist_ok=True)
                    if s_dir.resolve() != target_dir.resolve():
                        # Merge into existing canonical target folder, preferring larger/higher-res files
                        for item in list(s_dir.rglob("*")):
                            if not item.is_file():
                                continue
                            dst_f = target_dir / item.name
                            if dst_f.exists():
                                if item.stat().st_size > dst_f.stat().st_size:
                                    dst_f.unlink()
                                    shutil.move(str(item), str(dst_f))
                                else:
                                    item.unlink()
                                dupes_deduped += 1
                            else:
                                shutil.move(str(item), str(dst_f))
                        shutil.rmtree(s_dir, ignore_errors=True)
                        s_dir = target_dir
            else:
                log_msg(f"[{d_idx}/{total_dirs}] Checking filenames inside '{s_dir.name}'...")

            if not s_dir.exists():
                continue

            # Rename every .jpg inside this folder to exact canonical naming
            dir_ren = 0
            for img_p in sorted(s_dir.glob("*.jpg")):
                parsed = parse_unified_card_filename(img_p.name)
                if not parsed or not parsed.get("is_template"):
                    continue
                cid_n = normalize_numeric_tcdb_cid(parsed.get("cid") or "")
                side_c = parsed.get("side") or "F"

                if cid_n and cid_n in by_cid:
                    c_set, c_sub, c_num, c_plr = by_cid[cid_n]
                else:
                    c_set = target_title
                    c_sub = clean_tcdb_subset_title(parsed.get("subset") or "Base", checklist_set_name=target_title) or "Base"
                    c_num = str(parsed.get("card_number") or "0").strip().lstrip("#")
                    c_plr_clean, _, _ = _strip_inline_tags_errors_and_occupations(parsed.get("player") or "Unknown Player")
                    c_plr = c_plr_clean or parsed.get("player") or "Unknown Player"

                new_fname = build_template_image_filename(c_set, c_sub, c_num, c_plr, cid_n or "0", side=side_c)
                if img_p.name != new_fname:
                    dst_p = s_dir / new_fname
                    files_renamed += 1
                    dir_ren += 1
                    if not dry_run:
                        try:
                            if dst_p.exists() and dst_p.resolve() != img_p.resolve():
                                if img_p.stat().st_size > dst_p.stat().st_size:
                                    dst_p.unlink()
                                    img_p.replace(dst_p)
                                else:
                                    img_p.unlink()
                                dupes_deduped += 1
                            else:
                                img_p.replace(dst_p)
                        except Exception:
                            pass
            if dir_ren > 0:
                log_msg(f"  🏷️ Renamed {dir_ren:,} image file(s) inside '{s_dir.name}'")

    # Step 5: Align Cache\Library\Catalogs\*_catalog.json filenames
    catalogs_merged = 0
    cat_dir = _catalog_dir()
    if cat_dir.exists() and not dry_run:
        for cat_p in sorted(cat_dir.glob("*_catalog.json")):
            raw_stem = cat_p.name[: -len("_catalog.json")]
            target_fn, _ = _resolve_target_folder_and_title(raw_stem)
            target_cat = cat_dir / f"{target_fn}_catalog.json"
            if cat_p.resolve() != target_cat.resolve():
                try:
                    src_data = json.loads(cat_p.read_text(encoding="utf-8-sig"))
                    if target_cat.exists():
                        dst_data = json.loads(target_cat.read_text(encoding="utf-8-sig"))
                        if isinstance(src_data, dict) and isinstance(dst_data, dict):
                            for sk, sv in src_data.items():
                                if isinstance(sv, dict):
                                    dst_data.setdefault(sk, {}).update(sv)
                            target_cat.write_text(json.dumps(dst_data, indent=2), encoding="utf-8")
                        cat_p.unlink()
                    else:
                        cat_p.replace(target_cat)
                    catalogs_merged += 1
                except Exception:
                    pass

    sync_res = {} if dry_run else sync_set_library_download_status(rebuild_master_checklist=True)
    summary = (
        f"Reference Library Cleanup Complete: {folders_renamed} folder(s) aligned, {files_renamed:,} image filename(s) standardized, "
        f"{dupes_deduped:,} duplicate file(s) resolved, {csvs_merged} checklist CSV(s) & {catalogs_merged} catalog(s) aligned."
    )
    log_msg(f"✅ {summary}")
    return {
        "folders_renamed": folders_renamed,
        "files_renamed": files_renamed,
        "duplicates_resolved": dupes_deduped,
        "csvs_aligned": csvs_merged,
        "catalogs_aligned": catalogs_merged,
        "directory_repair": dir_res,
        "dedup": dedup_res,
        "sync": sync_res,
        "message": summary,
    }


def load_schedule_config() -> dict:
    ensure_directories()
    defaults = {
        "enabled": False,
        "pipeline_mode": "auto_scrape",
        "frequency": "DAILY",
        "time_24h": "03:00",
        "dir_crawl_enabled": False,
        "dir_crawl_frequency": "WEEKLY",
        "dir_crawl_time_24h": "04:00",
    }
    if SCHEDULE_CONFIG_FILE.exists():
        try:
            data = json.loads(SCHEDULE_CONFIG_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
    return defaults


def configure_scheduled_pipeline(
    pipeline_mode: str = "auto_scrape",
    frequency: str = "DAILY",
    time_24h: str = "03:00",
    enabled: bool = True,
) -> tuple[bool, str]:
    cfg = load_schedule_config()
    cfg.update({
        "enabled": bool(enabled),
        "pipeline_mode": pipeline_mode,
        "frequency": frequency.upper(),
        "time_24h": time_24h,
    })
    SCHEDULE_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return True, f"Saved pipeline schedule ({frequency} at {time_24h})."


def configure_directory_crawl_schedule(
    frequency: str = "WEEKLY",
    time_24h: str = "04:00",
    enabled: bool = True,
) -> tuple[bool, str]:
    cfg = load_schedule_config()
    cfg.update({
        "dir_crawl_enabled": bool(enabled),
        "dir_crawl_frequency": frequency.upper(),
        "dir_crawl_time_24h": time_24h,
    })
    SCHEDULE_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return True, f"Saved directory crawl schedule ({frequency} at {time_24h})."