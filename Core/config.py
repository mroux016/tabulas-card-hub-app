from __future__ import annotations
# ==============================================================================
# Core/config.py - CENTRALIZED PATHS, CONSTANTS, PSA/BGS MATRICES & VERSION REGISTRY
# ==============================================================================
import contextlib
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

__version__ = "0.24.0-beta.45"
__last_updated__ = "2026-11-21 15:05:00"
APP_RELEASE_VERSION = "0.24.0-beta.45"
APP_RELEASE_STAGE = "Pre-Release Beta"

_DEFAULT_HUB_DIR = r"C:\Tabulas Card Hub" if os.path.exists(r"C:\Tabulas Card Hub") else r"D:\OneDrive\Pictures\Cards"
BASE_DIR = Path(os.environ.get("CARDS_BASE_DIR", _DEFAULT_HUB_DIR))
IS_REORGANIZED_V24 = (BASE_DIR / "App").exists() or (BASE_DIR / "Data").exists() or (BASE_DIR / "Cache").exists()
APP_DIR = (BASE_DIR / "App") if (BASE_DIR / "App").exists() else BASE_DIR
CORE_DIR = APP_DIR / "Core"
TOOLS_DIR = (APP_DIR / "Tools") if (APP_DIR / "Tools").exists() else BASE_DIR
RUNTIME_DIR = (APP_DIR / "Runtime") if IS_REORGANIZED_V24 else BASE_DIR
BACKUP_SUBDIR = CORE_DIR / ".verified_backups"
FONTS_DIR = CORE_DIR / "fonts"
DOWNLOADED_FILES_DIR = CORE_DIR / "downloaded_files"
UPDATES_DIR = BASE_DIR / "Updates"

# Canonical registry of all 9 application modules and their expected pre-release versions
EXPECTED_MODULE_REGISTRY = [
    {
        "module_key": "Core.config",
        "rel_path": "Core/config.py",
        "role": "Core Configuration, Paths & Version Registry",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.database",
        "rel_path": "Core/database.py",
        "role": "1-Card-Per-Row Inventory, 7-Digit SKU & Checklist Engine",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.label_engine",
        "rel_path": "Core/label_engine.py",
        "role": "QR / SKU Label & R037L Alignment PDF Generator",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.scraper_engine",
        "rel_path": "Core/scraper_engine.py",
        "role": "TCDB Async/Stealth Template Scraper, CID Checklist & Library Tracker",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.rate_learner",
        "rel_path": "Core/rate_learner.py",
        "role": "Cross-Script Online Adaptive Rate, Window & Tier Learner",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.compute_backend",
        "rel_path": "Core/compute_backend.py",
        "role": "GPU/CPU Compute Layer (DirectML/CUDA RapidOCR, OpenCL Filters & VRAM Guardrails)",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.neural_vision",
        "rel_path": "Core/neural_vision.py",
        "role": "ONNX Deep Visual Embeddings & Local Offline Defect AI Foundation",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.vision_grader",
        "rel_path": "Core/vision_grader.py",
        "role": "4-Angle Back OCR, Flatbed Splitter, Template Matcher & PSA/BGS Grader",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.market_engine",
        "rel_path": "Core/market_engine.py",
        "role": "Grading Availability, SportsCardsPro Comps, Recommendation Engine & Set Completion",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "Core.sales_engine",
        "rel_path": "Core/sales_engine.py",
        "role": "Card-Level Rollup, Lot Recommender, COGS & Bio Listing Writer",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "cli",
        "rel_path": "cli.py",
        "role": "7-Lane Background Worker, Queue Engine, System Maintenance & Scheduler",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "launch_tabulas_hub",
        "rel_path": "launch_tabulas_hub.py",
        "role": "Standalone Desktop Window Launcher & Local REST API Server",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "App.jsx",
        "rel_path": "App.jsx",
        "role": "Chrome-Pulse React UI, Monitor Workspace & Live Hub Frontend",
        "expected_version": APP_RELEASE_VERSION,
    },
    {
        "module_key": "updater",
        "rel_path": "updater.py",
        "role": "Atomic Update Package Applicator, 5-Recent Archiver & Rollback Engine",
        "expected_version": APP_RELEASE_VERSION,
    },
]

INPUT_PATH = BASE_DIR / "Incoming_Scans"
FALLBACK_SCAN_PATH = BASE_DIR / "Raw_Scans"

ARCHIVE_DIR = BASE_DIR / "Archive"
ARCHIVE_SCAN_PATH = ARCHIVE_DIR / "Raw_Scans"
PROCESSED_ARCHIVE_DIR = ARCHIVE_DIR / "Committed_Batches"

INVENTORY_DIR = BASE_DIR / "Inventory"
INVENTORY_FILE = INVENTORY_DIR / "Inventory.csv"
ACTIVE_BATCH_FILE = INVENTORY_DIR / "Active_Staging_Batch.csv"
BATCHES_DIR = INVENTORY_DIR / "Batches"
LABELS_OUTPUT_DIR = INVENTORY_DIR / "Labels"

# Market / Valuation / Alert / Sales Cache Files
GRADING_TIERS_CACHE_FILE = INVENTORY_DIR / "grading_tiers_cache.json"
MARKET_COMPS_CACHE_FILE = INVENTORY_DIR / "market_comps_cache.csv"
COLLECTION_HISTORY_FILE = INVENTORY_DIR / "collection_value_history.csv"
MARKET_ALERTS_FILE = INVENTORY_DIR / "market_alerts.json"
MARKET_SETTINGS_FILE = INVENTORY_DIR / "market_alert_settings.json"
CARD_LEVEL_TARGETS_FILE = INVENTORY_DIR / "card_level_targets.json"
LISTING_DRAFTS_FILE = INVENTORY_DIR / "listing_drafts.csv"
RECOMMENDED_LOTS_FILE = INVENTORY_DIR / "recommended_lots.json"
EXPENSES_CSV_FILE = INVENTORY_DIR / "Expenses.csv"
EXPENSES_PRICING_CONFIG_FILE = INVENTORY_DIR / "expenses_and_pricing_config.json"
PLAYER_BIOS_CACHE_FILE = INVENTORY_DIR / "player_bios_cache.json"
NOTIFICATIONS_HISTORY_CSV = INVENTORY_DIR / "Notifications_History.csv"
SOLD_CARDS_CSV = INVENTORY_DIR / "Sold_Cards.csv"

NOTIFICATIONS_CSV_COLUMNS = [
    "Notification_ID",
    "Timestamp",
    "Category",
    "Title",
    "Message",
    "Severity",
    "Cleared",
]

SOLD_CARDS_CSV_COLUMNS = [
    "Sale_ID",
    "Sale_Date",
    "SKU",
    "Set",
    "Subset",
    "Card_Number",
    "Player",
    "Platform",
    "Sale_Price",
    "Shipping_Collected",
    "Marketplace_Fees",
    "Shipping_Cost",
    "Seller_Paid_Shipping",
    "Cost_Basis",
    "Net_Profit",
    "Notes",
]

EXPENSES_CSV_COLUMNS = [
    "ID",
    "Date",
    "Category",
    "Vendor",
    "Description",
    "Set Scope",
    "Cost",
]

CHECKLIST_DIR = BASE_DIR / "Checklists"
CHECKLIST_PATH = CHECKLIST_DIR / "Master_Checklist.csv"
CHECKLIST_BACKUP_PATH = CHECKLIST_DIR / "Master_Checklist_Backup.csv"
SET_CHECKLISTS_DIR = CHECKLIST_DIR / "Set_Checklists"

CHECKLIST_COLUMNS = [
    "Set",
    "Subset",
    "Card Number",
    "Player",
    "Team",
    "Print Run",
    "Attributes",
    "TCDB_CID",
    "Front_Downloaded",
    "Back_Downloaded",
    "TCDB_Image_Status",
]

# ==============================================================================
# 3-DRIVE ARCHITECTURE PATHS (C: Hub/Cache/Data/Logs, D: Pure Media, F: Archive)
# ==============================================================================
_DEFAULT_ARCHIVE = r"F:\Tabulas Archive" if (os.path.exists(r"F:\Tabulas Archive") or os.path.exists("F:\\")) else str(BASE_DIR / "Archive")
ARCHIVE_DIR = Path(os.environ.get("TABULAS_ARCHIVE_DIR", _DEFAULT_ARCHIVE))
ARCHIVE_SCAN_PATH = ARCHIVE_DIR / "Raw_Scans"
PROCESSED_ARCHIVE_DIR = ARCHIVE_DIR / "Committed_Batches"
ARCHIVE_LOGS_DIR = ARCHIVE_DIR / "Logs"
ARCHIVE_UPDATES_DIR = ARCHIVE_DIR / "Updates"
ARCHIVE_UPDATES_PACKAGES_DIR = ARCHIVE_UPDATES_DIR / "Packages"
ARCHIVE_UPDATES_SNAPSHOTS_DIR = ARCHIVE_UPDATES_DIR / "Snapshots"
ARCHIVE_CHECKLISTS_DIR = ARCHIVE_DIR / "Checklists_Snapshots"

_DEFAULT_SET_LIBRARY = r"D:\Tabulas Set Library" if (os.path.exists("D:\\") or not sys.platform.startswith("win")) else str(BASE_DIR / "Set_Templates")
_RAW_SET_LIB_ENV = Path(os.environ.get("TABULAS_SET_LIBRARY_DIR", _DEFAULT_SET_LIBRARY))
# Defensive guard: never allow a child worker to double-nest Reference_Library inside Reference_Library
SET_LIBRARY_ROOT = _RAW_SET_LIB_ENV.parent if _RAW_SET_LIB_ENV.name.lower() == "reference_library" else _RAW_SET_LIB_ENV
LEGACY_SET_TEMPLATES_DIR = BASE_DIR / "Set_Templates"

# Singular unified Cache & Daily Logs structure on C:
CACHE_DIR = BASE_DIR / "Cache"
CACHE_LIBRARY_DIR = CACHE_DIR / "Library"
CACHE_CATALOGS_DIR = CACHE_LIBRARY_DIR / "Catalogs"
CACHE_CHECKLISTS_DIR = CACHE_DIR / "Checklists"
CACHE_INVENTORY_DIR = CACHE_DIR / "Inventory"
CACHE_SALES_MARKET_DIR = CACHE_DIR / "Sales_and_Market"
CACHE_SYSTEM_DIR = CACHE_DIR / "System"
CACHE_GRADING_DIAGNOSTICS_DIR = CACHE_DIR / "Grading_Diagnostics"
CACHE_GRADING_FEEDBACK_DIR = CACHE_DIR / "Grading_Feedback"
GRADING_FEEDBACK_LOG_FILE = CACHE_GRADING_FEEDBACK_DIR / "grading_feedback_log.jsonl"

LOGS_ROOT_DIR = BASE_DIR / "Logs"
DAILY_LOGS_ROOT = LOGS_ROOT_DIR / "Logs"
REPORTS_DIR = LOGS_ROOT_DIR / "Reports"
DATA_DIR = BASE_DIR / "Data"

if IS_REORGANIZED_V24 or (SET_LIBRARY_ROOT / "Reference_Library").exists():
    REVIEWED_CARDS_DIR = SET_LIBRARY_ROOT / "_My_Collection"
    UNPROCESSED_CARDS_DIR = SET_LIBRARY_ROOT / "Unprocessed_Cards"
    INPUT_PATH = UNPROCESSED_CARDS_DIR / "Incoming_Scans"
    BATCHES_DIR = UNPROCESSED_CARDS_DIR / "Batches"
    REFERENCE_TEMPLATES_DIR = SET_LIBRARY_ROOT / "Reference_Library"
else:
    REVIEWED_CARDS_DIR = BASE_DIR / "_Cards"
    UNPROCESSED_CARDS_DIR = BASE_DIR
    REFERENCE_TEMPLATES_DIR = SET_LIBRARY_ROOT

if IS_REORGANIZED_V24:
    LOGS_DIR = CACHE_SYSTEM_DIR
    SET_LIBRARY_CACHE_DIR = CACHE_LIBRARY_DIR

    INVENTORY_DIR = DATA_DIR / "Inventory_Management"
    INVENTORY_FILE = INVENTORY_DIR / "Inventory.csv"
    LABELS_OUTPUT_DIR = INVENTORY_DIR / "Labels"

    CHECKLIST_DIR = DATA_DIR / "Checklists_and_Resources"
    CHECKLIST_PATH = CHECKLIST_DIR / "Master_Checklist.csv"
    SET_CHECKLISTS_DIR = CHECKLIST_DIR / "Set_Checklists"
    MASTER_DIRECTORY_CSV_FILE = CHECKLIST_DIR / "TCDB_Set_Directory.csv"

    SALES_HUB_DIR = DATA_DIR / "Sales_Hub"
    SOLD_CARDS_CSV = SALES_HUB_DIR / "Sold_Cards.csv"
    LISTING_DRAFTS_FILE = SALES_HUB_DIR / "Listing_Drafts.csv"
    MARKET_COMPS_CACHE_FILE = SALES_HUB_DIR / "Market_Comps.csv"

    COLLECTION_DIR = DATA_DIR / "Collection"
    COLLECTION_HISTORY_FILE = COLLECTION_DIR / "Collection_Value_History.csv"

    BOOKKEEPING_DIR = DATA_DIR / "Bookkeeping"
    EXPENSES_CSV_FILE = BOOKKEEPING_DIR / "Expenses.csv"

    NOTIFICATIONS_HISTORY_CSV = LOGS_ROOT_DIR / "Notifications_History.csv"

    CHECKLIST_BACKUP_PATH = CACHE_CHECKLISTS_DIR / "Master_Checklist_Backup.csv"
    TRACKING_FILE = CACHE_CHECKLISTS_DIR / "tracked_sets.json"
    BN_TRACKING_FILE = CACHE_CHECKLISTS_DIR / "breakninja_sets.json"
    RESUME_FILE = CACHE_CHECKLISTS_DIR / "scraper_resume_state.json"
    SET_CART_JSON_FILE = CACHE_CHECKLISTS_DIR / "tcdb_set_cart.json"
    CHECKLIST_CACHE_FILE = CACHE_CHECKLISTS_DIR / "checklist_cache_v22.pkl"

    FEATURE_CACHE_FILE = CACHE_LIBRARY_DIR / "template_feature_cache_v22.pkl"
    DEAD_BACKS_CACHE_PATH = CACHE_LIBRARY_DIR / "tcdb_dead_backs_cache.json"
    DEAD_FRONTS_CACHE_PATH = CACHE_LIBRARY_DIR / "tcdb_dead_fronts_cache.json"
    CACHE_CHECKPOINTS_DIR = CACHE_CHECKLISTS_DIR / "Checkpoints"

    ACTIVE_BATCH_FILE = CACHE_INVENTORY_DIR / "Active_Staging_Batch.csv"
    BATCH_REVIEW_SELECTION_FILE = CACHE_INVENTORY_DIR / "batch_review_selection.json"

    GRADING_TIERS_CACHE_FILE = CACHE_SALES_MARKET_DIR / "grading_tiers_cache.json"
    MARKET_ALERTS_FILE = CACHE_SALES_MARKET_DIR / "market_alerts.json"
    MARKET_SETTINGS_FILE = CACHE_SALES_MARKET_DIR / "market_alert_settings.json"
    CARD_LEVEL_TARGETS_FILE = CACHE_SALES_MARKET_DIR / "card_level_targets.json"
    RECOMMENDED_LOTS_FILE = CACHE_SALES_MARKET_DIR / "recommended_lots.json"
    EXPENSES_PRICING_CONFIG_FILE = CACHE_SALES_MARKET_DIR / "pricing_strategy.json"
    PLAYER_BIOS_CACHE_FILE = CACHE_SALES_MARKET_DIR / "player_bios_cache.json"
else:
    LOGS_DIR = LOGS_ROOT_DIR
    SET_LIBRARY_CACHE_DIR = SET_LIBRARY_ROOT / "logs"
    SALES_HUB_DIR = INVENTORY_DIR
    COLLECTION_DIR = INVENTORY_DIR
    BOOKKEEPING_DIR = INVENTORY_DIR
    MASTER_DIRECTORY_CSV_FILE = REFERENCE_TEMPLATES_DIR / "tcdb_master_set_directory.csv"
    SET_CART_JSON_FILE = REFERENCE_TEMPLATES_DIR / "tcdb_set_cart.json"
    TRACKING_FILE = REFERENCE_TEMPLATES_DIR / "tracked_sets.json"
    BN_TRACKING_FILE = REFERENCE_TEMPLATES_DIR / "breakninja_sets.json"
    RESUME_FILE = REFERENCE_TEMPLATES_DIR / "scraper_resume_state.json"
    FEATURE_CACHE_FILE = SET_LIBRARY_CACHE_DIR / "template_feature_cache_v22.pkl"
    CHECKLIST_CACHE_FILE = SET_LIBRARY_CACHE_DIR / "checklist_cache_v22.pkl"
    DEAD_BACKS_CACHE_PATH = SET_LIBRARY_CACHE_DIR / "tcdb_dead_backs_cache.json"
    DEAD_FRONTS_CACHE_PATH = SET_LIBRARY_CACHE_DIR / "tcdb_dead_fronts_cache.json"
    CACHE_CHECKPOINTS_DIR = SET_LIBRARY_CACHE_DIR / "Checkpoints"
    BATCH_REVIEW_SELECTION_FILE = LOGS_DIR / "batch_review_selection.json"


def get_daily_log_dir(date_obj: Optional[datetime] = None) -> Path:
    """Returns `C:\\Tabulas Card Hub\\Logs\\Logs\\YYYYMMDD\\` and ensures it exists."""
    d_path = DAILY_LOGS_ROOT / (date_obj or datetime.now()).strftime("%Y%m%d")
    d_path.mkdir(parents=True, exist_ok=True)
    return d_path


# GPU Compute Settings, VRAM Worker Guardrail & Neural Vision Model Foundation Paths
NEURAL_MODELS_DIR = (CACHE_LIBRARY_DIR if IS_REORGANIZED_V24 else SET_LIBRARY_CACHE_DIR) / "Models"
NEURAL_EMBEDDINGS_CACHE_FILE = (CACHE_LIBRARY_DIR if IS_REORGANIZED_V24 else SET_LIBRARY_CACHE_DIR) / "neural_embeddings_v1.pkl"
COMPUTE_SETTINGS_FILE = LOGS_DIR / "compute_settings.json"
GPU_WORKER_CLAIMS_FILE = LOGS_DIR / "gpu_worker_claims.json"

# Standard TCDB Glossary & Card Attribute Definitions
TCDB_STANDARD_GLOSSARY = {
    "RC": "Rookie Card",
    "ASR": "All-Star Rookies",
    "LL": "League Leaders",
    "CPC": "Combo Player Cards",
    "TC": "Team Card",
    "FS": "Future Stars",
    "SP": "Short Print",
    "SSP": "Super Short Print",
    "VAR": "Variation",
    "Auto": "Autographed",
    "AU": "Autographed",
    "Mem": "Memorabilia / Relic",
    "MEM": "Memorabilia / Relic",
    "REL": "Relic",
    "SN": "Serial Numbered",
    "1/1": "One of One",
    "HOF": "Hall of Fame",
    "AS": "All-Star",
    "PRO": "Prospect",
    "DP": "Draft Pick",
    "FDP": "First Draft Pick",
    "ERR": "Error Card",
    "UER": "Uncorrected Error",
    "COR": "Corrected Error",
    "EXCH": "Exchange / Redemption",
}

# Virtual Environment Python Path (prefers consolidated .venv inside C:\Tabulas Card Hub)
_LOCAL_VENV_PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
_LEGACY_VENV_PY = Path(r"C:\Users\micha\tabulas_env\Scripts\python.exe")
TABULAS_VENV_PYTHON = Path(
    os.environ.get(
        "TABULAS_VENV_PYTHON",
        str(_LOCAL_VENV_PY) if _LOCAL_VENV_PY.exists() else str(_LEGACY_VENV_PY),
    )
)

SKU_START = 1000001

CARD_STATUS_OPTIONS = [
    "In Stock",
    "Listed",
    "Grading",
    "Sold",
    "PC / Hold",
]

HOLD_TAG_OPTIONS = [
    "For Sale",
    "Make Me an Offer",
    "Personal Collection (PC)",
]

# Standardized Batch Manifest & Master Inventory Columns (PSA & BGS Only)
BATCH_MANIFEST_COLUMNS = [
    "Scan_Order",
    "SKU",
    "Status",
    "Hold_Tag",
    "Needs_Review",
    "Set",
    "Subset_Parallel",
    "Card_Number",
    "Player",
    "Team",
    "Print_Run",
    "Attributes",
    "Copy_Number",
    "Centering_LR",
    "Centering_TB",
    "Sub_Centering",
    "Sub_Corners",
    "Sub_Edges",
    "Sub_Surface",
    "Est_Grade",
    "Est_PSA",
    "Est_BGS",
    "Grading_Notes",
    "Raw_Price",
    "Valuation_Source",
    "Min_Sale_Price",
    "Rec_Sale_Price",
    "PSA_9_Price",
    "BGS_9_5_Price",
    "PSA_10_Price",
    "Est_Graded_PSA",
    "Est_Graded_BGS",
    "EV_PSA",
    "EV_BGS",
    "Best_Grader",
    "Max_Net_Gain",
    "Recommended_Action",
    "Template_Similarity",
    "Top_3_Template_Candidates",
    "Valid_Checklist_Subsets",
    "OCR_Confidence",
    "OCR_Signals",
    "Front_File",
    "Back_File",
    "Corners_File",
    "Matched_Template_Front",
    "Matched_Template_Back",
    "Source_Batch",
    "Source_PDF",
    "Date_Added",
    "Label_Printed",
    "Manual_Override",
]

INVENTORY_COLUMNS = [
    "SKU",
    "Status",
    "Hold_Tag",
    "Set",
    "Subset",
    "Card Number",
    "Player",
    "Team",
    "Print Run",
    "Attributes",
    "Copy_Number",
    "Centering_LR",
    "Centering_TB",
    "Sub_Centering",
    "Sub_Corners",
    "Sub_Edges",
    "Sub_Surface",
    "Est_Grade",
    "Est_PSA",
    "Est_BGS",
    "Grading_Notes",
    "Raw_Price",
    "Valuation_Source",
    "Min_Sale_Price",
    "Rec_Sale_Price",
    "PSA_9_Price",
    "BGS_9_5_Price",
    "PSA_10_Price",
    "Est_Graded_PSA",
    "Est_Graded_BGS",
    "EV_PSA",
    "EV_BGS",
    "Best_Grader",
    "Max_Net_Gain",
    "Recommended_Action",
    "Front_File",
    "Back_File",
    "Corners_File",
    "Matched_Template_Front",
    "Matched_Template_Back",
    "OCR_Confidence",
    "Template_Similarity",
    "Needs_Review",
    "Label_Printed",
    "Date_Added",
    "Source_Batch",
]

# Runtime flags
RUNTIME_CONFIG = {
    "scanner_dpi": 600,
    "save_debug_overlays": False,
    "save_review_sheets": False,
    "enable_pregrade_estimation": True,
    "enable_cardsight_fallback": True,
    "ocr_top_tier_threshold": 185,
    "visual_confirm_threshold": 0.75,
    "full_set_visual_match_threshold": 0.80,
    "full_set_visual_margin": 0.020,
    "parallel_self_correct_margin": 0.025,
    "parallel_min_confidence": 0.75,
    "parallel_group_min_confidence": 0.78,
    "parallel_group_sample_limit": 40,
    "variation_override_margin": 0.045,
    "golden_mirror_min_gold_score": 0.22,
    "golden_mirror_min_back_sim": 0.74,
    "canvas_min_weave_score": 0.48,
    "canvas_strong_weave_score": 0.68,
    "mini_max_aspect_ratio": 0.635,
    "standard_min_aspect_ratio": 0.665,
    "mini_format_mismatch_penalty": -0.35,
    "mini_base_prior_bonus": 0.055,
    "ag_back_visual_weight": 0.78,
    "t1_base_low_vis_flag_threshold": 0.75,
    "back_ocr_early_exit_score": 110.0,
    "sn_exact_match_bonus": 0.12,
    "sn_mismatch_penalty": -0.25,
    "cmp_match_bonus": 0.035,
    "cardsight_fallback_ocr_threshold": 185,
    "default_raw_price": 1.00,
    "base_prior_bonus": 0.065,
    "insert_ordinary_prior_bonus": 0.045,
    "min_template_confidence": 0.72,
    "min_margin_over_runner_up": 0.015,
    "min_insert_parallel_raw_sim": 0.80,
    "min_insert_parallel_margin": 0.025,
}

# CardSightAI & Optional Market API Keys
CARDSIGHT_API_KEY = os.environ.get("CARDSIGHT_API_KEY", "")
PRICECHARTING_API_KEY = os.environ.get("PRICECHARTING_API_KEY", "")
CARDHEDGER_API_KEY = os.environ.get("CARDHEDGER_API_KEY", "")
CARDSIGHT_MAGIC_URL = "https://api.cardsight.ai/v1/magic"
CARDSIGHT_IDENTIFY_URL = "https://api.cardsight.ai/v1/identify/card/baseball"
CARDSIGHT_SPORT_ENDPOINTS = {
    "baseball": "https://api.cardsight.ai/v1/identify/card/baseball",
    "football": "https://api.cardsight.ai/v1/identify/card/football",
    "basketball": "https://api.cardsight.ai/v1/identify/card/basketball",
    "hockey": "https://api.cardsight.ai/v1/identify/card/hockey",
    "soccer": "https://api.cardsight.ai/v1/identify/card/soccer",
}

# Baseline Grading Fees (Updated dynamically from Dugout Vault Grading Tracker)
GRADING_FEES = {
    "PSA": 39.99,
    "BGS": 79.95,
}

DEFAULT_DUGOUT_VAULT_TIERS = {
    "PSA": [
        {"tier": "Value Bulk", "price": 24.99, "max_value": 500.0, "turnaround": "140-160 Bus. Days", "status": "paused"},
        {"tier": "Value", "price": 39.99, "max_value": 500.0, "turnaround": "90-100 Bus. Days", "status": "open"},
        {"tier": "Value Plus", "price": 49.99, "max_value": 1000.0, "turnaround": "45 Bus. Days", "status": "paused"},
        {"tier": "Standard", "price": 59.99, "max_value": 1000.0, "turnaround": "70-80 Bus. Days", "status": "open"},
        {"tier": "Value Max", "price": 64.99, "max_value": 1500.0, "turnaround": "35 Bus. Days", "status": "paused"},
        {"tier": "Priority", "price": 79.99, "max_value": 1500.0, "turnaround": "50-60 Bus. Days", "status": "open"},
        {"tier": "Express", "price": 199.00, "max_value": 2500.0, "turnaround": "20-30 Bus. Days", "status": "open"},
        {"tier": "Super Express", "price": 349.00, "max_value": 5000.0, "turnaround": "10-15 Bus. Days", "status": "open"},
        {"tier": "Premier", "price": 599.00, "max_value": 10000.0, "turnaround": "7-10 Bus. Days", "status": "open"},
    ],
    "BGS": [
        {"tier": "Base (no subgrades)", "price": 14.95, "max_value": 999999.0, "turnaround": "75+ Bus. Days", "status": "paused"},
        {"tier": "Base (with subgrades)", "price": 17.95, "max_value": 999999.0, "turnaround": "75+ Bus. Days", "status": "paused"},
        {"tier": "Standard", "price": 34.95, "max_value": 999999.0, "turnaround": "45 Bus. Days", "status": "paused"},
        {"tier": "Express", "price": 79.95, "max_value": 999999.0, "turnaround": "15 Bus. Days", "status": "open"},
        {"tier": "Priority", "price": 124.95, "max_value": 999999.0, "turnaround": "5 Bus. Days", "status": "open"},
    ],
}

DEFAULT_GRADE_MULTIPLIERS = {
    "PSA": {
        10.0: 4.80, 9.0: 1.85, 8.5: 1.35, 8.0: 1.05, 7.5: 0.88, 7.0: 0.78,
        6.5: 0.68, 6.0: 0.60, 5.5: 0.52, 5.0: 0.45, 4.5: 0.38, 4.0: 0.32,
        3.5: 0.27, 3.0: 0.22, 2.5: 0.18, 2.0: 0.15, 1.5: 0.12, 1.0: 0.10,
    },
    "BGS": {
        10.0: 6.50, 9.5: 3.60, 9.0: 1.70, 8.5: 1.25, 8.0: 0.95, 7.5: 0.82,
        7.0: 0.72, 6.5: 0.62, 6.0: 0.55, 5.5: 0.48, 5.0: 0.42, 4.5: 0.35,
        4.0: 0.30, 3.5: 0.25, 3.0: 0.20, 2.5: 0.16, 2.0: 0.13, 1.5: 0.11, 1.0: 0.09,
    },
}

PSA_PROB_MATRIX = {
    10.0: {10.0: 0.76, 9.0: 0.21, 8.5: 0.02, 8.0: 0.01},
    9.5:  {10.0: 0.42, 9.0: 0.50, 8.5: 0.05, 8.0: 0.03},
    9.0:  {10.0: 0.12, 9.0: 0.72, 8.5: 0.10, 8.0: 0.06},
    8.5:  {9.0: 0.25, 8.5: 0.48, 8.0: 0.22, 7.5: 0.05},
    8.0:  {9.0: 0.06, 8.5: 0.18, 8.0: 0.58, 7.5: 0.10, 7.0: 0.08},
    7.5:  {8.0: 0.22, 7.5: 0.46, 7.0: 0.24, 6.5: 0.08},
    7.0:  {8.0: 0.06, 7.5: 0.16, 7.0: 0.58, 6.5: 0.12, 6.0: 0.08},
    6.5:  {7.0: 0.22, 6.5: 0.46, 6.0: 0.24, 5.5: 0.08},
    6.0:  {7.0: 0.06, 6.5: 0.16, 6.0: 0.58, 5.5: 0.12, 5.0: 0.08},
    5.5:  {6.0: 0.22, 5.5: 0.46, 5.0: 0.24, 4.5: 0.08},
    5.0:  {6.0: 0.06, 5.5: 0.16, 5.0: 0.58, 4.5: 0.12, 4.0: 0.08},
    4.5:  {5.0: 0.22, 4.5: 0.46, 4.0: 0.24, 3.5: 0.08},
    4.0:  {5.0: 0.06, 4.5: 0.16, 4.0: 0.58, 3.5: 0.12, 3.0: 0.08},
    3.5:  {4.0: 0.22, 3.5: 0.46, 3.0: 0.24, 2.5: 0.08},
    3.0:  {4.0: 0.06, 3.5: 0.16, 3.0: 0.58, 2.5: 0.12, 2.0: 0.08},
    2.5:  {3.0: 0.22, 2.5: 0.46, 2.0: 0.24, 1.5: 0.08},
    2.0:  {3.0: 0.06, 2.5: 0.16, 2.0: 0.58, 1.5: 0.12, 1.0: 0.08},
    1.5:  {2.0: 0.22, 1.5: 0.52, 1.0: 0.26},
    1.0:  {1.5: 0.15, 1.0: 0.85},
}

BGS_PROB_MATRIX = {
    10.0: {10.0: 0.18, 9.5: 0.72, 9.0: 0.10},
    9.5:  {10.0: 0.04, 9.5: 0.72, 9.0: 0.20, 8.5: 0.04},
    9.0:  {9.5: 0.16, 9.0: 0.66, 8.5: 0.14, 8.0: 0.04},
    8.5:  {9.0: 0.18, 8.5: 0.62, 8.0: 0.16, 7.5: 0.04},
    8.0:  {8.5: 0.16, 8.0: 0.62, 7.5: 0.16, 7.0: 0.06},
    7.5:  {8.0: 0.16, 7.5: 0.62, 7.0: 0.16, 6.5: 0.06},
    7.0:  {7.5: 0.16, 7.0: 0.62, 6.5: 0.16, 6.0: 0.06},
    6.5:  {7.0: 0.16, 6.5: 0.62, 6.0: 0.16, 5.5: 0.06},
    6.0:  {6.5: 0.16, 6.0: 0.62, 5.5: 0.16, 5.0: 0.06},
    5.5:  {6.0: 0.16, 5.5: 0.62, 5.0: 0.16, 4.5: 0.06},
    5.0:  {5.5: 0.16, 5.0: 0.62, 4.5: 0.16, 4.0: 0.06},
    4.5:  {5.0: 0.16, 4.5: 0.62, 4.0: 0.16, 3.5: 0.06},
    4.0:  {4.5: 0.16, 4.0: 0.62, 3.5: 0.16, 3.0: 0.06},
    3.5:  {4.0: 0.16, 3.5: 0.62, 3.0: 0.16, 2.5: 0.06},
    3.0:  {3.5: 0.16, 3.0: 0.62, 2.5: 0.16, 2.0: 0.06},
    2.5:  {3.0: 0.16, 2.5: 0.62, 2.0: 0.16, 1.5: 0.06},
    2.0:  {2.5: 0.16, 2.0: 0.62, 1.5: 0.16, 1.0: 0.06},
    1.5:  {2.0: 0.18, 1.5: 0.62, 1.0: 0.20},
    1.0:  {1.5: 0.15, 1.0: 0.85},
}

LABEL_TEMPLATES = {
    "R037L": {
        "name": 'Spartan Industrial R037L (1.5" x 0.5", 100/sheet | 12mm Left Margin)',
        "page_w": 8.5,
        "page_h": 11.0,
        "cols": 5,
        "rows": 20,
        "label_w": 1.5,
        "label_h": 0.5,
        "margin_x": round(12.2 / 25.4, 6),
        "margin_x_left_mm": 12.2,
        "margin_x_right_mm": 13.2,
        "margin_y": 0.5,
        "pitch_x": 1.5,
        "pitch_y": 0.5,
    },
    "AVERY_5160": {
        "name": 'Avery 5160 / 8160 (2.625" x 1.0", 30/sheet)',
        "page_w": 8.5,
        "page_h": 11.0,
        "cols": 3,
        "rows": 10,
        "label_w": 2.625,
        "label_h": 1.0,
        "margin_x": 0.1875,
        "margin_y": 0.5,
        "pitch_x": 2.75,
        "pitch_y": 1.0,
    },
    "AVERY_5167": {
        "name": 'Avery 5167 / 8167 (1.75" x 0.5", 80/sheet)',
        "page_w": 8.5,
        "page_h": 11.0,
        "cols": 4,
        "rows": 20,
        "label_w": 1.75,
        "label_h": 0.5,
        "margin_x": 0.3,
        "margin_y": 0.5,
        "pitch_x": 2.05,
        "pitch_y": 0.5,
    },
}

CMP_SUBSET_HINTS = {
    "CMP123053": ("2026 Topps Baseball", "Base"),
    "CMP143271": ("2026 Topps Allen & Ginter Baseball", "Base"),
    "CMP143346": ("2026 Topps Allen & Ginter Baseball", "Base Mini"),
    "CMP143320": ("2026 Topps Allen & Ginter Baseball", "Base Mini Variation A&G Back"),
}

SET_ALIAS_MAP = {
    "2026TOPPSBASEBALL": "2026 Topps Baseball",
    "2026TOPPS": "2026 Topps Baseball",
    "2026TOPPSALLENGINTERBASEBALL": "2026 Topps Allen & Ginter Baseball",
    "2026TOPPSALLENANDGINTERBASEBALL": "2026 Topps Allen & Ginter Baseball",
    "2025TOPPSBASEBALL": "2025 Topps Baseball",
    "2025TOPPSALLENGINTERBASEBALL": "2025 Topps Allen & Ginter Baseball",
    "2025TOPPSALLENANDGINTERBASEBALL": "2025 Topps Allen & Ginter Baseball",
    "2026BOWMANBASEBALL": "2026 Bowman Baseball",
}

NON_BORDER_VARIANT_KEYWORDS = (
    "GOLDEN MIRROR",
    "TRUE PHOTO",
    "CLEAR",
    "ACETATE",
    "WOOD",
    "METAL",
    "CANVAS",
    "MINI",
    "RELIC",
    "AUTOGRAPH",
    "PRINTING PLATE",
    "FIRST CARD",
    "3D",
)


def strip_accents(val) -> str:
    if val is None:
        return ""
    s = str(val)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def norm(val) -> str:
    return re.sub(r"[^A-Z0-9]", "", strip_accents(val).upper())


def format_print_run(val) -> str:
    if val is None:
        return ""
    s = strip_accents(str(val)).strip().replace(",", "")
    if not s or s.lower() in ("0", "-", "n/a", "none", "nan"):
        return ""
    if s == "1/1" or s == "1":
        return "1"
    m = re.search(r"(\d+)", s)
    return str(int(m.group(1))) if m else ""


def sanitize_filename_part(val) -> str:
    s = strip_accents(str(val or "")).strip()
    s = re.sub(r"[\\/:*?\"<>|\[\]]+", "_", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "Unknown"


def canonical_set_key(set_name: str) -> str:
    raw = norm(set_name)
    if raw in SET_ALIAS_MAP:
        return norm(SET_ALIAS_MAP[raw])
    s = strip_accents(str(set_name or "")).upper()
    s = re.sub(r"\b(SERIES\s*1|SERIES\s*2|SERIES\s*ONE|SERIES\s*TWO)\b", "", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def canonical_subset_key(subset_name: str, set_name: str = "") -> str:
    s = strip_accents(str(subset_name or "Base")).upper().strip()
    s = s.replace("_", " ").replace("-", " ")
    if s in (
        "",
        "BASE",
        "BASE SET",
        "BASE ROOKIE",
        "BASE ROOKIES",
        "BASE VETERAN",
        "BASE VETERANS",
        "BASE VETERAN COMBOS",
        "BASE ROOKIE DEBUT",
    ):
        return "BASE"
    if s.startswith("BASE ") and not s.startswith("BASE PAPER"):
        s = s[5:].strip()
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"[^A-Z0-9]", "", s) or "BASE"


def build_card_image_stem(set_name: str, subset_name: str, card_number: str, player_name: str) -> str:
    s_part = sanitize_filename_part(set_name)[:48].rstrip("_") or "Set"
    sub_part = sanitize_filename_part(subset_name or "Base")[:42].rstrip("_") or "Base"
    cn_part = sanitize_filename_part(str(card_number or "0").lstrip("#"))[:18].rstrip("_") or "0"
    p_part = sanitize_filename_part(player_name or "Unknown_Player")
    if len(p_part) > 60:
        p_part = p_part[:60].rstrip("_")
    stem = f"[{s_part}]_[{sub_part}]_[#{cn_part}]_[{p_part}]"
    if len(stem) > 145:
        avail_p = max(16, 145 - (len(stem) - len(p_part)))
        p_part = p_part[:avail_p].rstrip("_")
        stem = f"[{s_part}]_[{sub_part}]_[#{cn_part}]_[{p_part}]"
    return stem


def build_card_image_filenames(
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
    sku_str: str,
) -> tuple[str, str, str]:
    stem = build_card_image_stem(set_name, subset_name, card_number, player_name)
    clean_sku = sanitize_filename_part(sku_str)
    return (
        f"{stem}_[{clean_sku}]_F.jpg",
        f"{stem}_[{clean_sku}]_B.jpg",
        f"{stem}_[{clean_sku}]_C.jpg",
    )


def normalize_numeric_tcdb_cid(raw_cid: str) -> str:
    """
    Extracts the canonical numeric TCDB CID from strings like '58544801',
    'TCDB58544801', or legacy '{sid}-{cid}' like '585448-58544801'.
    """
    s = str(raw_cid or "").strip()
    s = re.sub(r"^TCDB", "", s, flags=re.IGNORECASE).strip()
    if "-" in s:
        tail = s.rsplit("-", 1)[-1].strip()
        if tail.isdigit():
            return tail
    if "_" in s:
        tail = s.rsplit("_", 1)[-1].strip()
        if tail.isdigit():
            return tail
    digits = re.sub(r"[^0-9]", "", s)
    return digits or sanitize_filename_part(s) or "0"


def format_tcdb_cid_tag(cid: str) -> str:
    """Formats a TCDB card ID as `TCDB{CID}` (e.g., '58544801' -> 'TCDB58544801')."""
    clean_cid = normalize_numeric_tcdb_cid(cid)
    return f"TCDB{clean_cid}"


def build_template_image_filename(
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
    cid: str,
    side: str = "F",
) -> str:
    """
    Builds the unified Set Template filename matching scanned card conventions:
      [Set]_[Subset]_[#CardNumber]_[Player]_[TCDB{CID}]_{F|B}.jpg
    """
    stem = build_card_image_stem(set_name, subset_name, card_number, player_name)
    cid_tag = format_tcdb_cid_tag(cid)
    side_up = str(side or "F").strip().upper()
    side_code = "B" if side_up.startswith("B") else "F"
    return f"{stem}_[{cid_tag}]_{side_code}.jpg"


def build_template_image_filenames(
    set_name: str,
    subset_name: str,
    card_number: str,
    player_name: str,
    cid: str,
) -> tuple[str, str]:
    """Returns `(front_template_filename, back_template_filename)` using the unified `TCDB{CID}` standard."""
    return (
        build_template_image_filename(set_name, subset_name, card_number, player_name, cid, side="F"),
        build_template_image_filename(set_name, subset_name, card_number, player_name, cid, side="B"),
    )


_UNIFIED_CARD_FILENAME_RE = re.compile(
    r"^\[([^\]]+)\]_\[([^\]]+)\]_\[#?([^\]]+)\]_\[([^\]]+)\]_\[([^\]]+)\]_([FBC])\.jpe?g$",
    re.IGNORECASE,
)


def parse_unified_card_filename(filename: str) -> Optional[dict]:
    """
    Parses `[Set]_[Subset]_[#CardNumber]_[Player]_[ID]_{F|B|C}.jpg` for both
    scanned cards (`[1000001]`) and Set Library templates (`[TCDB58544801]`).
    """
    m = _UNIFIED_CARD_FILENAME_RE.match(Path(filename).name)
    if not m:
        return None
    s_raw, sub_raw, cn_raw, p_raw, id_raw, side_raw = m.groups()
    is_tmpl = id_raw.upper().startswith("TCDB")
    return {
        "set": s_raw.replace("_", " ").strip(),
        "subset": sub_raw.replace("_", " ").strip() or "Base",
        "card_number": cn_raw.lstrip("#").strip(),
        "player": p_raw.replace("_", " ").strip(),
        "id_tag": id_raw,
        "is_template": is_tmpl,
        "cid": normalize_numeric_tcdb_cid(id_raw) if is_tmpl else "",
        "sku": "" if is_tmpl else id_raw,
        "side": side_raw.upper(),
    }


def _parse_semver_sort_tuple(ver_str: str) -> tuple:
    s = str(ver_str or "").strip().lstrip("vV")
    if not s:
        return (0, 0, 0, "", 0)
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z]+)\.?(\d+)?)?", s)
    if not m:
        return (0, 0, 0, s, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), (m.group(4) or "zzz").lower(), int(m.group(5) or 0))


def _extract_version_from_file_text(file_path: Path) -> tuple[str, str]:
    if not file_path.exists():
        return "Missing", "N/A"
    try:
        head_txt = file_path.read_text(encoding="utf-8-sig", errors="replace")[:4500]
        ver_s = ""
        for pat in (
            r'^__version__\s*=\s*["\']([^"\']+)["\']',
            r'^\s*const\s+APP_VERSION\s*=\s*["\']([^"\']+)["\']',
            r'^#\s*Release:\s*v?([0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?)',
        ):
            m_ver = re.search(pat, head_txt, re.MULTILINE)
            if m_ver:
                ver_s = m_ver.group(1).strip().lstrip("vV")
                break

        upd_s = ""
        for pat_u in (
            r'^__last_updated__\s*=\s*["\']([^"\']+)["\']',
            r'^\s*const\s+LAST_UPDATED\s*=\s*["\']([^"\']+)["\']',
        ):
            m_upd = re.search(pat_u, head_txt, re.MULTILINE)
            if m_upd:
                upd_s = m_upd.group(1).strip()
                break

        return ver_s or "Unknown", upd_s or ""
    except Exception:
        return "Read Error", "N/A"


def inspect_all_module_versions(pending_updates_map: Optional[dict[str, str]] = None) -> list[dict]:
    """
    Inspects each module's TRUE individual version (based on when that specific file was last
    updated on disk / in Updates/version_registry.json) and annotates any pending module updates
    discovered by `Check for Updates`.
    """
    import json

    reg_files: dict[str, dict] = {}
    reg_hist_ver_by_file: dict[str, tuple[str, str]] = {}
    reg_path = UPDATES_DIR / "version_registry.json"
    if reg_path.exists():
        try:
            reg_data = json.loads(reg_path.read_text(encoding="utf-8-sig"))
            if isinstance(reg_data, dict):
                if isinstance(reg_data.get("files"), dict):
                    reg_files = reg_data["files"]
                for h_item in reg_data.get("version_history") or []:
                    if not isinstance(h_item, dict):
                        continue
                    h_ver = str(h_item.get("version") or "").strip().lstrip("vV")
                    h_ts = str(h_item.get("timestamp") or h_item.get("applied_at") or "").strip()
                    for f_mod in h_item.get("files_modified") or []:
                        norm_f = str(f_mod).strip().replace("\\", "/")
                        if h_ver:
                            reg_hist_ver_by_file[norm_f] = (h_ver, h_ts)
        except Exception:
            pass

    norm_pending: dict[str, str] = {}
    if isinstance(pending_updates_map, dict):
        for k_p, v_p in pending_updates_map.items():
            norm_pending[str(k_p).strip().replace("\\", "/")] = str(v_p or "").strip().lstrip("vV")

    rows = []
    for entry in EXPECTED_MODULE_REGISTRY:
        mod_key = entry["module_key"]
        rel_path = str(entry["rel_path"]).replace("\\", "/")
        expected_ver = entry["expected_version"]
        disk_path = (APP_DIR / rel_path) if (APP_DIR / rel_path).exists() else (BASE_DIR / rel_path)
        backup_path = BACKUP_SUBDIR / disk_path.name

        file_ver, file_declared_ts = _extract_version_from_file_text(disk_path)
        backup_ver, _ = _extract_version_from_file_text(backup_path)

        cand_vers: list[str] = []
        if file_ver not in ("Missing", "Read Error", "Unknown", ""):
            cand_vers.append(file_ver)
        rf_meta = reg_files.get(rel_path) if isinstance(reg_files, dict) else None
        if isinstance(rf_meta, dict) and rf_meta.get("version"):
            cand_vers.append(str(rf_meta["version"]).strip().lstrip("vV"))
        if rel_path in reg_hist_ver_by_file:
            cand_vers.append(reg_hist_ver_by_file[rel_path][0])

        if cand_vers:
            actual_ver = max(cand_vers, key=_parse_semver_sort_tuple)
        else:
            actual_ver = file_ver

        if disk_path.exists():
            st_info = disk_path.stat()
            disk_mtime_str = datetime.fromtimestamp(st_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = f"{st_info.st_size / 1024.0:.1f} KB"
        else:
            disk_mtime_str = "File Missing"
            size_kb = "0.0 KB"

        loaded_mod = sys.modules.get(mod_key)
        if loaded_mod is not None:
            loaded_ver = str(getattr(loaded_mod, "__version__", "") or actual_ver).lstrip("vV")
            loaded_ts = str(getattr(loaded_mod, "__last_updated__", "") or file_declared_ts)
        else:
            loaded_ver = actual_ver
            loaded_ts = file_declared_ts or (reg_hist_ver_by_file.get(rel_path, ("", ""))[1])

        pending_ver = norm_pending.get(rel_path, "")
        has_pending_update = bool(
            pending_ver and _parse_semver_sort_tuple(pending_ver) > _parse_semver_sort_tuple(actual_ver)
        )

        if not disk_path.exists():
            status_str = "❌ File Missing"
        elif has_pending_update:
            status_str = "🆕 Update Available"
        else:
            status_str = "🟢 Current"

        rows.append({
            "Module": rel_path,
            "Component Role": entry["role"],
            "Loaded Version": loaded_ver,
            "Disk Version": actual_ver,
            "New Version": pending_ver if has_pending_update else "",
            "Expected": expected_ver,
            "Backup Snapshot": backup_ver if backup_path.exists() else "None",
            "Release Timestamp": loaded_ts or file_declared_ts or "—",
            "Disk Last Modified": disk_mtime_str,
            "Size": size_kb,
            "Status": status_str,
        })
    return rows


def relocate_root_downloaded_files():
    root_dl = BASE_DIR / "downloaded_files"
    if root_dl.exists() and root_dl.is_dir():
        DOWNLOADED_FILES_DIR.mkdir(parents=True, exist_ok=True)
        for item in root_dl.iterdir():
            target = DOWNLOADED_FILES_DIR / item.name
            try:
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        target.unlink()
                shutil.move(str(item), str(target))
            except Exception:
                pass
        shutil.rmtree(root_dl, ignore_errors=True)


def ensure_directories():
    dirs_to_create = [
        CORE_DIR,
        BACKUP_SUBDIR,
        FONTS_DIR,
        DOWNLOADED_FILES_DIR,
        UPDATES_DIR,
        LOGS_ROOT_DIR,
        DAILY_LOGS_ROOT,
        REPORTS_DIR,
        INVENTORY_DIR,
        LABELS_OUTPUT_DIR,
        CHECKLIST_DIR,
        SET_CHECKLISTS_DIR,
        SALES_HUB_DIR,
        COLLECTION_DIR,
        BOOKKEEPING_DIR,
        INPUT_PATH,
        BATCHES_DIR,
        REVIEWED_CARDS_DIR,
        REFERENCE_TEMPLATES_DIR,
        ARCHIVE_DIR,
        ARCHIVE_SCAN_PATH,
        PROCESSED_ARCHIVE_DIR,
        ARCHIVE_LOGS_DIR,
        ARCHIVE_UPDATES_PACKAGES_DIR,
        ARCHIVE_UPDATES_SNAPSHOTS_DIR,
        ARCHIVE_CHECKLISTS_DIR,
    ]
    if IS_REORGANIZED_V24:
        dirs_to_create.extend([
            CACHE_DIR,
            CACHE_LIBRARY_DIR,
            CACHE_CATALOGS_DIR,
            NEURAL_MODELS_DIR,
            CACHE_CHECKLISTS_DIR,
            CACHE_CHECKPOINTS_DIR,
            CACHE_INVENTORY_DIR,
            CACHE_SALES_MARKET_DIR,
            CACHE_SYSTEM_DIR,
            CACHE_GRADING_DIAGNOSTICS_DIR,
            CACHE_GRADING_FEEDBACK_DIR,
            RUNTIME_DIR,
        ])
    else:
        dirs_to_create.extend([
            LOGS_DIR,
            SET_LIBRARY_CACHE_DIR,
            CACHE_CHECKPOINTS_DIR,
            CACHE_GRADING_DIAGNOSTICS_DIR,
            CACHE_GRADING_FEEDBACK_DIR,
        ])

    for d in dirs_to_create:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    relocate_root_downloaded_files()


# ==============================================================================
# WINDOWS-SAFE ATOMIC FILE PERSISTENCE & STALE-SAFE CROSS-PROCESS FILE LOCKS
# ==============================================================================
_LOCAL_LOCK_REGISTRY_GUARD = threading.Lock()
_LOCAL_PATH_RLOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCK_DEPTH: dict[tuple[str, int], int] = {}


def _is_lock_holder_pid_alive(pid: int) -> bool:
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


def atomic_write_bytes(
    target_path: Path,
    writer_fn: Callable[[Path], None],
    retries: int = 5,
):
    """
    Writes `target_path` atomically via a PID+thread-qualified `.tmp` file and `os.replace()`
    with short retry backoff for Windows transient file-lock/AV contention and guaranteed `.tmp` cleanup.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_p = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    backoffs = (0.04, 0.06, 0.09, 0.12, 0.15)
    try:
        writer_fn(tmp_p)
        last_err: Optional[Exception] = None
        attempts = max(1, int(retries))
        for attempt in range(attempts):
            try:
                os.replace(str(tmp_p), str(target))
                return
            except (PermissionError, OSError) as exc:
                last_err = exc
                if attempt + 1 < attempts:
                    time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
        if last_err is not None:
            raise last_err
    finally:
        try:
            if tmp_p.exists():
                tmp_p.unlink()
        except Exception:
            pass


def atomic_write_text(
    target_path: Path,
    text: str,
    encoding: str = "utf-8",
    retries: int = 5,
):
    """Windows-safe atomic text/JSON writer backed by `atomic_write_bytes()`."""
    atomic_write_bytes(
        target_path,
        lambda tmp_p: tmp_p.write_text(text, encoding=encoding),
        retries=retries,
    )


@contextlib.contextmanager
def interprocess_file_lock(
    lock_path: Path,
    timeout: float = 20.0,
    stale_seconds: float = 30.0,
):
    """
    Re-entrant, stale-safe cross-process & multi-thread file lock using atomic `O_CREAT|O_EXCL`.
    Automatically recovers stale locks left by crashed/force-killed workers (dead PID or age > `stale_seconds`).
    """
    lp = Path(lock_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    key = str(lp.resolve()).lower()
    tid = threading.get_ident()

    with _LOCAL_LOCK_REGISTRY_GUARD:
        local_rlock = _LOCAL_PATH_RLOCKS.get(key)
        if local_rlock is None:
            local_rlock = threading.RLock()
            _LOCAL_PATH_RLOCKS[key] = local_rlock

    local_rlock.acquire()
    depth_key = (key, tid)
    prev_depth = _LOCAL_LOCK_DEPTH.get(depth_key, 0)
    if prev_depth > 0:
        _LOCAL_LOCK_DEPTH[depth_key] = prev_depth + 1
        try:
            yield
        finally:
            _LOCAL_LOCK_DEPTH[depth_key] = prev_depth
            local_rlock.release()
        return

    acquired_os_lock = False
    deadline = time.time() + max(0.05, float(timeout))
    token = f"{os.getpid()}|{tid}|{time.time():.6f}"
    try:
        while True:
            try:
                fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, token.encode("utf-8"))
                finally:
                    os.close(fd)
                acquired_os_lock = True
                break
            except FileExistsError:
                now_t = time.time()
                should_break = False
                try:
                    st = lp.stat()
                    raw_meta = lp.read_text(encoding="utf-8", errors="ignore").strip()
                    parts = raw_meta.split("|")
                    holder_pid = int(parts[0]) if (parts and parts[0].isdigit()) else 0
                    if holder_pid > 0:
                        if holder_pid != os.getpid() and not _is_lock_holder_pid_alive(holder_pid):
                            should_break = True
                    elif (now_t - st.st_mtime) > float(stale_seconds):
                        should_break = True
                except FileNotFoundError:
                    continue
                except Exception:
                    pass

                if should_break:
                    try:
                        lp.unlink()
                    except Exception:
                        pass
                    continue

                if now_t >= deadline:
                    raise TimeoutError(
                        f"Timed out after {float(timeout):.2f}s waiting for interprocess file lock: {lp}"
                    )
                time.sleep(0.04)

        _LOCAL_LOCK_DEPTH[depth_key] = 1
        yield
    finally:
        _LOCAL_LOCK_DEPTH.pop(depth_key, None)
        if acquired_os_lock:
            try:
                if lp.exists():
                    cur_tok = lp.read_text(encoding="utf-8", errors="ignore").strip()
                    if cur_tok == token:
                        lp.unlink()
            except Exception:
                pass
        local_rlock.release()