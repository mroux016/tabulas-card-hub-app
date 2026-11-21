from __future__ import annotations
# ==============================================================================
# Core/label_engine.py - QR / SKU LABEL & ALIGNMENT TEST SHEET PDF GENERATOR
# ==============================================================================
import io
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import pandas as pd
import qrcode
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

__version__ = "0.21.0-beta.1"
__last_updated__ = "2026-11-15 11:30:00"

from Core.config import (
    FONTS_DIR,
    LABELS_OUTPUT_DIR,
    LABEL_TEMPLATES,
    ensure_directories,
    format_print_run,
    strip_accents,
)

# Points conversion constants
INCH = 72.0
MM = INCH / 25.4

# --- TEAM ABBREVIATION <-> FULL TEAM NAME REGISTRY ---
TEAM_FULL_TO_ABBR = {
    # MLB
    "ARIZONA DIAMONDBACKS": "ARI",
    "ATLANTA BRAVES": "ATL",
    "BALTIMORE ORIOLES": "BAL",
    "BOSTON RED SOX": "BOS",
    "CHICAGO CUBS": "CHC",
    "CHICAGO WHITE SOX": "CWS",
    "CINCINNATI REDS": "CIN",
    "CLEVELAND GUARDIANS": "CLE",
    "CLEVELAND INDIANS": "CLE",
    "COLORADO ROCKIES": "COL",
    "DETROIT TIGERS": "DET",
    "HOUSTON ASTROS": "HOU",
    "KANSAS CITY ROYALS": "KC",
    "LOS ANGELES ANGELS": "LAA",
    "ANAHEIM ANGELS": "LAA",
    "CALIFORNIA ANGELS": "CAL",
    "LOS ANGELES DODGERS": "LAD",
    "BROOKLYN DODGERS": "BKN",
    "MIAMI MARLINS": "MIA",
    "FLORIDA MARLINS": "FLA",
    "MILWAUKEE BREWERS": "MIL",
    "MINNESOTA TWINS": "MIN",
    "NEW YORK METS": "NYM",
    "NEW YORK YANKEES": "NYY",
    "ATHLETICS": "ATH",
    "OAKLAND ATHLETICS": "OAK",
    "PHILADELPHIA PHILLIES": "PHI",
    "PITTSBURGH PIRATES": "PIT",
    "SAN DIEGO PADRES": "SD",
    "SAN FRANCISCO GIANTS": "SF",
    "NEW YORK GIANTS": "NYG",
    "SEATTLE MARINERS": "SEA",
    "ST. LOUIS CARDINALS": "STL",
    "ST LOUIS CARDINALS": "STL",
    "TAMPA BAY RAYS": "TB",
    "TAMPA BAY DEVIL RAYS": "TB",
    "TEXAS RANGERS": "TEX",
    "TORONTO BLUE JAYS": "TOR",
    "WASHINGTON NATIONALS": "WSH",
    "MONTREAL EXPOS": "MTL",
    # NFL
    "ARIZONA CARDINALS": "ARI",
    "ATLANTA FALCONS": "ATL",
    "BALTIMORE RAVENS": "BAL",
    "BUFFALO BILLS": "BUF",
    "CAROLINA PANTHERS": "CAR",
    "CHICAGO BEARS": "CHI",
    "CINCINNATI BENGALS": "CIN",
    "CLEVELAND BROWNS": "CLE",
    "DALLAS COWBOYS": "DAL",
    "DENVER BRONCOS": "DEN",
    "DETROIT LIONS": "DET",
    "GREEN BAY PACKERS": "GB",
    "HOUSTON TEXANS": "HOU",
    "INDIANAPOLIS COLTS": "IND",
    "JACKSONVILLE JAGUARS": "JAX",
    "KANSAS CITY CHIEFS": "KC",
    "LAS VEGAS RAIDERS": "LV",
    "OAKLAND RAIDERS": "OAK",
    "LOS ANGELES CHARGERS": "LAC",
    "SAN DIEGO CHARGERS": "SD",
    "LOS ANGELES RAMS": "LAR",
    "ST. LOUIS RAMS": "STL",
    "MIAMI DOLPHINS": "MIA",
    "MINNESOTA VIKINGS": "MIN",
    "NEW ENGLAND PATRIOTS": "NE",
    "NEW ORLEANS SAINTS": "NO",
    "NEW YORK JETS": "NYJ",
    "PHILADELPHIA EAGLES": "PHI",
    "PITTSBURGH STEELERS": "PIT",
    "SAN FRANCISCO 49ERS": "SF",
    "SEATTLE SEAHAWKS": "SEA",
    "TAMPA BAY BUCCANEERS": "TB",
    "TENNESSEE TITANS": "TEN",
    "WASHINGTON COMMANDERS": "WAS",
    # NBA
    "ATLANTA HAWKS": "ATL",
    "BOSTON CELTICS": "BOS",
    "BROOKLYN NETS": "BKN",
    "CHARLOTTE HORNETS": "CHA",
    "CHICAGO BULLS": "CHI",
    "CLEVELAND CAVALIERS": "CLE",
    "DALLAS MAVERICKS": "DAL",
    "DENVER NUGGETS": "DEN",
    "DETROIT PISTONS": "DET",
    "GOLDEN STATE WARRIORS": "GSW",
    "HOUSTON ROCKETS": "HOU",
    "INDIANA PACERS": "IND",
    "LOS ANGELES CLIPPERS": "LAC",
    "LOS ANGELES LAKERS": "LAL",
    "MEMPHIS GRIZZLIES": "MEM",
    "MIAMI HEAT": "MIA",
    "MILWAUKEE BUCKS": "MIL",
    "MINNESOTA TIMBERWOLVES": "MIN",
    "NEW ORLEANS PELICANS": "NOP",
    "NEW YORK KNICKS": "NYK",
    "OKLAHOMA CITY THUNDER": "OKC",
    "ORLANDO MAGIC": "ORL",
    "PHILADELPHIA 76ERS": "PHI",
    "PHOENIX SUNS": "PHX",
    "PORTLAND TRAIL BLAZERS": "POR",
    "SACRAMENTO KINGS": "SAC",
    "SAN ANTONIO SPURS": "SAS",
    "TORONTO RAPTORS": "TOR",
    "UTAH JAZZ": "UTA",
    "WASHINGTON WIZARDS": "WAS",
}

ABBR_TO_FULL_MLB = {
    "ARI": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "ATH": "Athletics",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CWS": "Chicago White Sox",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SF": "San Francisco Giants",
    "SEA": "Seattle Mariners",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
}

# Base parallel nouns — when splitting a compound "Insert + Parallel" name, any leading
# color/finish modifiers (e.g., "Blue", "Gold", "Black", "Rainbow") stay locked to the noun.
PARALLEL_NOUN_PATTERNS = (
    r"SuperFractor",
    r"FoilFractor",
    r"LogoFractor",
    r"FrozenFractor",
    r"X-Fractor",
    r"Refractor",
    r"Foil\s+Filigree",
    r"Silver\s+Portrait",
    r"Framed\s+Mini\s+Relic",
    r"Framed\s+Relics?",
    r"Black\s+Finite",
    r"Gold\s+Vinyl",
    r"Prizm",
    r"Border(?:ed)?",
    r"Foil",
    r"Autographs?",
    r"Relics?",
    r"A&G\s+Back",
    r"Brooklyn\s+Back",
    r"Independence\s+Day",
    r"Memorial\s+Day\s+Camo",
    r"Vintage\s+Stock",
)

COLOR_OR_FINISH_MODIFIERS = (
    r"(?:(?:True|Hot|Neon|Ice|Sky|Powder|Royal|Navy|Midnight|Cherry|Rose|Forest|Olive|Antique|Matte)\s+)?"
    r"(?:(?:Blue|Red|Gold|Orange|Green|Purple|Pink|Aqua|Teal|Yellow|Black|Silver|Bronze|Copper|Sepia|"
    r"Platinum|Rainbow|Holo|Prism|Mojo|RayWave|Shimmer|Speckle|Wave|Lava|Sonar|Camo|Wood|Metal|Clear)\s+)*"
)

# --- EXPANDED PARALLEL / SUBSET & LEAGUE COLOR PALETTES (PRINT-OPTIMIZED RGB) ---
LEAGUE_COLOR_RGB = {
    "MLB": (0.04, 0.18, 0.44),  # MLB Deep Navy
    "NFL": (0.01, 0.20, 0.41),  # NFL Shield Blue
    "NBA": (0.78, 0.16, 0.10),  # NBA Hardwood Red
    "NHL": (0.12, 0.14, 0.18),  # NHL Slate Black
    "MLS": (0.05, 0.42, 0.22),  # Pitch Green
    "F1":  (0.82, 0.06, 0.06),  # Racing Red
}

# Ordered from most specific multi-word color variants to broad color/type families
PARALLEL_COLOR_RULES: list[tuple[tuple[str, ...], tuple[float, float, float]]] = [
    # 1/1 & SuperFractor / Gold Vinyl
    (("SUPERFRACTOR", "FOILFRACTOR", "GOLD VINYL"), (0.54, 0.35, 0.00)),
    # Rose Gold / Pink-Gold
    (("ROSE GOLD", "PINK GOLD", "CHERRY BLOSSOM"), (0.72, 0.24, 0.38)),
    # Black & Gold
    (("BLACK AND GOLD", "BLACK GOLD"), (0.48, 0.34, 0.02)),
    # Red, White & Blue / Independence Day
    (("INDEPENDENCE DAY", "RED WHITE BLUE", "PATRIOTIC", "STARS & STRIPES", "STARS AND STRIPES"), (0.74, 0.08, 0.16)),
    # Memorial Day / Camo / Military
    (("MEMORIAL DAY", "DESERT CAMO", "WOODLAND CAMO", "CAMO"), (0.28, 0.44, 0.18)),
    # Father's Day / Powder / Sky / Ice / Sapphire Blue
    (("FATHER'S DAY", "FATHERS DAY", "POWDER BLUE", "SKY BLUE", "ICE BLUE", "UNIVERSITY BLUE", "CAROLINA BLUE", "FROZENFRACTOR", "FROZEN"), (0.08, 0.42, 0.76)),
    (("SAPPHIRE", "ROYAL BLUE", "TRUE BLUE", "NAVY BLUE", "MIDNIGHT BLUE", "PEACOCK", "BLUE SONAR", "BLUE WAVE", "BLUE REFRACTOR", "BLUE PRIZM", "BLUE FOIL FILIGREE", "BLUE FOIL", "BLUE BORDER", "BLUE"), (0.06, 0.28, 0.72)),
    # Mother's Day / Pink / Magenta / Fuchsia
    (("MOTHER'S DAY", "MOTHERS DAY", "HOT PINK", "NEON PINK", "MAGENTA", "FUCHSIA", "PINK REFRACTOR", "PINK WAVE", "PINK PRIZM", "PINK FOIL", "PINK MOJO", "PINK VELOCITY", "PINK"), (0.74, 0.10, 0.48)),
    # Aqua / Teal / Turquoise / Cyan
    (("AQUA", "TEAL", "TURQUOISE", "CYAN", "TIDAL", "OCEAN", "MINT"), (0.00, 0.46, 0.54)),
    # Purple / Violet / Amethyst / Lavender / Plum / Relics
    (("PURPLE", "VIOLET", "AMETHYST", "LAVENDER", "PLUM", "GRAPE", "BURGUNDY", "MAROON", "WINE", "FRAMED MINI RELIC", "FRAMED RELIC", "RELIC", "PATCH", "JERSEY", "BAT"), (0.46, 0.12, 0.60)),
    # Red / Ruby / Crimson / Scarlet / Garnet
    (("CRIMSON", "RUBY", "SCARLET", "GARNET", "CHERRY", "RED REFRACTOR", "RED WAVE", "RED PRIZM", "RED FOIL", "RED SHIMMER", "RED LAVA", "RED BORDER", "RED INK", "RED"), (0.78, 0.07, 0.12)),
    # Orange / Tangerine / Coral / Amber
    (("ORANGE", "TANGERINE", "CORAL", "AMBER", "SUNBURST", "TIGER", "PUMPKIN"), (0.82, 0.32, 0.00)),
    # Gold / Yellow / Citrine / Canary
    (("GOLD REFRACTOR", "GOLD PRIZM", "GOLD FOIL", "GOLD WAVE", "GOLD SHIMMER", "GOLD LAVA", "GOLD BORDER", "GOLD LABEL", "GOLD MEDALLION", "GOLD MINTED", "GOLD"), (0.54, 0.35, 0.00)),
    (("YELLOW", "CANARY", "CITRINE", "LEMON", "SUNSHINE", "NEON YELLOW", "ELECTRIC YELLOW"), (0.50, 0.38, 0.00)),
    # Green / Emerald / Neon Green / Lime / Jade
    (("NEON GREEN", "LIME GREEN", "LIME", "ELECTRIC GREEN", "SHAMROCK"), (0.12, 0.54, 0.14)),
    (("EMERALD", "FOREST GREEN", "JADE", "OLIVE", "GREEN REFRACTOR", "GREEN WAVE", "GREEN PRIZM", "GREEN FOIL", "GREEN SHIMMER", "GREEN SONAR", "GREEN BORDER", "GREEN"), (0.05, 0.46, 0.18)),
    # Bronze / Copper / Sepia / Vintage Stock / Wood / A&G Mini
    (("SEPIA", "VINTAGE STOCK", "BRONZE", "COPPER", "WOOD", "BURL", "SIENNA", "BROWN", "CHOCOLATE", "ROOT BEER", "A&G BACK", "BROOKLYN BACK"), (0.48, 0.28, 0.10)),
    # Black / Obsidian / Noir / Smoke / Charcoal / Onyx
    (("BLACK FINITE", "BLACK REFRACTOR", "BLACK PRIZM", "BLACK FOIL", "BLACK BORDER", "BLACK BORDERED", "BLACK SHIMMER", "BLACK WAVE", "NOIR", "OBSIDIAN", "ONYX", "CHARCOAL", "SMOKE", "NEGATIVE", "BLACK"), (0.10, 0.12, 0.16)),
    # Silver Portrait / Foil Filigree / Refractor / Chrome / Silver
    (("SILVER PORTRAIT", "FOIL FILIGREE", "LOGOFRACTOR", "X-FRACTOR", "XFRACTOR", "PRISM REFRACTOR", "REFRACTOR", "SILVER PRIZM", "SILVER", "RAINBOW FOIL", "HOLOFOIL", "HOLO", "PULSAR", "RAYWAVE", "SHIMMER", "SPECKLE", "MINI-DIAMOND", "HYPER", "MOJO", "PLATINUM", "MINI - CHROME", "CHROME", "CLEAR", "ACETATE"), (0.24, 0.34, 0.46)),
    # Autograph / Short Print / Golden Mirror / Design Variation
    (("GOLDEN MIRROR", "IMAGE VARIATION", "ROOKIE DESIGN VARIATION", "TRUE PHOTO", "SSP"), (0.60, 0.36, 0.02)),
    (("AUTOGRAPH", "AUTO"), (0.10, 0.22, 0.62)),
    # Standard Tobacco Mini
    (("MINI",), (0.42, 0.28, 0.14)),
]


def resolve_parallel_color_rgb(
    subset_text: str,
    print_run_raw: str = "",
) -> tuple[tuple[float, float, float], bool, str]:
    """
    Returns (rgb_tuple, is_non_base, card_tier) for the card's Subset / Parallel and Print Run.
    card_tier is one of: 'BASE', 'INSERT', 'PARALLEL', 'AUTO_RELIC', 'ONE_OF_ONE'.
    """
    up_sub = strip_accents(str(subset_text or "")).upper().strip()
    pr_clean = strip_accents(str(print_run_raw or "")).strip()

    if not up_sub or up_sub == "BASE":
        if pr_clean in ("1", "1/1"):
            return (0.74, 0.06, 0.12), True, "ONE_OF_ONE"
        return (0.30, 0.34, 0.40), False, "BASE"

    is_one_of_one = pr_clean in ("1", "1/1") or "1/1" in up_sub or "SUPERFRACTOR" in up_sub or "BLACK FINITE" in up_sub
    is_auto_relic = any(k in up_sub for k in ("AUTO", "RELIC", "PATCH", "JERSEY", "FRAMED"))

    for kw_tuple, rgb_val in PARALLEL_COLOR_RULES:
        for kw in kw_tuple:
            if re.search(rf"\b{re.escape(kw)}\b", up_sub) or kw in up_sub:
                tier = "ONE_OF_ONE" if is_one_of_one else ("AUTO_RELIC" if is_auto_relic else "PARALLEL")
                return rgb_val, True, tier

    if is_one_of_one:
        return (0.68, 0.44, 0.00), True, "ONE_OF_ONE"
    if is_auto_relic:
        return (0.46, 0.12, 0.60), True, "AUTO_RELIC"

    # Non-base Insert Set (e.g. N43, Career 250, Wicked Power, 1955 Topps Double Headers)
    return (0.08, 0.36, 0.48), True, "INSERT"


def resolve_serial_badge_rgb(parallel_rgb: tuple[float, float, float], serial_str: str) -> tuple[float, float, float]:
    """
    Chooses a high-contrast, visually distinct RGB color for the serial number badge ('#/150', '#/50', '1/1')
    so the serial number NEVER blends into the same color as the parallel pill.
    """
    r, g, b = parallel_rgb
    if serial_str == "1/1":
        if r > 0.60 and g < 0.25:
            return (0.70, 0.46, 0.00)
        return (0.78, 0.06, 0.12)

    if r > 0.45 and b < 0.45:
        return (0.06, 0.24, 0.64)
    return (0.76, 0.08, 0.14)


def get_team_abbreviation(team_name: str) -> str:
    """Returns a 2-to-3 letter team abbreviation for compact fallback lines."""
    clean = strip_accents(str(team_name or "")).strip()
    if not clean or clean.upper() in ("NO TEAM", "UNKNOWN", "NAN"):
        return ""
    up = clean.upper()
    if up in TEAM_FULL_TO_ABBR:
        return TEAM_FULL_TO_ABBR[up]
    if len(up) <= 3 and up.isalpha():
        return up
    words = [w for w in re.split(r"\s+", up) if w]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3])
    return up[:3]


def expand_full_team_name(team_raw: str, league: str = "MLB") -> str:
    """
    Expands team abbreviations (e.g., 'NYY' -> 'New York Yankees') and cleans
    full team names so Line 3 of the label displays the full team name cleanly.
    """
    clean = strip_accents(str(team_raw or "")).strip()
    if not clean or clean.upper() in ("NO TEAM", "UNKNOWN", "NAN", "NONE"):
        return ""
    if "/" in clean:
        parts = [expand_full_team_name(p.strip(), league=league) for p in clean.split("/") if p.strip()]
        return " / ".join(p for p in parts if p)
    up = clean.upper()
    if league == "MLB" and up in ABBR_TO_FULL_MLB:
        return ABBR_TO_FULL_MLB[up]
    return clean


# ==============================================================================
# 1. CONDENSED / NARROW FONT LOADER (ARIAL NARROW -> ROBOTO CONDENSED -> HELVETICA)
# ==============================================================================
_LOADED_FONTS: Optional[tuple[str, str, str]] = None


def ensure_and_load_fonts() -> tuple[str, str, str]:
    """
    Registers a high-legibility condensed/narrow font pair (regular_name, bold_name, display_label)
    for 1.5" x 0.5" thermal/laser card labels.
    """
    global _LOADED_FONTS
    if _LOADED_FONTS is not None:
        return _LOADED_FONTS

    ensure_directories()
    win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

    candidates = [
        (
            "ArialNarrow",
            "ArialNarrow-Bold",
            "Arial Narrow",
            [win_fonts / "ARIALN.TTF", FONTS_DIR / "ARIALN.TTF"],
            [win_fonts / "ARIALNB.TTF", FONTS_DIR / "ARIALNB.TTF"],
        ),
        (
            "RobotoCondensed",
            "RobotoCondensed-Bold",
            "Roboto Condensed",
            [FONTS_DIR / "RobotoCondensed-Regular.ttf"],
            [FONTS_DIR / "RobotoCondensed-Bold.ttf"],
        ),
        (
            "Arial",
            "Arial-Bold",
            "Arial",
            [win_fonts / "arial.ttf"],
            [win_fonts / "arialbd.ttf"],
        ),
    ]

    for reg_key, bold_key, label, reg_paths, bold_paths in candidates:
        reg_file = next((p for p in reg_paths if p.exists()), None)
        bold_file = next((p for p in bold_paths if p.exists()), None)
        if reg_file and bold_file:
            try:
                pdfmetrics.registerFont(TTFont(reg_key, str(reg_file)))
                pdfmetrics.registerFont(TTFont(bold_key, str(bold_file)))
                _LOADED_FONTS = (reg_key, bold_key, label)
                return _LOADED_FONTS
            except Exception:
                continue

    _LOADED_FONTS = ("Helvetica", "Helvetica-Bold", "Helvetica")
    return _LOADED_FONTS


# ==============================================================================
# 2. TEMPLATE GEOMETRY & PARTIAL SHEET CELL RESOLVER
# ==============================================================================
def resolve_template_spec(template_key: str = "R037L", custom_spec: Optional[dict] = None) -> dict:
    """Returns a normalized geometry dictionary for any built-in or custom label sheet."""
    if template_key == "CUSTOM" and custom_spec:
        spec = dict(custom_spec)
        key_name = "CUSTOM"
    else:
        key_name = template_key if template_key in LABEL_TEMPLATES else "R037L"
        spec = dict(LABEL_TEMPLATES[key_name])

    cols = max(1, int(spec.get("cols", 5)))
    rows = max(1, int(spec.get("rows", 20)))
    return {
        "key": key_name,
        "name": str(spec.get("name", key_name)),
        "page_w": float(spec.get("page_w", 8.5)),
        "page_h": float(spec.get("page_h", 11.0)),
        "cols": cols,
        "rows": rows,
        "label_w": float(spec.get("label_w", 1.5)),
        "label_h": float(spec.get("label_h", 0.5)),
        "margin_x": float(spec.get("margin_x", 0.5)),
        "margin_y": float(spec.get("margin_y", 0.5)),
        "pitch_x": float(spec.get("pitch_x", spec.get("label_w", 1.5))),
        "pitch_y": float(spec.get("pitch_y", spec.get("label_h", 0.5))),
        "cells_per_page": cols * rows,
    }


def _build_available_cell_sequence(
    total_cards: int,
    cols: int,
    rows: int,
    start_row: int = 1,
    start_col: int = 1,
    used_cells_page1: Optional[list[tuple[int, int]]] = None,
) -> list[tuple[int, int, int]]:
    """
    Produces a list of (page_index, row_1based, col_1based) coordinates for each card to print,
    skipping any used/peeled cells on Page 1.
    """
    used_p1 = set()
    start_linear = (max(1, start_row) - 1) * cols + (max(1, start_col) - 1)
    for r_i in range(1, rows + 1):
        for c_i in range(1, cols + 1):
            if (r_i - 1) * cols + (c_i - 1) < start_linear:
                used_p1.add((r_i, c_i))

    if used_cells_page1:
        for r_i, c_i in used_cells_page1:
            used_p1.add((int(r_i), int(c_i)))

    coords: list[tuple[int, int, int]] = []
    page_idx = 0
    while len(coords) < total_cards:
        for r_i in range(1, rows + 1):
            for c_i in range(1, cols + 1):
                if page_idx == 0 and (r_i, c_i) in used_p1:
                    continue
                coords.append((page_idx, r_i, c_i))
                if len(coords) >= total_cards:
                    break
            if len(coords) >= total_cards:
                break
        page_idx += 1
    return coords


# ==============================================================================
# 3. CARD DATA NORMALIZATION, SERIAL FORMATTING & MULTI-LINE TEXT LAYOUT
# ==============================================================================
def infer_league_tag(set_name: str, team_name: str = "") -> str:
    """Infers the 3-letter league badge (MLB, NFL, NBA, NHL, MLS, F1) for the bottom-left SKU line."""
    s = f"{set_name} {team_name}".upper()
    if any(k in s for k in ("FOOTBALL", "NFL", "PANINI PRIZM FOOTBALL", "DONRUSS FOOTBALL")):
        return "NFL"
    if any(k in s for k in ("BASKETBALL", "NBA", "HOOPS")):
        return "NBA"
    if any(k in s for k in ("HOCKEY", "NHL", "O-PEE-CHEE", "UPPER DECK SERIES")):
        return "NHL"
    if any(k in s for k in ("SOCCER", "MLS", "UEFA", "FIFA", "PREMIER LEAGUE")):
        return "MLS"
    if any(k in s for k in ("FORMULA 1", "F1", "RACING", "NASCAR")):
        return "F1"
    return "MLB"


def shorten_set_header(set_name: str) -> str:
    """
    Compacts verbose set names for Line 1 of the label:
      '2026 Topps Baseball' -> '2026 Topps'
      '2025 Topps Allen & Ginter Baseball' -> '2025 Topps Allen & Ginter'
      '2025 Topps Chrome Platinum Anniversary Baseball' -> '2025 Topps Chrome Platinum'
    """
    s = strip_accents(str(set_name or "")).strip()
    s = re.sub(r"\b(Baseball|Football|Basketball|Hockey|Soccer|Racing)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAnniversary\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bEdition\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" -_")
    return s or "Card Set"


def _fit_header_line_preserving_card_num(
    set_short: str,
    cnum_raw: str,
    font_name: str,
    max_width: float,
    preferred_size: float,
    min_size: float = 4.9,
) -> tuple[str, float]:
    """
    Fits Line 1 ('{Set} • #{CardNumber}') while 100% protecting the Card Number from ever
    being cut off (solving Spot #100 '#55DH-11' and long A&G insert numbers like '#WT8H-26'):
      Stage 1: Full '{YYYY} {Set} • #{CardNumber}' if it fits comfortably at >= 5.25pt
      Stage 2: Shortened year ''{YY} {Set} • #{CardNumber}' (e.g. ''25 Topps Chrome Platinum • #55DH-11')
      Stage 3: Shortened year + compact sub-brand (e.g. ''25 Topps Chrome Plat. • #55DH-11',
               ''26 Topps A&G • #WT8H-26')
      Stage 4: Truncates only the tail of the Set name if still needed, never the '#{CardNumber}'.
    """
    cnum_clean = str(cnum_raw or "").strip().lstrip("#")
    if not cnum_clean:
        return _fit_single_line_font_size(set_short, font_name, max_width, preferred_size, min_size)

    suffix = f" \u2022 #{cnum_clean}"
    safe_w = max(20.0, max_width - 1.8)

    year_short_set = re.sub(r"^(19|20)(\d{2})\b", r"'\2", set_short)
    compact_sub_brand = year_short_set
    for long_kw, short_kw in (
        ("Allen & Ginter", "A&G"),
        ("Allen and Ginter", "A&G"),
        ("Chrome Platinum", "Chrome Plat."),
        ("Stadium Club", "Stad. Club"),
        ("Heritage High Number", "Heritage HN"),
        ("Update Series", "Update"),
    ):
        compact_sub_brand = re.sub(re.escape(long_kw), short_kw, compact_sub_brand, flags=re.IGNORECASE)

    candidates = [
        (f"{set_short}{suffix}", max(min_size, 5.25)),
        (f"{year_short_set}{suffix}", max(min_size, 5.10)),
        (f"{compact_sub_brand}{suffix}", min_size),
    ]

    for cand_txt, floor_sz in candidates:
        if _text_width(cand_txt, font_name, floor_sz) <= safe_w:
            return _fit_single_line_font_size(cand_txt, font_name, safe_w, preferred_size, floor_sz)

    suffix_w = _text_width(suffix, font_name, min_size)
    avail_set_w = max(10.0, safe_w - suffix_w)
    trimmed_set = compact_sub_brand
    while len(trimmed_set) > 3 and _text_width(trimmed_set + "..", font_name, min_size) > avail_set_w:
        trimmed_set = trimmed_set[:-1].rstrip()
    final_str = f"{trimmed_set}..{suffix}" if trimmed_set != compact_sub_brand else f"{trimmed_set}{suffix}"
    return final_str, round(min_size, 2)


def format_serial_print_run(print_run_val: str) -> str:
    """
    Formats serial print runs per user specification:
      - 1 or '1/1' -> '1/1' (no '#' prefix)
      - Any other number N (e.g. 10, 50, 75, 199) -> '#/10', '#/50', '#/75', '#/199'
    """
    s = strip_accents(str(print_run_val or "")).strip().replace(",", "")
    if not s or s.lower() in ("0", "-", "n/a", "none", "nan"):
        return ""
    if s == "1/1" or s == "1":
        return "1/1"
    m = re.search(r"(\d+)", s)
    if not m:
        return ""
    num = int(m.group(1))
    if num <= 0:
        return ""
    if num == 1:
        return "1/1"
    return f"#/{num}"


def infer_insert_subset_from_card_number(set_name: str, card_num: str, current_subset: str) -> str:
    """
    If an insert card's subset was left blank or 'Base' in the manifest, infers the proper
    insert name from well-known card number prefixes (e.g. '#N43-17' -> 'N43',
    '#WT8H-26' -> '50 Ways to Say Hello Mini', '#CR-33' -> 'Career 250', '#WP-16' -> 'Wicked Power',
    '#RDV-18' -> 'Rookie Design Variation', '#FMR-SR' -> 'Framed Mini Relic').
    """
    sub_clean = strip_accents(str(current_subset or "")).strip()
    if sub_clean and sub_clean.lower() not in ("base", "base set", "nan", "none"):
        return sub_clean

    cn_up = strip_accents(str(card_num or "")).strip().lstrip("#").upper()
    if "-" not in cn_up:
        return sub_clean or "Base"

    prefix = cn_up.split("-", 1)[0]
    prefix_map = {
        "N43": "N43",
        "N34": "N34",
        "WP": "Wicked Power",
        "CR": "Career 250",
        "RDV": "Rookie Design Variation",
        "WT8H": "50 Ways to Say Hello Mini",
        "WTSH": "50 Ways to Say Hello Mini",
        "MM": "Musical Methods Mini",
        "FMR": "Framed Mini Relic",
        "MA": "Mini Autograph",
        "AGA": "Framed Mini Autograph",
        "AGR": "Relic",
        "55DH": "1955 Topps Double Headers",
        "BCP": "Chrome Prospects",
        "BP": "Bowman Prospects",
    }
    return prefix_map.get(prefix, sub_clean or "Base")


def normalize_subset_display_name(subset_raw: str, set_raw: str = "", cnum_raw: str = "") -> str:
    """
    Cleans and standardizes subset/parallel names for maximum readability on labels:
      1. Infers insert subset from card number prefix if subset was blank/'Base' (e.g. #N43-17 -> N43).
      2. Replaces 'AandG' / 'A and G' with 'A&G' everywhere ('A&G Back').
      3. Strips redundant set-name prefixes on relics/inserts ('Allen and Ginter Framed Relics Mini' -> 'Framed Mini Relic').
      4. Normalizes Allen & Ginter Mini names.
    """
    sub = infer_insert_subset_from_card_number(set_raw, cnum_raw, subset_raw)
    sub = strip_accents(str(sub or "")).strip()
    if not sub or sub.lower() in ("base", "base set", "nan", "none"):
        return "Base"

    if sub.lower().startswith("base ") and sub.lower() not in (
        "base set",
        "base rookie",
        "base rookies",
        "base veteran",
        "base veterans",
    ):
        sub = sub[5:].strip()
    elif sub.lower() in ("base rookie", "base rookies", "base veteran", "base veterans"):
        return "Base"

    sub = re.sub(r"\bA\s*and\s*G\b", "A&G", sub, flags=re.IGNORECASE)
    sub = re.sub(r"\bAandG\b", "A&G", sub, flags=re.IGNORECASE)

    sub = re.sub(r"^(?:Topps\s+)?Allen\s*(?:&|and)\s*Ginter\s+", "", sub, flags=re.IGNORECASE).strip()

    if re.search(r"Framed\s+Relics?\s+Mini", sub, flags=re.IGNORECASE):
        sub = "Framed Mini Relic"

    if re.search(r"Rookie\s+Design\s+Variations?", sub, flags=re.IGNORECASE):
        return "Rookie Design Variation"

    up = sub.upper()
    if up in ("MINI", "MINI VARIATION", "MINI VARIATIONS", "BASE MINI"):
        return "Mini"
    if "MINI" in up:
        if "A&G BACK" in up or "AG BACK" in up:
            return "Mini - A&G Back"
        if "BLACK BORDER" in up:
            return "Mini - Black Border"
        if "CHROME" in up:
            return "Mini - Chrome"
        if "GOLD BORDER" in up:
            return "Mini - Gold Border"
        if "NO NUMBER" in up:
            return "Mini - No Number"
        if "BROOKLYN BACK" in up:
            return "Mini - Brooklyn Back"
        if "WOOD" in up:
            return "Mini - Wood"
        if "METAL" in up:
            return "Mini - Metal"
        sub = re.sub(r"\bVariations?\b", "", sub, flags=re.IGNORECASE)
        sub = re.sub(r"\s+", " ", sub).strip(" -")

    return sub or "Base"


def format_subset_and_serial_text(subset_raw: str, print_run_raw: str, set_raw: str = "", cnum_raw: str = "") -> str:
    """
    Builds the complete Subset/Parallel + Serial string using normalized subset names
    and '#/N' (or '1/1') serial formatting.
    """
    sub = normalize_subset_display_name(subset_raw, set_raw=set_raw, cnum_raw=cnum_raw)

    def _fix_inline_serial(match: re.Match) -> str:
        prefix_ch = match.group(1)
        num_str = match.group(2)
        if prefix_ch == "1" and num_str == "1":
            return "1/1"
        return f"{prefix_ch}#/{int(num_str)}"

    sub = re.sub(r"(^|\s)#?/\s*(\d+)\b", _fix_inline_serial, sub)
    sub = re.sub(r"\b1#/1\b", "1/1", sub)

    pr_formatted = format_serial_print_run(print_run_raw)
    if pr_formatted:
        if not sub.endswith(pr_formatted) and pr_formatted not in sub.split():
            sub = f"{sub} {pr_formatted}".strip()

    return sub or "Base"


def _text_width(text: str, font_name: str, font_size: float) -> float:
    return float(pdfmetrics.stringWidth(text, font_name, font_size))


def _fit_single_line_font_size(
    text: str,
    font_name: str,
    max_width: float,
    preferred_size: float,
    min_size: float = 4.6,
) -> tuple[str, float]:
    """
    Finds the largest font size in [min_size, preferred_size] where text fits within max_width.
    If text still exceeds max_width at min_size, truncates cleanly with '..'.
    """
    sz = preferred_size
    while sz >= min_size:
        if _text_width(text, font_name, sz) <= max_width:
            return text, round(sz, 2)
        sz -= 0.15

    trimmed = text
    while len(trimmed) > 4 and _text_width(trimmed + "..", font_name, min_size) > max_width:
        trimmed = trimmed[:-1].rstrip()
    return (trimmed + ".." if trimmed != text else trimmed), round(min_size, 2)


def _format_player_line_to_fit(
    player_raw: str,
    font_name: str,
    max_width: float,
    preferred_size: float,
    min_size: float = 4.9,
) -> tuple[str, float]:
    """
    Tries the full Player name(s) first (so 'Ronald Acuna Jr./Hank Aaron' stays intact when it fits),
    and only condenses multi-player names to last names (e.g. 'Schwarber/Alonso/Soto') if the full
    string would not fit at min_size.
    """
    p_clean = strip_accents(str(player_raw or "Unknown Player")).strip()
    if _text_width(p_clean, font_name, min_size) <= max_width:
        return _fit_single_line_font_size(p_clean, font_name, max_width, preferred_size, min_size)

    if "/" in p_clean:
        players = [p.strip() for p in p_clean.split("/") if p.strip()]
        short_names = []
        for p in players:
            tokens = p.split()
            if len(tokens) >= 2 and tokens[-1].upper().rstrip(".") in ("JR", "SR", "II", "III", "IV"):
                short_names.append(" ".join(tokens[-2:]))
            elif tokens:
                short_names.append(tokens[-1])
        condensed = "/".join(short_names)
        if _text_width(condensed, font_name, min_size) <= max_width:
            return _fit_single_line_font_size(condensed, font_name, max_width, preferred_size, min_size)
        return _fit_single_line_font_size(condensed, font_name, max_width, preferred_size, 4.5)

    return _fit_single_line_font_size(p_clean, font_name, max_width, preferred_size, 4.5)


def _format_team_line_to_fit(
    team_full: str,
    font_name: str,
    max_width: float,
    preferred_size: float,
    min_size: float = 4.8,
) -> tuple[str, float]:
    """
    Fits the full team name on its own line:
      - Single team (e.g. 'New York Yankees', 'San Diego Padres', 'Atlanta Braves'): full team name.
      - Multi-team card (e.g. 'Jacksonville Jaguars/Cleveland Browns'): tries full names first,
        then team nicknames ('Jaguars / Browns'), then abbreviations ('JAX / CLE').
    """
    if not team_full:
        return "", preferred_size

    if _text_width(team_full, font_name, min_size) <= max_width:
        return _fit_single_line_font_size(team_full, font_name, max_width, preferred_size, min_size)

    if "/" in team_full:
        teams = [t.strip() for t in team_full.split("/") if t.strip()]
        nicknames = [t.split()[-1] for t in teams if t.split()]
        nick_str = " / ".join(nicknames)
        if _text_width(nick_str, font_name, min_size) <= max_width:
            return _fit_single_line_font_size(nick_str, font_name, max_width, preferred_size, min_size)
        abbr_str = " / ".join(get_team_abbreviation(t) for t in teams)
        return _fit_single_line_font_size(abbr_str, font_name, max_width, preferred_size, min_size)

    return _fit_single_line_font_size(team_full, font_name, max_width, preferred_size, 4.6)


def _split_subset_into_lines(
    subset_text: str,
    font_name: str,
    max_width: float,
    preferred_size: float,
    min_one_line_size: float = 4.35,
    min_two_line_size: float = 4.45,
) -> list[tuple[str, float]]:
    """
    Lays out the Subset/Parallel + Serial string following the exact 4-step priority order:
      0. Single Line at Preferred Size
      1. Priority 1 (Bump Serial Number First)
      2. Priority 2 (Shrink Font Size)
      3. Priority 3 (Intelligent Line Break)
    """
    text = subset_text.strip()
    if not text:
        text = "Base"

    pill_pad_single = 4.8
    pill_pad_dual = 11.4

    m_ser = re.search(r"^(.*?)\s+(#/\d+|1/1)$", text)
    if m_ser:
        base_sub = m_ser.group(1).strip()
        serial_tok = m_ser.group(2).strip()
    else:
        base_sub = text
        serial_tok = ""

    if serial_tok:
        avail_dual_w = max(20.0, max_width - pill_pad_dual)
        comb_txt = f"{base_sub} {serial_tok}"
        if _text_width(base_sub, font_name, 5.05) + _text_width(serial_tok, font_name, 5.05) <= avail_dual_w:
            sz = preferred_size
            while sz > 5.05:
                if _text_width(base_sub, font_name, sz) + _text_width(serial_tok, font_name, sz) <= avail_dual_w:
                    break
                sz -= 0.10
            return [(comb_txt, round(sz, 2))]

        avail_single_w = max(20.0, max_width - pill_pad_single)
        if _text_width(base_sub, font_name, min_one_line_size) <= avail_single_w:
            line1_str, sz1 = _fit_single_line_font_size(
                base_sub, font_name, avail_single_w, preferred_size, min_one_line_size
            )
            ser_sz = min(preferred_size, max(sz1, 4.85))
            return [(line1_str, sz1), (serial_tok, round(ser_sz, 2))]

        l1_raw, l2_par = _find_intelligent_subset_break(base_sub, font_name, avail_single_w, min_two_line_size)
        l2_full = f"{l2_par} {serial_tok}".strip()
        l1_str, sz1 = _fit_single_line_font_size(l1_raw, font_name, avail_single_w, preferred_size, min_two_line_size)
        l2_str, sz2 = _fit_single_line_font_size(l2_full, font_name, avail_dual_w, preferred_size, min_two_line_size)
        common_sz = min(sz1, sz2)
        return [(l1_str, common_sz), (l2_str, common_sz)]

    avail_single_w = max(20.0, max_width - pill_pad_single)

    if _text_width(base_sub, font_name, min_one_line_size) <= avail_single_w:
        line_str, sz = _fit_single_line_font_size(
            base_sub, font_name, avail_single_w, preferred_size, min_one_line_size
        )
        return [(line_str, sz)]

    l1_raw, l2_raw = _find_intelligent_subset_break(base_sub, font_name, avail_single_w, min_two_line_size)
    l1_str, sz1 = _fit_single_line_font_size(l1_raw, font_name, avail_single_w, preferred_size, min_two_line_size)
    l2_str, sz2 = _fit_single_line_font_size(l2_raw, font_name, avail_single_w, preferred_size, min_two_line_size)
    common_sz = min(sz1, sz2)
    return [(l1_str, common_sz), (l2_str, common_sz)]


def _find_intelligent_subset_break(
    base_sub: str,
    font_name: str,
    avail_w: float,
    min_sz: float,
) -> tuple[str, str]:
    """
    Splits an extra-long subset string into (line1, line2):
      1. First looks for a complete `[Color/Finish Modifiers] + [Parallel Noun]` suffix
         so a color adjective is NEVER separated from its parallel noun.
      2. Otherwise falls back to the most balanced word boundary.
    """
    for noun_pat in PARALLEL_NOUN_PATTERNS:
        full_pat = rf"^(?P<prefix>.+?)\s+(?P<parallel>{COLOR_OR_FINISH_MODIFIERS}{noun_pat})$"
        m = re.match(full_pat, base_sub, flags=re.IGNORECASE)
        if m:
            prefix_part = m.group("prefix").strip(" -")
            parallel_part = m.group("parallel").strip(" -")
            if prefix_part and parallel_part:
                return prefix_part, parallel_part

    words = base_sub.split()
    if len(words) < 2:
        return base_sub, ""

    best_pair = (words[0], " ".join(words[1:]))
    best_score = 1e9
    for split_i in range(1, len(words)):
        l_cand = " ".join(words[:split_i])
        r_cand = " ".join(words[split_i:])
        w_l = _text_width(l_cand, font_name, min_sz)
        w_r = _text_width(r_cand, font_name, min_sz)
        overflow_pen = max(0.0, w_l - avail_w) * 10.0 + max(0.0, w_r - avail_w) * 10.0
        score = overflow_pen + abs(w_l - w_r)
        if score < best_score:
            best_score = score
            best_pair = (l_cand, r_cand)
    return best_pair


def _build_qr_image_reader(payload_text: str) -> ImageReader:
    """Generates a crisp, zero-border QR code image for ReportLab rendering."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=0,
    )
    qr.add_data(str(payload_text))
    qr.make(fit=True)
    pil_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    pil_qr.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


# ==============================================================================
# 4. SINGLE LABEL CELL RENDERER (QR + SKU/LEAGUE + 4/5-LINE CARD TYPOGRAPHY)
# ==============================================================================
def render_single_card_label(
    c: canvas.Canvas,
    cell_x: float,
    cell_y: float,
    cell_w: float,
    cell_h: float,
    card_row: dict,
    font_reg: str,
    font_bold: str,
    draw_outline: bool = False,
):
    """
    Renders a single card label inside the bounding box (cell_x, cell_y, cell_w, cell_h).
    """
    if draw_outline:
        c.saveState()
        c.setStrokeColorRGB(0.82, 0.82, 0.82)
        c.setLineWidth(0.35)
        c.rect(cell_x, cell_y, cell_w, cell_h, stroke=1, fill=0)
        c.restoreState()

    sku_str = str(card_row.get("SKU", "1000001")).strip() or "1000001"
    set_raw = str(card_row.get("Set", "")).strip()
    sub_raw = str(
        card_row.get("Subset_Parallel")
        or card_row.get("Subset")
        or "Base"
    ).strip()
    cnum_raw = str(
        card_row.get("Card_Number")
        or card_row.get("Card Number")
        or ""
    ).strip().lstrip("#")
    player_raw = strip_accents(str(card_row.get("Player", "Unknown Player"))).strip() or "Unknown Player"
    team_raw = strip_accents(str(card_row.get("Team", ""))).strip()
    pr_raw = format_print_run(
        card_row.get("Print_Run") if "Print_Run" in card_row else card_row.get("Print Run", "")
    )

    league_tag = infer_league_tag(set_raw, team_raw)
    set_short = shorten_set_header(set_raw)

    subset_full_str = format_subset_and_serial_text(sub_raw, pr_raw, set_raw=set_raw, cnum_raw=cnum_raw)
    parallel_rgb, is_colored_parallel, card_tier = resolve_parallel_color_rgb(subset_full_str, pr_raw)
    league_rgb = LEAGUE_COLOR_RGB.get(league_tag, (0.04, 0.18, 0.44))

    # --- CARD-TYPE COLORED PERIMETER BORDER OUTLINE (FOR INSERTS, PARALLELS, AUTOS, RELICS & 1/1s) ---
    if is_colored_parallel:
        c.saveState()
        c.setStrokeColorRGB(*parallel_rgb)
        if card_tier in ("ONE_OF_ONE", "AUTO_RELIC"):
            c.setLineWidth(0.90)
        elif card_tier == "INSERT":
            c.setLineWidth(0.75)
            c.setDash(3, 1.5)
        else:
            c.setLineWidth(0.75)
        inset_b = 1.85
        c.roundRect(
            cell_x + inset_b,
            cell_y + inset_b,
            cell_w - 2.0 * inset_b,
            cell_h - 2.0 * inset_b,
            radius=2.2,
            stroke=1,
            fill=0,
        )
        c.restoreState()

    # --- GEOMETRY & PADDING ---
    pad_x = max(3.0, cell_w * 0.028)
    pad_top = max(2.1, cell_h * 0.060)
    pad_bot = max(2.0, cell_h * 0.056)

    footer_font_sz = max(4.4, min(5.0, cell_h * 0.132))
    footer_h = footer_font_sz + 1.4

    qr_max_h = cell_h - pad_top - pad_bot - footer_h - 1.2
    qr_size = max(14.0, min(cell_w * 0.232, qr_max_h))

    sku_part_txt = f"{sku_str} \u2022 "
    sku_part_w = _text_width(sku_part_txt, font_bold, footer_font_sz)
    lg_part_w = _text_width(league_tag, font_bold, footer_font_sz)
    footer_w = sku_part_w + lg_part_w
    left_col_w = max(qr_size, footer_w)

    qr_x = cell_x + pad_x + max(0.0, (left_col_w - qr_size) * 0.5)
    qr_y = cell_y + cell_h - pad_top - qr_size

    qr_reader = _build_qr_image_reader(sku_str)
    c.drawImage(qr_reader, qr_x, qr_y, width=qr_size, height=qr_size, mask="auto")

    footer_x = cell_x + pad_x + max(0.0, (left_col_w - footer_w) * 0.5)
    footer_y = cell_y + pad_bot + 0.4
    c.setFont(font_bold, footer_font_sz)
    c.setFillColorRGB(0.0, 0.0, 0.0)
    c.drawString(footer_x, footer_y, sku_part_txt)
    c.setFillColorRGB(*league_rgb)
    c.drawString(footer_x + sku_part_w, footer_y, league_tag)

    # --- VERTICAL DIVIDER LINE BETWEEN QR SECTION & INFO SECTION ---
    col_gap = max(3.6, cell_w * 0.036)
    divider_x = cell_x + pad_x + left_col_w + (col_gap * 0.46)
    c.saveState()
    if is_colored_parallel:
        c.setStrokeColorRGB(*parallel_rgb)
        c.setLineWidth(0.70)
    else:
        c.setStrokeColorRGB(0.55, 0.58, 0.64)
        c.setLineWidth(0.50)
    c.line(divider_x, cell_y + pad_bot + 0.4, divider_x, cell_y + cell_h - pad_top - 0.4)
    c.restoreState()

    # --- RIGHT-HAND TEXT COLUMN ---
    text_x = cell_x + pad_x + left_col_w + col_gap
    max_text_w = max(25.0, (cell_x + cell_w - pad_x - 0.8) - text_x)
    avail_text_h = cell_h - pad_top - pad_bot

    full_team = expand_full_team_name(team_raw, league=league_tag)
    is_team_card = bool(
        full_team
        and re.sub(r"[^A-Z0-9]", "", player_raw.upper()) == re.sub(r"[^A-Z0-9]", "", full_team.upper())
    )

    scale_h = min(1.30, max(0.75, cell_h / 36.0))
    pref_hdr_sz = round(6.05 * scale_h, 2)
    pref_plr_sz = round(6.05 * scale_h, 2)
    pref_tm_sz = round(5.45 * scale_h, 2)
    pref_sub_sz = round(5.35 * scale_h, 2)

    sub_font_to_use = font_bold if is_colored_parallel else font_reg
    sub_lines = _split_subset_into_lines(
        subset_full_str,
        sub_font_to_use,
        max_text_w,
        preferred_size=pref_sub_sz,
        min_one_line_size=round(4.35 * scale_h, 2),
        min_two_line_size=round(4.45 * scale_h, 2),
    )

    max_allowed_lines = 4 if cell_h < 30.0 else 5
    has_team_line = bool(full_team and not is_team_card and (2 + 1 + len(sub_lines) <= max_allowed_lines))

    total_lines_count = 2 + (1 if has_team_line else 0) + len(sub_lines)
    if total_lines_count >= 5:
        pref_hdr_sz = round(5.55 * scale_h, 2)
        pref_plr_sz = round(5.55 * scale_h, 2)
        pref_tm_sz = round(5.00 * scale_h, 2)
        pref_sub_sz = round(4.95 * scale_h, 2)
        sub_lines = _split_subset_into_lines(
            subset_full_str,
            sub_font_to_use,
            max_text_w,
            preferred_size=pref_sub_sz,
            min_one_line_size=round(4.30 * scale_h, 2),
            min_two_line_size=round(4.40 * scale_h, 2),
        )

    rendered_lines: list[tuple[str, str, float, tuple[float, float, float], bool]] = []

    hdr_str, hdr_sz = _fit_header_line_preserving_card_num(
        set_short, cnum_raw, font_bold, max_text_w, pref_hdr_sz, min_size=round(4.85 * scale_h, 2)
    )
    rendered_lines.append((hdr_str, font_bold, hdr_sz, (0.08, 0.16, 0.32), False))

    if has_team_line or not full_team or is_team_card:
        plr_str, plr_sz = _format_player_line_to_fit(
            player_raw, font_bold, max_text_w, pref_plr_sz, min_size=round(4.8 * scale_h, 2)
        )
        rendered_lines.append((plr_str, font_bold, plr_sz, (0.0, 0.0, 0.0), False))
    else:
        abbr = get_team_abbreviation(full_team)
        plr_with_abbr = f"{player_raw} ({abbr})" if abbr else player_raw
        plr_str, plr_sz = _format_player_line_to_fit(
            plr_with_abbr, font_bold, max_text_w, pref_plr_sz, min_size=round(4.7 * scale_h, 2)
        )
        rendered_lines.append((plr_str, font_bold, plr_sz, (0.0, 0.0, 0.0), False))

    if has_team_line:
        tm_str, tm_sz = _format_team_line_to_fit(
            full_team, font_reg, max_text_w, pref_tm_sz, min_size=round(4.7 * scale_h, 2)
        )
        rendered_lines.append((tm_str, font_reg, tm_sz, (0.24, 0.28, 0.34), False))

    for s_txt, s_sz in sub_lines:
        rendered_lines.append((s_txt, sub_font_to_use, s_sz, parallel_rgb, True))

    line_heights = [
        (sz * 1.24 if (is_sub and is_colored_parallel) else sz * 1.09)
        for _, _, sz, _, is_sub in rendered_lines
    ]
    total_block_h = sum(line_heights)
    if total_block_h > avail_text_h and total_block_h > 0:
        shrink_ratio = avail_text_h / total_block_h
        rendered_lines = [
            (t, fn, round(sz * shrink_ratio, 2), col_rgb, is_sub)
            for t, fn, sz, col_rgb, is_sub in rendered_lines
        ]
        line_heights = [
            (sz * 1.20 if (is_sub and is_colored_parallel) else sz * 1.06)
            for _, _, sz, _, is_sub in rendered_lines
        ]
        total_block_h = sum(line_heights)

    extra_gap = max(0.0, (avail_text_h - total_block_h) / max(1, len(rendered_lines)))
    extra_gap = min(1.05, extra_gap)

    curr_top_y = cell_y + cell_h - pad_top
    for idx_l, (txt_val, f_name, f_sz, col_rgb, is_sub) in enumerate(rendered_lines):
        if is_sub and is_colored_parallel:
            baseline_y = curr_top_y - (f_sz * 0.90)
            pill_h = f_sz * 1.06
            pill_y = baseline_y - (f_sz * 0.18)
            pad_pill_x = 2.2

            m_ser_only = re.match(r"^(#/\d+|1/1)$", txt_val.strip())
            m_ser_inline = re.search(r"^(.*?)\s+(#/\d+|1/1)$", txt_val.strip())

            if m_ser_only:
                ser_part = m_ser_only.group(1).strip()
                ser_badge_rgb = resolve_serial_badge_rgb(col_rgb, ser_part)
                ser_w = _text_width(ser_part, font_bold, f_sz)
                pill_w = min(max_text_w, ser_w + 2.0 * pad_pill_x)
                c.saveState()
                c.setFillColorRGB(*ser_badge_rgb)
                c.roundRect(text_x, pill_y, pill_w, pill_h, radius=1.5, stroke=0, fill=1)
                c.setFont(font_bold, f_sz)
                c.setFillColorRGB(1.0, 1.0, 1.0)
                c.drawString(text_x + pad_pill_x, baseline_y, ser_part)
                c.restoreState()
            elif m_ser_inline:
                base_part = m_ser_inline.group(1).strip()
                ser_part = m_ser_inline.group(2).strip()
                ser_badge_rgb = resolve_serial_badge_rgb(col_rgb, ser_part)

                base_w = _text_width(base_part, font_bold, f_sz)
                ser_w = _text_width(ser_part, font_bold, f_sz)
                pill_1_w = base_w + 2.0 * pad_pill_x
                pill_2_w = ser_w + 2.0 * pad_pill_x
                gap_pills = 1.8

                total_pills_w = pill_1_w + gap_pills + pill_2_w
                if total_pills_w > max_text_w and total_pills_w > 0:
                    adj_scale = max(0.82, (max_text_w - 4.0 * pad_pill_x - gap_pills) / max(1.0, base_w + ser_w))
                    f_sz = round(f_sz * adj_scale, 2)
                    base_w = _text_width(base_part, font_bold, f_sz)
                    ser_w = _text_width(ser_part, font_bold, f_sz)
                    pill_1_w = base_w + 2.0 * pad_pill_x
                    pill_2_w = ser_w + 2.0 * pad_pill_x

                c.saveState()
                c.setFillColorRGB(*col_rgb)
                c.roundRect(text_x, pill_y, pill_1_w, pill_h, radius=1.5, stroke=0, fill=1)
                c.setFont(font_bold, f_sz)
                c.setFillColorRGB(1.0, 1.0, 1.0)
                c.drawString(text_x + pad_pill_x, baseline_y, base_part)

                ser_pill_x = text_x + pill_1_w + gap_pills
                c.setFillColorRGB(*ser_badge_rgb)
                c.roundRect(ser_pill_x, pill_y, pill_2_w, pill_h, radius=1.5, stroke=0, fill=1)
                c.setFont(font_bold, f_sz)
                c.setFillColorRGB(1.0, 1.0, 1.0)
                c.drawString(ser_pill_x + pad_pill_x, baseline_y, ser_part)
                c.restoreState()
            else:
                txt_w = _text_width(txt_val, font_bold, f_sz)
                pill_w = min(max_text_w, txt_w + 2.0 * pad_pill_x)
                c.saveState()
                c.setFillColorRGB(*col_rgb)
                c.roundRect(text_x, pill_y, pill_w, pill_h, radius=1.5, stroke=0, fill=1)
                c.setFont(font_bold, f_sz)
                c.setFillColorRGB(1.0, 1.0, 1.0)
                c.drawString(text_x + pad_pill_x, baseline_y, txt_val)
                c.restoreState()
        else:
            baseline_y = curr_top_y - (f_sz * 0.84)
            c.setFont(f_name, f_sz)
            c.setFillColorRGB(*col_rgb)
            c.drawString(text_x, baseline_y, txt_val)

        curr_top_y -= (line_heights[idx_l] + extra_gap)

    c.setFillColorRGB(0.0, 0.0, 0.0)


# ==============================================================================
# 5. PRODUCTION LABEL PDF & 1-PAGE PRINTER ALIGNMENT TEST GENERATOR
# ==============================================================================
def _draw_top_left_orientation_mark(
    c: canvas.Canvas,
    geom: dict,
    font_bold: str,
    x_offset_mm: float = 0.0,
    y_offset_mm: float = 0.0,
):
    """
    Draws a small registration mark in the top-left waste margin above Row 1, Column 1
    ('TOP-LEFT CORNER (12.2mm Left Margin)') so you can immediately verify sheet orientation
    against your marked Top-Left corner without touching any sticker cells.
    """
    page_h_pt = geom["page_h"] * INCH
    margin_x_pt = geom["margin_x"] * INCH + (x_offset_mm * MM)
    top_grid_y_pt = page_h_pt - (geom["margin_y"] * INCH) + (y_offset_mm * MM)

    c.saveState()
    c.setFont(font_bold, 5.2)
    c.setFillColorRGB(0.28, 0.34, 0.44)
    c.setStrokeColorRGB(0.28, 0.34, 0.44)
    c.setLineWidth(0.5)

    tick_y = min(page_h_pt - 6.0, top_grid_y_pt + 4.5)
    c.line(margin_x_pt, tick_y - 2.5, margin_x_pt, tick_y + 2.5)
    c.line(margin_x_pt, tick_y, margin_x_pt + 5.0, tick_y)

    left_mm = round(geom["margin_x"] * 25.4, 1)
    c.drawString(
        margin_x_pt + 6.5,
        tick_y - 1.6,
        f"TOP-LEFT CORNER ({left_mm:.1f}mm Left Margin)",
    )
    c.restoreState()


def _cell_bottom_left_xy(
    geom: dict,
    row_1based: int,
    col_1based: int,
    x_offset_mm: float = 0.0,
    y_offset_mm: float = 0.0,
) -> tuple[float, float, float, float]:
    """
    Computes the ReportLab bottom-left (x, y) and (width, height) in points for a
    1-based (row, col) cell on the sheet, applying printer calibration offsets.
    """
    page_h_pt = geom["page_h"] * INCH
    cell_w_pt = geom["label_w"] * INCH
    cell_h_pt = geom["label_h"] * INCH
    margin_x_pt = geom["margin_x"] * INCH
    margin_y_pt = geom["margin_y"] * INCH
    pitch_x_pt = geom["pitch_x"] * INCH
    pitch_y_pt = geom["pitch_y"] * INCH

    x_pt = margin_x_pt + (col_1based - 1) * pitch_x_pt + (x_offset_mm * MM)
    top_y_pt = page_h_pt - margin_y_pt - (row_1based - 1) * pitch_y_pt + (y_offset_mm * MM)
    y_pt = top_y_pt - cell_h_pt
    return x_pt, y_pt, cell_w_pt, cell_h_pt


def generate_labels_pdf(
    cards_source: Union[pd.DataFrame, Path, str],
    output_pdf_path: Optional[Union[Path, str]] = None,
    template_key: str = "R037L",
    custom_spec: Optional[dict] = None,
    start_row: int = 1,
    start_col: int = 1,
    used_cells_page1: Optional[list[tuple[int, int]]] = None,
    x_offset_mm: float = 0.0,
    y_offset_mm: float = 0.0,
    draw_cell_outlines: bool = False,
) -> dict:
    """
    Generates a multi-page printable QR/SKU label PDF for a DataFrame or CSV manifest.
    Returns a summary dict with output_pdf_path, cards_printed, pages_rendered, and printed_skus.
    """
    ensure_directories()
    if isinstance(cards_source, (Path, str)):
        df = pd.read_csv(cards_source, dtype=str, keep_default_na=False)
    elif isinstance(cards_source, pd.DataFrame):
        df = cards_source.copy()
    else:
        raise ValueError("cards_source must be a pandas DataFrame or path to a CSV file.")

    geom = resolve_template_spec(template_key, custom_spec=custom_spec)
    font_reg, font_bold, font_label = ensure_and_load_fonts()

    if output_pdf_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_pdf_path = LABELS_OUTPUT_DIR / f"Labels_{geom['key']}_{ts}.pdf"
    else:
        output_pdf_path = Path(output_pdf_path)
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if df.empty:
        c = canvas.Canvas(str(output_pdf_path), pagesize=(geom["page_w"] * INCH, geom["page_h"] * INCH))
        c.save()
        return {
            "output_pdf_path": output_pdf_path,
            "cards_printed": 0,
            "pages_rendered": 0,
            "printed_skus": [],
            "template_key": geom["key"],
            "font_used": font_label,
        }

    records = df.to_dict(orient="records")
    coords = _build_available_cell_sequence(
        total_cards=len(records),
        cols=geom["cols"],
        rows=geom["rows"],
        start_row=start_row,
        start_col=start_col,
        used_cells_page1=used_cells_page1,
    )

    c = canvas.Canvas(str(output_pdf_path), pagesize=(geom["page_w"] * INCH, geom["page_h"] * INCH))
    c.setTitle(f"Tabulas Card Labels - {geom['name']}")

    _draw_top_left_orientation_mark(c, geom, font_bold, x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm)

    current_page = 0
    printed_skus: list[str] = []

    for rec, (page_idx, r_1b, c_1b) in zip(records, coords):
        while current_page < page_idx:
            c.showPage()
            _draw_top_left_orientation_mark(c, geom, font_bold, x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm)
            current_page += 1

        cx, cy, cw, ch = _cell_bottom_left_xy(
            geom,
            r_1b,
            c_1b,
            x_offset_mm=x_offset_mm,
            y_offset_mm=y_offset_mm,
        )
        render_single_card_label(
            c=c,
            cell_x=cx,
            cell_y=cy,
            cell_w=cw,
            cell_h=ch,
            card_row=rec,
            font_reg=font_reg,
            font_bold=font_bold,
            draw_outline=draw_cell_outlines,
        )
        sku_val = str(rec.get("SKU", "")).strip()
        if sku_val:
            printed_skus.append(sku_val)

    c.save()
    total_pages = (coords[-1][0] + 1) if coords else 1

    return {
        "output_pdf_path": output_pdf_path,
        "cards_printed": len(records),
        "pages_rendered": total_pages,
        "printed_skus": printed_skus,
        "template_key": geom["key"],
        "font_used": font_label,
    }


def _draw_calibration_rulers(c: canvas.Canvas, page_w_pt: float, page_h_pt: float, font_reg: str):
    """Draws millimeter calibration rulers along the top and left edges of the test sheet."""
    c.saveState()
    c.setStrokeColorRGB(0.45, 0.48, 0.55)
    c.setFillColorRGB(0.35, 0.38, 0.45)
    c.setLineWidth(0.4)
    c.setFont(font_reg, 4.8)

    max_mm_x = int(page_w_pt / MM)
    for mm_i in range(0, max_mm_x + 1, 2):
        x_pt = mm_i * MM
        tick_h = 8.0 if mm_i % 10 == 0 else (5.0 if mm_i % 5 == 0 else 2.5)
        c.line(x_pt, page_h_pt, x_pt, page_h_pt - tick_h)
        if mm_i > 0 and mm_i % 10 == 0:
            c.drawCentredString(x_pt, page_h_pt - 13.5, f"{mm_i}")

    max_mm_y = int(page_h_pt / MM)
    for mm_i in range(0, max_mm_y + 1, 2):
        y_pt = page_h_pt - (mm_i * MM)
        tick_w = 8.0 if mm_i % 10 == 0 else (5.0 if mm_i % 5 == 0 else 2.5)
        c.line(0, y_pt, tick_w, y_pt)
        if mm_i > 0 and mm_i % 10 == 0:
            c.drawString(9.5, y_pt - 1.8, f"{mm_i}")

    c.restoreState()


def generate_alignment_test_pdf(
    output_pdf_path: Optional[Union[Path, str]] = None,
    template_key: str = "R037L",
    custom_spec: Optional[dict] = None,
    x_offset_mm: float = 0.0,
    y_offset_mm: float = 0.0,
    used_cells_page1: Optional[list[tuple[int, int]]] = None,
    start_row: int = 1,
    start_col: int = 1,
) -> Path:
    """
    Generates a 1-page Printer Alignment & Calibration Test Sheet.
    """
    ensure_directories()
    geom = resolve_template_spec(template_key, custom_spec=custom_spec)
    font_reg, font_bold, font_label = ensure_and_load_fonts()

    if output_pdf_path is None:
        output_pdf_path = LABELS_OUTPUT_DIR / f"Alignment_Test_{geom['key']}.pdf"
    else:
        output_pdf_path = Path(output_pdf_path)
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    page_w_pt = geom["page_w"] * INCH
    page_h_pt = geom["page_h"] * INCH
    cols = geom["cols"]
    rows = geom["rows"]

    c = canvas.Canvas(str(output_pdf_path), pagesize=(page_w_pt, page_h_pt))
    c.setTitle(f"Alignment Test Sheet - {geom['name']}")

    _draw_calibration_rulers(c, page_w_pt, page_h_pt, font_reg)
    _draw_top_left_orientation_mark(c, geom, font_bold, x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm)

    hdr_y = page_h_pt - max(22.0, (geom["margin_y"] * INCH) * 0.62)
    c.setFont(font_bold, 6.8)
    c.setFillColorRGB(0.10, 0.16, 0.30)
    hdr_line = (
        f"ALIGNMENT TEST SHEET: {geom['name']}  |  Font: {font_label}  |  "
        f"Offset: X={x_offset_mm:+.1f}mm, Y={y_offset_mm:+.1f}mm  |  "
        f"Print at 100% / Actual Size"
    )
    c.drawCentredString(page_w_pt * 0.5, hdr_y, hdr_line)

    used_set = set()
    start_linear = (max(1, start_row) - 1) * cols + (max(1, start_col) - 1)
    for r_i in range(1, rows + 1):
        for c_i in range(1, cols + 1):
            if (r_i - 1) * cols + (c_i - 1) < start_linear:
                used_set.add((r_i, c_i))
    if used_cells_page1:
        for r_i, c_i in used_cells_page1:
            used_set.add((int(r_i), int(c_i)))

    mid_r = max(1, min(rows, (rows + 1) // 2))
    mid_c = max(1, min(cols, (cols + 1) // 2))

    sample_cards_by_cell = {
        (1, 1): {
            "SKU": "1000001",
            "Set": "2026 Topps Baseball",
            "Card Number": "1",
            "Player": "Aaron Judge",
            "Team": "New York Yankees",
            "Subset": "Base",
            "Print Run": "",
        },
        (1, cols): {
            "SKU": "1000005",
            "Set": "2026 Bowman Baseball",
            "Card Number": "BCP-15",
            "Player": "Leo De Vries",
            "Team": "San Diego Padres",
            "Subset": "Chrome Prospects Auto Gold Refractor",
            "Print Run": "50",
        },
        (mid_r, mid_c): {
            "SKU": "1000053",
            "Set": "2025 Panini Prizm Football",
            "Card Number": "301",
            "Player": "Travis Hunter/Shedeur Sanders",
            "Team": "Jacksonville Jaguars/Cleveland Browns",
            "Subset": "Rookie Prizm Black Finite",
            "Print Run": "1",
        },
        (rows, 1): {
            "SKU": "1000096",
            "Set": "2025 Topps Allen & Ginter Baseball",
            "Card Number": "103",
            "Player": "Ronald Acuna Jr.",
            "Team": "Atlanta Braves",
            "Subset": "Mini Black Bordered",
            "Print Run": "",
        },
        (rows, cols): {
            "SKU": "1000100",
            "Set": "2025 Topps Chrome Platinum Anniversary Baseball",
            "Card Number": "55DH-11",
            "Player": "Ronald Acuna Jr./Hank Aaron",
            "Team": "Atlanta Braves",
            "Subset": "1955 Topps Double Headers SuperFractor",
            "Print Run": "1",
        },
    }

    for r_i in range(1, rows + 1):
        for c_i in range(1, cols + 1):
            cx, cy, cw, ch = _cell_bottom_left_xy(
                geom,
                r_i,
                c_i,
                x_offset_mm=x_offset_mm,
                y_offset_mm=y_offset_mm,
            )
            linear_idx = (r_i - 1) * cols + c_i

            if (r_i, c_i) in sample_cards_by_cell and (r_i, c_i) not in used_set:
                render_single_card_label(
                    c=c,
                    cell_x=cx,
                    cell_y=cy,
                    cell_w=cw,
                    cell_h=ch,
                    card_row=sample_cards_by_cell[(r_i, c_i)],
                    font_reg=font_reg,
                    font_bold=font_bold,
                    draw_outline=True,
                )
                continue

            c.saveState()
            if (r_i, c_i) in used_set:
                c.setStrokeColorRGB(0.85, 0.65, 0.65)
                c.setDash(2, 2)
                c.setLineWidth(0.35)
                c.rect(cx, cy, cw, ch, stroke=1, fill=0)
                c.setFillColorRGB(0.75, 0.35, 0.35)
                c.setFont(font_reg, 5.2)
                c.drawCentredString(cx + cw * 0.5, cy + ch * 0.5 - 2.0, f"R{r_i}:C{c_i} [SKIP]")
            else:
                c.setStrokeColorRGB(0.68, 0.72, 0.78)
                c.setLineWidth(0.4)
                c.rect(cx, cy, cw, ch, stroke=1, fill=0)

                mid_x, mid_y = cx + cw * 0.5, cy + ch * 0.5
                c.setStrokeColorRGB(0.82, 0.85, 0.88)
                c.line(mid_x - 3.0, mid_y, mid_x + 3.0, mid_y)
                c.line(mid_x, mid_y - 3.0, mid_x, mid_y + 3.0)

                c.setFillColorRGB(0.32, 0.36, 0.42)
                c.setFont(font_reg, 5.4)
                c.drawCentredString(mid_x, mid_y - 2.0, f"R{r_i}:C{c_i} (#{linear_idx})")
            c.restoreState()

    c.save()
    return output_pdf_path