from __future__ import annotations
# ==============================================================================
# Core/sales_engine.py - PHASE 2 (#7-10): PC/OFFER/SALE TAGGING, CARD-LEVEL
# INVENTORY ROLLUP, LOT/SET/RAINBOW RECOMMENDER, EXPENSES/COGS CALCULATOR &
# HUMAN-WRITTEN BIO / STATS / ACCOLADES LISTING WRITER
# ==============================================================================
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

__version__ = "0.24.0-beta.18"
__last_updated__ = "2026-11-20 15:00:00"

from Core.config import (
    CARD_LEVEL_TARGETS_FILE,
    CHECKLIST_PATH,
    EXPENSES_CSV_COLUMNS,
    EXPENSES_CSV_FILE,
    EXPENSES_PRICING_CONFIG_FILE,
    HOLD_TAG_OPTIONS,
    LISTING_DRAFTS_FILE,
    PLAYER_BIOS_CACHE_FILE,
    RECOMMENDED_LOTS_FILE,
    canonical_subset_key,
    ensure_directories,
    format_print_run,
    norm,
    strip_accents,
)
from Core.vision_grader import recalculate_dataframe_multi_grader_roi
from Core.rate_learner import get_rate_learner


def _bio_adaptive_get(endpoint: str, url: str, headers: dict, timeout: int = 7):
    learner = get_rate_learner()
    learner.wait_before_request(endpoint)
    t0 = time.time()
    resp = requests.get(url, headers=headers, timeout=timeout)
    el_ms = int((time.time() - t0) * 1000)
    if resp.status_code == 429:
        wait_s, _ = learner.record_rate_limit(endpoint, retry_after_header=resp.headers.get("Retry-After"))
        time.sleep(min(wait_s, 30.0))
        return None
    if resp.status_code in (200, 404):
        learner.record_success(endpoint, elapsed_ms=el_ms, status_code=resp.status_code)
    return resp

LISTING_DRAFTS_COLUMNS = [
    "Draft_ID",
    "Listing_Type",
    "SKU_or_Lot_ID",
    "Set",
    "Subset",
    "Card_Number",
    "Player_or_Bundle",
    "Team",
    "Quantity",
    "Recommended_Price",
    "Platform_Target",
    "SEO_Title_80Char",
    "Description_Body",
    "Front_File",
    "Back_File",
    "Created_At",
]

EXPENSE_CATEGORIES = [
    "Boxes / Packs / Cases (COGS)",
    "Single Card Acquisitions (COGS)",
    "Card Protection & Storage (Sleeves, Toploaders, One-Touch, Boxes)",
    "Shipping Materials (Mailers, Team Bags, Tape, Labels)",
    "Equipment & Software (Scanner, Printer, Thermal Labels)",
    "Grading & Authentication Fees",
    "Other / Miscellaneous",
]

SET_BLURBS_CACHE_FILE = PLAYER_BIOS_CACHE_FILE.parent / "set_blurbs_cache.json"

DEFAULT_LISTING_CONTENT_OPTIONS = {
    "include_opening": True,
    "include_set_blurb": True,
    "include_player_bio": True,
    "include_player_stats": True,
    "include_player_accolades": True,
    "include_pregrade_notes": True,
    "include_grading_disclaimer": True,
    "include_shipping_policy": True,
    "include_as_is_disclaimer": True,
    "include_sku_ref": True,
}

COMPUTER_GRADING_DISCLAIMER = (
    "Please Note: The photos in this listing show the exact physical card you will receive. "
    "Any centering measurements or estimated pre-grades (PSA/BGS) mentioned above are computer-generated "
    "from our scanner for informational purposes only and do not represent a professional grade or a "
    "guarantee of card condition or quality."
)

AS_IS_48HR_DISCLAIMER = (
    "*Disclaimer: All cards are sold as-is based on the high-resolution scans provided. "
    "Please inspect all photos carefully prior to purchasing. Any questions, issues, or "
    "condition discrepancies must be reported within 48 hours of delivery.*"
)

DEFAULT_SHIPPING_POLICY_NOTE = (
    "Shipping method and protective holder depend on the card(s) purchased, total order value, quantity, "
    "and the shipping option selected at checkout. Every card ships at minimum in a penny sleeve with "
    "reinforced cardboard or equivalent rigid protection; higher-value cards may ship in semi-rigid "
    "Card Savers or rigid toploaders depending on value and shipping method selected. Please note that "
    "tracking may not be available on all economy/standard envelope shipments."
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


def build_unique_card_key(set_name: str, subset_name: str, card_number: str, player_name: str) -> str:
    """Builds a canonical unique card design identifier `(Set, Subset, Card Number, Player)`."""
    s_k = norm(set_name)
    sub_k = canonical_subset_key(subset_name, set_name)
    cn_k = norm(str(card_number or "").lstrip("#"))
    p_k = norm(player_name)
    return f"{s_k}|{sub_k}|{cn_k}|{p_k}"


# ==============================================================================
# 0. EXPENSES (Inventory\Expenses.csv), COST-BASIS & MARKET MARKUP CALCULATOR
# ==============================================================================
def _default_expenses_seed_rows() -> list[dict]:
    return [
        {
            "ID": "EXP-001",
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Category": "Card Protection & Storage (Sleeves, Toploaders, One-Touch, Boxes)",
            "Vendor": "",
            "Description": "Penny Sleeves, Toploaders & Card Savers Starter Stock",
            "Set Scope": "All Sets (Global Overhead)",
            "Cost": "25.00",
        },
        {
            "ID": "EXP-002",
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Category": "Shipping Materials (Mailers, Team Bags, Tape, Labels)",
            "Vendor": "",
            "Description": "Envelopes, Bubble Mailers & R037L Labels",
            "Set Scope": "All Sets (Global Overhead)",
            "Cost": "20.00",
        },
    ]


def _default_expenses_and_pricing_config() -> dict:
    return {
        "expenses_ledger": _default_expenses_seed_rows(),
        "pricing_strategy": {
            "market_markup_pct": 50.0,
            "make_offer_markup_pct": 75.0,
            "rookie_serial_bonus_pct": 15.0,
            "gem_mint_pregrade_bonus_pct": 20.0,
            "global_min_price_floor": 1.49,
            "target_min_net_profit_per_card": 0.65,
            "per_card_supplies_cost": 0.18,
            "per_order_packaging_cost": 0.35,
            "per_order_shipping_cost": 0.00,
            "marketplace_fee_pct": 13.25,
            "fixed_transaction_fee": 0.30,
            "amortize_overhead_across": "For Sale Cards Only",
            "custom_amortization_card_count": 500,
            "computed_unit_cogs_and_overhead": 0.25,
            "per_set_unit_cogs": {},
        },
    }


def load_expenses_csv_rows() -> list[dict]:
    """
    Reads `Inventory/Expenses.csv` using the exact columns:
      ID, Date, Category, Vendor, Description, Set Scope, Cost
    Trims any stray whitespace/tabs in CSV headers (e.g. 'Set Scope\\t' -> 'Set Scope')
    and preserves existing files on disk without overwriting them.
    """
    ensure_directories()
    if EXPENSES_CSV_FILE.exists():
        try:
            if EXPENSES_CSV_FILE.stat().st_size == 0:
                return []
            df = pd.read_csv(EXPENSES_CSV_FILE, dtype=str, keep_default_na=False)
            df.columns = [str(c).strip() for c in df.columns]

            # Map any legacy column names if encountered
            rename_legacy = {
                "Expense_ID": "ID",
                "Item_Description": "Description",
                "Associated_Set": "Set Scope",
                "Amount_USD": "Cost",
                "Notes": "Vendor",
            }
            for old_c, new_c in rename_legacy.items():
                if old_c in df.columns and new_c not in df.columns:
                    df.rename(columns={old_c: new_c}, inplace=True)

            for col in EXPENSES_CSV_COLUMNS:
                if col not in df.columns:
                    df[col] = ""

            rows = []
            for idx, r in df.iterrows():
                rec = {c: str(r.get(c, "")).strip() for c in df.columns}
                if not any(rec.values()):
                    continue
                if not rec.get("ID"):
                    rec["ID"] = f"EXP-{idx + 1:03d}"
                amt_f = _safe_float(rec.get("Cost"), 0.0)
                rec["Cost"] = f"{amt_f:.2f}"
                rows.append(rec)
            return rows
        except Exception:
            return []

    # Only seed starter rows if Inventory/Expenses.csv does not exist at all
    return save_expenses_csv_rows(_default_expenses_seed_rows())


def save_expenses_csv_rows(rows: list[dict]) -> list[dict]:
    """Persists expense records directly to `Inventory/Expenses.csv` (ID, Date, Category, Vendor, Description, Set Scope, Cost)."""
    ensure_directories()
    cleaned: list[dict] = []
    extra_cols: list[str] = []

    for idx, item in enumerate(rows or [], 1):
        if not isinstance(item, dict):
            continue
        norm_item = {str(k).strip(): v for k, v in item.items()}
        desc_s = str(norm_item.get("Description") or norm_item.get("Item_Description") or "").strip()
        vendor_s = str(norm_item.get("Vendor") or norm_item.get("Notes") or "").strip()
        scope_s = str(norm_item.get("Set Scope") or norm_item.get("Associated_Set") or "All Sets (Global Overhead)").strip()
        amt_raw = norm_item.get("Cost") if "Cost" in norm_item else norm_item.get("Amount_USD")
        amt_v = _safe_float(amt_raw, 0.0)

        if not desc_s and not vendor_s and amt_v <= 0 and len(rows) > 1:
            continue

        rec = {
            "ID": str(norm_item.get("ID") or norm_item.get("Expense_ID") or f"EXP-{idx:03d}").strip(),
            "Date": str(norm_item.get("Date") or datetime.now().strftime("%Y-%m-%d")).strip(),
            "Category": str(norm_item.get("Category") or EXPENSE_CATEGORIES[0]).strip(),
            "Vendor": vendor_s,
            "Description": desc_s or "Card Business Expense",
            "Set Scope": scope_s or "All Sets (Global Overhead)",
            "Cost": f"{amt_v:.2f}",
        }
        for k, v in norm_item.items():
            if k not in rec and k not in ("Expense_ID", "Item_Description", "Associated_Set", "Amount_USD", "Notes"):
                rec[k] = str(v or "").strip()
                if k not in extra_cols:
                    extra_cols.append(k)
        cleaned.append(rec)

    all_cols = list(EXPENSES_CSV_COLUMNS) + extra_cols
    out_df = pd.DataFrame(cleaned, columns=all_cols) if cleaned else pd.DataFrame(columns=all_cols)
    out_df.to_csv(EXPENSES_CSV_FILE, index=False, encoding="utf-8-sig")
    return cleaned


def load_expenses_and_pricing_config() -> dict:
    """Loads `Inventory/Expenses.csv` + `pricing_strategy` from `expenses_and_pricing_config.json`."""
    ensure_directories()
    default_cfg = _default_expenses_and_pricing_config()
    if EXPENSES_PRICING_CONFIG_FILE.exists():
        try:
            loaded = json.loads(EXPENSES_PRICING_CONFIG_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict) and isinstance(loaded.get("pricing_strategy"), dict):
                default_cfg["pricing_strategy"].update(loaded["pricing_strategy"])
        except Exception:
            pass
    default_cfg["expenses_ledger"] = load_expenses_csv_rows()
    return default_cfg


def save_expenses_and_pricing_config(cfg: dict) -> dict:
    """Saves `expenses_ledger` to `Inventory/Expenses.csv` and `pricing_strategy` to JSON."""
    ensure_directories()
    ledger_rows = cfg.get("expenses_ledger")
    if isinstance(ledger_rows, list):
        saved_rows = save_expenses_csv_rows(ledger_rows)
        cfg["expenses_ledger"] = saved_rows

    strat_payload = {
        "pricing_strategy": cfg.get("pricing_strategy", _default_expenses_and_pricing_config()["pricing_strategy"]),
        "expenses_csv_path": str(EXPENSES_CSV_FILE),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    EXPENSES_PRICING_CONFIG_FILE.write_text(json.dumps(strat_payload, indent=2), encoding="utf-8")
    return cfg


def compute_expense_and_cost_basis_summary(inv_df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """
    Aggregates all logged expenses from `Inventory/Expenses.csv` (`ID`, `Date`, `Category`,
    `Vendor`, `Description`, `Set Scope`, `Cost`) and computes per-card cost basis & break-even metrics.
    """
    if cfg is None:
        cfg = load_expenses_and_pricing_config()

    ledger = cfg.get("expenses_ledger", [])
    strat = cfg.get("pricing_strategy", {})

    cat_totals: dict[str, float] = defaultdict(float)
    set_specific_spend: dict[str, float] = defaultdict(float)
    global_overhead_spend = 0.0

    for item in ledger:
        amt = _safe_float(item.get("Cost") if "Cost" in item else item.get("Amount_USD"), 0.0)
        if amt <= 0:
            continue
        cat = str(item.get("Category", "Other / Miscellaneous")).strip()
        assoc_set = str(item.get("Set Scope") or item.get("Associated_Set") or "All Sets (Global Overhead)").strip()
        cat_totals[cat] += amt
        if assoc_set and assoc_set not in ("All Sets (Global Overhead)", "All Sets", "Global", "None", ""):
            set_specific_spend[assoc_set] += amt
        else:
            global_overhead_spend += amt

    total_expenses = sum(cat_totals.values())

    active_inv = inv_df[inv_df["Status"] != "Sold"].copy() if (inv_df is not None and not inv_df.empty) else pd.DataFrame()
    total_in_stock_count = max(1, len(active_inv))
    for_sale_count = (
        max(
            1,
            int(
                (
                    ~active_inv["Hold_Tag"]
                    .astype(str)
                    .str.contains("Personal Collection", case=False, na=False)
                ).sum()
            ),
        )
        if not active_inv.empty and "Hold_Tag" in active_inv.columns
        else total_in_stock_count
    )

    amort_mode = str(strat.get("amortize_overhead_across", "For Sale Cards Only"))
    if amort_mode == "All In-Stock Cards":
        denom_cards = total_in_stock_count
    elif amort_mode == "Custom Card Count":
        denom_cards = max(1, int(_safe_float(strat.get("custom_amortization_card_count"), 500)))
    else:
        denom_cards = for_sale_count

    global_overhead_per_card = round(global_overhead_spend / float(denom_cards), 4)

    per_set_unit_cogs: dict[str, float] = {}
    if not active_inv.empty:
        for s_name, grp in active_inv.groupby("Set"):
            s_cnt = max(1, len(grp))
            s_direct = set_specific_spend.get(str(s_name).strip(), 0.0) / float(s_cnt)
            per_set_unit_cogs[str(s_name).strip()] = round(global_overhead_per_card + s_direct, 2)

    overall_unit_cogs = round(total_expenses / float(denom_cards), 2)

    supplies_per_order = (
        _safe_float(strat.get("per_card_supplies_cost"), 0.18)
        + _safe_float(strat.get("per_order_packaging_cost"), 0.35)
        + _safe_float(strat.get("per_order_shipping_cost"), 0.00)
    )
    fixed_fee = _safe_float(strat.get("fixed_transaction_fee"), 0.30)
    fee_rate = min(0.50, max(0.0, _safe_float(strat.get("marketplace_fee_pct"), 13.25) / 100.0))
    target_profit = _safe_float(strat.get("target_min_net_profit_per_card"), 0.65)
    global_floor = _safe_float(strat.get("global_min_price_floor"), 1.49)

    avg_break_even = round((overall_unit_cogs + supplies_per_order + fixed_fee) / max(0.10, 1.0 - fee_rate), 2)
    avg_min_sale_price = max(
        global_floor,
        round(avg_break_even + (target_profit / max(0.10, 1.0 - fee_rate)), 2),
    )

    net_margin_at_min = max(
        0.25,
        (avg_min_sale_price * (1.0 - fee_rate)) - fixed_fee - supplies_per_order,
    )
    cards_to_break_even = int(np.ceil(total_expenses / net_margin_at_min)) if total_expenses > 0 else 0

    cogs_boxes_sum = sum(
        v for k, v in cat_totals.items()
        if any(kw in k.lower() for kw in ("box", "pack", "case", "cogs", "single", "acquisition"))
    )
    protection_sum = sum(
        v for k, v in cat_totals.items()
        if any(kw in k.lower() for kw in ("protect", "storage", "sleeve", "toploader", "holder", "suppl"))
    )
    shipping_sum = sum(
        v for k, v in cat_totals.items()
        if any(kw in k.lower() for kw in ("ship", "mailer", "envelope", "postage", "label"))
    )
    equipment_sum = max(0.0, total_expenses - cogs_boxes_sum - protection_sum - shipping_sum)

    return {
        "total_expenses": round(total_expenses, 2),
        "total_cogs_boxes": round(cogs_boxes_sum, 2),
        "total_protection": round(protection_sum, 2),
        "total_shipping_mat": round(shipping_sum, 2),
        "total_equipment": round(equipment_sum, 2),
        "denom_cards": denom_cards,
        "global_overhead_per_card": round(global_overhead_per_card, 2),
        "overall_unit_cogs": overall_unit_cogs,
        "per_set_unit_cogs": per_set_unit_cogs,
        "supplies_per_order": round(supplies_per_order, 2),
        "avg_break_even_price": avg_break_even,
        "avg_min_sale_price": avg_min_sale_price,
        "cards_to_break_even": cards_to_break_even,
        "category_breakdown": dict(cat_totals),
    }


def apply_pricing_strategy_to_inventory_df(inv_df: pd.DataFrame, cfg: Optional[dict] = None) -> tuple[pd.DataFrame, dict]:
    """
    Persists the latest computed unit COGS and per-set COGS into `expenses_and_pricing_config.json`,
    then recalculates `Min_Sale_Price`, `Rec_Sale_Price` (applying the user's `% Increase Over Market Price`),
    Graded Comps, and ROI across all rows of `inv_df`.
    """
    if cfg is None:
        cfg = load_expenses_and_pricing_config()
    summary = compute_expense_and_cost_basis_summary(inv_df, cfg=cfg)
    cfg["pricing_strategy"]["computed_unit_cogs_and_overhead"] = summary["overall_unit_cogs"]
    cfg["pricing_strategy"]["per_set_unit_cogs"] = summary["per_set_unit_cogs"]
    save_expenses_and_pricing_config(cfg)

    if inv_df is None or inv_df.empty:
        return inv_df, summary

    updated_df = recalculate_dataframe_multi_grader_roi(inv_df)
    return updated_df, summary


# ==============================================================================
# 1. ITEMS #7 & #8: CARD-LEVEL INVENTORY ROLLUP & PC / FOR-SALE AUTO-ALLOCATOR
# ==============================================================================
def load_card_level_targets() -> dict[str, dict]:
    """Loads custom per-card target retain quantities from Inventory/card_level_targets.json."""
    ensure_directories()
    if not CARD_LEVEL_TARGETS_FILE.exists():
        return {}
    try:
        with open(CARD_LEVEL_TARGETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_card_level_targets(targets_map: dict[str, dict]) -> dict[str, dict]:
    ensure_directories()
    with open(CARD_LEVEL_TARGETS_FILE, "w", encoding="utf-8") as f:
        json.dump(targets_map, f, indent=2)
    return targets_map


def build_card_level_inventory_df(
    inv_df: pd.DataFrame,
    default_retain_qty: int = 1,
) -> pd.DataFrame:
    """
    Item #8: Aggregates copy-level `Inventory.csv` into a unique Card-Level Inventory table:
      - Total_Copies (In-Stock physical copies owned)
      - Target_Retain_Qty (Desired copies to keep for PC, defaulting to `default_retain_qty`, usually 1)
      - PC_Retained_Qty (Copies currently tagged `Personal Collection (PC)`)
      - Make_Offer_Qty (Copies currently tagged `Make Me an Offer`)
      - For_Sale_Qty (Copies currently tagged `For Sale`)
      - Surplus_Sellable_Qty (`max(0, Total_Copies - Target_Retain_Qty)`)
      - Sold_Qty (Historical copies marked `Sold`)
      - Best_SKU, Best_PSA, Best_BGS (Highest pre-graded physical copy in stock)
      - Unit_Raw_Price, Unit_Rec_Sale_Price, Total_Sellable_Value
    """
    cols = [
        "Card_Key",
        "Set",
        "Subset",
        "Card Number",
        "Player",
        "Team",
        "Print Run",
        "Attributes",
        "Total_Copies",
        "Target_Retain_Qty",
        "PC_Retained_Qty",
        "Make_Offer_Qty",
        "For_Sale_Qty",
        "Surplus_Sellable_Qty",
        "Sold_Qty",
        "Best_SKU",
        "Best_PSA",
        "Best_BGS",
        "Unit_Raw_Price",
        "Unit_Rec_Sale_Price",
        "Total_Sellable_Value",
        "For_Sale_SKUs",
        "PC_SKUs",
    ]
    if inv_df is None or inv_df.empty:
        return pd.DataFrame(columns=cols)

    targets_map = load_card_level_targets()
    grouped_records: dict[str, list[dict]] = defaultdict(list)

    for _, row in inv_df.iterrows():
        c_key = build_unique_card_key(
            row.get("Set", ""),
            row.get("Subset", "Base"),
            row.get("Card Number", ""),
            row.get("Player", ""),
        )
        grouped_records[c_key].append(row.to_dict())

    rollup_rows = []
    for c_key, copies in grouped_records.items():
        first = copies[0]
        in_stock_copies = [c for c in copies if str(c.get("Status", "In Stock")) != "Sold"]
        sold_copies = [c for c in copies if str(c.get("Status", "")) == "Sold"]

        total_in_stock = len(in_stock_copies)
        target_retain = int(
            targets_map.get(c_key, {}).get("target_retain_qty", default_retain_qty)
        )

        pc_skus = []
        offer_skus = []
        sale_skus = []
        for c in in_stock_copies:
            ht = str(c.get("Hold_Tag", "For Sale")).strip()
            sku_s = str(c.get("SKU", "")).strip()
            if "Personal Collection" in ht or str(c.get("Status", "")) == "PC / Hold":
                pc_skus.append(sku_s)
            elif "Make Me an Offer" in ht:
                offer_skus.append(sku_s)
            else:
                sale_skus.append(sku_s)

        surplus_qty = max(0, total_in_stock - target_retain)

        def _grade_sort_key(c_dict: dict) -> tuple[float, float, float]:
            return (
                _safe_float(c_dict.get("Est_Grade"), 0.0),
                _safe_float(c_dict.get("Est_PSA"), 0.0),
                _safe_float(c_dict.get("Est_BGS"), 0.0),
            )

        sorted_by_grade = sorted(in_stock_copies, key=_grade_sort_key, reverse=True) if in_stock_copies else copies
        best_copy = sorted_by_grade[0]

        unit_raw = _safe_float(best_copy.get("Raw_Price"), 2.00)
        unit_rec = _safe_float(best_copy.get("Rec_Sale_Price"), unit_raw)
        sellable_val = round(len(sale_skus) * unit_rec, 2)

        rollup_rows.append({
            "Card_Key": c_key,
            "Set": str(first.get("Set", "")).strip(),
            "Subset": str(first.get("Subset", "Base")).strip(),
            "Card Number": str(first.get("Card Number", "")).strip().lstrip("#"),
            "Player": str(first.get("Player", "")).strip(),
            "Team": str(first.get("Team", "")).strip(),
            "Print Run": format_print_run(first.get("Print Run", "")),
            "Attributes": str(first.get("Attributes", "")).strip(),
            "Total_Copies": total_in_stock,
            "Target_Retain_Qty": target_retain,
            "PC_Retained_Qty": len(pc_skus),
            "Make_Offer_Qty": len(offer_skus),
            "For_Sale_Qty": len(sale_skus),
            "Surplus_Sellable_Qty": surplus_qty,
            "Sold_Qty": len(sold_copies),
            "Best_SKU": str(best_copy.get("SKU", "")),
            "Best_PSA": str(best_copy.get("Est_PSA", "")),
            "Best_BGS": str(best_copy.get("Est_BGS", "")),
            "Unit_Raw_Price": round(unit_raw, 2),
            "Unit_Rec_Sale_Price": round(unit_rec, 2),
            "Total_Sellable_Value": sellable_val,
            "For_Sale_SKUs": ", ".join(sale_skus),
            "PC_SKUs": ", ".join(pc_skus),
        })

    out_df = pd.DataFrame(rollup_rows, columns=cols)
    if not out_df.empty:
        out_df["_num_cn"] = pd.to_numeric(out_df["Card Number"], errors="coerce").fillna(999999)
        out_df = (
            out_df.sort_values(by=["Set", "_num_cn", "Card Number", "Subset"])
            .drop(columns=["_num_cn"])
            .reset_index(drop=True)
        )
    return out_df


def auto_allocate_pc_and_sale_copies(
    inv_df: pd.DataFrame,
    card_level_df: Optional[pd.DataFrame] = None,
    default_retain_qty: int = 1,
    preserve_make_offer: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Items #7 & #8 Smart Auto-Allocator:
    For each unique card design `(Set, Subset, Card Number, Player)`:
      1. Sorts all in-stock physical copies by highest estimated grade (`Est_Grade`, `Est_PSA`, `Est_BGS`).
      2. Tags the top `Target_Retain_Qty` copy/copies (e.g., your sharpest copy) as `Personal Collection (PC)`.
      3. Tags all remaining duplicate/surplus copies as `For Sale` (while optionally preserving
         any copies explicitly tagged `Make Me an Offer`).
    """
    if inv_df is None or inv_df.empty:
        return inv_df, {"pc_tagged": 0, "for_sale_tagged": 0, "offer_preserved": 0}

    targets_map = load_card_level_targets()
    if card_level_df is not None and not card_level_df.empty:
        for _, r in card_level_df.iterrows():
            ck = str(r.get("Card_Key", "")).strip()
            if ck:
                targets_map[ck] = {"target_retain_qty": max(0, int(_safe_float(r.get("Target_Retain_Qty"), default_retain_qty)))}
        save_card_level_targets(targets_map)

    out = inv_df.copy()
    if "Hold_Tag" not in out.columns:
        out["Hold_Tag"] = "For Sale"

    grouped_indices: dict[str, list[int]] = defaultdict(list)
    for row_idx, row in out.iterrows():
        if str(row.get("Status", "In Stock")) == "Sold":
            continue
        ck = build_unique_card_key(
            row.get("Set", ""),
            row.get("Subset", "Base"),
            row.get("Card Number", ""),
            row.get("Player", ""),
        )
        grouped_indices[ck].append(row_idx)

    pc_count = 0
    sale_count = 0
    offer_count = 0

    for ck, idx_list in grouped_indices.items():
        retain_q = int(targets_map.get(ck, {}).get("target_retain_qty", default_retain_qty))

        def _idx_grade_key(i: int) -> tuple:
            r = out.loc[i]
            return (
                _safe_float(r.get("Est_Grade"), 0.0),
                _safe_float(r.get("Est_PSA"), 0.0),
                _safe_float(r.get("Est_BGS"), 0.0),
                _safe_float(r.get("Sub_Centering"), 0.0),
                _safe_float(r.get("Sub_Corners"), 0.0),
                -_safe_float(r.get("SKU"), 0.0),
            )

        sorted_idxs = sorted(idx_list, key=_idx_grade_key, reverse=True)
        for rank_i, r_idx in enumerate(sorted_idxs, 1):
            curr_tag = str(out.at[r_idx, "Hold_Tag"]).strip()
            if rank_i <= retain_q:
                out.at[r_idx, "Hold_Tag"] = "Personal Collection (PC)"
                pc_count += 1
            else:
                if preserve_make_offer and "Make Me an Offer" in curr_tag:
                    out.at[r_idx, "Hold_Tag"] = "Make Me an Offer"
                    offer_count += 1
                else:
                    out.at[r_idx, "Hold_Tag"] = "For Sale"
                    sale_count += 1

    out = recalculate_dataframe_multi_grader_roi(out)
    return out, {
        "pc_tagged": pc_count,
        "for_sale_tagged": sale_count,
        "offer_preserved": offer_count,
    }


# ==============================================================================
# 2. ITEM #9: LOT, COMPLETE SET, TEAM SET, ROOKIE & RAINBOW RECOMMENDER
# ==============================================================================
def generate_lot_and_set_recommendations(
    inv_df: pd.DataFrame,
    master_chk_df: Optional[pd.DataFrame] = None,
    only_surplus_multi_copies: bool = True,
    default_retain_qty: int = 1,
    lot_discount_pct: float = 12.0,
    complete_set_premium_pct: float = 15.0,
) -> pd.DataFrame:
    """
    Item #9: Analyzes Inventory.csv and Master_Checklist.csv to recommend profitable
    selling bundles (Complete Sets, Insert Sets, Team Sets/Lots, Player/Rookie Lots,
    Parallel/Rainbow Lots, and Duplicate Card Bulk Lots).
    """
    cols = [
        "Lot_ID",
        "Lot_Category",
        "Set",
        "Lot_Title",
        "Unique_Cards",
        "Total_Cards",
        "Sum_Individual_Raw_USD",
        "Recommended_Lot_Price_USD",
        "Pricing_Strategy",
        "Rationale",
        "Included_SKUs",
    ]
    if inv_df is None or inv_df.empty:
        return pd.DataFrame(columns=cols)

    if master_chk_df is None and CHECKLIST_PATH.exists():
        try:
            master_chk_df = pd.read_csv(CHECKLIST_PATH, dtype=str, keep_default_na=False)
        except Exception:
            master_chk_df = pd.DataFrame()

    card_lvl_df = build_card_level_inventory_df(inv_df, default_retain_qty=default_retain_qty)
    if card_lvl_df.empty:
        return pd.DataFrame(columns=cols)

    if only_surplus_multi_copies:
        sellable_cards = card_lvl_df[
            (card_lvl_df["Total_Copies"] >= 2) & (card_lvl_df["Surplus_Sellable_Qty"] >= 1)
        ].copy()
    else:
        sellable_cards = card_lvl_df[card_lvl_df["For_Sale_Qty"] >= 1].copy()

    if sellable_cards.empty:
        return pd.DataFrame(columns=cols)

    active_inv = inv_df[inv_df["Status"] != "Sold"].copy()
    surplus_skus_by_key: dict[str, list[dict]] = defaultdict(list)

    targets_map = load_card_level_targets()
    grouped_rows: dict[str, list[dict]] = defaultdict(list)
    for _, r in active_inv.iterrows():
        ck = build_unique_card_key(r["Set"], r["Subset"], r["Card Number"], r["Player"])
        grouped_rows[ck].append(r.to_dict())

    for ck, c_list in grouped_rows.items():
        retain_q = int(targets_map.get(ck, {}).get("target_retain_qty", default_retain_qty))
        if only_surplus_multi_copies and len(c_list) <= max(1, retain_q):
            continue
        c_sorted = sorted(
            c_list,
            key=lambda x: (
                1 if "Personal Collection" in str(x.get("Hold_Tag", "")) else 0,
                _safe_float(x.get("Est_Grade"), 0.0),
                _safe_float(x.get("Est_PSA"), 0.0),
            ),
            reverse=True,
        )
        surplus_slice = c_sorted[retain_q:] if only_surplus_multi_copies else [
            x for x in c_sorted if "Personal Collection" not in str(x.get("Hold_Tag", ""))
        ]
        if surplus_slice:
            surplus_skus_by_key[ck] = surplus_slice

    recommendations = []
    lot_seq = 1
    disc_mult = max(0.50, 1.0 - (float(lot_discount_pct) / 100.0))
    prem_mult = 1.0 + (float(complete_set_premium_pct) / 100.0)

    # CATEGORY 1: COMPLETE BASE SETS & SET BUILDER LOTS
    for set_name, set_surplus_df in sellable_cards.groupby("Set"):
        chk_set = (
            master_chk_df[master_chk_df["Set"] == set_name].copy()
            if (master_chk_df is not None and not master_chk_df.empty)
            else pd.DataFrame()
        )
        base_surplus = set_surplus_df[set_surplus_df["Subset"].str.upper().isin(("BASE", "BASE SET"))]
        surplus_base_cnums = {norm(cn) for cn in base_surplus["Card Number"]}

        if not chk_set.empty:
            chk_base = chk_set[chk_set["Subset"].str.upper().isin(("BASE", "BASE SET"))].drop_duplicates(subset=["Card Number"])
            all_base_cnums = {norm(cn) for cn in chk_base["Card Number"]}

            if all_base_cnums and all_base_cnums.issubset(surplus_base_cnums):
                max_complete_sets = int(base_surplus["Surplus_Sellable_Qty"].min())
                chosen_skus = []
                raw_sum = 0.0
                for _, b_row in base_surplus.iterrows():
                    ck = b_row["Card_Key"]
                    if surplus_skus_by_key.get(ck):
                        s_item = surplus_skus_by_key[ck][0]
                        chosen_skus.append(str(s_item["SKU"]))
                        raw_sum += _safe_float(s_item.get("Raw_Price"), 1.50)

                rec_price = round(raw_sum * prem_mult, 2)
                recommendations.append({
                    "Lot_ID": f"LOT-{lot_seq:03d}",
                    "Lot_Category": "Complete Base Set",
                    "Set": set_name,
                    "Lot_Title": f"{set_name} Complete Base Set ({len(all_base_cnums)} Cards)",
                    "Unique_Cards": len(all_base_cnums),
                    "Total_Cards": len(all_base_cnums),
                    "Sum_Individual_Raw_USD": round(raw_sum, 2),
                    "Recommended_Lot_Price_USD": rec_price,
                    "Pricing_Strategy": f"+{complete_set_premium_pct:.0f}% Complete Set Convenience Premium",
                    "Rationale": f"100% of checklist present in duplicate/surplus inventory ({max_complete_sets} extra set(s) available while retaining PC set).",
                    "Included_SKUs": ", ".join(chosen_skus),
                })
                lot_seq += 1

            elif len(base_surplus) >= 15:
                chosen_skus = []
                raw_sum = 0.0
                for _, b_row in base_surplus.iterrows():
                    ck = b_row["Card_Key"]
                    if surplus_skus_by_key.get(ck):
                        s_item = surplus_skus_by_key[ck][0]
                        chosen_skus.append(str(s_item["SKU"]))
                        raw_sum += _safe_float(s_item.get("Raw_Price"), 1.50)
                rec_price = round(raw_sum * disc_mult, 2)
                recommendations.append({
                    "Lot_ID": f"LOT-{lot_seq:03d}",
                    "Lot_Category": "Base Set Builder Lot",
                    "Set": set_name,
                    "Lot_Title": f"{set_name} Base Set Builder Lot ({len(base_surplus)} Unique Cards, No Duplicates)",
                    "Unique_Cards": len(base_surplus),
                    "Total_Cards": len(base_surplus),
                    "Sum_Individual_Raw_USD": round(raw_sum, 2),
                    "Recommended_Lot_Price_USD": rec_price,
                    "Pricing_Strategy": f"-{lot_discount_pct:.0f}% Set-Builder Bundle Discount",
                    "Rationale": f"{len(base_surplus)} unique base cards with multiple copies in inventory (retains 1 copy of each for your PC).",
                    "Included_SKUs": ", ".join(chosen_skus),
                })
                lot_seq += 1

    # CATEGORY 2: TEAM SETS & TEAM LOTS
    for (set_name, team_name), team_df in sellable_cards.groupby(["Set", "Team"]):
        t_clean = str(team_name or "").strip()
        if not t_clean or t_clean.upper() in ("NO TEAM", "UNKNOWN", "NAN"):
            continue
        if len(team_df) < 3:
            continue

        chosen_skus = []
        raw_sum = 0.0
        for _, t_row in team_df.iterrows():
            ck = t_row["Card_Key"]
            if surplus_skus_by_key.get(ck):
                s_item = surplus_skus_by_key[ck][0]
                chosen_skus.append(str(s_item["SKU"]))
                raw_sum += _safe_float(s_item.get("Raw_Price"), 1.50)

        if len(chosen_skus) >= 3:
            rec_price = max(3.99, round(raw_sum * disc_mult, 2))
            recommendations.append({
                "Lot_ID": f"LOT-{lot_seq:03d}",
                "Lot_Category": "Team Set / Lot",
                "Set": set_name,
                "Lot_Title": f"{set_name} {t_clean} Team Lot ({len(chosen_skus)} Unique Cards)",
                "Unique_Cards": len(chosen_skus),
                "Total_Cards": len(chosen_skus),
                "Sum_Individual_Raw_USD": round(raw_sum, 2),
                "Recommended_Lot_Price_USD": rec_price,
                "Pricing_Strategy": f"-{lot_discount_pct:.0f}% Team Fan Bundle",
                "Rationale": f"Includes {len(chosen_skus)} unique {t_clean} cards pulled strictly from duplicate copies.",
                "Included_SKUs": ", ".join(chosen_skus),
            })
            lot_seq += 1

    # CATEGORY 3: PARALLEL & PARTIAL RAINBOW LOTS
    for (set_name, cnum_str, player_name), rb_df in sellable_cards.groupby(["Set", "Card Number", "Player"]):
        if len(rb_df) >= 2:
            chosen_skus = []
            raw_sum = 0.0
            subs_included = []
            for _, r_row in rb_df.iterrows():
                ck = r_row["Card_Key"]
                if surplus_skus_by_key.get(ck):
                    s_item = surplus_skus_by_key[ck][0]
                    chosen_skus.append(str(s_item["SKU"]))
                    subs_included.append(str(r_row["Subset"]))
                    raw_sum += _safe_float(s_item.get("Raw_Price"), 2.00)
            if len(chosen_skus) >= 2:
                rec_price = round(raw_sum * 1.05, 2)
                recommendations.append({
                    "Lot_ID": f"LOT-{lot_seq:03d}",
                    "Lot_Category": "Player Rainbow Lot",
                    "Set": set_name,
                    "Lot_Title": f"{set_name} #{cnum_str} {player_name} Rainbow Starter Lot ({', '.join(subs_included[:4])})",
                    "Unique_Cards": len(chosen_skus),
                    "Total_Cards": len(chosen_skus),
                    "Sum_Individual_Raw_USD": round(raw_sum, 2),
                    "Recommended_Lot_Price_USD": rec_price,
                    "Pricing_Strategy": "+5% Rainbow Collector Premium",
                    "Rationale": f"Bundles {len(chosen_skus)} surplus variations/parallels of #{cnum_str} {player_name}.",
                    "Included_SKUs": ", ".join(chosen_skus),
                })
                lot_seq += 1

    non_base_sellable = sellable_cards[~sellable_cards["Subset"].str.upper().isin(("BASE", "BASE SET"))]
    for (set_name, sub_name), sub_df in non_base_sellable.groupby(["Set", "Subset"]):
        if len(sub_df) >= 3:
            chosen_skus = []
            raw_sum = 0.0
            for _, s_row in sub_df.iterrows():
                ck = s_row["Card_Key"]
                if surplus_skus_by_key.get(ck):
                    s_item = surplus_skus_by_key[ck][0]
                    chosen_skus.append(str(s_item["SKU"]))
                    raw_sum += _safe_float(s_item.get("Raw_Price"), 2.50)
            if len(chosen_skus) >= 3:
                rec_price = round(raw_sum * disc_mult, 2)
                recommendations.append({
                    "Lot_ID": f"LOT-{lot_seq:03d}",
                    "Lot_Category": "Parallel / Insert Lot",
                    "Set": set_name,
                    "Lot_Title": f"{set_name} {sub_name} Parallel/Insert Lot ({len(chosen_skus)} Cards)",
                    "Unique_Cards": len(chosen_skus),
                    "Total_Cards": len(chosen_skus),
                    "Sum_Individual_Raw_USD": round(raw_sum, 2),
                    "Recommended_Lot_Price_USD": rec_price,
                    "Pricing_Strategy": f"-{lot_discount_pct:.0f}% Parallel Lot Discount",
                    "Rationale": f"{len(chosen_skus)} unique '{sub_name}' cards with duplicate copies in inventory.",
                    "Included_SKUs": ", ".join(chosen_skus),
                })
                lot_seq += 1

    # CATEGORY 4: HIGH-DUPLICATE SINGLE-CARD / PLAYER INVESTOR LOTS (4+ SURPLUS COPIES)
    high_dups = sellable_cards[sellable_cards["Surplus_Sellable_Qty"] >= 4].copy()
    for _, d_row in high_dups.iterrows():
        ck = d_row["Card_Key"]
        surplus_list = surplus_skus_by_key.get(ck, [])
        if len(surplus_list) < 4:
            continue
        lot_qty = min(10, len(surplus_list))
        picked_items = surplus_list[:lot_qty]
        skus_str = ", ".join(str(x["SKU"]) for x in picked_items)
        raw_sum = sum(_safe_float(x.get("Raw_Price"), 1.50) for x in picked_items)
        rec_price = max(3.99, round(raw_sum * 0.80, 2))
        recommendations.append({
            "Lot_ID": f"LOT-{lot_seq:03d}",
            "Lot_Category": "Multi-Copy Player Lot",
            "Set": d_row["Set"],
            "Lot_Title": f"({lot_qty}) {d_row['Set']} #{d_row['Card Number']} {d_row['Player']} [{d_row['Subset']}] Lot",
            "Unique_Cards": 1,
            "Total_Cards": lot_qty,
            "Sum_Individual_Raw_USD": round(raw_sum, 2),
            "Recommended_Lot_Price_USD": rec_price,
            "Pricing_Strategy": "-20% Multi-Copy Bulk Investor Lot",
            "Rationale": f"Moves {lot_qty} surplus copies of #{d_row['Card Number']} {d_row['Player']} in one transaction while keeping {d_row['Target_Retain_Qty']} in PC.",
            "Included_SKUs": skus_str,
        })
        lot_seq += 1

    rec_df = pd.DataFrame(recommendations, columns=cols)
    if not rec_df.empty:
        try:
            with open(RECOMMENDED_LOTS_FILE, "w", encoding="utf-8") as f:
                json.dump(recommendations, f, indent=2)
        except Exception:
            pass
    return rec_df


# ==============================================================================
# 3. ITEM #10: LISTING WRITER AGENT (HUMAN-WRITTEN BIO, STATS & ACCOLADES)
# ==============================================================================
def load_player_bios_cache() -> dict[str, dict]:
    """Loads cached web player bios, stats, and accolades from Inventory/player_bios_cache.json."""
    ensure_directories()
    if not PLAYER_BIOS_CACHE_FILE.exists():
        return {}
    try:
        with open(PLAYER_BIOS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_player_bios_cache(cache_map: dict[str, dict]) -> dict[str, dict]:
    ensure_directories()
    try:
        with open(PLAYER_BIOS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_map, f, indent=2)
    except Exception:
        pass
    return cache_map


def _fetch_mlb_stats_and_awards(player_name: str) -> dict[str, str]:
    """
    Queries the official MLB StatsAPI (statsapi.mlb.com) for a player's position,
    career/season statistics, and official awards/accolades (All-Star, MVP, Gold Glove,
    Silver Slugger, Rookie of the Year, World Series, etc.), written in natural collector prose.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    out = {"stats_summary": "", "accolades": "", "mlb_bio_line": ""}
    try:
        s_url = f"https://statsapi.mlb.com/api/v1/people/search?names={quote(player_name)}"
        resp = _bio_adaptive_get("mlb_statsapi", s_url, headers=headers, timeout=6)
        if not resp or resp.status_code != 200:
            return out
        people = (resp.json() or {}).get("people") or []
        if not people:
            return out

        person_id = people[0].get("id")
        if not person_id:
            return out

        d_url = (
            f"https://statsapi.mlb.com/api/v1/people/{person_id}"
            "?hydrate=awards,stats(group=[hitting,pitching],type=[career,yearByYear]),currentTeam"
        )
        d_resp = _bio_adaptive_get("mlb_statsapi", d_url, headers=headers, timeout=7)
        if not d_resp or d_resp.status_code != 200:
            return out
        p_data = ((d_resp.json() or {}).get("people") or [{}])[0]

        full_name = strip_accents(str(p_data.get("fullName") or player_name)).strip()
        pos_name = str((p_data.get("primaryPosition") or {}).get("name") or "").strip()
        curr_team = strip_accents(str((p_data.get("currentTeam") or {}).get("name") or "")).strip()
        debut = str(p_data.get("mlbDebutDate") or "").strip()
        bat_side = str((p_data.get("batSide") or {}).get("description") or "").strip()
        pitch_hand = str((p_data.get("pitchHand") or {}).get("description") or "").strip()

        bio_sentence = f"{full_name} is a {pos_name.lower() or 'ballplayer'}"
        if curr_team:
            bio_sentence += f" for the {curr_team}"
        if debut:
            bio_sentence += f" who made his big-league debut in {debut[:4]}"
        if bat_side and pitch_hand:
            bio_sentence += f" (bats {bat_side.lower()}, throws {pitch_hand.lower()})"
        out["mlb_bio_line"] = bio_sentence + "."

        awards_raw = p_data.get("awards") or []
        major_award_counts: dict[str, int] = defaultdict(int)
        for aw in awards_raw:
            aw_name = strip_accents(str(aw.get("name") or "")).strip()
            up_aw = aw_name.upper()
            if "ALL-STAR" in up_aw and ("AL " in up_aw or "NL " in up_aw or "MLB" in up_aw):
                major_award_counts["MLB All-Star"] += 1
            elif "MOST VALUABLE PLAYER" in up_aw and ("AL " in up_aw or "NL " in up_aw):
                major_award_counts["MVP"] += 1
            elif "CY YOUNG" in up_aw:
                major_award_counts["Cy Young Award winner"] += 1
            elif "ROOKIE OF THE YEAR" in up_aw or "BBWAA ROOKIE" in up_aw:
                major_award_counts["Rookie of the Year"] += 1
            elif "SILVER SLUGGER" in up_aw:
                major_award_counts["Silver Slugger"] += 1
            elif "GOLD GLOVE" in up_aw:
                major_award_counts["Gold Glove winner"] += 1
            elif "WORLD SERIES CHAMPION" in up_aw:
                major_award_counts["World Series Champion"] += 1
            elif "HALL OF FAME" in up_aw:
                major_award_counts["Baseball Hall of Fame inductee"] += 1
            elif "ALL-MLB" in up_aw:
                major_award_counts["All-MLB selection"] += 1
            elif "FUTURES GAME" in up_aw:
                major_award_counts["All-Star Futures Game selection"] += 1

        accolade_pills = []
        for aw_label, cnt in major_award_counts.items():
            if "Hall of Fame" in aw_label:
                accolade_pills.append("Baseball Hall of Fame inductee")
            elif cnt > 1:
                accolade_pills.append(f"{cnt}x {aw_label}")
            else:
                accolade_pills.append(aw_label)
        if accolade_pills:
            out["accolades"] = ", ".join(accolade_pills[:7])

        stats_list = p_data.get("stats") or []
        is_pitcher = "PITCHER" in pos_name.upper() or pos_name.upper() == "TWO-WAY PLAYER"
        is_hitter = not ("PITCHER" in pos_name.upper() and pos_name.upper() != "TWO-WAY PLAYER")

        stat_parts = []
        for s_block in stats_list:
            grp = str((s_block.get("group") or {}).get("displayName") or "").lower()
            s_type = str((s_block.get("type") or {}).get("displayName") or "").lower()
            splits = s_block.get("splits") or []
            if not splits:
                continue

            if s_type == "career":
                st = splits[-1].get("stat") or {}
                if grp == "hitting" and is_hitter and int(st.get("gamesPlayed", 0) or 0) > 0:
                    stat_parts.append(
                        f"Across {st.get('gamesPlayed', 0)} career MLB games, he has posted a {st.get('avg', '.---')} batting average "
                        f"with {st.get('homeRuns', 0)} home runs, {st.get('rbi', 0)} RBIs, {st.get('hits', 0)} hits, and a {st.get('ops', '.---')} OPS."
                    )
                elif grp == "pitching" and is_pitcher and int(st.get("gamesPlayed", 0) or 0) > 0:
                    stat_parts.append(
                        f"On the mound, he holds a {st.get('wins', 0)}-{st.get('losses', 0)} career record with a {st.get('era', '-.--')} ERA, "
                        f"{st.get('strikeOuts', 0)} strikeouts, and a {st.get('whip', '-.--')} WHIP over {st.get('inningsPitched', '0.0')} innings pitched."
                    )
            elif s_type == "yearbyyear" and splits:
                last_split = splits[-1]
                yr_s = str(last_split.get("season") or "")
                st = last_split.get("stat") or {}
                if grp == "hitting" and is_hitter and int(st.get("gamesPlayed", 0) or 0) >= 10:
                    stat_parts.append(
                        f"In {yr_s}, he hit {st.get('avg', '.---')} with {st.get('homeRuns', 0)} HRs, {st.get('rbi', 0)} RBIs, and a {st.get('ops', '.---')} OPS."
                    )
                elif grp == "pitching" and is_pitcher and int(st.get("gamesPlayed", 0) or 0) >= 3:
                    stat_parts.append(
                        f"In {yr_s}, he went {st.get('wins', 0)}-{st.get('losses', 0)} with a {st.get('era', '-.--')} ERA and {st.get('strikeOuts', 0)} strikeouts."
                    )

        if stat_parts:
            out["stats_summary"] = " ".join(stat_parts[:2])
    except Exception:
        pass
    return out


def _fetch_wikipedia_player_bio(player_name: str, sport_hint: str = "baseball") -> str:
    """
    Fetches a clean 2-sentence player biography from Wikipedia's REST API,
    stripping phonetic pronunciation clutter so it reads naturally.
    """
    headers = {"User-Agent": "TabulasCardHub/1.0 (https://localhost; support@tabulas.local)"}
    clean_name = strip_accents(player_name).strip()
    candidates = [
        clean_name.replace(" ", "_"),
        f"{clean_name.replace(' ', '_')}_({sport_hint}_player)",
        f"{clean_name.replace(' ', '_')}_(baseball)",
        f"{clean_name.replace(' ', '_')}_(American_football)",
        f"{clean_name.replace(' ', '_')}_(basketball)",
    ]
    for slug in candidates:
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(slug)}"
            resp = _bio_adaptive_get("wikipedia", url, headers=headers, timeout=5)
            if not resp or resp.status_code != 200:
                continue
            data = resp.json() or {}
            if data.get("type") == "disambiguation":
                continue
            extract = strip_accents(str(data.get("extract") or "")).strip()
            if len(extract) < 40:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", extract)
            bio_short = " ".join(sentences[:2]).strip()
            bio_short = re.sub(r"\s*\([^)]*born\s+[^)]*\)", "", bio_short)
            return re.sub(r"\s+", " ", bio_short).strip()
        except Exception:
            continue
    return ""


def fetch_and_cache_player_profile(
    player_name: str,
    team_name: str = "",
    set_name: str = "",
    force_refresh: bool = False,
    cache_ttl_days: int = 14,
) -> dict[str, str]:
    """
    Retrieves (or refreshes from the web) a player's standard biography, career/season stats,
    and career accolades. Supports multi-player cards ('/' separated).
    """
    cache_map = load_player_bios_cache()
    players = [p.strip() for p in strip_accents(str(player_name or "")).split("/") if p.strip()]
    if not players:
        return {"bio": "", "stats": "", "accolades": ""}

    sport_hint = "baseball"
    if "football" in set_name.lower() or "nfl" in set_name.lower():
        sport_hint = "American_football"
    elif "basketball" in set_name.lower() or "nba" in set_name.lower():
        sport_hint = "basketball"

    bios_out = []
    stats_out = []
    accolades_out = []
    cache_updated = False
    now_ep = time.time()

    for p_single in players[:3]:
        p_key = norm(p_single)
        if not p_key or p_key in ("UNKNOWNPLAYER", "CHECKLIST") or p_key.startswith("CHECKLISTTEAMCARD"):
            continue
        cached_entry = cache_map.get(p_key)
        is_fresh = False
        if cached_entry and not force_refresh:
            age_days = (now_ep - float(cached_entry.get("updated_epoch", 0.0))) / 86400.0
            if age_days <= float(cache_ttl_days) and cached_entry.get("bio"):
                is_fresh = True

        if not is_fresh:
            mlb_info = (
                _fetch_mlb_stats_and_awards(p_single)
                if sport_hint == "baseball"
                else {"stats_summary": "", "accolades": "", "mlb_bio_line": ""}
            )
            wiki_bio = _fetch_wikipedia_player_bio(p_single, sport_hint=sport_hint)
            final_bio = wiki_bio or mlb_info.get("mlb_bio_line") or ""
            cached_entry = {
                "player": p_single,
                "bio": final_bio,
                "stats": mlb_info.get("stats_summary", ""),
                "accolades": mlb_info.get("accolades", ""),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "updated_epoch": now_ep,
            }
            cache_map[p_key] = cached_entry
            cache_updated = True

        if cached_entry.get("bio"):
            bios_out.append(cached_entry["bio"])
        if cached_entry.get("stats"):
            stats_out.append(f"{p_single}: {cached_entry['stats']}" if len(players) > 1 else cached_entry["stats"])
        if cached_entry.get("accolades"):
            accolades_out.append(
                f"{p_single} ({cached_entry['accolades']})" if len(players) > 1 else cached_entry["accolades"]
            )

    if cache_updated:
        save_player_bios_cache(cache_map)

    return {
        "bio": " ".join(bios_out),
        "stats": " ".join(stats_out),
        "accolades": ", ".join(accolades_out),
    }


def extract_card_back_blurb_and_accolades(card_row: dict, force_web_refresh: bool = False) -> dict[str, str]:
    """
    Fetches standard web-sourced player biography, official career/season statistics,
    and career accolades for a card.
    """
    player_raw = strip_accents(str(card_row.get("Player", ""))).strip()
    team_raw = strip_accents(str(card_row.get("Team", ""))).strip()
    set_name = str(card_row.get("Set", "")).strip()

    profile = fetch_and_cache_player_profile(
        player_name=player_raw,
        team_name=team_raw,
        set_name=set_name,
        force_refresh=force_web_refresh,
    )
    return {
        "accolades": profile.get("accolades", ""),
        "card_back_blurb": profile.get("bio", ""),
        "stats_summary": profile.get("stats", ""),
    }


def load_set_blurbs_cache() -> dict[str, dict]:
    ensure_directories()
    if not SET_BLURBS_CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(SET_BLURBS_CACHE_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_set_blurbs_cache(cache_map: dict[str, dict]) -> dict[str, dict]:
    ensure_directories()
    try:
        SET_BLURBS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SET_BLURBS_CACHE_FILE.write_text(json.dumps(cache_map, indent=2), encoding="utf-8")
    except Exception:
        pass
    return cache_map


def save_custom_set_blurb(set_name: str, blurb_text: str) -> dict:
    clean_set = strip_accents(str(set_name or "")).strip()
    if not clean_set:
        return {"set": "", "blurb": ""}
    cache_map = load_set_blurbs_cache()
    s_key = norm(clean_set)
    entry = {
        "set": clean_set,
        "blurb": str(blurb_text or "").strip(),
        "is_custom": True,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    cache_map[s_key] = entry
    save_set_blurbs_cache(cache_map)
    return entry


def _build_default_set_blurb(set_name: str) -> str:
    s_clean = strip_accents(str(set_name or "")).strip()
    low = s_clean.lower()
    m_yr = re.search(r"\b((?:19|20)\d{2}(?:-\d{2})?)\b", s_clean)
    yr_s = m_yr.group(1) if m_yr else ""

    if "allen" in low and "ginter" in low:
        return (
            f"The {s_clean} release continues Topps' beloved vintage-inspired tobacco-card tradition, "
            "pairing MLB stars and rookies with pop-culture icons, world champions, and framed mini inserts on classic textured card stock."
        )
    if "chrome" in low and "sapphire" in low:
        return (
            f"{s_clean} is Topps' ultra-limited online-exclusive cracked-ice Chromium release, "
            "highly sought after by collectors for its signature blue-sapphire refractor finish and low-numbered parallels."
        )
    if "chrome" in low and "topps" in low:
        return (
            f"{s_clean} brings the flagship checklist onto premium Chromium card stock, "
            "featuring refractor rainbows, rookie debuts, and crisp metallic photography prized by modern collectors."
        )
    if "heritage" in low:
        return (
            f"{s_clean} honors classic vintage Topps card design on traditional heritage paper stock, "
            "blending nostalgic throwback styling with today's top rookies, short prints, and image variations."
        )
    if "bowman" in low:
        return (
            f"{s_clean} is the premier hobby showcase for baseball's top prospects and 1st Bowman debuts, "
            "combining crisp paper and Chrome cards with sought-after parallel rainbows."
        )
    if "prizm" in low:
        return (
            f"{s_clean} is Panini's flagship opti-chrome release, renowned across the hobby for its vibrant "
            "Prizm parallels, sharp action photography, and strong long-term collector demand."
        )
    if "topps" in low and "baseball" in low:
        return (
            f"{s_clean} is the cornerstone flagship baseball release of the {yr_s or 'modern'} collecting season, "
            "showcasing the league's biggest superstars, key Rookie Cards, foil parallels, and classic hobby inserts."
        )
    return (
        f"From the {s_clean} release, this officially licensed trading card highlights standout players, "
        "crisp photography, and collectible design details favored by set builders and player collectors alike."
    )


def fetch_and_cache_set_blurb(set_name: str, force_refresh: bool = False, reset_to_default: bool = False) -> dict:
    """Returns cached or newly generated collector prose blurb for a Card Set."""
    clean_set = strip_accents(str(set_name or "")).strip()
    if not clean_set:
        return {"set": "", "blurb": "", "is_custom": False}
    cache_map = load_set_blurbs_cache()
    s_key = norm(clean_set)
    existing = cache_map.get(s_key)
    if not reset_to_default and existing and existing.get("blurb") and (not force_refresh or existing.get("is_custom")):
        return existing

    blurb = _build_default_set_blurb(clean_set)
    entry = {
        "set": clean_set,
        "blurb": blurb,
        "is_custom": False,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    cache_map[s_key] = entry
    save_set_blurbs_cache(cache_map)
    return entry


def build_seo_listing_title(card_row: dict, max_len: int = 80) -> str:
    """
    Constructs a high-converting eBay / CollX SEO title strictly <= 80 characters:
      '{Set} #{CardNumber} {Player} {RC/ASR/Auto} {Subset} {#/PrintRun} {Team}'
    """
    set_raw = strip_accents(str(card_row.get("Set", ""))).strip()
    set_short = re.sub(r"\b(Baseball|Football|Basketball|Hockey|Soccer)\b", "", set_raw, flags=re.IGNORECASE).strip()
    cnum = str(card_row.get("Card Number") or card_row.get("Card_Number") or "").strip().lstrip("#")
    player = strip_accents(str(card_row.get("Player", ""))).strip()
    subset = strip_accents(str(card_row.get("Subset") or card_row.get("Subset_Parallel") or "Base")).strip()
    team = strip_accents(str(card_row.get("Team", ""))).strip()
    pr = format_print_run(card_row.get("Print Run") or card_row.get("Print_Run") or "")
    attrs = str(card_row.get("Attributes", "")).upper()

    pr_tag = "1/1" if pr == "1" else (f"#/{pr}" if pr else "")
    sub_tag = "" if subset.upper() in ("BASE", "BASE SET") else subset
    rc_badge = "RC" if re.search(r"\bRC\b", attrs) and "RC" not in player.upper() else (
        "All-Star Rookie" if re.search(r"\bASR\b", attrs) else ""
    )

    parts = [set_short, f"#{cnum}" if cnum else "", player, rc_badge]
    if sub_tag:
        parts.append(sub_tag)
    if pr_tag and pr_tag not in sub_tag:
        parts.append(pr_tag)
    if team and team.upper() != "NO TEAM" and team.lower() not in player.lower():
        parts.append(team)

    full_title = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    if len(full_title) <= max_len:
        return full_title

    if team and " " in team:
        nick = team.split()[-1]
        parts_nick = [set_short, f"#{cnum}" if cnum else "", player, sub_tag, pr_tag, nick]
        cand_nick = re.sub(r"\s+", " ", " ".join(p for p in parts_nick if p)).strip()
        if len(cand_nick) <= max_len:
            return cand_nick

    parts_no_tm = [set_short, f"#{cnum}" if cnum else "", player, sub_tag, pr_tag]
    cand_no_tm = re.sub(r"\s+", " ", " ".join(p for p in parts_no_tm if p)).strip()
    if len(cand_no_tm) <= max_len:
        return cand_no_tm

    return cand_no_tm[:max_len].rsplit(" ", 1)[0].strip()


def generate_card_listing_copy(
    card_row: dict,
    platform: str = "eBay & CollX",
    include_pregrade_notes: bool = True,
    extract_back_ocr_blurb: bool = True,
    force_web_refresh: bool = False,
    shipping_policy_note: str = DEFAULT_SHIPPING_POLICY_NOTE,
    content_options: Optional[dict] = None,
    custom_set_blurb: Optional[str] = None,
) -> dict[str, str]:
    """
    Item #10: Generates natural, human-sounding collector listing copy for a single physical card SKU,
    respecting granular `content_options` toggles (opening, set blurb, player bio, stats, accolades,
    scanner pre-grade notes, computer-grading disclaimer, shipping policy, 48h as-is disclaimer, SKU ref).
    """
    opts = dict(DEFAULT_LISTING_CONTENT_OPTIONS)
    opts["include_pregrade_notes"] = bool(include_pregrade_notes)
    if not extract_back_ocr_blurb:
        opts["include_player_bio"] = False
        opts["include_player_stats"] = False
        opts["include_player_accolades"] = False
    if isinstance(content_options, dict):
        for k, v in content_options.items():
            if k in opts:
                opts[k] = bool(v)

    sku_str = str(card_row.get("SKU", "")).strip()
    set_name = strip_accents(str(card_row.get("Set", ""))).strip()
    sub_name = strip_accents(str(card_row.get("Subset") or card_row.get("Subset_Parallel") or "Base")).strip()
    cnum_str = str(card_row.get("Card Number") or card_row.get("Card_Number") or "").strip().lstrip("#")
    player_name = strip_accents(str(card_row.get("Player", ""))).strip()
    team_name = strip_accents(str(card_row.get("Team", ""))).strip()
    pr_str = format_print_run(card_row.get("Print Run") or card_row.get("Print_Run") or "")
    rec_price = str(card_row.get("Rec_Sale_Price") or card_row.get("Raw_Price") or "2.00").strip()
    hold_tag = str(card_row.get("Hold_Tag", "For Sale")).strip()

    seo_title = build_seo_listing_title(card_row, max_len=80)
    need_player_web = opts["include_player_bio"] or opts["include_player_stats"] or opts["include_player_accolades"]
    blurb_data = (
        extract_card_back_blurb_and_accolades(card_row, force_web_refresh=force_web_refresh)
        if need_player_web
        else {"accolades": "", "card_back_blurb": "", "stats_summary": ""}
    )

    set_blurb_text = ""
    if opts["include_set_blurb"]:
        if custom_set_blurb and str(custom_set_blurb).strip():
            set_blurb_text = str(custom_set_blurb).strip()
        elif set_name:
            set_blurb_text = fetch_and_cache_set_blurb(set_name).get("blurb", "")

    is_base = sub_name.upper() in ("BASE", "BASE SET")
    team_phrase = f" ({team_name})" if team_name and team_name.upper() != "NO TEAM" else ""
    pr_phrase = (
        ", a 1/1 One-of-One"
        if pr_str == "1"
        else (f", serial-numbered #/{pr_str}" if pr_str else "")
    )

    paragraphs = []
    if opts["include_opening"]:
        if is_base:
            opening_line = (
                f"Up for sale is a {set_name} #{cnum_str} {player_name}{team_phrase} Base card{pr_phrase}. "
                f"This card was pulled, sleeved immediately, and scanned directly in its holder."
            )
        else:
            opening_line = (
                f"Up for sale is a {set_name} #{cnum_str} {player_name}{team_phrase} {sub_name}{pr_phrase}. "
                f"A great addition to any {player_name}{(' or ' + team_name) if team_name and team_name.upper() != 'NO TEAM' else ''} collection or set build."
            )
        if "Make Me an Offer" in hold_tag:
            opening_line += " Feel free to send over a reasonable offer if you're looking to add this one to your collection."
        paragraphs.append(opening_line)

    if opts["include_set_blurb"] and set_blurb_text:
        paragraphs.append(f"About the Set: {set_blurb_text}")

    player_sentences = []
    if opts["include_player_bio"] and blurb_data.get("card_back_blurb"):
        player_sentences.append(blurb_data["card_back_blurb"].strip())
    if opts["include_player_stats"] and blurb_data.get("stats_summary"):
        player_sentences.append(blurb_data["stats_summary"].strip())
    if opts["include_player_accolades"] and blurb_data.get("accolades"):
        player_sentences.append(f"Career honors include: {blurb_data['accolades'].strip()}.")
    if player_sentences:
        paragraphs.append(" ".join(player_sentences))

    cond_sentences = []
    if opts["include_pregrade_notes"]:
        est_psa = str(card_row.get("Est_PSA", "")).strip()
        est_bgs = str(card_row.get("Est_BGS", "")).strip()
        cent_lr = str(card_row.get("Centering_LR", "")).strip()
        cent_tb = str(card_row.get("Centering_TB", "")).strip()
        g_notes = str(card_row.get("Grading_Notes", "")).strip()
        details_bits = []
        if cent_lr or cent_tb:
            details_bits.append(f"centering around {cent_lr or '50/50'} L/R and {cent_tb or '50/50'} T/B")
        if est_psa or est_bgs:
            details_bits.append(f"an automated pre-grade estimate of PSA {est_psa or '9.0'} / BGS {est_bgs or '9.0'}")
        if details_bits:
            cond_sentences.append(f"Condition Notes: Our scanner check measured {' with '.join(details_bits)}.")
        if g_notes:
            cond_sentences.append(f"Inspection notes: {g_notes}.")
    if opts["include_grading_disclaimer"]:
        cond_sentences.append(COMPUTER_GRADING_DISCLAIMER)
    if cond_sentences:
        paragraphs.append(" ".join(cond_sentences))

    if opts["include_shipping_policy"]:
        paragraphs.append(f"Shipping & Packaging: {shipping_policy_note}")
    if opts["include_as_is_disclaimer"]:
        paragraphs.append(AS_IS_48HR_DISCLAIMER)
    if opts["include_sku_ref"] and sku_str:
        paragraphs.append(f"Inventory Ref: {sku_str}")

    return {
        "SEO_Title_80Char": seo_title,
        "Description_Body": "\n\n".join(paragraphs),
        "Recommended_Price": rec_price,
        "Set_Blurb": set_blurb_text,
        "Accolades": blurb_data.get("accolades", ""),
        "Card_Back_Blurb": blurb_data.get("card_back_blurb", ""),
        "Stats_Summary": blurb_data.get("stats_summary", ""),
    }


def generate_lot_listing_copy(lot_row: dict, inv_df: pd.DataFrame) -> dict[str, str]:
    """Generates custom SEO title and description for a recommended Set, Team Lot, or Rainbow Lot."""
    lot_title_raw = strip_accents(str(lot_row.get("Lot_Title", "Trading Card Lot"))).strip()
    seo_title = lot_title_raw[:80].rsplit(" ", 1)[0] if len(lot_title_raw) > 80 else lot_title_raw

    skus_list = [s.strip() for s in str(lot_row.get("Included_SKUs", "")).split(",") if s.strip()]
    lot_cards_df = inv_df[inv_df["SKU"].isin(skus_list)] if (inv_df is not None and not inv_df.empty) else pd.DataFrame()

    card_bullet_lines = []
    if not lot_cards_df.empty:
        for _, r in lot_cards_df.head(35).iterrows():
            pr = format_print_run(r.get("Print Run", ""))
            pr_s = f" (#/{pr})" if pr else ""
            card_bullet_lines.append(
                f"  - #{r.get('Card Number','')} {r.get('Player','')} [{r.get('Subset','Base')}]{pr_s} (SKU {r.get('SKU','')})"
            )
        if len(lot_cards_df) > 35:
            card_bullet_lines.append(f"  - ... plus {len(lot_cards_df) - 35} additional cards in this lot!")

    body_lines = [
        f"Up for sale is a {lot_title_raw} from {lot_row.get('Set', '')} ({lot_row.get('Total_Cards', len(skus_list))} total cards, {lot_row.get('Unique_Cards', len(skus_list))} unique).",
        "",
        "Cards Included in This Lot:",
        *(card_bullet_lines or ["  - Complete bundle as titled"]),
        "",
        f"Condition Note: {COMPUTER_GRADING_DISCLAIMER}",
        "",
        f"Shipping & Packaging: {DEFAULT_SHIPPING_POLICY_NOTE}",
        "",
        AS_IS_48HR_DISCLAIMER,
        f"Lot Ref: {lot_row.get('Lot_ID', 'LOT')}",
    ]
    return {
        "SEO_Title_80Char": seo_title,
        "Description_Body": "\n".join(body_lines),
        "Recommended_Price": f"{_safe_float(lot_row.get('Recommended_Lot_Price_USD'), 9.99):.2f}",
    }


def load_listing_drafts_df() -> pd.DataFrame:
    ensure_directories()
    if not LISTING_DRAFTS_FILE.exists():
        return pd.DataFrame(columns=LISTING_DRAFTS_COLUMNS)
    try:
        df = pd.read_csv(LISTING_DRAFTS_FILE, dtype=str, keep_default_na=False)
        for c in LISTING_DRAFTS_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        return df[LISTING_DRAFTS_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=LISTING_DRAFTS_COLUMNS)


def save_listing_drafts_df(df: pd.DataFrame) -> pd.DataFrame:
    ensure_directories()
    out = df.copy()
    for c in LISTING_DRAFTS_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out.drop_duplicates(subset=["Draft_ID"], keep="last")[LISTING_DRAFTS_COLUMNS].reset_index(drop=True)
    out.to_csv(LISTING_DRAFTS_FILE, index=False, encoding="utf-8-sig")
    return out


def compute_expense_based_strategy_recommendations(inv_df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """
    Analyzes logged expenses (Inventory/Expenses.csv) against current For-Sale inventory
    to generate actionable pricing, floor, and break-even strategy recommendations.
    """
    if cfg is None:
        cfg = load_expenses_and_pricing_config()
    summary = compute_expense_and_cost_basis_summary(inv_df, cfg=cfg)
    strat = cfg.get("pricing_strategy", {})

    curr_floor = _safe_float(strat.get("global_min_price_floor"), 1.49)
    curr_markup = _safe_float(strat.get("market_markup_pct"), 50.0)
    avg_be = float(summary.get("avg_break_even_price", 1.25))
    avg_min = float(summary.get("avg_min_sale_price", 1.49))
    unit_cogs = float(summary.get("overall_unit_cogs", 0.25))
    total_exp = float(summary.get("total_expenses", 0.0))

    active_inv = inv_df[inv_df["Status"] != "Sold"].copy() if (inv_df is not None and not inv_df.empty) else pd.DataFrame()
    total_rec_val = (
        float(pd.to_numeric(active_inv.get("Rec_Sale_Price", active_inv.get("Raw_Price", 0.0)), errors="coerce").fillna(0.0).sum())
        if not active_inv.empty
        else 0.0
    )

    recommendations = []
    if curr_floor < avg_min:
        recommendations.append({
            "priority": "HIGH",
            "title": f"Raise Global Price Floor to ${avg_min:.2f}",
            "detail": (
                f"Your current floor (${curr_floor:.2f}) is below your cost-recovered minimum sale price "
                f"(${avg_min:.2f} based on ${unit_cogs:.2f}/card COGS + ${summary['supplies_per_order']:.2f} supplies/order)."
            ),
            "suggested_patch": {"global_min_price_floor": round(avg_min, 2)},
        })
    if total_exp > 0 and total_rec_val < total_exp * 1.25:
        target_mk = round(min(150.0, max(curr_markup + 15.0, 60.0)), 1)
        recommendations.append({
            "priority": "MEDIUM",
            "title": f"Increase Market Markup to {target_mk:.0f}% to Cover Overhead",
            "detail": (
                f"Total logged expenses (${total_exp:,.2f}) vs. projected sellable inventory value "
                f"(${total_rec_val:,.2f}) leaves a thin margin after marketplace fees. Raising markup to {target_mk:.0f}% improves net recovery."
            ),
            "suggested_patch": {"market_markup_pct": target_mk},
        })
    if summary.get("cards_to_break_even", 0) > max(1, len(active_inv)):
        recommendations.append({
            "priority": "INFO",
            "title": "Bundle Low-Dollar Commons into Team/Set Lots",
            "detail": (
                f"Selling singles individually requires ~{summary['cards_to_break_even']:,} sales to break even. "
                "Bundling sub-$2 cards into 10-25 card Team or Set Builder lots amortizes the $0.30 fixed fee and packaging cost."
            ),
            "suggested_patch": {},
        })
    if not recommendations:
        recommendations.append({
            "priority": "OK",
            "title": "Pricing Strategy Covers All Logged Expenses",
            "detail": (
                f"Your floor (${curr_floor:.2f}) exceeds break-even (${avg_be:.2f}) and your projected inventory "
                f"(${total_rec_val:,.2f}) comfortably covers logged expenses (${total_exp:,.2f})."
            ),
            "suggested_patch": {},
        })

    return {
        "summary": summary,
        "recommendations": recommendations,
    }
