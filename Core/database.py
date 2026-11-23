from __future__ import annotations
# ==============================================================================
# Core/database.py - 1-CARD-PER-ROW INVENTORY, 7-DIGIT SKU & CHECKLIST ENGINE
# ==============================================================================
import gc
import json
import os
import pickle
import re
import shutil
import stat
import sys
import time
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

__version__ = "0.25.0-beta.1"
__last_updated__ = "2026-11-21 18:45:00"

from Core.config import (
    ACTIVE_BATCH_FILE,
    ARCHIVE_SCAN_PATH,
    BASE_DIR,
    BATCHES_DIR,
    BATCH_MANIFEST_COLUMNS,
    CHECKLIST_CACHE_FILE,
    CHECKLIST_PATH,
    FALLBACK_SCAN_PATH,
    INPUT_PATH,
    INVENTORY_COLUMNS,
    INVENTORY_DIR,
    INVENTORY_FILE,
    LOGS_DIR,
    PROCESSED_ARCHIVE_DIR,
    REFERENCE_TEMPLATES_DIR,
    REVIEWED_CARDS_DIR,
    SKU_START,
    atomic_write_bytes,
    build_card_image_filenames,
    build_card_image_stem,
    canonical_set_key,
    canonical_subset_key,
    ensure_directories,
    format_print_run,
    interprocess_file_lock,
    norm,
    parse_unified_card_filename,
    sanitize_filename_part,
    strip_accents,
)

ACTIVE_JOB_STATE_FILE = LOGS_DIR / "job_state_ingest_inventory.json"
ACTIVE_JOB_LOG_FILE = LOGS_DIR / "job_log_ingest_inventory.log"
LEGACY_JOB_LOG_FILE = LOGS_DIR / "active_job_terminal.log"


# ==============================================================================
# 0. VERBOSE CONSOLE & LIVE MONITOR ACTION LOGGER + ONEDRIVE-SAFE FILE OPS
# ==============================================================================
def log_action_detail(
    msg: str,
    monitor_title: Optional[str] = None,
    current: int = 1,
    total: int = 1,
    status: str = "COMPLETED",
):
    """
    Prints detailed action logs immediately to the console (stdout) AND appends
    them to the Scan & Inventory lane log (job_log_ingest_inventory.log).
    """
    ensure_directories()
    ts = datetime.now().strftime("%H:%M:%S")
    clean_msg = str(msg).rstrip("\r\n")
    if not clean_msg:
        return

    formatted = f"[{ts}] {clean_msg}"
    try:
        print(formatted, flush=True)
    except UnicodeEncodeError:
        print(formatted.encode("ascii", errors="replace").decode("ascii"), flush=True)
    except Exception:
        pass

    ascii_line = clean_msg.encode("ascii", "ignore").decode("ascii")
    for log_f in (ACTIVE_JOB_LOG_FILE, LEGACY_JOB_LOG_FILE):
        try:
            with open(log_f, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {ascii_line}\n")
        except Exception:
            pass

    if monitor_title:
        try:
            running_bg = False
            if ACTIVE_JOB_STATE_FILE.exists():
                with open(ACTIVE_JOB_STATE_FILE, "r", encoding="utf-8") as fr:
                    cur_state = json.load(fr)
                if cur_state.get("status") == "RUNNING" and int(cur_state.get("pid", 0)) > 0:
                    running_bg = True
            if not running_bg:
                now_ep = time.time()
                pct = min(100, int(round(100.0 * current / max(1, total))))
                new_state = {
                    "lane": "ingest_inventory",
                    "status": status,
                    "job_type": "ui_action",
                    "title": monitor_title,
                    "current": int(current),
                    "total": max(1, int(total)),
                    "percent": pct,
                    "current_item": clean_msg[:95],
                    "start_epoch": now_ep,
                    "updated_epoch": now_ep,
                    "elapsed_seconds": 0.0,
                    "eta_seconds": None,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "pid": 0,
                    "error_msg": "",
                }
                with open(ACTIVE_JOB_STATE_FILE, "w", encoding="utf-8") as fw:
                    json.dump(new_state, fw, indent=2)
        except Exception:
            pass


def _clear_readonly_flag(path: Path):
    try:
        if path.exists():
            os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass


def _safe_move_file(src: Path, dst: Path, retries: int = 5) -> bool:
    """Moves a single file safely across Windows/OneDrive folders with copy+unlink fallback."""
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.resolve() == dst.resolve():
            return True
    except Exception:
        pass

    _clear_readonly_flag(src)
    if dst.exists():
        _clear_readonly_flag(dst)

    for attempt in range(retries):
        try:
            if dst.exists():
                dst.unlink()
            os.replace(str(src), str(dst))
            return True
        except Exception:
            if attempt == 1:
                gc.collect()
            time.sleep(0.15 * (attempt + 1))

    try:
        shutil.copy2(str(src), str(dst))
        for _ in range(3):
            try:
                _clear_readonly_flag(src)
                src.unlink()
            except Exception:
                gc.collect()
                time.sleep(0.15)
            else:
                break
        return True
    except Exception as e:
        log_action_detail(f"  [!] Warning: Could not move file {src.name} -> {dst}: {e}")
        return False


def _safe_archive_directory(src_dir: Path, dst_dir: Path) -> Path:
    """Moves a directory into Archive without crashing on Windows/OneDrive file locks."""
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    if not src_dir.exists():
        return dst_dir

    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    if dst_dir.exists():
        dst_dir = dst_dir.parent / f"{dst_dir.name}_{datetime.now().strftime('%H%M%S')}"

    gc.collect()
    _clear_readonly_flag(src_dir)

    try:
        os.rename(str(src_dir), str(dst_dir))
        return dst_dir
    except Exception:
        pass

    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in sorted(src_dir.rglob("*")):
        if item.is_file():
            rel = item.relative_to(src_dir)
            target_p = dst_dir / rel
            _safe_move_file(item, target_p)

    manifest_leftover = src_dir / "Batch_Inventory_Manifest.csv"
    if manifest_leftover.exists():
        try:
            _clear_readonly_flag(manifest_leftover)
            manifest_leftover.unlink()
        except Exception:
            try:
                manifest_leftover.rename(src_dir / "_COMMITTED_Manifest.bak")
            except Exception:
                pass

    for attempt in range(4):
        try:
            def _on_rm_error(func, p, _exc):
                try:
                    os.chmod(p, stat.S_IWRITE)
                    func(p)
                except Exception:
                    pass

            shutil.rmtree(str(src_dir), onexc=_on_rm_error)
            if not src_dir.exists():
                break
        except Exception:
            gc.collect()
            time.sleep(0.25 * (attempt + 1))

    if src_dir.exists():
        try:
            with open(src_dir / "_COMMITTED.lock", "w", encoding="utf-8") as f:
                f.write(datetime.now().isoformat())
        except Exception:
            pass

    return dst_dir


# ==============================================================================
# 1. NATURAL ALPHANUMERIC CARD NUMBER SORTING
# ==============================================================================
def natural_card_sort_key(val) -> str:
    """Converts a card number like 'BCP-15' or '103' into a zero-padded natural sort string."""
    s = str(val or "").strip().lstrip("#").upper()
    if not s:
        return "9_ZZZZZZ"
    prefix = "0" if s[0].isdigit() else "1"
    padded = re.sub(r"(\d+)", lambda m: f"{int(m.group(1)):010d}", s)
    return f"{prefix}_{padded}"


def sort_cards_df(df: pd.DataFrame) -> pd.DataFrame:
    """Sorts a card DataFrame naturally by Set, Card Number, Subset, Copy_Number, and SKU."""
    if df is None or df.empty:
        return df
    out = df.copy()
    cnum_col = "Card Number" if "Card Number" in out.columns else ("Card_Number" if "Card_Number" in out.columns else None)
    sub_col = "Subset" if "Subset" in out.columns else ("Subset_Parallel" if "Subset_Parallel" in out.columns else None)

    out["_sort_set"] = out["Set"].astype(str) if "Set" in out.columns else ""
    out["_sort_cnum"] = out[cnum_col].map(natural_card_sort_key) if cnum_col else ""
    out["_sort_sub"] = out[sub_col].astype(str) if sub_col else ""
    out["_sort_copy"] = pd.to_numeric(out.get("Copy_Number", 1), errors="coerce").fillna(1).astype(int)
    out["_sort_sku"] = pd.to_numeric(out.get("SKU", 0), errors="coerce").fillna(0).astype(int)

    out = out.sort_values(
        by=["_sort_set", "_sort_cnum", "_sort_sub", "_sort_copy", "_sort_sku"],
        ascending=[True, True, True, True, True],
    ).drop(columns=["_sort_set", "_sort_cnum", "_sort_sub", "_sort_copy", "_sort_sku"]).reset_index(drop=True)
    return out


# ==============================================================================
# 2. MASTER CHECKLIST LOADER, BINARY CACHE & INSTANT CARD LOOKUP ENGINE
# ==============================================================================
_CACHED_CHECKLIST_TUPLE = None
_CACHED_CHECKLIST_MTIME = None


def load_master_checklist(
    checklist_path: Path = CHECKLIST_PATH,
    force_reload: bool = False,
) -> tuple[pd.DataFrame, dict, set, dict]:
    """
    Loads Master_Checklist.csv and builds:
      - root_df: Deduplicated base/insert root cards with precomputed norm_cnum, norm_player, norm_team
      - parallels_map: {(Set, norm_cnum, norm_player): [valid Subsets...]}
      - ordinary_roots: set of base/insert root subset names
      - print_run_map: {(Set, Subset, norm_cnum): print_run_str}
    """
    global _CACHED_CHECKLIST_TUPLE, _CACHED_CHECKLIST_MTIME
    ensure_directories()
    checklist_path = Path(checklist_path)

    if not checklist_path.exists():
        empty_root = pd.DataFrame(
            columns=["Set", "Subset", "Card Number", "Player", "Team", "Print Run", "Attributes", "norm_cnum", "norm_player", "norm_team"]
        )
        return empty_root, {}, {"Base"}, {}

    is_master_file = False
    try:
        is_master_file = checklist_path.resolve() == CHECKLIST_PATH.resolve()
    except Exception:
        is_master_file = (checklist_path.name == CHECKLIST_PATH.name)

    mtime = checklist_path.stat().st_mtime
    cache_sig = (str(checklist_path), mtime)
    if not force_reload and _CACHED_CHECKLIST_TUPLE is not None and _CACHED_CHECKLIST_MTIME == cache_sig:
        return _CACHED_CHECKLIST_TUPLE

    if is_master_file and not force_reload and CHECKLIST_CACHE_FILE.exists():
        try:
            with open(CHECKLIST_CACHE_FILE, "rb") as f:
                cached = pickle.load(f)
            if isinstance(cached, dict) and cached.get("mtime") == mtime and "data" in cached:
                _CACHED_CHECKLIST_TUPLE = cached["data"]
                _CACHED_CHECKLIST_MTIME = cache_sig
                return _CACHED_CHECKLIST_TUPLE
        except Exception:
            pass

    df = pd.read_csv(checklist_path, dtype=str, keep_default_na=False)
    for col in ("Set", "Subset", "Card Number", "Player", "Team", "Print Run", "Attributes"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].map(strip_accents).str.strip()

    df["Subset"] = df["Subset"].replace("", "Base")
    df["Print Run"] = df["Print Run"].map(format_print_run)
    df["norm_cnum"] = df["Card Number"].map(norm)
    df["norm_player"] = df["Player"].map(norm)
    df["norm_team"] = df["Team"].map(norm)

    def _extract_attr_tags_and_subplayers(p_str: str, attr_str: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        raw_parts = [p.strip() for p in str(p_str or "").split("/") if p.strip()]
        m_br = re.search(r"\[([^\]]+)\]", str(attr_str or ""))
        if m_br:
            for sub_p in m_br.group(1).split("/"):
                sp_clean = sub_p.strip()
                if sp_clean and sp_clean not in raw_parts:
                    raw_parts.append(sp_clean)

        tag_tokens = []
        clean_attr_no_br = re.sub(r"\[[^\]]*\]", "", str(attr_str or ""))
        for tok in clean_attr_no_br.split(","):
            t_c = tok.strip().upper()
            if t_c:
                tag_tokens.append(t_c)

        norm_parts = tuple(norm(p) for p in raw_parts if norm(p))
        lasts = []
        for p in raw_parts:
            toks = [t for t in re.split(r"\s+", strip_accents(p).strip()) if t]
            if not toks:
                continue
            if len(toks) >= 2 and toks[-1].upper().rstrip(".") in ("JR", "SR", "II", "III", "IV"):
                last_tok = norm(toks[-2])
                init_last = norm(toks[0][0] + toks[-2])
            else:
                last_tok = norm(toks[-1])
                init_last = norm(toks[0][0] + toks[-1]) if len(toks) >= 2 else last_tok
            if last_tok:
                lasts.append(last_tok)
            if init_last and init_last != last_tok:
                lasts.append(init_last)
        return tuple(tag_tokens), norm_parts, tuple(lasts)

    parsed_meta = [
        _extract_attr_tags_and_subplayers(p_v, a_v)
        for p_v, a_v in zip(df["Player"], df["Attributes"])
    ]
    df["attr_tags"] = [m[0] for m in parsed_meta]
    df["norm_player_parts"] = [m[1] for m in parsed_meta]
    df["norm_player_lasts"] = [m[2] for m in parsed_meta]
    df["is_multi_player"] = [
        ("/" in str(p_v)) or ("[" in str(a_v))
        for p_v, a_v in zip(df["Player"], df["Attributes"])
    ]

    parallels_map: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    card_num_subsets: dict[tuple[str, str], list[str]] = defaultdict(list)
    print_run_map: dict[tuple[str, str, str], str] = {}

    for s_val, sub_val, cn_val, n_cn, plr_val, n_plr, pr_val in zip(
        df["Set"],
        df["Subset"],
        df["Card Number"],
        df["norm_cnum"],
        df["Player"],
        df["norm_player"],
        df["Print Run"],
    ):
        k_norm = (s_val, n_cn, n_plr)
        if sub_val not in parallels_map[k_norm]:
            parallels_map[k_norm].append(sub_val)

        k_raw = (s_val, cn_val, plr_val)
        if k_raw != k_norm and sub_val not in parallels_map[k_raw]:
            parallels_map[k_raw].append(sub_val)

        if sub_val not in card_num_subsets[(s_val, n_cn)]:
            card_num_subsets[(s_val, n_cn)].append(sub_val)

        if pr_val:
            print_run_map[(s_val, sub_val, n_cn)] = pr_val
            print_run_map[(s_val, sub_val, cn_val)] = pr_val

    ordinary_roots = {"Base"}
    for (_, _), subs in card_num_subsets.items():
        if subs:
            shortest = min(subs, key=len)
            ordinary_roots.add(shortest)

    df["_sub_len"] = df["Subset"].str.len()
    df["_is_base"] = df["Subset"].str.upper().apply(lambda x: 0 if x == "BASE" or x.startswith("BASE ") else 1)
    root_df = (
        df.sort_values(by=["_is_base", "_sub_len"])
        .drop_duplicates(subset=["Set", "norm_cnum", "norm_player"], keep="first")
        .drop(columns=["_sub_len", "_is_base"])
        .reset_index(drop=True)
    )

    result_tuple = (root_df, dict(parallels_map), ordinary_roots, print_run_map)
    _CACHED_CHECKLIST_TUPLE = result_tuple
    _CACHED_CHECKLIST_MTIME = cache_sig

    if is_master_file:
        try:
            def _dump_chk_cache(tmp_p: Path):
                with open(tmp_p, "wb") as f:
                    pickle.dump({"mtime": mtime, "data": result_tuple}, f, protocol=pickle.HIGHEST_PROTOCOL)
            atomic_write_bytes(CHECKLIST_CACHE_FILE, _dump_chk_cache)
        except Exception:
            pass

    return result_tuple


def lookup_card_details(
    master_df: pd.DataFrame,
    set_name: str,
    card_number: str,
    subset_name: Optional[str] = None,
    player_hint: Optional[str] = None,
) -> dict:
    """Looks up a card in Master_Checklist.csv by (Set, Card Number, optional Subset, optional Player hint)."""
    clean_cnum = str(card_number or "").strip().lstrip("#")
    default_out = {
        "card_number": clean_cnum,
        "player": player_hint.strip() if player_hint and player_hint.strip() else "Unknown Player",
        "team": "",
        "print_run": "",
        "attributes": "",
        "available_subsets": ["Base"],
    }
    if master_df is None or master_df.empty or not set_name or not clean_cnum:
        return default_out

    set_slice = master_df[master_df["Set"] == set_name]
    if set_slice.empty:
        return default_out

    exact_cnum = set_slice[set_slice["Card Number"].str.lower() == clean_cnum.lower()]
    if exact_cnum.empty:
        n_cnum = norm(clean_cnum)
        exact_cnum = set_slice[set_slice["Card Number"].map(norm) == n_cnum]

    if exact_cnum.empty:
        return default_out

    if player_hint and player_hint.strip() and player_hint.strip() != "Unknown Player":
        n_plr = norm(player_hint)
        plr_filtered = exact_cnum[
            exact_cnum["Player"].map(norm).apply(lambda p: n_plr in p or p in n_plr)
        ]
        if not plr_filtered.empty:
            exact_cnum = plr_filtered

    avail_subsets = list(dict.fromkeys(exact_cnum["Subset"].dropna().tolist()))
    if not avail_subsets:
        avail_subsets = ["Base"]

    chosen_row = exact_cnum.iloc[0]
    if subset_name:
        sub_clean = subset_name.strip().lower()
        sub_matches = exact_cnum[exact_cnum["Subset"].str.lower() == sub_clean]
        if sub_matches.empty:
            target_canon = canonical_subset_key(subset_name, set_name)
            sub_matches = exact_cnum[
                exact_cnum["Subset"].apply(lambda s: canonical_subset_key(s, set_name) == target_canon)
            ]
        if not sub_matches.empty:
            chosen_row = sub_matches.iloc[0]

    raw_plr = str(chosen_row.get("Player", "Unknown Player")).strip() or "Unknown Player"
    raw_tm = str(chosen_row.get("Team", "")).strip()
    if (
        raw_plr.upper() in ("CHECKLIST", "CHECKLIST TEAM CARD", "TEAM CHECKLIST", "TEAM CARD")
        or raw_plr.upper().startswith("CHECKLIST TEAM CARD")
    ) and raw_tm and raw_tm.upper() not in ("NO TEAM", "UNKNOWN"):
        raw_plr = raw_tm.split("/")[0].strip()

    return {
        "card_number": str(chosen_row.get("Card Number", clean_cnum)).strip().lstrip("#"),
        "player": raw_plr,
        "team": raw_tm,
        "print_run": format_print_run(chosen_row.get("Print Run", "")),
        "attributes": str(chosen_row.get("Attributes", "")).strip(),
        "available_subsets": avail_subsets,
    }


# ==============================================================================
# 3. 1-ROW-PER-CARD INVENTORY.CSV & 7-DIGIT SKU ALLOCATOR
# ==============================================================================
def load_inventory_df() -> pd.DataFrame:
    """Loads Inventory/Inventory.csv ensuring all INVENTORY_COLUMNS exist and SKUs are assigned."""
    ensure_directories()
    if not INVENTORY_FILE.exists():
        empty_df = pd.DataFrame(columns=INVENTORY_COLUMNS)
        inv_lock = INVENTORY_FILE.with_suffix(".csv.lock")
        with interprocess_file_lock(inv_lock):
            if not INVENTORY_FILE.exists():
                atomic_write_bytes(
                    INVENTORY_FILE,
                    lambda tmp_p: empty_df.to_csv(tmp_p, index=False, encoding="utf-8-sig"),
                )
        return empty_df

    try:
        df = pd.read_csv(INVENTORY_FILE, dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame(columns=INVENTORY_COLUMNS)

    if "Subset_Parallel" in df.columns and "Subset" not in df.columns:
        df.rename(columns={"Subset_Parallel": "Subset"}, inplace=True)
    if "Card_Number" in df.columns and "Card Number" not in df.columns:
        df.rename(columns={"Card_Number": "Card Number"}, inplace=True)
    if "Print_Run" in df.columns and "Print Run" not in df.columns:
        df.rename(columns={"Print_Run": "Print Run"}, inplace=True)

    for col in INVENTORY_COLUMNS:
        if col not in df.columns:
            if col == "Status":
                df[col] = "In Stock"
            elif col == "Hold_Tag":
                df[col] = "For Sale"
            elif col == "Copy_Number":
                df[col] = "1"
            elif col in ("Needs_Review", "Label_Printed"):
                df[col] = "False"
            elif col == "Valuation_Source":
                df[col] = ""
            elif col in ("Rec_Sale_Price", "Min_Sale_Price"):
                df[col] = df.get("Raw_Price", "")
            else:
                df[col] = ""

    df["Hold_Tag"] = df["Hold_Tag"].replace("", "For Sale")
    df["Min_Sale_Price"] = [
        msp if str(msp).strip() else str(raw or "").strip()
        for msp, raw in zip(df["Min_Sale_Price"], df["Raw_Price"])
    ]
    df["Rec_Sale_Price"] = [
        rsp if str(rsp).strip() else str(raw or "").strip()
        for rsp, raw in zip(df["Rec_Sale_Price"], df["Raw_Price"])
    ]
    df["Valuation_Source"] = [
        vs if str(vs).strip() else ("Uncomped" if not str(raw or "").strip() else "")
        for vs, raw in zip(df["Valuation_Source"], df["Raw_Price"])
    ]
    df["Card Number"] = df["Card Number"].astype(str).str.strip().str.lstrip("#")
    df["Print Run"] = df["Print Run"].map(format_print_run)
    df = assign_missing_skus(df)
    return df[INVENTORY_COLUMNS]


def save_inventory_df(df: pd.DataFrame) -> pd.DataFrame:
    """Saves Inventory/Inventory.csv safely with all standard columns."""
    ensure_directories()
    out = df.copy()
    for col in INVENTORY_COLUMNS:
        if col not in out.columns:
            if col == "Hold_Tag":
                out[col] = "For Sale"
            elif col == "Rec_Sale_Price":
                out[col] = out.get("Raw_Price", "")
            else:
                out[col] = ""
    out["Hold_Tag"] = out["Hold_Tag"].replace("", "For Sale")
    out["Card Number"] = out["Card Number"].astype(str).str.strip().str.lstrip("#")
    out["Print Run"] = out["Print Run"].map(format_print_run)
    out = out[INVENTORY_COLUMNS]
    inv_lock = INVENTORY_FILE.with_suffix(".csv.lock")
    with interprocess_file_lock(inv_lock):
        atomic_write_bytes(
            INVENTORY_FILE,
            lambda tmp_p: out.to_csv(tmp_p, index=False, encoding="utf-8-sig"),
        )
    return out


def update_inventory_df_atomic(
    mutator_fn: Callable[[pd.DataFrame], pd.DataFrame],
    timeout: float = 30.0,
) -> pd.DataFrame:
    """
    Executes a read-modify-write on Inventory.csv under an interprocess file lock so concurrent
    HTTP requests and background workers never overwrite each other's commits or edits.
    """
    ensure_directories()
    inv_lock = INVENTORY_FILE.with_suffix(".csv.lock")
    with interprocess_file_lock(inv_lock, timeout=timeout):
        current_df = load_inventory_df()
        updated_df = mutator_fn(current_df.copy())
        return save_inventory_df(current_df if updated_df is None else updated_df)


def merge_inventory_updates_by_sku(
    updated_rows_df: pd.DataFrame,
    baseline_df: Optional[pd.DataFrame] = None,
    columns_to_merge: Optional[list[str]] = None,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """
    Re-reads Inventory.csv under lock and merges only mutated cells/columns keyed by SKU.
    When `baseline_df` is provided, only cells whose values changed relative to `baseline_df`
    are applied onto the fresh DataFrame, preserving concurrent edits and newly committed SKUs.
    """
    if updated_rows_df is None or updated_rows_df.empty or "SKU" not in updated_rows_df.columns:
        return load_inventory_df()

    upd = updated_rows_df.copy()
    upd["SKU"] = upd["SKU"].astype(str).str.strip()
    upd = upd[upd["SKU"] != ""]
    if upd.empty:
        return load_inventory_df()

    base_lookup: dict[str, dict] = {}
    if baseline_df is not None and not baseline_df.empty and "SKU" in baseline_df.columns:
        for _, b_row in baseline_df.iterrows():
            b_sku = str(b_row.get("SKU") or "").strip()
            if b_sku:
                base_lookup[b_sku] = b_row.to_dict()

    allowed_cols = (
        [c for c in columns_to_merge if c != "SKU" and c in upd.columns]
        if columns_to_merge is not None
        else [c for c in upd.columns if c != "SKU"]
    )

    def _apply_merge(fresh_df: pd.DataFrame) -> pd.DataFrame:
        if fresh_df.empty or "SKU" not in fresh_df.columns or not allowed_cols:
            return fresh_df
        fresh_df = fresh_df.copy()
        fresh_df["SKU"] = fresh_df["SKU"].astype(str).str.strip()
        sku_to_idx: dict[str, int] = {}
        for f_idx, f_sku in zip(fresh_df.index, fresh_df["SKU"]):
            if f_sku:
                sku_to_idx[f_sku] = f_idx

        for _, u_row in upd.iterrows():
            u_sku = str(u_row.get("SKU") or "").strip()
            target_idx = sku_to_idx.get(u_sku)
            if target_idx is None:
                continue
            b_rec = base_lookup.get(u_sku)
            for col in allowed_cols:
                new_val = u_row.get(col)
                if b_rec is not None:
                    old_val = b_rec.get(col, "")
                    if str(new_val) == str(old_val):
                        continue
                if col not in fresh_df.columns:
                    fresh_df[col] = ""
                fresh_df.at[target_idx, col] = new_val
        return fresh_df

    return update_inventory_df_atomic(_apply_merge, timeout=timeout)


def get_next_sku_int() -> int:
    """Finds the highest existing 7-digit SKU across Inventory, Batches, and _Cards and returns max + 1."""
    ensure_directories()
    max_sku = SKU_START - 1

    csv_candidates = [INVENTORY_FILE, ACTIVE_BATCH_FILE]
    if BATCHES_DIR.exists():
        csv_candidates.extend(BATCHES_DIR.rglob("Batch_Inventory_Manifest.csv"))

    for csv_p in csv_candidates:
        if csv_p.exists():
            try:
                s_df = pd.read_csv(csv_p, usecols=lambda c: c == "SKU", dtype=str, keep_default_na=False)
                if "SKU" in s_df.columns:
                    nums = pd.to_numeric(s_df["SKU"], errors="coerce").dropna()
                    if not nums.empty:
                        max_sku = max(max_sku, int(nums.max()))
            except Exception:
                pass

    if REVIEWED_CARDS_DIR.exists():
        sku_re = re.compile(r"_\[(\d{7})\]_[FBC]\.jpg$", re.IGNORECASE)
        for p in REVIEWED_CARDS_DIR.rglob("*.jpg"):
            m = sku_re.search(p.name)
            if m:
                max_sku = max(max_sku, int(m.group(1)))

    return max(SKU_START, max_sku + 1)


def assign_missing_skus(df: pd.DataFrame) -> pd.DataFrame:
    """Assigns sequential 7-digit SKUs to any rows in df missing a valid SKU."""
    if df is None or df.empty:
        return df
    if "SKU" in df.columns:
        sku_series = df["SKU"].astype(str).str.strip()
        if sku_series.str.fullmatch(r"\d{7,}").all() and not sku_series.duplicated().any():
            return df

    out = df.copy()
    if "SKU" not in out.columns:
        out["SKU"] = ""

    existing_valid: set[str] = set()
    needs_sku_indices = []
    max_in_df = SKU_START - 1
    for idx, v in out["SKU"].items():
        s = str(v).strip()
        if s.isdigit() and int(s) >= SKU_START:
            val_i = int(s)
            max_in_df = max(max_in_df, val_i)
            if s in existing_valid:
                needs_sku_indices.append(idx)
            else:
                existing_valid.add(s)
                out.at[idx, "SKU"] = s
        else:
            needs_sku_indices.append(idx)

    if not needs_sku_indices:
        return out

    next_val = max(get_next_sku_int(), max_in_df + 1)
    for idx in needs_sku_indices:
        while f"{next_val:07d}" in existing_valid:
            next_val += 1
        sku_str = f"{next_val:07d}"
        out.at[idx, "SKU"] = sku_str
        existing_valid.add(sku_str)
        next_val += 1

    return out


def _index_reviewed_cards_by_sku() -> dict[tuple[str, str], Path]:
    """Builds a fast lookup {(sku_str, side_tag): Path} across all files in _Cards."""
    index_map: dict[tuple[str, str], Path] = {}
    if not REVIEWED_CARDS_DIR.exists():
        return index_map
    pat = re.compile(r"_\[(\d{7})\]_([FBC])\.jpg$", re.IGNORECASE)
    for p in REVIEWED_CARDS_DIR.rglob("*.jpg"):
        m = pat.search(p.name)
        if m:
            index_map[(m.group(1), m.group(2).upper())] = p
    return index_map


def _locate_card_image_in_repository(
    old_filename: str,
    sku_str: str,
    side_tag: str,
    candidate_sets: list[str],
    sku_file_index: dict[tuple[str, str], Path],
) -> Optional[Path]:
    """Finds a physical card image in _Cards by exact set folder path or by 7-digit SKU."""
    if old_filename:
        for s_name in candidate_sets:
            if not s_name:
                continue
            cand_p = REVIEWED_CARDS_DIR / sanitize_filename_part(s_name) / old_filename
            if cand_p.exists():
                return cand_p
    if (sku_str, side_tag.upper()) in sku_file_index:
        p = sku_file_index[(sku_str, side_tag.upper())]
        if p.exists():
            return p
    return None


def resolve_template_reference_paths(
    set_name: str,
    subset_name: str,
    card_number: str,
) -> dict:
    """
    Looks up the matching Front (`_F.jpg`) and Back (`_B.jpg`) template reference images
    in `D:\\Tabulas Set Library` (`REFERENCE_TEMPLATES_DIR`) for `(set_name, subset_name, card_number)`.
    """
    empty_res = {
        "front_rel": "",
        "back_rel": "",
        "front_abs": "",
        "back_abs": "",
        "match_kind": "none",
        "cid_tag": "",
    }
    if not set_name or not REFERENCE_TEMPLATES_DIR.exists():
        return empty_res

    s_dir = REFERENCE_TEMPLATES_DIR / sanitize_filename_part(set_name)
    if not s_dir.exists() or not s_dir.is_dir():
        target_s_key = canonical_set_key(set_name)
        s_dir = next(
            (
                d for d in REFERENCE_TEMPLATES_DIR.iterdir()
                if d.is_dir()
                and d.name.lower() not in ("logs", "reports", ".verified_backups")
                and canonical_set_key(d.name.replace("_", " ")) == target_s_key
            ),
            None,
        )
    if s_dir is None or not s_dir.exists():
        return empty_res

    target_sub_canon = canonical_subset_key(subset_name or "Base", set_name)
    target_cnum_norm = norm(str(card_number or "").lstrip("#"))

    exact_f: Optional[Path] = None
    exact_b: Optional[Path] = None
    exact_cid = ""

    exemplar_f: Optional[Path] = None
    exemplar_b: Optional[Path] = None
    exemplar_cid = ""

    for img_p in sorted(s_dir.glob("*.jpg")):
        parsed = parse_unified_card_filename(img_p.name)
        if not parsed:
            continue
        sub_c = canonical_subset_key(parsed["subset"], set_name)
        if sub_c != target_sub_canon:
            continue
        cn_n = norm(parsed["card_number"])
        side_c = parsed["side"]
        id_tag = parsed["id_tag"]

        if target_cnum_norm and cn_n == target_cnum_norm:
            if side_c == "F" and exact_f is None:
                exact_f = img_p
                exact_cid = id_tag
            elif side_c == "B" and exact_b is None:
                exact_b = img_p
                if not exact_cid:
                    exact_cid = id_tag
        else:
            if side_c == "F" and exemplar_f is None:
                exemplar_f = img_p
                exemplar_cid = id_tag
            elif side_c == "B" and exemplar_b is None:
                exemplar_b = img_p
                if not exemplar_cid:
                    exemplar_cid = id_tag

        if exact_f is not None and exact_b is not None:
            break

    chosen_f = exact_f or exemplar_f
    chosen_b = exact_b or (exemplar_b if exact_f is None else None)
    match_kind = "exact_card" if (exact_f is not None or exact_b is not None) else (
        "subset_exemplar" if (exemplar_f is not None or exemplar_b is not None) else "none"
    )
    chosen_cid = exact_cid or exemplar_cid

    front_rel = chosen_f.relative_to(REFERENCE_TEMPLATES_DIR).as_posix() if chosen_f else ""
    back_rel = chosen_b.relative_to(REFERENCE_TEMPLATES_DIR).as_posix() if chosen_b else ""

    return {
        "front_rel": front_rel,
        "back_rel": back_rel,
        "front_abs": str(chosen_f) if chosen_f else "",
        "back_abs": str(chosen_b) if chosen_b else "",
        "match_kind": match_kind,
        "cid_tag": chosen_cid,
    }


def sync_inventory_copy_numbers_and_files(
    inv_df: pd.DataFrame,
    previous_inv_df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, int]:
    """
    Recalculates sequential Copy_Number (1, 2, 3...) for every card in inv_df and
    automatically renames/moves linked _F.jpg, _B.jpg, and _C.jpg files inside _Cards/<Set>/.
    """
    if inv_df is None or inv_df.empty:
        return inv_df, 0

    ensure_directories()
    out = assign_missing_skus(inv_df.copy())

    prev_by_sku = {}
    if previous_inv_df is not None and not previous_inv_df.empty and "SKU" in previous_inv_df.columns:
        prev_by_sku = {str(r["SKU"]).strip(): r.to_dict() for _, r in previous_inv_df.iterrows()}

    sku_file_index = _index_reviewed_cards_by_sku()
    copy_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    renamed_sets_count = 0
    copy_changed_count = 0

    log_action_detail(
        f"Syncing Copy_Number & verifying _Cards filenames across {len(out)} inventory SKU(s)...",
        monitor_title="Syncing Inventory Copy #s & Filenames",
        current=0,
        total=len(out),
        status="RUNNING",
    )

    for idx, row in out.iterrows():
        sku_str = str(row.get("SKU", "")).strip()
        set_name = str(row.get("Set", "")).strip() or "Unknown_Set"
        sub_name = str(row.get("Subset", "Base")).strip() or "Base"
        cnum_str = str(row.get("Card Number", "0")).strip().lstrip("#") or "0"
        player_name = str(row.get("Player", "Unknown Player")).strip() or "Unknown Player"
        old_copy_str = str(row.get("Copy_Number", "1")).strip()

        out.at[idx, "Set"] = set_name
        out.at[idx, "Subset"] = sub_name
        out.at[idx, "Card Number"] = cnum_str
        out.at[idx, "Player"] = player_name
        out.at[idx, "Print Run"] = format_print_run(row.get("Print Run", ""))

        design_key = (
            norm(set_name),
            canonical_subset_key(sub_name, set_name),
            norm(cnum_str),
            norm(player_name),
        )
        copy_counts[design_key] += 1
        new_copy_str = str(copy_counts[design_key])
        out.at[idx, "Copy_Number"] = new_copy_str
        if old_copy_str != new_copy_str:
            copy_changed_count += 1

        prev_row = prev_by_sku.get(sku_str, {})
        old_set = str(prev_row.get("Set", set_name)).strip()
        old_sub = str(prev_row.get("Subset", sub_name)).strip() or "Base"
        old_cnum = str(prev_row.get("Card Number", cnum_str)).strip().lstrip("#") or "0"
        old_f = str(prev_row.get("Front_File") or row.get("Front_File") or "").strip()
        old_b = str(prev_row.get("Back_File") or row.get("Back_File") or "").strip()
        old_c = str(prev_row.get("Corners_File") or row.get("Corners_File") or "").strip()

        # Re-resolve Set Library reference template paths whenever card identity changes
        if prev_row and (old_set != set_name or old_sub != sub_name or old_cnum != cnum_str):
            tmpl_ref = resolve_template_reference_paths(set_name, sub_name, cnum_str)
            out.at[idx, "Matched_Template_Front"] = tmpl_ref.get("front_rel", "")
            out.at[idx, "Matched_Template_Back"] = tmpl_ref.get("back_rel", "")

        has_linked_files = bool(old_f or old_b or old_c or (sku_str, "F") in sku_file_index)
        if not has_linked_files:
            continue

        new_f, new_b, new_c = build_card_image_filenames(
            set_name, sub_name, cnum_str, player_name, sku_str
        )
        target_set_dir = REVIEWED_CARDS_DIR / sanitize_filename_part(set_name)

        card_renamed = False
        for old_fname, new_fname, side_tag in (
            (old_f, new_f, "F"),
            (old_b, new_b, "B"),
            (old_c, new_c, "C"),
        ):
            src_path = _locate_card_image_in_repository(
                old_fname,
                sku_str,
                side_tag,
                [old_set, set_name],
                sku_file_index,
            )
            if src_path is not None and src_path.exists():
                target_set_dir.mkdir(parents=True, exist_ok=True)
                dst_path = target_set_dir / new_fname
                if src_path.resolve() != dst_path.resolve():
                    if _safe_move_file(src_path, dst_path):
                        sku_file_index[(sku_str, side_tag)] = dst_path
                        card_renamed = True

        if card_renamed or (old_f, old_b, old_c) != (new_f, new_b, new_c):
            renamed_sets_count += 1

        if old_f or (sku_str, "F") in sku_file_index:
            out.at[idx, "Front_File"] = new_f
        if old_b or (sku_str, "B") in sku_file_index:
            out.at[idx, "Back_File"] = new_b
        if old_c or (sku_str, "C") in sku_file_index:
            out.at[idx, "Corners_File"] = new_c

    log_action_detail(
        f"Inventory sync complete: {len(out)} SKU(s) verified, {copy_changed_count} copy #s adjusted, {renamed_sets_count} image set(s) renamed.",
        monitor_title=f"Inventory Sync Complete ({renamed_sets_count} Renamed)",
        current=len(out),
        total=len(out),
        status="COMPLETED",
    )
    return out, renamed_sets_count


def delete_inventory_skus(
    skus_to_delete: list[str],
    delete_card_images: bool = False,
) -> dict:
    """Removes one or more SKUs from Inventory.csv and optionally deletes their images from _Cards."""
    inv_df = load_inventory_df()
    if inv_df.empty or not skus_to_delete:
        return {"deleted_rows": 0, "deleted_images": 0}

    del_set = {str(s).strip() for s in skus_to_delete if str(s).strip()}
    to_remove_df = inv_df[inv_df["SKU"].isin(del_set)]
    remaining_df = inv_df[~inv_df["SKU"].isin(del_set)].reset_index(drop=True)

    deleted_imgs = 0
    for _, r in to_remove_df.iterrows():
        if delete_card_images:
            s_dir = REVIEWED_CARDS_DIR / sanitize_filename_part(str(r.get("Set", "")))
            for col in ("Front_File", "Back_File", "Corners_File"):
                fn = str(r.get(col, "")).strip()
                if fn and (s_dir / fn).exists():
                    try:
                        _clear_readonly_flag(s_dir / fn)
                        (s_dir / fn).unlink()
                        deleted_imgs += 1
                    except Exception:
                        pass

    remaining_df, _ = sync_inventory_copy_numbers_and_files(remaining_df, previous_inv_df=inv_df)
    save_inventory_df(remaining_df)
    return {"deleted_rows": len(to_remove_df), "deleted_images": deleted_imgs}


# ==============================================================================
# 4. EXISTING COPY COUNTER & BATCH DISCOVERY
# ==============================================================================
def get_existing_copy_count(set_name: str, subset_name: str, card_number: str, player_name: str) -> int:
    """Counts how many physical copies of (Set, Subset, Card Number, Player) already exist in Inventory or _Cards."""
    ensure_directories()
    cnum_clean = str(card_number or "").strip().lstrip("#")
    target_set_norm = norm(set_name)
    target_sub_canon = canonical_subset_key(subset_name, set_name)
    target_cnum_norm = norm(cnum_clean)
    target_plr_norm = norm(player_name)

    inv_count = 0
    if INVENTORY_FILE.exists():
        try:
            inv_df = pd.read_csv(INVENTORY_FILE, dtype=str, keep_default_na=False)
            if not inv_df.empty and "Set" in inv_df.columns:
                c_col = "Card Number" if "Card Number" in inv_df.columns else "Card_Number"
                s_col = "Subset" if "Subset" in inv_df.columns else "Subset_Parallel"
                for s_v, sub_v, cn_v, p_v in zip(
                    inv_df["Set"],
                    inv_df.get(s_col, pd.Series(dtype=str)),
                    inv_df.get(c_col, pd.Series(dtype=str)),
                    inv_df.get("Player", pd.Series(dtype=str)),
                ):
                    if (
                        norm(s_v) == target_set_norm
                        and canonical_subset_key(sub_v, s_v) == target_sub_canon
                        and norm(str(cn_v).lstrip("#")) == target_cnum_norm
                        and norm(p_v) == target_plr_norm
                    ):
                        inv_count += 1
        except Exception:
            pass

    cards_dir_count = 0
    set_folder = REVIEWED_CARDS_DIR / sanitize_filename_part(set_name)
    if set_folder.exists():
        stem_prefix = build_card_image_stem(set_name, subset_name, cnum_clean, player_name)
        for p in set_folder.glob("*_F*.jpg"):
            if p.name.startswith(stem_prefix):
                cards_dir_count += 1

    return max(inv_count, cards_dir_count)


def find_unarchived_scan_batches() -> list[tuple[str, Path, list[Path]]]:
    """
    Discovers all unarchived scanner PDF folders inside Incoming_Scans (or legacy Raw_Scans),
    returning [(batch_name, folder_path, [pdf_paths...]), ...].
    """
    ensure_directories()
    discovered = []
    seen_dirs = set()

    for root_scan_dir in (INPUT_PATH, FALLBACK_SCAN_PATH):
        if not root_scan_dir.exists():
            continue

        root_pdfs = sorted(root_scan_dir.glob("*.pdf"))
        if root_pdfs and root_scan_dir.resolve() not in seen_dirs:
            seen_dirs.add(root_scan_dir.resolve())
            b_name = f"Scans_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            discovered.append((b_name, root_scan_dir, root_pdfs))

        for sub in sorted(root_scan_dir.iterdir()):
            if not sub.is_dir() or sub.name.lower() == "archive":
                continue
            if sub.resolve() in seen_dirs:
                continue
            pdfs = sorted(sub.glob("*.pdf"))
            if pdfs:
                seen_dirs.add(sub.resolve())
                discovered.append((sub.name, sub, pdfs))

    return discovered


def list_uncommitted_batch_folders() -> list[Path]:
    """Returns all uncommitted processed batch folders containing Batch_Inventory_Manifest.csv."""
    ensure_directories()
    candidates = []
    for search_dir in (BATCHES_DIR, BASE_DIR / "Processed_Cards"):
        if not search_dir.exists():
            continue
        for d in search_dir.iterdir():
            if not d.is_dir() or d.name.lower() == "archive":
                continue
            if (d / "_COMMITTED.lock").exists() or not (d / "Batch_Inventory_Manifest.csv").exists():
                if (d / "_COMMITTED.lock").exists():
                    shutil.rmtree(str(d), ignore_errors=True)
                continue
            candidates.append(d)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates


def clear_uncommitted_batch(
    batch_dir: Optional[Path] = None,
    clear_all: bool = False,
    restore_raw_scans_from_archive: bool = True,
) -> dict:
    """
    Clears one or all uncommitted batch folders in `Inventory/Batches` and optionally
    restores any archived raw PDFs from `Archive/Raw_Scans/<batch_name>` back into `Incoming_Scans`.
    """
    ensure_directories()
    targets = list_uncommitted_batch_folders() if clear_all else ([Path(batch_dir)] if batch_dir else [])
    cleared_batches = []
    restored_pdfs = 0

    for t_dir in targets:
        if not t_dir or not t_dir.exists():
            continue
        b_name = t_dir.name
        if restore_raw_scans_from_archive:
            arc_raw = ARCHIVE_SCAN_PATH / b_name
            if arc_raw.exists() and arc_raw.is_dir():
                dst_inc = INPUT_PATH / b_name
                dst_inc.mkdir(parents=True, exist_ok=True)
                for pdf_f in sorted(arc_raw.glob("*.pdf")):
                    if _safe_move_file(pdf_f, dst_inc / pdf_f.name):
                        restored_pdfs += 1

        try:
            def _on_rm_err(func, p, _exc):
                try:
                    os.chmod(p, stat.S_IWRITE)
                    func(p)
                except Exception:
                    pass

            shutil.rmtree(str(t_dir), onexc=_on_rm_err)
        except Exception:
            pass

        if t_dir.exists():
            man_p = t_dir / "Batch_Inventory_Manifest.csv"
            if man_p.exists():
                try:
                    _clear_readonly_flag(man_p)
                    man_p.unlink()
                except Exception:
                    pass
        cleared_batches.append(b_name)

    return {
        "cleared_count": len(cleared_batches),
        "cleared_batches": cleared_batches,
        "restored_pdfs": restored_pdfs,
    }


def resolve_manual_override_subset(user_input: str, valid_subsets: list, set_name: str = "") -> tuple[str, str]:
    """Matches a user's manual subset/parallel override against valid_subsets for that card."""
    raw = strip_accents(str(user_input or "")).strip()
    if not raw:
        return (valid_subsets[0] if valid_subsets else "Base"), "Default"
    if not valid_subsets:
        return raw, "Custom (No Checklist Subsets)"

    for vs in valid_subsets:
        if vs.lower() == raw.lower():
            return vs, "Exact Match"

    raw_canon = canonical_subset_key(raw, set_name)
    for vs in valid_subsets:
        if canonical_subset_key(vs, set_name) == raw_canon:
            return vs, f"Canonical Match -> {vs}"

    best_vs = raw
    best_score = 0.0
    raw_tokens = set(re.findall(r"[a-z0-9]+", raw.lower()))

    for vs in valid_subsets:
        vs_low = vs.lower()
        vs_tokens = set(re.findall(r"[a-z0-9]+", vs_low))
        seq_ratio = SequenceMatcher(None, raw.lower(), vs_low).ratio()
        tok_overlap = (len(raw_tokens & vs_tokens) / max(1, len(raw_tokens))) if raw_tokens else 0.0
        combined_score = 0.55 * seq_ratio + 0.45 * tok_overlap
        if raw.lower() in vs_low or vs_low in raw.lower():
            combined_score += 0.15
        if combined_score > best_score:
            best_score = combined_score
            best_vs = vs

    if best_score >= 0.62:
        return best_vs, f"Fuzzy Match ({best_score:.2f})"
    return raw, "Custom Override"


def apply_manifest_overrides_and_rename(
    batch_dir: Path,
    df_override: pd.DataFrame = None,
    target_skus: Optional[set[str]] = None,
    master_df_override: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, int, int]:
    """
    Validates and applies overrides on a batch manifest, auto-updates Team, Print_Run,
    Attributes, and Matched_Template_Front/Back, and renames _F, _B, _C files.
    When `target_skus` is supplied (e.g. single-card save in Guided Batch Review),
    skips heavy checklist/template lookups on untouched rows for instant saves.
    """
    batch_dir = Path(batch_dir)
    manifest_path = batch_dir / "Batch_Inventory_Manifest.csv"
    df = df_override.copy() if df_override is not None else pd.read_csv(manifest_path, dtype=str, keep_default_na=False)

    log_action_detail(
        f"Validating overrides & filenames in batch '{batch_dir.name}' ({len(target_skus) if target_skus else len(df)} target card(s))...",
        monitor_title=f"Validating & Renaming Batch '{batch_dir.name}'",
        current=0,
        total=max(1, len(target_skus) if target_skus else len(df)),
        status="RUNNING",
    )

    if master_df_override is not None:
        master_df = master_df_override
    else:
        master_df = pd.read_csv(CHECKLIST_PATH, dtype=str, keep_default_na=False) if CHECKLIST_PATH.exists() else pd.DataFrame()
    set_slices_cache: dict[str, pd.DataFrame] = {}
    if not master_df.empty and "Set" in master_df.columns:
        for s_k, grp in master_df.groupby("Set", sort=False):
            set_slices_cache[str(s_k).strip()] = grp

    override_cols = [c for c in df.columns if "override" in c.lower()]
    if not override_cols:
        df["Manual_Override"] = ""
        override_cols = ["Manual_Override"]

    df = assign_missing_skus(df)

    copy_tracker = defaultdict(int)
    seeded_inventory_stems: set[str] = set()
    renamed_count = 0
    override_applied_count = 0
    temp_moves = []

    for row_idx, row in df.iterrows():
        sku_str = str(row.get("SKU", "")).strip()
        set_name = str(row.get("Set", "")).strip()
        cnum_raw = str(row.get("Card_Number", row.get("Card Number", ""))).strip().lstrip("#")
        player_name = str(row.get("Player", "")).strip()
        current_sub = str(row.get("Subset_Parallel", row.get("Subset", "Base"))).strip() or "Base"
        old_f = str(row.get("Front_File", "")).strip()
        old_b = str(row.get("Back_File", "")).strip()
        old_c = str(row.get("Corners_File", "")).strip()

        manual_val = ""
        for oc in override_cols:
            val = str(row.get(oc, "")).strip()
            if val:
                manual_val = val
                break

        # Fast-skip untouched rows during single-card Guided Review saves
        if target_skus is not None and sku_str not in target_skus and not manual_val:
            card_stem_skip = build_card_image_stem(set_name, current_sub, cnum_raw, player_name)
            copy_tracker[card_stem_skip] += 1
            continue

        set_chk_slice = set_slices_cache.get(set_name, pd.DataFrame())
        details = lookup_card_details(set_chk_slice, set_name, cnum_raw, current_sub, player_hint=player_name)
        valid_subsets = details["available_subsets"]

        if manual_val:
            final_sub, _ = resolve_manual_override_subset(manual_val, valid_subsets, set_name)
            override_applied_count += 1
        else:
            final_sub, _ = resolve_manual_override_subset(current_sub, valid_subsets, set_name)

        if final_sub == current_sub:
            final_details = details
        else:
            final_details = lookup_card_details(set_chk_slice, set_name, cnum_raw, final_sub, player_hint=player_name)
        cnum_final = final_details["card_number"] or cnum_raw
        if final_details["player"] and final_details["player"] != "Unknown Player":
            player_final = final_details["player"]
        else:
            player_final = player_name or "Unknown Player"

        team_final = final_details["team"] or str(row.get("Team", "")).strip()
        if canonical_subset_key(final_sub, set_name) == "BASE":
            pr_final = ""
        else:
            pr_final = final_details["print_run"] or format_print_run(row.get("Print_Run", ""))
        attr_final = final_details.get("attributes") or str(row.get("Attributes", "")).strip()

        df.at[row_idx, "Subset_Parallel"] = final_sub
        df.at[row_idx, "Card_Number"] = f"#{cnum_final}"
        df.at[row_idx, "Player"] = player_final
        df.at[row_idx, "Team"] = team_final
        df.at[row_idx, "Print_Run"] = pr_final
        df.at[row_idx, "Attributes"] = attr_final

        for oc in override_cols:
            df.at[row_idx, oc] = ""

        card_stem = build_card_image_stem(set_name, final_sub, cnum_final, player_final)
        if card_stem not in seeded_inventory_stems:
            copy_tracker[card_stem] += get_existing_copy_count(set_name, final_sub, cnum_final, player_final)
            seeded_inventory_stems.add(card_stem)
        copy_tracker[card_stem] += 1
        copy_num = copy_tracker[card_stem]

        new_f, new_b, new_c = build_card_image_filenames(set_name, final_sub, cnum_final, player_final, sku_str)

        df.at[row_idx, "Copy_Number"] = str(copy_num)
        df.at[row_idx, "Front_File"] = new_f
        df.at[row_idx, "Back_File"] = new_b
        df.at[row_idx, "Corners_File"] = new_c

        tmpl_ref = resolve_template_reference_paths(set_name, final_sub, cnum_final)
        if tmpl_ref["front_rel"]:
            df.at[row_idx, "Matched_Template_Front"] = tmpl_ref["front_rel"]
        if tmpl_ref["back_rel"]:
            df.at[row_idx, "Matched_Template_Back"] = tmpl_ref["back_rel"]

        if (old_f, old_b, old_c) != (new_f, new_b, new_c):
            renamed_count += 1
            for old_name, new_name, tag in [(old_f, new_f, "F"), (old_b, new_b, "B"), (old_c, new_c, "C")]:
                if not old_name:
                    continue
                src_p = batch_dir / old_name
                tmp_p = batch_dir / f"__tmp_rename_{row_idx}_{tag}.jpg"
                dst_p = batch_dir / new_name
                if src_p.exists():
                    _safe_move_file(src_p, tmp_p)
                    temp_moves.append((tmp_p, dst_p))

    for tmp_p, dst_p in temp_moves:
        if tmp_p.exists():
            _safe_move_file(tmp_p, dst_p)

    cols_to_drop = [c for c in override_cols if c != "Manual_Override"]
    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True)
    if "Manual_Override" in df.columns:
        other_cols = [c for c in df.columns if c != "Manual_Override"]
        df = df[other_cols + ["Manual_Override"]]
    else:
        df["Manual_Override"] = ""

    with interprocess_file_lock(manifest_path.with_suffix(".csv.lock")):
        atomic_write_bytes(
            manifest_path,
            lambda tmp_p: df.to_csv(tmp_p, index=False, encoding="utf-8-sig"),
        )
    return df, override_applied_count, renamed_count


# ==============================================================================
# 6. COMMIT BATCH TO 1-ROW-PER-CARD INVENTORY & PERMANENT _CARDS LIBRARY
# ==============================================================================
def commit_batch_to_inventory(
    batch_dir: Path,
    move_images_and_archive: bool = True,
    recalculate_sales_strategy: bool = True,
) -> dict:
    """Finalizes a verified batch, moves images to _Cards, and appends rows to Inventory.csv."""
    batch_dir = Path(batch_dir)
    df, overrides_applied, renamed_sets = apply_manifest_overrides_and_rename(batch_dir)
    if df.empty:
        return {"committed_cards": 0, "moved_images": 0, "skus": []}

    df = assign_missing_skus(df)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    moved_img_count = 0
    if move_images_and_archive:
        for row_idx, row in df.iterrows():
            sku_str = str(row["SKU"]).strip()
            set_folder_name = sanitize_filename_part(row["Set"])
            target_set_dir = REVIEWED_CARDS_DIR / set_folder_name
            target_set_dir.mkdir(parents=True, exist_ok=True)

            f_name, b_name, c_name = build_card_image_filenames(
                row["Set"],
                row["Subset_Parallel"],
                str(row["Card_Number"]).lstrip("#"),
                row["Player"],
                sku_str,
            )

            for col_name, final_fname in [("Front_File", f_name), ("Back_File", b_name), ("Corners_File", c_name)]:
                src_img = batch_dir / str(row.get(col_name, ""))
                dst_img = target_set_dir / final_fname
                if src_img.exists():
                    if _safe_move_file(src_img, dst_img):
                        moved_img_count += 1
                df.at[row_idx, col_name] = final_fname

    inv_df = load_inventory_df()
    existing_skus = set(inv_df["SKU"].astype(str).tolist())

    new_inv_rows = []
    for _, row in df.iterrows():
        sku_str = str(row["SKU"]).strip()
        raw_p = str(row.get("Raw_Price", "")).strip()
        val_src = str(row.get("Valuation_Source", "")).strip() or (
            "Manual" if raw_p else "Uncomped"
        )
        min_p = str(row.get("Min_Sale_Price", "")).strip() or raw_p
        rec_p = str(row.get("Rec_Sale_Price", "")).strip() or raw_p
        new_rec = {
            "SKU": sku_str,
            "Status": str(row.get("Status", "In Stock")).strip() or "In Stock",
            "Hold_Tag": str(row.get("Hold_Tag", "For Sale")).strip() or "For Sale",
            "Set": str(row.get("Set", "")).strip(),
            "Subset": str(row.get("Subset_Parallel", row.get("Subset", "Base"))).strip(),
            "Card Number": str(row.get("Card_Number", row.get("Card Number", ""))).strip().lstrip("#"),
            "Player": str(row.get("Player", "")).strip(),
            "Team": str(row.get("Team", "")).strip(),
            "Print Run": format_print_run(row.get("Print_Run", row.get("Print Run", ""))),
            "Attributes": str(row.get("Attributes", "")).strip(),
            "Copy_Number": str(row.get("Copy_Number", "1")).strip(),
            "Centering_LR": str(row.get("Centering_LR", "")).strip(),
            "Centering_TB": str(row.get("Centering_TB", "")).strip(),
            "Sub_Centering": str(row.get("Sub_Centering", "")).strip(),
            "Sub_Corners": str(row.get("Sub_Corners", "")).strip(),
            "Sub_Edges": str(row.get("Sub_Edges", "")).strip(),
            "Sub_Surface": str(row.get("Sub_Surface", "")).strip(),
            "Est_Grade": str(row.get("Est_Grade", "")).strip(),
            "Est_PSA": str(row.get("Est_PSA", "")).strip(),
            "Est_BGS": str(row.get("Est_BGS", "")).strip(),
            "Grading_Notes": str(row.get("Grading_Notes", "")).strip(),
            "Raw_Price": raw_p,
            "Valuation_Source": val_src,
            "Min_Sale_Price": min_p,
            "Rec_Sale_Price": rec_p,
            "PSA_9_Price": str(row.get("PSA_9_Price", "")).strip(),
            "BGS_9_5_Price": str(row.get("BGS_9_5_Price", "")).strip(),
            "PSA_10_Price": str(row.get("PSA_10_Price", "")).strip(),
            "Est_Graded_PSA": str(row.get("Est_Graded_PSA", "")).strip(),
            "Est_Graded_BGS": str(row.get("Est_Graded_BGS", "")).strip(),
            "EV_PSA": str(row.get("EV_PSA", "")).strip(),
            "EV_BGS": str(row.get("EV_BGS", "")).strip(),
            "Best_Grader": str(row.get("Best_Grader", "")).strip(),
            "Max_Net_Gain": str(row.get("Max_Net_Gain", "")).strip(),
            "Recommended_Action": str(row.get("Recommended_Action", "")).strip(),
            "Front_File": str(row.get("Front_File", "")).strip(),
            "Back_File": str(row.get("Back_File", "")).strip(),
            "Corners_File": str(row.get("Corners_File", "")).strip(),
            "Matched_Template_Front": str(row.get("Matched_Template_Front", "")).strip(),
            "Matched_Template_Back": str(row.get("Matched_Template_Back", "")).strip(),
            "OCR_Confidence": str(row.get("OCR_Confidence", "")).strip(),
            "Template_Similarity": str(row.get("Template_Similarity", "")).strip(),
            "Needs_Review": "False",
            "Label_Printed": str(row.get("Label_Printed", "False")).strip() or "False",
            "Date_Added": str(row.get("Date_Added", now_str)).strip() or now_str,
            "Source_Batch": str(row.get("Source_Batch", batch_dir.name)).strip(),
        }
        if sku_str in existing_skus:
            inv_df.loc[inv_df["SKU"] == sku_str, INVENTORY_COLUMNS] = [new_rec[c] for c in INVENTORY_COLUMNS]
        else:
            new_inv_rows.append(new_rec)

    if new_inv_rows:
        new_rows_df = pd.DataFrame(new_inv_rows)
        inv_df = new_rows_df if inv_df.empty else pd.concat([inv_df, new_rows_df], ignore_index=True)

    save_inventory_df(inv_df)
    man_p = batch_dir / "Batch_Inventory_Manifest.csv"
    with interprocess_file_lock(man_p.with_suffix(".csv.lock")):
        atomic_write_bytes(
            man_p,
            lambda tmp_p: df.to_csv(tmp_p, index=False, encoding="utf-8-sig"),
        )

    if recalculate_sales_strategy:
        try:
            from Core.sales_engine import recalculate_sales_strategy_from_cache
            recalculate_sales_strategy_from_cache(save_inventory=True, trigger_source="auto_on_commit")
        except Exception:
            pass

    if move_images_and_archive:
        source_batches = set(df["Source_Batch"].dropna().unique()) if "Source_Batch" in df.columns else set()
        for sb_name in source_batches:
            if not sb_name:
                continue
            src_pdf_dir = INPUT_PATH / sb_name
            if src_pdf_dir.exists() and src_pdf_dir.is_dir() and src_pdf_dir != INPUT_PATH:
                ARCHIVE_SCAN_PATH.mkdir(parents=True, exist_ok=True)
                _safe_archive_directory(src_pdf_dir, ARCHIVE_SCAN_PATH / sb_name)

        if batch_dir.exists() and batch_dir not in (BATCHES_DIR, INVENTORY_DIR):
            PROCESSED_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            _safe_archive_directory(batch_dir, PROCESSED_ARCHIVE_DIR / batch_dir.name)

    return {
        "committed_cards": len(df),
        "moved_images": moved_img_count,
        "overrides_applied": overrides_applied,
        "renamed_sets": renamed_sets,
        "skus": df["SKU"].tolist(),
    }



def _safe_move_file_overwrite(src: Path, dst: Path) -> bool:
    """Safely moves a file (even across Windows drives or over existing destinations)."""
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dst.exists() and dst.resolve() == src.resolve():
            return True
    except Exception:
        pass
    try:
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))
        return True
    except Exception:
        try:
            shutil.copy2(str(src), str(dst))
            try:
                src.unlink()
            except Exception:
                pass
            return True
        except Exception:
            return False


def _safe_archive_folder_move(src_dir: Path, dst_dir: Path) -> bool:
    """
    Safely archives a folder (e.g. D: -> F:) without ever throwing `shutil.Error: Destination already exists`
    or failing a commit due to a Windows Explorer lock.
    """
    if not src_dir.exists() or not src_dir.is_dir():
        return False
    try:
        dst_dir.parent.mkdir(parents=True, exist_ok=True)
        final_dst = dst_dir
        if final_dst.exists():
            ts_suf = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_dst = dst_dir.parent / f"{dst_dir.name}_{ts_suf}"
        shutil.copytree(str(src_dir), str(final_dst), dirs_exist_ok=True)
        shutil.rmtree(str(src_dir), ignore_errors=True)
        return True
    except Exception:
        return False


def remove_cards_from_batch(
    batch_dir: Path,
    skus: list[str],
    delete_files: bool = True,
) -> dict:
    """
    Removes one or more card SKU(s) from an uncommitted batch's `Batch_Inventory_Manifest.csv`
    and deletes their `_F.jpg`, `_B.jpg`, and `_C.jpg` image files from `batch_dir`.
    Marks any matching entries in `.processed_pdfs.json` as `"DELETED"` so resuming the batch
    never re-imports a scan the user intentionally removed.
    """
    import json

    batch_dir = Path(batch_dir)
    man_p = batch_dir / "Batch_Inventory_Manifest.csv"
    if not man_p.exists():
        return {"success": False, "error": f"Batch manifest not found: {batch_dir.name}"}

    sku_set = {str(s or "").strip() for s in (skus or []) if str(s or "").strip()}
    if not sku_set:
        return {"success": False, "error": "No SKU(s) specified for deletion."}

    df = pd.read_csv(man_p, dtype=str, keep_default_na=False)
    if df.empty or "SKU" not in df.columns:
        return {"success": True, "removedCount": 0, "removedSkus": [], "deletedFiles": 0, "cards": []}

    df["SKU"] = df["SKU"].astype(str).str.strip()
    del_mask = df["SKU"].isin(sku_set)
    removed_df = df[del_mask].copy()
    kept_df = df[~del_mask].copy()
    removed_skus = [str(s).strip() for s in removed_df["SKU"].tolist()]

    deleted_files = 0
    if delete_files and not removed_df.empty:
        for _, r in removed_df.iterrows():
            for col_f in ("Front_File", "Back_File", "Corners_File"):
                fn = str(r.get(col_f) or "").strip()
                if fn:
                    fp = batch_dir / fn
                    if fp.exists() and fp.is_file():
                        try:
                            fp.unlink()
                            deleted_files += 1
                        except Exception:
                            pass
            # Also catch any orphaned _[{SKU}]_{F|B|C}.jpg or legacy _{SKU}_{F|B|C}.jpg matching the removed SKU
            sk_s = str(r.get("SKU") or "").strip()
            if sk_s:
                sk_up = sk_s.upper()
                for cand_f in batch_dir.glob("*.jpg"):
                    if not cand_f.is_file():
                        continue
                    n_up = cand_f.name.upper()
                    if f"_[{sk_up}]_" not in n_up and f"_{sk_up}_" not in n_up:
                        continue
                    try:
                        cand_f.unlink()
                        deleted_files += 1
                    except Exception:
                        pass

    tmp_man = man_p.with_suffix(".csv.tmp")
    kept_df.to_csv(tmp_man, index=False, encoding="utf-8-sig")
    os.replace(str(tmp_man), str(man_p))

    # Preserve deleted PDFs in .processed_pdfs.json so batch resume won't re-ingest deleted scans
    cp_file = batch_dir / ".processed_pdfs.json"
    if cp_file.exists() and removed_skus:
        try:
            cp_data = json.loads(cp_file.read_text(encoding="utf-8-sig"))
            if isinstance(cp_data, dict):
                rm_set = set(removed_skus)
                changed_cp = False
                for k_pdf, v_sku in list(cp_data.items()):
                    if str(v_sku).strip() in rm_set:
                        cp_data[k_pdf] = f"DELETED_{v_sku}"
                        changed_cp = True
                if changed_cp:
                    tmp_cp = cp_file.with_suffix(".json.tmp")
                    tmp_cp.write_text(json.dumps(cp_data, indent=2), encoding="utf-8")
                    os.replace(str(tmp_cp), str(cp_file))
        except Exception:
            pass

    return {
        "success": True,
        "batchName": batch_dir.name,
        "removedCount": len(removed_skus),
        "removedSkus": removed_skus,
        "deletedFiles": deleted_files,
        "cards": kept_df.to_dict(orient="records"),
    }


def commit_batch_to_inventory_v2(
    batch_dir: Path,
    move_images_and_archive: bool = True,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    recalculate_sales_strategy: bool = True,
) -> dict:
    """
    Hardened 3-Drive Batch Commit Engine (`v0.24.0-beta.44`):
      - Preserves each batch's exact `Source_Batch = batch_dir.name` so committing multiple
        or all batches keeps every batch cleanly separated in Inventory & Label Hub.
      - Auto-resolves any SKU collision against `Inventory.csv` before writing.
      - Moves (or copies) `_F/_B/_C.jpg` scans safely into `D:\\Tabulas Set Library\\_My_Collection\\<Set>\\`.
      - Writes `_COMMITTED.lock` immediately and safely archives raw PDFs & batch manifests to
        `F:\\Tabulas Archive\\` without ever crashing on existing archive folders or Windows locks.
    """
    from Core.config import (
        ARCHIVE_SCAN_PATH,
        INPUT_PATH,
        INVENTORY_COLUMNS,
        PROCESSED_ARCHIVE_DIR,
        REVIEWED_CARDS_DIR,
        ensure_directories,
        format_print_run,
        sanitize_filename_part,
    )

    ensure_directories()
    batch_dir = Path(batch_dir)
    batch_name = batch_dir.name
    man_p = batch_dir / "Batch_Inventory_Manifest.csv"
    if not man_p.exists():
        return {"success": False, "batch_name": batch_name, "committed_cards": 0, "error": f"Manifest not found in {batch_dir}"}

    batch_df = pd.read_csv(man_p, dtype=str, keep_default_na=False)
    if batch_df.empty:
        return {"success": False, "batch_name": batch_name, "committed_cards": 0, "error": f"Batch '{batch_name}' has 0 cards to commit."}

    prev_inv_df = load_inventory_df()
    existing_skus: set[str] = set()
    max_sku_num = 1000000
    if not prev_inv_df.empty and "SKU" in prev_inv_df.columns:
        for s_v in prev_inv_df["SKU"].astype(str).str.strip().tolist():
            if s_v:
                existing_skus.add(s_v)
                if s_v.isdigit():
                    max_sku_num = max(max_sku_num, int(s_v))

    today_str = datetime.now().strftime("%Y-%m-%d")
    new_rows: list[dict] = []
    moved_images = 0
    total_batch_rows = len(batch_df)

    if log_cb:
        log_cb(f"📂 Committing batch '{batch_name}' ({total_batch_rows:,} card(s), move_and_archive={move_images_and_archive})...")

    for row_pos, (_, r) in enumerate(batch_df.iterrows(), 1):
        sku_s = str(r.get("SKU") or "").strip()
        if not sku_s or sku_s in existing_skus:
            max_sku_num += 1
            sku_s = f"{max_sku_num:07d}"
        existing_skus.add(sku_s)

        set_n = str(r.get("Set") or "").strip() or "Unknown Set"
        sub_n = str(r.get("Subset_Parallel") or r.get("Subset") or "Base").strip() or "Base"
        cnum_n = str(r.get("Card_Number") or r.get("Card Number") or "0").strip().lstrip("#")
        plr_n = str(r.get("Player") or "Unknown Player").strip()
        tm_n = str(r.get("Team") or "").strip()
        pr_n = "" if canonical_subset_key(sub_n, set_n) == "BASE" else format_print_run(r.get("Print_Run") or r.get("Print Run") or "")

        dest_set_dir = REVIEWED_CARDS_DIR / sanitize_filename_part(set_n)
        dest_set_dir.mkdir(parents=True, exist_ok=True)
        canon_f, canon_b, canon_c = build_card_image_filenames(set_n, sub_n, cnum_n, plr_n, sku_s)

        final_files = {"Front_File": "", "Back_File": "", "Corners_File": ""}
        for col_f, canon_fn in (("Front_File", canon_f), ("Back_File", canon_b), ("Corners_File", canon_c)):
            old_fn = str(r.get(col_f) or "").strip()
            src_fp = (batch_dir / old_fn) if old_fn else None
            if src_fp is not None and src_fp.exists() and src_fp.is_file():
                dst_fp = dest_set_dir / canon_fn
                if move_images_and_archive:
                    if _safe_move_file_overwrite(src_fp, dst_fp):
                        moved_images += 1
                        final_files[col_f] = canon_fn
                    else:
                        final_files[col_f] = old_fn
                else:
                    try:
                        shutil.copy2(str(src_fp), str(dst_fp))
                        moved_images += 1
                        final_files[col_f] = canon_fn
                    except Exception:
                        final_files[col_f] = old_fn
            elif old_fn:
                final_files[col_f] = old_fn

        inv_rec = {col: "" for col in INVENTORY_COLUMNS}
        inv_rec.update({
            "SKU": sku_s,
            "Set": set_n,
            "Subset": sub_n,
            "Card Number": cnum_n,
            "Player": plr_n,
            "Team": tm_n,
            "Print Run": pr_n,
            "Attributes": str(r.get("Attributes") or "").strip(),
            "Copy_Number": str(r.get("Copy_Number") or "1").strip(),
            "Status": str(r.get("Status") or "In Stock").strip() or "In Stock",
            "Hold_Tag": str(r.get("Hold_Tag") or "For Sale").strip() or "For Sale",
            "Label_Printed": str(r.get("Label_Printed") or "False").strip() or "False",
            "Needs_Review": str(r.get("Needs_Review") or "False").strip() or "False",
            "Source_Batch": batch_name,
            "Date_Added": today_str,
            "Front_File": final_files["Front_File"],
            "Back_File": final_files["Back_File"],
            "Corners_File": final_files["Corners_File"],
            "Matched_Template_Front": str(r.get("Matched_Template_Front") or "").strip(),
            "Matched_Template_Back": str(r.get("Matched_Template_Back") or "").strip(),
            "OCR_Confidence": str(r.get("OCR_Confidence") or "").strip(),
            "Template_Similarity": str(r.get("Template_Similarity") or "").strip(),
            "Est_Grade": str(r.get("Est_Grade") or "").strip(),
            "Est_PSA": str(r.get("Est_PSA") or "").strip(),
            "Est_BGS": str(r.get("Est_BGS") or "").strip(),
            "Centering_LR": str(r.get("Centering_LR") or "").strip(),
            "Centering_TB": str(r.get("Centering_TB") or "").strip(),
            "Sub_Centering": str(r.get("Sub_Centering") or "").strip(),
            "Sub_Corners": str(r.get("Sub_Corners") or "").strip(),
            "Sub_Edges": str(r.get("Sub_Edges") or "").strip(),
            "Sub_Surface": str(r.get("Sub_Surface") or "").strip(),
            "Grading_Notes": str(r.get("Grading_Notes") or "").strip(),
            "Raw_Price": str(r.get("Raw_Price") or "").strip(),
            "Valuation_Source": str(r.get("Valuation_Source") or "").strip() or (
                "Uncomped" if not str(r.get("Raw_Price") or "").strip() else "Verified SCP Exact"
            ),
            "Min_Sale_Price": str(r.get("Min_Sale_Price") or "").strip(),
            "Rec_Sale_Price": str(r.get("Rec_Sale_Price") or r.get("Raw_Price") or "").strip(),
            "PSA_9_Price": str(r.get("PSA_9_Price") or "").strip(),
            "BGS_9_5_Price": str(r.get("BGS_9_5_Price") or "").strip(),
            "PSA_10_Price": str(r.get("PSA_10_Price") or "").strip(),
            "Est_Graded_PSA": str(r.get("Est_Graded_PSA") or "").strip(),
            "Est_Graded_BGS": str(r.get("Est_Graded_BGS") or "").strip(),
            "EV_PSA": str(r.get("EV_PSA") or "").strip(),
            "EV_BGS": str(r.get("EV_BGS") or "").strip(),
            "Best_Grader": str(r.get("Best_Grader") or "").strip(),
            "Max_Net_Gain": str(r.get("Max_Net_Gain") or "").strip(),
            "Recommended_Action": str(r.get("Recommended_Action") or "").strip(),
        })
        new_rows.append(inv_rec)
        if progress_callback is not None:
            progress_callback(row_pos, total_batch_rows, inv_rec)

    if log_cb:
        log_cb(f"  💾 Moved {moved_images:,} scan image(s) to _My_Collection. Syncing copy numbers & writing Inventory.csv...")

    new_df = pd.DataFrame(new_rows, columns=INVENTORY_COLUMNS)
    inv_lock = INVENTORY_FILE.with_suffix(".csv.lock")
    with interprocess_file_lock(inv_lock):
        latest_inv_df = load_inventory_df()
        combined_df = new_df if latest_inv_df.empty else pd.concat([latest_inv_df, new_df], ignore_index=True)
        combined_df = assign_missing_skus(combined_df)
        try:
            synced_df, _ = sync_inventory_copy_numbers_and_files(combined_df, previous_inv_df=latest_inv_df)
        except Exception:
            synced_df = combined_df
        save_inventory_df(synced_df)

    # Mark committed immediately before archive moves so UI never sees a ghost batch
    try:
        (batch_dir / "_COMMITTED.lock").write_text(
            f"Committed {len(new_rows)} cards to Inventory.csv on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            encoding="utf-8",
        )
    except Exception:
        pass

    archived_scans = False
    archived_batch = False
    if move_images_and_archive:
        raw_scan_dir = INPUT_PATH / batch_name
        if raw_scan_dir.exists() and raw_scan_dir.is_dir():
            if log_cb:
                log_cb(f"  📦 Archiving raw scanner PDFs -> {ARCHIVE_SCAN_PATH / batch_name} ...")
            archived_scans = _safe_archive_folder_move(raw_scan_dir, ARCHIVE_SCAN_PATH / batch_name)
        if log_cb:
            log_cb(f"  📦 Archiving committed batch folder -> {PROCESSED_ARCHIVE_DIR / batch_name} ...")
        archived_batch = _safe_archive_folder_move(batch_dir, PROCESSED_ARCHIVE_DIR / batch_name)

    sales_strategy_res = None
    if recalculate_sales_strategy:
        try:
            from Core.sales_engine import recalculate_sales_strategy_from_cache
            sales_strategy_res = recalculate_sales_strategy_from_cache(
                save_inventory=True,
                trigger_source="auto_on_commit",
            )
            if log_cb:
                log_cb(
                    f"  📈 Auto-recalculated Sales Strategy from cached comps: "
                    f"Unit COGS=${sales_strategy_res['summary'].get('overall_unit_cogs', 0.0):.2f} | "
                    f"Verified Market=${sales_strategy_res.get('total_verified_market_value', 0.0):,.2f} "
                    f"({sales_strategy_res.get('comped_cards_count', 0)} comped, "
                    f"{sales_strategy_res.get('uncomped_cards_count', 0)} uncomped) | "
                    f"Lots={sales_strategy_res.get('lots_count', 0)}"
                )
        except Exception as strat_err:
            if log_cb:
                log_cb(f"  [!] Warning: Auto Sales Strategy recalculation skipped: {strat_err}")

    if log_cb:
        log_cb(
            f"  ✅ Batch '{batch_name}' committed: {len(new_rows):,} card(s) added to Inventory.csv "
            f"(Source_Batch={batch_name} | images moved={moved_images:,} | raw PDFs archived={archived_scans})."
        )

    return {
        "success": True,
        "batch_name": batch_name,
        "committed_cards": len(new_rows),
        "moved_images": moved_images,
        "archived_scans": archived_scans,
        "archived_batch": archived_batch,
        "sales_strategy_recalculated": bool(sales_strategy_res and sales_strategy_res.get("success")),
        "sales_strategy_summary": (sales_strategy_res or {}).get("summary", {}),
    }
