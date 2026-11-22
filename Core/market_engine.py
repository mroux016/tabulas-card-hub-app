from __future__ import annotations
# ==============================================================================
# Core/market_engine.py - PHASE 1 (#1-6): GRADING AVAILABILITY, MARKET COMPS,
# RECOMMENDATION ENGINE (<7.0 GUARD), ALERTS, 5-MODE COMPLETION & CARDS-TO-BUY
# ==============================================================================
import json
import os
import re
import smtplib
import subprocess
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

__version__ = "0.25.0-beta.1"
__last_updated__ = "2026-11-21 18:45:00"

try:
    from bs4 import BeautifulSoup
except ImportError:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "beautifulsoup4", "--quiet", "--no-warn-conflicts"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

from Core.config import (
    BGS_PROB_MATRIX,
    CARDHEDGER_API_KEY,
    CHECKLIST_PATH,
    COLLECTION_HISTORY_FILE,
    DEFAULT_DUGOUT_VAULT_TIERS,
    DEFAULT_GRADE_MULTIPLIERS,
    EXPENSES_PRICING_CONFIG_FILE,
    GRADING_FEES,
    GRADING_TIERS_CACHE_FILE,
    INVENTORY_FILE,
    MARKET_ALERTS_FILE,
    MARKET_COMPS_CACHE_FILE,
    MARKET_SETTINGS_FILE,
    PRICECHARTING_API_KEY,
    PSA_PROB_MATRIX,
    RUNTIME_CONFIG,
    canonical_subset_key,
    ensure_directories,
    format_print_run,
    norm,
    strip_accents,
)
from Core.rate_learner import get_rate_learner


def _adaptive_http_get(endpoint: str, url: str, headers: dict, timeout: int = 12, allow_redirects: bool = True, max_rl_retries: int = 3):
    """Rate-learned HTTP GET wrapper for SportsCardsPro and Dugout Vault."""
    learner = get_rate_learner()
    for rl_i in range(1, max_rl_retries + 1):
        learner.wait_before_request(endpoint)
        t0 = time.time()
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
            el_ms = int((time.time() - t0) * 1000)
            if resp.status_code == 429:
                wait_s, _ = learner.record_rate_limit(endpoint, retry_after_header=resp.headers.get("Retry-After"))
                if rl_i < max_rl_retries:
                    time.sleep(wait_s)
                    continue
                return resp
            if resp.status_code == 403:
                learner.record_cf_challenge(endpoint)
                return resp
            if resp.status_code in (200, 404):
                learner.record_success(endpoint, elapsed_ms=el_ms, status_code=resp.status_code)
            return resp
        except Exception:
            return None
    return None

DUGOUT_VAULT_TRACKER_URL = "https://www.dugoutvault.app/grading-tracker"
SPORTSCARDSPRO_BASE_URL = "https://www.sportscardspro.com"

MARKET_COMPS_COLUMNS = [
    "Comp_Key",
    "Set",
    "Subset",
    "Card Number",
    "Player",
    "Print Run",
    "Ungraded",
    "Grade_7",
    "Grade_8",
    "Grade_9",
    "BGS_9_5",
    "PSA_10",
    "BGS_10",
    "Sales_Volume",
    "Card_URL",
    "Comp_URL",
    "Source_URL",
    "Last_Updated",
]

SET_COMPLETION_MODES = (
    "1. Base Cards Only",
    "2. Inserts Only",
    "3. Combined Base + Parallels (Any Version of Base Card, Excl. Inserts)",
    "4. Combined Base + Parallel + Insert (Any Version of Every Card)",
    "5. Complete Master Checklist (All Base, Parallels & Inserts)",
)


def _safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    s = re.sub(r"[^0-9.\-]", "", str(val).strip())
    if not s or s in (".", "-", "-."):
        return default
    try:
        return float(s)
    except Exception:
        return default


def _abbreviate_turnaround(turnaround_raw: str) -> str:
    """Abbreviates 'business days' / 'business day' to 'Bus. Days' / 'Bus. Day'."""
    s = str(turnaround_raw or "").strip()
    s = re.sub(r"\bbusiness\s+days\b", "Bus. Days", s, flags=re.IGNORECASE)
    s = re.sub(r"\bbusiness\s+day\b", "Bus. Day", s, flags=re.IGNORECASE)
    return s


def build_comp_key(set_name: str, subset_name: str, card_number: str, player_name: str = "") -> str:
    """Builds a canonical lookup key for market_comps_cache.csv."""
    s_k = norm(set_name)
    sub_k = canonical_subset_key(subset_name, set_name)
    cn_k = norm(str(card_number or "").lstrip("#"))
    p_k = norm(player_name)
    return f"{s_k}|{sub_k}|{cn_k}|{p_k}"


# ==============================================================================
# 1. GRADING AVAILABILITY & MAX-VALUE TIER TRACKER
# ==============================================================================
_VALID_PSA_TIER_PREFIXES = (
    ("value bulk", "Value Bulk"),
    ("value plus", "Value Plus"),
    ("value max", "Value Max"),
    ("value", "Value"),
    ("standard", "Standard"),
    ("priority", "Priority"),
    ("super express", "Super Express"),
    ("express", "Express"),
    ("premier", "Premier"),
    ("walk-through", "Walk-Through"),
    ("walkthrough", "Walk-Through"),
)

_VALID_BGS_TIER_PREFIXES = (
    ("base (no subgrades)", "Base (no subgrades)"),
    ("base (with subgrades)", "Base (with subgrades)"),
    ("standard", "Standard"),
    ("express", "Express"),
    ("priority", "Priority"),
)


def _normalize_grader_tier_name(grader: str, raw_tier: str) -> Optional[str]:
    s = re.sub(r"\s+", " ", str(raw_tier or "")).strip()
    if not s:
        return None
    low = s.lower()
    table = _VALID_PSA_TIER_PREFIXES if grader.upper() == "PSA" else _VALID_BGS_TIER_PREFIXES
    for pref_low, canon_label in table:
        if low.startswith(pref_low):
            if pref_low == "standard" and ("($" in low or "$1,500" in low or "$3,500" in low):
                return None
            return canon_label
    return None


def _sanitize_cached_grading_tiers(data: dict) -> tuple[dict, bool]:
    changed = False
    out = dict(data)
    for grader_key in ("PSA", "BGS"):
        raw_list = out.get(grader_key, [])
        cleaned_list = []
        seen_names = set()
        for item in raw_list:
            if not isinstance(item, dict):
                changed = True
                continue
            canon_t = _normalize_grader_tier_name(grader_key, item.get("tier", ""))
            if not canon_t or canon_t in seen_names:
                changed = True
                continue
            turn_abbr = _abbreviate_turnaround(item.get("turnaround", ""))
            if canon_t != item.get("tier") or turn_abbr != item.get("turnaround"):
                changed = True
            seen_names.add(canon_t)
            cleaned_list.append({
                "tier": canon_t,
                "price": float(item.get("price", 0.0)),
                "max_value": float(item.get("max_value", 999999.0)),
                "turnaround": turn_abbr,
                "status": "paused" if "pause" in str(item.get("status", "open")).lower() else "open",
            })
        if not cleaned_list:
            cleaned_list = list(DEFAULT_DUGOUT_VAULT_TIERS[grader_key])
            changed = True
        out[grader_key] = cleaned_list
    return out, changed


def load_grading_tiers_cache() -> dict:
    """Loads cached PSA and BGS grading tiers (price, max_value, Bus. Days turnaround, open/paused)."""
    ensure_directories()
    if GRADING_TIERS_CACHE_FILE.exists():
        try:
            with open(GRADING_TIERS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "PSA" in data and "BGS" in data:
                sanitized, was_dirty = _sanitize_cached_grading_tiers(data)
                if was_dirty:
                    with open(GRADING_TIERS_CACHE_FILE, "w", encoding="utf-8") as fw:
                        json.dump(sanitized, fw, indent=2)
                return sanitized
        except Exception:
            pass
    default_payload = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": DUGOUT_VAULT_TRACKER_URL,
        "PSA": DEFAULT_DUGOUT_VAULT_TIERS["PSA"],
        "BGS": DEFAULT_DUGOUT_VAULT_TIERS["BGS"],
    }
    try:
        with open(GRADING_TIERS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(default_payload, f, indent=2)
    except Exception:
        pass
    return default_payload


def refresh_dugout_vault_grading_tiers(include_collectors_club_bulk: bool = False) -> dict:
    """Scrapes live PSA and Beckett (BGS) grading availability & turnaround (in Bus. Days)."""
    ensure_directories()
    cached = load_grading_tiers_cache()
    if BeautifulSoup is None:
        return cached

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = _adaptive_http_get("dugoutvault", DUGOUT_VAULT_TRACKER_URL, headers=headers, timeout=15)
        if not resp or resp.status_code != 200:
            return cached
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return cached

    parsed_psa = []
    parsed_bgs = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        hdr_cells = [th.get_text(" ", strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        if "tier" not in " ".join(hdr_cells) or "grader" in " ".join(hdr_cells):
            continue

        nearest_heading = table.find_previous(["h2", "h3"])
        heading_txt = nearest_heading.get_text(" ", strip=True).upper() if nearest_heading else ""

        target_grader = None
        target_list = None
        if heading_txt.startswith("PSA") and not parsed_psa:
            target_grader = "PSA"
            target_list = parsed_psa
        elif ("BECKETT" in heading_txt or "BGS" in heading_txt) and not parsed_bgs:
            target_grader = "BGS"
            target_list = parsed_bgs

        if target_list is None or target_grader is None:
            continue

        seen_tiers = set()
        for tr in rows[1:]:
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(tds) < 4:
                continue
            tier_clean = _normalize_grader_tier_name(target_grader, tds[0])
            if not tier_clean or tier_clean in seen_tiers:
                continue

            price_val = _safe_float(tds[1], 0.0)
            max_val_raw = tds[2].strip()
            if "UNLIMITED" in max_val_raw.upper() or not max_val_raw:
                max_val = 999999.0
            else:
                max_val = _safe_float(max_val_raw, 999999.0)
            turnaround_str = _abbreviate_turnaround(tds[3].strip())
            status_str = tds[4].strip().lower() if len(tds) >= 5 else "open"
            status_clean = "paused" if "pause" in status_str else "open"

            if price_val > 0:
                seen_tiers.add(tier_clean)
                target_list.append({
                    "tier": tier_clean,
                    "price": price_val,
                    "max_value": max_val,
                    "turnaround": turnaround_str,
                    "status": status_clean,
                })

    if parsed_psa:
        cached["PSA"] = parsed_psa
    if parsed_bgs:
        cached["BGS"] = parsed_bgs
    cached["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    cached["source"] = DUGOUT_VAULT_TRACKER_URL

    try:
        with open(GRADING_TIERS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cached, f, indent=2)
    except Exception:
        pass

    psa_min = resolve_grading_tier_fee("PSA", 100.0, cached, include_collectors_club_bulk=include_collectors_club_bulk)
    bgs_min = resolve_grading_tier_fee("BGS", 100.0, cached, include_collectors_club_bulk=include_collectors_club_bulk)
    GRADING_FEES["PSA"] = psa_min["price"]
    GRADING_FEES["BGS"] = bgs_min["price"]
    return cached


def resolve_grading_tier_fee(
    grader: str,
    declared_value: float,
    tiers_data: Optional[dict] = None,
    include_collectors_club_bulk: bool = False,
) -> dict:
    if tiers_data is None:
        tiers_data = load_grading_tiers_cache()
    grader_tiers = tiers_data.get(grader.upper(), DEFAULT_DUGOUT_VAULT_TIERS.get(grader.upper(), []))

    open_tiers = []
    for t in grader_tiers:
        if str(t.get("status", "open")).lower() != "open":
            continue
        if not include_collectors_club_bulk and "bulk" in str(t.get("tier", "")).lower():
            continue
        open_tiers.append(t)

    if not open_tiers:
        open_tiers = list(grader_tiers)

    open_tiers.sort(key=lambda x: (float(x.get("price", 999.0)), float(x.get("max_value", 999999.0))))
    for t in open_tiers:
        if float(t.get("max_value", 999999.0)) >= float(declared_value):
            return {
                "tier": str(t.get("tier", "Standard")),
                "price": float(t.get("price", GRADING_FEES.get(grader, 39.99))),
                "max_value": float(t.get("max_value", 999999.0)),
                "turnaround": _abbreviate_turnaround(str(t.get("turnaround", ""))),
            }

    highest = open_tiers[-1] if open_tiers else {"tier": "Premier", "price": 599.0, "max_value": 10000.0, "turnaround": "7-10 Bus. Days"}
    return {
        "tier": str(highest.get("tier", "Premier")),
        "price": float(highest.get("price", 599.0)),
        "max_value": float(highest.get("max_value", 10000.0)),
        "turnaround": _abbreviate_turnaround(str(highest.get("turnaround", ""))),
    }


# ==============================================================================
# 2. CARD VALUES & GRADE-LEVEL COMPS ENGINE (SPORTSCARDSPRO / 130POINT)
# ==============================================================================
_SCP_NON_BASE_SLUG_TOKENS = (
    "tin-type", "tintype", "mini", "silver-portrait", "foil-filigree", "filigree",
    "framed", "relic", "autograph", "auto", "chrome", "black-border", "gold-border",
    "no-number", "brooklyn-back", "ag-back", "a&g-back", "wood", "metal", "cloth",
    "silk", "rip-card", "glossy", "superfractor", "printing-plate", "refractor",
    "x-fractor", "logofractor", "frozenfractor", "foilfractor", "prizm", "holo-foil",
    "holofoil", "rainbow-foil", "diamante", "confetti", "spring-training", "companion",
    "golden-mirror", "true-photo", "image-variation", "design-variation", "ssp",
    "clear", "acetate", "canvas", "first-card", "vintage-stock", "independence-day",
    "mothers-day", "fathers-day", "memorial-day", "camo", "black-finite", "gold-vinyl",
    "wave", "shimmer", "mojo", "sonar", "speckle", "pulsar", "raywave", "1-of-1",
    "blue", "green", "orange", "purple", "red", "pink", "aqua", "yellow", "gold", "black",
)

_SCP_EXCLUSIVE_FINISH_TOKENS = (
    "chrome", "refractor", "x-fractor", "superfractor", "logofractor",
    "frozenfractor", "foilfractor", "filigree", "portrait", "mini",
    "framed", "relic", "autograph", "auto", "tin-type", "tintype",
    "wood", "metal", "cloth", "silk", "rip", "brooklyn", "no-number",
    "glossy", "diamante", "confetti", "holofoil", "sonar", "wave",
    "shimmer", "mojo", "speckle", "camo", "acetate", "clear", "canvas",
)


def _classify_sportscardspro_slug_match(
    source_url: str,
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
) -> str:
    u_low = str(source_url or "").strip().lower()
    if "/game/" not in u_low:
        return "EXACT"

    parts = u_low.split("/game/", 1)[-1].split("/")
    if len(parts) < 2:
        return "MISMATCH"
    set_slug, card_slug = parts[0], parts[1].split("?")[0].split("#")[0]

    yr_m = re.search(r"\b(19\d\d|20\d\d)\b", str(set_name or ""))
    if yr_m and yr_m.group(1) not in set_slug:
        return "MISMATCH"

    set_up = str(set_name or "").upper()
    if "ALLEN" in set_up and "allen" not in set_slug:
        return "MISMATCH"
    if "ALLEN" not in set_up and "allen" in set_slug:
        return "MISMATCH"
    if "CHROME" not in set_up and "chrome" in set_slug:
        return "MISMATCH"
    if "BOWMAN" not in set_up and "bowman" in set_slug:
        return "MISMATCH"
    if "HOLIDAY" not in set_up and "holiday" in set_slug:
        return "MISMATCH"

    cn_clean = re.sub(r"[^a-z0-9]+", "-", strip_accents(str(card_number or "")).lower().lstrip("#")).strip("-")
    if cn_clean and not (card_slug.endswith(f"-{cn_clean}") or f"-{cn_clean}-" in card_slug or card_slug == cn_clean):
        return "MISMATCH"

    p_slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(str(player_name or "")).lower()).strip("-")
    p_tokens = [t for t in p_slug.split("-") if len(t) >= 3]
    if p_tokens and not all(pt in card_slug for pt in p_tokens[:2]):
        return "MISMATCH"

    rem_slug = card_slug
    for p_tok in [t for t in p_slug.split("-") if len(t) >= 2]:
        rem_slug = re.sub(rf"\b{re.escape(p_tok)}\b", "", rem_slug)
    if cn_clean:
        rem_slug = re.sub(rf"\b{re.escape(cn_clean)}\b", "", rem_slug)
    rem_slug = re.sub(r"-+", "-", rem_slug).strip("-")

    sub_clean = strip_accents(str(subset_name or "Base")).strip().lower()
    sub_norm = sub_clean.replace("a&g", "ag").replace("a and g", "ag")

    if sub_clean in ("", "base", "base set"):
        if rem_slug:
            for bad_tok in _SCP_NON_BASE_SLUG_TOKENS:
                if bad_tok in rem_slug or bad_tok in card_slug:
                    return "MISMATCH"
            allowed_base_extras = {"series-1", "series-2", "update", "base", "rc", "rookie"}
            extra_words = {w for w in rem_slug.split("-") if len(w) >= 2}
            if not extra_words.issubset(allowed_base_extras):
                return "MISMATCH"
        return "EXACT"

    for high_end_tok in ("tin-type", "tintype", "framed", "autograph", "auto", "relic", "superfractor", "1-of-1", "printing-plate"):
        if high_end_tok in card_slug and high_end_tok.replace("-", " ") not in sub_norm and high_end_tok not in sub_norm:
            return "MISMATCH"

    sub_tokens = [
        t for t in re.findall(r"[a-z0-9]{2,}", sub_norm)
        if t not in ("base", "variation", "variations", "parallel", "card", "cards", "set", "the", "and", "back", "border", "bordered")
    ]

    has_conflicting_finish = False
    for excl_tok in _SCP_EXCLUSIVE_FINISH_TOKENS:
        if excl_tok in rem_slug and excl_tok not in sub_norm:
            has_conflicting_finish = True
            break

    all_sub_tokens_present = bool(sub_tokens) and all(st in card_slug for st in sub_tokens)
    if all_sub_tokens_present and not has_conflicting_finish:
        return "EXACT"

    shared_tokens = [st for st in sub_tokens if st in rem_slug]
    if shared_tokens:
        if ("mini" in rem_slug) != ("mini" in sub_norm):
            return "MISMATCH"
        return "PROXY_COMP"

    return "MISMATCH"


def _is_valid_sportscardspro_url_for_subset(
    source_url: str,
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
) -> bool:
    return (
        _classify_sportscardspro_slug_match(source_url, set_name, subset_name, card_number, player_name)
        == "EXACT"
    )


def load_market_comps_cache() -> pd.DataFrame:
    ensure_directories()
    if not MARKET_COMPS_CACHE_FILE.exists():
        empty_df = pd.DataFrame(columns=MARKET_COMPS_COLUMNS)
        empty_df.to_csv(MARKET_COMPS_CACHE_FILE, index=False, encoding="utf-8-sig")
        return empty_df
    try:
        df = pd.read_csv(MARKET_COMPS_CACHE_FILE, dtype=str, keep_default_na=False)
        for col in MARKET_COMPS_COLUMNS:
            if col not in df.columns:
                df[col] = ""

        if not df.empty:
            keep_rows = []
            modified = False
            for _, row in df.iterrows():
                r_dict = row.to_dict()
                s_n = r_dict.get("Set", "")
                sub_n = r_dict.get("Subset", "Base")
                c_n = r_dict.get("Card Number", "")
                p_n = r_dict.get("Player", "")
                exact_u = build_sportscardspro_url(s_n, sub_n, c_n, p_n, keep_literal_ampersand=True)

                curr_src = str(r_dict.get("Source_URL") or r_dict.get("Card_URL") or "").strip()
                if not r_dict.get("Card_URL"):
                    r_dict["Card_URL"] = exact_u
                    modified = True

                match_kind = _classify_sportscardspro_slug_match(curr_src, s_n, sub_n, c_n, p_n)
                if match_kind == "MISMATCH":
                    modified = True
                    continue
                elif match_kind == "PROXY_COMP":
                    if r_dict.get("Card_URL") != exact_u or r_dict.get("Comp_URL") != curr_src:
                        r_dict["Card_URL"] = exact_u
                        r_dict["Comp_URL"] = curr_src
                        r_dict["Source_URL"] = exact_u
                        comp_slug_tail = curr_src.rstrip("/").split("/")[-1]
                        r_dict["Sales_Volume"] = f"Proxy Comp ({comp_slug_tail})"
                        modified = True
                else:
                    if r_dict.get("Card_URL") != curr_src and "/game/" in curr_src:
                        r_dict["Card_URL"] = curr_src
                        modified = True
                    if r_dict.get("Comp_URL") == r_dict.get("Card_URL"):
                        r_dict["Comp_URL"] = ""
                        modified = True

                keep_rows.append(r_dict)

            df = pd.DataFrame(keep_rows, columns=MARKET_COMPS_COLUMNS) if keep_rows else pd.DataFrame(columns=MARKET_COMPS_COLUMNS)
            if modified:
                df.to_csv(MARKET_COMPS_CACHE_FILE, index=False, encoding="utf-8-sig")

        return df[MARKET_COMPS_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=MARKET_COMPS_COLUMNS)


def save_market_comps_cache(df: pd.DataFrame) -> pd.DataFrame:
    ensure_directories()
    out = df.copy()
    for col in MARKET_COMPS_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out.drop_duplicates(subset=["Comp_Key"], keep="last")[MARKET_COMPS_COLUMNS].reset_index(drop=True)
    out.to_csv(MARKET_COMPS_CACHE_FILE, index=False, encoding="utf-8-sig")
    return out


def build_sportscardspro_url(
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
    keep_literal_ampersand: bool = True,
) -> str:
    s_clean = strip_accents(str(set_name or "")).lower()
    sport_prefix = "baseball-cards"
    for sp, slug in (
        ("football", "football-cards"),
        ("basketball", "basketball-cards"),
        ("hockey", "hockey-cards"),
        ("soccer", "soccer-cards"),
        ("racing", "racing-cards"),
    ):
        if sp in s_clean:
            sport_prefix = slug
            s_clean = s_clean.replace(sp, "").strip()
            break
    s_clean = s_clean.replace("baseball", "")
    if keep_literal_ampersand:
        set_slug = re.sub(r"[^a-z0-9&]+", "-", s_clean).strip("-")
    else:
        set_slug = re.sub(r"[^a-z0-9]+", "-", s_clean.replace("&", "and")).strip("-")

    p_clean = strip_accents(str(player_name or "")).lower().replace("/", "-")
    c_clean = strip_accents(str(card_number or "")).lower().lstrip("#")
    sub_clean = strip_accents(str(subset_name or "Base")).lower()

    if sub_clean in ("", "base", "base set"):
        card_slug = re.sub(r"[^a-z0-9]+", "-", f"{p_clean}-{c_clean}").strip("-")
    else:
        card_slug = re.sub(r"[^a-z0-9]+", "-", f"{p_clean}-{sub_clean}-{c_clean}").strip("-")

    return f"{SPORTSCARDSPRO_BASE_URL}/game/{sport_prefix}-{set_slug}/{card_slug}"


def _parse_sportscardspro_html(html_text: str, url: str = "") -> Optional[dict]:
    if BeautifulSoup is None or not html_text:
        return None
    soup = BeautifulSoup(html_text, "html.parser")
    text_blob = soup.get_text(" ", strip=True)

    prices = {}
    id_map = {
        "used_price": "Ungraded",
        "complete_price": "Grade_7",
        "new_price": "Grade_8",
        "graded_price": "Grade_9",
        "box_only_price": "BGS_9_5",
        "manual_only_price": "PSA_10",
        "bgs_10_price": "BGS_10",
    }
    for td_id, col_key in id_map.items():
        el = soup.find(id=td_id)
        if el:
            p_span = el.find(class_="price") or el
            val = _safe_float(p_span.get_text(" ", strip=True), 0.0)
            if val > 0:
                prices[col_key] = val

    if not prices:
        m_strip = re.search(
            r"Ungraded\s+Grade\s*7(?:\s*&\s*7\.5)?\s+Grade\s*8(?:\s*&\s*8\.5)?\s+Grade\s*9\s+Grade\s*9\.5\s+PSA\s*10(?:\s+BGS\s*10)?\s+"
            r"(\$[0-9.,]+|-)\s*(?:[+\-]\$[0-9.,]+\s*)?"
            r"(\$[0-9.,]+|-)\s*(?:[+\-]\$[0-9.,]+\s*)?"
            r"(\$[0-9.,]+|-)\s*(?:[+\-]\$[0-9.,]+\s*)?"
            r"(\$[0-9.,]+|-)\s*(?:[+\-]\$[0-9.,]+\s*)?"
            r"(\$[0-9.,]+|-)\s*(?:[+\-]\$[0-9.,]+\s*)?"
            r"(\$[0-9.,]+|-)",
            text_blob,
            re.IGNORECASE,
        )
        if m_strip:
            keys_order = ["Ungraded", "Grade_7", "Grade_8", "Grade_9", "BGS_9_5", "PSA_10"]
            for k, raw_g in zip(keys_order, m_strip.groups()):
                v = _safe_float(raw_g, 0.0)
                if v > 0:
                    prices[k] = v

    if not prices:
        return None

    vol_m = re.search(r"volume:\s*([0-9]+\s+sales?\s+per\s+\w+|rare|[0-9]+\s+sale)", text_blob, re.IGNORECASE)
    vol_str = vol_m.group(1) if vol_m else "live_scp"
    raw_v = prices.get("Ungraded", 0.0)
    psa10_v = prices.get("PSA_10", 0.0)
    bgs95_v = prices.get("BGS_9_5", round(psa10_v * 0.65, 2) if psa10_v > 0 else 0.0)
    bgs10_v = prices.get("BGS_10", round(psa10_v * 1.35, 2) if psa10_v > 0 else 0.0)

    return {
        "Ungraded": f"{raw_v:.2f}" if raw_v > 0 else "",
        "Grade_7": f"{prices['Grade_7']:.2f}" if prices.get("Grade_7", 0) > 0 else "",
        "Grade_8": f"{prices['Grade_8']:.2f}" if prices.get("Grade_8", 0) > 0 else "",
        "Grade_9": f"{prices['Grade_9']:.2f}" if prices.get("Grade_9", 0) > 0 else "",
        "BGS_9_5": f"{bgs95_v:.2f}" if bgs95_v > 0 else "",
        "PSA_10": f"{psa10_v:.2f}" if psa10_v > 0 else "",
        "BGS_10": f"{bgs10_v:.2f}" if bgs10_v > 0 else "",
        "Sales_Volume": vol_str,
        "Source_URL": url,
    }


def _parse_sportscardspro_search_results(
    html_text: str,
    set_name: str,
    card_number: str,
    player_name: str,
    subset_name: str,
    headers: dict,
    exact_card_url: str = "",
) -> Optional[dict]:
    if BeautifulSoup is None or not html_text:
        return None
    soup = BeautifulSoup(html_text, "html.parser")
    target_cnum = str(card_number or "").strip().lstrip("#").lower()
    target_plr_tokens = [t.lower() for t in re.findall(r"[a-zA-Z]{3,}", strip_accents(str(player_name or "")))]
    target_sub = strip_accents(str(subset_name or "Base")).strip().lower()

    exact_candidates = []
    proxy_candidates = []

    for tr in soup.find_all("tr"):
        a_game = tr.find("a", href=re.compile(r"/game/", re.IGNORECASE))
        if not a_game:
            continue
        href = str(a_game.get("href", "")).strip()
        full_game_url = href if href.startswith("http") else f"{SPORTSCARDSPRO_BASE_URL}{href if href.startswith('/') else '/' + href}"

        match_type = _classify_sportscardspro_slug_match(
            full_game_url, set_name, subset_name, card_number, player_name
        )
        if match_type == "MISMATCH":
            continue

        title_cell = tr.find("td", class_="title") or a_game
        row_title = strip_accents(title_cell.get_text(" ", strip=True)).lower()

        if target_sub in ("", "base", "base set") and "[" in row_title and "]" in row_title:
            bracket_inside = re.findall(r"\[([^\]]+)\]", row_title)
            if any(b.strip() not in ("base", "rc", "rookie") for b in bracket_inside):
                continue

        price_cells = tr.find_all("td", class_=re.compile(r"price", re.IGNORECASE))
        p_vals = [_safe_float(td.get_text(" ", strip=True), 0.0) for td in price_cells[:3]] if price_cells else []
        inline_prices = {
            "Ungraded": p_vals[0] if len(p_vals) > 0 and p_vals[0] > 0 else 0.0,
            "Grade_9": p_vals[1] if len(p_vals) > 1 and p_vals[1] > 0 else 0.0,
            "PSA_10": p_vals[2] if len(p_vals) > 2 and p_vals[2] > 0 else 0.0,
        }
        has_inline_price = any(v > 0 for v in inline_prices.values())

        score = 0
        if target_cnum and re.search(rf"(?:#|\b){re.escape(target_cnum)}\b", row_title):
            score += 45
        matched_plr_toks = sum(1 for pt in target_plr_tokens if pt in row_title)
        if target_plr_tokens and matched_plr_toks == 0:
            continue
        score += matched_plr_toks * 20
        if has_inline_price:
            score += 15

        cand_info = {
            "url": full_game_url,
            "score": score,
            "inline_prices": inline_prices,
            "has_price": has_inline_price,
        }
        if match_type == "EXACT":
            exact_candidates.append(cand_info)
        elif match_type == "PROXY_COMP" and has_inline_price:
            proxy_candidates.append(cand_info)

    exact_candidates.sort(key=lambda x: x["score"], reverse=True)
    proxy_candidates.sort(key=lambda x: x["score"], reverse=True)

    resolved_exact_url = exact_candidates[0]["url"] if exact_candidates else exact_card_url

    if exact_candidates:
        best_ex = exact_candidates[0]
        try:
            g_resp = _adaptive_http_get("sportscardspro", best_ex["url"], headers=headers, timeout=10)
            if g_resp and g_resp.status_code == 200:
                parsed_full = _parse_sportscardspro_html(g_resp.text, url=best_ex["url"])
                if parsed_full:
                    parsed_full["Card_URL"] = best_ex["url"]
                    parsed_full["Comp_URL"] = ""
                    parsed_full["Source_URL"] = best_ex["url"]
                    return parsed_full
        except Exception:
            pass

        if best_ex["has_price"]:
            ip = best_ex["inline_prices"]
            raw_v, g9_v, psa10_v = ip["Ungraded"], ip["Grade_9"], ip["PSA_10"]
            return {
                "Ungraded": f"{raw_v:.2f}" if raw_v > 0 else "",
                "Grade_7": "",
                "Grade_8": "",
                "Grade_9": f"{g9_v:.2f}" if g9_v > 0 else "",
                "BGS_9_5": f"{psa10_v * 0.65:.2f}" if psa10_v > 0 else "",
                "PSA_10": f"{psa10_v:.2f}" if psa10_v > 0 else "",
                "BGS_10": f"{psa10_v * 1.35:.2f}" if psa10_v > 0 else "",
                "Sales_Volume": "Exact Match",
                "Card_URL": best_ex["url"],
                "Comp_URL": "",
                "Source_URL": best_ex["url"],
            }

    if proxy_candidates:
        best_px = proxy_candidates[0]
        px_slug_name = best_px["url"].rstrip("/").split("/")[-1]
        try:
            p_resp = _adaptive_http_get("sportscardspro", best_px["url"], headers=headers, timeout=10)
            if p_resp and p_resp.status_code == 200:
                parsed_px = _parse_sportscardspro_html(p_resp.text, url=best_px["url"])
                if parsed_px:
                    parsed_px["Card_URL"] = resolved_exact_url or exact_card_url
                    parsed_px["Comp_URL"] = best_px["url"]
                    parsed_px["Source_URL"] = resolved_exact_url or exact_card_url
                    parsed_px["Sales_Volume"] = f"Proxy Comp ({px_slug_name})"
                    return parsed_px
        except Exception:
            pass

        ip = best_px["inline_prices"]
        raw_v, g9_v, psa10_v = ip["Ungraded"], ip["Grade_9"], ip["PSA_10"]
        return {
            "Ungraded": f"{raw_v:.2f}" if raw_v > 0 else "",
            "Grade_7": "",
            "Grade_8": "",
            "Grade_9": f"{g9_v:.2f}" if g9_v > 0 else "",
            "BGS_9_5": f"{psa10_v * 0.65:.2f}" if psa10_v > 0 else "",
            "PSA_10": f"{psa10_v:.2f}" if psa10_v > 0 else "",
            "BGS_10": f"{psa10_v * 1.35:.2f}" if psa10_v > 0 else "",
            "Sales_Volume": f"Proxy Comp ({px_slug_name})",
            "Card_URL": resolved_exact_url or exact_card_url,
            "Comp_URL": best_px["url"],
            "Source_URL": resolved_exact_url or exact_card_url,
        }

    return None


def fetch_card_market_comps(
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
    print_run: str = "",
    fallback_raw_price: float = 2.00,
) -> dict:
    comp_key = build_comp_key(set_name, subset_name, card_number, player_name)
    direct_url = build_sportscardspro_url(set_name, subset_name, card_number, player_name, keep_literal_ampersand=True)
    alt_direct_url = build_sportscardspro_url(set_name, subset_name, card_number, player_name, keep_literal_ampersand=False)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    verified_exact_url = direct_url
    extracted = None

    for cand_u in dict.fromkeys([direct_url, alt_direct_url]):
        try:
            resp = _adaptive_http_get("sportscardspro", cand_u, headers=headers, timeout=10)
            if resp and resp.status_code == 200 and "Ungraded" in resp.text:
                if _is_valid_sportscardspro_url_for_subset(resp.url, set_name, subset_name, card_number, player_name):
                    verified_exact_url = resp.url
                    extracted = _parse_sportscardspro_html(resp.text, url=resp.url)
                    if extracted:
                        extracted["Card_URL"] = verified_exact_url
                        extracted["Comp_URL"] = ""
                        extracted["Source_URL"] = verified_exact_url
                        break
        except Exception:
            continue

    if extracted is None:
        first_player = str(player_name or "").split("/")[0].strip()
        q_parts = [set_name, f"#{str(card_number).lstrip('#')}", first_player]
        if subset_name and subset_name.lower() != "base":
            q_parts.append(subset_name)
        search_url = f"{SPORTSCARDSPRO_BASE_URL}/search-products?q={quote(' '.join(q_parts))}&type=prices"
        try:
            s_resp = _adaptive_http_get("sportscardspro", search_url, headers=headers, timeout=12, allow_redirects=True)
            if s_resp and s_resp.status_code == 200:
                if "/game/" in s_resp.url:
                    match_kind = _classify_sportscardspro_slug_match(
                        s_resp.url, set_name, subset_name, card_number, player_name
                    )
                    if match_kind == "EXACT":
                        verified_exact_url = s_resp.url
                        extracted = _parse_sportscardspro_html(s_resp.text, url=s_resp.url)
                        if extracted:
                            extracted["Card_URL"] = verified_exact_url
                            extracted["Comp_URL"] = ""
                            extracted["Source_URL"] = verified_exact_url
                    elif match_kind == "PROXY_COMP":
                        extracted = _parse_sportscardspro_html(s_resp.text, url=s_resp.url)
                        if extracted:
                            px_slug = s_resp.url.rstrip("/").split("/")[-1]
                            extracted["Card_URL"] = verified_exact_url
                            extracted["Comp_URL"] = s_resp.url
                            extracted["Source_URL"] = verified_exact_url
                            extracted["Sales_Volume"] = f"Proxy Comp ({px_slug})"
                else:
                    extracted = _parse_sportscardspro_search_results(
                        s_resp.text,
                        set_name,
                        card_number,
                        player_name,
                        subset_name,
                        headers,
                        exact_card_url=verified_exact_url,
                    )
        except Exception:
            extracted = None

    pr_clean = format_print_run(print_run)
    raw_val = _safe_float((extracted or {}).get("Ungraded"), 0.0)
    if raw_val <= 0:
        sub_up = str(subset_name or "Base").upper()
        if pr_clean == "1":
            raw_val = max(fallback_raw_price, 150.00)
        elif pr_clean.isdigit() and int(pr_clean) <= 10:
            raw_val = max(fallback_raw_price, 45.00)
        elif pr_clean.isdigit() and int(pr_clean) <= 50:
            raw_val = max(fallback_raw_price, 18.00)
        elif pr_clean.isdigit() and int(pr_clean) <= 199:
            raw_val = max(fallback_raw_price, 7.50)
        elif any(k in sub_up for k in ("AUTO", "RELIC", "SILVER PORTRAIT", "FOIL FILIGREE", "CHROME", "BLACK BORDER")):
            raw_val = max(fallback_raw_price, 4.00)
        else:
            raw_val = min(fallback_raw_price, 2.50) if fallback_raw_price > 25.0 else max(0.99, fallback_raw_price)

    g7_default = round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][7.0], raw_val + 2.00), 2)
    g8_default = round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][8.0], raw_val + 4.50), 2)
    g9_default = round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][9.0], raw_val * 1.45 + 7.50), 2)
    psa10_default = round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][10.0], raw_val * 2.50 + 18.00), 2)
    bgs95_default = round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["BGS"][9.5], psa10_default * 0.68), 2)
    bgs10_default = round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["BGS"][10.0], psa10_default * 1.35), 2)

    g7 = _safe_float((extracted or {}).get("Grade_7"), g7_default)
    g8 = _safe_float((extracted or {}).get("Grade_8"), g8_default)
    g9 = _safe_float((extracted or {}).get("Grade_9"), g9_default)
    psa10 = _safe_float((extracted or {}).get("PSA_10"), psa10_default)
    bgs95 = _safe_float((extracted or {}).get("BGS_9_5"), round(psa10 * 0.68, 2) if (extracted or {}).get("PSA_10") else bgs95_default)
    bgs10 = _safe_float((extracted or {}).get("BGS_10"), round(psa10 * 1.35, 2) if (extracted or {}).get("PSA_10") else bgs10_default)

    final_card_url = (extracted or {}).get("Card_URL") or verified_exact_url
    final_comp_url = (extracted or {}).get("Comp_URL", "")

    return {
        "Comp_Key": comp_key,
        "Set": str(set_name).strip(),
        "Subset": str(subset_name or "Base").strip(),
        "Card Number": str(card_number).strip().lstrip("#"),
        "Player": str(player_name).strip(),
        "Print Run": pr_clean,
        "Ungraded": f"{raw_val:.2f}",
        "Grade_7": f"{g7:.2f}",
        "Grade_8": f"{g8:.2f}",
        "Grade_9": f"{g9:.2f}",
        "BGS_9_5": f"{bgs95:.2f}",
        "PSA_10": f"{psa10:.2f}",
        "BGS_10": f"{bgs10:.2f}",
        "Sales_Volume": (extracted or {}).get("Sales_Volume", "Estimated (No sales on exact page)"),
        "Card_URL": final_card_url,
        "Comp_URL": final_comp_url,
        "Source_URL": final_card_url,
        "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def purge_mismatched_comps_and_recalculate_inventory(inv_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    comps_df = load_market_comps_cache()
    comps_by_key = {str(r["Comp_Key"]): r.to_dict() for _, r in comps_df.iterrows() if r.get("Comp_Key")}

    if inv_df is None or inv_df.empty:
        return inv_df, 0

    out = inv_df.copy()
    reset_count = 0
    tiers_data = load_grading_tiers_cache()
    settings = load_market_alert_settings()
    pricing_cfg = _load_pricing_strategy_settings()
    default_raw = float(RUNTIME_CONFIG.get("default_raw_price", 2.00))

    for row_idx, row in out.iterrows():
        r_dict = row.to_dict()
        ck = build_comp_key(
            r_dict.get("Set", ""),
            r_dict.get("Subset", "Base"),
            r_dict.get("Card Number", ""),
            r_dict.get("Player", ""),
        )
        comp_rec = comps_by_key.get(ck)
        sub_up = str(r_dict.get("Subset", "Base")).strip().upper()
        pr_s = format_print_run(r_dict.get("Print Run", ""))
        curr_raw = _safe_float(r_dict.get("Raw_Price"), default_raw)

        if comp_rec is None and ((sub_up in ("BASE", "BASE SET") and not pr_s and curr_raw > 35.0) or curr_raw > 100.0):
            r_dict["Raw_Price"] = f"{default_raw:.2f}"
            r_dict["PSA_9_Price"] = ""
            r_dict["BGS_9_5_Price"] = ""
            r_dict["PSA_10_Price"] = ""
            reset_count += 1

        roi_res = compute_tier_aware_roi_and_recommendation(
            r_dict,
            comp_row=comp_rec,
            tiers_data=tiers_data,
            min_grade_net_gain=float(settings.get("min_grade_net_gain", 15.0)),
            min_grade_roi_pct=float(settings.get("min_grade_roi_pct", 35.0)),
            pricing_cfg=pricing_cfg,
        )
        for k, v in roi_res.items():
            out.at[row_idx, k] = v

    record_collection_value_snapshot(out, persist_to_disk=True)
    return out, reset_count


# ==============================================================================
# 3. RECOMMENDATION ENGINE (WITH < 7.0 GRADE GUARD UNLESS SERIAL / SPECIAL CARD)
# ==============================================================================
def _load_pricing_strategy_settings() -> dict:
    defaults = {
        "market_markup_pct": 0.0,
        "make_offer_markup_pct": 25.0,
        "rookie_serial_bonus_pct": 0.0,
        "gem_mint_pregrade_bonus_pct": 0.0,
        "global_min_price_floor": 0.99,
        "target_min_net_profit_per_card": 0.50,
        "per_card_supplies_cost": 0.18,
        "per_order_packaging_cost": 0.35,
        "per_order_shipping_cost": 0.00,
        "marketplace_fee_pct": 13.25,
        "fixed_transaction_fee": 0.30,
        "computed_unit_cogs_and_overhead": 0.25,
    }
    if EXPENSES_PRICING_CONFIG_FILE.exists():
        try:
            with open(EXPENSES_PRICING_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "pricing_strategy" in data:
                defaults.update(data["pricing_strategy"])
        except Exception:
            pass
    return defaults


def is_serial_or_special_card(card_row: dict) -> bool:
    """
    Returns True if a card is serial-numbered (`Print Run` present / `#/N` / `1/1`) or
    otherwise a unique/special card (`Auto`, `Relic`, `Mem`, `SSP`, `SP`, `SuperFractor`,
    `Printing Plate`, `Golden Mirror`, `Case Hit`, `Rip Card`, `Wood`, `Metal`, `1/1`).
    """
    pr_str = format_print_run(card_row.get("Print Run") or card_row.get("Print_Run") or "")
    if pr_str:
        return True

    attrs_up = str(card_row.get("Attributes", "")).upper()
    if re.search(r"(#/\d+|1/1|\bAUTO\b|\bAU\b|\bMEM\b|\bREL\b|\bSSP\b|\bSP\b|\bHOF\b)", attrs_up):
        return True

    sub_up = str(card_row.get("Subset") or card_row.get("Subset_Parallel") or "").upper()
    special_keywords = (
        "AUTO", "RELIC", "PATCH", "JERSEY", "FRAMED", "SUPERFRACTOR",
        "FOILFRACTOR", "PRINTING PLATE", "GOLDEN MIRROR", "TRUE PHOTO",
        "SSP", "CASE HIT", "HOME FIELD ADVANTAGE", "HEAVY LUMBER",
        "RIP CARD", "WOOD", "METAL", "SILK", "CLOTH", "1/1", "BLACK FINITE",
        "GOLD VINYL", "BOOKLET", "CUT SIGNATURE",
    )
    return any(kw in sub_up for kw in special_keywords)


def compute_tier_aware_roi_and_recommendation(
    card_row: dict,
    comp_row: Optional[dict] = None,
    tiers_data: Optional[dict] = None,
    min_grade_net_gain: float = 15.0,
    min_grade_roi_pct: float = 35.0,
    pricing_cfg: Optional[dict] = None,
) -> dict:
    """
    Recommendation Engine:
      - Calculates Raw_Price, Min_Sale_Price, Rec_Sale_Price, PSA/BGS Comps, and Net EV.
      - Enforces the < 7.0 Grade Guard: NEVER recommends grading (`GRADE PSA`, `GRADE BGS`,
        or `PC SLAB`) for any card whose estimated grade (`max(Est_PSA, Est_BGS)`) is < 7.0
        UNLESS `is_serial_or_special_card(card_row)` is True AND Net Gain > $0.
    """
    if tiers_data is None:
        tiers_data = load_grading_tiers_cache()
    if pricing_cfg is None:
        pricing_cfg = _load_pricing_strategy_settings()

    default_raw = float(RUNTIME_CONFIG.get("default_raw_price", 2.00))
    raw_val = _safe_float(
        (comp_row or {}).get("Ungraded") or card_row.get("Raw_Price"),
        default=default_raw,
    )
    if raw_val <= 0:
        raw_val = default_raw

    est_phys = float(
        np.clip(
            round(
                _safe_float(
                    card_row.get("Est_Grade") or card_row.get("Est_BGS") or card_row.get("Est_PSA"),
                    9.0,
                )
                * 2.0
            )
            / 2.0,
            1.0,
            10.0,
        )
    )
    est_psa_grade = float(
        np.clip(
            round(_safe_float(card_row.get("Est_PSA") or est_phys, 9.0) * 2.0) / 2.0,
            1.0,
            10.0,
        )
    )
    est_bgs = float(
        np.clip(
            round(_safe_float(card_row.get("Est_BGS") or est_phys, 9.0) * 2.0) / 2.0,
            1.0,
            10.0,
        )
    )
    highest_est_grade = max(est_phys, est_psa_grade, est_bgs)

    psa9_comp = _safe_float(
        (comp_row or {}).get("Grade_9") or card_row.get("PSA_9_Price"),
        round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][9.0], raw_val * 1.45 + 7.50), 2),
    )
    psa10_comp = _safe_float(
        (comp_row or {}).get("PSA_10") or card_row.get("PSA_10_Price"),
        round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][10.0], raw_val * 2.50 + 18.00), 2),
    )
    bgs95_comp = _safe_float(
        (comp_row or {}).get("BGS_9_5") or card_row.get("BGS_9_5_Price"),
        round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["BGS"][9.5], psa10_comp * 0.68), 2),
    )
    bgs10_comp = _safe_float(
        (comp_row or {}).get("BGS_10"),
        round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["BGS"][10.0], psa10_comp * 1.35), 2),
    )
    g8_comp = _safe_float(
        (comp_row or {}).get("Grade_8"),
        round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][8.0], raw_val + 4.50), 2),
    )
    g7_comp = _safe_float(
        (comp_row or {}).get("Grade_7"),
        round(max(raw_val * DEFAULT_GRADE_MULTIPLIERS["PSA"][7.0], raw_val + 2.00), 2),
    )

    def _grade_val_lookup(grader: str, g_num: float) -> float:
        if g_num >= 10.0:
            return psa10_comp if grader == "PSA" else bgs10_comp
        if g_num == 9.5:
            return bgs95_comp
        if g_num == 9.0:
            return psa9_comp
        if g_num in (8.5, 8.0):
            return g8_comp if g_num == 8.0 else round(0.5 * (g8_comp + psa9_comp), 2)
        if g_num in (7.5, 7.0):
            return g7_comp
        mult_map = DEFAULT_GRADE_MULTIPLIERS.get(grader, {})
        mult = mult_map.get(g_num, 0.70)
        return raw_val * mult

    psa_dist = PSA_PROB_MATRIX.get(est_phys, PSA_PROB_MATRIX[9.0])
    gross_ev_psa = sum(prob * _grade_val_lookup("PSA", g) for g, prob in psa_dist.items())
    direct_psa_slab_val = _grade_val_lookup("PSA", est_psa_grade)
    psa_top_val = max(gross_ev_psa, direct_psa_slab_val)
    psa_tier = resolve_grading_tier_fee("PSA", declared_value=psa_top_val, tiers_data=tiers_data)
    net_ev_psa = gross_ev_psa - psa_tier["price"]
    gain_psa = net_ev_psa - raw_val
    roi_psa = (gain_psa / max(1.0, raw_val + psa_tier["price"])) * 100.0

    bgs_dist = BGS_PROB_MATRIX.get(est_bgs, BGS_PROB_MATRIX[9.0])
    gross_ev_bgs = sum(prob * _grade_val_lookup("BGS", g) for g, prob in bgs_dist.items())
    direct_bgs_slab_val = _grade_val_lookup("BGS", est_bgs)
    bgs_top_val = max(gross_ev_bgs, direct_bgs_slab_val)
    bgs_tier = resolve_grading_tier_fee("BGS", declared_value=bgs_top_val, tiers_data=tiers_data)
    net_ev_bgs = gross_ev_bgs - bgs_tier["price"]
    gain_bgs = net_ev_bgs - raw_val
    roi_bgs = (gain_bgs / max(1.0, raw_val + bgs_tier["price"])) * 100.0

    if gain_psa >= gain_bgs:
        best_grader = "PSA"
        max_gain = gain_psa
        best_roi = roi_psa
        best_tier_lbl = f"PSA {psa_tier['tier']} (${psa_tier['price']:.0f})"
    else:
        best_grader = "BGS"
        max_gain = gain_bgs
        best_roi = roi_bgs
        best_tier_lbl = f"BGS {bgs_tier['tier']} (${bgs_tier['price']:.0f})"

    unit_cogs = float(pricing_cfg.get("computed_unit_cogs_and_overhead", 0.25))
    set_cogs_map = pricing_cfg.get("per_set_unit_cogs", {})
    card_set_name = str(card_row.get("Set", "")).strip()
    if isinstance(set_cogs_map, dict) and card_set_name in set_cogs_map:
        unit_cogs = float(set_cogs_map[card_set_name])

    supplies_cost = (
        float(pricing_cfg.get("per_card_supplies_cost", 0.18))
        + float(pricing_cfg.get("per_order_packaging_cost", 0.35))
        + float(pricing_cfg.get("per_order_shipping_cost", 0.00))
    )
    fixed_fee = float(pricing_cfg.get("fixed_transaction_fee", 0.30))
    fee_rate = min(0.50, max(0.0, float(pricing_cfg.get("marketplace_fee_pct", 13.25)) / 100.0))
    min_profit = float(pricing_cfg.get("target_min_net_profit_per_card", 0.50))
    global_floor = float(pricing_cfg.get("global_min_price_floor", 0.99))

    break_even_price = (unit_cogs + supplies_cost + fixed_fee) / max(0.10, 1.0 - fee_rate)
    min_sale_price = max(global_floor, round(break_even_price + (min_profit / max(0.10, 1.0 - fee_rate)), 2))

    hold_tag = str(card_row.get("Hold_Tag", "For Sale")).strip() or "For Sale"
    base_markup_pct = float(pricing_cfg.get("market_markup_pct", 0.0))
    offer_markup_pct = float(pricing_cfg.get("make_offer_markup_pct", 25.0))

    effective_markup_pct = max(base_markup_pct, offer_markup_pct) if "Make Me an Offer" in hold_tag else base_markup_pct

    pr_str = format_print_run(card_row.get("Print Run") or card_row.get("Print_Run") or "")
    sub_str = str(card_row.get("Subset") or card_row.get("Subset_Parallel") or "Base").strip()
    if pr_str or sub_str.upper() not in ("BASE", "BASE SET"):
        effective_markup_pct += float(pricing_cfg.get("rookie_serial_bonus_pct", 0.0))
    if max(est_psa_grade, est_bgs) >= 9.5:
        effective_markup_pct += float(pricing_cfg.get("gem_mint_pregrade_bonus_pct", 0.0))

    target_market_price = round(raw_val * (1.0 + effective_markup_pct / 100.0), 2)
    if "Make Me an Offer" in hold_tag:
        target_market_price = max(target_market_price, round(gross_ev_psa * 0.55, 2))

    rec_sale_price = max(min_sale_price, target_market_price)

    # STRICT < 7.0 GRADE GUARD:
    # Do NOT recommend grading for any card with an estimated grade < 7.0 unless it is
    # a serial-numbered card or a unique/special card (Auto, Relic, 1/1, SSP, etc.)
    is_special = is_serial_or_special_card(card_row)
    eligible_for_grading = (highest_est_grade >= 7.0) and (
        highest_est_grade >= 8.5 or is_special
    ) or (highest_est_grade < 7.0 and is_special)

    if "Personal Collection" in hold_tag or str(card_row.get("Status", "")) == "PC / Hold":
        if eligible_for_grading and max_gain >= min_grade_net_gain and (highest_est_grade >= 9.5 or is_special):
            action = f"PC SLAB {best_grader} (+${max_gain:.2f} | Est Slab ${max(gross_ev_psa, gross_ev_bgs):.2f})"
        else:
            action = f"PC HOLD (Est Slab ${max(gross_ev_psa, gross_ev_bgs):.2f})"
    elif eligible_for_grading and max_gain >= min_grade_net_gain and best_roi >= min_grade_roi_pct:
        action = f"GRADE {best_grader} (+${max_gain:.2f} Net | {best_tier_lbl})"
    elif rec_sale_price >= 2.50:
        action = f"LIST RAW (${rec_sale_price:.2f} | Min ${min_sale_price:.2f})"
    else:
        action = f"BULK / LOT (${rec_sale_price:.2f} | Min ${min_sale_price:.2f})"

    return {
        "Raw_Price": f"{raw_val:.2f}",
        "Min_Sale_Price": f"{min_sale_price:.2f}",
        "Rec_Sale_Price": f"{rec_sale_price:.2f}",
        "PSA_9_Price": f"{psa9_comp:.2f}",
        "BGS_9_5_Price": f"{bgs95_comp:.2f}",
        "PSA_10_Price": f"{psa10_comp:.2f}",
        "Est_Graded_PSA": f"{gross_ev_psa:.2f}",
        "Est_Graded_BGS": f"{gross_ev_bgs:.2f}",
        "EV_PSA": f"{net_ev_psa:.2f}",
        "EV_BGS": f"{net_ev_bgs:.2f}",
        "Best_Grader": best_grader if (eligible_for_grading and max_gain > 0) else "RAW",
        "Max_Net_Gain": f"{max_gain:+.2f}",
        "Recommended_Action": action,
    }


# ==============================================================================
# 4. DAILY VALUATION REFRESH, COLLECTION HISTORY & MARKET ALERTS
# ==============================================================================
def load_market_alert_settings() -> dict:
    ensure_directories()
    default_s = {
        "min_grade_net_gain": 15.0,
        "min_grade_roi_pct": 35.0,
        "price_spike_pct": 25.0,
        "email_enabled": False,
        "delivery_method": "ntfy_topic",
        "ntfy_topic": "tabulas_mroux_cards",
        "webhook_url": "",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "michael.j.roux@gmail.com",
        "smtp_app_password": "",
        "recipient_email": "michael.j.roux@gmail.com",
    }
    if MARKET_SETTINGS_FILE.exists():
        try:
            with open(MARKET_SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                default_s.update(loaded)
                if not str(default_s.get("recipient_email", "")).strip():
                    default_s["recipient_email"] = "michael.j.roux@gmail.com"
                if not str(default_s.get("smtp_user", "")).strip():
                    default_s["smtp_user"] = "michael.j.roux@gmail.com"
                if not str(default_s.get("ntfy_topic", "")).strip():
                    default_s["ntfy_topic"] = "tabulas_mroux_cards"
        except Exception:
            pass
    return default_s


def save_market_alert_settings(settings: dict) -> dict:
    ensure_directories()
    curr = load_market_alert_settings()
    curr.update(settings)
    with open(MARKET_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(curr, f, indent=2)
    return curr


def load_market_alerts() -> list[dict]:
    ensure_directories()
    if not MARKET_ALERTS_FILE.exists():
        return []
    try:
        with open(MARKET_ALERTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def send_market_alert_email(alerts: list[dict], settings: Optional[dict] = None) -> tuple[bool, str]:
    if not alerts:
        return False, "No new alerts to send."
    cfg = settings or load_market_alert_settings()
    method = str(cfg.get("delivery_method", "ntfy_topic")).strip()
    recipient = str(cfg.get("recipient_email", "michael.j.roux@gmail.com")).strip()

    subject_str = f"Tabulas Market Alert: {len(alerts)} Card Recommendation / Price Update(s)"
    lines = [
        f"Tabulas detected {len(alerts)} market / grading recommendation change(s) on {datetime.now().strftime('%Y-%m-%d %H:%M')}:\n"
    ]
    for a in alerts[:40]:
        lines.append(
            f"- [{a.get('alert_type')}] SKU {a.get('sku')} ({a.get('card_desc')}): "
            f"{a.get('old_action')} -> {a.get('new_action')} | Raw: ${a.get('old_price')} -> ${a.get('new_price')}"
        )
    body_text = "\n".join(lines)

    if method == "ntfy_topic":
        topic = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(cfg.get("ntfy_topic", "tabulas_mroux_cards")).strip())
        if not topic:
            topic = "tabulas_mroux_cards"
        headers = {
            "Title": subject_str,
            "Priority": "high",
            "Tags": "chart_with_upwards_trend,card_index",
        }
        try:
            resp = requests.post(
                f"https://ntfy.sh/{topic}",
                data=body_text.encode("utf-8"),
                headers=headers,
                timeout=12,
            )
            if resp.status_code == 200:
                return (
                    True,
                    f"Sent instant alert to https://ntfy.sh/{topic} (Open that link on phone/PC or subscribe in the free ntfy app — zero password required!).",
                )
            return False, f"ntfy.sh returned HTTP {resp.status_code}: {resp.text[:160]}"
        except Exception as e:
            return False, f"ntfy.sh request error: {e}"

    if method == "windows_outlook":
        if not recipient:
            return False, "Recipient email is empty."
        ps_script = (
            "$ol = New-Object -ComObject Outlook.Application; "
            "$mail = $ol.CreateItem(0); "
            f"$mail.To = '{recipient.replace(chr(39), '')}'; "
            f"$mail.Subject = '{subject_str.replace(chr(39), '')}'; "
            f"$mail.Body = {json.dumps(body_text)}; "
            "$mail.Send();"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0:
                return True, f"Sent alert email to {recipient} via local Windows Outlook!"
            return False, f"Windows Outlook error (ensure classic Outlook is signed in): {res.stderr.strip() or res.stdout.strip()}"
        except Exception as e:
            return False, f"Windows Outlook launch error: {e}"

    if method == "webhook":
        wh_url = str(cfg.get("webhook_url", "")).strip()
        if not wh_url:
            return False, "Webhook URL is empty. Paste a Discord, Slack, or Make/Zapier webhook URL first."
        try:
            payload = {
                "content": f"**{subject_str}**\n```\n{body_text[:1800]}\n```",
                "text": f"*{subject_str}*\n{body_text}",
                "subject": subject_str,
                "recipient": recipient,
                "alerts": alerts[:40],
            }
            resp = requests.post(wh_url, json=payload, timeout=12)
            if 200 <= resp.status_code < 300:
                return True, f"Delivered alert digest ({len(alerts)} alert(s)) to Webhook!"
            return False, f"Webhook returned HTTP {resp.status_code}: {resp.text[:160]}"
        except Exception as e:
            return False, f"Webhook error: {e}"

    if not cfg.get("smtp_user") or not recipient or not cfg.get("smtp_app_password"):
        return (
            False,
            "Gmail App Password is not set. Either switch Delivery Method to 'Passwordless Push/Browser (ntfy.sh)' or enable 2-Step Verification on your Google Account first.",
        )

    msg = EmailMessage()
    msg["Subject"] = subject_str
    msg["From"] = cfg["smtp_user"]
    msg["To"] = recipient
    msg.set_content(body_text)

    try:
        with smtplib.SMTP(cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 587)), timeout=15) as server:
            server.starttls()
            server.login(cfg["smtp_user"], cfg.get("smtp_app_password", ""))
            server.send_message(msg)
        return True, f"Sent email digest ({len(alerts)} alert(s)) to {recipient} via Gmail SMTP."
    except Exception as e:
        return False, f"SMTP error: {e}"


def refresh_inventory_market_valuations(
    inv_df: pd.DataFrame,
    fetch_live_web_comps: bool = True,
    refresh_grading_tiers: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[pd.DataFrame, list[dict], dict]:
    ensure_directories()
    if inv_df is None or inv_df.empty:
        return inv_df, [], {}

    settings = load_market_alert_settings()
    tiers_data = (
        refresh_dugout_vault_grading_tiers()
        if refresh_grading_tiers
        else load_grading_tiers_cache()
    )
    comps_df = load_market_comps_cache()
    comps_by_key = {str(r["Comp_Key"]): r.to_dict() for _, r in comps_df.iterrows() if r.get("Comp_Key")}

    out = inv_df.copy()
    if "Hold_Tag" not in out.columns:
        out["Hold_Tag"] = "For Sale"
    if "Rec_Sale_Price" not in out.columns:
        out["Rec_Sale_Price"] = out.get("Raw_Price", "2.00")

    unique_cards = {}
    for _, row in out.iterrows():
        if str(row.get("Status", "")).strip().lower() == "sold":
            continue
        c_key = build_comp_key(
            row.get("Set", ""),
            row.get("Subset", "Base"),
            row.get("Card Number", ""),
            row.get("Player", ""),
        )
        if c_key not in unique_cards:
            unique_cards[c_key] = row.to_dict()

    today_prefix = datetime.now().strftime("%Y-%m-%d")
    total_unique = max(1, len(unique_cards))

    for idx_u, (c_key, sample_row) in enumerate(unique_cards.items(), 1):
        existing_comp = comps_by_key.get(c_key)
        already_fresh_today = bool(
            existing_comp and str(existing_comp.get("Last_Updated", "")).startswith(today_prefix)
        )
        if fetch_live_web_comps and not already_fresh_today:
            comp_rec = fetch_card_market_comps(
                set_name=sample_row.get("Set", ""),
                subset_name=sample_row.get("Subset", "Base"),
                card_number=sample_row.get("Card Number", ""),
                player_name=sample_row.get("Player", ""),
                print_run=sample_row.get("Print Run", ""),
                fallback_raw_price=_safe_float(sample_row.get("Raw_Price"), 2.00),
            )
            comps_by_key[c_key] = comp_rec

        if progress_callback:
            progress_callback(
                idx_u,
                total_unique,
                f"Valued [{idx_u}/{total_unique}] {sample_row.get('Set','')} #{sample_row.get('Card Number','')} {sample_row.get('Player','')}",
            )

    save_market_comps_cache(pd.DataFrame(list(comps_by_key.values())))

    new_alerts = []
    existing_alerts = load_market_alerts()
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    pricing_cfg = _load_pricing_strategy_settings()

    for row_idx, row in out.iterrows():
        if str(row.get("Status", "")).strip().lower() == "sold":
            continue
        r_dict = row.to_dict()
        c_key = build_comp_key(
            r_dict.get("Set", ""),
            r_dict.get("Subset", "Base"),
            r_dict.get("Card Number", ""),
            r_dict.get("Player", ""),
        )
        comp_rec = comps_by_key.get(c_key)

        old_action = str(r_dict.get("Recommended_Action", "")).strip()
        old_raw = _safe_float(r_dict.get("Raw_Price"), 2.00)

        roi_res = compute_tier_aware_roi_and_recommendation(
            r_dict,
            comp_row=comp_rec,
            tiers_data=tiers_data,
            min_grade_net_gain=float(settings.get("min_grade_net_gain", 15.0)),
            min_grade_roi_pct=float(settings.get("min_grade_roi_pct", 35.0)),
            pricing_cfg=pricing_cfg,
        )
        for k, v in roi_res.items():
            out.at[row_idx, k] = v

        new_action = roi_res["Recommended_Action"]
        new_raw = _safe_float(roi_res["Raw_Price"], old_raw)

        old_cat = old_action.split(" ")[0] if old_action else ""
        new_cat = new_action.split(" ")[0] if new_action else ""
        pct_move = ((new_raw - old_raw) / max(0.50, old_raw)) * 100.0 if old_raw > 0 else 0.0

        if (old_cat and new_cat and old_cat != new_cat) or abs(pct_move) >= float(settings.get("price_spike_pct", 25.0)):
            alert_type = "RECOMMENDATION_FLIP" if old_cat != new_cat else ("PRICE_SURGE" if pct_move > 0 else "PRICE_DROP")
            new_alerts.append({
                "timestamp": now_ts,
                "alert_type": alert_type,
                "sku": str(r_dict.get("SKU", "")),
                "card_desc": f"{r_dict.get('Set','')} #{r_dict.get('Card Number','')} {r_dict.get('Player','')} [{r_dict.get('Subset','Base')}]",
                "old_action": old_action or "N/A",
                "new_action": new_action,
                "old_price": f"{old_raw:.2f}",
                "new_price": f"{new_raw:.2f}",
                "pct_change": f"{pct_move:+.1f}%",
            })

    if new_alerts:
        combined_alerts = (new_alerts + existing_alerts)[:250]
        try:
            with open(MARKET_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(combined_alerts, f, indent=2)
        except Exception:
            pass
        if settings.get("email_enabled"):
            send_market_alert_email(new_alerts, settings=settings)

    summary = record_collection_value_snapshot(out, persist_to_disk=True)
    return out, new_alerts, summary


def record_collection_value_snapshot(inv_df: pd.DataFrame, persist_to_disk: bool = True) -> dict:
    ensure_directories()
    if inv_df is None or inv_df.empty:
        return {
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Total_Cards": 0,
            "Unique_Cards": 0,
            "Total_Raw_Value": 0.0,
            "Total_Rec_Sale_Value": 0.0,
            "Total_Optimal_EV": 0.0,
            "Grade_Candidates_Count": 0,
        }

    in_stock = inv_df[inv_df["Status"] != "Sold"].copy()
    raw_vals = pd.to_numeric(in_stock.get("Raw_Price", 0.0), errors="coerce").fillna(0.0)
    rec_vals = pd.to_numeric(in_stock.get("Rec_Sale_Price", raw_vals), errors="coerce").fillna(raw_vals)
    ev_psa = pd.to_numeric(in_stock.get("EV_PSA", 0.0), errors="coerce").fillna(0.0)
    ev_bgs = pd.to_numeric(in_stock.get("EV_BGS", 0.0), errors="coerce").fillna(0.0)

    optimal_vals = np.maximum(raw_vals, np.maximum(ev_psa, ev_bgs))
    grade_candidates = int(in_stock["Recommended_Action"].astype(str).str.startswith("GRADE").sum())

    snap = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Total_Cards": int(len(in_stock)),
        "Unique_Cards": int(len(in_stock.drop_duplicates(subset=["Set", "Subset", "Card Number", "Player"]))),
        "Total_Raw_Value": round(float(raw_vals.sum()), 2),
        "Total_Rec_Sale_Value": round(float(rec_vals.sum()), 2),
        "Total_Optimal_EV": round(float(optimal_vals.sum()), 2),
        "Grade_Candidates_Count": grade_candidates,
    }

    if persist_to_disk or not COLLECTION_HISTORY_FILE.exists():
        hist_df = pd.DataFrame([snap])
        if COLLECTION_HISTORY_FILE.exists():
            try:
                old_h = pd.read_csv(COLLECTION_HISTORY_FILE, dtype=str, keep_default_na=False)
                if "Date" in old_h.columns:
                    old_h = old_h[old_h["Date"] != snap["Date"]].dropna(how="all")
                if not old_h.empty:
                    hist_df = pd.concat([old_h, hist_df.astype(str)], ignore_index=True)
            except Exception:
                pass
        try:
            hist_df.to_csv(COLLECTION_HISTORY_FILE, index=False, encoding="utf-8-sig")
        except Exception:
            pass
    return snap


# ==============================================================================
# 5. 5-MODE SET COMPLETION & PROGRESS ENGINE (WITH PRINT-RUN FILTER)
# ==============================================================================
def _classify_checklist_rows_for_set(set_chk_df: pd.DataFrame) -> pd.DataFrame:
    df = set_chk_df.copy()
    df["clean_cnum"] = df["Card Number"].astype(str).str.strip().str.lstrip("#")
    df["clean_sub"] = df["Subset"].astype(str).str.strip().replace("", "Base")
    df["pr_num"] = pd.to_numeric(df["Print Run"].map(format_print_run), errors="coerce")

    base_cnums = set(
        df[df["clean_sub"].str.upper().isin(("BASE", "BASE SET"))]["clean_cnum"].unique()
    )
    insert_root_subs_by_cnum = {}
    non_base_df = df[~df["clean_cnum"].isin(base_cnums)]
    for cn, grp in non_base_df.groupby("clean_cnum"):
        subs = sorted(grp["clean_sub"].unique(), key=lambda s: (len(s), s))
        if subs:
            insert_root_subs_by_cnum[cn] = subs[0]

    df["is_base_root"] = df["clean_sub"].str.upper().isin(("BASE", "BASE SET"))
    df["is_base_family"] = df["clean_cnum"].isin(base_cnums)
    df["is_insert_root"] = [
        (cn not in base_cnums and sub == insert_root_subs_by_cnum.get(cn))
        for cn, sub in zip(df["clean_cnum"], df["clean_sub"])
    ]
    return df


def compute_set_completion_metrics(
    master_chk_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    set_name: str,
    completion_mode: str = SET_COMPLETION_MODES[0],
    exclude_limited_print_runs: bool = False,
    min_print_run_threshold: int = 0,
    include_pc_cards: bool = True,
) -> dict:
    if master_chk_df is None or master_chk_df.empty or not set_name:
        return {
            "set_name": set_name,
            "mode": completion_mode,
            "owned_count": 0,
            "total_count": 0,
            "completion_pct": 0.0,
            "missing_df": pd.DataFrame(),
            "owned_df": pd.DataFrame(),
        }

    set_slice = master_chk_df[master_chk_df["Set"] == set_name].copy()
    if set_slice.empty:
        return {
            "set_name": set_name,
            "mode": completion_mode,
            "owned_count": 0,
            "total_count": 0,
            "completion_pct": 0.0,
            "missing_df": pd.DataFrame(),
            "owned_df": pd.DataFrame(),
        }

    tagged_chk = _classify_checklist_rows_for_set(set_slice)

    if exclude_limited_print_runs:
        if min_print_run_threshold > 0:
            tagged_chk = tagged_chk[
                tagged_chk["pr_num"].isna() | (tagged_chk["pr_num"] >= int(min_print_run_threshold))
            ]
        else:
            tagged_chk = tagged_chk[tagged_chk["pr_num"].isna()]

    inv_slice = inv_df[(inv_df["Set"] == set_name) & (inv_df["Status"] != "Sold")].copy() if not inv_df.empty else pd.DataFrame()
    if not inv_slice.empty and not include_pc_cards and "Hold_Tag" in inv_slice.columns:
        inv_slice = inv_slice[~inv_slice["Hold_Tag"].astype(str).str.contains("Personal Collection", case=False, na=False)]

    owned_cnums_all = set()
    owned_exact_pairs = set()
    if not inv_slice.empty:
        for cn_v, sub_v in zip(inv_slice["Card Number"], inv_slice["Subset"]):
            cn_clean = str(cn_v).strip().lstrip("#")
            owned_cnums_all.add(norm(cn_clean))
            owned_exact_pairs.add((norm(cn_clean), canonical_subset_key(str(sub_v), set_name)))

    mode_code = str(completion_mode)[0]
    if mode_code == "1":
        target_df = tagged_chk[tagged_chk["is_base_root"]].drop_duplicates(subset=["clean_cnum"]).copy()
        is_owned = [
            (norm(cn), canonical_subset_key("Base", set_name)) in owned_exact_pairs
            for cn in target_df["clean_cnum"]
        ]
    elif mode_code == "2":
        target_df = tagged_chk[tagged_chk["is_insert_root"]].drop_duplicates(subset=["clean_cnum", "clean_sub"]).copy()
        is_owned = [
            (norm(cn), canonical_subset_key(sub, set_name)) in owned_exact_pairs
            for cn, sub in zip(target_df["clean_cnum"], target_df["clean_sub"])
        ]
    elif mode_code == "3":
        base_family_df = tagged_chk[tagged_chk["is_base_family"]]
        owned_base_family_cnums = {
            norm(cn)
            for cn, sub in zip(base_family_df["clean_cnum"], base_family_df["clean_sub"])
            if (norm(cn), canonical_subset_key(sub, set_name)) in owned_exact_pairs
        }
        target_df = tagged_chk[tagged_chk["is_base_root"]].drop_duplicates(subset=["clean_cnum"]).copy()
        is_owned = [norm(cn) in owned_base_family_cnums for cn in target_df["clean_cnum"]]
    elif mode_code == "4":
        target_df = (
            tagged_chk[tagged_chk["is_base_root"] | tagged_chk["is_insert_root"]]
            .drop_duplicates(subset=["clean_cnum"])
            .copy()
        )
        is_owned = [norm(cn) in owned_cnums_all for cn in target_df["clean_cnum"]]
    else:
        target_df = tagged_chk.drop_duplicates(subset=["clean_cnum", "clean_sub", "Player"]).copy()
        is_owned = [
            (norm(cn), canonical_subset_key(sub, set_name)) in owned_exact_pairs
            for cn, sub in zip(target_df["clean_cnum"], target_df["clean_sub"])
        ]

    target_df["Owned"] = is_owned
    cols_keep = ["Set", "Subset", "Card Number", "Player", "Team", "Print Run", "Attributes", "Owned"]
    target_df = target_df[[c for c in cols_keep if c in target_df.columns]]

    owned_df = target_df[target_df["Owned"] == True].reset_index(drop=True)
    missing_df = target_df[target_df["Owned"] != True].reset_index(drop=True)

    tot = len(target_df)
    own = len(owned_df)
    pct = round((own / float(tot)) * 100.0, 2) if tot > 0 else 0.0

    return {
        "set_name": set_name,
        "mode": completion_mode,
        "owned_count": own,
        "total_count": tot,
        "missing_count": len(missing_df),
        "completion_pct": pct,
        "missing_df": missing_df,
        "owned_df": owned_df,
    }


# ==============================================================================
# 6. CARDS-TO-BUY PLANNER (SET, INSERT & PLAYER/CARD RAINBOW BUILDER)
# ==============================================================================
def generate_cards_to_buy_list(
    master_chk_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    set_name: str,
    target_type: str = "Set Completion",
    completion_mode: str = SET_COMPLETION_MODES[0],
    subset_filter: str = "",
    rainbow_card_number: str = "",
    exclude_limited_print_runs: bool = False,
    min_print_run_threshold: int = 0,
    max_budget_per_card: float = 0.0,
) -> tuple[pd.DataFrame, dict]:
    comps_df = load_market_comps_cache()
    comps_by_key = {str(r["Comp_Key"]): r.to_dict() for _, r in comps_df.iterrows() if r.get("Comp_Key")}

    if target_type == "Card / Player Rainbow" and rainbow_card_number:
        cn_clean = str(rainbow_card_number).strip().lstrip("#")
        set_slice = master_chk_df[
            (master_chk_df["Set"] == set_name)
            & (master_chk_df["Card Number"].map(norm) == norm(cn_clean))
        ].copy()
        if exclude_limited_print_runs:
            pr_nums = pd.to_numeric(set_slice["Print Run"].map(format_print_run), errors="coerce")
            if min_print_run_threshold > 0:
                set_slice = set_slice[pr_nums.isna() | (pr_nums >= int(min_print_run_threshold))]
            else:
                set_slice = set_slice[pr_nums.isna()]

        inv_slice = inv_df[(inv_df["Set"] == set_name) & (inv_df["Status"] != "Sold")] if not inv_df.empty else pd.DataFrame()
        owned_subs = {
            canonical_subset_key(str(s), set_name)
            for cn, s in zip(inv_slice.get("Card Number", []), inv_slice.get("Subset", []))
            if norm(str(cn).lstrip("#")) == norm(cn_clean)
        }
        set_slice["Owned"] = [
            canonical_subset_key(str(s), set_name) in owned_subs for s in set_slice["Subset"]
        ]
        missing_df = set_slice[set_slice["Owned"] != True].copy()
        owned_count = int((set_slice["Owned"] == True).sum())
        total_count = len(set_slice)
    elif target_type == "Specific Subset / Insert" and subset_filter:
        set_slice = master_chk_df[
            (master_chk_df["Set"] == set_name)
            & (master_chk_df["Subset"].astype(str).str.lower() == subset_filter.strip().lower())
        ].copy()
        inv_slice = inv_df[(inv_df["Set"] == set_name) & (inv_df["Status"] != "Sold")] if not inv_df.empty else pd.DataFrame()
        target_canon = canonical_subset_key(subset_filter, set_name)
        owned_cnums = {
            norm(str(cn).lstrip("#"))
            for cn, s in zip(inv_slice.get("Card Number", []), inv_slice.get("Subset", []))
            if canonical_subset_key(str(s), set_name) == target_canon
        }
        set_slice["Owned"] = [norm(str(cn).lstrip("#")) in owned_cnums for cn in set_slice["Card Number"]]
        missing_df = set_slice[set_slice["Owned"] != True].copy()
        owned_count = int((set_slice["Owned"] == True).sum())
        total_count = len(set_slice)
    else:
        comp_res = compute_set_completion_metrics(
            master_chk_df,
            inv_df,
            set_name=set_name,
            completion_mode=completion_mode,
            exclude_limited_print_runs=exclude_limited_print_runs,
            min_print_run_threshold=min_print_run_threshold,
        )
        missing_df = comp_res["missing_df"].copy()
        owned_count = comp_res["owned_count"]
        total_count = comp_res["total_count"]

    if missing_df.empty:
        return pd.DataFrame(), {
            "owned_count": owned_count,
            "total_count": total_count,
            "missing_count": 0,
            "estimated_total_cost": 0.0,
        }

    est_prices = []
    buy_links = []
    for _, r in missing_df.iterrows():
        c_key = build_comp_key(r["Set"], r["Subset"], r["Card Number"], r["Player"])
        cached_c = comps_by_key.get(c_key)
        if cached_c and _safe_float(cached_c.get("Ungraded"), 0.0) > 0:
            p_val = _safe_float(cached_c["Ungraded"], 1.50)
        else:
            pr_s = format_print_run(r.get("Print Run", ""))
            sub_u = str(r.get("Subset", "Base")).upper()
            if pr_s == "1":
                p_val = 150.00
            elif pr_s.isdigit() and int(pr_s) <= 10:
                p_val = 45.00
            elif pr_s.isdigit() and int(pr_s) <= 50:
                p_val = 18.00
            elif pr_s.isdigit() and int(pr_s) <= 199:
                p_val = 7.50
            elif sub_u in ("BASE", "BASE SET"):
                p_val = 1.25
            else:
                p_val = 3.00
        est_prices.append(round(p_val, 2))
        q_ebay = quote(f"{r['Set']} #{r['Card Number']} {r['Player']} {r['Subset'] if r['Subset'] != 'Base' else ''}".strip())
        buy_links.append(f"https://www.ebay.com/sch/i.html?_nkw={q_ebay}&_sop=15")

    missing_df["Est_Cost_USD"] = est_prices
    missing_df["eBay_Buy_Link"] = buy_links

    if max_budget_per_card > 0:
        missing_df = missing_df[missing_df["Est_Cost_USD"] <= float(max_budget_per_card)].copy()

    missing_df = missing_df.sort_values(by=["Est_Cost_USD", "Card Number"], ascending=[True, True]).reset_index(drop=True)
    total_cost = round(float(missing_df["Est_Cost_USD"].sum()), 2)

    return missing_df, {
        "owned_count": owned_count,
        "total_count": total_count,
        "missing_count": len(missing_df),
        "estimated_total_cost": total_cost,
    }