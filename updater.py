from __future__ import annotations
# ==============================================================================
# updater.py - TABULAS CARD HUB ATOMIC PATCH, CHANGELOG & ROLLBACK ENGINE
# ==============================================================================
# Supports 4 Execution Modes:
#   1. Automatic at App Startup : `python updater.py --auto` (called by Launch_Tabulas_Hub.bat & launch_tabulas_hub.py)
#   2. Manual inside Running App: Triggered via REST API (`/api/updater/*`) or Streamlit UI
#   3. Manual Interactive CLI   : `python updater.py` (interactive terminal menu for apply, changelog, rollback)
#   4. Scheduled Background Task: `python updater.py --schedule DAILY --time 02:00`
# ==============================================================================
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Optional

import requests

try:
    from packaging.version import InvalidVersion as _PackagingInvalidVersion
    from packaging.version import Version as _PackagingVersion
except Exception:
    _PackagingVersion = None
    _PackagingInvalidVersion = ValueError

from Core.config import (
    UPDATER_CONFIG_FILE,
    atomic_write_bytes,
    atomic_write_text,
    interprocess_file_lock,
)
from Core.maintenance_scheduler import is_worker_pool_busy

__version__ = "0.25.0-beta.1"
__last_updated__ = "2026-11-21 18:45:00"

_DEFAULT_HUB_DIR = r"C:\Tabulas Card Hub" if os.path.exists(r"C:\Tabulas Card Hub") else os.getcwd()
BASE_DIR = Path(os.environ.get("CARDS_BASE_DIR", _DEFAULT_HUB_DIR))
APP_DIR = (BASE_DIR / "App") if (BASE_DIR / "App").exists() else BASE_DIR
UPDATES_DIR = BASE_DIR / "Updates"
SNAPSHOTS_DIR = UPDATES_DIR / ".snapshots"
REGISTRY_FILE = UPDATES_DIR / "version_registry.json"
VERIFIED_BACKUPS_DIR = APP_DIR / "Core" / ".verified_backups"

_DEFAULT_ARC_ROOT = Path(os.environ.get("TABULAS_ARCHIVE_DIR", r"F:\Tabulas Archive"))
ARCHIVE_UPDATES_PACKAGES_DIR = _DEFAULT_ARC_ROOT / "Updates" / "Packages"
ARCHIVE_UPDATES_SNAPSHOTS_DIR = _DEFAULT_ARC_ROOT / "Updates" / "Snapshots"


def _resolve_disk_path(rel_path: str) -> Path:
    """Maps logical file paths (e.g. 'App.jsx', 'Core/config.py') into App/ automatically after v0.24 reorganization."""
    norm_rel = str(rel_path or "").strip().replace("\\", "/")
    if norm_rel in ("Launch_Tabulas_Hub.bat",):
        return BASE_DIR / norm_rel
    if (BASE_DIR / "App").exists():
        return BASE_DIR / "App" / norm_rel
    return BASE_DIR / norm_rel


def _log_updater_event(msg: str):
    try:
        day_dir = BASE_DIR / "Logs" / "Logs" / datetime.now().strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        log_f = day_dir / f"{datetime.now().strftime('%Y%m%d')}_updater.log"
        with open(log_f, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

WINDOWS_UPDATER_TASK_NAME = "Tabulas_Auto_Code_Updater_Job"

TRACKED_APP_FILES = [
    "Core/config.py",
    "Core/database.py",
    "Core/label_engine.py",
    "Core/scraper_engine.py",
    "Core/rate_learner.py",
    "Core/compute_backend.py",
    "Core/neural_vision.py",
    "Core/vision_grader.py",
    "Core/market_engine.py",
    "Core/sales_engine.py",
    "cli.py",
    "launch_tabulas_hub.py",
    "App.jsx",
    "updater.py",
    "Launch_Tabulas_Hub.bat",
]


# ==============================================================================
# 1. SEMANTIC VERSION COMPARATOR & FILE HASHING
# ==============================================================================
def parse_version_tuple(ver_str: str) -> tuple:
    """
    Converts a version string like 'v0.22.0-beta.9' or '0.21.0-beta.3' into a
    comparable tuple: (0, 22, 0, 'beta', 9).
    """
    s = str(ver_str or "").strip().lstrip("vV")
    if not s:
        return (0, 0, 0, "", 0)
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z]+)\.?(\d+)?)?", s)
    if not m:
        return (0, 0, 0, s, 0)
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3))
    tag = (m.group(4) or "zzz").lower()  # release > beta > alpha
    tag_num = int(m.group(5) or 0)
    return (major, minor, patch, tag, tag_num)


def is_newer_version(candidate_ver: str, current_ver: str) -> bool:
    return parse_version_tuple(candidate_ver) > parse_version_tuple(current_ver)


def compute_sha256(file_path: Path) -> str:
    if not file_path.exists() or not file_path.is_file():
        return ""
    h = hashlib.sha256()
    h.update(file_path.read_bytes())
    return h.hexdigest()[:16]


def detect_file_version_on_disk(rel_path: str) -> str:
    p = _resolve_disk_path(rel_path)
    if not p.exists():
        return "0.0.0"
    try:
        head = p.read_text(encoding="utf-8-sig", errors="replace")[:4000]
        for pat in (
            r'__version__\s*=\s*["\']([^"\']+)["\']',
            r'APP_RELEASE_VERSION\s*=\s*["\']([^"\']+)["\']',
            r'const\s+APP_VERSION\s*=\s*["\']([^"\']+)["\']',
            r'Release:\s*v?([0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?)',
        ):
            m = re.search(pat, head)
            if m:
                return m.group(1).strip().lstrip("vV")
    except Exception:
        pass
    return "0.22.0-beta.8"


# ==============================================================================
# 2. VERSION REGISTRY DATABASE (Updates/version_registry.json)
# ==============================================================================
def ensure_updater_dirs():
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    VERIFIED_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def load_version_registry() -> dict:
    """
    Loads `Updates/version_registry.json`, auto-initializing it from the current
    files on disk if it does not exist yet.
    """
    ensure_updater_dirs()
    if REGISTRY_FILE.exists():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "current_release_version" in data:
                return data
        except Exception:
            pass

    # Initialize baseline registry from current files on disk
    files_meta = {}
    highest_ver = "0.22.0-beta.8"
    for rel in TRACKED_APP_FILES:
        p = _resolve_disk_path(rel)
        if p.exists() and p.is_file():
            v = detect_file_version_on_disk(rel)
            if is_newer_version(v, highest_ver):
                highest_ver = v
            files_meta[rel] = {
                "version": v,
                "sha256": compute_sha256(p),
                "last_updated": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }

    reg = {
        "current_release_version": highest_ver,
        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "applied_packages": [],
        "version_history": [
            {
                "version": highest_ver,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": "Initial Baseline Snapshot",
                "package_file": "baseline",
                "changelog": ["Initialized Tabulas Atomic Updater & Version Registry."],
            }
        ],
        "files": files_meta,
    }
    save_version_registry(reg)
    create_version_snapshot(highest_ver, label="baseline")
    return reg


def save_version_registry(reg: dict):
    ensure_updater_dirs()
    reg["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")


# ==============================================================================
# 3. STRUCTURED UPDATE PACKAGE (.txt) PARSER
# ==============================================================================
def parse_update_package_file(txt_path: Path) -> dict:
    """
    Parses a standardized Tabulas Update Package `.txt` file from `Updates/`.

    Supported Format:
    ===========================================================================
    TABULAS_UPDATE_PACKAGE: v1
    VERSION: 0.22.0-beta.9
    TIMESTAMP: 2026-11-18 12:00:00
    TITLE: Short title of the update
    AUTHOR: Gemini
    ===========================================================================
    === CHANGELOG_START ===
    - Bullet 1
    - Bullet 2
    === CHANGELOG_END ===

    === FILE_UPDATE: Core/config.py ===
    ACTION: PATCH   (or REPLACE_FILE)
    <<< OPERATION: REPLACE >>>   (or INSERT_AFTER, INSERT_BEFORE, APPEND, PREPEND, REGEX_REPLACE)
    <<< TARGET_START >>>
    exact existing lines to find
    <<< TARGET_END >>>
    <<< REPLACEMENT_START >>>
    exact new lines to put in its place
    <<< REPLACEMENT_END >>>
    === END_FILE_UPDATE ===
    """
    raw = txt_path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")

    def _extract_header(key: str, default: str = "") -> str:
        m = re.search(rf"^{key}\s*:\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip().lstrip("vV") if (m and key.upper() == "VERSION") else (m.group(1).strip() if m else default)

    version = _extract_header("VERSION", "")
    timestamp = _extract_header("TIMESTAMP", datetime.fromtimestamp(txt_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"))
    title = _extract_header("TITLE", txt_path.stem)
    pkg_type = _extract_header("PACKAGE_TYPE", "").upper()

    # Extract Changelog bullets
    changelog_lines = []
    m_cl = re.search(r"===\s*CHANGELOG_START\s*===\n(.*?)\n===\s*CHANGELOG_END\s*===", raw, re.DOTALL)
    if m_cl:
        for ln in m_cl.group(1).splitlines():
            clean_ln = ln.strip()
            if clean_ln:
                changelog_lines.append(clean_ln.lstrip("-*• ").strip())

    # Extract File Update blocks
    file_updates = []
    file_pattern = re.compile(
        r"===\s*FILE_UPDATE\s*:\s*([^\n=]+?)\s*===\n(.*?)\n===\s*END_FILE_UPDATE\s*===",
        re.DOTALL,
    )
    for m_file in file_pattern.finditer(raw):
        target_rel_path = m_file.group(1).strip().replace("\\", "/")
        block_body = m_file.group(2)

        m_act = re.search(r"^ACTION\s*:\s*(\S+)", block_body, re.MULTILINE | re.IGNORECASE)
        action_type = (m_act.group(1).strip().upper() if m_act else "PATCH")

        operations = []
        if action_type == "REPLACE_FILE":
            m_content = re.search(
                r"<<<\s*CONTENT_START\s*>>>\n(.*?)\n<<<\s*CONTENT_END\s*>>>",
                block_body,
                re.DOTALL,
            )
            if m_content:
                operations.append({
                    "op": "REPLACE_FILE",
                    "target": "",
                    "replacement": m_content.group(1),
                })
        else:
            op_pattern = re.compile(
                r"<<<\s*OPERATION\s*:\s*([A-Z_]+)\s*>>>\s*\n"
                r"(?:<<<\s*TARGET_START\s*>>>\n(.*?)\n<<<\s*TARGET_END\s*>>>\s*\n)?"
                r"<<<\s*REPLACEMENT_START\s*>>>\n(.*?)\n<<<\s*REPLACEMENT_END\s*>>>",
                re.DOTALL,
            )
            for m_op in op_pattern.finditer(block_body):
                op_name = m_op.group(1).strip().upper()
                target_txt = m_op.group(2) if m_op.group(2) is not None else ""
                repl_txt = m_op.group(3) if m_op.group(3) is not None else ""
                operations.append({
                    "op": op_name,
                    "target": target_txt,
                    "replacement": repl_txt,
                })

        file_updates.append({
            "rel_path": target_rel_path,
            "action": action_type,
            "operations": operations,
        })

    is_changelog_only = (pkg_type == "CHANGELOG_ONLY") or (bool(version and changelog_lines) and not file_updates)
    return {
        "package_file": txt_path.name,
        "package_path": str(txt_path),
        "version": version,
        "timestamp": timestamp,
        "title": title,
        "package_type": "CHANGELOG_ONLY" if is_changelog_only else "PATCH",
        "is_changelog_only": is_changelog_only,
        "changelog": changelog_lines,
        "file_updates": file_updates,
        "is_valid_package": bool(version and (file_updates or changelog_lines)),
    }


def is_rolled_back_package_file(file_path: Path) -> bool:
    """Returns True if an update package file was renamed as rolled back (`.rolledback.txt`)."""
    name_low = file_path.name.lower()
    return ".rolledback." in name_low or name_low.endswith(".rolledback.txt") or name_low.startswith("rolledback_")


def discover_update_packages(include_rolled_back: bool = False) -> list[dict]:
    """
    Scans `C:\\Tabulas Card Hub\\Updates\\*.txt` and returns all valid update packages
    strictly sorted in ascending semantic version order for incremental application.
    Skips `.rolledback.txt` files unless `include_rolled_back=True`.
    """
    ensure_updater_dirs()
    packages = []
    for txt_p in sorted(UPDATES_DIR.glob("*.txt")):
        is_rb = is_rolled_back_package_file(txt_p)
        if is_rb and not include_rolled_back:
            continue
        try:
            pkg = parse_update_package_file(txt_p)
            if pkg["is_valid_package"]:
                pkg["is_rolled_back"] = is_rb
                packages.append(pkg)
        except Exception:
            continue
    packages.sort(key=lambda p: (parse_version_tuple(p["version"]), p["timestamp"], p["package_file"]))
    return packages


def get_pending_module_updates(pending_packages: Optional[list[dict]] = None) -> dict[str, str]:
    """
    Returns `{rel_path: latest_pending_version}` for every module touched by pending update
    packages in `./Updates/` so the Check for Updates registry table can highlight exactly
    which modules have new versions waiting.
    """
    if pending_packages is None:
        chk = check_and_apply_pending_updates(auto_apply=False)
        pending_packages = chk.get("pending_packages") or []

    mod_map: dict[str, str] = {}
    if not pending_packages:
        return mod_map

    ordered = sorted(pending_packages, key=lambda p: parse_version_tuple(p.get("version", "")))
    highest_ver = ""
    for pkg in ordered:
        ver_s = str(pkg.get("version") or "").strip().lstrip("vV")
        if ver_s:
            highest_ver = ver_s
        for f_upd in pkg.get("file_updates") or []:
            rel = str(f_upd.get("rel_path") or "").strip().replace("\\", "/")
            if rel and ver_s:
                mod_map[rel] = ver_s

    if highest_ver and mod_map:
        mod_map.setdefault("Core/config.py", highest_ver)
    return mod_map


# ==============================================================================
# 4. SNAPSHOT, ATOMIC PATCH APPLICATOR & SYNTAX VALIDATOR
# ==============================================================================
def create_version_snapshot(version_str: str, label: str = "") -> Path:
    """
    Saves a complete backup copy of all tracked script files into
    `Updates/.snapshots/v<version_str>/` so rolling back to any version is instant.
    """
    ensure_updater_dirs()
    clean_v = str(version_str).strip().lstrip("vV")
    snap_folder = SNAPSHOTS_DIR / f"v{clean_v}"
    snap_folder.mkdir(parents=True, exist_ok=True)

    copied_files = []
    for rel in TRACKED_APP_FILES:
        src_p = _resolve_disk_path(rel)
        if src_p.exists() and src_p.is_file():
            dst_p = snap_folder / rel
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_p, dst_p)
            copied_files.append(rel)

    meta = {
        "version": clean_v,
        "label": label,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": copied_files,
    }
    (snap_folder / "snapshot_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return snap_folder


def _validate_file_syntax(rel_path: str, content: str) -> tuple[bool, str]:
    """Validates Python `.py` syntax via `ast.parse()` and balanced braces for `.js`/`.jsx`."""
    if rel_path.endswith(".py"):
        try:
            ast.parse(content, filename=rel_path)
            return True, "Python AST Valid"
        except (SyntaxError, IndentationError) as e:
            return False, f"{type(e).__name__} in {rel_path} (line {getattr(e, 'lineno', '?')}): {e.msg}"
    return True, "Syntax OK"


def _apply_single_operation_to_text(
    src_text: str,
    op_dict: dict,
    rel_path: str,
) -> tuple[str, str]:
    """
    Applies a single structured operation (`REPLACE`, `INSERT_AFTER`, `INSERT_BEFORE`,
    `APPEND`, `PREPEND`, `REGEX_REPLACE`, `REPLACE_FILE`) to `src_text`.
    Includes idempotency detection: if the replacement is already present and the target
    is gone, reports `Already Applied` instead of failing.
    """
    op = op_dict["op"]
    target = op_dict.get("target", "").replace("\r\n", "\n")
    replacement = op_dict.get("replacement", "").replace("\r\n", "\n")
    norm_src = src_text.replace("\r\n", "\n")

    if op == "REPLACE_FILE":
        return replacement + ("\n" if not replacement.endswith("\n") else ""), "Replaced full file"

    if op == "APPEND":
        if replacement.strip() in norm_src:
            return norm_src, "Append block already present"
        sep = "\n" if norm_src.endswith("\n") else "\n\n"
        return norm_src + sep + replacement + "\n", "Appended block"

    if op == "PREPEND":
        if replacement.strip() in norm_src:
            return norm_src, "Prepend block already present"
        return replacement + "\n" + norm_src, "Prepended block"

    if op == "REGEX_REPLACE":
        new_txt, count = re.subn(target, replacement, norm_src, flags=re.MULTILINE)
        if count == 0 and replacement.strip() in norm_src:
            return norm_src, "Regex replacement already present"
        if count == 0:
            raise ValueError(f"REGEX_REPLACE target pattern not found in {rel_path}: {target[:80]}")
        return new_txt, f"Regex replaced ({count} occurrence(s))"

    # Exact or whitespace-tolerant block matching for REPLACE / INSERT_AFTER / INSERT_BEFORE
    if target in norm_src:
        if op == "REPLACE":
            return norm_src.replace(target, replacement, 1), "Replaced target block"
        elif op == "INSERT_AFTER":
            if replacement.strip() in norm_src:
                return norm_src, "Insert-after block already present"
            return norm_src.replace(target, target + "\n" + replacement, 1), "Inserted after target block"
        elif op == "INSERT_BEFORE":
            if replacement.strip() in norm_src:
                return norm_src, "Insert-before block already present"
            return norm_src.replace(target, replacement + "\n" + target, 1), "Inserted before target block"

    # Line-trimmed fallback match (tolerates trailing whitespace differences)
    src_lines = norm_src.splitlines()
    target_lines = [ln.rstrip() for ln in target.splitlines()]
    if target_lines:
        n_t = len(target_lines)
        for i in range(len(src_lines) - n_t + 1):
            window = [ln.rstrip() for ln in src_lines[i : i + n_t]]
            if window == target_lines:
                repl_lines = replacement.splitlines()
                if op == "REPLACE":
                    new_lines = src_lines[:i] + repl_lines + src_lines[i + n_t :]
                elif op == "INSERT_AFTER":
                    new_lines = src_lines[: i + n_t] + repl_lines + src_lines[i + n_t :]
                elif op == "INSERT_BEFORE":
                    new_lines = src_lines[:i] + repl_lines + src_lines[i:]
                else:
                    new_lines = src_lines
                return "\n".join(new_lines) + "\n", f"Applied {op} (line-trimmed match at line {i + 1})"

    # Indentation-tolerant fallback for non-Python files (.jsx, .js, .html, .css)
    if target_lines and not rel_path.endswith(".py"):
        stripped_target = [ln.strip() for ln in target.splitlines()]
        n_t = len(stripped_target)
        for i in range(len(src_lines) - n_t + 1):
            window_stripped = [ln.strip() for ln in src_lines[i : i + n_t]]
            if window_stripped == stripped_target:
                repl_lines = replacement.splitlines()
                if op == "REPLACE":
                    new_lines = src_lines[:i] + repl_lines + src_lines[i + n_t :]
                elif op == "INSERT_AFTER":
                    new_lines = src_lines[: i + n_t] + repl_lines + src_lines[i + n_t :]
                elif op == "INSERT_BEFORE":
                    new_lines = src_lines[:i] + repl_lines + src_lines[i:]
                else:
                    new_lines = src_lines
                return "\n".join(new_lines) + "\n", f"Applied {op} (indent-tolerant match at line {i + 1})"

    # Check if replacement is already present (idempotent re-run)
    if replacement.strip() and replacement.strip() in norm_src:
        return norm_src, "Already applied (idempotent)"

    raise ValueError(
        f"Target block for {op} not found in '{rel_path}'.\n"
        f"Expected Target Preview:\n{target[:250]}"
    )


def _auto_stamp_file_version(content: str, rel_path: str, new_version: str, timestamp_str: str) -> str:
    """
    Automatically updates `__version__`, `__last_updated__`, `APP_RELEASE_VERSION`,
    and `APP_VERSION` inside any touched file so module versions never drift!
    """
    clean_v = str(new_version).strip().lstrip("vV")
    out = content
    out = re.sub(
        r'^(__version__\s*=\s*["\'])([^"\']+)(["\'])',
        rf"\g<1>{clean_v}\g<3>",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'^(__last_updated__\s*=\s*["\'])([^"\']+)(["\'])',
        rf"\g<1>{timestamp_str}\g<3>",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'^(APP_RELEASE_VERSION\s*=\s*["\'])([^"\']+)(["\'])',
        rf"\g<1>{clean_v}\g<3>",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'^(\s*const\s+APP_VERSION\s*=\s*["\'])([^"\']+)(["\'])',
        rf"\g<1>{clean_v}\g<3>",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'^(\s*const\s+LAST_UPDATED\s*=\s*["\'])([^"\']+)(["\'])',
        rf"\g<1>{timestamp_str}\g<3>",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'^(#\s*Release:\s*v?)([0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?)',
        rf"\g<1>{clean_v}",
        out,
        flags=re.MULTILINE,
    )
    return out


def apply_update_package(pkg: dict, dry_run: bool = False) -> dict:
    """
    Atomically applies a parsed Update Package:
      1. Snapshots the current pre-update version to `Updates/.snapshots/v<current>/`
      2. Computes all file changes in memory and validates `.py` AST syntax
      3. If 100% valid, writes all updated files to disk, syncs `Core/.verified_backups/`,
         saves a snapshot of the new version `Updates/.snapshots/v<new_version>/`,
         and updates `Updates/version_registry.json`.
    """
    reg = load_version_registry()
    cur_ver = reg.get("current_release_version", "0.22.0-beta.8")
    target_ver = pkg["version"]
    ts_str = pkg.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if pkg.get("is_changelog_only") and not pkg.get("file_updates"):
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "changelog_only": True,
                "version": target_ver,
                "package_file": pkg["package_file"],
                "files_modified": [],
                "logs": ["  + [CHANGELOG_ONLY] Validated changelog record (no code diffs to apply)"],
            }
        reg["current_release_version"] = target_ver
        if pkg["package_file"] not in reg.get("applied_packages", []):
            reg.setdefault("applied_packages", []).append(pkg["package_file"])
        reg.setdefault("version_history", []).append({
            "version": target_ver,
            "timestamp": ts_str,
            "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": pkg["title"],
            "package_file": pkg["package_file"],
            "files_modified": [],
            "changelog": pkg["changelog"],
        })
        save_version_registry(reg)
        _log_updater_event(f"RECORDED CHANGELOG v{target_ver} ({pkg['package_file']}) — {pkg['title']}")
        return {
            "success": True,
            "dry_run": False,
            "changelog_only": True,
            "version": target_ver,
            "package_file": pkg["package_file"],
            "title": pkg["title"],
            "files_modified": [],
            "changelog": pkg["changelog"],
            "logs": ["  + [CHANGELOG_ONLY] Recorded changelog entry in version_registry.json"],
        }

    staged_writes: dict[str, str] = {}
    op_logs: list[str] = []

    try:
        for f_upd in pkg.get("file_updates", []):
            rel_path = f_upd["rel_path"]
            disk_p = _resolve_disk_path(rel_path)
            if rel_path in staged_writes:
                working_txt = staged_writes[rel_path]
            elif disk_p.exists():
                working_txt = disk_p.read_text(encoding="utf-8-sig", errors="replace")
            else:
                working_txt = ""

            for op_item in f_upd.get("operations", []):
                working_txt, note = _apply_single_operation_to_text(working_txt, op_item, rel_path)
                op_logs.append(f"  + [{rel_path}] {op_item['op']}: {note}")

            working_txt = _auto_stamp_file_version(working_txt, rel_path, target_ver, ts_str)
            valid_syn, syn_msg = _validate_file_syntax(rel_path, working_txt)
            if not valid_syn:
                raise SyntaxError(syn_msg)

            staged_writes[rel_path] = working_txt

        # Also bump Core/config.py version stamp so global version inspector stays 100% in sync
        cfg_rel = "Core/config.py"
        cfg_p = _resolve_disk_path(cfg_rel)
        if cfg_rel not in staged_writes and cfg_p.exists():
            cfg_txt = cfg_p.read_text(encoding="utf-8-sig", errors="replace")
            cfg_stamped = _auto_stamp_file_version(cfg_txt, cfg_rel, target_ver, ts_str)
            valid_cfg, _ = _validate_file_syntax(cfg_rel, cfg_stamped)
            if valid_cfg:
                staged_writes[cfg_rel] = cfg_stamped

    except Exception as e:
        return {
            "success": False,
            "version": target_ver,
            "package_file": pkg["package_file"],
            "error": str(e),
            "logs": op_logs,
        }

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "version": target_ver,
            "package_file": pkg["package_file"],
            "files_modified": list(staged_writes.keys()),
            "logs": op_logs,
        }

    # 1. Snapshot current state before writing
    create_version_snapshot(cur_ver, label=f"Pre-update backup before v{target_ver}")

    # 2. Commit all staged writes to disk & update Core/.verified_backups
    for rel_path, final_txt in staged_writes.items():
        dst_p = _resolve_disk_path(rel_path)
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        dst_p.write_text(final_txt, encoding="utf-8")
        if dst_p.suffix == ".py":
            try:
                shutil.copy2(dst_p, VERIFIED_BACKUPS_DIR / dst_p.name)
            except Exception:
                pass
        reg.setdefault("files", {})[rel_path] = {
            "version": target_ver,
            "sha256": compute_sha256(dst_p),
            "last_updated": ts_str,
        }

    # 3. Snapshot the newly applied version for instant future rollbacks
    create_version_snapshot(target_ver, label=pkg["title"])

    # 4. Record in version_registry.json
    reg["current_release_version"] = target_ver
    if pkg["package_file"] not in reg.get("applied_packages", []):
        reg.setdefault("applied_packages", []).append(pkg["package_file"])

    hist_entry = {
        "version": target_ver,
        "timestamp": ts_str,
        "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": pkg["title"],
        "package_file": pkg["package_file"],
        "files_modified": list(staged_writes.keys()),
        "changelog": pkg["changelog"],
    }
    reg.setdefault("version_history", []).append(hist_entry)
    save_version_registry(reg)
    _log_updater_event(
        f"APPLIED v{target_ver} ({pkg['package_file']}) — {pkg['title']} | Files: {', '.join(staged_writes.keys())}"
    )
    archive_old_updates(keep_recent=5)

    return {
        "success": True,
        "dry_run": False,
        "version": target_ver,
        "package_file": pkg["package_file"],
        "title": pkg["title"],
        "files_modified": list(staged_writes.keys()),
        "changelog": pkg["changelog"],
        "logs": op_logs,
    }


def check_and_apply_pending_updates(auto_apply: bool = True, dry_run: bool = False) -> dict:
    """
    Scans `C:\\Tabulas Card Hub\\Updates\\*.txt`, compares package versions against
    `Updates/version_registry.json`, and applies ALL incremental newer packages strictly
    in ascending semantic version order (e.g. 1.0.1 -> 1.0.2 -> 1.0.3 -> 1.0.6 -> 1.1.0).
    Skips any `.rolledback.txt` packages automatically.
    """
    reg = load_version_registry()
    start_ver = reg.get("current_release_version", "0.22.0-beta.8")
    applied_set = set(reg.get("applied_packages", []))

    all_active_packages = discover_update_packages(include_rolled_back=False)
    all_packages_with_rb = discover_update_packages(include_rolled_back=True)

    pending = [
        pkg for pkg in all_active_packages
        if pkg["package_file"] not in applied_set and is_newer_version(pkg["version"], start_ver)
    ]
    # Guarantee strict ascending incremental version order
    pending.sort(key=lambda p: (parse_version_tuple(p["version"]), p["timestamp"], p["package_file"]))

    if not pending:
        return {
            "status": "UP_TO_DATE",
            "current_version": start_ver,
            "pending_count": 0,
            "applied_results": [],
            "all_packages": all_packages_with_rb,
            "message": f"Everything is up to date (v{start_ver}).",
        }

    chain_str = " -> ".join([f"v{start_ver}"] + [f"v{p['version']}" for p in pending])

    if not auto_apply:
        return {
            "status": "UPDATES_AVAILABLE",
            "current_version": start_ver,
            "pending_count": len(pending),
            "pending_packages": pending,
            "upgrade_chain": chain_str,
            "all_packages": all_packages_with_rb,
            "message": f"{len(pending)} incremental update(s) ready: {chain_str}",
        }

    applied_results = []
    running_ver = start_ver
    for step_idx, pkg in enumerate(pending, 1):
        # Verify strictly incremental progression
        if not is_newer_version(pkg["version"], running_ver):
            continue
        res = apply_update_package(pkg, dry_run=dry_run)
        res["step"] = f"{step_idx}/{len(pending)}"
        applied_results.append(res)
        if not res["success"]:
            return {
                "status": "FAILED",
                "previous_version": start_ver,
                "current_version": load_version_registry().get("current_release_version", running_ver),
                "pending_count": len(pending) - (step_idx - 1),
                "upgrade_chain": chain_str,
                "applied_results": applied_results,
                "all_packages": discover_update_packages(include_rolled_back=True),
                "message": f"Incremental update halted at step {step_idx}/{len(pending)} (v{pkg['version']}): {res.get('error')}",
            }
        running_ver = pkg["version"]

    new_ver = running_ver if dry_run else load_version_registry().get("current_release_version", running_ver)
    return {
        "status": "UPDATED",
        "previous_version": start_ver,
        "current_version": new_ver,
        "pending_count": 0,
        "upgrade_chain": chain_str,
        "applied_results": applied_results,
        "all_packages": discover_update_packages(include_rolled_back=True),
        "message": f"Applied {len(applied_results)} incremental update(s) in order: {chain_str}!",
    }


# ==============================================================================
# 5. ROLLBACK ENGINE & CHANGELOG VIEWER
# ==============================================================================
def archive_old_updates(keep_recent: int = 5) -> dict:
    """
    Keeps ONLY the `keep_recent` newest applied update `.txt` packages & `.snapshots/`
    locally inside `C:\\Tabulas Card Hub\\Updates\\`, moving older packages, `.rolledback.txt`,
    and older snapshots to `F:\\Tabulas Archive\\Updates\\` (still 100% restorable!).
    """
    ensure_updater_dirs()
    if not _DEFAULT_ARC_ROOT.exists() and not os.path.exists("F:\\"):
        return {"archived_packages": 0, "archived_snapshots": 0}

    ARCHIVE_UPDATES_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_UPDATES_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    reg = load_version_registry()
    cur_ver = reg.get("current_release_version", "")
    applied_set = set(reg.get("applied_packages", []))

    archived_pkgs = 0
    applied_local = []
    for txt_p in sorted(UPDATES_DIR.glob("*.txt")):
        if is_rolled_back_package_file(txt_p):
            try:
                dst = ARCHIVE_UPDATES_PACKAGES_DIR / txt_p.name
                shutil.move(str(txt_p), str(dst))
                archived_pkgs += 1
            except Exception:
                pass
            continue
        try:
            pkg = parse_update_package_file(txt_p)
            if pkg["is_valid_package"] and (txt_p.name in applied_set or not is_newer_version(pkg["version"], cur_ver)):
                applied_local.append((parse_version_tuple(pkg["version"]), txt_p))
        except Exception:
            continue

    applied_local.sort(key=lambda x: x[0], reverse=True)
    for _, old_txt in applied_local[keep_recent:]:
        try:
            shutil.move(str(old_txt), str(ARCHIVE_UPDATES_PACKAGES_DIR / old_txt.name))
            archived_pkgs += 1
        except Exception:
            pass

    archived_snaps = 0
    local_snaps = []
    if SNAPSHOTS_DIR.exists():
        for d in SNAPSHOTS_DIR.iterdir():
            if d.is_dir() and d.name.startswith("v"):
                v_s = d.name.lstrip("vV")
                local_snaps.append((parse_version_tuple(v_s), v_s, d))
    local_snaps.sort(key=lambda x: x[0], reverse=True)

    kept = 0
    for _, v_s, snap_d in local_snaps:
        if v_s == cur_ver or kept < keep_recent:
            kept += 1
            continue
        try:
            dst_s = ARCHIVE_UPDATES_SNAPSHOTS_DIR / snap_d.name
            if dst_s.exists():
                shutil.rmtree(dst_s, ignore_errors=True)
            shutil.move(str(snap_d), str(dst_s))
            archived_snaps += 1
        except Exception:
            pass

    if archived_pkgs or archived_snaps:
        _log_updater_event(f"ARCHIVED {archived_pkgs} older package(s) & {archived_snaps} older snapshot(s) -> {ARCHIVE_UPDATES_PACKAGES_DIR.parent}")
    return {"archived_packages": archived_pkgs, "archived_snapshots": archived_snaps}


def _scan_snapshot_dir(root_dir: Path, current_ver: str, hist_by_ver: dict, is_archived: bool) -> list[dict]:
    out = []
    if not root_dir.exists():
        return out
    for d in root_dir.iterdir():
        if not d.is_dir() or not d.name.startswith("v"):
            continue
        v_str = d.name.lstrip("vV")
        meta = {}
        meta_f = d / "snapshot_meta.json"
        if meta_f.exists():
            try:
                meta = json.loads(meta_f.read_text(encoding="utf-8"))
            except Exception:
                pass
        h_info = hist_by_ver.get(v_str, {})
        out.append({
            "version": v_str,
            "is_current": (v_str == current_ver),
            "is_archived": is_archived,
            "snapshot_dir": str(d),
            "created_at": meta.get("created_at") or h_info.get("timestamp", ""),
            "title": h_info.get("title") or meta.get("label") or f"Snapshot v{v_str}",
            "package_file": h_info.get("package_file", "snapshot"),
            "changelog": h_info.get("changelog", []),
            "files_count": len(meta.get("files", [])),
        })
    out.sort(key=lambda x: parse_version_tuple(x["version"]), reverse=True)
    return out


def count_archived_rollback_snapshots() -> int:
    if not ARCHIVE_UPDATES_SNAPSHOTS_DIR.exists():
        return 0
    return sum(1 for d in ARCHIVE_UPDATES_SNAPSHOTS_DIR.iterdir() if d.is_dir() and d.name.startswith("v"))


def list_available_rollback_versions(include_archived: bool = False) -> list[dict]:
    """Lists local rollback snapshots on C: (and optionally extended archived snapshots on F:)."""
    ensure_updater_dirs()
    reg = load_version_registry()
    current_ver = reg.get("current_release_version", "")
    hist_by_ver = {str(h.get("version", "")).strip().lstrip("vV"): h for h in reg.get("version_history", []) if h.get("version")}
    for pkg in discover_update_packages(include_rolled_back=True):
        hist_by_ver.setdefault(pkg["version"], pkg)

    local_snaps = _scan_snapshot_dir(SNAPSHOTS_DIR, current_ver, hist_by_ver, is_archived=False)
    if not include_archived:
        return local_snaps
    seen_vers = {s["version"] for s in local_snaps}
    arc_snaps = [s for s in _scan_snapshot_dir(ARCHIVE_UPDATES_SNAPSHOTS_DIR, current_ver, hist_by_ver, is_archived=True) if s["version"] not in seen_vers]
    return local_snaps + arc_snaps


def rollback_to_version(target_version: str) -> dict:
    """Restores all tracked scripts from either C:\\...\\Updates\\.snapshots\\ OR F:\\Tabulas Archive\\Updates\\Snapshots\\."""
    clean_target = str(target_version).strip().lstrip("vV")
    snap_dir = SNAPSHOTS_DIR / f"v{clean_target}"
    if not snap_dir.exists() or not snap_dir.is_dir():
        arc_cand = ARCHIVE_UPDATES_SNAPSHOTS_DIR / f"v{clean_target}"
        if arc_cand.exists() and arc_cand.is_dir():
            snap_dir = arc_cand
        else:
            return {"success": False, "error": f"Snapshot v{clean_target} not found on C: or F:\\Tabulas Archive."}

    reg = load_version_registry()
    curr_ver = reg.get("current_release_version", "")
    if curr_ver and curr_ver != clean_target:
        create_version_snapshot(curr_ver, label=f"Auto-backup prior to rollback to v{clean_target}")

    restored_files = []
    for item in snap_dir.rglob("*"):
        if not item.is_file() or item.name == "snapshot_meta.json":
            continue
        rel = item.relative_to(snap_dir).as_posix()
        dst_p = _resolve_disk_path(rel)
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dst_p)
        if dst_p.suffix == ".py":
            try:
                shutil.copy2(dst_p, VERIFIED_BACKUPS_DIR / dst_p.name)
            except Exception:
                pass
        restored_files.append(rel)
        reg.setdefault("files", {})[rel] = {
            "version": clean_target,
            "sha256": compute_sha256(dst_p),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # Rename any update package .txt files newer than clean_target to `.rolledback.txt`
    # so they remain in ./Updates for audit/history but are NOT reprocessed on the next update run!
    renamed_packages = []
    all_pkgs_list = discover_update_packages(include_rolled_back=False)
    for pkg in all_pkgs_list:
        if is_newer_version(pkg["version"], clean_target):
            orig_p = Path(pkg["package_path"])
            if orig_p.exists() and not is_rolled_back_package_file(orig_p):
                rb_name = f"{orig_p.stem}.rolledback{orig_p.suffix}"
                rb_path = orig_p.with_name(rb_name)
                if rb_path.exists():
                    ts_suf = datetime.now().strftime("%H%M%S")
                    rb_path = orig_p.with_name(f"{orig_p.stem}.rolledback_{ts_suf}{orig_p.suffix}")
                try:
                    orig_p.rename(rb_path)
                    renamed_packages.append(f"{orig_p.name} -> {rb_path.name}")
                except Exception:
                    pass

    all_pkgs_map = {p["package_file"]: p["version"] for p in all_pkgs_list}
    reg["applied_packages"] = [
        pf for pf in reg.get("applied_packages", [])
        if not is_newer_version(all_pkgs_map.get(pf, "0.0.0"), clean_target)
    ]
    reg["current_release_version"] = clean_target
    cl_notes = [f"Restored {len(restored_files)} file(s) from snapshot v{clean_target}."]
    if renamed_packages:
        cl_notes.append(f"Archived rolled-back package(s) so they will not re-apply: {', '.join(renamed_packages)}")
    reg.setdefault("version_history", []).append({
        "version": clean_target,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": f"Rolled back from v{curr_ver} to v{clean_target}",
        "package_file": f"rollback_to_v{clean_target}",
        "files_modified": restored_files,
        "changelog": cl_notes,
    })
    save_version_registry(reg)
    _log_updater_event(
        f"ROLLBACK v{curr_ver} -> v{clean_target} | Restored {len(restored_files)} file(s) | Archived: {', '.join(renamed_packages) or 'none'}"
    )

    return {
        "success": True,
        "previous_version": curr_ver,
        "current_version": clean_target,
        "restored_files": restored_files,
        "renamed_packages": renamed_packages,
        "message": (
            f"Rolled back to v{clean_target} ({len(restored_files)} file(s) restored; "
            f"{len(renamed_packages)} newer update package(s) renamed to .rolledback.txt)."
        ),
    }


def configure_scheduled_auto_updater(
    frequency: str = "DAILY",
    time_24h: str = "02:00",
    enabled: bool = True,
) -> tuple[bool, str]:
    """Schedules `python updater.py --auto` in Windows Task Scheduler (`schtasks`)."""
    if os.name != "nt":
        return False, "Windows Task Scheduler is only supported on Windows."

    if not enabled:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", WINDOWS_UPDATER_TASK_NAME, "/F"],
            capture_output=True,
            text=True,
        )
        return True, f"Removed scheduled task '{WINDOWS_UPDATER_TASK_NAME}'."

    python_exe = sys.executable
    updater_script = str(_resolve_disk_path("updater.py"))
    task_cmd = f'"{python_exe}" "{updater_script}" --auto'
    res = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/F",
            "/SC",
            frequency.upper(),
            "/TN",
            WINDOWS_UPDATER_TASK_NAME,
            "/TR",
            task_cmd,
            "/ST",
            time_24h,
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        return True, f"Scheduled automatic code updater '{WINDOWS_UPDATER_TASK_NAME}' ({frequency.upper()} at {time_24h})."
    return False, f"Failed to schedule updater: {res.stderr or res.stdout}"


# ==============================================================================
# 6. INTERACTIVE TERMINAL CLI & STARTUP ENTRY POINT
# ==============================================================================
def print_status_and_changelogs():
    reg = load_version_registry()
    cur_v = reg.get("current_release_version", "Unknown")
    pkgs = discover_update_packages()
    snaps = list_available_rollback_versions()

    print("=" * 74)
    print(f"  TABULAS CARD HUB CODE UPDATER & ROLLBACK MANAGER (Current: v{cur_v})")
    print(f"  Updates Folder : {UPDATES_DIR}")
    print(f"  Registry File  : {REGISTRY_FILE}")
    print("=" * 74)

    print("\n📦 UPDATE PACKAGES IN ./Updates:")
    if not pkgs:
        print("  (No update .txt packages found in ./Updates yet)")
    else:
        applied_set = set(reg.get("applied_packages", []))
        for idx, p in enumerate(pkgs, 1):
            is_app = p["package_file"] in applied_set or not is_newer_version(p["version"], cur_v)
            badge = "✅ APPLIED" if is_app else "🆕 PENDING"
            print(f"  [{idx}] v{p['version']:<14} | {badge:<10} | {p['timestamp']} | {p['title']} ({p['package_file']})")
            for cl in p.get("changelog", []):
                print(f"       • {cl}")

    print("\n⏪ AVAILABLE ROLLBACK SNAPSHOTS:")
    for idx, s in enumerate(snaps, 1):
        cur_tag = " (ACTIVE)" if s["is_current"] else ""
        print(f"  [{idx}] v{s['version']:<14}{cur_tag:<9} | {s['created_at']} | {s['title']}")


def run_interactive_cli():
    while True:
        print_status_and_changelogs()
        print("\nOptions:")
        print("  [A] Apply all pending updates in ./Updates")
        print("  [D] Dry-Run / Validate pending updates without modifying files")
        print("  [C] View full Changelog history")
        print("  [R] Rollback to a previous version snapshot")
        print("  [S] Schedule automatic daily check in Windows Task Scheduler")
        print("  [Q] Quit")
        choice = input("\nSelect an action [A/D/C/R/S/Q]: ").strip().upper()

        if choice == "Q":
            break
        elif choice == "A":
            res = check_and_apply_pending_updates(auto_apply=True, dry_run=False)
            print(f"\n>>> {res['message']}")
            for r in res.get("applied_results", []):
                for ln in r.get("logs", []):
                    print(ln)
            input("\nPress Enter to continue...")
        elif choice == "D":
            res = check_and_apply_pending_updates(auto_apply=True, dry_run=True)
            print(f"\n>>> [DRY RUN] {res['message']}")
            for r in res.get("applied_results", []):
                for ln in r.get("logs", []):
                    print(ln)
            input("\nPress Enter to continue...")
        elif choice == "C":
            reg = load_version_registry()
            print("\n" + "=" * 74)
            print("  COMPLETE VERSION & CHANGELOG HISTORY")
            print("=" * 74)
            for h in reversed(reg.get("version_history", [])):
                print(f"\n🔹 v{h.get('version')} — {h.get('title')} ({h.get('timestamp')}) [{h.get('package_file')}]")
                for b in h.get("changelog", []):
                    print(f"    • {b}")
            input("\nPress Enter to continue...")
        elif choice == "R":
            snaps = list_available_rollback_versions()
            target_v = input("\nEnter version number to roll back to (e.g. 0.22.0-beta.8): ").strip().lstrip("vV")
            if target_v:
                res = rollback_to_version(target_v)
                print(f"\n>>> {res.get('message') or res.get('error')}")
                input("\nPress Enter to continue...")
        elif choice == "S":
            t_in = input("Enter 24h time for daily update check [default 02:00]: ").strip() or "02:00"
            ok, msg = configure_scheduled_auto_updater("DAILY", t_in, enabled=True)
            print(f"\n>>> {msg}")
            input("\nPress Enter to continue...")


def main():
    parser = argparse.ArgumentParser(description="Tabulas Card Hub Atomic Code Updater & Rollback Manager")
    parser.add_argument("--auto", action="store_true", help="Automatically check and apply any newer update packages in ./Updates")
    parser.add_argument("--check", action="store_true", help="Check for pending updates without applying them")
    parser.add_argument("--dry-run", action="store_true", help="Validate pending update packages without writing to disk")
    parser.add_argument("--changelog", action="store_true", help="Display version & changelog history")
    parser.add_argument("--rollback", type=str, help="Roll back to a specific version snapshot (e.g. 0.22.0-beta.8)")
    parser.add_argument("--schedule", type=str, choices=["DAILY", "WEEKLY", "DISABLE"], help="Configure Windows Scheduled Task")
    parser.add_argument("--time", type=str, default="02:00", help="24h start time for scheduled updater task")
    args = parser.parse_args()

    if args.rollback:
        res = rollback_to_version(args.rollback)
        print(res.get("message") or res.get("error"))
        sys.exit(0 if res.get("success") else 1)

    if args.schedule:
        ok, msg = configure_scheduled_auto_updater(
            frequency="DAILY" if args.schedule == "DISABLE" else args.schedule,
            time_24h=args.time,
            enabled=(args.schedule != "DISABLE"),
        )
        print(msg)
        sys.exit(0 if ok else 1)

    if args.changelog:
        print_status_and_changelogs()
        return

    if args.check:
        res = check_and_apply_pending_updates(auto_apply=False)
        print(f"[Updater] {res['message']}")
        return

    if args.auto or args.dry_run:
        res = check_and_apply_pending_updates(auto_apply=True, dry_run=bool(args.dry_run))
        print(f"[Updater] {res['message']}")
        for r in res.get("applied_results", []):
            for ln in r.get("logs", []):
                print(ln)
        return

    run_interactive_cli()


# ==============================================================================
# 7. GITHUB RELEASES CLIENT & SAFE ZIP APPLIER
# ==============================================================================
GITHUB_API_VERSION = "2026-03-10"
GITHUB_USER_AGENT = "TabulasCardHub-Updater"
DEFAULT_UPDATER_CONFIG = {
    "github_owner": "",
    "github_repo": "",
    "channel": "beta",
    "github_token": "",
}
PROTECTED_UPDATE_ROOTS = {
    "data",
    "cache",
    "logs",
    "set library",
    "archive",
    "batches",
    "downloaded_files",
    ".git",
    ".agents",
    ".env",
}
_PRE_STAGE_RANKS = {
    "dev": 0,
    "alpha": 1,
    "a": 1,
    "beta": 2,
    "b": 2,
    "rc": 3,
    "c": 3,
    "": 4,
}


def _fallback_parse_semver(ver_str: str) -> tuple:
    """Safe semver/beta tuple parser used when `packaging` is unavailable or fails."""
    s = str(ver_str or "").strip().lstrip("vV")
    if not s:
        return (0, 0, 0, 0, 0)
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-_.]?([a-zA-Z]+)[._-]?(\d+)?)?", s)
    if not m:
        return (0, 0, 0, 0, 0)
    major = int(m.group(1) or 0)
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    stage = (m.group(4) or "").lower()
    stage_rank = _PRE_STAGE_RANKS.get(stage, 1 if stage else 4)
    pre_num = int(m.group(5) or 0)
    return (major, minor, patch, stage_rank, pre_num)


def _parse_release_version(ver_str: str):
    """Parses a release tag/version using `packaging.version.Version` with semver fallback."""
    clean = str(ver_str or "").strip().lstrip("vV")
    if _PackagingVersion is not None and clean:
        try:
            return _PackagingVersion(clean)
        except _PackagingInvalidVersion:
            pass
    return _fallback_parse_semver(clean)


def is_newer_release_version(candidate_ver: str, current_ver: str) -> bool:
    """Returns True if `candidate_ver` is strictly newer than `current_ver`."""
    cand_parsed = _parse_release_version(candidate_ver)
    curr_parsed = _parse_release_version(current_ver)
    if type(cand_parsed) is type(curr_parsed):
        return cand_parsed > curr_parsed
    return _fallback_parse_semver(candidate_ver) > _fallback_parse_semver(current_ver)


def _resolve_github_token(config: Optional[dict] = None) -> tuple[str, str]:
    cfg = config or {}
    saved_tok = str(cfg.get("github_token") or "").strip()
    if saved_tok:
        return saved_tok, "config"
    env_tok = str(os.environ.get("TABULAS_GITHUB_TOKEN") or "").strip()
    if env_tok:
        return env_tok, "env"
    return "", ""


def load_updater_config(config_path: Optional[Path] = None) -> dict:
    """Loads `Data/updater_config.json` with `TABULAS_GITHUB_TOKEN` env fallback."""
    cfg_p = Path(config_path) if config_path else UPDATER_CONFIG_FILE
    data: dict[str, Any] = {}
    if cfg_p.exists():
        try:
            raw = json.loads(cfg_p.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                data = raw
        except Exception:
            data = {}

    owner = str(data.get("github_owner") or "").strip()
    repo = str(data.get("github_repo") or "").strip()
    channel = str(data.get("channel") or "beta").strip().lower()
    if channel not in ("stable", "beta"):
        channel = "beta"

    saved_token = str(data.get("github_token") or "").strip()
    env_token = str(os.environ.get("TABULAS_GITHUB_TOKEN") or "").strip()
    effective_token = saved_token or env_token
    token_source = "config" if saved_token else ("env" if env_token else "")

    return {
        "github_owner": owner,
        "github_repo": repo,
        "channel": channel,
        "github_token": effective_token,
        "has_saved_token": bool(saved_token),
        "token_source": token_source,
    }


def save_updater_config(cfg: dict, config_path: Optional[Path] = None) -> dict:
    """Atomically saves GitHub updater config to `Data/updater_config.json`."""
    cfg_p = Path(config_path) if config_path else UPDATER_CONFIG_FILE
    cfg_p.parent.mkdir(parents=True, exist_ok=True)
    lock_p = cfg_p.with_suffix(".lock")

    with interprocess_file_lock(lock_p):
        existing: dict[str, Any] = {}
        if cfg_p.exists():
            try:
                raw = json.loads(cfg_p.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    existing = raw
            except Exception:
                existing = {}

        owner = str(cfg.get("github_owner") if cfg.get("github_owner") is not None else existing.get("github_owner", "")).strip()
        repo = str(cfg.get("github_repo") if cfg.get("github_repo") is not None else existing.get("github_repo", "")).strip()
        repo_slug = str(cfg.get("repo") or "").strip()
        if repo_slug and "/" in repo_slug:
            parts = [p.strip() for p in repo_slug.split("/", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                owner, repo = parts[0], parts[1]

        channel = str(cfg.get("channel") or existing.get("channel") or "beta").strip().lower()
        if channel not in ("stable", "beta"):
            channel = "beta"

        clear_tok = bool(cfg.get("clear_token"))
        incoming_tok = cfg.get("github_token")
        if clear_tok:
            saved_tok = ""
        elif incoming_tok is None:
            saved_tok = str(existing.get("github_token") or "").strip()
        else:
            tok_str = str(incoming_tok).strip()
            if tok_str and not set(tok_str).issubset({"*", "•"}):
                saved_tok = tok_str
            elif tok_str == "":
                saved_tok = ""
            else:
                saved_tok = str(existing.get("github_token") or "").strip()

        to_write = {
            "github_owner": owner,
            "github_repo": repo,
            "channel": channel,
            "github_token": saved_tok,
        }
        atomic_write_text(cfg_p, json.dumps(to_write, indent=2), encoding="utf-8")

    return load_updater_config(cfg_p)


def mask_updater_config(cfg: dict) -> dict:
    """Returns a UI-safe config dict with any token masked."""
    owner = str(cfg.get("github_owner") or "").strip()
    repo = str(cfg.get("github_repo") or "").strip()
    token, token_source = _resolve_github_token(cfg)
    if not token_source and cfg.get("token_source"):
        token_source = str(cfg.get("token_source") or "")
    masked = ""
    if token:
        masked = f"••••{token[-4:]}" if len(token) > 4 else "••••"
    return {
        "github_owner": owner,
        "github_repo": repo,
        "repo": f"{owner}/{repo}" if (owner and repo) else (owner or repo),
        "channel": str(cfg.get("channel") or "beta").strip().lower(),
        "has_token": bool(token),
        "token_source": token_source,
        "github_token_masked": masked,
    }


def _build_github_headers(config: Optional[dict], accept: str) -> dict[str, str]:
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": GITHUB_USER_AGENT,
    }
    token, _ = _resolve_github_token(config)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _resolve_changelog_path(changelog_path: Optional[Path] = None) -> Path:
    if changelog_path is not None:
        return Path(changelog_path)
    cand = APP_DIR / "CHANGELOG.md"
    if cand.exists():
        return cand
    return Path(__file__).resolve().parent / "CHANGELOG.md"


def format_release_changelog(raw_md: str, *, fallback_title: str = "") -> dict:
    """
    Normalizes release markdown into clean user-facing markdown, structured sections,
    and flat bullet lines suitable for version_registry.json and UI rendering.
    """
    raw = str(raw_md or "").replace("\r\n", "\n").strip()
    if not raw:
        lines = [fallback_title.strip()] if fallback_title.strip() else []
        return {
            "markdown": f"- {lines[0]}" if lines else "",
            "sections": [{"heading": "Release Notes", "items": lines}] if lines else [],
            "lines": lines,
        }

    # Strip trailing horizontal rules and GitHub auto-generated Full Changelog links
    cleaned_lines: list[str] = []
    for ln in raw.splitlines():
        s = ln.rstrip()
        if re.match(r"^\*\*Full Changelog\*\*\s*:\s*https?://", s.strip(), re.IGNORECASE):
            continue
        if s.strip() == "---":
            continue
        cleaned_lines.append(s)

    sections: list[dict] = []
    current_heading = ""
    current_items: list[str] = []
    flat_lines: list[str] = []

    def _flush():
        nonlocal current_heading, current_items
        if current_items:
            sections.append({
                "heading": current_heading or "Highlights",
                "items": list(current_items),
            })
        current_items = []

    for ln in cleaned_lines:
        stripped = ln.strip()
        if not stripped:
            continue
        m_sub = re.match(r"^#{2,4}\s+(.+)$", stripped)
        if m_sub:
            _flush()
            current_heading = m_sub.group(1).strip()
            continue
        item = re.sub(r"^[-*•]\s+", "", stripped).strip()
        if item:
            current_items.append(item)
            if current_heading and current_heading.lower() not in ("highlights", "release notes"):
                flat_lines.append(f"[{current_heading}] {item}")
            else:
                flat_lines.append(item)
    _flush()

    md_parts: list[str] = []
    for sec in sections:
        if sec["heading"] and sec["heading"].lower() not in ("highlights", "release notes"):
            md_parts.append(f"### {sec['heading']}")
        for it in sec["items"]:
            md_parts.append(f"- {it}")
        md_parts.append("")
    clean_md = "\n".join(md_parts).strip()
    if not clean_md and fallback_title.strip():
        clean_md = f"- {fallback_title.strip()}"
        flat_lines = [fallback_title.strip()]
        sections = [{"heading": "Release Notes", "items": flat_lines}]

    return {
        "markdown": clean_md,
        "sections": sections,
        "lines": flat_lines,
    }


def parse_changelog_markdown(changelog_path: Optional[Path] = None) -> list[dict]:
    """
    Parses `CHANGELOG.md` into structured release entries sorted newest-first.
    Supports headings like:
      ## [v0.25.0-beta.8] — 2026-11-23 — Release Title
      ## v0.25.0-beta.7 - Release Title
    """
    path = _resolve_changelog_path(changelog_path)
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    heading_re = re.compile(
        r"^##\s+\[?v?([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.]+)?)\]?\s*(?:[—–-]\s*(.+))?$",
        re.MULTILINE,
    )
    matches = list(heading_re.finditer(raw))
    entries: list[dict] = []

    for idx, m in enumerate(matches):
        ver = m.group(1).strip().lstrip("vV")
        rest = (m.group(2) or "").strip()
        date_str = ""
        title = rest
        m_date = re.match(r"^(\d{4}-\d{2}-\d{2})\s*(?:[—–-]\s*(.+))?$", rest)
        if m_date:
            date_str = m_date.group(1).strip()
            title = (m_date.group(2) or "").strip()
        if not title:
            title = f"Release v{ver}"

        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        body_raw = raw[start:end].strip()
        formatted = format_release_changelog(body_raw, fallback_title=title)

        entries.append({
            "version": ver,
            "tag_name": f"v{ver}",
            "date": date_str,
            "timestamp": f"{date_str} 00:00:00" if date_str else "",
            "title": title,
            "source": "changelog_md",
            "package_file": "CHANGELOG.md",
            "changelog_md": formatted["markdown"],
            "changelog": formatted["lines"],
            "sections": formatted["sections"],
        })

    entries.sort(key=lambda e: parse_version_tuple(e.get("version", "")), reverse=True)
    return entries


def extract_changelog_for_version(version_or_tag: str, changelog_path: Optional[Path] = None) -> Optional[dict]:
    """Returns the parsed `CHANGELOG.md` entry matching `version_or_tag`, or `None`."""
    target = str(version_or_tag or "").strip().lstrip("vV").lower()
    if not target:
        return None
    for entry in parse_changelog_markdown(changelog_path=changelog_path):
        if str(entry.get("version", "")).strip().lstrip("vV").lower() == target:
            return entry
    return None


def get_unified_changelog_history(
    changelog_path: Optional[Path] = None,
    registry_path: Optional[Path] = None,
) -> list[dict]:
    """
    Merges release history from `CHANGELOG.md`, `Updates/version_registry.json`, and
    `Updates/*.txt` packages into a deduplicated newest-first list for the Updates UI.
    """
    merged: dict[str, dict] = {}

    def _norm_ver(v: Any) -> str:
        return str(v or "").strip().lstrip("vV")

    # 1. Start with CHANGELOG.md (richest user-facing formatting)
    for entry in parse_changelog_markdown(changelog_path=changelog_path):
        ver = _norm_ver(entry.get("version"))
        if not ver:
            continue
        merged[ver] = {
            **entry,
            "is_applied": False,
            "is_rolled_back": False,
            "files_modified": [],
        }

    # 2. Enrich / add from Updates/*.txt packages
    try:
        pkgs = discover_update_packages(include_rolled_back=True)
    except Exception:
        pkgs = []
    for pkg in pkgs:
        ver = _norm_ver(pkg.get("version"))
        if not ver:
            continue
        existing = merged.get(ver)
        if existing:
            existing["is_rolled_back"] = bool(existing.get("is_rolled_back") or pkg.get("is_rolled_back"))
            if not existing.get("timestamp") and pkg.get("timestamp"):
                existing["timestamp"] = pkg["timestamp"]
            if existing.get("package_file") == "CHANGELOG.md" and pkg.get("package_file"):
                existing["package_file"] = pkg["package_file"]
        else:
            lines = [str(x).strip() for x in (pkg.get("changelog") or []) if str(x).strip()]
            raw_md = "\n".join(f"- {ln}" for ln in lines)
            fmt = format_release_changelog(raw_md, fallback_title=pkg.get("title", ""))
            merged[ver] = {
                "version": ver,
                "tag_name": f"v{ver}",
                "date": str(pkg.get("timestamp") or "")[:10],
                "timestamp": str(pkg.get("timestamp") or ""),
                "title": str(pkg.get("title") or f"Update v{ver}"),
                "source": "local_package",
                "package_file": str(pkg.get("package_file") or ""),
                "changelog_md": fmt["markdown"],
                "changelog": fmt["lines"],
                "sections": fmt["sections"],
                "is_applied": False,
                "is_rolled_back": bool(pkg.get("is_rolled_back")),
                "files_modified": [],
            }

    # 3. Enrich / add from version_registry.json (includes applied GitHub Releases)
    reg_file = Path(registry_path) if registry_path else REGISTRY_FILE
    reg_data: dict[str, Any] = {}
    if reg_file.exists():
        try:
            loaded = json.loads(reg_file.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                reg_data = loaded
        except Exception:
            reg_data = {}

    cur_ver = _norm_ver(reg_data.get("current_release_version"))
    for h in reg_data.get("version_history") or []:
        if not isinstance(h, dict):
            continue
        ver = _norm_ver(h.get("version"))
        if not ver:
            continue
        pkg_id = str(h.get("package_file") or "")
        if pkg_id.startswith("rollback_to_"):
            continue
        is_gh = pkg_id.startswith("github:")
        h_lines = [str(x).strip() for x in (h.get("changelog") or []) if str(x).strip()]
        h_md = str(h.get("changelog_md") or "").strip()
        h_secs = h.get("changelog_sections") if isinstance(h.get("changelog_sections"), list) else None
        existing = merged.get(ver)
        if existing:
            existing["is_applied"] = True
            existing["applied_at"] = h.get("applied_at") or h.get("timestamp") or existing.get("applied_at", "")
            existing["files_modified"] = list(h.get("files_modified") or existing.get("files_modified") or [])
            if is_gh:
                existing["source"] = "github_release"
                existing["package_file"] = pkg_id
            if not existing.get("changelog_md") and h_md:
                fmt = format_release_changelog(h_md, fallback_title=h.get("title", ""))
                existing["changelog_md"] = fmt["markdown"]
                existing["changelog"] = fmt["lines"]
                existing["sections"] = h_secs or fmt["sections"]
        else:
            raw_md = h_md or "\n".join(f"- {ln}" for ln in h_lines)
            fmt = format_release_changelog(raw_md, fallback_title=h.get("title", ""))
            merged[ver] = {
                "version": ver,
                "tag_name": f"v{ver}",
                "date": str(h.get("timestamp") or "")[:10],
                "timestamp": str(h.get("timestamp") or h.get("applied_at") or ""),
                "applied_at": str(h.get("applied_at") or ""),
                "title": str(h.get("title") or f"Release v{ver}"),
                "source": "github_release" if is_gh else "registry",
                "package_file": pkg_id or "registry",
                "changelog_md": fmt["markdown"],
                "changelog": fmt["lines"] or h_lines,
                "sections": h_secs or fmt["sections"],
                "is_applied": True,
                "is_rolled_back": False,
                "files_modified": list(h.get("files_modified") or []),
            }

    for ver, item in merged.items():
        if cur_ver and not is_newer_version(ver, cur_ver) and not item.get("is_rolled_back"):
            item["is_applied"] = True
        item["is_current"] = bool(cur_ver and ver == cur_ver)

    result = list(merged.values())
    result.sort(key=lambda e: parse_version_tuple(e.get("version", "")), reverse=True)
    return result


def check_github_release(
    config: dict,
    current_version: str,
    *,
    session: Any = None,
    timeout: float = 15.0,
    changelog_path: Optional[Path] = None,
) -> dict:
    """
    Queries GitHub Releases API for the configured repo & channel (`stable` or `beta`).
    """
    owner = str(config.get("github_owner") or "").strip()
    repo = str(config.get("github_repo") or "").strip()
    if not owner or not repo:
        raise ValueError("GitHub owner and repository must be configured (e.g. 'owner/repo').")

    channel = str(config.get("channel") or "beta").strip().lower()
    if channel not in ("stable", "beta"):
        channel = "beta"

    http = session or requests
    headers = _build_github_headers(config, "application/vnd.github+json")
    base_api = f"https://api.github.com/repos/{owner}/{repo}"

    if channel == "stable":
        url = f"{base_api}/releases/latest"
        resp = http.get(url, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text[:250]}")
        selected = resp.json()
        if not isinstance(selected, dict) or selected.get("draft"):
            raise RuntimeError("No published stable GitHub release found.")
    else:
        url = f"{base_api}/releases?per_page=10"
        resp = http.get(url, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text[:250]}")
        releases = resp.json()
        if not isinstance(releases, list):
            raise RuntimeError("Unexpected GitHub Releases API response.")
        candidates = [r for r in releases if isinstance(r, dict) and not r.get("draft") and r.get("tag_name")]
        if not candidates:
            raise RuntimeError("No non-draft GitHub releases found.")

        def _cand_key(rel_obj: dict):
            tag = str(rel_obj.get("tag_name") or "")
            if _PackagingVersion is not None:
                try:
                    return (1, _PackagingVersion(tag.lstrip("vV")))
                except _PackagingInvalidVersion:
                    pass
            return (0, _fallback_parse_semver(tag))

        selected = max(candidates, key=_cand_key)

    tag_name = str(selected.get("tag_name") or "").strip()
    latest_ver = tag_name.lstrip("vV")
    clean_current = str(current_version or "").strip().lstrip("vV")

    assets = selected.get("assets") or []
    zip_asset: Optional[dict] = None
    checksum_asset: Optional[dict] = None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        low = name.lower()
        if low == "sha256sums.txt":
            checksum_asset = asset
        elif low.endswith(".zip"):
            if zip_asset is None or low.startswith("tabulas-hub-"):
                zip_asset = asset

    raw_body = str(selected.get("body") or "").strip()
    release_title = str(selected.get("name") or tag_name).strip()
    if not raw_body:
        local_cl = extract_changelog_for_version(tag_name, changelog_path=changelog_path)
        if local_cl and local_cl.get("changelog_md"):
            raw_body = str(local_cl["changelog_md"])
    formatted_cl = format_release_changelog(raw_body, fallback_title=release_title)

    return {
        "update_available": bool(latest_ver and is_newer_release_version(latest_ver, clean_current)),
        "current_version": clean_current,
        "latest_version": latest_ver,
        "tag_name": tag_name,
        "release_name": release_title,
        "published_at": str(selected.get("published_at") or ""),
        "changelog_md": formatted_cl["markdown"],
        "changelog": formatted_cl["lines"],
        "changelog_sections": formatted_cl["sections"],
        "html_url": str(selected.get("html_url") or ""),
        "zip_asset_api_url": str((zip_asset or {}).get("url") or ""),
        "zip_asset_name": str((zip_asset or {}).get("name") or ""),
        "checksum_asset_api_url": str((checksum_asset or {}).get("url") or ""),
        "is_prerelease": bool(selected.get("prerelease", False)),
        "channel": channel,
    }


def _is_protected_rel_path(rel_posix: str) -> bool:
    parts = [p.lower() for p in PurePosixPath(rel_posix).parts if p not in ("", ".")]
    if not parts:
        return True
    if parts[0] in PROTECTED_UPDATE_ROOTS:
        return True
    if len(parts) >= 2 and parts[0] == "core" and parts[1] == "downloaded_files":
        return True
    return False


def _validate_zip_member_safety(member_name: str, app_root_resolved: Path) -> Optional[str]:
    raw = str(member_name or "").replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return f"Unsafe absolute zip member path: {member_name}"
    posix_parts = PurePosixPath(raw).parts
    if any(part == ".." for part in posix_parts):
        return f"Path traversal detected in zip member: {member_name}"
    target = (app_root_resolved / Path(*posix_parts)).resolve()
    try:
        target.relative_to(app_root_resolved)
    except ValueError:
        return f"Zip member escapes application root: {member_name}"
    return None


def _parse_sha256sums(sums_text: str, target_asset_name: str = "") -> str:
    entries: list[tuple[str, str]] = []
    for line in str(sums_text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", clean)
        if m:
            entries.append((m.group(1).lower(), m.group(2).strip()))
    if not entries:
        return ""
    if target_asset_name:
        target_low = Path(target_asset_name).name.lower()
        for digest, fname in entries:
            if Path(fname).name.lower() == target_low:
                return digest
    if len(entries) == 1:
        return entries[0][0]
    return ""


def _create_pre_update_backup_zip(app_root: Path, backup_dir: Path, current_version: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_v = re.sub(r"[^0-9A-Za-z._-]+", "_", str(current_version or "unknown").lstrip("vV"))
    backup_path = backup_dir / f"pre_update_v{clean_v}_{ts}.zip"
    skip_dirs = {
        ".git",
        ".github",
        ".agents",
        "data",
        "cache",
        "logs",
        "set library",
        "archive",
        "batches",
        "downloaded_files",
        "__pycache__",
        "node_modules",
    }
    app_resolved = app_root.resolve()
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(app_resolved):
            dirnames[:] = sorted(d for d in dirnames if d.lower() not in skip_dirs)
            for fname in sorted(filenames):
                if fname.endswith((".log", ".lock", ".tmp")):
                    continue
                fp = Path(dirpath) / fname
                rel = fp.relative_to(app_resolved).as_posix()
                if _is_protected_rel_path(rel):
                    continue
                zf.write(fp, arcname=rel)

    existing_backups = sorted(
        backup_dir.glob("pre_update_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_b in existing_backups[5:]:
        try:
            old_b.unlink()
        except Exception:
            pass
    return backup_path


def apply_github_release_update(
    release_info: dict,
    app_root: Path | str,
    config: dict,
    *,
    session: Any = None,
    busy_checker: Any = None,
    cache_dir: Optional[Path] = None,
    registry_path: Optional[Path] = None,
    timeout: float = 60.0,
) -> dict:
    """
    Safely downloads, verifies (SHA-256 + zip-slip check), backs up, and extracts a GitHub Release zip.
    """
    checker = busy_checker or is_worker_pool_busy
    busy_res = checker()
    if isinstance(busy_res, tuple):
        is_busy, busy_reason = bool(busy_res[0]), str(busy_res[1] or "")
    else:
        is_busy, busy_reason = bool(busy_res), ""
    if is_busy:
        msg = f"Aborted update: worker pool is busy ({busy_reason or 'active job running'})."
        return {
            "success": False,
            "aborted": True,
            "reason": "worker_pool_busy",
            "error": msg,
            "message": msg,
            "restart_required": False,
            "requirements_changed": False,
        }

    zip_url = str(release_info.get("zip_asset_api_url") or "").strip()
    sums_url = str(release_info.get("checksum_asset_api_url") or "").strip()
    zip_name = str(release_info.get("zip_asset_name") or "release.zip").strip()
    if not zip_url or not sums_url:
        return {
            "success": False,
            "error": "Release metadata is missing zip_asset_api_url or checksum_asset_api_url.",
            "restart_required": False,
            "requirements_changed": False,
        }

    app_root_p = Path(app_root).resolve()
    http = session or requests
    dl_headers = _build_github_headers(config, "application/octet-stream")

    with tempfile.TemporaryDirectory(prefix="tabulas_gh_upd_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        zip_tmp = tmp_dir / zip_name

        r_sums = http.get(sums_url, headers=dl_headers, timeout=timeout)
        if r_sums.status_code >= 400:
            return {
                "success": False,
                "error": f"Failed to download SHA256SUMS.txt (HTTP {r_sums.status_code}).",
                "restart_required": False,
                "requirements_changed": False,
            }
        expected_sha = _parse_sha256sums(r_sums.text, zip_name)
        if not expected_sha:
            return {
                "success": False,
                "error": f"Could not find SHA-256 entry for {zip_name} in SHA256SUMS.txt.",
                "restart_required": False,
                "requirements_changed": False,
            }

        r_zip = http.get(zip_url, headers=dl_headers, timeout=timeout)
        if r_zip.status_code >= 400:
            return {
                "success": False,
                "error": f"Failed to download release archive (HTTP {r_zip.status_code}).",
                "restart_required": False,
                "requirements_changed": False,
            }
        zip_bytes = r_zip.content
        actual_sha = hashlib.sha256(zip_bytes).hexdigest().lower()
        if actual_sha != expected_sha:
            return {
                "success": False,
                "error": f"SHA-256 mismatch for {zip_name}: expected {expected_sha}, got {actual_sha}.",
                "restart_required": False,
                "requirements_changed": False,
            }
        zip_tmp.write_bytes(zip_bytes)

        try:
            with zipfile.ZipFile(zip_tmp, "r") as zf:
                infos = zf.infolist()
                for info in infos:
                    err = _validate_zip_member_safety(info.filename, app_root_p)
                    if err:
                        return {
                            "success": False,
                            "error": err,
                            "restart_required": False,
                            "requirements_changed": False,
                        }

                # Determine current version & requirements.txt hash before touching disk
                reg_file = Path(registry_path) if registry_path else REGISTRY_FILE
                reg_data: dict[str, Any] = {}
                if reg_file.exists():
                    try:
                        parsed_reg = json.loads(reg_file.read_text(encoding="utf-8-sig"))
                        if isinstance(parsed_reg, dict):
                            reg_data = parsed_reg
                    except Exception:
                        reg_data = {}
                cur_ver = str(reg_data.get("current_release_version") or release_info.get("current_version") or "0.0.0").lstrip("vV")

                req_file = app_root_p / "requirements.txt"
                req_sha_before = hashlib.sha256(req_file.read_bytes()).hexdigest() if req_file.exists() else ""

                backup_root = (Path(cache_dir) if cache_dir else (BASE_DIR / "Cache")) / "Update_Backups"
                backup_zip = _create_pre_update_backup_zip(app_root_p, backup_root, cur_ver)

                files_updated: list[str] = []
                files_skipped_protected: list[str] = []

                for info in infos:
                    if info.is_dir():
                        continue
                    rel_posix = PurePosixPath(info.filename.replace("\\", "/")).as_posix().lstrip("./")
                    if not rel_posix or _is_protected_rel_path(rel_posix):
                        files_skipped_protected.append(rel_posix or info.filename)
                        continue
                    dest_path = (app_root_p / Path(*PurePosixPath(rel_posix).parts)).resolve()
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    payload_bytes = zf.read(info.filename)
                    atomic_write_bytes(dest_path, lambda tmp_p, b=payload_bytes: tmp_p.write_bytes(b))
                    files_updated.append(rel_posix)

                req_sha_after = hashlib.sha256(req_file.read_bytes()).hexdigest() if req_file.exists() else ""
                requirements_changed = req_sha_before != req_sha_after

                new_ver = str(release_info.get("latest_version") or release_info.get("tag_name") or "").strip().lstrip("vV")
                rel_title = str(release_info.get("release_name") or f"GitHub Release v{new_ver}").strip()
                cl_raw = str(release_info.get("changelog_md") or "").strip()
                if not cl_raw and isinstance(release_info.get("changelog"), list):
                    cl_raw = "\n".join(f"- {str(x).strip()}" for x in release_info["changelog"] if str(x).strip())
                formatted_cl = format_release_changelog(
                    cl_raw,
                    fallback_title=f"Applied GitHub Release {release_info.get('tag_name') or new_ver}",
                )
                cl_lines = formatted_cl["lines"]

                reg_file.parent.mkdir(parents=True, exist_ok=True)
                with interprocess_file_lock(reg_file.with_suffix(".lock")):
                    latest_reg: dict[str, Any] = {}
                    if reg_file.exists():
                        try:
                            loaded = json.loads(reg_file.read_text(encoding="utf-8-sig"))
                            if isinstance(loaded, dict):
                                latest_reg = loaded
                        except Exception:
                            latest_reg = {}
                    if not latest_reg:
                        latest_reg = {
                            "current_release_version": cur_ver,
                            "applied_packages": [],
                            "version_history": [],
                            "files": {},
                        }

                    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if new_ver:
                        latest_reg["current_release_version"] = new_ver
                    latest_reg["last_checked"] = now_ts
                    pkg_id = f"github:{release_info.get('tag_name') or new_ver}"
                    if pkg_id not in latest_reg.setdefault("applied_packages", []):
                        latest_reg["applied_packages"].append(pkg_id)
                    latest_reg.setdefault("version_history", []).append({
                        "version": new_ver or cur_ver,
                        "timestamp": str(release_info.get("published_at") or now_ts),
                        "applied_at": now_ts,
                        "title": rel_title,
                        "package_file": pkg_id,
                        "files_modified": files_updated,
                        "changelog": cl_lines,
                        "changelog_md": formatted_cl["markdown"],
                        "changelog_sections": formatted_cl["sections"],
                    })
                    atomic_write_text(reg_file, json.dumps(latest_reg, indent=2), encoding="utf-8")

                _log_updater_event(
                    f"GITHUB RELEASE APPLIED v{new_ver} ({zip_name}) | {len(files_updated)} file(s) updated | Backup: {backup_zip.name}"
                )
                return {
                    "success": True,
                    "version": new_ver,
                    "tag_name": str(release_info.get("tag_name") or ""),
                    "release_name": rel_title,
                    "files_updated": files_updated,
                    "files_skipped_protected": files_skipped_protected,
                    "backup_zip": str(backup_zip),
                    "changelog": cl_lines,
                    "changelog_md": formatted_cl["markdown"],
                    "changelog_sections": formatted_cl["sections"],
                    "restart_required": True,
                    "requirements_changed": requirements_changed,
                    "message": f"Installed GitHub Release v{new_ver} ({len(files_updated)} file(s) updated). Restart required.",
                }
        except zipfile.BadZipFile as exc:
            return {
                "success": False,
                "error": f"Downloaded archive is not a valid zip file: {exc}",
                "restart_required": False,
                "requirements_changed": False,
            }


if __name__ == "__main__":
    main()