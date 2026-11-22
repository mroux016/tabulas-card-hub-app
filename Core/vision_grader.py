from __future__ import annotations
# ==============================================================================
# Core/vision_grader.py - 4-ANGLE HORIZONTAL-AWARE BACK OCR, FLATBED SPLITTER,
# 2-STAGE WHOLE-IMAGE (FRONT + BACK) CONFIRMATION, CARDSIGHT FALLBACK & GRADER
# ==============================================================================
import io
import os
import pickle
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import json
from concurrent.futures import ThreadPoolExecutor
from Core.compute_backend import (
    demote_to_cpu_on_error,
    get_accelerated_rapidocr,
    load_compute_settings,
    opencl_clahe_enhance,
    opencl_highpass_and_cross_weave,
)
from Core.neural_vision import (
    calibrate_neural_cosine_to_card_sim,
    flush_neural_embeddings_if_dirty,
    get_neural_embedding_engine,
    get_or_compute_image_descriptor,
    get_or_compute_image_embedding,
    is_neural_embeddings_enabled,
    precompute_batch_image_descriptors,
    score_multiregion_parallel_pair,
    score_parallel_group_vectorized,
    search_set_neural_embeddings,
)


def _compute_hybrid_neural_sim(
    scan_crop_rgb: np.ndarray,
    classical_sim: float,
    ref_path: Optional[str] = None,
    ref_crop_rgb: Optional[np.ndarray] = None,
    scan_emb: Optional[np.ndarray] = None,
    neural_weight: float = 0.55,
    scan_desc: Optional[dict] = None,
    match_mode: str = "identity",
) -> tuple[float, Optional[np.ndarray]]:
    """
    Blends DINOv2-small semantic/multi-region similarity (`neural_weight`) with Classical ZNCC/SSIM/LAB
    (`1 - neural_weight`) whenever DINOv2 is installed & enabled. Falls back cleanly to
    `classical_sim` with zero overhead when DINOv2 is not installed.
    """
    if not is_neural_embeddings_enabled():
        return classical_sim, scan_emb
    try:
        eng = get_neural_embedding_engine(load_now=True)
        if eng is None or not eng.is_ready:
            return classical_sim, scan_emb

        q_desc = scan_desc
        if q_desc is None and scan_emb is not None:
            q_desc = {"vec": scan_emb}
        if q_desc is None:
            q_desc = eng.extract_descriptor(scan_crop_rgb, include_color_foil=(match_mode != "identity"))
        if not isinstance(q_desc, dict) or q_desc.get("vec") is None:
            return classical_sim, None
        q_emb = q_desc["vec"]

        r_desc = None
        if ref_path:
            r_desc = get_or_compute_image_descriptor(ref_path, require_multiregion=(match_mode != "identity"))
        if r_desc is None and ref_crop_rgb is not None:
            r_desc = eng.extract_descriptor(ref_crop_rgb, include_color_foil=(match_mode != "identity"))
        if not isinstance(r_desc, dict) or r_desc.get("vec") is None:
            return classical_sim, q_emb

        if match_mode != "identity" or (q_desc.get("center_vec") is not None and r_desc.get("center_vec") is not None):
            mr_res = score_multiregion_parallel_pair(q_desc, r_desc, mode=match_mode)
            n_sim = float(mr_res["score"])
        else:
            raw_cos = float(np.dot(q_emb, r_desc["vec"]))
            n_sim = calibrate_neural_cosine_to_card_sim(raw_cos)

        blended = float(neural_weight) * n_sim + (1.0 - float(neural_weight)) * float(classical_sim)
        return round(float(np.clip(blended, 0.0, 1.0)), 4), q_emb
    except Exception:
        return classical_sim, scan_emb

import cv2
try:
    import pymupdf as fitz
except ImportError:
    import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont

__version__ = "0.24.0-beta.43"
__last_updated__ = "2026-11-21 03:10:00"

from Core.config import (
    ARCHIVE_DIR,
    BATCH_MANIFEST_COLUMNS,
    BATCHES_DIR,
    CARDSIGHT_API_KEY,
    CARDSIGHT_IDENTIFY_URL,
    CARDSIGHT_SPORT_ENDPOINTS,
    CHECKLIST_PATH,
    CMP_SUBSET_HINTS,
    FEATURE_CACHE_FILE,
    REFERENCE_TEMPLATES_DIR,
    REVIEWED_CARDS_DIR,
    RUNTIME_CONFIG,
    atomic_write_bytes,
    build_card_image_filenames,
    build_card_image_stem,
    canonical_set_key,
    canonical_subset_key,
    ensure_directories,
    format_print_run,
    norm,
    parse_unified_card_filename,
    sanitize_filename_part,
    strip_accents,
)
from Core.database import (
    apply_manifest_overrides_and_rename,
    get_existing_copy_count,
    get_next_sku_int,
    load_inventory_df,
    load_master_checklist,
    save_inventory_df,
)
from Core.market_engine import (
    build_comp_key,
    compute_tier_aware_roi_and_recommendation,
    load_grading_tiers_cache,
    load_market_alert_settings,
    load_market_comps_cache,
)


# ==============================================================================
# 0. GENERAL PARSING & OCR ENGINE HELPERS
# ==============================================================================
def parse_price_val(val, default_val: Optional[float] = 1.00) -> Optional[float]:
    if val is None:
        return default_val
    s = re.sub(r"[^0-9.\-]", "", str(val).strip())
    if not s or s in (".", "-", "-."):
        return default_val
    try:
        return float(s)
    except Exception:
        return default_val


def _get_rapid_ocr_engine(log_cb: Optional[Callable[[str], None]] = None):
    """GPU-accelerated RapidOCR engine (DirectML / CUDA) with 100% automatic CPU fallback."""
    return get_accelerated_rapidocr(log_cb=log_cb)


def _run_rapidocr_lines(img_np: np.ndarray) -> list[str]:
    if img_np is None or img_np.size == 0:
        return []
    ocr_engine = _get_rapid_ocr_engine()
    if ocr_engine is None:
        return []
    for attempt in range(2):
        try:
            res, _ = ocr_engine(img_np)
            if not res:
                return []
            lines = []
            for item in res:
                if len(item) >= 2 and item[1]:
                    txt = str(item[1]).strip()
                    if txt:
                        lines.append(txt)
            return lines
        except Exception as e:
            if attempt == 0:
                demote_to_cpu_on_error(e)
                ocr_engine = _get_rapid_ocr_engine()
                if ocr_engine is None:
                    return []
            else:
                return []
    return []


def _run_rapidocr_detailed(img_np: np.ndarray) -> list[dict]:
    """
    Runs GPU-accelerated RapidOCR (with automatic CPU retry on GPU/OOM errors) and returns
    bounding-box geometry + confidence for each detected text line.
    """
    if img_np is None or img_np.size == 0:
        return []
    ih, iw = float(img_np.shape[0]), float(img_np.shape[1])
    if ih <= 0 or iw <= 0:
        return []
    ocr_engine = _get_rapid_ocr_engine()
    if ocr_engine is None:
        return []
    for attempt in range(2):
        try:
            res, _ = ocr_engine(img_np)
            if not res:
                return []
            out = []
            for item in res:
                if len(item) < 2 or not item[1]:
                    continue
                txt = str(item[1]).strip()
                if not txt:
                    continue
                box = item[0]
                conf = float(item[2]) if len(item) >= 3 and item[2] is not None else 0.85
                xs = [float(pt[0]) for pt in box] if box else [0.0, 1.0]
                ys = [float(pt[1]) for pt in box] if box else [0.0, 1.0]
                bw = max(1.0, max(xs) - min(xs))
                bh = max(1.0, max(ys) - min(ys))
                cx = (min(xs) + max(xs)) * 0.5 / iw
                cy = (min(ys) + max(ys)) * 0.5 / ih
                out.append({"text": txt, "conf": conf, "bw": bw, "bh": bh, "cx": cx, "cy": cy})
            return out
        except Exception as e:
            if attempt == 0:
                demote_to_cpu_on_error(e)
                ocr_engine = _get_rapid_ocr_engine()
                if ocr_engine is None:
                    return []
            else:
                return []
    return []


def render_pdf_page_to_pil(pdf_path: Path, page_index: int = 0, dpi: int = 600) -> Optional[Image.Image]:
    try:
        doc = fitz.open(str(pdf_path))
        if page_index >= len(doc):
            doc.close()
            return None
        page = doc.load_page(page_index)
        zoom = float(dpi) / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return img
    except Exception:
        return None


# ==============================================================================
# 1. MULTI-CARD FLATBED PDF SPLITTER & FRONT/BACK PAIRING ENGINE
# ==============================================================================
def _detect_flatbed_card_regions(page_img: Image.Image) -> list[tuple[int, int, int, int]]:
    w, h = page_img.size
    page_area = float(w * h)
    scale = 1200.0 / max(w, h)
    sw, sh = max(100, int(w * scale)), max(100, int(h * scale))
    small = np.array(page_img.resize((sw, sh), Image.Resampling.BILINEAR))

    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(blur, 30, 110)
    non_white = ((gray < 242) & (gray > 12)).astype(np.uint8) * 255
    combined = cv2.bitwise_or(edges, non_white)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)

    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    small_area = float(sw * sh)

    boxes = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        box_area = float(cw * ch)
        if not (0.045 * small_area <= box_area <= 0.42 * small_area):
            continue
        aspect = max(cw, ch) / max(1.0, float(min(cw, ch)))
        if not (1.12 <= aspect <= 1.85):
            continue
        pad_x = int(cw * 0.03)
        pad_y = int(ch * 0.03)
        ox1 = max(0, int((x - pad_x) / scale))
        oy1 = max(0, int((y - pad_y) / scale))
        ox2 = min(w, int((x + cw + pad_x) / scale))
        oy2 = min(h, int((y + ch + pad_y) / scale))
        if (ox2 - ox1) * (oy2 - oy1) < 0.70 * page_area:
            boxes.append((ox1, oy1, ox2, oy2))

    if len(boxes) <= 1:
        return []

    row_band_h = max(100, int(h * 0.18))
    boxes.sort(key=lambda b: (int(((b[1] + b[3]) * 0.5) // row_band_h), (b[0] + b[2]) * 0.5))
    return boxes


def expand_flatbed_pdfs_in_batch_folder(
    batch_folder: Path,
    pdf_files: Optional[list[Path]] = None,
    flip_mode: str = "auto",
    log_cb: Optional[Callable[[str], None]] = None,
) -> tuple[list[Path], int]:
    batch_folder = Path(batch_folder)
    if pdf_files is None:
        pdf_files = sorted(batch_folder.glob("*.pdf"))

    created_count = 0
    for pdf_p in list(pdf_files):
        if "_FBCard" in pdf_p.stem:
            continue
        try:
            doc = fitz.open(str(pdf_p))
            num_pages = len(doc)
            max_pt_dim = 0.0
            if num_pages >= 2:
                r0 = doc.load_page(0).rect
                max_pt_dim = max(float(r0.width), float(r0.height))
            doc.close()
        except Exception:
            continue

        if num_pages < 2:
            continue
        # Fast bypass: standard single-card feeder scans (~2.5" x 3.5" = 180pt x 252pt) are never multi-card flatbed sheets
        if 0.0 < max_pt_dim < 420.0:
            continue
        if log_cb:
            log_cb(f"  ✂️ Checking large PDF '{pdf_p.name}' ({max_pt_dim / 72.0:.1f} in) for multi-card flatbed layout...")

        p1_img = render_pdf_page_to_pil(pdf_p, 0, dpi=300)
        p2_img = render_pdf_page_to_pil(pdf_p, 1, dpi=300)
        if p1_img is None or p2_img is None:
            continue

        boxes_p1 = _detect_flatbed_card_regions(p1_img)
        if len(boxes_p1) < 2:
            continue

        boxes_p2 = _detect_flatbed_card_regions(p2_img)
        if len(boxes_p2) != len(boxes_p1):
            boxes_p2 = list(boxes_p1)

        p1_hi = render_pdf_page_to_pil(pdf_p, 0, dpi=RUNTIME_CONFIG.get("scanner_dpi", 600)) or p1_img
        p2_hi = render_pdf_page_to_pil(pdf_p, 1, dpi=RUNTIME_CONFIG.get("scanner_dpi", 600)) or p2_img
        sx = p1_hi.width / float(p1_img.width)
        sy = p1_hi.height / float(p1_img.height)

        if flip_mode == "mirrored_x":
            row_band = max(100, int(p2_img.height * 0.18))
            grouped_rows: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
            for b in boxes_p2:
                r_key = int(((b[1] + b[3]) * 0.5) // row_band)
                grouped_rows[r_key].append(b)
            paired_b2 = []
            for r_key in sorted(grouped_rows.keys()):
                row_list = sorted(grouped_rows[r_key], key=lambda b: b[0], reverse=True)
                paired_b2.extend(row_list)
            boxes_p2 = paired_b2
        else:
            used_b2 = set()
            matched_b2 = []
            for b1 in boxes_p1:
                cx1, cy1 = (b1[0] + b1[2]) * 0.5, (b1[1] + b1[3]) * 0.5
                best_j = 0
                best_d = 1e18
                for j, b2 in enumerate(boxes_p2):
                    if j in used_b2:
                        continue
                    cx2, cy2 = (b2[0] + b2[2]) * 0.5, (b2[1] + b2[3]) * 0.5
                    d = (cx1 - cx2) ** 2 + (cy1 - cy2) ** 2
                    if d < best_d:
                        best_d = d
                        best_j = j
                used_b2.add(best_j)
                matched_b2.append(boxes_p2[best_j])
            boxes_p2 = matched_b2

        for idx_c, (b1, b2) in enumerate(zip(boxes_p1, boxes_p2), 1):
            c_front = p1_hi.crop((int(b1[0] * sx), int(b1[1] * sy), int(b1[2] * sx), int(b1[3] * sy)))
            c_back = p2_hi.crop((int(b2[0] * sx), int(b2[1] * sy), int(b2[2] * sx), int(b2[3] * sy)))

            out_pdf = batch_folder / f"{pdf_p.stem}_FBCard{idx_c:02d}.pdf"
            new_doc = fitz.open()
            for side_im in (c_front, c_back):
                buf = io.BytesIO()
                side_im.save(buf, format="JPEG", quality=95)
                img_bytes = buf.getvalue()
                w_pt = side_im.width * 72.0 / float(RUNTIME_CONFIG.get("scanner_dpi", 600))
                h_pt = side_im.height * 72.0 / float(RUNTIME_CONFIG.get("scanner_dpi", 600))
                page = new_doc.new_page(width=w_pt, height=h_pt)
                page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=img_bytes)
            new_doc.save(str(out_pdf))
            new_doc.close()
            created_count += 1

        arc_fb_dir = batch_folder / "Archive_Flatbed_Sheets"
        arc_fb_dir.mkdir(parents=True, exist_ok=True)
        try:
            pdf_p.replace(arc_fb_dir / pdf_p.name)
        except Exception:
            pass

    final_pdfs = sorted(batch_folder.glob("*.pdf"))
    return final_pdfs, created_count


# ==============================================================================
# 2. PHYSICAL CARD BOUNDARY DETECTOR & 8-CORNER INSPECTION SHEET BUILDER
# ==============================================================================
def detect_physical_card_box(img: Image.Image) -> tuple[int, int, int, int]:
    w, h = img.size
    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    scale = 800.0 / max(w, h)
    sw, sh = max(80, int(w * scale)), max(80, int(h * scale))
    s_gray = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)

    blur = cv2.GaussianBlur(s_gray, (5, 5), 0)
    edges = cv2.Canny(blur, 25, 95)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    dil = cv2.dilate(edges, kernel, iterations=2)

    cnts, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_box = (int(w * 0.04), int(h * 0.03), int(w * 0.96), int(h * 0.97))
    best_area = 0.0
    total_s_area = float(sw * sh)

    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        a = float(cw * ch)
        if 0.35 * total_s_area <= a <= 0.98 * total_s_area:
            if a > best_area:
                best_area = a
                best_box = (
                    max(0, int(x / scale)),
                    max(0, int(y / scale)),
                    min(w, int((x + cw) / scale)),
                    min(h, int((y + ch) / scale)),
                )

    return best_box


def build_corners_inspection_sheet(
    front_img: Image.Image,
    back_img: Image.Image,
    front_box: Optional[tuple[int, int, int, int]] = None,
    back_box: Optional[tuple[int, int, int, int]] = None,
    tile_size: int = 360,
) -> Image.Image:
    if front_box is None:
        front_box = detect_physical_card_box(front_img)
    if back_box is None:
        back_box = detect_physical_card_box(back_img)

    def _extract_four_corner_crops(im: Image.Image, box: tuple[int, int, int, int]) -> list[Image.Image]:
        w, h = im.size
        x1, y1, x2, y2 = box
        cw = max(100, x2 - x1)
        ch = max(100, y2 - y1)
        span = int(min(cw, ch) * 0.28)
        margin_out = int(span * 0.26)

        coords = [
            (max(0, x1 - margin_out), max(0, y1 - margin_out), min(w, x1 + span), min(h, y1 + span)),
            (max(0, x2 - span), max(0, y1 - margin_out), min(w, x2 + margin_out), min(h, y1 + span)),
            (max(0, x1 - margin_out), max(0, y2 - span), min(w, x1 + span), min(h, y2 + margin_out)),
            (max(0, x2 - span), max(0, y2 - span), min(w, x2 + margin_out), min(h, y2 + margin_out)),
        ]
        tiles = []
        for cx1, cy1, cx2, cy2 in coords:
            crop = im.crop((cx1, cy1, max(cx1 + 20, cx2), max(cy1 + 20, cy2)))
            tiles.append(crop.resize((tile_size, tile_size), Image.Resampling.LANCZOS))
        return tiles

    f_tiles = _extract_four_corner_crops(front_img, front_box)
    b_tiles = _extract_four_corner_crops(back_img, back_box)

    pad = 14
    hdr_h = 28
    canvas_w = 4 * tile_size + 5 * pad
    canvas_h = 2 * (tile_size + hdr_h) + 3 * pad
    sheet = Image.new("RGB", (canvas_w, canvas_h), (18, 22, 29))
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    f_labels = ["FRONT - TOP LEFT", "FRONT - TOP RIGHT", "FRONT - BOTTOM LEFT", "FRONT - BOTTOM RIGHT"]
    b_labels = ["BACK - TOP LEFT", "BACK - TOP RIGHT", "BACK - BOTTOM LEFT", "BACK - BOTTOM RIGHT"]

    for col_i in range(4):
        x_pos = pad + col_i * (tile_size + pad)
        y1_lbl = pad
        draw.text((x_pos + 4, y1_lbl + 4), f_labels[col_i], fill=(175, 190, 210), font=font)
        sheet.paste(f_tiles[col_i], (x_pos, y1_lbl + hdr_h))

        y2_lbl = pad * 2 + tile_size + hdr_h
        draw.text((x_pos + 4, y2_lbl + 4), b_labels[col_i], fill=(175, 190, 210), font=font)
        sheet.paste(b_tiles[col_i], (x_pos, y2_lbl + hdr_h))

    return sheet


# ==============================================================================
# 3. 4-ANGLE HORIZONTAL-AWARE BACK OCR & CARD IDENTITY MATCHER
# ==============================================================================
_FOOTER_ANCHOR_TOKENS = (
    "THETOPPSCOMPANY",
    "TOPPSCOMPANY",
    "BOWMAN",
    "PANINIAMERICA",
    "UPPERDECK",
    "MAJORLEAGUEBASEBALL",
    "OFFICIALLYLICENSED",
    "PRINTEDIN",
    "MLBPA",
    "MLBP",
    "CMP",
    "ALLRIGHTSRESERVED",
    "TRADEMARKS",
)

_HEADER_ANCHOR_TOKENS = (
    "SERIESONE",
    "SERIESTWO",
    "UPDATESERIES",
    "MAJORLEAGUEBATTING",
    "MAJORLEAGUEPITCHING",
    "BATTINGRECORD",
    "PITCHINGRECORD",
    "BORN",
    "BATS",
    "THROWS",
    "DRAFTED",
    "ACQUIRED",
    "WORLDSCHAMPIONS",
    "COMMEMORATING",
)


def _score_upright_ocr_orientation(items: list[dict]) -> float:
    """
    Scores how strongly a rotated image is in its true upright reading orientation:
      - Rewards crisp horizontal text boxes (`bw > bh * 1.15`) weighted by confidence & word count.
      - Penalizes sideways vertical text boxes (`bh > bw * 1.15`) so landscape card backs
        rotate cleanly to horizontal instead of staying sideways.
      - Uses positional anchors (copyright/legal footer in bottom 35% vs top 35%,
        series/bio/stats header in top 52% vs bottom 25%) to separate 0°/180° and 90°/270° decisively!
    """
    if not items:
        return -50.0

    score = 0.0
    horiz_cnt = 0
    vert_cnt = 0
    footer_bottom_hit = False
    footer_top_hit = False
    header_top_hit = False
    header_bottom_hit = False

    for it in items:
        txt = it["text"]
        conf = float(it["conf"])
        bw = float(it["bw"])
        bh = float(it["bh"])
        cy = float(it["cy"])
        n_txt = norm(txt)
        alpha_words = len(re.findall(r"[A-Za-z]{3,}", txt))

        if bw >= bh * 1.15:
            horiz_cnt += 1
            score += conf * (3.5 + min(len(txt), 22) * 0.45 + alpha_words * 2.2)
        elif bh >= bw * 1.15 and len(txt) >= 3:
            vert_cnt += 1
            score -= conf * (6.5 + min(len(txt), 16) * 0.35)
        else:
            score += conf * 1.0

        if any(tok in n_txt for tok in _FOOTER_ANCHOR_TOKENS):
            if cy >= 0.62:
                footer_bottom_hit = True
            elif cy <= 0.38:
                footer_top_hit = True

        if any(tok in n_txt for tok in _HEADER_ANCHOR_TOKENS):
            if cy <= 0.55:
                header_top_hit = True
            elif cy >= 0.72:
                header_bottom_hit = True

    if footer_bottom_hit:
        score += 75.0
    if footer_top_hit and not footer_bottom_hit:
        score -= 60.0
    if header_top_hit:
        score += 40.0
    if header_bottom_hit and not header_top_hit:
        score -= 30.0
    if horiz_cnt >= 3 and horiz_cnt > vert_cnt * 2:
        score += 25.0

    return round(score, 2)


def extract_back_ocr_and_orient(
    back_img: Image.Image,
    preferred_angle: Optional[int] = None,
    force_all_angles: bool = False,
) -> tuple[Image.Image, dict]:
    """
    Fast Early-Exit 4-Angle Geometry-Aware Card Back Orientation & OCR Extractor:
    Tests `preferred_angle` first and early-exits on a decisive upright lock (`score >= 110`)
    unless `force_all_angles=True` (used by the Rotation Fixer to evaluate all 4 angles cleanly).
    """
    early_exit_thresh = float(RUNTIME_CONFIG.get("back_ocr_early_exit_score", 110.0))
    angle_order = [0, 90, 270, 180]
    if preferred_angle in (0, 90, 180, 270):
        angle_order = [int(preferred_angle)] + [a for a in angle_order if a != int(preferred_angle)]

    best_angle = angle_order[0]
    best_text_img = back_img
    best_text_lines: list[str] = []
    best_text_score = -1e9
    score_0: Optional[float] = None
    ricoh_0deg_lines: list[str] = []

    for idx_a, angle in enumerate(angle_order):
        rot_im = back_img if angle == 0 else back_img.rotate(angle, expand=True)
        w, h = rot_im.size
        scale = min(1.0, 1150.0 / max(w, h))
        small_im = rot_im.resize((max(80, int(w * scale)), max(80, int(h * scale))), Image.Resampling.BILINEAR)
        items = _run_rapidocr_detailed(np.array(small_im))
        lines = [it["text"] for it in items]
        readability_score = _score_upright_ocr_orientation(items)

        if angle == 0:
            ricoh_0deg_lines = lines
            score_0 = readability_score

        if readability_score > best_text_score:
            best_text_score = readability_score
            best_angle = angle
            best_text_img = rot_im
            best_text_lines = lines

        # Fast early-exit on clear upright reading orientation (skipped when force_all_angles=True)
        if not force_all_angles and readability_score >= early_exit_thresh and len(lines) >= 4:
            break

    tw, th = best_text_img.size
    hdr_crop = best_text_img.crop((int(tw * 0.02), int(th * 0.02), int(tw * 0.98), int(th * 0.32)))
    hdr_np = np.array(hdr_crop)
    hdr_norm = _run_rapidocr_lines(hdr_np)
    hdr_inv = _run_rapidocr_lines(255 - hdr_np)

    tr_crop = best_text_img.crop((int(tw * 0.62), int(th * 0.02), int(tw * 0.98), int(th * 0.28)))
    tl_crop = best_text_img.crop((int(tw * 0.02), int(th * 0.02), int(tw * 0.38), int(th * 0.28)))
    corner_lines = _run_rapidocr_lines(np.array(tl_crop)) + _run_rapidocr_lines(np.array(tr_crop))

    ftr_crop = best_text_img.crop((int(tw * 0.05), int(th * 0.76), int(tw * 0.95), int(th * 0.98)))
    ftr_lines = _run_rapidocr_lines(np.array(ftr_crop))

    # Return the truly upright back image (landscape when back is landscape, portrait when portrait!)
    return best_text_img, {
        "full_lines": hdr_norm + best_text_lines + ftr_lines,
        "header_norm": hdr_norm,
        "header_inv": hdr_inv,
        "corner_zoom": corner_lines,
        "ricoh_0deg": ricoh_0deg_lines,
        "back_rotation_angle": best_angle,
        "back_score_0": score_0,
        "back_best_score": best_text_score,
        "back_is_landscape": bool(best_text_img.width > best_text_img.height),
    }


def _find_exact_front_reference_path(
    set_name: str,
    subset_name: str,
    card_number: str,
    template_catalog: dict,
    reviewed_by_card: dict,
    exclude_paths: Optional[set[str]] = None,
) -> Optional[Path]:
    """
    Locates an upright `_F.jpg` reference template for orientation alignment:
      1. Exact `(Set, Subset, Card #)` in `Reference_Library`
      2. Base `(Set, Base, Card #)` in `Reference_Library` (same layout/orientation for parallels!)
      3. Direct disk lookup via `resolve_template_reference_paths()`
      4. Other confirmed `_My_Collection` copies (strictly excluding `exclude_paths` so a card
         never compares against itself!)
    """
    if not set_name or not card_number or str(card_number) == "0":
        return None

    excl_norm: set[str] = set()
    for ep in (exclude_paths or set()):
        try:
            excl_norm.add(str(Path(ep).resolve()).lower())
        except Exception:
            excl_norm.add(str(ep).lower())

    def _is_allowed(p_obj: Path) -> bool:
        if not p_obj.exists():
            return False
        if not excl_norm:
            return True
        try:
            return str(p_obj.resolve()).lower() not in excl_norm
        except Exception:
            return str(p_obj).lower() not in excl_norm

    s_key = canonical_set_key(set_name)
    sub_canon = canonical_subset_key(subset_name or "Base", set_name)
    n_cn = norm(str(card_number).lstrip("#"))

    set_tmpls = template_catalog.get(s_key, {}) if isinstance(template_catalog, dict) else {}
    # 1. Exact subset in Reference_Library
    for t_sub, t_bkt in set_tmpls.items():
        if isinstance(t_bkt, dict) and canonical_subset_key(t_sub, set_name) == sub_canon:
            c_list = (t_bkt.get("cards") or {}).get(n_cn, [])
            if c_list and c_list[0].get("front_path"):
                cand = Path(c_list[0]["front_path"])
                if _is_allowed(cand):
                    return cand

    # 2. Base card in Reference_Library (parallels share the exact same portrait/landscape orientation)
    if sub_canon != "BASE":
        for t_sub, t_bkt in set_tmpls.items():
            if isinstance(t_bkt, dict) and canonical_subset_key(t_sub, set_name) == "BASE":
                c_list = (t_bkt.get("cards") or {}).get(n_cn, [])
                if c_list and c_list[0].get("front_path"):
                    cand = Path(c_list[0]["front_path"])
                    if _is_allowed(cand):
                        return cand

    # 3. Direct disk lookup in Reference_Library (handles templates downloaded after cache build)
    try:
        from Core.database import resolve_template_reference_paths
        disk_ref = resolve_template_reference_paths(set_name, subset_name or "Base", card_number)
        if disk_ref.get("front_abs"):
            cand = Path(disk_ref["front_abs"])
            if _is_allowed(cand):
                return cand
    except Exception:
        pass

    # 4. Other confirmed _My_Collection scans (excluding the card itself!)
    for r_item in (reviewed_by_card.get((s_key, n_cn), []) if isinstance(reviewed_by_card, dict) else []):
        if len(r_item) >= 4 and r_item[3]:
            cand = Path(r_item[3])
            if _is_allowed(cand):
                return cand
    return None


def orient_front_card_image(
    front_img: Image.Image,
    back_rotation_angle: int = 0,
    set_name: str = "",
    subset_name: str = "Base",
    card_number: str = "",
    template_catalog: Optional[dict] = None,
    reviewed_by_card: Optional[dict] = None,
    exclude_paths: Optional[set[str]] = None,
) -> tuple[Image.Image, int, str]:
    """
    Restores automatic upright orientation for Card Fronts (both horizontal/landscape cards
    and upside-down vertical scans):
      1. If an upright reference front image exists in `Reference_Library` (or another confirmed
         `_My_Collection` scan, excluding `exclude_paths`), matches its aspect ratio and picks
         the highest-similarity upright angle (requiring >= +0.035 margin for 180° flips).
      2. If no reference image exists yet, inspects Front OCR bounding-box geometry across
         0° / 90° / 270° / 180° to detect sideways horizontal cards and upside-down scans.
    Returns `(oriented_front_img, rotation_angle_applied, reason)`.
    """
    # 1. Reference-Guided Orientation
    ref_p = (
        _find_exact_front_reference_path(
            set_name,
            subset_name,
            card_number,
            template_catalog,
            reviewed_by_card,
            exclude_paths=exclude_paths,
        )
        if (template_catalog is not None and reviewed_by_card is not None)
        else None
    )
    if ref_p is not None and ref_p.exists():
        try:
            with Image.open(ref_p) as ref_im:
                ref_rgb = np.array(ref_im.convert("RGB"))
            ref_h, ref_w = ref_rgb.shape[:2]
            ref_is_landscape = ref_w > ref_h * 1.10
            scan_is_landscape = front_img.width > front_img.height * 1.10

            same_aspect = (ref_is_landscape == scan_is_landscape)
            cand_angles = (0, 180) if same_aspect else (90, 270)
            sim_by_ang: dict[int, float] = {}
            for ang in cand_angles:
                rot_f = front_img if ang == 0 else front_img.rotate(ang, expand=True)
                fb = detect_physical_card_box(rot_f)
                fcrop = np.array(rot_f.crop((fb[0], fb[1], max(fb[0] + 20, fb[2]), max(fb[1] + 20, fb[3]))))
                sim_by_ang[ang] = _compute_single_side_whole_image_similarity(fcrop, ref_rgb)

            if same_aspect:
                s0 = sim_by_ang.get(0, 0.0)
                s180 = sim_by_ang.get(180, 0.0)
                if s180 >= s0 + 0.035:
                    reason = f"RefGuided({'Landscape' if ref_is_landscape else 'Portrait'} 180deg, {s180:.2f} vs {s0:.2f})"
                    return front_img.rotate(180, expand=True), 180, reason
                return front_img, 0, f"RefAligned(0deg, sim={s0:.2f})"
            else:
                best_ang = 90 if sim_by_ang.get(90, 0.0) >= sim_by_ang.get(270, 0.0) else 270
                best_sim = sim_by_ang[best_ang]
                reason = f"RefGuided({'Landscape' if ref_is_landscape else 'Portrait'} {best_ang}deg, sim={best_sim:.2f})"
                return front_img.rotate(best_ang, expand=True), best_ang, reason
        except Exception:
            pass

    # 2. Standalone OCR Geometry Fallback (When no reference template exists yet)
    try:
        fw, fh = front_img.size
        f_scale = min(1.0, 900.0 / max(fw, fh))
        small_0 = front_img.resize((max(80, int(fw * f_scale)), max(80, int(fh * f_scale))), Image.Resampling.BILINEAR)
        items_0 = _run_rapidocr_detailed(np.array(small_0))
        sc_0 = _score_upright_ocr_orientation(items_0)

        horiz_0 = sum(1 for it in items_0 if it["bw"] >= it["bh"] * 1.15 and len(it["text"]) >= 3)
        vert_0 = sum(1 for it in items_0 if it["bh"] >= it["bw"] * 1.15 and len(it["text"]) >= 3)

        # Horizontal card fed vertically (predominantly vertical text at 0°)
        if vert_0 >= 2 and vert_0 > horiz_0:
            best_ang = 0
            best_sc = sc_0
            for ang in (90, 270):
                rot_f = front_img.rotate(ang, expand=True)
                rw, rh = rot_f.size
                r_sc = min(1.0, 900.0 / max(rw, rh))
                s_rot = rot_f.resize((max(80, int(rw * r_sc)), max(80, int(rh * r_sc))), Image.Resampling.BILINEAR)
                sc_rot = _score_upright_ocr_orientation(_run_rapidocr_detailed(np.array(s_rot)))
                if sc_rot > best_sc + 18.0:
                    best_sc = sc_rot
                    best_ang = ang
            if best_ang in (90, 270):
                return front_img.rotate(best_ang, expand=True), best_ang, f"FrontOCR_Landscape({best_ang}deg)"

        # Check 180° flip when back was inverted OR 0° has weak/upside-down front OCR
        if back_rotation_angle == 180 or horiz_0 == 0:
            rot_180 = front_img.rotate(180, expand=True)
            s_180 = rot_180.resize((max(80, int(fw * f_scale)), max(80, int(fh * f_scale))), Image.Resampling.BILINEAR)
            sc_180 = _score_upright_ocr_orientation(_run_rapidocr_detailed(np.array(s_180)))
            req_gain = -5.0 if back_rotation_angle == 180 else 20.0
            if sc_180 >= sc_0 + req_gain:
                return rot_180, 180, "BackInvertedFlip(180deg)" if back_rotation_angle == 180 else "FrontOCR_Flip(180deg)"
    except Exception:
        pass

    return front_img, 0, "Default(0deg)"


_COMMON_PRINT_RUN_DENOMS = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 35, 40, 45, 49, 50, 55, 60, 65, 70, 75, 76, 80, 85, 90, 99,
    100, 125, 149, 150, 175, 199, 200, 225, 249, 250, 275, 299, 300, 350, 399, 400, 499, 500, 599, 600, 750, 799,
    999, 1000, 1999, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027,
}


def _parse_serial_denominator_from_lines(lines: list[str]) -> Optional[str]:
    joined = " ".join(str(x or "") for x in (lines or []))
    if not joined:
        return None
    # Strip explicit full dates like 04/12/2026 or 11/18/99 so birthdates/stat dates are never mistaken for SNs
    cleaned = re.sub(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\b", " ", joined)
    for m in re.finditer(r"\b(\d{1,4})\s*/\s*(\d{1,4})\b", cleaned):
        raw_num, raw_den = m.group(1), m.group(2)
        num, den = int(raw_num), int(raw_den)
        if not (1 <= num <= den <= 2050):
            continue
        # Reject baseball milestone ratios like 20/20, 30/30, 40/40, 50/50 unless zero-padded or 1/1
        if num == den and den in (10, 15, 20, 25, 30, 40, 50) and not raw_num.startswith("0"):
            ctx_around = cleaned[max(0, m.start() - 18) : min(len(cleaned), m.end() + 18)].upper()
            if any(k in ctx_around for k in ("CLUB", "SEASON", "HR", "SB", "STEAL", "HOMER", "GAME", "AVG", "RBI")):
                continue
        # Reject month/day pairs (e.g. 5/14) unless denominator is a known hobby print run and numerator is zero-padded or >= 13
        if 1 <= num <= 12 and 1 <= den <= 31 and len(raw_num) == 1 and den not in (1, 5, 10, 15, 25):
            continue
        # Allow Gold year-numbered stamps (e.g. 0412/2026, 1845/2026) while rejecting 4/2026 date fragments
        if den in (2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
            if len(raw_num) >= 3 or (len(raw_num) == 4 and raw_num.startswith("0")):
                return str(den)
            continue
        if den in _COMMON_PRINT_RUN_DENOMS or (len(raw_num) == len(raw_den) and raw_num.startswith("0")):
            return str(den)
    return None


def extract_stamped_serial_print_run(
    front_img: Image.Image,
    back_ocr_lines: list[str],
    front_ocr_lines: Optional[list[str]] = None,
    scan_front_for_stamp: bool = False,
) -> Optional[str]:
    """
    Detects foil-stamped serial numbers (e.g. 0412/2026, 017/099, 12/50, 1/1) from Back OCR,
    any already-extracted Front OCR, and (when `scan_front_for_stamp=True` on serial-numbered parallel
    candidates) targeted Front top/bottom foil-stamp zones.
    """
    back_hit = _parse_serial_denominator_from_lines(back_ocr_lines or [])
    if back_hit:
        return back_hit
    if front_ocr_lines:
        f_hit = _parse_serial_denominator_from_lines(front_ocr_lines)
        if f_hit:
            return f_hit
    if scan_front_for_stamp and front_img is not None:
        try:
            fw, fh = front_img.size
            scale = min(1.0, 1100.0 / max(fw, fh))
            f_sm = front_img.resize((max(80, int(fw * scale)), max(80, int(fh * scale))), Image.Resampling.BILINEAR)
            f_np = np.array(f_sm)
            sh, sw = f_np.shape[:2]
            stamp_lines = []
            for band in (f_np[: int(sh * 0.25), :], f_np[int(sh * 0.72) :, :]):
                if band.size == 0:
                    continue
                stamp_lines.extend(_run_rapidocr_lines(band))
                stamp_lines.extend(_run_rapidocr_lines(255 - band))
            return _parse_serial_denominator_from_lines(stamp_lines)
        except Exception:
            pass
    return None


# ==============================================================================
# AUTO-LEARNING CMP FOOTER CODE REGISTRY (Cache/Library/cmp_code_map.json)
# ==============================================================================
_CMP_MAP_FILE = FEATURE_CACHE_FILE.parent / "cmp_code_map.json"
_CMP_MAP_CACHE: Optional[dict[str, dict[str, str]]] = None


def _extract_cmp_code_from_blob(full_blob: str) -> str:
    m = re.search(r"\b(CMP\d{5,8})\b", str(full_blob or "").upper())
    return m.group(1) if m else ""


def _load_learned_cmp_map() -> dict[str, dict[str, str]]:
    global _CMP_MAP_CACHE
    if _CMP_MAP_CACHE is not None:
        return _CMP_MAP_CACHE
    loaded: dict[str, dict[str, str]] = {}
    for code_k, (s_n, sub_n) in CMP_SUBSET_HINTS.items():
        loaded[code_k.upper()] = {"set": s_n, "subset": sub_n}
    if _CMP_MAP_FILE.exists():
        try:
            raw = json.loads(_CMP_MAP_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                loaded.update(raw)
        except Exception:
            pass
    _CMP_MAP_CACHE = loaded
    return _CMP_MAP_CACHE


def _record_learned_cmp_code(cmp_code: str, set_name: str, subset_name: str):
    code = str(cmp_code or "").strip().upper()
    if not code or not set_name or not subset_name:
        return
    m = _load_learned_cmp_map()
    if code in m:
        return
    m[code] = {"set": set_name, "subset": subset_name}
    try:
        _CMP_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CMP_MAP_FILE.write_text(json.dumps(m, indent=2), encoding="utf-8")
    except Exception:
        pass


def is_base_family_root(subset_name: str, set_name: str = "") -> bool:
    s = str(subset_name or "Base").strip().upper()
    return s in ("", "BASE", "BASE SET") or s.startswith("BASE ")


def _dynamic_filter_candidate_sets(
    full_blob: str,
    root_df: pd.DataFrame,
) -> tuple[pd.DataFrame, Optional[str], Optional[str]]:
    if root_df is None or root_df.empty:
        return root_df, None, None

    cmp_set = None
    cmp_subset = None
    for cmp_code, (s_name, sub_name) in CMP_SUBSET_HINTS.items():
        if cmp_code in full_blob:
            cmp_set = s_name
            cmp_subset = sub_name
            break

    if cmp_set:
        sub_df = root_df[root_df["Set"] == cmp_set]
        if not sub_df.empty:
            return sub_df, cmp_set, cmp_subset

    cand = root_df
    if "ALLENGINTER" in full_blob or "ALLENANDGINTER" in full_blob:
        ag_df = cand[cand["Set"].str.contains("Allen", case=False, na=False)]
        if not ag_df.empty:
            cand = ag_df
    elif "STADIUMCLUB" in full_blob:
        sc_df = cand[cand["Set"].str.contains("Stadium Club", case=False, na=False)]
        if not sc_df.empty:
            cand = sc_df
    elif "BOWMAN" in full_blob:
        bw_df = cand[cand["Set"].str.contains("Bowman", case=False, na=False)]
        if not bw_df.empty:
            cand = bw_df
    else:
        non_ag = cand[~cand["Set"].str.contains("Allen", case=False, na=False)]
        if not non_ag.empty and ("SERIESONE" in full_blob or "SERIESTWO" in full_blob):
            cand = non_ag

    return cand, cmp_set, cmp_subset


def _score_candidates(
    cand_df: pd.DataFrame,
    cnum_candidates: set[str],
    series_badge_cnums: set[str],
    header_corner_cnums: set[str],
    header_blob: str,
    full_blob: str,
    cmp_hint_subset: Optional[str],
    is_series_one: bool,
    is_series_two: bool,
    is_leaders_card: bool = False,
):
    best_row = None
    best_score = -1
    best_reasons = []

    has_strong_cnum_signal = bool(series_badge_cnums or header_corner_cnums)
    has_asr_ocr = "ALLSTARROOKIE" in full_blob or "ALLSTARROOKIES" in full_blob
    has_fs_ocr = "FUTURESTARS" in full_blob or "FUTURESTAR" in full_blob

    for _, row in cand_df.iterrows():
        score = 0
        reasons = []
        cnum = row["norm_cnum"]
        pname = row["norm_player"]
        tname = row["norm_team"]
        row_tags = row.get("attr_tags") or ()
        is_ll_tag = "LL" in row_tags or "LEADERS" in pname
        is_cpc_tag = "CPC" in row_tags
        is_tc_tag = "TC" in row_tags or (pname == tname) or pname.startswith("CHECKLISTTEAMCARD")
        is_multi = bool(row.get("is_multi_player", "/" in str(row.get("Player", ""))))

        if not cnum or cnum == "0":
            continue

        cnum_matched = False
        if cnum in cnum_candidates:
            cnum_matched = True
            if "-" in str(row["Card Number"]):
                score += 80
                reasons.append(f"Insert#({row['Card Number']})")
            else:
                score += 58
                reasons.append(f"Card#({row['Card Number']})")
            if cnum in series_badge_cnums:
                score += 48
                reasons.append(f"SeriesBadge#({row['Card Number']})")
            elif cnum in header_corner_cnums:
                score += 24
                reasons.append(f"HeaderCorner#({row['Card Number']})")

        if is_multi or is_ll_tag or is_cpc_tag:
            p_parts = row.get("norm_player_parts") or ()
            p_lasts = row.get("norm_player_lasts") or ()
            if 2 <= len(p_parts) <= 4:
                full_matches = sum(1 for pt in p_parts if len(pt) >= 5 and pt in full_blob)
                hdr_matches = sum(1 for lt in p_lasts if len(lt) >= 4 and lt in header_blob)

                if full_matches == len(p_parts):
                    score += 95
                    reasons.append(f"AllFeaturedPlayers({len(p_parts)})")
                elif full_matches >= 2:
                    score += 78
                    reasons.append(f"MultiPlayers({full_matches}/{len(p_parts)})")
                elif hdr_matches >= 2:
                    score += 72
                    reasons.append(f"MultiHeader({hdr_matches})")
                elif full_matches == 1 and (hdr_matches >= 1 or cnum_matched):
                    score += 48
                    reasons.append("PartialMulti")

                if is_leaders_card and is_ll_tag and (full_matches >= 2 or hdr_matches >= 2):
                    score += 45
                    reasons.append("LL_TagPlayersLock")

        if is_ll_tag:
            stat_core = re.sub(r"^(19|20)\d{2}(AL|NL|MLB)?|^(AMERICAN|NATIONAL)LEAGUE", "", pname)
            if pname in header_blob or pname in full_blob:
                score += 90
                reasons.append(f"LeadersTitle({row['Player']})")
            elif len(stat_core) >= 6 and (stat_core in header_blob or stat_core in full_blob):
                score += 70
                reasons.append(f"LeadersStat({row['Player']})")
            if is_leaders_card and cnum_matched:
                score += 38
                reasons.append("LL_Card#Match")
        elif is_cpc_tag:
            if len(pname) >= 4 and (pname in header_blob or pname in full_blob):
                score += 85
                reasons.append(f"ComboTitle({row['Player']})")
        elif not is_tc_tag and not is_multi:
            matched_single_player = False
            if len(pname) >= 4 and pname in header_blob:
                score += 72
                matched_single_player = True
                reasons.append(f"HeaderPlayer({row['Player']})")
            elif len(pname) >= 5 and pname in full_blob:
                matched_single_player = True
                if (has_strong_cnum_signal and not cnum_matched) or is_leaders_card:
                    score += 15
                    reasons.append(f"BioMention({row['Player']})")
                else:
                    score += 42
                    reasons.append(f"BodyPlayer({row['Player']})")
            elif cnum_matched:
                # Penalize stray card-number / stat-line hits that have zero player name evidence
                score -= 20
                reasons.append("NoPlayerPenalty")

            if is_leaders_card and cnum not in series_badge_cnums:
                score -= 60
                reasons.append("LeadersSinglePenalty")
        elif is_tc_tag:
            if pname in header_blob or (len(tname) >= 5 and tname in header_blob):
                score += 65
                reasons.append(f"TeamHeader({row['Team']})")
            elif cnum_matched and len(tname) >= 5 and tname in full_blob:
                score += 38
                reasons.append(f"TeamCard({row['Team']})")

        if has_asr_ocr and "ASR" in row_tags:
            score += 22
            reasons.append("Tag(ASR)")
        if has_fs_ocr and "FS" in row_tags:
            score += 22
            reasons.append("Tag(FS)")

        if len(tname) >= 5 and (tname in header_blob or tname in full_blob):
            score += 15
            reasons.append("Team")

        if cmp_hint_subset and row["Subset"] == cmp_hint_subset:
            score += 15
            reasons.append(f"CMP({cmp_hint_subset})")

        sub_up_sc = str(row["Subset"] or "Base").strip().upper()
        cnum_raw_sc = str(row["Card Number"] or "").strip()
        is_base_root_sc = is_base_family_root(row["Subset"], row["Set"])

        if is_base_root_sc and cnum_raw_sc.isdigit():
            score += 10
            num_val = int(cnum_raw_sc)
            if is_series_one and 1 <= num_val <= 350:
                score += 10
            elif is_series_two and 351 <= num_val <= 700:
                score += 10

        # Prevent OCR alone from picking Golden Mirror / Variations / Relics over Base without visual proof
        if "GOLDEN MIRROR" in sub_up_sc or ("VARIATION" in sub_up_sc and "-" not in cnum_raw_sc):
            score -= 32
        elif _is_relic_or_auto_subset(row["Subset"]) and "-" not in cnum_raw_sc:
            if not _back_ocr_has_relic_or_auto_text(full_blob):
                score -= 40

        if score > best_score:
            best_score = score
            best_row = row
            best_reasons = reasons

    return best_row, best_score, best_reasons


def _extract_cnum_tokens_from_line(raw_line: str) -> tuple[set[str], set[str]]:
    cnums: set[str] = set()
    badge_cnums: set[str] = set()
    clean = strip_accents(str(raw_line or "")).strip().upper()
    if not clean:
        return cnums, badge_cnums

    n_full = norm(clean)
    if 1 <= len(n_full) <= 8:
        cnums.add(n_full)

    for m_ser in re.finditer(
        r"(?:^|\b)#?([A-Z]{0,4}-?\d{1,4}[A-Z]?)\s*(?:SERIES\s*ONE|SERIES\s*TWO|UPDATE\s*SERIES)",
        clean,
    ):
        tok = norm(m_ser.group(1))
        if tok:
            cnums.add(tok)
            badge_cnums.add(tok)

    for m_ins in re.finditer(r"\b([A-Z0-9]{1,5}-\d{1,4}[A-Z]?)\b", clean):
        tok = norm(m_ins.group(1))
        if tok and not re.match(r"^(19|20)\d{2}", tok):
            cnums.add(tok)
            badge_cnums.add(tok)

    tokens = [t.strip("#.,:;()[]") for t in clean.split() if t.strip("#.,:;()[]")]
    for pos_i, tok in enumerate(tokens):
        if pos_i not in (0, len(tokens) - 1) and len(tokens) > 2:
            continue
        if re.match(r"^\d{1,4}[A-Z]?$", tok):
            if re.match(r"^(19[5-9]\d|20[0-2]\d)$", tok):
                continue
            cnums.add(norm(tok))

    return cnums, badge_cnums


def match_card_identity(ocr_bundle: dict, root_df: pd.DataFrame):
    full_lines = ocr_bundle["full_lines"]
    top_norm = ocr_bundle["header_norm"]
    top_inv = ocr_bundle["header_inv"]
    corner_zoom = ocr_bundle["corner_zoom"]
    ricoh_lines = ocr_bundle.get("ricoh_0deg", [])

    header_lines = top_norm[:10] + top_inv[:10] + corner_zoom + full_lines[:10] + ricoh_lines[:8]
    cnum_candidates = set()
    series_badge_cnums = set()
    header_corner_cnums = set()

    for src_idx, src in enumerate([corner_zoom, top_norm[:10], top_inv[:10], full_lines[:12], ricoh_lines[:8]]):
        is_hdr_or_corner = src_idx in (0, 1, 2)
        for i, line in enumerate(src):
            n_line = norm(line)
            if n_line:
                cnum_candidates.add(n_line)
            line_cnums, line_badges = _extract_cnum_tokens_from_line(line)
            cnum_candidates.update(line_cnums)
            series_badge_cnums.update(line_badges)
            if is_hdr_or_corner:
                header_corner_cnums.update(line_cnums)

            if i < len(src) - 1:
                next_line = src[i + 1]
                n_next = norm(next_line)
                combined_pair = n_line + n_next
                cnum_candidates.add(combined_pair)
                if any(s_tag in n_next for s_tag in ("SERIESONE", "SERIESTWO", "UPDATESERIES")):
                    if n_line and len(n_line) <= 6:
                        series_badge_cnums.add(n_line)
                        cnum_candidates.add(n_line)
                    for tc in line_cnums:
                        series_badge_cnums.add(tc)
                if any(s_tag in n_line for s_tag in ("SERIESONE", "SERIESTWO", "UPDATESERIES")):
                    next_cnums, _ = _extract_cnum_tokens_from_line(next_line)
                    for tc in next_cnums:
                        series_badge_cnums.add(tc)
                        cnum_candidates.add(tc)

            m_inline_ser = re.search(r"^([A-Z0-9\-]{1,6})(?:SERIESONE|SERIESTWO|UPDATESERIES)", n_line)
            if m_inline_ser:
                cnum_candidates.add(m_inline_ser.group(1))
                series_badge_cnums.add(m_inline_ser.group(1))

    header_blob = norm(" ".join(header_lines))
    full_blob = norm(" ".join(full_lines + ricoh_lines))

    is_series_one = "SERIESONE" in full_blob
    is_series_two = "SERIESTWO" in full_blob or "ERIESTWO" in full_blob
    is_leaders_card = (
        "LEAGUELEADERS" in full_blob
        or "LEADERS" in header_blob
        or any(
            k in full_blob
            for k in (
                "RUNSBATTEDINLEADERS",
                "HOMERUNLEADERS",
                "BATTINGAVERAGELEADERS",
                "EARNEDRUNAVERAGELEADERS",
                "STRIKEOUTLEADERS",
                "WINSLEADERS",
                "STOLENBASELEADERS",
                "SAVESLEADERS",
                "HITSLEADERS",
            )
        )
    )

    cand_df, _, cmp_hint_subset = _dynamic_filter_candidate_sets(full_blob, root_df)

    best_row, best_score, best_reasons = _score_candidates(
        cand_df,
        cnum_candidates,
        series_badge_cnums,
        header_corner_cnums,
        header_blob,
        full_blob,
        cmp_hint_subset,
        is_series_one,
        is_series_two,
        is_leaders_card=is_leaders_card,
    )

    if best_score < 60 and len(cand_df) < len(root_df):
        fb_row, fb_score, fb_reasons = _score_candidates(
            root_df,
            cnum_candidates,
            series_badge_cnums,
            header_corner_cnums,
            header_blob,
            full_blob,
            cmp_hint_subset,
            is_series_one,
            is_series_two,
            is_leaders_card=is_leaders_card,
        )
        if fb_score > best_score:
            best_row, best_score, best_reasons = fb_row, fb_score, fb_reasons

    return best_row, best_score, "+".join(best_reasons)


def get_top_card_identity_candidates(
    ocr_bundle: dict,
    root_df: pd.DataFrame,
    top_k: int = 3,
) -> list[tuple[pd.Series, int, str]]:
    """Step 1 OCR Narrowing: Returns up to `top_k` candidate `(checklist_row, ocr_score, ocr_reasons)` matches."""
    primary_row, primary_score, primary_reasons = match_card_identity(ocr_bundle, root_df)
    if primary_row is None or root_df is None or root_df.empty:
        return []

    results: list[tuple[pd.Series, int, str]] = [(primary_row, primary_score, primary_reasons)]
    if top_k <= 1:
        return results

    full_lines = ocr_bundle.get("full_lines", [])
    top_norm = ocr_bundle.get("header_norm", [])
    top_inv = ocr_bundle.get("header_inv", [])
    corner_zoom = ocr_bundle.get("corner_zoom", [])
    ricoh_lines = ocr_bundle.get("ricoh_0deg", [])

    header_lines = top_norm[:10] + top_inv[:10] + corner_zoom + full_lines[:10] + ricoh_lines[:8]
    cnum_candidates: set[str] = set()
    for src in (corner_zoom, top_norm[:10], top_inv[:10], full_lines[:12], ricoh_lines[:8]):
        for line in src:
            line_cnums, _ = _extract_cnum_tokens_from_line(line)
            cnum_candidates.update(line_cnums)

    full_blob = norm(" ".join(full_lines + ricoh_lines))
    header_blob = norm(" ".join(header_lines))
    cand_df, _, _ = _dynamic_filter_candidate_sets(full_blob, root_df)

    seen_keys = {(primary_row["Set"], primary_row["norm_cnum"], primary_row["norm_player"])}
    extra_scored: list[tuple[int, pd.Series, str]] = []

    for _, row in cand_df.iterrows():
        k = (row["Set"], row["norm_cnum"], row["norm_player"])
        if k in seen_keys:
            continue
        sc = 0
        rsn = []
        if row["norm_cnum"] in cnum_candidates:
            sc += 55
            rsn.append(f"AltCard#({row['Card Number']})")
        if len(row["norm_player"]) >= 4 and row["norm_player"] in header_blob:
            sc += 65
            rsn.append(f"AltHeaderPlayer({row['Player']})")
        elif len(row["norm_player"]) >= 5 and row["norm_player"] in full_blob:
            sc += 35
            rsn.append(f"AltBodyPlayer({row['Player']})")
        if sc >= 55:
            seen_keys.add(k)
            extra_scored.append((sc, row, "+".join(rsn)))

    extra_scored.sort(key=lambda x: x[0], reverse=True)
    for sc, row, rsn in extra_scored[: max(0, top_k - 1)]:
        results.append((row, sc, rsn))

    return results


# ==============================================================================
# 4. DUAL-SIDE (FRONT + BACK) WHOLE-IMAGE INDEX & 2-STAGE CONFIRMATION MATCHER
# ==============================================================================
_BACK_DIFFERENTIATED_KEYWORDS = (
    "AGBACK",
    "BROOKLYNBACK",
    "NONUMBER",
    "FLIPSTOCK",
    "REDINK",
    "BLUEINK",
    "GREENINK",
    "BLANKBACK",
)

_GOLDEN_MIRROR_KEYWORDS = ("GOLDEN MIRROR", "GOLDENMIRROR")
_VARIATION_OR_ERROR_KEYWORDS = (
    "IMAGE VARIATION", "PHOTO VARIATION", "DESIGN VARIATION", "ACTION VARIATION",
    "VARIATION", "SHORT PRINT", "SUPER SHORT PRINT", "SSP", "ERROR", "UER", "COR",
)
_RELIC_OR_AUTO_KEYWORDS = (
    "RELIC", "MATERIAL", "JERSEY", "PATCH", "SWATCH", "BAT ", "MEMORABILIA",
    "AUTOGRAPH", "AUTO ", "AUTOS", "SIGNATURE", "SIGNED", "INK", "CUT SIG", "BOOKLET",
)
_RELIC_AUTO_BACK_OCR_TOKENS = (
    "GAMEUSED", "MEMORABILIA", "PLAYERWORN", "AUTHENTICRELIC", "RELIC",
    "AUTOGRAPH", "WITNESSED", "CONGRATULATIONS", "CERTIFIEDAUTOGRAPH", "SIGNING",
)


def _is_golden_mirror_subset(subset_name: str) -> bool:
    u = str(subset_name or "").upper()
    return any(k in u for k in _GOLDEN_MIRROR_KEYWORDS)


def _is_variation_or_error_subset(subset_name: str) -> bool:
    u = f" {str(subset_name or '').upper()} "
    if _is_golden_mirror_subset(u):
        return True
    return any(k in u for k in _VARIATION_OR_ERROR_KEYWORDS) or bool(re.search(r"\b(SP|SSP|VAR|ERR|UER|COR)\b", u))


def _is_relic_or_auto_subset(subset_name: str) -> bool:
    u = f" {str(subset_name or '').upper()} "
    return any(k in u for k in _RELIC_OR_AUTO_KEYWORDS)


def _back_ocr_has_relic_or_auto_text(full_blob_norm: str) -> bool:
    b = str(full_blob_norm or "").upper()
    return any(tok in b for tok in _RELIC_AUTO_BACK_OCR_TOKENS)


def _get_dynamic_front_back_weights(subset_name: str, set_name: str = "", card_attributes: str = "") -> tuple[float, float]:
    """
    Returns `(front_weight, back_weight)` tailored to the card type:
      - Back-differentiated cards (Golden Mirror, A&G Back, Brooklyn Back, Flip Stock, No Number,
        League Leaders `LL`, Combo Cards `CPC`, Relic/Auto certs): `0.40 Front / 0.60 Back`.
      - Image / Photo / Error / Walk This Way Variations: `0.94 Front / 0.06 Back`.
      - Standard Foil / Color Parallels (Gold, Rainbow Foil, Holo, Diamante, etc.): `0.88 Front / 0.12 Back`.
      - Standard Base cards: `0.78 Front / 0.22 Back`.
    """
    sub_canon = canonical_subset_key(subset_name or "Base", set_name)
    attrs_up = f" {str(card_attributes or '').upper()} "
    if (
        _is_golden_mirror_subset(subset_name)
        or any(bk in sub_canon for bk in _BACK_DIFFERENTIATED_KEYWORDS)
        or _is_relic_or_auto_subset(subset_name)
        or bool(re.search(r"\b(LL|CPC)\b", attrs_up))
    ):
        return 0.40, 0.60
    if _is_variation_or_error_subset(subset_name):
        return 0.94, 0.06
    if sub_canon != "BASE":
        return 0.88, 0.12
    return 0.78, 0.22


def _compute_rarity_and_sn_prior_adjustment(
    subset_name: str,
    set_name: str,
    expected_print_run: str,
    detected_serial_denom: Optional[str],
    is_base: bool,
    is_ordinary_root: bool,
    parallel_heavy_mode: bool = False,
) -> tuple[float, str]:
    """
    Applies a realistic hobby rarity/odds + serial-number prior:
      - Base is most likely (`+0.065`, or `+0.020` in parallel-heavy mode).
      - Matching stamped serial denominator (`#/N`) grants a strong `+0.12` boost.
      - Contradicting stamped serial denominator applies `-0.25`.
      - Serial-numbered parallels with NO detected serial stamp incur tiered rarity penalties
        (`/2026`..`/499`: -0.025, `/299`..`/50`: -0.045, `/25`..`/2`: -0.070, `1/1`: -0.100).
    """
    cfg_base_prior = float(RUNTIME_CONFIG.get("base_prior_bonus", 0.065))
    cfg_ord_prior = float(RUNTIME_CONFIG.get("insert_ordinary_prior_bonus", 0.045))
    base_prior = min(0.020, cfg_base_prior * 0.35) if parallel_heavy_mode else cfg_base_prior
    ord_prior = min(0.015, cfg_ord_prior * 0.35) if parallel_heavy_mode else cfg_ord_prior

    pr_clean = format_print_run(expected_print_run)
    det_sn = format_print_run(detected_serial_denom or "")
    sub_up = str(subset_name or "").upper()

    if is_base:
        if det_sn:
            # A genuine stamped serial number on the card strongly opposes plain unnumbered Base
            return -0.04, f"SN_OpposesBase(#/{det_sn})"
        return base_prior, ""

    if pr_clean:
        if det_sn:
            if det_sn == pr_clean:
                return float(RUNTIME_CONFIG.get("sn_exact_match_bonus", 0.12)), f"SN_Match(#/{det_sn})"
            return float(RUNTIME_CONFIG.get("sn_mismatch_penalty", -0.25)), f"SN_Mismatch(got#{det_sn}!=#{pr_clean})"
        pr_int = int(pr_clean) if pr_clean.isdigit() else 999
        if pr_int <= 1:
            return -0.100, "NoSN_1of1"
        if pr_int <= 25:
            return -0.070, f"NoSN_#{pr_int}"
        if pr_int <= 299:
            return -0.045, f"NoSN_#{pr_int}"
        return -0.025, f"NoSN_#{pr_int}"

    if any(k in sub_up for k in ("1/1", "SUPERFRACTOR", "PLATINUM", "PRINTING PLATE", "GOLDEN MIRROR")):
        return -0.085, "UltraRarePrior"
    if is_ordinary_root:
        return ord_prior, ""
    return 0.0, ""


def _check_front_ocr_for_named_variation(
    front_img: Image.Image,
    front_box: tuple[int, int, int, int],
    subset_name: str,
) -> tuple[bool, str]:
    """
    Named-Variation Front-OCR Gate:
    Currently enforces that any `"Walk This Way"` variation must actually show `"WALK THIS WAY"`
    (or `"WALKTHISWAY"`) in Front OCR. Returns `(passed, reason_tag)`.
    """
    sub_up = str(subset_name or "").upper()
    if "WALK THIS WAY" not in sub_up and "WALKTHISWAY" not in norm(sub_up):
        return True, ""
    try:
        fx1, fy1, fx2, fy2 = front_box
        f_crop = front_img.crop((fx1, fy1, max(fx1 + 40, fx2), max(fy1 + 40, fy2)))
        fw, fh = f_crop.size
        f_scale = min(1.0, 1100.0 / max(fw, fh))
        f_sm = f_crop.resize((max(80, int(fw * f_scale)), max(80, int(fh * f_scale))), Image.Resampling.BILINEAR)
        f_np = np.array(f_sm)
        lines = _run_rapidocr_lines(f_np) + _run_rapidocr_lines(255 - f_np)
        blob = norm(" ".join(lines))
        if "WALKTHISWAY" in blob or ("WALKTHIS" in blob and "WAY" in blob):
            return True, "WalkThisWay_FrontOCR_OK"
        return False, "WalkThisWay_NoFrontOCR"
    except Exception:
        return False, "WalkThisWay_NoFrontOCR"


def _measure_gold_back_score(back_crop_rgb: Optional[np.ndarray]) -> float:
    """
    Measures the metallic/rich golden-yellow color coverage on a card back (0.0 .. 1.0).
    Standard Topps backs are gray/white/blue/team-colored (~0.00 - 0.06), whereas
    Golden Mirror SSP backs are overwhelmingly rich gold (~0.28 - 0.80).
    """
    if back_crop_rgb is None or back_crop_rgb.size == 0:
        return 0.0
    try:
        small = cv2.resize(back_crop_rgb, (160, 224), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)

        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        a_ch = lab[:, :, 1]
        b_ch = lab[:, :, 2]

        gold_mask = (
            (h >= 13) & (h <= 34)
            & (s >= 52)
            & (v >= 95)
            & (b_ch >= 142)
            & (a_ch >= 118) & (a_ch <= 152)
        )
        border_mask = np.ones((224, 160), dtype=bool)
        border_mask[28:196, 20:140] = False
        full_ratio = float(np.mean(gold_mask))
        border_ratio = float(np.mean(gold_mask[border_mask]))
        return round(float(0.45 * full_ratio + 0.55 * border_ratio), 4)
    except Exception:
        return 0.0


def _is_canvas_subset(subset_name: str) -> bool:
    u = f" {str(subset_name or '').upper()} "
    return any(k in u for k in (" CANVAS", " LINEN", " CLOTH", " BURLAP"))


def _measure_canvas_weave_score(front_crop_rgb: Optional[np.ndarray]) -> float:
    """
    Measures physical woven-canvas substrate micro-texture (0.0 .. 1.0) to separate true
    Canvas-stock parallels from smooth paper/cardboard Base cards:
      1. Normalizes scale to `min_side = 600px` (~240 DPI) so canvas threads (3-6px period)
         measure identically across portrait & landscape scans.
      2. Inspects the clean right/bottom white border (explicitly avoiding 2026 Topps' printed
         left stitching bar!) where paper Base cards are dead smooth while Canvas shows weave.
      3. Inspects the smoothest 40% of interior `28x28` photo patches (blurred bokeh, uniform,
         dark shadows) for both high-pass micro-residual and 2D cross-weave (`min(|gx|, |gy|)`).
    Typical values:
      - Paper/cardboard Base card: ~0.00 - 0.18
      - True woven Canvas card   : ~0.42 - 0.92
    """
    if front_crop_rgb is None or front_crop_rgb.size == 0:
        return 0.0
    try:
        ih, iw = front_crop_rgb.shape[:2]
        if min(ih, iw) < 120:
            return 0.0

        # Scale so shorter side == 600px (consistent physical mm-per-pixel frequency scale)
        scale = 600.0 / float(min(ih, iw))
        nw, nh = max(120, int(round(iw * scale))), max(120, int(round(ih * scale)))
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        resized = cv2.resize(front_crop_rgb, (nw, nh), interpolation=interp)
        gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY).astype(np.float32)

        # Win #3: GPU OpenCL UMat high-pass & dual-axis cross-weave pipeline (automatic CPU fallback)
        blur_macro, hp_abs, cross_weave = opencl_highpass_and_cross_weave(gray)

        # Zone A: Clean white border avoiding the left decorative stitch bar (use right & top-right on portrait, bottom & right on landscape)
        is_landscape = nw > nh
        if is_landscape:
            b1 = hp_abs[int(nh * 0.945) : int(nh * 0.982), int(nw * 0.16) : int(nw * 0.86)]
            b2 = hp_abs[int(nh * 0.16) : int(nh * 0.84), int(nw * 0.955) : int(nw * 0.985)]
        else:
            b1 = hp_abs[int(nh * 0.14) : int(nh * 0.86), int(nw * 0.945) : int(nw * 0.982)]
            b2 = hp_abs[int(nh * 0.015) : int(nh * 0.045), int(nw * 0.72) : int(nw * 0.95)]

        border_vals = []
        if b1.size >= 40:
            border_vals.append(float(np.median(b1)))
        if b2.size >= 40:
            border_vals.append(float(np.median(b2)))
        border_hp_mad = min(border_vals) if border_vals else 0.0

        # Zone B: Smoothest 40% of interior 28x28 photo patches (isolates bokeh/solid areas cleanly)
        macro_gx = cv2.Sobel(blur_macro, cv2.CV_32F, 1, 0, ksize=3)
        macro_gy = cv2.Sobel(blur_macro, cv2.CV_32F, 0, 1, ksize=3)
        macro_mag = cv2.magnitude(macro_gx, macro_gy)

        y_start, y_end = int(nh * 0.14), int(nh * 0.78)
        x_start, x_end = int(nw * 0.18), int(nw * 0.88)
        patch_stats = []
        step = 28
        for py in range(y_start, max(y_start + step, y_end - step), step):
            for px in range(x_start, max(x_start + step, x_end - step), step):
                m_patch = macro_mag[py : py + step, px : px + step]
                if m_patch.size < 100:
                    continue
                macro_e = float(np.mean(m_patch))
                micro_e = float(np.mean(hp_abs[py : py + step, px : px + step]))
                cw_e = float(np.mean(cross_weave[py : py + step, px : px + step]))
                patch_stats.append((macro_e, micro_e, cw_e))

        if not patch_stats:
            return 0.0

        patch_stats.sort(key=lambda t: t[0])
        smooth_k = max(4, int(len(patch_stats) * 0.40))
        smoothest = patch_stats[:smooth_k]
        smooth_micro = float(np.median([t[1] for t in smoothest]))
        smooth_cross = float(np.median([t[2] for t in smoothest]))

        # Directional balance on the clean white border: real canvas weave has balanced X & Y threads,
        # whereas scanner streaks or printed edge lines are strongly 1-dimensional.
        if is_landscape:
            cw_b1 = cross_weave[int(nh * 0.945) : int(nh * 0.982), int(nw * 0.16) : int(nw * 0.86)]
            cw_b2 = cross_weave[int(nh * 0.16) : int(nh * 0.84), int(nw * 0.955) : int(nw * 0.985)]
        else:
            cw_b1 = cross_weave[int(nh * 0.14) : int(nh * 0.86), int(nw * 0.945) : int(nw * 0.982)]
            cw_b2 = cross_weave[int(nh * 0.015) : int(nh * 0.045), int(nw * 0.72) : int(nw * 0.95)]
        b_cw_vals = []
        if cw_b1.size >= 40:
            b_cw_vals.append(float(np.median(cw_b1)))
        if cw_b2.size >= 40:
            b_cw_vals.append(float(np.median(cw_b2)))
        border_cw_med = min(b_cw_vals) if b_cw_vals else 0.0

        s_border_hp = float(np.clip((border_hp_mad - 1.85) / 4.2, 0.0, 1.0))
        s_border_cw = float(np.clip((border_cw_med - 2.60) / 6.0, 0.0, 1.0))
        s_border = 0.50 * s_border_hp + 0.50 * s_border_cw

        s_interior = float(np.clip((smooth_micro - 2.40) / 4.8, 0.0, 1.0))
        s_cross = float(np.clip((smooth_cross - 3.60) / 6.8, 0.0, 1.0))
        interior_score = 0.45 * s_interior + 0.55 * s_cross

        # Mandatory white-border weave floor: genuine Canvas stock is woven edge-to-edge (including the white border!).
        # Smooth paper/cardboard Base cards have near-zero white-border weave and must NEVER pass on photo grain/pinstripes alone.
        if s_border < 0.28:
            return round(float(np.clip(s_border * 0.75, 0.0, 0.30)), 4)

        weave_score = float(np.sqrt(max(0.0, s_border * interior_score)))
        return round(float(np.clip(weave_score, 0.0, 1.0)), 4)
    except Exception:
        return 0.0


# ==============================================================================
# ALLEN & GINTER MINI / T206 PHYSICAL ASPECT-RATIO & A&G BACK CLASSIFIER SUITE
# ==============================================================================
_SUBSET_FORMAT_CACHE: dict[tuple[str, str], str] = {}
_BACK_EXEMPLAR_RGB_CACHE: dict[str, Optional[np.ndarray]] = {}


def _is_framed_mini_subset(subset_name: str) -> bool:
    u = f" {str(subset_name or '').upper()} "
    return "FRAMED" in u or "RIP CARD" in u or "FULL SIZE" in u or "FULL-SIZE" in u or "BOXLOADER" in u or "OVERSIZED" in u


def _is_ag_back_subset(subset_name: str) -> bool:
    u = str(subset_name or "").upper()
    c = norm(u)
    return "AGBACK" in c or "A&G BACK" in u or "A&G MAN BACK" in u or "AGMANBACK" in c


def _is_brooklyn_back_subset(subset_name: str) -> bool:
    return "BROOKLYN" in str(subset_name or "").upper()


def _is_no_number_subset(subset_name: str) -> bool:
    c = norm(subset_name)
    return "NONUMBER" in c or "NO NUMBER" in str(subset_name or "").upper()


def _is_black_border_subset(subset_name: str) -> bool:
    u = f" {str(subset_name or '').upper()} "
    return ("BLACK BORDER" in u or "MINI BLACK" in u or "BLACK MINI" in u) and "BROOKLYN" not in u


def _is_gold_border_subset(subset_name: str) -> bool:
    u = f" {str(subset_name or '').upper()} "
    return "GOLD BORDER" in u or "MINI GOLD" in u or "GOLD MINI" in u


def _is_ordinary_mini_subset(subset_name: str, set_name: str = "") -> bool:
    """Returns True for the plain unframed regular Mini subset (e.g., 'Mini', 'Base Mini', 'Mini Base')."""
    if _is_framed_mini_subset(subset_name):
        return False
    c = canonical_subset_key(subset_name or "", set_name)
    return c in ("MINI", "BASEMINI", "MINIBASE", "MINIS", "MINICARDS", "MINIEXTENDED", "EXTENDEDMINI")


def _classify_subset_physical_format(
    subset_name: str,
    set_name: str = "",
    template_catalog: Optional[dict] = None,
) -> str:
    """
    Classifies a checklist subset's true physical card size:
      - `'MINI'`     : Unframed Allen & Ginter Mini / T206 tobacco card (~1.47" x 2.625", aspect ~0.56)
      - `'STANDARD'` : Full-size trading card (~2.50" x 3.50", aspect ~0.714), including Framed Minis
    Checks explicit subset/set naming first, then inspects up to 3 `Reference_Library` JPEG headers
    (<0.1ms each, no pixel decode) so Mini-only inserts without the word 'Mini' are detected too!
    """
    sub_u = f" {str(subset_name or 'Base').upper()} "
    set_u = f" {str(set_name or '').upper()} "
    s_key = canonical_set_key(set_name)
    sub_canon = canonical_subset_key(subset_name or "Base", set_name)
    cache_k = (s_key, sub_canon)
    if cache_k in _SUBSET_FORMAT_CACHE:
        return _SUBSET_FORMAT_CACHE[cache_k]

    mini_max_asp = float(RUNTIME_CONFIG.get("mini_max_aspect_ratio", 0.635))
    fmt = "STANDARD"

    if _is_framed_mini_subset(sub_u):
        fmt = "STANDARD"
    elif "T206" in set_u or "TOPPS 206" in set_u or "T206" in sub_u or "TOBACCO" in sub_u:
        fmt = "MINI"
    elif " MINI" in sub_u or "MINI " in sub_u or sub_canon == "MINI":
        fmt = "MINI"
    elif sub_canon in ("BASE", "BASESET") or any(
        k in sub_u for k in ("CHROME", "FOIL FILIGREE", "HOT BOX", "SILVER PORTRAIT", "GLOSSY", "RELIC", "AUTOGRAPH")
    ):
        fmt = "STANDARD"
    elif template_catalog and s_key in template_catalog:
        set_tmpls = template_catalog.get(s_key, {})
        ratios = []
        for t_sub, t_bkt in set_tmpls.items():
            if not isinstance(t_bkt, dict) or canonical_subset_key(t_sub, set_name) != sub_canon:
                continue
            for c_list in (t_bkt.get("cards") or {}).values():
                if not c_list:
                    continue
                fp_s = c_list[0].get("front_path") or ""
                if fp_s and Path(fp_s).exists():
                    try:
                        with Image.open(fp_s) as im_hdr:
                            w_h, h_h = im_hdr.size
                        if min(w_h, h_h) > 40:
                            ratios.append(min(w_h, h_h) / float(max(w_h, h_h)))
                    except Exception:
                        pass
                if len(ratios) >= 3:
                    break
            if len(ratios) >= 3:
                break
        if ratios and float(np.median(ratios)) <= mini_max_asp:
            fmt = "MINI"

    _SUBSET_FORMAT_CACHE[cache_k] = fmt
    return fmt


def _is_unframed_mini_subset(subset_name: str, set_name: str = "", template_catalog: Optional[dict] = None) -> bool:
    return _classify_subset_physical_format(subset_name, set_name=set_name, template_catalog=template_catalog) == "MINI"


def _detect_card_format_geometry(
    front_img: Image.Image,
    back_img: Optional[Image.Image],
    front_box: tuple[int, int, int, int],
    back_box: Optional[tuple[int, int, int, int]] = None,
) -> dict:
    """
    Measures physical aspect ratio (`short_side / long_side`) from Front & Back crops + raw scans:
      - Standard trading card (2.50" x 3.50"): ~0.714 (typically 0.675 .. 0.755)
      - Allen & Ginter Mini / T206 (1.47" x 2.625"): ~0.560 (typically 0.515 .. 0.625)
    Completely DPI-independent and orientation-invariant (works for portrait & landscape scans).
    """
    def _aspect_for_side(im: Optional[Image.Image], box: Optional[tuple[int, int, int, int]]) -> Optional[float]:
        if im is None:
            return None
        iw, ih = im.size
        raw_asp = min(iw, ih) / float(max(1, max(iw, ih)))
        if box is not None:
            bw = max(1, int(box[2]) - int(box[0]))
            bh = max(1, int(box[3]) - int(box[1]))
            box_area_frac = (bw * bh) / float(max(1, iw * ih))
            if box_area_frac >= 0.22:
                box_asp = min(bw, bh) / float(max(bw, bh))
                if raw_asp <= 0.635 and box_asp > raw_asp + 0.04:
                    return raw_asp
                return box_asp
        return raw_asp

    f_asp = _aspect_for_side(front_img, front_box)
    b_asp = _aspect_for_side(back_img, back_box)

    if f_asp is not None and b_asp is not None:
        if abs(f_asp - b_asp) <= 0.06:
            card_asp = 0.5 * (f_asp + b_asp)
        else:
            card_asp = min(f_asp, b_asp) if min(f_asp, b_asp) <= 0.62 else 0.5 * (f_asp + b_asp)
    else:
        card_asp = f_asp if f_asp is not None else (b_asp if b_asp is not None else 0.714)

    mini_max = float(RUNTIME_CONFIG.get("mini_max_aspect_ratio", 0.635))
    std_min = float(RUNTIME_CONFIG.get("standard_min_aspect_ratio", 0.665))
    is_mini = bool(card_asp <= mini_max)
    is_standard = bool(card_asp >= std_min)

    return {
        "front_aspect": round(float(f_asp or card_asp), 4),
        "back_aspect": round(float(b_asp or card_asp), 4),
        "card_aspect": round(float(card_asp), 4),
        "is_mini": is_mini,
        "is_standard": is_standard,
        "format_label": f"Mini:{card_asp:.2f}" if is_mini else (f"Std:{card_asp:.2f}" if is_standard else f"Mid:{card_asp:.2f}"),
    }


def _measure_black_border_score(front_crop_rgb: Optional[np.ndarray]) -> float:
    """Measures solid black outer-border coverage (0.0 .. 1.0) to identify Mini Black Border cards."""
    if front_crop_rgb is None or front_crop_rgb.size == 0:
        return 0.0
    try:
        small = cv2.resize(front_crop_rgb, (160, 256), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
        mask_b = np.zeros((256, 160), dtype=bool)
        mask_b[4:252, 4:156] = True
        mask_b[22:234, 18:142] = False
        v_ch = hsv[:, :, 2][mask_b]
        s_ch = hsv[:, :, 1][mask_b]
        dark_mask = (v_ch <= 62) & (s_ch <= 115)
        return round(float(np.mean(dark_mask)), 4)
    except Exception:
        return 0.0


def _measure_gold_border_front_score(front_crop_rgb: Optional[np.ndarray]) -> float:
    """Measures metallic gold/amber outer-border coverage on the Front (separates Mini Gold Border from cream Mini)."""
    if front_crop_rgb is None or front_crop_rgb.size == 0:
        return 0.0
    try:
        small = cv2.resize(front_crop_rgb, (160, 256), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)
        mask_b = np.zeros((256, 160), dtype=bool)
        mask_b[4:252, 4:156] = True
        mask_b[22:234, 18:142] = False
        h = hsv[:, :, 0][mask_b]
        s = hsv[:, :, 1][mask_b]
        v = hsv[:, :, 2][mask_b]
        b_ch = lab[:, :, 2][mask_b]
        gold_mask = (h >= 12) & (h <= 34) & (s >= 65) & (v >= 85) & (b_ch >= 145)
        return round(float(np.mean(gold_mask)), 4)
    except Exception:
        return 0.0


def _analyze_ag_back_ocr_signals(back_ocr_lines: list[str], card_number: str = "") -> dict:
    """
    Inspects Back OCR text to distinguish Allen & Ginter back variants:
      - Standard Mini / Full-Size Back: player bio/stats lines ('BATS', 'THROWS', 'BORN', 'MAJOR LEAGUE')
      - Mini A&G Back: vintage ornate A&G ad ('WORLDS CHAMPIONS', 'RICHMOND', 'ORIGINAL PICTURE', etc.)
      - Mini Brooklyn Back: 'BROOKLYN', '237 36TH' ad + '/25'
      - Mini No Number: A&G back design with card number absent from back OCR
    """
    raw_blob = " ".join(str(x or "") for x in (back_ocr_lines or []))
    n_blob = norm(raw_blob)

    brooklyn_hits = sum(
        1 for tok in ("BROOKLYN", "23736TH", "36THST", "BROOKLYNNY", "THEBROOKLYN")
        if tok in n_blob
    )
    ag_ad_hits = sum(
        1 for tok in (
            "WORLDSCHAMPIONS", "WORLDCHAMPIONS", "RICHMONDVA", "RICHMONDVIRGINIA",
            "ORIGINALPICTURE", "CIGARETTES", "THISCARDISONEOF", "ALLENANDGINTER",
            "ALLENGINTERS", "GINTERS", "CHEROOTS", "SMOKINGTOBACCO", "FACTORYNO",
            "THEFAMOUS", "COLLECTALL",
        )
        if tok in n_blob
    )
    bio_stat_hits = sum(
        1 for tok in (
            "BATS", "THROWS", "BORN", "DRAFTED", "ACQUIRED", "MAJORLEAGUEBATTING",
            "MAJORLEAGUEPITCHING", "BATTINGRECORD", "PITCHINGRECORD", "HEIGHT", "WEIGHT",
            "CAREERTOTALS", "MLBTOTALS", "SEASONSTATS", "HOMERUNS", "RUNSBATTEDIN",
        )
        if tok in n_blob
    )

    cn_clean = norm(str(card_number or "").lstrip("#"))
    cn_on_back = bool(cn_clean and cn_clean != "0" and re.search(rf"(?<![A-Z0-9]){re.escape(cn_clean)}(?![A-Z0-9])", raw_blob.upper()))

    return {
        "has_brooklyn_text": brooklyn_hits >= 1,
        "has_ag_ad_text": (ag_ad_hits >= 1 and bio_stat_hits == 0) or (ag_ad_hits >= 2),
        "has_standard_bio_stats": bio_stat_hits >= 1,
        "ag_ad_hits": ag_ad_hits,
        "bio_stat_hits": bio_stat_hits,
        "card_number_on_back": cn_on_back,
    }


def _load_cached_back_exemplar_rgb(img_path_str: str) -> Optional[np.ndarray]:
    p_s = str(img_path_str or "").strip()
    if not p_s:
        return None
    if p_s in _BACK_EXEMPLAR_RGB_CACHE:
        return _BACK_EXEMPLAR_RGB_CACHE[p_s]
    p_obj = Path(p_s)
    if not p_obj.exists():
        _BACK_EXEMPLAR_RGB_CACHE[p_s] = None
        return None
    try:
        with Image.open(p_obj) as im:
            rgb = np.array(im.convert("RGB"))
        ih, iw = rgb.shape[:2]
        asp = min(ih, iw) / float(max(1, max(ih, iw)))
        is_land = iw > ih
        wh = ((356, 200) if is_land else (200, 356)) if asp <= 0.635 else ((356, 256) if is_land else (256, 356))
        resized = cv2.resize(rgb, wh, interpolation=cv2.INTER_AREA)
        if len(_BACK_EXEMPLAR_RGB_CACHE) > 800:
            _BACK_EXEMPLAR_RGB_CACHE.clear()
        _BACK_EXEMPLAR_RGB_CACHE[p_s] = resized
        return resized
    except Exception:
        _BACK_EXEMPLAR_RGB_CACHE[p_s] = None
        return None


def _compute_subset_group_back_similarity(
    scan_back_crop: Optional[np.ndarray],
    back_paths: list[str],
    max_samples: int = 8,
) -> Optional[float]:
    """
    Compares the scanned card's Back against up to `max_samples` exemplar `_B.jpg` files
    for a subset (crucial for Allen & Ginter where every `Mini A&G Back` or `Mini Brooklyn Back`
    shares the identical back design across the entire set!).
    """
    if scan_back_crop is None or scan_back_crop.size == 0 or not back_paths:
        return None
    sims = []
    for bp in back_paths[:max_samples]:
        ref_arr = _load_cached_back_exemplar_rgb(bp)
        if ref_arr is not None:
            sims.append(_compute_single_side_whole_image_similarity(scan_back_crop, ref_arr))
    if not sims:
        return None
    sims.sort(reverse=True)
    top_k = sims[: min(3, len(sims))]
    return round(float(np.mean(top_k)), 4)


def _extract_front_nameplate_ocr_lines(front_img: Image.Image, front_box: tuple[int, int, int, int]) -> list[str]:
    """Fast targeted Front nameplate OCR (bottom 30% + top 22% bands) to rescue A&G Back Mini identities."""
    try:
        fx1, fy1, fx2, fy2 = front_box
        f_crop = front_img.crop((fx1, fy1, max(fx1 + 40, fx2), max(fy1 + 40, fy2)))
        fw, fh = f_crop.size
        f_scale = min(1.0, 1100.0 / max(fw, fh))
        f_sm = f_crop.resize((max(80, int(fw * f_scale)), max(80, int(fh * f_scale))), Image.Resampling.BILINEAR)
        f_np = np.array(f_sm)
        sh = f_np.shape[0]
        lines = []
        for band in (f_np[int(sh * 0.68) :, :], f_np[: int(sh * 0.24), :]):
            if band.size == 0:
                continue
            lines.extend(_run_rapidocr_lines(band))
            lines.extend(_run_rapidocr_lines(255 - band))
        return lines
    except Exception:
        return []

_LEGACY_TMPL_FILENAME_RE = re.compile(
    r"^(?P<set>.+?)___(?P<subset>.+?)__(?P<cid>[A-Za-z0-9\-]+?)(?P<qual>[RS])?_(?P<side>Front|Back|F|B)\.jpe?g$",
    re.IGNORECASE,
)


def _compute_visual_feature_vector(img: Image.Image, card_box: Optional[tuple[int, int, int, int]] = None) -> np.ndarray:
    if card_box is not None:
        x1, y1, x2, y2 = card_box
        crop = img.crop((x1, y1, max(x1 + 20, x2), max(y1 + 20, y2)))
    else:
        crop = img

    small_rgb = np.array(crop.resize((128, 176), Image.Resampling.BILINEAR))
    hsv = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2LAB).astype(np.float32) / 255.0
    gray = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2GRAY)

    mask_border = np.ones((176, 128), dtype=np.uint8)
    mask_border[24:152, 18:110] = 0

    hist_border_h = cv2.calcHist([hsv], [0], mask_border, [24], [0, 180]).flatten()
    hist_border_s = cv2.calcHist([hsv], [1], mask_border, [16], [0, 256]).flatten()
    hist_border_v = cv2.calcHist([hsv], [2], mask_border, [16], [0, 256]).flatten()
    border_vec = np.concatenate([hist_border_h * 1.4, hist_border_s * 1.2, hist_border_v * 1.0]).astype(np.float32)
    b_norm = float(np.linalg.norm(border_vec))
    if b_norm > 1e-6:
        border_vec /= b_norm

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    eq_gray = clahe.apply(gray)
    struct_thumb = cv2.resize(eq_gray, (24, 34), interpolation=cv2.INTER_AREA).astype(np.float32).flatten() / 255.0
    struct_thumb -= float(np.mean(struct_thumb))
    s_norm = float(np.linalg.norm(struct_thumb))
    if s_norm > 1e-6:
        struct_thumb /= s_norm

    sobel_x = cv2.Sobel(eq_gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(eq_gray, cv2.CV_32F, 0, 1, ksize=3)
    edge_mag = cv2.magnitude(sobel_x, sobel_y)
    edge_thumb = cv2.resize(edge_mag, (24, 34), interpolation=cv2.INTER_AREA).flatten()
    e_norm = float(np.linalg.norm(edge_thumb))
    if e_norm > 1e-6:
        edge_thumb /= e_norm

    interior_lab = lab[18:158, 14:114, :]
    lab_grid = cv2.resize(interior_lab, (12, 16), interpolation=cv2.INTER_AREA).flatten()
    l_norm = float(np.linalg.norm(lab_grid))
    if l_norm > 1e-6:
        lab_grid /= l_norm

    vec = np.concatenate([
        border_vec * 0.90,
        struct_thumb * 1.35,
        edge_thumb * 1.15,
        lab_grid * 1.25,
    ]).astype(np.float32)

    norm_val = float(np.linalg.norm(vec))
    return vec / norm_val if norm_val > 1e-6 else vec


def _compute_single_side_whole_image_similarity(
    scan_crop_rgb: np.ndarray,
    tmpl_rgb: np.ndarray,
) -> float:
    s_is_land = scan_crop_rgb.shape[1] > scan_crop_rgb.shape[0]
    t_is_land = tmpl_rgb.shape[1] > tmpl_rgb.shape[0]
    # If a TCDB reference template was uploaded sideways relative to our upright scan, test both 90° rotations
    if s_is_land != t_is_land:
        best_rot = 0.0
        for rot_code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            t_rot = cv2.rotate(tmpl_rgb, rot_code)
            sc_r = _compute_single_side_whole_image_similarity(scan_crop_rgb, t_rot)
            if sc_r > best_rot:
                best_rot = sc_r
        return best_rot

    s_asp = min(scan_crop_rgb.shape[0], scan_crop_rgb.shape[1]) / float(max(1, max(scan_crop_rgb.shape[0], scan_crop_rgb.shape[1])))
    t_asp = min(tmpl_rgb.shape[0], tmpl_rgb.shape[1]) / float(max(1, max(tmpl_rgb.shape[0], tmpl_rgb.shape[1])))
    mini_max_asp = float(RUNTIME_CONFIG.get("mini_max_aspect_ratio", 0.635))
    both_mini = (s_asp <= mini_max_asp and t_asp <= mini_max_asp + 0.03)
    if both_mini:
        target_wh = (356, 200) if s_is_land else (200, 356)
    else:
        target_wh = (356, 256) if s_is_land else (256, 356)
    s_256 = cv2.resize(scan_crop_rgb, target_wh, interpolation=cv2.INTER_AREA)
    t_256 = cv2.resize(tmpl_rgb, target_wh, interpolation=cv2.INTER_AREA)

    s_g64 = cv2.GaussianBlur(cv2.cvtColor(s_256, cv2.COLOR_RGB2GRAY), (3, 3), 0)
    t_g64 = cv2.GaussianBlur(cv2.cvtColor(t_256, cv2.COLOR_RGB2GRAY), (3, 3), 0)
    s_f = cv2.resize(s_g64, (64, 88), interpolation=cv2.INTER_AREA).astype(np.float32)
    t_f = cv2.resize(t_g64, (64, 88), interpolation=cv2.INTER_AREA).astype(np.float32)
    s_f -= float(np.mean(s_f))
    t_f -= float(np.mean(t_f))
    denom_zncc = float(np.linalg.norm(s_f) * np.linalg.norm(t_f))
    zncc_raw = float(np.sum(s_f * t_f) / denom_zncc) if denom_zncc > 1e-6 else 0.0
    zncc_sim = float(np.clip((zncc_raw + 1.0) * 0.5, 0.0, 1.0))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    s_eq = clahe.apply(cv2.resize(cv2.cvtColor(s_256, cv2.COLOR_RGB2GRAY), (128, 176), interpolation=cv2.INTER_AREA)).astype(np.float32)
    t_eq = clahe.apply(cv2.resize(cv2.cvtColor(t_256, cv2.COLOR_RGB2GRAY), (128, 176), interpolation=cv2.INTER_AREA)).astype(np.float32)

    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    mu1 = cv2.GaussianBlur(s_eq, (7, 7), 1.5)
    mu2 = cv2.GaussianBlur(t_eq, (7, 7), 1.5)
    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu1_mu2 = mu1 * mu2
    sigma1_sq = cv2.GaussianBlur(s_eq * s_eq, (7, 7), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(t_eq * t_eq, (7, 7), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(s_eq * t_eq, (7, 7), 1.5) - mu1_mu2
    ssim_map = ((2.0 * mu1_mu2 + c1) * (2.0 * sigma12 + c2)) / ((mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2))
    ssim_sim = float(np.clip((float(np.mean(ssim_map)) + 1.0) * 0.5, 0.0, 1.0))

    s_lab = cv2.resize(cv2.cvtColor(s_256, cv2.COLOR_RGB2LAB), (32, 44), interpolation=cv2.INTER_AREA).astype(np.float32)
    t_lab = cv2.resize(cv2.cvtColor(t_256, cv2.COLOR_RGB2LAB), (32, 44), interpolation=cv2.INTER_AREA).astype(np.float32)
    weights = np.array([0.45, 1.35, 1.35], dtype=np.float32)
    s_w = (s_lab * weights).flatten()
    t_w = (t_lab * weights).flatten()
    s_w -= float(np.mean(s_w))
    t_w -= float(np.mean(t_w))
    denom_lab = float(np.linalg.norm(s_w) * np.linalg.norm(t_w))
    lab_raw = float(np.sum(s_w * t_w) / denom_lab) if denom_lab > 1e-6 else 0.0
    lab_sim = float(np.clip((lab_raw + 1.0) * 0.5, 0.0, 1.0))

    blended = 0.40 * zncc_sim + 0.35 * ssim_sim + 0.25 * lab_sim
    return round(float(np.clip(blended, 0.0, 1.0)), 4)


_LAZY_BORDER_SIG_CACHE: dict[str, Optional[np.ndarray]] = {}
_BORDER_SIG_CACHE_FILE = FEATURE_CACHE_FILE.parent / "parallel_border_sigs_v24.pkl"
_BORDER_SIG_DISK_LOADED = False
_BORDER_SIG_DIRTY_CNT = 0


def _ensure_border_sig_cache_loaded():
    global _BORDER_SIG_DISK_LOADED
    if _BORDER_SIG_DISK_LOADED:
        return
    _BORDER_SIG_DISK_LOADED = True
    if _BORDER_SIG_CACHE_FILE.exists():
        try:
            with open(_BORDER_SIG_CACHE_FILE, "rb") as f:
                loaded = pickle.load(f)
            if isinstance(loaded, dict):
                _LAZY_BORDER_SIG_CACHE.update(loaded)
        except Exception:
            pass


def _flush_border_sig_cache(force: bool = False):
    global _BORDER_SIG_DIRTY_CNT
    if not force and _BORDER_SIG_DIRTY_CNT < 25:
        return
    _BORDER_SIG_DIRTY_CNT = 0
    try:
        trimmed = dict(list(_LAZY_BORDER_SIG_CACHE.items())[-4000:])
        def _dump_border_sig(tmp_p: Path):
            with open(tmp_p, "wb") as f:
                pickle.dump(trimmed, f, protocol=pickle.HIGHEST_PROTOCOL)
        atomic_write_bytes(_BORDER_SIG_CACHE_FILE, _dump_border_sig)
    except Exception:
        pass


def _compute_border_foil_signature(crop_rgb: np.ndarray) -> np.ndarray:
    """
    Extracts an L2-normalized outer-border color & foil-finish texture signature
    designed to distinguish similar parallels (e.g., Purple Holo Foil vs. Purple Rainbow Foil
    vs. Purple Diamante vs. Base) even when comparing across different players in the same parallel.
    """
    small_rgb = cv2.resize(crop_rgb, (160, 224), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2LAB)
    gray = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2GRAY)

    # Outer 12% perimeter border band (where foil color & pattern dominate)
    mask_border = np.ones((224, 160), dtype=np.uint8)
    mask_border[26:198, 20:140] = 0

    h_hist = cv2.calcHist([hsv], [0], mask_border, [36], [0, 180]).flatten().astype(np.float32)
    s_hist = cv2.calcHist([hsv], [1], mask_border, [20], [0, 256]).flatten().astype(np.float32)
    v_hist = cv2.calcHist([hsv], [2], mask_border, [16], [0, 256]).flatten().astype(np.float32)
    a_hist = cv2.calcHist([lab], [1], mask_border, [20], [0, 256]).flatten().astype(np.float32)
    b_hist = cv2.calcHist([lab], [2], mask_border, [20], [0, 256]).flatten().astype(np.float32)

    for arr in (h_hist, s_hist, v_hist, a_hist, b_hist):
        n_v = float(np.linalg.norm(arr))
        if n_v > 1e-6:
            arr /= n_v

    # High-frequency foil-sparkle / holo texture features on the border band
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(sx, sy)
    lap_abs = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    border_bool = mask_border.astype(bool)

    grad_vals = np.clip(grad_mag[border_bool], 0.0, 255.0)
    lap_vals = np.clip(lap_abs[border_bool], 0.0, 255.0)
    g_hist, _ = np.histogram(grad_vals, bins=16, range=(0.0, 255.0))
    l_hist, _ = np.histogram(lap_vals, bins=12, range=(0.0, 255.0))
    tex_vec = np.concatenate([g_hist.astype(np.float32), l_hist.astype(np.float32)])
    t_norm = float(np.linalg.norm(tex_vec))
    if t_norm > 1e-6:
        tex_vec /= t_norm

    # Saturation-vs-luminance energy summary (distinguishes matte paper vs rainbow vs holo foil)
    s_border = hsv[:, :, 1][border_bool].astype(np.float32) / 255.0
    v_border = hsv[:, :, 2][border_bool].astype(np.float32) / 255.0
    stats_vec = np.array([
        float(np.mean(s_border)),
        float(np.std(s_border)),
        float(np.percentile(s_border, 90)),
        float(np.mean(v_border)),
        float(np.std(v_border)),
        float(np.mean(grad_vals) / 255.0),
        float(np.std(grad_vals) / 255.0),
        float(np.mean(lap_vals) / 255.0),
    ], dtype=np.float32)
    st_norm = float(np.linalg.norm(stats_vec))
    if st_norm > 1e-6:
        stats_vec /= st_norm

    sig = np.concatenate([
        h_hist * 1.45,
        s_hist * 1.25,
        v_hist * 0.85,
        a_hist * 1.35,
        b_hist * 1.35,
        tex_vec * 1.30,
        stats_vec * 1.10,
    ]).astype(np.float32)
    total_norm = float(np.linalg.norm(sig))
    return sig / total_norm if total_norm > 1e-6 else sig


def _get_lazy_border_foil_signature(img_path_str: str) -> Optional[np.ndarray]:
    global _BORDER_SIG_DIRTY_CNT
    _ensure_border_sig_cache_loaded()
    p_str = str(img_path_str or "").strip()
    if not p_str:
        return None
    if p_str in _LAZY_BORDER_SIG_CACHE:
        return _LAZY_BORDER_SIG_CACHE[p_str]
    p_obj = Path(p_str)
    if not p_obj.exists():
        return None
    try:
        with Image.open(p_obj) as im:
            sig = _compute_border_foil_signature(np.array(im.convert("RGB")))
        _LAZY_BORDER_SIG_CACHE[p_str] = sig
        _BORDER_SIG_DIRTY_CNT += 1
        _flush_border_sig_cache(force=False)
        return sig
    except Exception:
        return None


def _extract_enhanced_back_and_front_ocr(
    front_img: Image.Image,
    back_oriented: Image.Image,
    front_box: tuple[int, int, int, int],
    back_box: tuple[int, int, int, int],
    base_ocr_bundle: dict,
) -> dict:
    """
    Tier 3 Enhanced Re-Read + Front OCR:
      1. Runs CLAHE contrast-boosted & sharpened high-res OCR on the card back's top corners,
         top header, and full back to rescue clipped/faint card digits (e.g., '121' misread as '21').
      2. Runs Front OCR across the cropped card front + zoomed bottom & top nameplate bands
         (normal & inverted) to extract the player name and team directly off the front!
    """
    extra_back_hdr: list[str] = []
    extra_back_corners: list[str] = []
    extra_back_full: list[str] = []
    front_lines: list[str] = []

    try:
        bx1, by1, bx2, by2 = back_box
        b_crop = back_oriented.crop((bx1, by1, max(bx1 + 40, bx2), max(by1 + 40, by2)))
        bw, bh = b_crop.size
        b_scale = min(1.0, 1600.0 / max(bw, bh))
        b_hi = b_crop.resize((max(100, int(bw * b_scale)), max(100, int(bh * b_scale))), Image.Resampling.LANCZOS)
        b_np = np.array(b_hi)
        b_eq, b_eq_rgb = opencl_clahe_enhance(b_np)
        eh, ew = b_eq.shape[:2]

        # Re-read enhanced full back + sharpened header
        extra_back_full.extend(_run_rapidocr_lines(b_eq_rgb))
        hdr_band = b_eq_rgb[: int(eh * 0.28), :]
        extra_back_hdr.extend(_run_rapidocr_lines(hdr_band))
        extra_back_hdr.extend(_run_rapidocr_lines(255 - hdr_band))

        # High-contrast zoomed top-left & top-right corner crops (normal, inverted, Otsu thresholded)
        for c_patch in (b_eq[: int(eh * 0.24), : int(ew * 0.42)], b_eq[: int(eh * 0.24), int(ew * 0.58) :]):
            if c_patch.size == 0:
                continue
            up_c = cv2.resize(c_patch, (0, 0), fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
            up_rgb = cv2.cvtColor(up_c, cv2.COLOR_GRAY2RGB)
            extra_back_corners.extend(_run_rapidocr_lines(up_rgb))
            extra_back_corners.extend(_run_rapidocr_lines(255 - up_rgb))
            _, otsu_c = cv2.threshold(up_c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            extra_back_corners.extend(_run_rapidocr_lines(cv2.cvtColor(otsu_c, cv2.COLOR_GRAY2RGB)))
    except Exception:
        pass

    try:
        fx1, fy1, fx2, fy2 = front_box
        f_crop = front_img.crop((fx1, fy1, max(fx1 + 40, fx2), max(fy1 + 40, fy2)))
        fw, fh = f_crop.size
        f_scale = min(1.0, 1250.0 / max(fw, fh))
        f_mid = f_crop.resize((max(100, int(fw * f_scale)), max(100, int(fh * f_scale))), Image.Resampling.LANCZOS)
        f_np = np.array(f_mid)
        front_lines.extend(_run_rapidocr_lines(f_np))

        # Zoomed bottom & top nameplate bands (normal + inverted for dark/colored nameplates)
        mh, mw = f_np.shape[:2]
        for band in (f_np[int(mh * 0.68) :, :], f_np[: int(mh * 0.26), :]):
            if band.size == 0:
                continue
            front_lines.extend(_run_rapidocr_lines(band))
            front_lines.extend(_run_rapidocr_lines(255 - band))
    except Exception:
        pass

    return {
        "full_lines": list(base_ocr_bundle.get("full_lines", [])) + extra_back_full + extra_back_hdr + extra_back_corners + front_lines,
        "header_norm": list(base_ocr_bundle.get("header_norm", [])) + extra_back_hdr + front_lines,
        "header_inv": list(base_ocr_bundle.get("header_inv", [])),
        "corner_zoom": list(base_ocr_bundle.get("corner_zoom", [])) + extra_back_corners,
        "ricoh_0deg": list(base_ocr_bundle.get("ricoh_0deg", [])),
    }


def _verify_candidate_whole_image(
    scan_front_crop: np.ndarray,
    scan_back_crop: Optional[np.ndarray],
    set_name: str,
    subset_name: str,
    card_number: str,
    template_catalog: dict,
    reviewed_by_card: dict,
    batch_visual_memory: Optional[dict] = None,
    scan_front_desc: Optional[dict] = None,
    scan_back_desc: Optional[dict] = None,
) -> dict:
    """
    Tier 2 Direct Whole-Image Confirmation:
    Compares the scanned card's Front + Back directly against reference image(s) of
    `(set_name, subset_name, card_number)` from `Reference_Library`, `_My_Collection`,
    and high-confidence cards already identified earlier in the current batch.
    """
    s_key = canonical_set_key(set_name)
    sub_canon = canonical_subset_key(subset_name or "Base", set_name)
    n_cnum = norm(str(card_number or "").lstrip("#"))
    is_back_diff = any(bk in sub_canon for bk in _BACK_DIFFERENTIATED_KEYWORDS)

    best = {
        "has_ref": False,
        "sim": 0.0,
        "front_sim": 0.0,
        "back_sim": None,
        "front_rel": "",
        "back_rel": "",
        "source": "None",
    }

    # 1. Check in-batch already high-confidence identified cards first (instant memory hit!)
    if batch_visual_memory:
        mem_rec = batch_visual_memory.get((s_key, sub_canon, n_cnum))
        if mem_rec is not None:
            f_sim = _compute_single_side_whole_image_similarity(scan_front_crop, mem_rec["front_rgb"])
            b_sim = (
                _compute_single_side_whole_image_similarity(scan_back_crop, mem_rec["back_rgb"])
                if (scan_back_crop is not None and mem_rec.get("back_rgb") is not None)
                else None
            )
            comb = ((0.45 * f_sim + 0.55 * b_sim) if is_back_diff else (0.65 * f_sim + 0.35 * b_sim)) if b_sim is not None else f_sim
            best = {
                "has_ref": True,
                "sim": round(comb, 4),
                "front_sim": f_sim,
                "back_sim": b_sim,
                "front_rel": mem_rec.get("front_rel", ""),
                "back_rel": mem_rec.get("back_rel", ""),
                "source": "Batch_Confirmed",
            }
            if best["sim"] >= 0.86:
                return best

    # 2. Gather exact card reference images — PRIORITIZE _My_Collection (same scanner/lighting!) before Reference_Library
    candidate_pairs: list[tuple[str, str, str]] = []
    for r_item in reviewed_by_card.get((s_key, n_cnum), []):
        if canonical_subset_key(r_item[0], set_name) == sub_canon and len(r_item) >= 4 and r_item[3]:
            candidate_pairs.append((r_item[3], r_item[4] if len(r_item) >= 5 else "", "My_Collection"))

    set_tmpls = template_catalog.get(s_key, {})
    for t_sub, t_bkt in set_tmpls.items():
        if not isinstance(t_bkt, dict):
            continue
        if canonical_subset_key(t_sub, set_name) == sub_canon:
            for c_rec in t_bkt.get("cards", {}).get(n_cnum, [])[:3]:
                if c_rec.get("front_path"):
                    candidate_pairs.append((c_rec.get("front_path", ""), c_rec.get("back_path", ""), "Reference_Library"))

    # Guarantee 100% parity with Guided Batch Review: if lazy index missed a newly downloaded image, resolve directly on disk
    if not candidate_pairs and set_name and n_cnum:
        try:
            from Core.database import resolve_template_reference_paths
            disk_ref = resolve_template_reference_paths(set_name, subset_name or "Base", card_number)
            if disk_ref.get("front_abs") and Path(disk_ref["front_abs"]).exists():
                candidate_pairs.append((disk_ref["front_abs"], disk_ref.get("back_abs", ""), "Disk_RefFallback"))
        except Exception:
            pass

    q_front_neural_emb = scan_front_desc.get("vec") if isinstance(scan_front_desc, dict) else None
    q_back_neural_emb = scan_back_desc.get("vec") if isinstance(scan_back_desc, dict) else None
    if candidate_pairs and is_neural_embeddings_enabled():
        batch_paths = [p for fp_s, bp_s, _ in candidate_pairs[:4] for p in (fp_s, bp_s) if p]
        if batch_paths:
            precompute_batch_image_descriptors(batch_paths, require_multiregion=False)

    for fp_s, bp_s, src_lbl in candidate_pairs[:4]:
        if not fp_s or not Path(fp_s).exists():
            continue
        try:
            with Image.open(fp_s) as tf_im:
                tf_arr = np.array(tf_im.convert("RGB"))
            f_sim_cls = _compute_single_side_whole_image_similarity(scan_front_crop, tf_arr)
            f_sim, q_front_neural_emb = _compute_hybrid_neural_sim(
                scan_front_crop, f_sim_cls, ref_path=fp_s, ref_crop_rgb=tf_arr, scan_emb=q_front_neural_emb, neural_weight=0.55, scan_desc=scan_front_desc, match_mode="identity"
            )
            b_sim = None
            if scan_back_crop is not None and bp_s and Path(bp_s).exists():
                with Image.open(bp_s) as tb_im:
                    tb_arr = np.array(tb_im.convert("RGB"))
                b_sim_cls = _compute_single_side_whole_image_similarity(scan_back_crop, tb_arr)
                b_sim, q_back_neural_emb = _compute_hybrid_neural_sim(
                    scan_back_crop, b_sim_cls, ref_path=bp_s, ref_crop_rgb=tb_arr, scan_emb=q_back_neural_emb, neural_weight=0.50, scan_desc=scan_back_desc, match_mode="identity"
                )
            comb = ((0.45 * f_sim + 0.55 * b_sim) if is_back_diff else (0.65 * f_sim + 0.35 * b_sim)) if b_sim is not None else f_sim
            if not best["has_ref"] or comb > best["sim"]:
                best = {
                    "has_ref": True,
                    "sim": round(comb, 4),
                    "front_sim": f_sim,
                    "back_sim": b_sim,
                    "front_rel": _format_rel_template_ref(Path(fp_s), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR),
                    "back_rel": _format_rel_template_ref(Path(bp_s), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR) if bp_s else "",
                    "source": f"{src_lbl}+DINOv2" if q_front_neural_emb is not None else src_lbl,
                }
        except Exception:
            continue

    return best


def _search_set_visually(
    front_img: Image.Image,
    front_box: tuple[int, int, int, int],
    back_img: Optional[Image.Image],
    back_box: Optional[tuple[int, int, int, int]],
    set_name: str,
    preferred_subset: str,
    active_root_df: pd.DataFrame,
    parallels_map: dict,
    template_catalog: dict,
    reviewed_by_card: dict,
    batch_visual_memory: Optional[dict] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    scan_front_desc: Optional[dict] = None,
) -> Optional[dict]:
    """
    Tier 4 Full-Set Visual Search:
    Searches the scanned card visually across:
      1. High-confidence cards already identified in the current batch (instant memory lookup).
      2. `_My_Collection` reviewed cards for the set.
      3. `Reference_Library` images for the set (prioritizing `preferred_subset` / `Base` first).
    Shortlists Top 6 by Stage-1 vector dot-product, then verifies via Stage-2 Whole-Image Comparison.
    """
    if active_root_df is None or active_root_df.empty:
        return None

    fx1, fy1, fx2, fy2 = front_box
    scan_front_crop = np.array(front_img.crop((fx1, fy1, max(fx1 + 20, fx2), max(fy1 + 20, fy2))))
    q_front_vec = _compute_visual_feature_vector(front_img, front_box)

    scan_back_crop = None
    q_back_vec = None
    if back_img is not None:
        if back_box is not None:
            bx1, by1, bx2, by2 = back_box
            scan_back_crop = np.array(back_img.crop((bx1, by1, max(bx1 + 20, bx2), max(by1 + 20, by2))))
        else:
            scan_back_crop = np.array(back_img)
        q_back_vec = _compute_visual_feature_vector(back_img, back_box)

    s_key = canonical_set_key(set_name)
    pref_sub_canon = canonical_subset_key(preferred_subset or "Base", set_name)
    stage1_hits: list[tuple[float, dict]] = []

    # 1. Instant scan against already-ID'd high-confidence cards from this same batch
    if batch_visual_memory:
        for (m_sk, m_sub_c, m_cn), m_rec in batch_visual_memory.items():
            if s_key and m_sk != s_key:
                continue
            fv = m_rec.get("front_vec")
            bv = m_rec.get("back_vec")
            if fv is None:
                continue
            f_s1 = float(np.dot(q_front_vec, fv))
            s1 = (0.65 * f_s1 + 0.35 * float(np.dot(q_back_vec, bv))) if (q_back_vec is not None and bv is not None) else f_s1
            stage1_hits.append((s1, {
                "n_cnum": m_cn,
                "subset": m_rec.get("subset", preferred_subset or "Base"),
                "front_rgb": m_rec.get("front_rgb"),
                "back_rgb": m_rec.get("back_rgb"),
                "front_path": "",
                "back_path": "",
                "front_rel": m_rec.get("front_rel", ""),
                "back_rel": m_rec.get("back_rel", ""),
                "source": "Batch_Visual",
            }))

    # 2. Scan _My_Collection cards for this set
    for (r_sk, r_cn), r_list in reviewed_by_card.items():
        if s_key and r_sk != s_key:
            continue
        if not r_list:
            continue
        # Prefer matching subset or first copy
        picked = next((x for x in r_list if canonical_subset_key(x[0], set_name) == pref_sub_canon), r_list[0])
        r_sub, r_fv, r_bv, r_fp, r_bp = picked[0], picked[1], (picked[2] if len(picked) >= 3 else None), (picked[3] if len(picked) >= 4 else ""), (picked[4] if len(picked) >= 5 else "")
        if r_fv is None and r_fp:
            r_fv = _get_lazy_visual_feature_vector(r_fp)
        if r_fv is None:
            continue
        f_s1 = float(np.dot(q_front_vec, r_fv))
        if q_back_vec is not None and r_bv is None and r_bp:
            r_bv = _get_lazy_visual_feature_vector(r_bp)
        s1 = (0.65 * f_s1 + 0.35 * float(np.dot(q_back_vec, r_bv))) if (q_back_vec is not None and r_bv is not None) else f_s1
        stage1_hits.append((s1, {
            "n_cnum": r_cn,
            "subset": r_sub,
            "front_path": r_fp,
            "back_path": r_bp,
            "source": "Collection_Visual",
        }))

    # 3. Scan Reference_Library cards for this set (prioritize preferred_subset / Base to stay blazing fast)
    set_tmpls = template_catalog.get(s_key, {})
    target_sub_buckets = []
    for t_sub, t_bkt in set_tmpls.items():
        if not isinstance(t_bkt, dict):
            continue
        t_canon = canonical_subset_key(t_sub, set_name)
        if t_canon == pref_sub_canon or t_canon == "BASE":
            target_sub_buckets.insert(0, (t_sub, t_bkt))
        elif not preferred_subset:
            target_sub_buckets.append((t_sub, t_bkt))

    seen_ref_cnums: set[str] = set()
    ref_evaluated = 0
    for t_sub, t_bkt in target_sub_buckets:
        for n_cn, c_list in (t_bkt.get("cards") or {}).items():
            if not n_cn or n_cn == "_GENERIC" or n_cn in seen_ref_cnums or not c_list:
                continue
            c_rec = c_list[0]
            fp_s = str(c_rec.get("front_path") or "")
            bp_s = str(c_rec.get("back_path") or "")
            if not fp_s:
                continue
            fv = c_rec.get("front_vec")
            if fv is None:
                fv = _get_lazy_visual_feature_vector(fp_s)
                c_rec["front_vec"] = fv
            if fv is None:
                continue
            seen_ref_cnums.add(n_cn)
            ref_evaluated += 1
            f_s1 = float(np.dot(q_front_vec, fv))
            bv = c_rec.get("back_vec")
            if q_back_vec is not None and bv is None and bp_s and f_s1 >= 0.68:
                bv = _get_lazy_visual_feature_vector(bp_s)
                c_rec["back_vec"] = bv
            s1 = (0.65 * f_s1 + 0.35 * float(np.dot(q_back_vec, bv))) if (q_back_vec is not None and bv is not None) else f_s1
            stage1_hits.append((s1, {
                "n_cnum": n_cn,
                "subset": t_sub,
                "front_path": fp_s,
                "back_path": bp_s,
                "source": "RefLibrary_Visual",
            }))
            if ref_evaluated >= 1200:
                break
        if ref_evaluated >= 1200:
            break

    # 4. Instant (<2ms) Full-Set DINOv2 Semantic Vector Search across ALL indexed cards in the set (no 1,200 cap!)
    q_t4_neural_desc = scan_front_desc
    q_t4_neural_emb = q_t4_neural_desc.get("vec") if isinstance(q_t4_neural_desc, dict) else None
    if is_neural_embeddings_enabled():
        try:
            eng_n = get_neural_embedding_engine(load_now=True)
            if eng_n is not None and eng_n.is_ready:
                if q_t4_neural_desc is None:
                    q_t4_neural_desc = eng_n.extract_descriptor(scan_front_crop, include_color_foil=False)
                    q_t4_neural_emb = q_t4_neural_desc.get("vec") if isinstance(q_t4_neural_desc, dict) else None
                if q_t4_neural_emb is not None:
                    n_hits = search_set_neural_embeddings(q_t4_neural_emb, set_name=set_name, side="F", top_k=10)
                    for n_cos, n_meta in n_hits:
                        fp_n = str(n_meta.get("path") or "")
                        bp_n = fp_n[:-6] + "_B.jpg" if fp_n.upper().endswith("_F.JPG") and Path(fp_n[:-6] + "_B.jpg").exists() else ""
                        stage1_hits.append((float(n_cos) + 0.08, {
                            "n_cnum": str(n_meta.get("n_cnum") or ""),
                            "subset": str(n_meta.get("subset") or preferred_subset or "Base"),
                            "front_path": fp_n,
                            "back_path": bp_n,
                            "source": f"DINOv2_{n_meta.get('source', 'Index')}",
                        }))
        except Exception:
            pass

    if not stage1_hits:
        return None

    stage1_hits.sort(key=lambda x: x[0], reverse=True)
    # Deduplicate by card number and run Stage-2 Direct Whole-Image Comparison on Top 6
    top_unique: list[dict] = []
    seen_s2: set[str] = set()
    for _, item in stage1_hits:
        cn_k = item["n_cnum"]
        if cn_k in seen_s2:
            continue
        seen_s2.add(cn_k)
        top_unique.append(item)
        if len(top_unique) >= 6:
            break

    if top_unique and is_neural_embeddings_enabled():
        t4_ref_paths = [str(it.get("front_path") or "") for it in top_unique if it.get("front_path")]
        if t4_ref_paths:
            precompute_batch_image_descriptors(t4_ref_paths, require_multiregion=False)

    stage2_scored: list[tuple[float, dict]] = []
    for item in top_unique:
        try:
            tf_arr = item.get("front_rgb")
            if tf_arr is None and item.get("front_path") and Path(item["front_path"]).exists():
                with Image.open(item["front_path"]) as tf_im:
                    tf_arr = np.array(tf_im.convert("RGB"))
            if tf_arr is None:
                continue
            f_sim_cls = _compute_single_side_whole_image_similarity(scan_front_crop, tf_arr)
            f_sim, q_t4_neural_emb = _compute_hybrid_neural_sim(
                scan_front_crop, f_sim_cls, ref_path=item.get("front_path"), ref_crop_rgb=tf_arr, scan_emb=q_t4_neural_emb, neural_weight=0.58, scan_desc=q_t4_neural_desc, match_mode="identity"
            )
            b_sim = None
            tb_arr = item.get("back_rgb")
            if scan_back_crop is not None:
                if tb_arr is None and item.get("back_path") and Path(item["back_path"]).exists():
                    with Image.open(item["back_path"]) as tb_im:
                        tb_arr = np.array(tb_im.convert("RGB"))
                if tb_arr is not None:
                    b_sim = _compute_single_side_whole_image_similarity(scan_back_crop, tb_arr)
            comb = (0.65 * f_sim + 0.35 * b_sim) if b_sim is not None else f_sim
            item["sim"] = round(comb, 4)
            item["front_sim"] = f_sim
            item["back_sim"] = b_sim
            stage2_scored.append((comb, item))
        except Exception:
            continue

    if not stage2_scored:
        return None

    stage2_scored.sort(key=lambda x: x[0], reverse=True)
    win_sim, win_item = stage2_scored[0]
    runner_sim = stage2_scored[1][0] if len(stage2_scored) > 1 else (win_sim - 0.15)
    margin = win_sim - runner_sim

    min_vis = float(RUNTIME_CONFIG.get("full_set_visual_match_threshold", 0.82))
    min_marg = float(RUNTIME_CONFIG.get("full_set_visual_margin", 0.020))
    if win_sim < min_vis or (margin < min_marg and win_sim < 0.88):
        return None

    # Resolve winning card number back to checklist row
    hits_df = active_root_df[active_root_df["norm_cnum"] == win_item["n_cnum"]]
    if hits_df.empty:
        return None
    matched = hits_df.iloc[0]
    s_final = str(matched["Set"]).strip()
    cn_final = str(matched["Card Number"]).strip().lstrip("#")
    plr_final = str(matched["Player"]).strip()
    tm_final = str(matched["Team"]).strip()
    attr_final = str(matched.get("Attributes", "")).strip()
    par_key = (s_final, matched["norm_cnum"], matched["norm_player"])
    valid_subs = list(parallels_map.get(par_key) or [str(matched["Subset"])])

    fp_rel = win_item.get("front_rel") or (
        _format_rel_template_ref(Path(win_item["front_path"]), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR)
        if win_item.get("front_path")
        else ""
    )
    bp_rel = win_item.get("back_rel") or (
        _format_rel_template_ref(Path(win_item["back_path"]), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR)
        if win_item.get("back_path")
        else ""
    )
    if log_cb:
        log_cb(
            f"    🔎 [Tier 4 Full-Set Visual Recovery] Matched #{cn_final} {plr_final} "
            f"(sim={win_sim:.3f}, margin=+{margin:.3f}, src={win_item['source']})"
        )
    return {
        "Set": s_final,
        "Card_Number": cn_final,
        "Player": plr_final,
        "Team": tm_final,
        "Attributes": attr_final,
        "Subset": win_item.get("subset") or valid_subs[0],
        "valid_subsets": valid_subs,
        "sim": round(win_sim, 4),
        "front_rel": fp_rel,
        "back_rel": bp_rel,
        "source": win_item["source"],
    }


def verify_and_correct_parallel_match(
    front_img: Image.Image,
    front_box: tuple[int, int, int, int],
    back_img: Optional[Image.Image],
    back_box: Optional[tuple[int, int, int, int]],
    set_name: str,
    card_number: str,
    current_subset: str,
    valid_subsets: list[str],
    ordinary_roots: set[str],
    template_catalog: dict,
    reviewed_by_card: dict,
    reviewed_parallels: dict,
    parallel_heavy_mode: bool = False,
    back_ocr_blob: str = "",
    print_run_map: Optional[dict] = None,
    detected_serial_denom: Optional[str] = None,
    card_attributes: str = "",
    cmp_hint_subset: str = "",
    scan_front_desc: Optional[dict] = None,
) -> dict:
    """
    Mandatory Visual Validation & Self-Correction Tournament for Parallels, Golden Mirrors,
    Image/Error Variations, and Relics:
      1. 1-to-1 Exact Card Validation whenever exact `(Set, Subset, Card #)` reference image exists.
      2. Group Similarity across available cards in the parallel (up to 40 evenly distributed cards)
         when the exact card image isn't available (and as finish consistency support).
      3. Mandatory Golden Mirror Back Validation: checks gold-back colorimetric score AND back
         whole-image match against Golden Mirror backs vs. Base backs. Non-gold backs disqualify GM!
      4. Mandatory Image/Error Variation Gate: requires exact 1-to-1 visual match clearly beating Base.
      5. Mandatory Relic/Auto Gate: prevents plain numeric Base cards from falsely flipping to Relics.
      6. Restored Base Prior Advantage (`base_prior_bonus = 0.065`, `0.020` in Parallel-Heavy mode).
    """
    fx1, fy1, fx2, fy2 = front_box
    scan_front_crop = np.array(front_img.crop((fx1, fy1, max(fx1 + 20, fx2), max(fy1 + 20, fy2))))
    q_border_sig = _compute_border_foil_signature(scan_front_crop)
    q_par_desc = scan_front_desc
    if q_par_desc is None and is_neural_embeddings_enabled():
        try:
            eng_par = get_neural_embedding_engine(load_now=True)
            if eng_par is not None and eng_par.is_ready:
                q_par_desc = eng_par.extract_descriptor(scan_front_crop, include_color_foil=True)
        except Exception:
            q_par_desc = None
    elif isinstance(q_par_desc, dict) and q_par_desc.get("color_foil_vec") is None and is_neural_embeddings_enabled():
        try:
            from Core.neural_vision import extract_color_foil_descriptor
            q_par_desc = dict(q_par_desc)
            q_par_desc["color_foil_vec"] = extract_color_foil_descriptor(scan_front_crop)
        except Exception:
            pass

    scan_back_crop = None
    gold_back_score = 0.0
    if back_img is not None:
        if back_box is not None:
            bx1, by1, bx2, by2 = back_box
            scan_back_crop = np.array(back_img.crop((bx1, by1, max(bx1 + 20, bx2), max(by1 + 20, by2))))
        else:
            scan_back_crop = np.array(back_img)
        gold_back_score = _measure_gold_back_score(scan_back_crop)

    s_key = canonical_set_key(set_name)
    n_cnum = norm(card_number)
    set_tmpls = template_catalog.get(s_key, {})
    set_rev_pars = reviewed_parallels.get(s_key, {})
    exact_card_revs = reviewed_by_card.get((s_key, n_cnum), [])

    cfg_base_prior = float(RUNTIME_CONFIG.get("base_prior_bonus", 0.065))
    cfg_ord_prior = float(RUNTIME_CONFIG.get("insert_ordinary_prior_bonus", 0.045))
    base_prior = min(0.020, cfg_base_prior * 0.35) if parallel_heavy_mode else cfg_base_prior
    ord_prior = min(0.015, cfg_ord_prior * 0.35) if parallel_heavy_mode else cfg_ord_prior
    sample_limit = max(12, int(RUNTIME_CONFIG.get("parallel_group_sample_limit", 40)))
    gm_min_gold = float(RUNTIME_CONFIG.get("golden_mirror_min_gold_score", 0.22))
    gm_min_back_sim = float(RUNTIME_CONFIG.get("golden_mirror_min_back_sim", 0.74))
    canvas_min_weave = float(RUNTIME_CONFIG.get("canvas_min_weave_score", 0.48))
    canvas_strong_weave = float(RUNTIME_CONFIG.get("canvas_strong_weave_score", 0.68))
    var_margin = float(RUNTIME_CONFIG.get("variation_override_margin", 0.045))
    min_par_conf = float(RUNTIME_CONFIG.get("parallel_min_confidence", 0.75))
    min_grp_conf = float(RUNTIME_CONFIG.get("parallel_group_min_confidence", 0.78))
    fmt_mismatch_pen = float(RUNTIME_CONFIG.get("mini_format_mismatch_penalty", -0.35))
    mini_base_prior = float(RUNTIME_CONFIG.get("mini_base_prior_bonus", 0.055))
    ag_back_wt = float(RUNTIME_CONFIG.get("ag_back_visual_weight", 0.78))

    card_geom = _detect_card_format_geometry(front_img, back_img, front_box, back_box)
    ag_ocr = _analyze_ag_back_ocr_signals([back_ocr_blob], card_number=card_number)

    has_base_valid = any(canonical_subset_key(s, set_name) == "BASE" for s in (valid_subsets or []))
    candidates_to_check = list(dict.fromkeys((["Base"] if has_base_valid else []) + [current_subset] + list(valid_subsets or [])))

    has_canvas_in_cands = any(_is_canvas_subset(sc) for sc in candidates_to_check)
    canvas_weave_score = _measure_canvas_weave_score(scan_front_crop) if has_canvas_in_cands else 0.0
    has_black_in_cands = any(_is_black_border_subset(sc) for sc in candidates_to_check)
    black_border_score = _measure_black_border_score(scan_front_crop) if has_black_in_cands else 0.0
    has_gold_border_cands = any(_is_gold_border_subset(sc) for sc in candidates_to_check)
    gold_border_front_score = _measure_gold_border_front_score(scan_front_crop) if has_gold_border_cands else 0.0
    has_ag_back_tournament = any(
        _is_ag_back_subset(sc) or _is_brooklyn_back_subset(sc) or _is_no_number_subset(sc)
        for sc in candidates_to_check
    )

    scored: list[dict] = []
    rejected_notes: list[str] = []

    pr_map = print_run_map or {}
    walk_this_way_checked: Optional[tuple[bool, str]] = None

    for sub_cand in candidates_to_check:
        sub_canon = canonical_subset_key(sub_cand, set_name)
        sub_fmt = _classify_subset_physical_format(sub_cand, set_name=set_name, template_catalog=template_catalog)
        is_mini_sub = (sub_fmt == "MINI")
        is_ord_mini = _is_ordinary_mini_subset(sub_cand, set_name)
        is_base = (sub_canon == "BASE")
        is_gm = _is_golden_mirror_subset(sub_cand)
        is_canvas = _is_canvas_subset(sub_cand)
        is_var = _is_variation_or_error_subset(sub_cand)
        is_relic = _is_relic_or_auto_subset(sub_cand)
        is_ag_bk = _is_ag_back_subset(sub_cand)
        is_bklyn_bk = _is_brooklyn_back_subset(sub_cand)
        is_nonum_bk = _is_no_number_subset(sub_cand)
        is_black_bdr = _is_black_border_subset(sub_cand)
        is_gold_bdr = _is_gold_border_subset(sub_cand)
        is_back_diff = is_gm or is_ag_bk or is_bklyn_bk or is_nonum_bk or any(bk in sub_canon for bk in _BACK_DIFFERENTIATED_KEYWORDS)
        fw_wt, bw_wt = _get_dynamic_front_back_weights(sub_cand, set_name=set_name, card_attributes=card_attributes)

        # Hard physical format filter: skip impossible format mismatches early when valid same-format candidates exist
        if card_geom["is_mini"] and not is_mini_sub:
            rejected_notes.append(f"FmtReject({sub_cand}:NotMini)")
            continue
        if card_geom["is_standard"] and is_mini_sub:
            rejected_notes.append(f"FmtReject({sub_cand}:NotStd)")
            continue
        expected_pr = (
            pr_map.get((set_name, sub_cand, n_cnum))
            or pr_map.get((set_name, sub_cand, str(card_number).lstrip("#")))
            or ""
        )

        # Mandatory Front-OCR gate for "Walk This Way" variation
        if "WALK THIS WAY" in str(sub_cand).upper() or "WALKTHISWAY" in sub_canon:
            if walk_this_way_checked is None:
                walk_this_way_checked = _check_front_ocr_for_named_variation(front_img, front_box, sub_cand)
            if not walk_this_way_checked[0]:
                rejected_notes.append(walk_this_way_checked[1])
                continue

        exact_pairs: list[tuple[str, str]] = []
        exemplar_front_paths: list[str] = []
        exemplar_back_paths: list[str] = []

        # Prioritize _My_Collection confirmed scans first!
        # (Exact _My_Collection scans already added first above)

        for t_sub, t_bkt in set_tmpls.items():
            if not isinstance(t_bkt, dict):
                continue
            if canonical_subset_key(t_sub, set_name) == sub_canon:
                cards_map = t_bkt.get("cards") or {}
                for c_rec in cards_map.get(n_cnum, [])[:2]:
                    if c_rec.get("front_path"):
                        exact_pairs.append((c_rec.get("front_path", ""), c_rec.get("back_path", "")))
                other_recs = [
                    c_list[0] for k_cn, c_list in cards_map.items()
                    if k_cn != n_cnum and c_list and c_list[0].get("front_path")
                ]
                if len(other_recs) > sample_limit:
                    step = max(1, len(other_recs) // sample_limit)
                    other_recs = other_recs[::step][:sample_limit]
                for rec_e in other_recs:
                    fp_e = rec_e.get("front_path") or ""
                    bp_e = rec_e.get("back_path") or ""
                    if fp_e:
                        exemplar_front_paths.append(fp_e)
                    if bp_e:
                        exemplar_back_paths.append(bp_e)

        for r_item in exact_card_revs:
            if canonical_subset_key(r_item[0], set_name) == sub_canon and len(r_item) >= 4 and r_item[3]:
                exact_pairs.append((r_item[3], r_item[4] if len(r_item) >= 5 else ""))

        if len(exemplar_front_paths) < sample_limit:
            for p_sub, p_list in set_rev_pars.items():
                if canonical_subset_key(p_sub, set_name) == sub_canon:
                    for p_it in p_list:
                        fp_p = p_it.get("front_path", "") if isinstance(p_it, dict) else ""
                        bp_p = p_it.get("back_path", "") if isinstance(p_it, dict) else ""
                        if fp_p and fp_p not in exemplar_front_paths:
                            exemplar_front_paths.append(fp_p)
                        if bp_p and bp_p not in exemplar_back_paths:
                            exemplar_back_paths.append(bp_p)
                        if len(exemplar_front_paths) >= sample_limit:
                            break

        if not exact_pairs and not exemplar_front_paths:
            continue

        if q_par_desc is not None and is_neural_embeddings_enabled():
            par_batch_paths = [fp_s for fp_s, _ in exact_pairs[:2] if fp_s] + [
                ex_fp for ex_fp in exemplar_front_paths[:sample_limit] if ex_fp
            ]
            if par_batch_paths:
                precompute_batch_image_descriptors(par_batch_paths, require_multiregion=True)

        par_match_mode = "variation" if is_var else ("back_diff" if is_back_diff else "parallel")
        best_exact_whole = None
        best_exact_front = None
        best_exact_back = None
        best_exact_border = None
        best_fp, best_bp = "", ""
        for fp_s, bp_s in exact_pairs[:2]:
            if not fp_s or not Path(fp_s).exists():
                continue
            try:
                with Image.open(fp_s) as tf_im:
                    tf_arr = np.array(tf_im.convert("RGB"))
                f_sim_raw = _compute_single_side_whole_image_similarity(scan_front_crop, tf_arr)
                # Blend DINOv2 multi-region similarity strongly for Image/Photo Variations (60%) & parallel checks (38%)
                n_wt_par = 0.60 if is_var else (0.38 if not is_back_diff else 0.22)
                f_sim, _ = _compute_hybrid_neural_sim(
                    scan_front_crop,
                    f_sim_raw,
                    ref_path=fp_s,
                    ref_crop_rgb=tf_arr,
                    neural_weight=n_wt_par,
                    scan_desc=q_par_desc,
                    match_mode=par_match_mode,
                )
                b_sim = None
                if scan_back_crop is not None and bp_s and Path(bp_s).exists():
                    with Image.open(bp_s) as tb_im:
                        tb_arr = np.array(tb_im.convert("RGB"))
                    b_sim = _compute_single_side_whole_image_similarity(scan_back_crop, tb_arr)
                whole_s = (fw_wt * f_sim + bw_wt * b_sim) if b_sim is not None else f_sim
                ref_bsig = _get_lazy_border_foil_signature(fp_s)
                b_foil_s = float(np.dot(q_border_sig, ref_bsig)) if ref_bsig is not None else whole_s
                if best_exact_whole is None or whole_s > best_exact_whole:
                    best_exact_whole = whole_s
                    best_exact_front = f_sim
                    best_exact_back = b_sim
                    best_exact_border = b_foil_s
                    best_fp, best_bp = fp_s, bp_s
            except Exception:
                continue

        ex_scores = []
        parallel_consistency = None
        if q_par_desc is not None and exemplar_front_paths and is_neural_embeddings_enabled():
            parallel_consistency = score_parallel_group_vectorized(
                q_par_desc, exemplar_front_paths[:sample_limit], top_k=5
            )
        if parallel_consistency is None:
            for ex_fp in exemplar_front_paths[:sample_limit]:
                ex_sig = _get_lazy_border_foil_signature(ex_fp)
                if ex_sig is not None:
                    ex_scores.append(float(np.dot(q_border_sig, ex_sig)))
            ex_scores.sort(reverse=True)
            top_k_grp = ex_scores[: min(5, len(ex_scores))]
            parallel_consistency = float(np.mean(top_k_grp)) if top_k_grp else None
        ex_count_n = len(ex_scores) if ex_scores else len(exemplar_front_paths[:sample_limit])

        # Compute group back similarity across ALL back-differentiated AND competing Mini/Base subsets!
        group_back_sim = best_exact_back
        need_group_back = is_back_diff or (has_ag_back_tournament and (is_mini_sub or is_base))
        if need_group_back and group_back_sim is None and scan_back_crop is not None and exemplar_back_paths:
            group_back_sim = _compute_subset_group_back_similarity(scan_back_crop, exemplar_back_paths, max_samples=8)

        if not best_fp and exemplar_front_paths:
            best_fp = exemplar_front_paths[0]
        if not best_bp and exemplar_back_paths:
            best_bp = exemplar_back_paths[0]

        if best_exact_whole is not None:
            if parallel_consistency is not None:
                front_combined = 0.54 * best_exact_whole + 0.28 * float(best_exact_border or best_exact_whole) + 0.18 * parallel_consistency
                detail = f"1v1:{best_exact_whole:.2f}|Foil:{best_exact_border:.2f}|Grp:{parallel_consistency:.2f}(n={ex_count_n})"
            else:
                front_combined = 0.64 * best_exact_whole + 0.36 * float(best_exact_border or best_exact_whole)
                detail = f"1v1:{best_exact_whole:.2f}|Foil:{best_exact_border:.2f}"
            src_kind = "Exact1v1"
        elif parallel_consistency is not None:
            front_combined = parallel_consistency
            detail = f"ParGrp:{parallel_consistency:.2f}(n={ex_count_n})"
            src_kind = "ParallelGroup"
        elif group_back_sim is not None:
            front_combined = group_back_sim
            detail = f"BackOnly:{group_back_sim:.2f}"
            src_kind = "BackExemplars"
        else:
            continue

        # Integrate Back Visual Similarity directly into raw_score for A&G Back / Brooklyn / Mini Back tournaments!
        if has_ag_back_tournament and group_back_sim is not None and (is_back_diff or is_ord_mini or (card_geom["is_mini"] and is_mini_sub and not is_black_bdr and not is_gold_bdr)):
            raw_score = (1.0 - ag_back_wt) * front_combined + ag_back_wt * group_back_sim
            detail = f"BackVis:{group_back_sim:.2f}|{detail}"
            src_kind = "Back+Front"
        elif is_back_diff and group_back_sim is not None and best_exact_back is None:
            raw_score = 0.40 * front_combined + 0.60 * group_back_sim
            detail = f"BackGrp:{group_back_sim:.2f}|{detail}"
        else:
            raw_score = front_combined

        # Base / Ordinary Mini / Rarity / Serial Number priors
        if card_geom["is_mini"] and is_ord_mini:
            prior_bonus = mini_base_prior
            sn_note = f"MiniBasePrior({card_geom['format_label']})"
        else:
            prior_bonus, sn_note = _compute_rarity_and_sn_prior_adjustment(
                subset_name=sub_cand,
                set_name=set_name,
                expected_print_run=expected_pr,
                detected_serial_denom=detected_serial_denom,
                is_base=is_base,
                is_ordinary_root=(sub_cand in ordinary_roots),
                parallel_heavy_mode=parallel_heavy_mode,
            )

        # Back OCR & Front Border physical corroboration for Allen & Ginter Minis
        if is_bklyn_bk:
            if ag_ocr["has_brooklyn_text"]:
                prior_bonus += 0.12
                detail = f"{detail}|BklynOCR"
            elif not (detected_serial_denom and str(detected_serial_denom) == "25"):
                prior_bonus -= 0.08
        elif is_nonum_bk:
            if ag_ocr["card_number_on_back"]:
                prior_bonus -= 0.14
                detail = f"{detail}|HasBackNum"
            elif ag_ocr["has_ag_ad_text"]:
                prior_bonus += 0.05
        elif is_ag_bk:
            if ag_ocr["has_ag_ad_text"]:
                prior_bonus += 0.07
                detail = f"{detail}|AGBackOCR"
            elif ag_ocr["has_standard_bio_stats"] and not ag_ocr["has_ag_ad_text"]:
                prior_bonus -= 0.09
                detail = f"{detail}|BioOnBack"
        elif is_ord_mini and has_ag_back_tournament:
            if ag_ocr["has_standard_bio_stats"]:
                prior_bonus += 0.05
                detail = f"{detail}|StdBioOCR"
            elif ag_ocr["has_ag_ad_text"] and not ag_ocr["has_standard_bio_stats"]:
                prior_bonus -= 0.08
                detail = f"{detail}|AGAdDetected"

        if is_black_bdr:
            if black_border_score >= 0.45:
                prior_bonus += 0.10
            detail = f"{detail}|BlkBdr:{black_border_score:.2f}"
        if is_gold_bdr:
            if gold_border_front_score >= 0.40:
                prior_bonus += 0.08
            detail = f"{detail}|GldBdr:{gold_border_front_score:.2f}"

        if is_canvas and canvas_weave_score >= canvas_strong_weave:
            prior_bonus += 0.03
            detail = f"{detail}|Weave:{canvas_weave_score:.2f}"
        elif is_canvas:
            detail = f"{detail}|Weave:{canvas_weave_score:.2f}"

        if cmp_hint_subset and canonical_subset_key(cmp_hint_subset, set_name) == sub_canon:
            prior_bonus += float(RUNTIME_CONFIG.get("cmp_match_bonus", 0.035))
        if sn_note:
            detail = f"{detail}|{sn_note}"

        scored.append({
            "subset": sub_cand,
            "sub_canon": sub_canon,
            "is_base": is_base,
            "is_ord_mini": is_ord_mini,
            "is_mini_sub": is_mini_sub,
            "is_gm": is_gm,
            "is_canvas": is_canvas,
            "is_black_bdr": is_black_bdr,
            "is_gold_bdr": is_gold_bdr,
            "is_var": is_var,
            "is_relic": is_relic,
            "has_exact": best_exact_whole is not None,
            "exact_whole": best_exact_whole,
            "exact_front": best_exact_front,
            "back_sim": group_back_sim,
            "raw_score": round(float(raw_score), 4),
            "adj_score": round(float(raw_score + prior_bonus), 4),
            "detail": detail,
            "src_kind": src_kind,
            "front_rel": _format_rel_template_ref(Path(best_fp), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR) if best_fp else "",
            "back_rel": _format_rel_template_ref(Path(best_bp), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR) if best_bp else "",
        })

    if not scored:
        return {
            "subset": "Base" if has_base_valid else current_subset,
            "score": 0.0,
            "self_corrected": False,
            "is_ambiguous": True,
            "top3_str": f"{current_subset}(NoParallelRefs)",
            "front_rel": "",
            "back_rel": "",
            "note": "NoParallelRefs",
        }

    base_entry = next((x for x in scored if x["is_base"]), None)
    base_raw = base_entry["raw_score"] if base_entry else 0.0
    base_back_sim = base_entry["back_sim"] if (base_entry and base_entry["back_sim"] is not None) else 0.0

    validated: list[dict] = []
    for item in scored:
        if item["is_base"]:
            validated.append(item)
            continue

        if item["is_gm"]:
            gm_back_ok = False
            if item["back_sim"] is not None:
                if (item["back_sim"] >= gm_min_back_sim and gold_back_score >= 0.15 and item["back_sim"] >= base_back_sim + 0.025) or (
                    gold_back_score >= 0.30 and item["back_sim"] >= base_back_sim
                ):
                    gm_back_ok = True
            else:
                if gold_back_score >= max(0.28, gm_min_gold) and item["has_exact"] and item["raw_score"] >= base_raw + 0.04:
                    gm_back_ok = True
            if not gm_back_ok:
                rejected_notes.append(f"GM_BackRejected(gold={gold_back_score:.2f},bSim={item['back_sim'] or 0:.2f})")
                continue

        elif item.get("is_canvas"):
            if canvas_weave_score < canvas_min_weave:
                rejected_notes.append(f"Canvas_SmoothPaperRejected(weave={canvas_weave_score:.2f})")
                continue

        elif item.get("is_black_bdr"):
            if black_border_score < 0.28:
                rejected_notes.append(f"BlackBorder_Rejected(blk={black_border_score:.2f})")
                continue

        elif item.get("is_gold_bdr"):
            if gold_border_front_score < 0.22:
                rejected_notes.append(f"GoldBorder_Rejected(gld={gold_border_front_score:.2f})")
                continue

        elif item["is_var"]:
            if not item["has_exact"] or item["raw_score"] < 0.78 or (base_entry is not None and item["raw_score"] < base_raw + var_margin):
                rejected_notes.append(f"VarRejected({item['subset']}:{item['raw_score']:.2f})")
                continue

        elif item["is_relic"]:
            is_plain_num = str(card_number or "").strip().lstrip("#").isdigit()
            has_ocr_cert = _back_ocr_has_relic_or_auto_text(back_ocr_blob)
            if is_plain_num and not has_ocr_cert:
                if not item["has_exact"] or item["raw_score"] < 0.85 or (base_entry is not None and item["raw_score"] < base_raw + 0.07):
                    rejected_notes.append(f"RelicRejected({item['subset']}:NoBackCert)")
                    continue

        else:
            req_conf = min_par_conf if item["has_exact"] else min_grp_conf
            if item["raw_score"] < req_conf:
                rejected_notes.append(f"ParLowConf({item['subset']}:{item['raw_score']:.2f})")
                continue

        validated.append(item)

    if not validated:
        if base_entry is not None:
            validated = [base_entry]
        else:
            return {
                "subset": "Base" if has_base_valid else current_subset,
                "score": 0.0,
                "self_corrected": (has_base_valid and canonical_subset_key(current_subset, set_name) != "BASE"),
                "is_ambiguous": True,
                "top3_str": " | ".join(rejected_notes[:3]) or f"{current_subset}(Rejected)",
                "front_rel": "",
                "back_rel": "",
                "note": "+".join(rejected_notes[:2]) or "ParallelRejected->Base",
            }

    validated.sort(key=lambda x: x["adj_score"], reverse=True)
    winner = validated[0]
    runner = validated[1] if len(validated) > 1 else None
    margin = (winner["adj_score"] - runner["adj_score"]) if runner else 0.15

    cur_in_val = next((x for x in validated if x["sub_canon"] == canonical_subset_key(current_subset, set_name)), None)
    sc_margin = float(RUNTIME_CONFIG.get("parallel_self_correct_margin", 0.025))

    self_corrected = False
    if cur_in_val is None:
        chosen = winner
        self_corrected = (winner["sub_canon"] != canonical_subset_key(current_subset, set_name))
    elif winner["sub_canon"] != cur_in_val["sub_canon"] and (winner["adj_score"] - cur_in_val["adj_score"]) >= sc_margin:
        chosen = winner
        self_corrected = True
    else:
        chosen = cur_in_val

    is_ambiguous = (chosen["raw_score"] < min_par_conf) or (
        not chosen["is_base"] and runner is not None and margin < 0.020
    )
    top3_str = " | ".join(f"{x['subset']}({x['raw_score']:.3f} [{x['detail']}])" for x in validated[:3])
    if rejected_notes:
        top3_str = f"{top3_str} | Rej:{','.join(rejected_notes[:2])}"

    if self_corrected:
        note = f"ParallelSelfCorrected({current_subset}->{chosen['subset']})"
    elif rejected_notes:
        note = f"Validated({chosen['subset']}:{chosen['raw_score']:.2f})+" + "+".join(rejected_notes[:2])
    else:
        note = f"VisualVerified({chosen['src_kind']}:{chosen['raw_score']:.2f})"

    return {
        "subset": chosen["subset"],
        "score": chosen["raw_score"],
        "self_corrected": self_corrected,
        "is_ambiguous": is_ambiguous,
        "top3_str": top3_str,
        "front_rel": chosen["front_rel"],
        "back_rel": chosen["back_rel"],
        "note": note,
    }


def identify_and_verify_card_pipeline(
    front_img: Image.Image,
    back_oriented: Image.Image,
    front_box: tuple[int, int, int, int],
    back_box: tuple[int, int, int, int],
    ocr_bundle: dict,
    active_root_df: pd.DataFrame,
    parallels_map: dict,
    ordinary_roots: set,
    template_catalog: dict,
    reviewed_by_card: dict,
    reviewed_parallels: dict,
    clean_locked_set: str = "",
    clean_locked_subset: str = "",
    parallel_heavy_mode: bool = False,
    stamped_pr: Optional[str] = None,
    batch_visual_memory: Optional[dict] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    print_run_map: Optional[dict] = None,
    precomputed_front_desc: Optional[dict] = None,
    precomputed_back_desc: Optional[dict] = None,
) -> dict:
    """
    Unified 5-Tier Card Identification & 3-Step Parallel Verification Pipeline:
      - Tier 1 (`OCR >= 190`): Top-tier auto-lock (good to go).
      - Tier 2 (`OCR < 190`): Whole-Image Front+Back confirmation against the candidate's
        reference image(s). If confirmed (`sim >= 0.79`), good to go (`Needs_Review = False`).
      - Tier 3 (Tier 2 failed -> ALWAYS flagged for review): Enhanced Back Re-Read + Front OCR
        re-identification + visual check of the new candidate.
      - Tier 4 (Still unconfirmed -> Flagged): Full-Set Visual Search across already-ID'd batch
        cards, `_My_Collection`, and `Reference_Library`.
      - Tier 5 (Still unconfirmed -> Flagged): CardSightAI API fallback.
      - Parallel Verification: Any card identified as a non-Base parallel (or when subset isn't
        locked to Base) runs the 3-step Parallel Visual Verification & Self-Correction Tournament.
    """
    top_tier_thresh = int(RUNTIME_CONFIG.get("ocr_top_tier_threshold", 185))
    vis_confirm_thresh = float(RUNTIME_CONFIG.get("visual_confirm_threshold", 0.75))

    fx1, fy1, fx2, fy2 = front_box
    scan_front_crop = np.array(front_img.crop((fx1, fy1, max(fx1 + 20, fx2), max(fy1 + 20, fy2))))
    bx1, by1, bx2, by2 = back_box
    scan_back_crop = np.array(back_oriented.crop((bx1, by1, max(bx1 + 20, bx2), max(by1 + 20, by2))))

    scan_front_desc = precomputed_front_desc
    scan_back_desc = precomputed_back_desc
    if scan_front_desc is None and is_neural_embeddings_enabled():
        try:
            eng_id = get_neural_embedding_engine(load_now=True)
            if eng_id is not None and eng_id.is_ready:
                want_pt = bool(load_compute_settings().get("enable_defect_ai", True))
                scan_front_desc = eng_id.extract_descriptor(
                    scan_front_crop, include_color_foil=True, include_patch_tokens=want_pt
                )
        except Exception:
            scan_front_desc = None

    card_geom = _detect_card_format_geometry(front_img, back_oriented, front_box, back_box)
    ag_back_ocr = _analyze_ag_back_ocr_signals(ocr_bundle.get("full_lines", []))

    matched_row, ocr_score, ocr_reasons = match_card_identity(ocr_bundle, active_root_df)

    # Automatic Front Nameplate OCR Assist for Minis & A&G Back cards (whose vintage ad backs often omit bio/team text!)
    if (card_geom["is_mini"] or ag_back_ocr["has_ag_ad_text"] or ag_back_ocr["has_brooklyn_text"]) and (
        matched_row is None or ocr_score < top_tier_thresh
    ):
        front_np_lines = _extract_front_nameplate_ocr_lines(front_img, front_box)
        if front_np_lines:
            aug_bundle = {
                "full_lines": list(ocr_bundle.get("full_lines", [])) + front_np_lines,
                "header_norm": list(ocr_bundle.get("header_norm", [])) + front_np_lines,
                "header_inv": list(ocr_bundle.get("header_inv", [])),
                "corner_zoom": list(ocr_bundle.get("corner_zoom", [])),
                "ricoh_0deg": list(ocr_bundle.get("ricoh_0deg", [])),
            }
            f_row, f_score, f_reasons = match_card_identity(aug_bundle, active_root_df)
            if f_row is not None and f_score > ocr_score:
                matched_row, ocr_score, ocr_reasons = f_row, f_score, f"{f_reasons}+MiniFrontOCR".strip("+")
                ocr_bundle = aug_bundle

    def _unpack_row(row_obj):
        if row_obj is None:
            return clean_locked_set or "2026 Topps Baseball", "0", "Unknown Player", "", "", ["Base"]
        s_n = clean_locked_set or str(row_obj["Set"]).strip()
        cn_s = str(row_obj["Card Number"]).strip().lstrip("#")
        p_n = str(row_obj["Player"]).strip()
        t_n = str(row_obj["Team"]).strip()
        a_s = str(row_obj.get("Attributes", "")).strip()
        pk = (s_n, row_obj["norm_cnum"], row_obj["norm_player"])
        v_subs = list(parallels_map.get(pk) or parallels_map.get((s_n, cn_s, p_n)) or [str(row_obj["Subset"])])
        return s_n, cn_s, p_n, t_n, a_s, v_subs

    set_name, cnum_str, player_name, team_name, attr_str, valid_subsets = _unpack_row(matched_row)
    tier_tag = "T1_OCR_Lock"
    force_needs_review = False
    confirmed_vis_sim = 0.0
    matched_tmpl_front = ""
    matched_tmpl_back = ""
    top3_str = ""
    is_ambig = False

    back_ocr_blob = norm(" ".join(ocr_bundle.get("full_lines", []) + ocr_bundle.get("ricoh_0deg", [])))
    detected_cmp_code = _extract_cmp_code_from_blob(back_ocr_blob)
    learned_cmp_entry = _load_learned_cmp_map().get(detected_cmp_code, {}) if detected_cmp_code else {}
    cmp_hint_sub = str(learned_cmp_entry.get("subset") or "") if (learned_cmp_entry and canonical_set_key(learned_cmp_entry.get("set", "")) == canonical_set_key(set_name)) else ""
    t1_low_vis_flag = float(RUNTIME_CONFIG.get("t1_base_low_vis_flag_threshold", 0.75))

    # ------------------------------------------------------------------
    # TIER 1 vs TIER 2..5 WATERFALL
    # ------------------------------------------------------------------
    if matched_row is not None and ocr_score >= top_tier_thresh:
        tier_tag = "T1_OCR_Lock"
        ocr_reasons = f"{ocr_reasons}+T1_OCR_Lock".strip("+")
        if card_geom["is_mini"] and not clean_locked_subset:
            mini_def_sub = next((s for s in valid_subsets if _is_ordinary_mini_subset(s, set_name)), None) or next(
                (s for s in valid_subsets if _is_unframed_mini_subset(s, set_name, template_catalog)), None
            )
            t1_sub_check = mini_def_sub or (valid_subsets[0] if valid_subsets else "Base")
        elif clean_locked_subset:
            t1_sub_check = clean_locked_subset
        else:
            # Always prefer "Base" for Tier-1 visual confirmation when Base is a valid subset
            # (prevents comparing a Base card against an alphabetical parallel like "Aqua Holo Foil"!)
            base_opt_t1 = next((s for s in (valid_subsets or []) if canonical_subset_key(s, set_name) == "BASE"), None)
            t1_sub_check = base_opt_t1 or (valid_subsets[0] if valid_subsets else "Base")
        if cnum_str != "0":
            t1_ver = _verify_candidate_whole_image(
                scan_front_crop, scan_back_crop, set_name, t1_sub_check, cnum_str,
                template_catalog, reviewed_by_card, batch_visual_memory=batch_visual_memory,
                scan_front_desc=scan_front_desc, scan_back_desc=scan_back_desc,
            )
            if t1_ver.get("has_ref"):
                confirmed_vis_sim = t1_ver["sim"]
                matched_tmpl_front = t1_ver.get("front_rel", "")
                matched_tmpl_back = t1_ver.get("back_rel", "")
    else:
        # TIER 2: Direct Whole-Image Confirmation against reference images of the OCR candidate
        if card_geom["is_mini"] and not clean_locked_subset:
            mini_t2_sub = next((s for s in valid_subsets if _is_ordinary_mini_subset(s, set_name)), None) or next(
                (s for s in valid_subsets if _is_unframed_mini_subset(s, set_name, template_catalog)), None
            )
            target_sub_check = mini_t2_sub or (valid_subsets[0] if valid_subsets else "Base")
        else:
            target_sub_check = clean_locked_subset or (valid_subsets[0] if valid_subsets else "Base")
        t2_ver = (
            _verify_candidate_whole_image(
                scan_front_crop, scan_back_crop, set_name, target_sub_check, cnum_str,
                template_catalog, reviewed_by_card, batch_visual_memory=batch_visual_memory,
                scan_front_desc=scan_front_desc, scan_back_desc=scan_back_desc,
            )
            if (matched_row is not None and cnum_str != "0")
            else {"has_ref": False, "sim": 0.0}
        )

        # ALWAYS preserve the measured visual score & reference paths when a reference image exists (even if < 75%!)
        if t2_ver.get("has_ref"):
            confirmed_vis_sim = float(t2_ver.get("sim", 0.0))
            matched_tmpl_front = t2_ver.get("front_rel", "") or matched_tmpl_front
            matched_tmpl_back = t2_ver.get("back_rel", "") or matched_tmpl_back

        if t2_ver.get("has_ref") and t2_ver.get("sim", 0.0) >= vis_confirm_thresh:
            tier_tag = f"T2_VisualConfirmed({t2_ver['sim']:.2f})"
            ocr_reasons = f"{ocr_reasons}+{tier_tag}".strip("+")
            if log_cb:
                log_cb(f"    🔵 [Tier 2 Visual Confirm] #{cnum_str} {player_name} (OCR {ocr_score} -> Vis {confirmed_vis_sim:.3f} via {t2_ver.get('source','')})")
        else:
            # TIER 3: Failed Tier 2 -> Enhanced Back Re-Read + Front OCR (ALWAYS flagged for review!)
            if log_cb:
                log_cb(
                    f"    🟠 [Tier 3 Re-Read + Front OCR] OCR {ocr_score} failed Tier 2 visual check "
                    f"(sim={t2_ver.get('sim', 0.0):.3f}) on #{cnum_str} {player_name} — running enhanced back + front OCR..."
                )
            force_needs_review = True
            enh_bundle = _extract_enhanced_back_and_front_ocr(front_img, back_oriented, front_box, back_box, ocr_bundle)
            t3_row, t3_score, t3_reasons = match_card_identity(enh_bundle, active_root_df)
            t3_confirmed = False

            if t3_row is not None:
                t3_set, t3_cn, t3_plr, t3_tm, t3_attr, t3_subs = _unpack_row(t3_row)
                t3_sub_check = clean_locked_subset or (t3_subs[0] if t3_subs else "Base")
                t3_ver = _verify_candidate_whole_image(
                    scan_front_crop, scan_back_crop, t3_set, t3_sub_check, t3_cn,
                    template_catalog, reviewed_by_card, batch_visual_memory=batch_visual_memory,
                    scan_front_desc=scan_front_desc, scan_back_desc=scan_back_desc,
                )
                if (t3_ver.get("has_ref") and t3_ver.get("sim", 0.0) >= vis_confirm_thresh) or (
                    t3_score >= top_tier_thresh and (not t3_ver.get("has_ref") or t3_ver.get("sim", 0.0) >= vis_confirm_thresh)
                ):
                    set_name, cnum_str, player_name, team_name, attr_str, valid_subsets = t3_set, t3_cn, t3_plr, t3_tm, t3_attr, t3_subs
                    matched_row = t3_row
                    ocr_score = max(ocr_score, t3_score)
                    if t3_ver.get("has_ref"):
                        confirmed_vis_sim = float(t3_ver.get("sim", 0.0))
                        matched_tmpl_front = t3_ver.get("front_rel", "") or matched_tmpl_front
                        matched_tmpl_back = t3_ver.get("back_rel", "") or matched_tmpl_back
                    tier_tag = f"T3_ReRead+FrontOCR({confirmed_vis_sim:.2f})" if confirmed_vis_sim > 0 else "T3_ReRead+FrontOCR"
                    ocr_reasons = f"{t3_reasons}+{tier_tag}".strip("+")
                    t3_confirmed = True
                    if log_cb:
                        log_cb(f"    ✅ [Tier 3 Recovered] #{cnum_str} {player_name} (OCR {ocr_score}, Vis {confirmed_vis_sim:.3f}) [Flagged for Review]")
                elif t3_score > ocr_score + 15:
                    # Keep improved Tier 3 guess AND its visual score before trying Tier 4
                    set_name, cnum_str, player_name, team_name, attr_str, valid_subsets = t3_set, t3_cn, t3_plr, t3_tm, t3_attr, t3_subs
                    matched_row = t3_row
                    ocr_score = t3_score
                    if t3_ver.get("has_ref"):
                        confirmed_vis_sim = float(t3_ver.get("sim", 0.0))
                        matched_tmpl_front = t3_ver.get("front_rel", "") or matched_tmpl_front
                        matched_tmpl_back = t3_ver.get("back_rel", "") or matched_tmpl_back
                    ocr_reasons = f"{t3_reasons}+T3_Attempt".strip("+")
                elif t3_ver.get("has_ref") and confirmed_vis_sim <= 0.0 and t3_cn == cnum_str:
                    confirmed_vis_sim = float(t3_ver.get("sim", 0.0))
                    matched_tmpl_front = t3_ver.get("front_rel", "") or matched_tmpl_front
                    matched_tmpl_back = t3_ver.get("back_rel", "") or matched_tmpl_back

            # TIER 4: Still Unconfirmed -> Full-Set Visual Search (Batch + _My_Collection + Reference_Library)
            t4_confirmed = False
            if not t3_confirmed:
                t4_res = _search_set_visually(
                    front_img=front_img,
                    front_box=front_box,
                    back_img=back_oriented,
                    back_box=back_box,
                    set_name=set_name,
                    preferred_subset=clean_locked_subset or "Base",
                    active_root_df=active_root_df,
                    parallels_map=parallels_map,
                    template_catalog=template_catalog,
                    reviewed_by_card=reviewed_by_card,
                    batch_visual_memory=batch_visual_memory,
                    log_cb=log_cb,
                    scan_front_desc=scan_front_desc,
                )
                if t4_res is not None:
                    set_name = t4_res["Set"]
                    cnum_str = t4_res["Card_Number"]
                    player_name = t4_res["Player"]
                    team_name = t4_res["Team"]
                    attr_str = t4_res["Attributes"]
                    valid_subsets = t4_res["valid_subsets"]
                    confirmed_vis_sim = t4_res["sim"]
                    matched_tmpl_front = t4_res.get("front_rel", "")
                    matched_tmpl_back = t4_res.get("back_rel", "")
                    tier_tag = f"T4_SetVisual({confirmed_vis_sim:.2f})"
                    ocr_reasons = f"{ocr_reasons}+{tier_tag}".strip("+")
                    t4_confirmed = True

            # TIER 5: Still Unconfirmed -> CardSightAI Fallback
            if not t3_confirmed and not t4_confirmed:
                cs_res = identify_card_with_cardsight_fallback(
                    front_img=front_img,
                    front_box=front_box,
                    root_df=active_root_df,
                    parallels_map=parallels_map,
                    locked_set=clean_locked_set,
                )
                if cs_res is not None:
                    set_name = cs_res["Set"]
                    cnum_str = cs_res["Card_Number"]
                    player_name = cs_res["Player"]
                    team_name = cs_res["Team"]
                    attr_str = cs_res["Attributes"]
                    valid_subsets = cs_res["valid_subsets"]
                    tier_tag = "T5_CardSightAI"
                    ocr_reasons = f"{ocr_reasons}+T5_CardSightAI".strip("+")
                    if cnum_str != "0":
                        t5_ver = _verify_candidate_whole_image(
                            scan_front_crop, scan_back_crop, set_name, clean_locked_subset or (valid_subsets[0] if valid_subsets else "Base"),
                            cnum_str, template_catalog, reviewed_by_card, batch_visual_memory=batch_visual_memory,
                            scan_front_desc=scan_front_desc, scan_back_desc=scan_back_desc,
                        )
                        if t5_ver.get("has_ref"):
                            confirmed_vis_sim = float(t5_ver.get("sim", 0.0))
                            matched_tmpl_front = t5_ver.get("front_rel", "") or matched_tmpl_front
                            matched_tmpl_back = t5_ver.get("back_rel", "") or matched_tmpl_back
                else:
                    tier_tag = "T5_Unconfirmed"
                    is_ambig = True

    # ------------------------------------------------------------------
    # SUBSET / PARALLEL MATCHING & MANDATORY VISUAL VALIDATION TOURNAMENT
    # ------------------------------------------------------------------
    is_locked_base = bool(clean_locked_subset and canonical_subset_key(clean_locked_subset, set_name) == "BASE")
    if is_locked_base:
        chosen_sub = clean_locked_subset
        tmpl_sim = confirmed_vis_sim if confirmed_vis_sim > 0 else 0.0
        top3_str = f"{clean_locked_subset}({tmpl_sim:.3f} [{tier_tag}])" if confirmed_vis_sim > 0 else f"{clean_locked_subset}(Locked - NoRef)"
        if not matched_tmpl_front:
            s_tmpls_lk = template_catalog.get(canonical_set_key(set_name), {})
            n_cn_lk = norm(cnum_str)
            for t_sub_k, t_bkt in s_tmpls_lk.items():
                if isinstance(t_bkt, dict) and canonical_subset_key(t_sub_k, set_name) == "BASE":
                    c_hits = t_bkt.get("cards", {}).get(n_cn_lk) or t_bkt.get("cards", {}).get("_GENERIC") or []
                    if c_hits:
                        fp_lk = c_hits[0].get("front_path") or ""
                        bp_lk = c_hits[0].get("back_path") or ""
                        if fp_lk:
                            matched_tmpl_front = _format_rel_template_ref(Path(fp_lk), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR)
                        if bp_lk:
                            matched_tmpl_back = _format_rel_template_ref(Path(bp_lk), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR)
                        break
    else:
        if clean_locked_subset:
            chosen_sub = clean_locked_subset
            tmpl_sim = confirmed_vis_sim if confirmed_vis_sim > 0 else 0.0
            top3_str = f"{clean_locked_subset}(PreSelected)"
        else:
            (
                chosen_sub,
                tmpl_sim,
                top3_str,
                is_ambig_m,
                _,
                _,
                _,
                mf_rel,
                mb_rel,
            ) = match_front_to_templates(
                front_img=front_img,
                front_box=front_box,
                set_name=set_name,
                card_number=cnum_str,
                valid_subsets=valid_subsets,
                ordinary_roots=ordinary_roots,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                reviewed_parallels=reviewed_parallels,
                parallel_heavy_mode=parallel_heavy_mode,
                stamped_print_run=stamped_pr,
                back_img=back_oriented,
                back_box=back_box,
            )
            if is_ambig_m:
                is_ambig = True
            if mf_rel:
                matched_tmpl_front = mf_rel
            if mb_rel:
                matched_tmpl_back = mb_rel

        is_non_base_card = canonical_subset_key(chosen_sub, set_name) != "BASE"
        has_mini_or_ag_subs = any(
            _is_unframed_mini_subset(s, set_name, template_catalog) or _is_ag_back_subset(s) or _is_brooklyn_back_subset(s)
            for s in (valid_subsets or [])
        )
        # ALWAYS run the Parallel / Mini / Back Verification Tournament on physical Minis or A&G Back candidates!
        should_run_par_verify = (
            len(valid_subsets) >= 1
            and (
                is_non_base_card
                or (card_geom["is_mini"] and has_mini_or_ag_subs)
                or (has_mini_or_ag_subs and (ag_back_ocr["has_ag_ad_text"] or ag_back_ocr["has_brooklyn_text"]))
            )
        )

        # ONLY look for a stamped serial number when the card is suspected to be a parallel WITH a checklist print run!
        effective_stamped_pr = None
        if should_run_par_verify and print_run_map:
            cand_has_pr = any(
                bool(
                    print_run_map.get((set_name, s_chk, norm(cnum_str)))
                    or print_run_map.get((set_name, s_chk, cnum_str))
                )
                for s_chk in ([chosen_sub] + (valid_subsets if card_geom["is_mini"] else []))
            )
            if cand_has_pr:
                effective_stamped_pr = stamped_pr or extract_stamped_serial_print_run(
                    front_img, ocr_bundle.get("full_lines", []), scan_front_for_stamp=True
                )

        if should_run_par_verify:
            par_res = verify_and_correct_parallel_match(
                front_img=front_img,
                front_box=front_box,
                back_img=back_oriented,
                back_box=back_box,
                set_name=set_name,
                card_number=cnum_str,
                current_subset=chosen_sub,
                valid_subsets=valid_subsets,
                ordinary_roots=ordinary_roots,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                reviewed_parallels=reviewed_parallels,
                parallel_heavy_mode=parallel_heavy_mode,
                back_ocr_blob=back_ocr_blob,
                print_run_map=print_run_map,
                detected_serial_denom=effective_stamped_pr,
                card_attributes=attr_str,
                cmp_hint_subset=cmp_hint_sub,
                scan_front_desc=scan_front_desc,
            )
            chosen_sub = par_res["subset"]
            if par_res["score"] > 0:
                tmpl_sim = par_res["score"]
            elif confirmed_vis_sim > 0 and canonical_subset_key(chosen_sub, set_name) == "BASE":
                tmpl_sim = confirmed_vis_sim
            top3_str = par_res["top3_str"]
            if par_res["front_rel"]:
                matched_tmpl_front = par_res["front_rel"]
            if par_res["back_rel"]:
                matched_tmpl_back = par_res["back_rel"]
            ocr_reasons = f"{ocr_reasons}+{par_res['note']}".strip("+")
            if par_res["is_ambiguous"] and canonical_subset_key(chosen_sub, set_name) != "BASE":
                is_ambig = True
                force_needs_review = True
            elif canonical_subset_key(chosen_sub, set_name) == "BASE" and not force_needs_review:
                is_ambig = False
        else:
            if confirmed_vis_sim > tmpl_sim:
                tmpl_sim = confirmed_vis_sim
            # T1_OCR_Lock Base Guard: do NOT flag high-confidence (>=185 OCR) Base locks over minor template margins
            if tier_tag == "T1_OCR_Lock" and canonical_subset_key(chosen_sub, set_name) == "BASE" and not force_needs_review:
                is_ambig = False

    # Evaluate final Visual Confidence threshold (< 75%) ONCE against the final chosen subset's actual visual score
    if canonical_subset_key(chosen_sub, set_name) == "BASE" and confirmed_vis_sim > tmpl_sim:
        tmpl_sim = confirmed_vis_sim
    if tier_tag == "T1_OCR_Lock":
        if 0.0 < tmpl_sim < t1_low_vis_flag:
            force_needs_review = True
            if "T1_LowVisWarn" not in ocr_reasons:
                ocr_reasons = f"{ocr_reasons}+T1_LowVisWarn({tmpl_sim:.2f})"
        elif canonical_subset_key(chosen_sub, set_name) == "BASE" and not is_ambig:
            force_needs_review = False

    needs_review = bool(force_needs_review or is_ambig or cnum_str == "0" or player_name == "Unknown Player")

    # Annotate physical card format (Mini vs Std) in OCR_Signals for clear inspection in Batch Review & Deep-Dive
    fmt_tag = f"Fmt({card_geom['format_label']})"
    if fmt_tag not in ocr_reasons:
        ocr_reasons = f"{ocr_reasons}+{fmt_tag}".strip("+")

    # Auto-learn CMP code mapping on confident locks
    if detected_cmp_code and not needs_review and set_name and chosen_sub:
        _record_learned_cmp_code(detected_cmp_code, set_name, chosen_sub)

    # Store high-confidence ID'd cards in batch_visual_memory so duplicate copies & Tier 4 resolve in <2ms!
    if batch_visual_memory is not None and not needs_review and cnum_str != "0" and player_name != "Unknown Player":
        mem_key = (canonical_set_key(set_name), canonical_subset_key(chosen_sub, set_name), norm(cnum_str))
        if mem_key not in batch_visual_memory:
            batch_visual_memory[mem_key] = {
                "subset": chosen_sub,
                "front_vec": _compute_visual_feature_vector(front_img, front_box),
                "back_vec": _compute_visual_feature_vector(back_oriented, back_box),
                "front_rgb": cv2.resize(scan_front_crop, (256, 356), interpolation=cv2.INTER_AREA),
                "back_rgb": cv2.resize(scan_back_crop, (256, 356), interpolation=cv2.INTER_AREA),
                "front_rel": matched_tmpl_front,
                "back_rel": matched_tmpl_back,
            }

    return {
        "Set": set_name,
        "Card_Number": cnum_str,
        "Player": player_name,
        "Team": team_name,
        "Attributes": attr_str,
        "Subset": chosen_sub,
        "valid_subsets": valid_subsets,
        "OCR_Confidence": ocr_score,
        "OCR_Signals": ocr_reasons,
        "Template_Similarity": tmpl_sim,
        "Top_3_Template_Candidates": top3_str,
        "Matched_Template_Front": matched_tmpl_front,
        "Matched_Template_Back": matched_tmpl_back,
        "Needs_Review": needs_review,
        "Tier_Tag": tier_tag,
        "front_patch_tokens": scan_front_desc.get("patch_tokens") if isinstance(scan_front_desc, dict) else None,
    }


def _format_rel_template_ref(img_path: Optional[Path], templates_dir: Path, reviewed_dir: Path) -> str:
    if img_path is None:
        return ""
    p = Path(img_path)
    try:
        rel_t = p.relative_to(templates_dir)
        return rel_t.as_posix()
    except Exception:
        pass
    try:
        rel_r = p.relative_to(reviewed_dir)
        return f"_cards/{rel_r.as_posix()}"
    except Exception:
        return str(p)


_MEM_TEMPLATE_CACHE = None
_LAZY_VEC_CACHE: dict[str, Optional[np.ndarray]] = {}


def _get_lazy_visual_feature_vector(img_path_str: str) -> Optional[np.ndarray]:
    """Lazily computes & caches an image's whole-card visual feature vector on first comparison."""
    p_str = str(img_path_str or "").strip()
    if not p_str:
        return None
    if p_str in _LAZY_VEC_CACHE:
        return _LAZY_VEC_CACHE[p_str]
    p_obj = Path(p_str)
    if not p_obj.exists():
        _LAZY_VEC_CACHE[p_str] = None
        return None
    try:
        with Image.open(p_obj) as im:
            vec = _compute_visual_feature_vector(im.convert("RGB"))
        if len(_LAZY_VEC_CACHE) > 2500:
            _LAZY_VEC_CACHE.clear()
        _LAZY_VEC_CACHE[p_str] = vec
        return vec
    except Exception:
        _LAZY_VEC_CACHE[p_str] = None
        return None


def index_set_templates_and_reviewed_cards(
    templates_dir: Path = REFERENCE_TEMPLATES_DIR,
    reviewed_dir: Path = REVIEWED_CARDS_DIR,
    force_rebuild: bool = False,
    locked_set: Optional[str] = None,
    lazy_vectors: bool = True,
    log_cb: Optional[Callable[[str], None]] = None,
) -> tuple[dict, dict, dict]:
    """
    Ultra-fast Reference Library & Collection Template Indexer:
      - With `lazy_vectors=True` (default), indexes ONLY filenames/paths (0 Image.open() calls at startup),
        completing across 50,000+ images in < 0.5 seconds! Visual vectors are computed lazily on demand
        inside `match_front_to_templates()` ONLY for the narrowed candidate card's valid subsets.
      - When `locked_set` is specified, scopes directory scanning to that single set (~10ms).
    """
    global _MEM_TEMPLATE_CACHE
    ensure_directories()
    locked_key = canonical_set_key(locked_set) if locked_set else ""

    if not locked_key and not force_rebuild and _MEM_TEMPLATE_CACHE is not None:
        return _MEM_TEMPLATE_CACHE

    if not locked_key and not force_rebuild and FEATURE_CACHE_FILE.exists():
        try:
            with open(FEATURE_CACHE_FILE, "rb") as f:
                cached = pickle.load(f)
            if isinstance(cached, dict) and cached.get("schema") == "v24_lazy" and isinstance(cached.get("data"), tuple):
                _MEM_TEMPLATE_CACHE = cached["data"]
                return _MEM_TEMPLATE_CACHE
            if isinstance(cached, tuple) and len(cached) == 3:
                _MEM_TEMPLATE_CACHE = cached
                return _MEM_TEMPLATE_CACHE
        except Exception:
            pass

    t0 = time.time()
    template_catalog: dict[str, dict[str, dict]] = defaultdict(dict)
    reviewed_by_card: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    reviewed_parallels: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    indexed_tmpl_files = 0
    indexed_rev_files = 0

    if Path(templates_dir).exists():
        set_dirs = [
            d for d in Path(templates_dir).iterdir()
            if d.is_dir() and d.name.lower() not in ("logs", "reports", ".verified_backups", "_my_collection", "unprocessed_cards", "reference_library")
        ]
        if locked_key:
            set_dirs = [d for d in set_dirs if canonical_set_key(d.name.replace("_", " ")) == locked_key]

        tot_sdirs = len(set_dirs)
        for sd_idx, set_sub in enumerate(set_dirs, 1):
            pair_buckets: dict[tuple[str, str, str], dict] = defaultdict(dict)
            for img_p in set_sub.glob("*.jpg"):
                indexed_tmpl_files += 1
                parsed = parse_unified_card_filename(img_p.name)
                if parsed is not None:
                    s_name = parsed["set"]
                    sub_raw = parsed["subset"]
                    cnum_raw = parsed["card_number"]
                    id_tag = parsed["id_tag"]
                    side_c = parsed["side"]
                else:
                    m_leg = _LEGACY_TMPL_FILENAME_RE.match(img_p.name)
                    if not m_leg:
                        continue
                    s_name = m_leg.group("set").replace("_", " ").strip()
                    sub_raw = m_leg.group("subset").replace("_", " ").strip() or "Base"
                    cnum_raw = ""
                    id_tag = m_leg.group("cid")
                    side_c = "B" if m_leg.group("side").upper().startswith("B") else "F"

                s_key = canonical_set_key(s_name or set_sub.name.replace("_", " "))
                n_cnum = norm(cnum_raw)
                b_key = (s_key, sub_raw, f"{n_cnum}_{id_tag}")
                pair_buckets[b_key]["s_key"] = s_key
                pair_buckets[b_key]["sub_raw"] = sub_raw
                pair_buckets[b_key]["n_cnum"] = n_cnum
                if side_c == "F":
                    pair_buckets[b_key]["front_path"] = img_p
                elif side_c == "B":
                    pair_buckets[b_key]["back_path"] = img_p

            for _, b_info in pair_buckets.items():
                f_path = b_info.get("front_path")
                b_path = b_info.get("back_path")
                if f_path is None and b_path is None:
                    continue
                s_key = b_info["s_key"]
                sub_raw = b_info["sub_raw"]
                n_cnum = b_info["n_cnum"]

                f_vec = None
                b_vec = None
                if not lazy_vectors:
                    try:
                        if f_path is not None and f_path.exists():
                            with Image.open(f_path) as im_f:
                                f_vec = _compute_visual_feature_vector(im_f.convert("RGB"))
                        if b_path is not None and b_path.exists():
                            with Image.open(b_path) as im_b:
                                b_vec = _compute_visual_feature_vector(im_b.convert("RGB"))
                    except Exception:
                        continue

                sub_bucket = template_catalog[s_key].setdefault(
                    sub_raw,
                    {"front_vecs": [], "back_vecs": [], "cards": defaultdict(list)},
                )
                if f_vec is not None and len(sub_bucket["front_vecs"]) < 16:
                    sub_bucket["front_vecs"].append(f_vec)
                if b_vec is not None and len(sub_bucket["back_vecs"]) < 16:
                    sub_bucket["back_vecs"].append(b_vec)

                card_rec = {
                    "front_path": str(f_path) if f_path else "",
                    "back_path": str(b_path) if b_path else "",
                    "front_vec": f_vec,
                    "back_vec": b_vec,
                }
                if n_cnum:
                    sub_bucket["cards"][n_cnum].append(card_rec)
                if len(sub_bucket["cards"]["_GENERIC"]) < 6 and f_path is not None:
                    sub_bucket["cards"]["_GENERIC"].append(card_rec)
            if log_cb and (tot_sdirs <= 20 or sd_idx % 5 == 0 or sd_idx == tot_sdirs):
                log_cb(f"  [{sd_idx}/{tot_sdirs}] Indexed '{set_sub.name}' ({len(pair_buckets):,} card image pairs)")

    if Path(reviewed_dir).exists():
        rev_dirs = [d for d in Path(reviewed_dir).iterdir() if d.is_dir()]
        if locked_key:
            rev_dirs = [d for d in rev_dirs if canonical_set_key(d.name.replace("_", " ")) == locked_key]

        rev_buckets: dict[tuple[str, str, str, str], dict] = defaultdict(dict)
        for r_dir in rev_dirs:
            for img_p in r_dir.glob("*.jpg"):
                indexed_rev_files += 1
                parsed = parse_unified_card_filename(img_p.name)
                if not parsed or parsed["side"] not in ("F", "B"):
                    continue
                s_key = canonical_set_key(parsed["set"])
                sub_clean = parsed["subset"]
                n_cnum = norm(parsed["card_number"])
                id_tag = parsed["id_tag"]
                rk = (s_key, sub_clean, n_cnum, id_tag)
                rev_buckets[rk]["s_key"] = s_key
                rev_buckets[rk]["sub_clean"] = sub_clean
                rev_buckets[rk]["n_cnum"] = n_cnum
                if parsed["side"] == "F":
                    rev_buckets[rk]["front_path"] = img_p
                else:
                    rev_buckets[rk]["back_path"] = img_p

        for _, r_info in rev_buckets.items():
            f_path = r_info.get("front_path")
            if f_path is None:
                continue
            b_path = r_info.get("back_path")
            s_key = r_info["s_key"]
            sub_clean = r_info["sub_clean"]
            n_cnum = r_info["n_cnum"]

            f_vec = None
            b_vec = None
            if not lazy_vectors:
                try:
                    with Image.open(f_path) as im_f:
                        f_vec = _compute_visual_feature_vector(im_f.convert("RGB"))
                    if b_path is not None and b_path.exists():
                        with Image.open(b_path) as im_b:
                            b_vec = _compute_visual_feature_vector(im_b.convert("RGB"))
                except Exception:
                    continue

            reviewed_by_card[(s_key, n_cnum)].append((
                sub_clean,
                f_vec,
                b_vec,
                str(f_path),
                str(b_path) if b_path else "",
            ))
            if len(reviewed_parallels[s_key][sub_clean]) < 8:
                reviewed_parallels[s_key][sub_clean].append({
                    "front_vec": f_vec,
                    "back_vec": b_vec,
                    "front_path": str(f_path),
                    "back_path": str(b_path) if b_path else "",
                })

    clean_tmpl_cat = {}
    for sk, subs_dict in template_catalog.items():
        clean_tmpl_cat[sk] = {}
        for sub_k, b_val in subs_dict.items():
            clean_tmpl_cat[sk][sub_k] = {
                "front_vecs": b_val["front_vecs"],
                "back_vecs": b_val["back_vecs"],
                "cards": dict(b_val["cards"]),
            }

    out_tuple = (
        clean_tmpl_cat,
        dict(reviewed_by_card),
        {k: dict(v) for k, v in reviewed_parallels.items()},
    )
    if log_cb:
        log_cb(
            f"  🗂️ Indexed {indexed_tmpl_files:,} Reference Library + {indexed_rev_files:,} Collection image paths "
            f"in {time.time() - t0:.2f}s (lazy on-demand vectors)."
        )

    if not locked_key:
        _MEM_TEMPLATE_CACHE = out_tuple
        try:
            def _dump_feat_cache(tmp_p: Path):
                with open(tmp_p, "wb") as f:
                    pickle.dump({"schema": "v24_lazy", "data": out_tuple}, f, protocol=pickle.HIGHEST_PROTOCOL)
            atomic_write_bytes(FEATURE_CACHE_FILE, _dump_feat_cache)
        except Exception:
            pass

    return out_tuple


def match_front_to_templates(
    front_img: Image.Image,
    front_box: tuple[int, int, int, int],
    set_name: str,
    card_number: str,
    valid_subsets: list[str],
    ordinary_roots: set[str],
    template_catalog: dict,
    reviewed_by_card: dict,
    reviewed_parallels: dict,
    parallel_heavy_mode: bool = False,
    cmp_hint_subset: Optional[str] = None,
    stamped_print_run: Optional[str] = None,
    back_img: Optional[Image.Image] = None,
    back_box: Optional[tuple[int, int, int, int]] = None,
) -> tuple[str, float, str, bool, float, float, str, str, str]:
    if not valid_subsets:
        return "Base", 0.90, "Base(0.900)", False, 0.90, 0.20, "DefaultBase", "", ""

    if cmp_hint_subset and cmp_hint_subset in valid_subsets and not parallel_heavy_mode:
        return cmp_hint_subset, 0.92, f"{cmp_hint_subset}(0.920)", False, 0.92, 0.15, "CMP_Hint", "", ""

    fx1, fy1, fx2, fy2 = front_box
    scan_front_crop = np.array(front_img.crop((fx1, fy1, max(fx1 + 20, fx2), max(fy1 + 20, fy2))))
    q_front_vec = _compute_visual_feature_vector(front_img, front_box)

    scan_back_crop = None
    q_back_vec = None
    if back_img is not None:
        if back_box is not None:
            bx1, by1, bx2, by2 = back_box
            scan_back_crop = np.array(back_img.crop((bx1, by1, max(bx1 + 20, bx2), max(by1 + 20, by2))))
        else:
            scan_back_crop = np.array(back_img)
        q_back_vec = _compute_visual_feature_vector(back_img, back_box)

    s_key = canonical_set_key(set_name)
    n_cnum = norm(card_number)

    set_tmpls = template_catalog.get(s_key, {})
    set_rev_pars = reviewed_parallels.get(s_key, {})
    exact_card_revs = reviewed_by_card.get((s_key, n_cnum), [])

    cfg_base_prior = float(RUNTIME_CONFIG.get("base_prior_bonus", 0.065))
    cfg_ord_prior = float(RUNTIME_CONFIG.get("insert_ordinary_prior_bonus", 0.045))
    base_prior = min(0.020, cfg_base_prior * 0.35) if parallel_heavy_mode else cfg_base_prior
    ord_prior = min(0.015, cfg_ord_prior * 0.35) if parallel_heavy_mode else cfg_ord_prior

    stage1_candidates: list[dict] = []
    for sub_cand in valid_subsets:
        sub_canon = canonical_subset_key(sub_cand, set_name)
        is_back_diff = any(bk in sub_canon for bk in _BACK_DIFFERENTIATED_KEYWORDS)
        exact_pairs: list[dict] = []
        subset_exemplars: list[dict] = []
        src_lbl = "Prior"

        for t_sub, t_bucket in set_tmpls.items():
            if not isinstance(t_bucket, dict):
                continue
            if canonical_subset_key(t_sub, set_name) == sub_canon:
                c_list = t_bucket.get("cards", {}).get(n_cnum, [])
                if c_list:
                    exact_pairs.extend(c_list)
                    src_lbl = "Set_Library_Exact"
                for g_rec in t_bucket.get("cards", {}).get("_GENERIC", []):
                    subset_exemplars.append(g_rec)
                for fv in t_bucket.get("front_vecs", []):
                    subset_exemplars.append({"front_vec": fv, "back_vec": None, "front_path": "", "back_path": ""})

        for r_item in exact_card_revs:
            r_sub = r_item[0]
            if canonical_subset_key(r_sub, set_name) == sub_canon:
                r_fvec = r_item[1]
                r_bvec = r_item[2] if len(r_item) >= 3 else None
                r_fp = r_item[3] if len(r_item) >= 4 else ""
                r_bp = r_item[4] if len(r_item) >= 5 else ""
                exact_pairs.append({
                    "front_vec": r_fvec,
                    "back_vec": r_bvec,
                    "front_path": r_fp,
                    "back_path": r_bp,
                })
                if src_lbl == "Prior":
                    src_lbl = "_Cards_Exact"

        if not exact_pairs and not subset_exemplars:
            for p_sub, p_list in set_rev_pars.items():
                if canonical_subset_key(p_sub, set_name) == sub_canon:
                    for p_item in p_list:
                        if isinstance(p_item, dict):
                            subset_exemplars.append(p_item)
                        else:
                            subset_exemplars.append({"front_vec": p_item, "back_vec": None, "front_path": "", "back_path": ""})
                    if src_lbl == "Prior":
                        src_lbl = "Subset_Exemplar"

        pool_to_score = exact_pairs if exact_pairs else subset_exemplars[:8]
        best_s1 = 0.72
        best_pair_rec = pool_to_score[0] if pool_to_score else {"front_path": "", "back_path": ""}

        for cand_rec in pool_to_score:
            fv = cand_rec.get("front_vec")
            if fv is None and cand_rec.get("front_path"):
                fv = _get_lazy_visual_feature_vector(cand_rec["front_path"])
            bv = cand_rec.get("back_vec")
            if bv is None and q_back_vec is not None and cand_rec.get("back_path"):
                bv = _get_lazy_visual_feature_vector(cand_rec["back_path"])
            f_sim = float(np.dot(q_front_vec, fv)) if fv is not None else 0.72
            if q_back_vec is not None and bv is not None:
                b_sim = float(np.dot(q_back_vec, bv))
                comb = (0.45 * f_sim + 0.55 * b_sim) if is_back_diff else (0.65 * f_sim + 0.35 * b_sim)
            else:
                comb = f_sim
            if comb > best_s1:
                best_s1 = comb
                best_pair_rec = cand_rec

        stage1_candidates.append({
            "sub_cand": sub_cand,
            "sub_canon": sub_canon,
            "is_back_diff": is_back_diff,
            "has_exact_image": bool(exact_pairs),
            "stage1_sim": best_s1,
            "pair_rec": best_pair_rec,
            "src_lbl": src_lbl,
        })

    stage1_candidates.sort(key=lambda x: (1 if x["has_exact_image"] else 0, x["stage1_sim"]), reverse=True)

    card_geom_s1 = _detect_card_format_geometry(front_img, back_img, front_box, back_box)
    fmt_mismatch_pen = float(RUNTIME_CONFIG.get("mini_format_mismatch_penalty", -0.35))
    mini_base_prior = float(RUNTIME_CONFIG.get("mini_base_prior_bonus", 0.055))
    ag_back_wt = float(RUNTIME_CONFIG.get("ag_back_visual_weight", 0.78))

    _s1_back_crop = None
    if back_img is not None:
        if back_box is not None:
            _bx1, _by1, _bx2, _by2 = back_box
            _s1_back_crop = np.array(back_img.crop((_bx1, _by1, max(_bx1 + 20, _bx2), max(_by1 + 20, _by2))))
        else:
            _s1_back_crop = np.array(back_img)

    has_canvas_cand = any(_is_canvas_subset(it["sub_cand"]) for it in stage1_candidates)
    canvas_weave_s1 = _measure_canvas_weave_score(scan_front_crop) if has_canvas_cand else 0.0
    canvas_min_weave_s1 = float(RUNTIME_CONFIG.get("canvas_min_weave_score", 0.48))
    has_ag_or_mini_back_cand = any(
        _is_ag_back_subset(it["sub_cand"]) or _is_brooklyn_back_subset(it["sub_cand"]) or _is_no_number_subset(it["sub_cand"])
        for it in stage1_candidates
    )

    final_scored: list[dict] = []
    for rank_i, item in enumerate(stage1_candidates):
        sub_fmt_s1 = _classify_subset_physical_format(item["sub_cand"], set_name=set_name, template_catalog=template_catalog)
        is_mini_sub_s1 = (sub_fmt_s1 == "MINI")
        sub_cand = item["sub_cand"]
        pair_rec = item["pair_rec"]
        fp_str = str(pair_rec.get("front_path") or "")
        bp_str = str(pair_rec.get("back_path") or "")

        front_whole_sim = item["stage1_sim"]
        back_whole_sim = None
        used_stage2 = False

        is_base_cand = (item["sub_canon"] == "BASE")
        must_eval_s2 = (
            is_base_cand
            or item["has_exact_image"]
            or rank_i < 8
            or (card_geom_s1["is_mini"] and is_mini_sub_s1)
            or (has_ag_or_mini_back_cand and (item.get("is_back_diff") or _is_ordinary_mini_subset(item["sub_cand"], set_name)))
        )
        if must_eval_s2 and fp_str and Path(fp_str).exists():
            try:
                with Image.open(fp_str) as t_fim:
                    t_f_arr = np.array(t_fim.convert("RGB"))
                front_whole_sim = _compute_single_side_whole_image_similarity(scan_front_crop, t_f_arr)
                used_stage2 = True
            except Exception:
                pass

        if used_stage2 and scan_back_crop is not None and bp_str and Path(bp_str).exists():
            try:
                with Image.open(bp_str) as t_bim:
                    t_b_arr = np.array(t_bim.convert("RGB"))
                back_whole_sim = _compute_single_side_whole_image_similarity(scan_back_crop, t_b_arr)
            except Exception:
                back_whole_sim = None

        if back_whole_sim is not None:
            raw_sim = (
                0.45 * front_whole_sim + 0.55 * back_whole_sim
                if item["is_back_diff"]
                else 0.65 * front_whole_sim + 0.35 * back_whole_sim
            )
            score_detail = f"F:{front_whole_sim:.2f}|B:{back_whole_sim:.2f}"
        else:
            raw_sim = front_whole_sim
            score_detail = f"F:{front_whole_sim:.2f}"

        if has_ag_or_mini_back_cand and _s1_back_crop is not None and (item.get("is_back_diff") or (card_geom_s1["is_mini"] and is_mini_sub_s1)):
            _s1_set_tmpls = template_catalog.get(canonical_set_key(set_name), {})
            _s1_ex_bps = []
            for _ts_k, _tb_k in _s1_set_tmpls.items():
                if isinstance(_tb_k, dict) and canonical_subset_key(_ts_k, set_name) == item["sub_canon"]:
                    for _cl in (_tb_k.get("cards") or {}).values():
                        if _cl and _cl[0].get("back_path"):
                            _s1_ex_bps.append(_cl[0]["back_path"])
                        if len(_s1_ex_bps) >= 6:
                            break
            _s1_b_sim = _compute_subset_group_back_similarity(_s1_back_crop, _s1_ex_bps, max_samples=6)
            if _s1_b_sim is not None:
                raw_sim = (1.0 - ag_back_wt) * raw_sim + ag_back_wt * _s1_b_sim

        bonus = 0.0
        if card_geom_s1["is_mini"]:
            if not is_mini_sub_s1:
                bonus += fmt_mismatch_pen
            elif _is_ordinary_mini_subset(sub_cand, set_name):
                bonus += mini_base_prior
        elif card_geom_s1["is_standard"]:
            if is_mini_sub_s1:
                bonus += fmt_mismatch_pen
            elif sub_cand.upper() in ("BASE", "BASE SET"):
                bonus += base_prior
            elif sub_cand in ordinary_roots:
                bonus += ord_prior
        else:
            if sub_cand.upper() in ("BASE", "BASE SET"):
                bonus = base_prior
            elif sub_cand in ordinary_roots:
                bonus = ord_prior

        if _is_canvas_subset(sub_cand) and canvas_weave_s1 < canvas_min_weave_s1:
            bonus -= 0.28

        adj_score = raw_sim + bonus
        final_scored.append({
            "adj_score": adj_score,
            "raw_sim": raw_sim,
            "sub_cand": sub_cand,
            "src_lbl": f"{item['src_lbl']}_2Stage" if used_stage2 else item["src_lbl"],
            "score_detail": score_detail,
            "front_rel": _format_rel_template_ref(Path(fp_str), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR) if fp_str else "",
            "back_rel": _format_rel_template_ref(Path(bp_str), REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR) if bp_str else "",
        })

    final_scored.sort(key=lambda x: x["adj_score"], reverse=True)
    winner = final_scored[0]
    runner_adj = final_scored[1]["adj_score"] if len(final_scored) > 1 else (winner["adj_score"] - 0.15)
    margin = winner["adj_score"] - runner_adj

    top3_str = " | ".join(
        f"{x['sub_cand']}({x['adj_score']:.3f} [{x['score_detail']}])"
        for x in final_scored[:3]
    )
    min_conf = float(RUNTIME_CONFIG.get("min_template_confidence", 0.72))
    min_marg = float(RUNTIME_CONFIG.get("min_margin_over_runner_up", 0.015))
    is_ambiguous = (winner["raw_sim"] < min_conf) or (margin < min_marg and len(final_scored) > 1)

    return (
        winner["sub_cand"],
        round(winner["raw_sim"], 4),
        top3_str,
        is_ambiguous,
        round(winner["raw_sim"], 4),
        round(margin, 4),
        winner["src_lbl"],
        winner["front_rel"],
        winner["back_rel"],
    )


def identify_card_with_cardsight_fallback(
    front_img: Image.Image,
    front_box: tuple[int, int, int, int],
    root_df: pd.DataFrame,
    parallels_map: dict,
    locked_set: str = "",
) -> Optional[dict]:
    if not RUNTIME_CONFIG.get("enable_cardsight_fallback", True) or not CARDSIGHT_API_KEY:
        return None
    if root_df is None or root_df.empty:
        return None

    try:
        fx1, fy1, fx2, fy2 = front_box
        crop = front_img.crop((fx1, fy1, max(fx1 + 40, fx2), max(fy1 + 40, fy2)))
        crop.thumbnail((900, 1250), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=88)
        buf.seek(0)

        endpoint = CARDSIGHT_IDENTIFY_URL
        s_low = str(locked_set or "").lower()
        for sp_key, sp_url in CARDSIGHT_SPORT_ENDPOINTS.items():
            if sp_key in s_low:
                endpoint = sp_url
                break

        resp = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {CARDSIGHT_API_KEY}"},
            files={"image": ("card_front.jpg", buf, "image/jpeg")},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        payload = resp.json() if resp.content else {}
        detections = payload.get("detections") or payload.get("cards") or ([payload] if isinstance(payload, dict) else [])
        if not detections:
            return None

        top_det = detections[0] if isinstance(detections[0], dict) else {}
        card_obj = top_det.get("card") if isinstance(top_det.get("card"), dict) else top_det

        det_cnum = str(card_obj.get("cardNumber") or card_obj.get("number") or "").strip().lstrip("#")
        det_plr = strip_accents(str(card_obj.get("playerName") or card_obj.get("name") or "")).strip()
        det_sub = strip_accents(str(card_obj.get("parallelName") or card_obj.get("insertName") or "Base")).strip() or "Base"

        if not det_cnum and not det_plr:
            return None

        cand_df = root_df[root_df["Set"] == locked_set] if locked_set else root_df
        if det_cnum:
            cnum_hits = cand_df[cand_df["norm_cnum"] == norm(det_cnum)]
            if not cnum_hits.empty:
                cand_df = cnum_hits
        if det_plr:
            n_p = norm(det_plr)
            plr_hits = cand_df[cand_df["norm_player"].apply(lambda x: n_p in x or x in n_p)]
            if not plr_hits.empty:
                cand_df = plr_hits

        if cand_df.empty:
            return None

        matched = cand_df.iloc[0]
        s_final = locked_set or str(matched["Set"]).strip()
        cn_final = str(matched["Card Number"]).strip().lstrip("#")
        plr_final = str(matched["Player"]).strip()
        tm_final = str(matched["Team"]).strip()
        attr_final = str(matched.get("Attributes", "")).strip()

        par_key = (s_final, matched["norm_cnum"], matched["norm_player"])
        valid_subs = list(parallels_map.get(par_key) or [str(matched["Subset"])])
        chosen_sub = next((vs for vs in valid_subs if canonical_subset_key(vs, s_final) == canonical_subset_key(det_sub, s_final)), valid_subs[0])

        return {
            "Set": s_final,
            "Card_Number": cn_final,
            "Player": plr_final,
            "Team": tm_final,
            "Attributes": attr_final,
            "Subset": chosen_sub,
            "valid_subsets": valid_subs,
        }
    except Exception:
        return None


# ==============================================================================
# 5. FULL 1.0 - 10.0 PHYSICAL PSA & BGS PRE-GRADE ESTIMATOR
# ==============================================================================
def estimate_card_pregrade(
    front_img: Image.Image,
    back_img: Image.Image,
    front_box: Optional[tuple[int, int, int, int]] = None,
    back_box: Optional[tuple[int, int, int, int]] = None,
    front_patch_tokens: Optional[np.ndarray] = None,
    back_patch_tokens: Optional[np.ndarray] = None,
) -> dict:
    if front_box is None:
        front_box = detect_physical_card_box(front_img)
    if back_box is None:
        back_box = detect_physical_card_box(back_img)

    fx1, fy1, fx2, fy2 = front_box
    card_crop = front_img.crop((fx1, fy1, max(fx1 + 40, fx2), max(fy1 + 40, fy2)))
    cw, ch = card_crop.size
    arr = np.array(card_crop)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    mid_y1, mid_y2 = int(ch * 0.25), int(ch * 0.75)
    mid_x1, mid_x2 = int(cw * 0.25), int(cw * 0.75)

    grad_x = np.abs(cv2.Sobel(gray[mid_y1:mid_y2, :], cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0)
    grad_y = np.abs(cv2.Sobel(gray[:, mid_x1:mid_x2], cv2.CV_32F, 0, 1, ksize=3)).mean(axis=1)

    left_span = max(4, int(cw * 0.14))
    top_span = max(4, int(ch * 0.14))
    l_idx = int(np.argmax(grad_x[3:left_span])) + 3 if left_span > 4 else int(cw * 0.05)
    r_idx = int(np.argmax(grad_x[::-1][3:left_span])) + 3 if left_span > 4 else int(cw * 0.05)
    t_idx = int(np.argmax(grad_y[3:top_span])) + 3 if top_span > 4 else int(ch * 0.05)
    b_idx = int(np.argmax(grad_y[::-1][3:top_span])) + 3 if top_span > 4 else int(ch * 0.05)

    lr_tot = max(1, l_idx + r_idx)
    tb_tot = max(1, t_idx + b_idx)
    lr_l = int(np.clip(int(round((l_idx / float(lr_tot)) * 100.0)), 32, 68))
    lr_r = 100 - lr_l
    tb_t = int(np.clip(int(round((t_idx / float(tb_tot)) * 100.0)), 32, 68))
    tb_b = 100 - tb_t

    worst_axis = max(lr_l, lr_r, tb_t, tb_b)
    if worst_axis <= 53:
        sub_centering = 10.0
    elif worst_axis <= 55:
        sub_centering = 9.5
    elif worst_axis <= 60:
        sub_centering = 9.0
    elif worst_axis <= 65:
        sub_centering = 8.5
    elif worst_axis <= 70:
        sub_centering = 8.0
    elif worst_axis <= 75:
        sub_centering = 7.0
    else:
        sub_centering = 6.0

    win4_res = None
    try:
        if bool(load_compute_settings().get("enable_defect_ai", True)):
            from Core.surface_defect_engine import inspect_card_surface_through_sleeve
            win4_res = inspect_card_surface_through_sleeve(
                front_img=front_img,
                back_img=back_img,
                front_box=front_box,
                back_box=back_box,
                front_patch_tokens=front_patch_tokens,
                back_patch_tokens=back_patch_tokens,
                enable_onnx_anomaly=True,
                claim_slot=True,
            )
    except Exception:
        win4_res = None

    if isinstance(win4_res, dict):
        sub_corners = float(win4_res["sub_corners"])
        sub_edges = float(win4_res["sub_edges"])
        sub_surface = float(win4_res["sub_surface"])
        edge_callout = ""
        worst_corner_name = "Corner"
        defect_notes_extra = list(win4_res.get("defect_notes") or [])
        artifact_warning = str(win4_res.get("artifact_warning") or "").strip()
    else:
        corner_names = ["Front Top-Left", "Front Top-Right", "Front Bot-Left", "Front Bot-Right"]
        c_span = max(16, int(min(cw, ch) * 0.08))
        c_patches = [
            gray[:c_span, :c_span],
            gray[:c_span, cw - c_span:],
            gray[ch - c_span:, :c_span],
            gray[ch - c_span:, cw - c_span:],
        ]
        corner_scores = []
        worst_corner_name = "Front Top-Left"
        worst_corner_val = 10.0
        for c_lbl, patch in zip(corner_names, c_patches):
            lap_var = float(cv2.Laplacian(patch, cv2.CV_64F).var())
            score_c = 9.5 if lap_var >= 110 else (9.0 if lap_var >= 55 else 8.5)
            corner_scores.append(score_c)
            if score_c < worst_corner_val:
                worst_corner_val = score_c
                worst_corner_name = c_lbl
        sub_corners = round(float(min(corner_scores)), 1)

        edge_strip = max(8, int(min(cw, ch) * 0.025))
        edge_zones = [
            ("Front Top edge", gray[:edge_strip, c_span:cw - c_span]),
            ("Front Bottom edge", gray[ch - edge_strip:, c_span:cw - c_span]),
            ("Front Left edge", gray[c_span:ch - c_span, :edge_strip]),
            ("Front Right edge", gray[c_span:ch - c_span, cw - edge_strip:]),
        ]
        sub_edges = 9.5
        edge_callout = ""
        for e_name, e_patch in edge_zones:
            if e_patch.size == 0:
                continue
            std_e = float(np.std(e_patch))
            if std_e > 48.0 and sub_edges > 8.5:
                sub_edges = 8.5
                edge_callout = f"edge nick/whitening on {e_name} (8.5)"
            elif std_e > 34.0 and sub_edges > 9.0:
                sub_edges = 9.0
                edge_callout = f"minor edge wear on {e_name} (9.0)"

        center_patch = gray[int(ch * 0.18):int(ch * 0.82), int(cw * 0.18):int(cw * 0.82)]
        lap_surf = float(cv2.Laplacian(center_patch, cv2.CV_64F).var()) if center_patch.size else 100.0
        sub_surface = 9.5 if lap_surf >= 45.0 else 9.0
        defect_notes_extra = []
        artifact_warning = ""

    subs = sorted([sub_centering, sub_corners, sub_edges, sub_surface])
    min_sub = subs[0]
    avg_sub = float(np.mean(subs))
    raw_bgs = min(avg_sub, min_sub + 1.0)
    est_bgs = round(np.clip(round(raw_bgs * 2.0) / 2.0, 1.0, 10.0), 1)

    if est_bgs >= 9.5 and sub_centering >= 9.5 and min_sub >= 9.0:
        est_psa = 10.0
    elif est_bgs >= 9.0:
        est_psa = 9.0
    else:
        est_psa = est_bgs

    tier_lbl = "Gem Mint" if est_psa >= 10.0 else ("Mint" if est_psa >= 9.0 else ("NM-MT" if est_psa >= 8.0 else "NM"))
    notes_list = [f"{tier_lbl} tier"]
    if abs(lr_l - 50) >= 6:
        shift_dir = "left (wider right border)" if lr_l < 50 else "right (wider left border)"
        notes_list.append(f"Centering: Front L/R shifted {shift_dir} ({lr_l}/{lr_r})")
    if abs(tb_t - 50) >= 6:
        shift_tb = "up (wider bottom border)" if tb_t < 50 else "down (wider top border)"
        notes_list.append(f"Centering: Front T/B shifted {shift_tb} ({tb_t}/{tb_b})")
    if defect_notes_extra:
        notes_list.extend(defect_notes_extra)
    else:
        if sub_corners < 9.5:
            notes_list.append(f"Corners: {worst_corner_name} corner softness ({sub_corners:.1f})")
        if edge_callout:
            notes_list.append(f"Edges: {edge_callout}")
    if artifact_warning:
        notes_list.append(artifact_warning)
    if len(notes_list) == 1:
        notes_list.append(f"Sharp corners & clean surface ({lr_l}/{lr_r} L/R, {tb_t}/{tb_b} T/B)")

    return {
        "Centering_LR": f"{lr_l}/{lr_r}",
        "Centering_TB": f"{tb_t}/{tb_b}",
        "Sub_Centering": f"{sub_centering:.1f}",
        "Sub_Corners": f"{sub_corners:.1f}",
        "Sub_Edges": f"{sub_edges:.1f}",
        "Sub_Surface": f"{sub_surface:.1f}",
        "Est_Grade": f"{est_bgs:.1f}",
        "Est_PSA": f"{est_psa:.1f}",
        "Est_BGS": f"{est_bgs:.1f}",
        "Grading_Notes": " | ".join(notes_list),
    }


def run_cardsight_api_benchmark(test_image_path: Optional[Path] = None):
    if not CARDSIGHT_API_KEY:
        print("[!] CARDSIGHT_API_KEY environment variable is not set.")
        return
    target = test_image_path or (ARCHIVE_DIR / "tray_scan_test.jpg")
    if not target.exists():
        print(f"[!] Test image not found at {target}")
        return
    try:
        with open(target, "rb") as f:
            resp = requests.post(
                CARDSIGHT_IDENTIFY_URL,
                headers={"Authorization": f"Bearer {CARDSIGHT_API_KEY}"},
                files={"image": f},
                timeout=20,
            )
        print(f"CardSightAI HTTP {resp.status_code}: {resp.text[:500]}")
    except Exception as e:
        print(f"CardSightAI benchmark error: {e}")


# ==============================================================================
# 7. BATCH INGESTION, BATCH RE-IDENTIFICATION & MULTI-GRADER ROI RECALCULATOR
# ==============================================================================
def recalculate_dataframe_multi_grader_roi(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    from Core.market_engine import _load_pricing_strategy_settings, _lookup_comp_row

    out = df.copy()
    if "Valuation_Source" not in out.columns:
        out["Valuation_Source"] = ""
    tiers_data = load_grading_tiers_cache()
    comps_df = load_market_comps_cache()
    comps_by_key = {str(r["Comp_Key"]): r.to_dict() for _, r in comps_df.iterrows() if r.get("Comp_Key")}
    settings = load_market_alert_settings()
    pricing_cfg = _load_pricing_strategy_settings()

    cnum_col = "Card Number" if "Card Number" in out.columns else "Card_Number"
    sub_col = "Subset" if "Subset" in out.columns else "Subset_Parallel"
    pr_col = "Print Run" if "Print Run" in out.columns else "Print_Run"

    for idx, row in out.iterrows():
        r_dict = row.to_dict()
        comp_rec = _lookup_comp_row(
            comps_by_key,
            r_dict.get("Set", ""),
            r_dict.get(sub_col, "Base"),
            r_dict.get(cnum_col, ""),
            r_dict.get("Player", ""),
            print_run=r_dict.get(pr_col, ""),
        )
        roi_res = compute_tier_aware_roi_and_recommendation(
            r_dict,
            comp_row=comp_rec,
            tiers_data=tiers_data,
            min_grade_net_gain=float(settings.get("min_grade_net_gain", 15.0)),
            min_grade_roi_pct=float(settings.get("min_grade_roi_pct", 35.0)),
            pricing_cfg=pricing_cfg,
        )
        for k, v in roi_res.items():
            out.at[idx, k] = v

    return out


def process_single_batch(
    batch_name: str,
    source_folder: Path,
    pdf_files: list[Path],
    root_df: pd.DataFrame,
    parallels_map: dict,
    ordinary_roots: set,
    print_run_map: dict,
    template_catalog: dict,
    reviewed_by_card: dict,
    reviewed_parallels: dict,
    parallel_heavy_mode: bool = False,
    default_raw_price: float = 1.00,
    locked_set: Optional[str] = None,
    locked_subset: Optional[str] = None,
    auto_split_flatbed: bool = True,
    flatbed_flip_mode: str = "auto",
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> tuple[Path, pd.DataFrame]:
    ensure_directories()
    if auto_split_flatbed:
        pdf_files, split_created = expand_flatbed_pdfs_in_batch_folder(
            source_folder, pdf_files=pdf_files, flip_mode=flatbed_flip_mode, log_cb=log_cb
        )
        if split_created > 0 and log_cb:
            log_cb(f"  ✂️ Split multi-card flatbed PDFs into {split_created} individual 2-page card PDF(s).")

    out_dir = BATCHES_DIR / sanitize_filename_part(batch_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    clean_locked_set = str(locked_set or "").strip()
    if clean_locked_set and ("MIXED" in clean_locked_set.upper() or "AUTO-DETECT" in clean_locked_set.upper()):
        clean_locked_set = ""

    clean_locked_subset = str(locked_subset or "").strip()
    if clean_locked_subset and ("AUTO-DETECT" in clean_locked_subset.upper() or "MIXED" in clean_locked_subset.upper()):
        clean_locked_subset = ""

    active_root_df = (
        root_df[root_df["Set"] == clean_locked_set]
        if (clean_locked_set and not root_df.empty and not root_df[root_df["Set"] == clean_locked_set].empty)
        else root_df
    )

    next_sku_i = get_next_sku_int()
    copy_tracker: dict[str, int] = defaultdict(int)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    dpi_val = int(RUNTIME_CONFIG.get("scanner_dpi", 600))
    from Core.market_engine import _load_pricing_strategy_settings
    tiers_data_batch = load_grading_tiers_cache()
    pricing_cfg_batch = _load_pricing_strategy_settings()

    records: list[dict] = []
    batch_visual_memory: dict = {}
    last_written_by_sku: dict[str, dict] = {}
    last_back_angle: Optional[int] = None
    processed_pdf_map: dict[str, str] = {}
    checkpoint_file = out_dir / ".processed_pdfs.json"
    existing_man_path = out_dir / "Batch_Inventory_Manifest.csv"
    original_total_pdfs = len(pdf_files)
    already_done_cnt = 0

    # ==========================================================================
    # MANIFEST RESUME & COMPLETED-BATCH SKIP CHECK
    # Reads existing Batch_Inventory_Manifest.csv + .processed_pdfs.json, skips
    # already-completed batches 100% untouched, and resumes partial batches
    # right where they left off while preserving all existing SKUs & edits!
    # ==========================================================================
    if existing_man_path.exists():
        try:
            existing_df = pd.read_csv(existing_man_path, dtype=str, keep_default_na=False)
            if not existing_df.empty:
                existing_recs = [
                    {col: str(r.get(col, "")) for col in BATCH_MANIFEST_COLUMNS}
                    for _, r in existing_df.iterrows()
                    if str(r.get("SKU", "")).strip()
                ]
                # 1. Load companion .processed_pdfs.json if present
                if checkpoint_file.exists():
                    try:
                        raw_cp = json.loads(checkpoint_file.read_text(encoding="utf-8-sig"))
                        if isinstance(raw_cp, dict):
                            for k_p, v_s in raw_cp.items():
                                processed_pdf_map[str(k_p).strip().lower()] = str(v_s).strip()
                    except Exception:
                        pass

                # 2. Also harvest any Source_PDF / Source_File names recorded in the manifest CSV
                src_pdf_col = next(
                    (c for c in ("Source_PDF", "Source_File", "PDF_File", "Original_PDF") if c in existing_df.columns),
                    None,
                )
                if src_pdf_col:
                    for _, r_e in existing_df.iterrows():
                        sp_n = str(r_e.get(src_pdf_col) or "").strip()
                        sk_n = str(r_e.get("SKU") or "").strip()
                        if sp_n:
                            processed_pdf_map[Path(sp_n).name.lower()] = sk_n

                # 3. Determine which PDFs remain to be processed
                if processed_pdf_map:
                    remaining_pdfs = [p for p in pdf_files if p.name.lower() not in processed_pdf_map]
                else:
                    # Legacy manifest without .processed_pdfs.json or Source_PDF column:
                    # sorted pdf_files were processed in exact sequential order!
                    if len(existing_recs) >= len(pdf_files):
                        remaining_pdfs = []
                        for p_done, rec_done in zip(pdf_files, existing_recs):
                            processed_pdf_map[p_done.name.lower()] = str(rec_done.get("SKU", ""))
                    else:
                        remaining_pdfs = list(pdf_files[len(existing_recs) :])
                        for p_done, rec_done in zip(pdf_files[: len(existing_recs)], existing_recs):
                            processed_pdf_map[p_done.name.lower()] = str(rec_done.get("SKU", ""))

                if len(existing_recs) > 0 and len(remaining_pdfs) == 0:
                    # Batch is 100% completed — write .processed_pdfs.json for instant future skips and return untouched!
                    try:
                        checkpoint_file.write_text(json.dumps(processed_pdf_map, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    if log_cb:
                        log_cb(
                            f"⏭️ [SKIP COMPLETE BATCH] '{batch_name}': All {original_total_pdfs:,} PDF(s) are already processed "
                            f"in Batch_Inventory_Manifest.csv ({len(existing_recs):,} cards). Keeping existing SKUs & edits untouched."
                        )
                    return out_dir, existing_df

                if len(existing_recs) > 0 and len(remaining_pdfs) < len(pdf_files):
                    records = list(existing_recs)
                    already_done_cnt = len(existing_recs)
                    max_existing_sku = 0
                    for rec_e in existing_recs:
                        sk_e = str(rec_e.get("SKU", "")).strip()
                        if sk_e:
                            last_written_by_sku[sk_e] = dict(rec_e)
                            if sk_e.isdigit():
                                max_existing_sku = max(max_existing_sku, int(sk_e))
                        stem_e = build_card_image_stem(
                            rec_e.get("Set", ""),
                            rec_e.get("Subset_Parallel", "Base"),
                            str(rec_e.get("Card_Number", "")).lstrip("#"),
                            rec_e.get("Player", ""),
                        )
                        if stem_e not in copy_tracker:
                            copy_tracker[stem_e] = get_existing_copy_count(
                                rec_e.get("Set", ""),
                                rec_e.get("Subset_Parallel", "Base"),
                                str(rec_e.get("Card_Number", "")).lstrip("#"),
                                rec_e.get("Player", ""),
                            )
                        copy_tracker[stem_e] += 1

                    if max_existing_sku >= next_sku_i:
                        next_sku_i = max_existing_sku + 1
                    pdf_files = remaining_pdfs
                    if log_cb:
                        log_cb(
                            f"♻️ [RESUME BATCH] '{batch_name}': Preserved {already_done_cnt:,} already-processed card(s) "
                            f"from manifest — resuming {len(pdf_files):,} remaining PDF(s) (next SKU {next_sku_i:07d})!"
                        )
        except Exception as resume_err:
            if log_cb:
                log_cb(f"  ⚠️ Manifest resume check note on '{batch_name}': {resume_err}")

    total_pdfs = len(pdf_files)

    def _flush_batch_manifest_preserving_user_edits(force_final: bool = False):
        """
        Atomically flushes `Batch_Inventory_Manifest.csv` AND `.processed_pdfs.json` while
        preserving ANY edits made concurrently in Guided Batch Review (prevents live edit reversions!).
        """
        man_path = out_dir / "Batch_Inventory_Manifest.csv"
        if man_path.exists() and last_written_by_sku:
            try:
                disk_df = pd.read_csv(man_path, dtype=str, keep_default_na=False)
                disk_by_sku = {str(r["SKU"]).strip(): r.to_dict() for _, r in disk_df.iterrows() if str(r.get("SKU", "")).strip()}
                for r_i, mem_rec in enumerate(records):
                    sku_k = str(mem_rec.get("SKU", "")).strip()
                    prev_w = last_written_by_sku.get(sku_k)
                    disk_r = disk_by_sku.get(sku_k)
                    if prev_w is not None and disk_r is not None:
                        changed_externally = any(
                            str(disk_r.get(fld, "")).strip() != str(prev_w.get(fld, "")).strip()
                            for fld in ("Set", "Subset_Parallel", "Card_Number", "Player", "Team", "Print_Run", "Needs_Review", "Front_File", "Back_File")
                        )
                        if changed_externally:
                            records[r_i] = {col: str(disk_r.get(col, "")) for col in BATCH_MANIFEST_COLUMNS}
            except Exception:
                pass

        try:
            live_df = pd.DataFrame(records, columns=BATCH_MANIFEST_COLUMNS)
            tmp_man = out_dir / "Batch_Inventory_Manifest.csv.tmp"
            live_df.to_csv(tmp_man, index=False, encoding="utf-8-sig")
            os.replace(str(tmp_man), str(man_path))
            for r_obj in records:
                sku_k = str(r_obj.get("SKU", "")).strip()
                if sku_k:
                    last_written_by_sku[sku_k] = dict(r_obj)
            if processed_pdf_map:
                tmp_cp = checkpoint_file.with_suffix(".json.tmp")
                tmp_cp.write_text(json.dumps(processed_pdf_map, indent=2), encoding="utf-8")
                os.replace(str(tmp_cp), str(checkpoint_file))
        except Exception:
            if force_final:
                pd.DataFrame(records, columns=BATCH_MANIFEST_COLUMNS).to_csv(man_path, index=False, encoding="utf-8-sig")

    io_pool = ThreadPoolExecutor(max_workers=2)
    pending_save_futures = []

    try:
      for idx, pdf_p in enumerate(pdf_files, 1):
        front_img = render_pdf_page_to_pil(pdf_p, 0, dpi=dpi_val)
        back_img = render_pdf_page_to_pil(pdf_p, 1, dpi=dpi_val) or front_img
        if front_img is None:
            continue

        back_oriented, ocr_bundle = extract_back_ocr_and_orient(back_img, preferred_angle=last_back_angle)
        back_rot_ang = int(ocr_bundle.get("back_rotation_angle", 0) or 0)
        last_back_angle = back_rot_ang

        # Quick initial OCR guess to guide reference-aware horizontal/upside-down front rotation BEFORE visual confirmation!
        pre_row, _, _ = match_card_identity(ocr_bundle, active_root_df)
        pre_set = clean_locked_set or (str(pre_row["Set"]).strip() if pre_row is not None else "")
        pre_cnum = str(pre_row["Card Number"]).strip().lstrip("#") if pre_row is not None else ""
        pre_sub = clean_locked_subset or (str(pre_row["Subset"]).strip() if pre_row is not None else "Base")

        front_img, front_rot_ang, front_rot_rsn = orient_front_card_image(
            front_img=front_img,
            back_rotation_angle=back_rot_ang,
            set_name=pre_set,
            subset_name=pre_sub,
            card_number=pre_cnum,
            template_catalog=template_catalog,
            reviewed_by_card=reviewed_by_card,
        )
        if log_cb and (back_rot_ang != 0 or front_rot_ang != 0):
            rot_bits = []
            if front_rot_ang != 0:
                rot_bits.append(f"Front ↻{front_rot_ang}° ({front_rot_rsn})")
            if back_rot_ang != 0:
                rot_bits.append(f"Back ↻{back_rot_ang}° ({'Landscape' if back_oriented.width > back_oriented.height else 'Portrait'})")
            log_cb(f"    ↻ [Auto-Orient {pdf_p.name}] {' | '.join(rot_bits)}")

        front_box = detect_physical_card_box(front_img)
        back_box = detect_physical_card_box(back_oriented)

        id_res = identify_and_verify_card_pipeline(
            front_img=front_img,
            back_oriented=back_oriented,
            front_box=front_box,
            back_box=back_box,
            ocr_bundle=ocr_bundle,
            active_root_df=active_root_df,
            parallels_map=parallels_map,
            ordinary_roots=ordinary_roots,
            template_catalog=template_catalog,
            reviewed_by_card=reviewed_by_card,
            reviewed_parallels=reviewed_parallels,
            clean_locked_set=clean_locked_set,
            clean_locked_subset=clean_locked_subset,
            parallel_heavy_mode=parallel_heavy_mode,
            stamped_pr=None,
            batch_visual_memory=batch_visual_memory,
            log_cb=log_cb,
            print_run_map=print_run_map,
        )

        # If Tier 3/4/5 resolved a different card than pre_row, verify front orientation against the final card's reference!
        if id_res["Card_Number"] != pre_cnum and id_res["Card_Number"] != "0":
            front_img_2, front_rot_2, front_rsn_2 = orient_front_card_image(
                front_img=front_img,
                back_rotation_angle=0,
                set_name=id_res["Set"],
                subset_name=id_res["Subset"],
                card_number=id_res["Card_Number"],
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
            )
            if front_rot_2 != 0:
                front_img = front_img_2
                front_box = detect_physical_card_box(front_img)
                if log_cb:
                    log_cb(f"    ↻ [Post-ID Front Orient] Rotated #{id_res['Card_Number']} {id_res['Player']} ↻{front_rot_2}° ({front_rsn_2})")

        set_name = id_res["Set"]
        cnum_str = id_res["Card_Number"]
        player_name = id_res["Player"]
        team_name = id_res["Team"]
        attr_str = id_res["Attributes"]
        chosen_sub = id_res["Subset"]
        valid_subsets = id_res["valid_subsets"]
        ocr_score = id_res["OCR_Confidence"]
        ocr_reasons = id_res["OCR_Signals"]
        tmpl_sim = id_res["Template_Similarity"]
        top3_str = id_res["Top_3_Template_Candidates"]
        matched_tmpl_front = id_res["Matched_Template_Front"]
        matched_tmpl_back = id_res["Matched_Template_Back"]
        needs_rev = id_res["Needs_Review"]

        # Never assign a Print_Run to Base or any unnumbered subset; use checklist print run only for numbered parallels
        checklist_pr_val = (
            print_run_map.get((set_name, chosen_sub, norm(cnum_str)))
            or print_run_map.get((set_name, chosen_sub, cnum_str))
            or ""
        )
        pr_val = "" if (canonical_subset_key(chosen_sub, set_name) == "BASE" or not checklist_pr_val) else checklist_pr_val

        sku_str = f"{next_sku_i:07d}"
        next_sku_i += 1

        stem = build_card_image_stem(set_name, chosen_sub, cnum_str, player_name)
        if stem not in copy_tracker:
            copy_tracker[stem] = get_existing_copy_count(set_name, chosen_sub, cnum_str, player_name)
        copy_tracker[stem] += 1
        copy_num = copy_tracker[stem]

        f_fname, b_fname, c_fname = build_card_image_filenames(
            set_name, chosen_sub, cnum_str, player_name, sku_str
        )

        grade_info = estimate_card_pregrade(
            front_img,
            back_oriented,
            front_box=front_box,
            back_box=back_box,
            front_patch_tokens=id_res.get("front_patch_tokens"),
        )

        # Pipeline JPEG encoding & 8-Corner sheet saving in background threads so disk I/O overlaps with the next PDF's OCR
        def _save_card_images_bg(f_im, b_im, fb, bb, fp, bp, cp):
            try:
                f_im.save(fp, format="JPEG", quality=94)
                b_im.save(bp, format="JPEG", quality=94)
                c_im = build_corners_inspection_sheet(f_im, b_im, front_box=fb, back_box=bb)
                c_im.save(cp, format="JPEG", quality=92)
            except Exception:
                pass

        pending_save_futures.append(
            io_pool.submit(_save_card_images_bg, front_img, back_oriented, front_box, back_box, out_dir / f_fname, out_dir / b_fname, out_dir / c_fname)
        )
        if len(pending_save_futures) > 6:
            try:
                pending_save_futures.pop(0).result(timeout=30)
            except Exception:
                pass

        base_rec = {
            "Scan_Order": str(idx),
            "SKU": sku_str,
            "Status": "In Stock",
            "Hold_Tag": "For Sale",
            "Needs_Review": "True" if needs_rev else "False",
            "Set": set_name,
            "Subset_Parallel": chosen_sub,
            "Card_Number": f"#{cnum_str}",
            "Player": player_name,
            "Team": team_name,
            "Print_Run": format_print_run(pr_val),
            "Attributes": attr_str,
            "Copy_Number": str(copy_num),
            **grade_info,
            "Raw_Price": "",
            "Valuation_Source": "Uncomped",
            "Min_Sale_Price": "",
            "Rec_Sale_Price": "",
            "PSA_9_Price": "",
            "BGS_9_5_Price": "",
            "PSA_10_Price": "",
            "Est_Graded_PSA": "",
            "Est_Graded_BGS": "",
            "EV_PSA": "",
            "EV_BGS": "",
            "Best_Grader": "RAW",
            "Max_Net_Gain": "",
            "Recommended_Action": "LIST RAW",
            "Template_Similarity": f"{tmpl_sim:.3f}",
            "Top_3_Template_Candidates": top3_str,
            "Valid_Checklist_Subsets": " | ".join(valid_subsets[:20]),
            "OCR_Confidence": str(ocr_score),
            "OCR_Signals": ocr_reasons,
            "Front_File": f_fname,
            "Back_File": b_fname,
            "Corners_File": c_fname,
            "Matched_Template_Front": matched_tmpl_front,
            "Matched_Template_Back": matched_tmpl_back,
            "Source_Batch": batch_name,
            "Source_PDF": pdf_p.name,
            "Date_Added": now_str,
            "Label_Printed": "False",
            "Manual_Override": "",
        }
        roi_info = compute_tier_aware_roi_and_recommendation(
            base_rec,
            tiers_data=tiers_data_batch,
            pricing_cfg=pricing_cfg_batch,
        )
        base_rec.update(roi_info)
        records.append(base_rec)
        processed_pdf_map[pdf_p.name.lower()] = sku_str

        # Stream cards live to Uncommitted Batches on every card (<=600 PDFs) or every 2 cards (>600 PDFs)
        if total_pdfs <= 600 or idx % 2 == 0 or idx == total_pdfs:
            for fut in pending_save_futures:
                try:
                    fut.result(timeout=30)
                except Exception:
                    pass
            pending_save_futures.clear()
            _flush_batch_manifest_preserving_user_edits(force_final=False)

        if progress_callback is not None:
            progress_callback(already_done_cnt + idx, max(original_total_pdfs, already_done_cnt + total_pdfs), base_rec)
    finally:
      for fut in pending_save_futures:
          try:
              fut.result(timeout=30)
          except Exception:
              pass
      io_pool.shutdown(wait=True)
      _flush_border_sig_cache(force=True)
      flush_neural_embeddings_if_dirty()

    _flush_batch_manifest_preserving_user_edits(force_final=True)
    manifest_df = pd.DataFrame(records, columns=BATCH_MANIFEST_COLUMNS)
    return out_dir, manifest_df


def reidentify_batch_cards(
    batch_dir: Path,
    target_mode: str = "flagged_and_suspect",
    selected_skus: Optional[list[str]] = None,
    locked_set: Optional[str] = None,
    locked_subset: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> tuple[pd.DataFrame, int, int]:
    batch_dir = Path(batch_dir)
    manifest_path = batch_dir / "Batch_Inventory_Manifest.csv"
    if not manifest_path.exists():
        if log_cb:
            log_cb(f"⚠️ Manifest not found in {batch_dir}")
        return pd.DataFrame(), 0, 0

    df = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    if df.empty:
        if log_cb:
            log_cb(f"⚠️ Batch '{batch_dir.name}' has 0 cards.")
        return df, 0, 0

    if log_cb:
        log_cb(f"🧠 Re-Identify Batch '{batch_dir.name}' ({len(df):,} cards total | mode={target_mode})...")
        log_cb("📚 Loading checklist & lazy-indexing Reference Library + Collection images...")

    root_df, parallels_map, ordinary_roots, print_run_map = load_master_checklist(CHECKLIST_PATH, force_reload=False)
    template_catalog, reviewed_by_card, reviewed_parallels = index_set_templates_and_reviewed_cards(
        REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR, lazy_vectors=True, log_cb=log_cb
    )

    clean_locked_set = str(locked_set or "").strip()
    if clean_locked_set and ("MIXED" in clean_locked_set.upper() or "AUTO-DETECT" in clean_locked_set.upper()):
        clean_locked_set = ""

    clean_locked_subset = str(locked_subset or "").strip()
    if clean_locked_subset and ("AUTO-DETECT" in clean_locked_subset.upper() or "MIXED" in clean_locked_subset.upper()):
        clean_locked_subset = ""

    active_root_df = (
        root_df[root_df["Set"] == clean_locked_set]
        if (clean_locked_set and not root_df.empty and not root_df[root_df["Set"] == clean_locked_set].empty)
        else root_df
    )

    top_tier_thresh = int(RUNTIME_CONFIG.get("ocr_top_tier_threshold", 185))
    sel_set = set(selected_skus or [])
    rows_to_check = []
    batch_visual_memory: dict = {}

    for r_idx, row in df.iterrows():
        sku_s = str(row.get("SKU", "")).strip()
        ocr_conf = int(parse_price_val(row.get("OCR_Confidence", "0"), 0) or 0)
        needs_rev_r = str(row.get("Needs_Review", "")).lower() == "true"

        if target_mode == "selected_skus":
            if sku_s in sel_set:
                rows_to_check.append(r_idx)
        elif target_mode == "all":
            rows_to_check.append(r_idx)
        else:
            ocr_sig = str(row.get("OCR_Signals", ""))
            plr_s = str(row.get("Player", ""))
            is_body_only = ("BodyPlayer" in ocr_sig and "Card#" not in ocr_sig and "Insert#" not in ocr_sig)
            is_placeholder = "CHECKLIST TEAM CARD" in plr_s.upper() or plr_s == "Unknown Player"
            if needs_rev_r or ocr_conf < top_tier_thresh or is_body_only or is_placeholder:
                rows_to_check.append(r_idx)
            else:
                # Seed batch_visual_memory from already top-tier (>=190) cards in this batch for instant Tier 2/4 confirmation!
                fp_m = batch_dir / str(row.get("Front_File", "")).strip()
                bp_m = batch_dir / str(row.get("Back_File", "")).strip()
                if fp_m.exists():
                    s_m = str(row.get("Set", "")).strip()
                    sub_m = str(row.get("Subset_Parallel", "Base")).strip() or "Base"
                    cn_m = str(row.get("Card_Number", "")).strip().lstrip("#")
                    mk = (canonical_set_key(s_m), canonical_subset_key(sub_m, s_m), norm(cn_m))
                    if mk not in batch_visual_memory and len(batch_visual_memory) < 400:
                        try:
                            with Image.open(fp_m) as fim_m:
                                frgb = fim_m.convert("RGB")
                                fb_m = detect_physical_card_box(frgb)
                                fcrop_m = np.array(frgb.crop((fb_m[0], fb_m[1], max(fb_m[0] + 20, fb_m[2]), max(fb_m[1] + 20, fb_m[3]))))
                                fvec_m = _compute_visual_feature_vector(frgb, fb_m)
                            bvec_m, bcrop_m = None, None
                            if bp_m.exists():
                                with Image.open(bp_m) as bim_m:
                                    brgb = bim_m.convert("RGB")
                                    bb_m = detect_physical_card_box(brgb)
                                    bcrop_m = cv2.resize(np.array(brgb.crop((bb_m[0], bb_m[1], max(bb_m[0] + 20, bb_m[2]), max(bb_m[1] + 20, bb_m[3])))), (256, 356), interpolation=cv2.INTER_AREA)
                                    bvec_m = _compute_visual_feature_vector(brgb, bb_m)
                            batch_visual_memory[mk] = {
                                "subset": sub_m,
                                "front_vec": fvec_m,
                                "back_vec": bvec_m,
                                "front_rgb": cv2.resize(fcrop_m, (256, 356), interpolation=cv2.INTER_AREA),
                                "back_rgb": bcrop_m,
                                "front_rel": str(row.get("Matched_Template_Front", "")),
                                "back_rel": str(row.get("Matched_Template_Back", "")),
                            }
                        except Exception:
                            pass

    total_targets = max(1, len(rows_to_check))
    changed_count = 0
    if log_cb:
        log_cb(
            f"🔎 Selected {len(rows_to_check):,} card(s) to re-identify (seeded {len(batch_visual_memory):,} high-confidence visual templates from this batch)."
        )

    pre_front_descs: dict[str, dict] = {}
    if rows_to_check and is_neural_embeddings_enabled():
        reid_front_paths = [
            batch_dir / str(df.loc[ri].get("Front_File", "")).strip()
            for ri in rows_to_check
            if str(df.loc[ri].get("Front_File", "")).strip()
        ]
        if reid_front_paths:
            pre_front_descs = precompute_batch_image_descriptors(reid_front_paths, require_multiregion=True, auto_persist=False)

    for pos_i, r_idx in enumerate(rows_to_check, 1):
        row = df.loc[r_idx]
        f_path = batch_dir / str(row.get("Front_File", "")).strip()
        b_path = batch_dir / str(row.get("Back_File", "")).strip()
        if not b_path.exists() or not f_path.exists():
            continue

        try:
            f_img = Image.open(f_path).convert("RGB")
            b_img = Image.open(b_path).convert("RGB")
            b_oriented, ocr_bundle = extract_back_ocr_and_orient(b_img, force_all_angles=True)
            back_rot_ang = int(ocr_bundle.get("back_rotation_angle", 0) or 0)
            b_sc0 = ocr_bundle.get("back_score_0")
            b_best = float(ocr_bundle.get("back_best_score", 0.0) or 0.0)
            if back_rot_ang != 0 and b_sc0 is not None and (b_best < float(b_sc0) + 8.0):
                b_oriented = b_img
                back_rot_ang = 0

            row_set_hint = clean_locked_set or str(row.get("Set", "")).strip()
            row_root_df = (
                active_root_df[active_root_df["Set"] == row_set_hint]
                if (row_set_hint and not active_root_df[active_root_df["Set"] == row_set_hint].empty)
                else active_root_df
            )

            pre_row, _, _ = match_card_identity(ocr_bundle, row_root_df)
            pre_set = row_set_hint or (str(pre_row["Set"]).strip() if pre_row is not None else "")
            pre_cnum = str(pre_row["Card Number"]).strip().lstrip("#") if pre_row is not None else str(row.get("Card_Number", "")).strip().lstrip("#")
            pre_sub = clean_locked_subset or (str(pre_row["Subset"]).strip() if pre_row is not None else str(row.get("Subset_Parallel", "Base")).strip())

            f_img, front_rot_ang, _ = orient_front_card_image(
                front_img=f_img,
                back_rotation_angle=back_rot_ang,
                set_name=pre_set,
                subset_name=pre_sub,
                card_number=pre_cnum,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                exclude_paths={str(f_path.resolve())},
            )

            f_box = detect_physical_card_box(f_img)
            b_box = detect_physical_card_box(b_oriented)

            f_desc_pre = pre_front_descs.get(str(f_path.resolve()).lower()) if pre_front_descs and front_rot_ang == 0 else None
            id_res = identify_and_verify_card_pipeline(
                front_img=f_img,
                back_oriented=b_oriented,
                front_box=f_box,
                back_box=b_box,
                ocr_bundle=ocr_bundle,
                active_root_df=row_root_df,
                parallels_map=parallels_map,
                ordinary_roots=ordinary_roots,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                reviewed_parallels=reviewed_parallels,
                clean_locked_set=row_set_hint,
                clean_locked_subset=clean_locked_subset,
                stamped_pr=None,
                batch_visual_memory=batch_visual_memory,
                log_cb=log_cb,
                print_run_map=print_run_map,
                precomputed_front_desc=f_desc_pre,
            )

            new_set = id_res["Set"]
            new_cnum = id_res["Card_Number"]
            new_plr = id_res["Player"]
            new_tm = id_res["Team"]
            new_attr = id_res["Attributes"]
            chosen_sub = id_res["Subset"]
            old_cnum = str(row.get("Card_Number", "")).strip().lstrip("#")
            old_plr = str(row.get("Player", "")).strip()

            if new_cnum != pre_cnum and new_cnum != "0":
                f_img_2, front_rot_2, _ = orient_front_card_image(
                    front_img=f_img,
                    back_rotation_angle=0,
                    set_name=new_set,
                    subset_name=chosen_sub,
                    card_number=new_cnum,
                    template_catalog=template_catalog,
                    reviewed_by_card=reviewed_by_card,
                    exclude_paths={str(f_path.resolve())},
                )
                if front_rot_2 != 0:
                    f_img = f_img_2
                    front_rot_ang = (front_rot_ang + front_rot_2) % 360
                    f_box = detect_physical_card_box(f_img)

            # Save corrected rotations & regenerate 8-corner sheet + regrade whenever orientation changed
            if front_rot_ang != 0:
                f_img.save(f_path, format="JPEG", quality=94)
            if back_rot_ang != 0:
                b_oriented.save(b_path, format="JPEG", quality=94)
            if front_rot_ang != 0 or back_rot_ang != 0:
                c_fname_r = str(row.get("Corners_File", "")).strip() or (f_path.name[:-6] + "_C.jpg")
                c_im_r = build_corners_inspection_sheet(f_img, b_oriented, front_box=f_box, back_box=b_box)
                c_im_r.save(batch_dir / c_fname_r, format="JPEG", quality=92)
                g_upd_r = estimate_card_pregrade(f_img, b_oriented, front_box=f_box, back_box=b_box)
                for gk, gv in g_upd_r.items():
                    df.at[r_idx, gk] = gv
                if log_cb:
                    log_cb(f"    ↻ [Auto-Rotated SKU {row.get('SKU','')}] Front ↻{front_rot_ang}° | Back ↻{back_rot_ang}° -> Updated Corners & Grade")

            chk_pr_reid = (
                print_run_map.get((new_set, chosen_sub, norm(new_cnum)))
                or print_run_map.get((new_set, chosen_sub, new_cnum))
                or ""
            )
            pr_val = "" if (canonical_subset_key(chosen_sub, new_set) == "BASE" or not chk_pr_reid) else chk_pr_reid

            if new_cnum != old_cnum or new_plr != old_plr:
                changed_count += 1

            df.at[r_idx, "Set"] = new_set
            df.at[r_idx, "Card_Number"] = f"#{new_cnum}"
            df.at[r_idx, "Player"] = new_plr
            df.at[r_idx, "Team"] = new_tm
            df.at[r_idx, "Subset_Parallel"] = chosen_sub
            df.at[r_idx, "Print_Run"] = format_print_run(pr_val)
            df.at[r_idx, "Attributes"] = new_attr
            df.at[r_idx, "OCR_Confidence"] = str(id_res["OCR_Confidence"])
            df.at[r_idx, "OCR_Signals"] = id_res["OCR_Signals"]
            df.at[r_idx, "Template_Similarity"] = f"{id_res['Template_Similarity']:.3f}"
            df.at[r_idx, "Top_3_Template_Candidates"] = id_res["Top_3_Template_Candidates"]
            df.at[r_idx, "Matched_Template_Front"] = id_res["Matched_Template_Front"]
            df.at[r_idx, "Matched_Template_Back"] = id_res["Matched_Template_Back"]
            df.at[r_idx, "Needs_Review"] = "True" if id_res["Needs_Review"] else "False"
        except Exception:
            pass

        if progress_callback is not None:
            progress_callback(pos_i, total_targets, df.loc[r_idx].to_dict())

    flush_neural_embeddings_if_dirty()
    df, _, renamed_cnt = apply_manifest_overrides_and_rename(batch_dir, df_override=df)
    return df, changed_count, renamed_cnt


def regrade_batch_cards(
    batch_dir: Path,
    regenerate_corner_sheets: bool = True,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> tuple[pd.DataFrame, int]:
    batch_dir = Path(batch_dir)
    manifest_path = batch_dir / "Batch_Inventory_Manifest.csv"
    if not manifest_path.exists():
        if log_cb:
            log_cb(f"⚠️ Batch manifest not found: {manifest_path}")
        return pd.DataFrame(), 0

    df = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    total_rows = max(1, len(df))
    regraded_count = 0
    if log_cb:
        log_cb(f"🔄 Starting Batch Pre-Grading on '{batch_dir.name}' ({len(df):,} cards | corner_sheets={regenerate_corner_sheets})...")

    for pos_i, (idx, row) in enumerate(df.iterrows(), 1):
        f_p = batch_dir / str(row.get("Front_File", "")).strip()
        b_p = batch_dir / str(row.get("Back_File", "")).strip()
        c_p = batch_dir / str(row.get("Corners_File", "")).strip()
        if f_p.exists():
            try:
                f_im = Image.open(f_p).convert("RGB")
                b_im = Image.open(b_p).convert("RGB") if b_p.exists() else f_im
                f_box = detect_physical_card_box(f_im)
                b_box = detect_physical_card_box(b_im)
                g_res = estimate_card_pregrade(f_im, b_im, front_box=f_box, back_box=b_box)
                for k, v in g_res.items():
                    df.at[idx, k] = v
                if regenerate_corner_sheets and c_p.name:
                    c_im = build_corners_inspection_sheet(f_im, b_im, front_box=f_box, back_box=b_box)
                    c_im.save(c_p, format="JPEG", quality=92)
                regraded_count += 1
            except Exception:
                pass
        if progress_callback is not None:
            progress_callback(pos_i, total_rows, df.loc[idx].to_dict())

    df = recalculate_dataframe_multi_grader_roi(df)
    df.to_csv(manifest_path, index=False, encoding="utf-8-sig")
    return df, regraded_count


def regrade_inventory_cards(
    inv_df: Optional[pd.DataFrame] = None,
    regenerate_corner_sheets: bool = True,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> tuple[pd.DataFrame, int]:
    if inv_df is None:
        inv_df = load_inventory_df()
    if inv_df.empty:
        if log_cb:
            log_cb("⚠️ Master Inventory is empty — nothing to re-grade.")
        return inv_df, 0

    out = inv_df.copy()
    total = len(out)
    regraded_count = 0
    if log_cb:
        log_cb(f"🔄 Starting Full Inventory Pre-Grading across {total:,} card(s)...")

    for pos_i, (idx, row) in enumerate(out.iterrows(), 1):
        s_folder = REVIEWED_CARDS_DIR / sanitize_filename_part(str(row.get("Set", "")))
        f_fn = str(row.get("Front_File", "")).strip()
        b_fn = str(row.get("Back_File", "")).strip()
        c_fn = str(row.get("Corners_File", "")).strip()
        f_p = s_folder / f_fn if f_fn else None
        b_p = s_folder / b_fn if b_fn else None
        c_p = s_folder / c_fn if c_fn else None

        if f_p and f_p.exists():
            try:
                f_im = Image.open(f_p).convert("RGB")
                b_im = Image.open(b_p).convert("RGB") if (b_p and b_p.exists()) else f_im
                f_box = detect_physical_card_box(f_im)
                b_box = detect_physical_card_box(b_im)
                g_res = estimate_card_pregrade(f_im, b_im, front_box=f_box, back_box=b_box)
                for k, v in g_res.items():
                    out.at[idx, k] = v
                if regenerate_corner_sheets and c_p:
                    c_im = build_corners_inspection_sheet(f_im, b_im, front_box=f_box, back_box=b_box)
                    c_im.save(c_p, format="JPEG", quality=92)
                regraded_count += 1
            except Exception:
                pass

        if progress_callback is not None:
            progress_callback(pos_i, total, out.loc[idx].to_dict())

    out = recalculate_dataframe_multi_grader_roi(out)
    save_inventory_df(out)
    return out, regraded_count



def reprocess_single_batch_card(
    batch_dir: Path,
    sku: str,
    locked_set: Optional[str] = None,
    locked_subset: Optional[str] = None,
    regrade_too: bool = True,
) -> dict:
    """
    Re-runs OCR, 5-Tier Visual Confirmation, Parallel Self-Correction, and optional Pre-Grading
    on a single physical card SKU inside an uncommitted batch (for Guided Review's Reprocess button).
    """
    batch_dir = Path(batch_dir)
    man_path = batch_dir / "Batch_Inventory_Manifest.csv"
    if not man_path.exists():
        return {"success": False, "error": f"Batch manifest not found: {man_path}"}

    df = pd.read_csv(man_path, dtype=str, keep_default_na=False)
    sku_s = str(sku or "").strip()
    hits = df.index[df["SKU"].astype(str).str.strip() == sku_s].tolist()
    if not hits:
        return {"success": False, "error": f"SKU {sku_s} not found in batch {batch_dir.name}"}

    r_idx = hits[0]
    row = df.loc[r_idx]
    f_path = batch_dir / str(row.get("Front_File", "")).strip()
    b_path = batch_dir / str(row.get("Back_File", "")).strip()
    if not f_path.exists() or not b_path.exists():
        return {"success": False, "error": f"Card images missing on disk for SKU {sku_s}"}

    from Core.config import SET_CHECKLISTS_DIR
    row_set = str(locked_set or row.get("Set", "")).strip()
    chk_p = CHECKLIST_PATH
    if row_set:
        cand_s = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(row_set)}.csv"
        if cand_s.exists():
            chk_p = cand_s

    root_df, parallels_map, ordinary_roots, print_run_map = load_master_checklist(chk_p, force_reload=False)
    template_catalog, reviewed_by_card, reviewed_parallels = index_set_templates_and_reviewed_cards(
        REFERENCE_TEMPLATES_DIR, REVIEWED_CARDS_DIR, locked_set=row_set or None, lazy_vectors=True
    )

    with Image.open(f_path) as fim:
        f_img = fim.convert("RGB")
    with Image.open(b_path) as bim:
        b_img = bim.convert("RGB")

    b_oriented, ocr_bundle = extract_back_ocr_and_orient(b_img, force_all_angles=True)
    back_rot_ang = int(ocr_bundle.get("back_rotation_angle", 0) or 0)
    b_sc0 = ocr_bundle.get("back_score_0")
    b_best = float(ocr_bundle.get("back_best_score", 0.0) or 0.0)
    if back_rot_ang != 0 and b_sc0 is not None and (b_best < float(b_sc0) + 8.0):
        b_oriented = b_img
        back_rot_ang = 0

    active_root = root_df[root_df["Set"] == row_set] if (row_set and not root_df[root_df["Set"] == row_set].empty) else root_df
    pre_row, _, _ = match_card_identity(ocr_bundle, active_root)
    pre_set = row_set or (str(pre_row["Set"]).strip() if pre_row is not None else "")
    pre_cnum = str(pre_row["Card Number"]).strip().lstrip("#") if pre_row is not None else str(row.get("Card_Number", "")).strip().lstrip("#")
    pre_sub = str(locked_subset or (str(pre_row["Subset"]).strip() if pre_row is not None else str(row.get("Subset_Parallel", "Base")).strip())).strip()

    f_img, front_rot_ang, _ = orient_front_card_image(
        front_img=f_img,
        back_rotation_angle=back_rot_ang,
        set_name=pre_set,
        subset_name=pre_sub,
        card_number=pre_cnum,
        template_catalog=template_catalog,
        reviewed_by_card=reviewed_by_card,
        exclude_paths={str(f_path.resolve())},
    )

    f_box = detect_physical_card_box(f_img)
    b_box = detect_physical_card_box(b_oriented)

    id_res = identify_and_verify_card_pipeline(
        front_img=f_img,
        back_oriented=b_oriented,
        front_box=f_box,
        back_box=b_box,
        ocr_bundle=ocr_bundle,
        active_root_df=active_root,
        parallels_map=parallels_map,
        ordinary_roots=ordinary_roots,
        template_catalog=template_catalog,
        reviewed_by_card=reviewed_by_card,
        reviewed_parallels=reviewed_parallels,
        clean_locked_set=row_set,
        clean_locked_subset=str(locked_subset or "").strip(),
        stamped_pr=None,
        print_run_map=print_run_map,
    )

    new_set = id_res["Set"]
    new_cnum = id_res["Card_Number"]
    new_plr = id_res["Player"]
    chosen_sub = id_res["Subset"]

    if new_cnum != pre_cnum and new_cnum != "0":
        f_img_2, front_rot_2, _ = orient_front_card_image(
            front_img=f_img,
            back_rotation_angle=0,
            set_name=new_set,
            subset_name=chosen_sub,
            card_number=new_cnum,
            template_catalog=template_catalog,
            reviewed_by_card=reviewed_by_card,
            exclude_paths={str(f_path.resolve())},
        )
        if front_rot_2 != 0:
            f_img = f_img_2
            front_rot_ang = (front_rot_ang + front_rot_2) % 360
            f_box = detect_physical_card_box(f_img)

    # Persist corrected upright Front & Back images whenever rotation was needed
    if front_rot_ang != 0:
        f_img.save(f_path, format="JPEG", quality=94)
    if back_rot_ang != 0:
        b_oriented.save(b_path, format="JPEG", quality=94)

    chk_pr_single = (
        print_run_map.get((new_set, chosen_sub, norm(new_cnum)))
        or print_run_map.get((new_set, chosen_sub, new_cnum))
        or ""
    )
    pr_val = "" if (canonical_subset_key(chosen_sub, new_set) == "BASE" or not chk_pr_single) else chk_pr_single

    df.at[r_idx, "Set"] = new_set
    df.at[r_idx, "Card_Number"] = f"#{new_cnum}"
    df.at[r_idx, "Player"] = new_plr
    df.at[r_idx, "Team"] = id_res["Team"]
    df.at[r_idx, "Subset_Parallel"] = chosen_sub
    df.at[r_idx, "Print_Run"] = format_print_run(pr_val)
    df.at[r_idx, "Attributes"] = id_res["Attributes"]
    df.at[r_idx, "OCR_Confidence"] = str(id_res["OCR_Confidence"])
    df.at[r_idx, "OCR_Signals"] = id_res["OCR_Signals"]
    df.at[r_idx, "Template_Similarity"] = f"{id_res['Template_Similarity']:.3f}"
    df.at[r_idx, "Top_3_Template_Candidates"] = id_res["Top_3_Template_Candidates"]
    df.at[r_idx, "Matched_Template_Front"] = id_res["Matched_Template_Front"]
    df.at[r_idx, "Matched_Template_Back"] = id_res["Matched_Template_Back"]
    df.at[r_idx, "Needs_Review"] = "True" if id_res["Needs_Review"] else "False"

    if regrade_too or front_rot_ang != 0 or back_rot_ang != 0:
        c_fname_s = str(row.get("Corners_File", "")).strip() or (f_path.name[:-6] + "_C.jpg")
        try:
            c_im_s = build_corners_inspection_sheet(f_img, b_oriented, front_box=f_box, back_box=b_box)
            c_im_s.save(batch_dir / c_fname_s, format="JPEG", quality=92)
        except Exception:
            pass
        g_res = estimate_card_pregrade(
            f_img,
            b_oriented,
            front_box=f_box,
            back_box=b_box,
            front_patch_tokens=id_res.get("front_patch_tokens"),
        )
        for gk, gv in g_res.items():
            df.at[r_idx, gk] = gv

    res_df, _, ren_cnt = apply_manifest_overrides_and_rename(
        batch_dir, df_override=df, target_skus={sku_s}, master_df_override=root_df
    )
    updated_row = res_df[res_df["SKU"].astype(str).str.strip() == sku_s].iloc[0].to_dict()
    _flush_border_sig_cache(force=True)
    return {
        "success": True,
        "sku": sku_s,
        "renamedCount": ren_cnt,
        "card": updated_row,
        "cards": res_df.to_dict(orient="records"),
    }



def reprocess_batch_cards_list(
    batch_dir: Path,
    skus: list[str],
    locked_set: Optional[str] = None,
    locked_subset: Optional[str] = None,
    regrade_too: bool = True,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Parallel-worker entrypoint to reprocess 1 or more specific SKUs inside an uncommitted batch
    with live `[i/total]` progress telemetry and incremental manifest saves.
    """
    batch_dir = Path(batch_dir)
    clean_skus = [str(s).strip() for s in (skus or []) if str(s).strip()]
    if not clean_skus:
        return {"success": False, "error": "No SKUs supplied for batch reprocessing."}

    total = len(clean_skus)
    processed = 0
    last_card: dict = {}
    if log_cb:
        log_cb(f"🔄 Reprocessing {total} card(s) in batch '{batch_dir.name}' (regrade={regrade_too})...")

    for idx_i, sku_s in enumerate(clean_skus, 1):
        res = reprocess_single_batch_card(
            batch_dir=batch_dir,
            sku=sku_s,
            locked_set=locked_set,
            locked_subset=locked_subset,
            regrade_too=regrade_too,
        )
        if res.get("success") and isinstance(res.get("card"), dict):
            processed += 1
            last_card = res["card"]
            if progress_callback is not None:
                progress_callback(idx_i, total, last_card)
        elif log_cb:
            log_cb(f"  [{idx_i}/{total}] ⚠️ Failed reprocessing SKU {sku_s}: {res.get('error', 'Unknown error')}")

    return {
        "success": processed > 0,
        "processedCount": processed,
        "skus": clean_skus,
        "lastCard": last_card,
    }


def _locate_inventory_card_images(row: dict, sku_str: str) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Finds a committed Inventory SKU's Front, Back, and Corners images inside `_My_Collection`."""
    set_folder = REVIEWED_CARDS_DIR / sanitize_filename_part(str(row.get("Set") or "").strip())
    f_name = str(row.get("Front_File") or "").strip()
    b_name = str(row.get("Back_File") or "").strip()
    c_name = str(row.get("Corners_File") or "").strip()

    f_p = (set_folder / f_name) if f_name else None
    b_p = (set_folder / b_name) if b_name else None
    c_p = (set_folder / c_name) if c_name else None

    if f_p is not None and not f_p.exists():
        f_p = None
    if b_p is not None and not b_p.exists():
        b_p = None
    if c_p is not None and not c_p.exists():
        c_p = None

    # Fallback lookup by exact 7-digit SKU suffix anywhere under _My_Collection
    # Matches both unified `_[{sku}]_{F|B|C}.jpg` and legacy `_{sku}_{F|B|C}.jpg` without glob bracket wildcards
    if (f_p is None or b_p is None) and sku_str and REVIEWED_CARDS_DIR.exists():
        sku_up = sku_str.upper()
        for cand in REVIEWED_CARDS_DIR.rglob("*.jpg"):
            n_up = cand.name.upper()
            if f"_[{sku_up}]_" not in n_up and f"_{sku_up}_" not in n_up:
                continue
            if f_p is None and (n_up.endswith(f"_[{sku_up}]_F.JPG") or n_up.endswith(f"_{sku_up}_F.JPG")):
                f_p = cand
            elif b_p is None and (n_up.endswith(f"_[{sku_up}]_B.JPG") or n_up.endswith(f"_{sku_up}_B.JPG")):
                b_p = cand
            elif c_p is None and (n_up.endswith(f"_[{sku_up}]_C.JPG") or n_up.endswith(f"_{sku_up}_C.JPG")):
                c_p = cand
            if f_p is not None and b_p is not None and c_p is not None:
                break
    return f_p, b_p, c_p


def reprocess_inventory_skus(
    skus: list[str],
    locked_set: Optional[str] = None,
    locked_subset: Optional[str] = None,
    regrade_too: bool = True,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Re-scans physical `_My_Collection` Front & Back images for 1 or more Master Inventory SKUs:
      1. Runs 4-angle orientation, 5-Tier OCR + Visual Confirmation, Parallel Self-Correction,
         and optional Pre-Grading + 8-Corner sheet regeneration.
      2. Updates `Inventory.csv` (marking `Label_Printed = False` if any label-visible identity
         field changed), recalculates multi-grader ROI, and renames `_My_Collection` files cleanly.
    """
    from Core.config import SET_CHECKLISTS_DIR
    from Core.database import load_inventory_df, save_inventory_df, sync_inventory_copy_numbers_and_files

    clean_skus = [str(s).strip() for s in (skus or []) if str(s).strip()]
    if not clean_skus:
        return {"success": False, "error": "No SKUs specified for inventory reprocessing."}

    inv_df = load_inventory_df()
    if inv_df.empty:
        return {"success": False, "error": "Master Inventory.csv is empty."}

    prev_df = inv_df.copy()
    inv_df["SKU"] = inv_df["SKU"].astype(str).str.strip()
    target_indices = []
    for s_val in clean_skus:
        hits = inv_df.index[inv_df["SKU"] == s_val].tolist()
        if hits:
            target_indices.append((s_val, hits[0]))

    if not target_indices:
        return {"success": False, "error": f"None of the requested SKU(s) were found in Inventory.csv."}

    # Determine whether all target SKUs share a single Set for fast single-set checklist loading
    involved_sets = {
        str(locked_set or inv_df.at[r_i, "Set"] or "").strip()
        for _, r_i in target_indices
        if str(locked_set or inv_df.at[r_i, "Set"] or "").strip()
    }
    single_set_hint = next(iter(involved_sets)) if len(involved_sets) == 1 else ""
    chk_path = CHECKLIST_PATH
    if single_set_hint:
        cand_s = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(single_set_hint)}.csv"
        if cand_s.exists():
            chk_path = cand_s

    if log_cb:
        log_cb(
            f"🔄 Reprocessing {len(target_indices)} Master Inventory SKU(s) "
            f"(checklist={chk_path.name}, regrade={regrade_too})..."
        )

    root_df, parallels_map, ordinary_roots, print_run_map = load_master_checklist(chk_path, force_reload=False)
    template_catalog, reviewed_by_card, reviewed_parallels = index_set_templates_and_reviewed_cards(
        REFERENCE_TEMPLATES_DIR,
        REVIEWED_CARDS_DIR,
        locked_set=single_set_hint or None,
        lazy_vectors=True,
        log_cb=log_cb,
    )

    total_targets = len(target_indices)
    processed_indices: list[int] = []

    pre_inv_descs: dict[str, dict] = {}
    if target_indices and is_neural_embeddings_enabled():
        inv_front_paths = []
        for sku_s_p, r_idx_p in target_indices:
            fp_p, _, _ = _locate_inventory_card_images(inv_df.loc[r_idx_p].to_dict(), sku_s_p)
            if fp_p is not None and fp_p.exists():
                inv_front_paths.append(fp_p)
        if inv_front_paths:
            pre_inv_descs = precompute_batch_image_descriptors(inv_front_paths, require_multiregion=True, auto_persist=False)

    for pos_i, (sku_s, r_idx) in enumerate(target_indices, 1):
        row_d = inv_df.loc[r_idx].to_dict()
        f_p, b_p, c_p = _locate_inventory_card_images(row_d, sku_s)
        if f_p is None or not f_p.exists():
            if log_cb:
                log_cb(f"  [{pos_i}/{total_targets}] ⚠️ Front image missing on disk for SKU {sku_s}; skipping.")
            continue

        try:
            with Image.open(f_p) as fim:
                f_img = fim.convert("RGB")
            if b_p is not None and b_p.exists():
                with Image.open(b_p) as bim:
                    b_img = bim.convert("RGB")
            else:
                b_img = f_img

            b_oriented, ocr_bundle = extract_back_ocr_and_orient(b_img, force_all_angles=True)
            back_rot_ang = int(ocr_bundle.get("back_rotation_angle", 0) or 0)
            b_sc0 = ocr_bundle.get("back_score_0")
            b_best = float(ocr_bundle.get("back_best_score", 0.0) or 0.0)
            if back_rot_ang != 0 and b_sc0 is not None and (b_best < float(b_sc0) + 8.0):
                b_oriented = b_img
                back_rot_ang = 0

            row_set_hint = str(locked_set or row_d.get("Set") or "").strip()
            active_root = (
                root_df[root_df["Set"] == row_set_hint]
                if (row_set_hint and not root_df[root_df["Set"] == row_set_hint].empty)
                else root_df
            )

            pre_row, _, _ = match_card_identity(ocr_bundle, active_root)
            pre_set = row_set_hint or (str(pre_row["Set"]).strip() if pre_row is not None else "")
            pre_cnum = str(pre_row["Card Number"]).strip().lstrip("#") if pre_row is not None else str(row_d.get("Card Number") or "").strip().lstrip("#")
            pre_sub = str(locked_subset or (str(pre_row["Subset"]).strip() if pre_row is not None else str(row_d.get("Subset") or "Base").strip())).strip()

            f_img_oriented, front_rot_ang, front_rot_rsn = orient_front_card_image(
                front_img=f_img,
                back_rotation_angle=back_rot_ang,
                set_name=pre_set,
                subset_name=pre_sub,
                card_number=pre_cnum,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                exclude_paths={str(f_p.resolve())},
            )
            if front_rot_ang != 0:
                f_img = f_img_oriented
                try:
                    f_img.save(f_p, format="JPEG", quality=94)
                except Exception:
                    pass
            if back_rot_ang != 0 and b_p is not None and b_p.exists():
                try:
                    b_oriented.save(b_p, format="JPEG", quality=94)
                except Exception:
                    pass
            if log_cb and (front_rot_ang != 0 or back_rot_ang != 0):
                log_cb(f"    ↻ [Auto-Orient SKU {sku_s}] Front ↻{front_rot_ang}° ({front_rot_rsn}) | Back ↻{back_rot_ang}°")

            f_box = detect_physical_card_box(f_img)
            b_box = detect_physical_card_box(b_oriented)

            f_desc_inv = pre_inv_descs.get(str(f_p.resolve()).lower()) if pre_inv_descs and front_rot_ang == 0 else None
            id_res = identify_and_verify_card_pipeline(
                front_img=f_img,
                back_oriented=b_oriented,
                front_box=f_box,
                back_box=b_box,
                ocr_bundle=ocr_bundle,
                active_root_df=active_root,
                parallels_map=parallels_map,
                ordinary_roots=ordinary_roots,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                reviewed_parallels=reviewed_parallels,
                clean_locked_set=row_set_hint,
                clean_locked_subset=str(locked_subset or "").strip(),
                stamped_pr=None,
                log_cb=log_cb,
                print_run_map=print_run_map,
                precomputed_front_desc=f_desc_inv,
            )

            new_set = id_res["Set"]
            new_cnum = str(id_res["Card_Number"]).strip().lstrip("#")
            new_plr = id_res["Player"]
            new_tm = id_res["Team"]
            chosen_sub = id_res["Subset"]
            chk_pr = (
                print_run_map.get((new_set, chosen_sub, norm(new_cnum)))
                or print_run_map.get((new_set, chosen_sub, new_cnum))
                or ""
            )
            new_pr = "" if (canonical_subset_key(chosen_sub, new_set) == "BASE" or not chk_pr) else format_print_run(chk_pr)

            label_changed = (
                new_set != str(row_d.get("Set") or "").strip()
                or chosen_sub != str(row_d.get("Subset") or "").strip()
                or new_cnum != str(row_d.get("Card Number") or "").strip().lstrip("#")
                or new_plr != str(row_d.get("Player") or "").strip()
                or new_tm != str(row_d.get("Team") or "").strip()
                or new_pr != str(row_d.get("Print Run") or "").strip()
            )

            inv_df.at[r_idx, "Set"] = new_set
            inv_df.at[r_idx, "Subset"] = chosen_sub
            inv_df.at[r_idx, "Card Number"] = new_cnum
            inv_df.at[r_idx, "Player"] = new_plr
            inv_df.at[r_idx, "Team"] = new_tm
            inv_df.at[r_idx, "Print Run"] = new_pr
            inv_df.at[r_idx, "Attributes"] = id_res["Attributes"]
            inv_df.at[r_idx, "OCR_Confidence"] = str(id_res["OCR_Confidence"])
            inv_df.at[r_idx, "OCR_Signals"] = id_res["OCR_Signals"]
            inv_df.at[r_idx, "Template_Similarity"] = f"{id_res['Template_Similarity']:.3f}"
            inv_df.at[r_idx, "Top_3_Template_Candidates"] = id_res["Top_3_Template_Candidates"]
            inv_df.at[r_idx, "Matched_Template_Front"] = id_res["Matched_Template_Front"]
            inv_df.at[r_idx, "Matched_Template_Back"] = id_res["Matched_Template_Back"]
            inv_df.at[r_idx, "Needs_Review"] = "True" if id_res["Needs_Review"] else "False"
            if label_changed:
                inv_df.at[r_idx, "Label_Printed"] = "False"

            if new_cnum != pre_cnum and new_cnum != "0":
                f_img_2, front_rot_2, front_rsn_2 = orient_front_card_image(
                    front_img=f_img,
                    back_rotation_angle=0,
                    set_name=new_set,
                    subset_name=chosen_sub,
                    card_number=new_cnum,
                    template_catalog=template_catalog,
                    reviewed_by_card=reviewed_by_card,
                    exclude_paths={str(f_p.resolve())},
                )
                if front_rot_2 != 0:
                    f_img = f_img_2
                    front_rot_ang = (front_rot_ang + front_rot_2) % 360
                    try:
                        f_img.save(f_p, format="JPEG", quality=94)
                    except Exception:
                        pass
                    f_box = detect_physical_card_box(f_img)
                    if log_cb:
                        log_cb(f"    ↻ [Post-ID Orient SKU {sku_s}] Front ↻{front_rot_2}° ({front_rsn_2})")

            if regrade_too or front_rot_ang != 0 or back_rot_ang != 0:
                g_res = estimate_card_pregrade(
            f_img,
            b_oriented,
            front_box=f_box,
            back_box=b_box,
            front_patch_tokens=id_res.get("front_patch_tokens"),
        )
                for gk, gv in g_res.items():
                    if gk in inv_df.columns:
                        inv_df.at[r_idx, gk] = gv
                target_c_p = c_p
                if target_c_p is None and f_p.name.upper().endswith("_F.JPG"):
                    target_c_p = f_p.with_name(f_p.name[:-6] + "_C.jpg")
                if target_c_p is not None and target_c_p.parent.exists():
                    try:
                        c_im = build_corners_inspection_sheet(f_img, b_oriented, front_box=f_box, back_box=b_box)
                        c_im.save(target_c_p, format="JPEG", quality=92)
                    except Exception:
                        pass

            processed_indices.append(r_idx)
            if progress_callback is not None:
                progress_callback(pos_i, total_targets, inv_df.loc[r_idx].to_dict())
        except Exception as e:
            if log_cb:
                log_cb(f"  [{pos_i}/{total_targets}] ❌ Error reprocessing SKU {sku_s}: {e}")

    renamed_cnt = 0
    if processed_indices:
        sub_roi = recalculate_dataframe_multi_grader_roi(inv_df.loc[processed_indices].copy())
        for col_c in sub_roi.columns:
            if col_c not in inv_df.columns:
                inv_df[col_c] = ""
            inv_df.loc[processed_indices, col_c] = sub_roi[col_c]
        synced_df, renamed_cnt = sync_inventory_copy_numbers_and_files(inv_df, previous_inv_df=prev_df)
        inv_df = save_inventory_df(synced_df)

    _flush_border_sig_cache(force=True)
    flush_neural_embeddings_if_dirty()
    if log_cb:
        log_cb(f"✅ Reprocessed {len(processed_indices)}/{total_targets} Inventory SKU(s) ({renamed_cnt} _My_Collection file set(s) renamed).")
    return {
        "success": len(processed_indices) > 0,
        "processedCount": len(processed_indices),
        "renamedCount": renamed_cnt,
        "skus": clean_skus,
    }



def fix_card_rotations_and_regrade(
    scope: str = "all",
    set_filter: Optional[str] = None,
    dry_run: bool = False,
    progress_callback: Optional[Callable[[int, int, dict], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Standalone Card Rotation Fixer (DevTools Utility — ZERO Re-Identification):
      - Inspects existing card scans across Master Inventory (`_My_Collection`), Uncommitted Batches,
        or both (`scope in ('all', 'inventory', 'batches')`).
      - Keeps every card's existing identity (`Set`, `Subset`, `Card Number`, `Player`, `Team`,
        `Print Run`, `SKU`, manual prices) 100% untouched.
      - Checks both Back (4-angle OCR geometry) and Front (Reference-guided + Front-OCR geometry,
        excluding the card's own file from references).
      - ONLY on impacted cards where Front or Back actually rotated:
          1. Saves the corrected upright `_F.jpg` and/or `_B.jpg` in-place.
          2. Regenerates the 8-Corner Inspection Sheet (`_C.jpg`).
          3. Re-runs `estimate_card_pregrade()` and recalculates multi-grader ROI (preserving manual prices).
    """
    from Core.config import BATCHES_DIR
    from Core.database import load_inventory_df, save_inventory_df

    clean_scope = str(scope or "all").strip().lower()
    clean_set_filter = str(set_filter or "").strip()
    if clean_set_filter in ("All Sets", "ALL"):
        clean_set_filter = ""

    if log_cb:
        log_cb(
            f"↻ Starting Card Rotation Fixer (scope={clean_scope}, set={clean_set_filter or 'All Sets'}, "
            f"dry_run={dry_run}) — Identity fields will NOT be modified."
        )

    template_catalog, reviewed_by_card, _ = index_set_templates_and_reviewed_cards(
        REFERENCE_TEMPLATES_DIR,
        REVIEWED_CARDS_DIR,
        locked_set=clean_set_filter or None,
        lazy_vectors=True,
        log_cb=log_cb,
    )

    # Collect work units first so overall progress bar & ETA are exact
    inv_df = pd.DataFrame()
    inv_work: list[int] = []
    if clean_scope in ("all", "inventory"):
        inv_df = load_inventory_df()
        if not inv_df.empty:
            for r_idx, row in inv_df.iterrows():
                if clean_set_filter and str(row.get("Set") or "").strip() != clean_set_filter:
                    continue
                inv_work.append(r_idx)

    batch_jobs: list[tuple[Path, Path, pd.DataFrame, list[int]]] = []
    if clean_scope in ("all", "batches") and BATCHES_DIR.exists():
        for b_dir in sorted(BATCHES_DIR.iterdir()):
            if not b_dir.is_dir() or b_dir.name.lower() == "archive" or (b_dir / "_COMMITTED.lock").exists():
                continue
            man_p = b_dir / "Batch_Inventory_Manifest.csv"
            if not man_p.exists():
                continue
            try:
                bdf = pd.read_csv(man_p, dtype=str, keep_default_na=False)
                if bdf.empty:
                    continue
                b_rows = [
                    ri for ri, rr in bdf.iterrows()
                    if not clean_set_filter or str(rr.get("Set") or "").strip() == clean_set_filter
                ]
                if b_rows:
                    batch_jobs.append((b_dir, man_p, bdf, b_rows))
            except Exception:
                continue

    total_to_check = len(inv_work) + sum(len(x[3]) for x in batch_jobs)
    if total_to_check == 0:
        msg = "No cards found matching the selected Rotation Fixer scope/set filter."
        if log_cb:
            log_cb(f"⚠️ {msg}")
        return {"checked": 0, "impacted": 0, "fronts_rotated": 0, "backs_rotated": 0, "message": msg}

    if log_cb:
        log_cb(
            f"🔎 Checking orientation across {total_to_check:,} card(s) "
            f"({len(inv_work):,} Inventory + {total_to_check - len(inv_work):,} Uncommitted Batch)..."
        )

    checked = 0
    impacted = 0
    fronts_rot_cnt = 0
    backs_rot_cnt = 0

    def _check_and_fix_pair(
        sku_s: str,
        set_n: str,
        sub_n: str,
        cnum_n: str,
        plr_n: str,
        old_psa: str,
        old_bgs: str,
        f_p: Optional[Path],
        b_p: Optional[Path],
        c_p: Optional[Path],
    ) -> Optional[dict]:
        nonlocal fronts_rot_cnt, backs_rot_cnt
        if f_p is None or not f_p.exists():
            return None

        with Image.open(f_p) as fim:
            f_img = fim.convert("RGB")
        has_back_file = b_p is not None and b_p.exists()
        if has_back_file:
            with Image.open(b_p) as bim:
                b_img = bim.convert("RGB")
        else:
            b_img = f_img

        # 1. Back 4-angle orientation check (strictly require decisive win over 0° before rotating)
        back_rot_ang = 0
        b_oriented = b_img
        if has_back_file:
            b_cand, ocr_b = extract_back_ocr_and_orient(b_img, preferred_angle=0, force_all_angles=True)
            cand_ang = int(ocr_b.get("back_rotation_angle", 0) or 0)
            sc0 = ocr_b.get("back_score_0")
            sc_best = float(ocr_b.get("back_best_score", 0.0) or 0.0)
            orig_land = b_img.width > b_img.height * 1.10
            cand_land = b_cand.width > b_cand.height * 1.10
            req_margin = 6.0 if (cand_land != orig_land) else 12.0
            if cand_ang != 0 and (sc0 is None or sc_best >= float(sc0) + req_margin):
                b_oriented = b_cand
                back_rot_ang = cand_ang

        # 2. Front orientation check using the card's existing known identity (excluding itself!)
        f_oriented, front_rot_ang, front_rsn = orient_front_card_image(
            front_img=f_img,
            back_rotation_angle=back_rot_ang,
            set_name=set_n,
            subset_name=sub_n,
            card_number=cnum_n,
            template_catalog=template_catalog,
            reviewed_by_card=reviewed_by_card,
            exclude_paths={str(f_p.resolve())},
        )

        if front_rot_ang == 0 and back_rot_ang == 0:
            return None

        if front_rot_ang != 0:
            fronts_rot_cnt += 1
        if back_rot_ang != 0:
            backs_rot_cnt += 1

        if dry_run:
            if log_cb:
                log_cb(
                    f"  [DRY-RUN] SKU {sku_s} — {set_n} #{cnum_n} {plr_n}: "
                    f"Front ↻{front_rot_ang}° ({front_rsn}) | Back ↻{back_rot_ang}°"
                )
            return {"dry_run": True}

        if front_rot_ang != 0:
            f_oriented.save(f_p, format="JPEG", quality=94)
        if back_rot_ang != 0 and has_back_file:
            b_oriented.save(b_p, format="JPEG", quality=94)

        f_box = detect_physical_card_box(f_oriented)
        b_box = detect_physical_card_box(b_oriented)

        target_c_p = c_p
        if target_c_p is None and f_p.name.upper().endswith("_F.JPG"):
            target_c_p = f_p.with_name(f_p.name[:-6] + "_C.jpg")
        if target_c_p is not None and target_c_p.parent.exists():
            try:
                c_im = build_corners_inspection_sheet(f_oriented, b_oriented, front_box=f_box, back_box=b_box)
                c_im.save(target_c_p, format="JPEG", quality=92)
            except Exception:
                pass

        grade_upd = estimate_card_pregrade(f_oriented, b_oriented, front_box=f_box, back_box=b_box)
        if log_cb:
            log_cb(
                f"  ↻ [FIXED] SKU {sku_s} — {set_n} #{cnum_n} {plr_n} [{sub_n}] | "
                f"Front ↻{front_rot_ang}° ({front_rsn}) | Back ↻{back_rot_ang}° | "
                f"New 8-Corners + Grade: PSA {old_psa or '?'}->{grade_upd.get('Est_PSA','?')} / "
                f"BGS {old_bgs or '?'}->{grade_upd.get('Est_BGS','?')}"
            )
        return grade_upd

    # Phase 1: Master Inventory (_My_Collection)
    inv_impacted_indices: list[int] = []
    if inv_work and not inv_df.empty:
        for r_idx in inv_work:
            checked += 1
            row = inv_df.loc[r_idx].to_dict()
            sku_s = str(row.get("SKU") or "").strip()
            set_n = str(row.get("Set") or "").strip()
            sub_n = str(row.get("Subset") or "Base").strip() or "Base"
            cnum_n = str(row.get("Card Number") or "").strip().lstrip("#")
            plr_n = str(row.get("Player") or "").strip()
            f_p, b_p, c_p = _locate_inventory_card_images(row, sku_s)
            try:
                g_upd = _check_and_fix_pair(
                    sku_s, set_n, sub_n, cnum_n, plr_n,
                    str(row.get("Est_PSA") or ""), str(row.get("Est_BGS") or ""),
                    f_p, b_p, c_p,
                )
                if g_upd is not None:
                    impacted += 1
                    if not dry_run:
                        for gk, gv in g_upd.items():
                            if gk in inv_df.columns:
                                inv_df.at[r_idx, gk] = gv
                        inv_impacted_indices.append(r_idx)
            except Exception as e:
                if log_cb:
                    log_cb(f"  ⚠️ Error checking Inventory SKU {sku_s}: {e}")

            if progress_callback is not None and (checked % 5 == 0 or checked == total_to_check or r_idx in inv_impacted_indices[-1:]):
                progress_callback(checked, total_to_check, {
                    "SKU": sku_s, "Set": set_n, "Player": plr_n,
                    "impacted": impacted, "scope_label": "Master Inventory",
                })

        if inv_impacted_indices and not dry_run:
            # Recalculate ROI on impacted rows only while strictly preserving manual Raw_Price / Rec_Sale_Price
            saved_prices = {
                ri: (str(inv_df.at[ri, "Raw_Price"]), str(inv_df.at[ri, "Rec_Sale_Price"]))
                for ri in inv_impacted_indices
            }
            sub_roi = recalculate_dataframe_multi_grader_roi(inv_df.loc[inv_impacted_indices].copy())
            for col_c in sub_roi.columns:
                if col_c not in inv_df.columns:
                    inv_df[col_c] = ""
                inv_df.loc[inv_impacted_indices, col_c] = sub_roi[col_c]
            for ri, (orig_raw, orig_rec) in saved_prices.items():
                inv_df.at[ri, "Raw_Price"] = orig_raw
                inv_df.at[ri, "Rec_Sale_Price"] = orig_rec
            save_inventory_df(inv_df)

    # Phase 2: Uncommitted Batches
    for b_dir, man_p, bdf, b_rows in batch_jobs:
        b_impacted: list[int] = []
        for r_idx in b_rows:
            checked += 1
            row = bdf.loc[r_idx].to_dict()
            sku_s = str(row.get("SKU") or "").strip()
            set_n = str(row.get("Set") or "").strip()
            sub_n = str(row.get("Subset_Parallel") or "Base").strip() or "Base"
            cnum_n = str(row.get("Card_Number") or "").strip().lstrip("#")
            plr_n = str(row.get("Player") or "").strip()
            f_fn = str(row.get("Front_File") or "").strip()
            b_fn = str(row.get("Back_File") or "").strip()
            c_fn = str(row.get("Corners_File") or "").strip()
            f_p = (b_dir / f_fn) if f_fn else None
            b_p = (b_dir / b_fn) if b_fn else None
            c_p = (b_dir / c_fn) if c_fn else None
            try:
                g_upd = _check_and_fix_pair(
                    sku_s, set_n, sub_n, cnum_n, plr_n,
                    str(row.get("Est_PSA") or ""), str(row.get("Est_BGS") or ""),
                    f_p, b_p, c_p,
                )
                if g_upd is not None:
                    impacted += 1
                    if not dry_run:
                        for gk, gv in g_upd.items():
                            if gk in bdf.columns:
                                bdf.at[r_idx, gk] = gv
                        b_impacted.append(r_idx)
            except Exception as e:
                if log_cb:
                    log_cb(f"  ⚠️ Error checking Batch '{b_dir.name}' SKU {sku_s}: {e}")

            if progress_callback is not None and (checked % 5 == 0 or checked == total_to_check or r_idx in b_impacted[-1:]):
                progress_callback(checked, total_to_check, {
                    "SKU": sku_s, "Set": set_n, "Player": plr_n,
                    "impacted": impacted, "scope_label": f"Batch: {b_dir.name}",
                })

        if b_impacted and not dry_run:
            sub_roi = recalculate_dataframe_multi_grader_roi(bdf.loc[b_impacted].copy())
            for col_c in sub_roi.columns:
                if col_c not in bdf.columns:
                    bdf[col_c] = ""
                bdf.loc[b_impacted, col_c] = sub_roi[col_c]
            tmp_m = man_p.with_suffix(".csv.tmp")
            bdf.to_csv(tmp_m, index=False, encoding="utf-8-sig")
            os.replace(str(tmp_m), str(man_p))

    summary = (
        f"Rotation Fixer Complete: Checked {checked:,} card(s) | "
        f"Fixed {impacted:,} impacted card(s) (Fronts rotated: {fronts_rot_cnt:,}, Backs rotated: {backs_rot_cnt:,}) | "
        f"Regenerated {impacted:,} 8-corner sheet(s) & re-graded (Zero identities modified)."
    )
    if log_cb:
        log_cb(f"✅ {summary}")
    return {
        "checked": checked,
        "impacted": impacted,
        "fronts_rotated": fronts_rot_cnt,
        "backs_rotated": backs_rot_cnt,
        "message": summary,
    }



def _decode_base64_payload(b64_str: str) -> bytes:
    import base64
    raw = str(b64_str or "").strip()
    if "," in raw and raw[:64].lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def _decode_uploaded_image_bytes(
    raw_bytes: bytes,
    filename: str = "",
    page_index: int = 0,
) -> Optional[Image.Image]:
    """
    Decodes uploaded image bytes (JPG, PNG, WEBP, BMP, TIFF) or renders a specific page
    of an uploaded PDF at scanner DPI into an upright EXIF-corrected RGB PIL Image.
    """
    from PIL import ImageOps

    if not raw_bytes:
        return None
    is_pdf = str(filename or "").strip().lower().endswith(".pdf") or raw_bytes[:5] == b"%PDF-"
    if is_pdf:
        doc = None
        try:
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            if len(doc) <= page_index:
                return None
            page = doc.load_page(page_index)
            dpi_val = int(RUNTIME_CONFIG.get("pdf_render_dpi", 600))
            max_pt = max(float(page.rect.width), float(page.rect.height))
            if max_pt > 450.0:
                dpi_val = min(dpi_val, 300)
            mat = fitz.Matrix(dpi_val / 72.0, dpi_val / 72.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        finally:
            if doc is not None:
                doc.close()

    with Image.open(io.BytesIO(raw_bytes)) as im:
        im_fixed = ImageOps.exif_transpose(im)
        return im_fixed.convert("RGB")


def replace_card_images_from_bytes(
    target_type: str,
    sku: str,
    batch_name: str = "",
    front_b64: str = "",
    front_filename: str = "",
    back_b64: str = "",
    back_filename: str = "",
    pdf_b64: str = "",
    pdf_filename: str = "",
    auto_orient: bool = True,
    regrade_too: bool = True,
) -> dict:
    """
    Replaces the Front and/or Back scan image of an existing card in either:
      - `target_type == "inventory"` (`D:\\Tabulas Set Library\\_My_Collection\\<Set>\\` + `Inventory.csv`)
      - `target_type == "batch"` (`D:\\Tabulas Set Library\\Unprocessed_Cards\\Batches\\<batch_name>\\` + `Batch_Inventory_Manifest.csv`)
    Accepts individual image files (JPG/PNG/WEBP/BMP/TIFF/1-page PDF) OR a single 2-page PDF
    (Page 1 = Front, Page 2 = Back). Preserves existing card identity & manual prices, optionally
    auto-orients the replacement scans, rebuilds the 8-Corner Sheet (`_C.jpg`), and refreshes Pre-Grades.
    """
    from Core.config import BATCHES_DIR
    from Core.database import load_inventory_df, save_inventory_df

    sku_s = str(sku or "").strip()
    if not sku_s:
        return {"success": False, "error": "SKU is required."}

    new_front_img: Optional[Image.Image] = None
    new_back_img: Optional[Image.Image] = None

    try:
        if pdf_b64:
            pdf_raw = _decode_base64_payload(pdf_b64)
            new_front_img = _decode_uploaded_image_bytes(pdf_raw, pdf_filename or "scan.pdf", page_index=0)
            new_back_img = _decode_uploaded_image_bytes(pdf_raw, pdf_filename or "scan.pdf", page_index=1)
        else:
            if front_b64:
                new_front_img = _decode_uploaded_image_bytes(_decode_base64_payload(front_b64), front_filename, page_index=0)
            if back_b64:
                new_back_img = _decode_uploaded_image_bytes(_decode_base64_payload(back_b64), back_filename, page_index=0)
    except Exception as e:
        return {"success": False, "error": f"Could not decode uploaded file: {e}"}

    if new_front_img is None and new_back_img is None:
        return {"success": False, "error": "Please select at least one valid Front image, Back image, or 2-page PDF."}

    is_inventory = str(target_type or "").strip().lower() == "inventory"

    if is_inventory:
        df = load_inventory_df()
        if df.empty:
            return {"success": False, "error": "Master Inventory.csv is empty."}
        df["SKU"] = df["SKU"].astype(str).str.strip()
        hits = df.index[df["SKU"] == sku_s].tolist()
        if not hits:
            return {"success": False, "error": f"SKU {sku_s} not found in Master Inventory."}
        r_idx = hits[0]
        row_d = df.loc[r_idx].to_dict()
        set_n = str(row_d.get("Set") or "").strip() or "Unknown Set"
        sub_n = str(row_d.get("Subset") or "Base").strip() or "Base"
        cnum_n = str(row_d.get("Card Number") or "0").strip().lstrip("#")
        plr_n = str(row_d.get("Player") or "Unknown Player").strip()

        f_p, b_p, c_p = _locate_inventory_card_images(row_d, sku_s)
        set_dir = REVIEWED_CARDS_DIR / sanitize_filename_part(set_n)
        set_dir.mkdir(parents=True, exist_ok=True)
        canon_f, canon_b, canon_c = build_card_image_filenames(set_n, sub_n, cnum_n, plr_n, sku_s)
        f_p = f_p or (set_dir / (str(row_d.get("Front_File") or "").strip() or canon_f))
        b_p = b_p or (set_dir / (str(row_d.get("Back_File") or "").strip() or canon_b))
        c_p = c_p or (set_dir / (str(row_d.get("Corners_File") or "").strip() or canon_c))
        target_dir = f_p.parent
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        b_name = str(batch_name or "").strip()
        batch_dir = BATCHES_DIR / b_name
        man_p = batch_dir / "Batch_Inventory_Manifest.csv"
        if not b_name or not man_p.exists():
            return {"success": False, "error": f"Batch manifest not found: {b_name}"}
        df = pd.read_csv(man_p, dtype=str, keep_default_na=False)
        df["SKU"] = df["SKU"].astype(str).str.strip()
        hits = df.index[df["SKU"] == sku_s].tolist()
        if not hits:
            return {"success": False, "error": f"SKU {sku_s} not found in batch '{b_name}'."}
        r_idx = hits[0]
        row_d = df.loc[r_idx].to_dict()
        set_n = str(row_d.get("Set") or "").strip() or "Unknown Set"
        sub_n = str(row_d.get("Subset_Parallel") or "Base").strip() or "Base"
        cnum_n = str(row_d.get("Card_Number") or "0").strip().lstrip("#")
        plr_n = str(row_d.get("Player") or "Unknown Player").strip()

        canon_f, canon_b, canon_c = build_card_image_filenames(set_n, sub_n, cnum_n, plr_n, sku_s)
        f_p = batch_dir / (str(row_d.get("Front_File") or "").strip() or canon_f)
        b_p = batch_dir / (str(row_d.get("Back_File") or "").strip() or canon_b)
        c_p = batch_dir / (str(row_d.get("Corners_File") or "").strip() or canon_c)
        target_dir = batch_dir

    old_psa = str(row_d.get("Est_PSA") or "")
    old_bgs = str(row_d.get("Est_BGS") or "")
    front_rot_ang = 0
    back_rot_ang = 0

    # Auto-orient newly uploaded image(s) if enabled
    if auto_orient:
        if new_back_img is not None:
            b_cand, ocr_b = extract_back_ocr_and_orient(new_back_img, preferred_angle=0, force_all_angles=True)
            cand_ang = int(ocr_b.get("back_rotation_angle", 0) or 0)
            sc0 = ocr_b.get("back_score_0")
            sc_best = float(ocr_b.get("back_best_score", 0.0) or 0.0)
            orig_land = new_back_img.width > new_back_img.height * 1.10
            cand_land = b_cand.width > b_cand.height * 1.10
            req_margin = 6.0 if (cand_land != orig_land) else 12.0
            if cand_ang != 0 and (sc0 is None or sc_best >= float(sc0) + req_margin):
                new_back_img = b_cand
                back_rot_ang = cand_ang

        if new_front_img is not None:
            template_catalog, reviewed_by_card, _ = index_set_templates_and_reviewed_cards(
                REFERENCE_TEMPLATES_DIR,
                REVIEWED_CARDS_DIR,
                locked_set=set_n or None,
                lazy_vectors=True,
            )
            excl = {str(f_p.resolve())} if f_p.exists() else set()
            new_front_img, front_rot_ang, _ = orient_front_card_image(
                front_img=new_front_img,
                back_rotation_angle=back_rot_ang,
                set_name=set_n,
                subset_name=sub_n,
                card_number=cnum_n,
                template_catalog=template_catalog,
                reviewed_by_card=reviewed_by_card,
                exclude_paths=excl,
            )

    # Persist replacement image(s) in-place
    replaced_sides: list[str] = []
    if new_front_img is not None:
        new_front_img.save(f_p, format="JPEG", quality=94)
        df.at[r_idx, "Front_File"] = f_p.name
        replaced_sides.append("Front")
    if new_back_img is not None:
        new_back_img.save(b_p, format="JPEG", quality=94)
        df.at[r_idx, "Back_File"] = b_p.name
        replaced_sides.append("Back")

    # Resolve final Front & Back PIL images (using existing disk scan for any unreplaced side)
    final_f = new_front_img
    if final_f is None and f_p.exists():
        with Image.open(f_p) as fim:
            final_f = fim.convert("RGB")
    final_b = new_back_img
    if final_b is None and b_p.exists():
        with Image.open(b_p) as bim:
            final_b = bim.convert("RGB")
    if final_f is None:
        final_f = final_b
    if final_b is None:
        final_b = final_f

    # Rebuild 8-Corner Inspection Sheet & Re-Grade (preserving identity & manual prices)
    if regrade_too and final_f is not None and final_b is not None:
        f_box = detect_physical_card_box(final_f)
        b_box = detect_physical_card_box(final_b)
        try:
            c_im = build_corners_inspection_sheet(final_f, final_b, front_box=f_box, back_box=b_box)
            c_im.save(c_p, format="JPEG", quality=92)
            df.at[r_idx, "Corners_File"] = c_p.name
        except Exception:
            pass

        g_res = estimate_card_pregrade(final_f, final_b, front_box=f_box, back_box=b_box)
        for gk, gv in g_res.items():
            if gk in df.columns:
                df.at[r_idx, gk] = gv

        saved_raw = str(df.at[r_idx, "Raw_Price"]) if "Raw_Price" in df.columns else ""
        saved_rec = str(df.at[r_idx, "Rec_Sale_Price"]) if "Rec_Sale_Price" in df.columns else ""
        sub_roi = recalculate_dataframe_multi_grader_roi(df.loc[[r_idx]].copy())
        for col_c in sub_roi.columns:
            if col_c not in df.columns:
                df[col_c] = ""
            df.at[r_idx, col_c] = sub_roi.iloc[0][col_c]
        if is_inventory:
            if saved_raw:
                df.at[r_idx, "Raw_Price"] = saved_raw
            if saved_rec:
                df.at[r_idx, "Rec_Sale_Price"] = saved_rec

    if is_inventory:
        saved_df = save_inventory_df(df)
        updated_card = saved_df[saved_df["SKU"].astype(str).str.strip() == sku_s].iloc[0].to_dict()
        return {
            "success": True,
            "sku": sku_s,
            "replacedSides": replaced_sides,
            "frontRotated": front_rot_ang,
            "backRotated": back_rot_ang,
            "oldPSA": old_psa,
            "newPSA": str(updated_card.get("Est_PSA") or ""),
            "oldBGS": old_bgs,
            "newBGS": str(updated_card.get("Est_BGS") or ""),
            "card": updated_card,
            "rows": saved_df.to_dict(orient="records"),
        }
    else:
        tmp_m = man_p.with_suffix(".csv.tmp")
        df.to_csv(tmp_m, index=False, encoding="utf-8-sig")
        os.replace(str(tmp_m), str(man_p))
        updated_card = df.loc[r_idx].to_dict()
        return {
            "success": True,
            "sku": sku_s,
            "replacedSides": replaced_sides,
            "frontRotated": front_rot_ang,
            "backRotated": back_rot_ang,
            "oldPSA": old_psa,
            "newPSA": str(updated_card.get("Est_PSA") or ""),
            "oldBGS": old_bgs,
            "newBGS": str(updated_card.get("Est_BGS") or ""),
            "card": updated_card,
            "cards": df.to_dict(orient="records"),
        }
