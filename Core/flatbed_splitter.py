from __future__ import annotations

import copy
import io
import json
import math
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import fitz
import numpy as np
from PIL import Image

from Core.config import (
    BATCHES_DIR,
    REVIEWED_CARDS_DIR,
    RUNTIME_CONFIG,
    SPLITTER_LEARNING_PROFILE_FILE,
    SPLITTER_STAGING_DIR,
    atomic_write_text,
    sanitize_filename_part,
)

# ==============================================================================
# 1. DETERMINISTIC COLOR TOKENS & DEFAULT SELF-LEARNING CALIBRATION PROFILE
# ==============================================================================
PAIR_COLOR_PALETTE: list[str] = [
    "#3B82F6",  # Blue
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EF4444",  # Red
    "#8B5CF6",  # Violet
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#84CC16",  # Lime
    "#F97316",  # Orange
    "#14B8A6",  # Teal
    "#6366F1",  # Indigo
    "#E11D48",  # Rose
]

DEFAULT_SPLITTER_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "ema_alpha": 0.25,
    "sample_count": 0,
    # Toploader-like border/margin padding per side (ratio of detected card width/height)
    "pad_ratio_x": 0.075,
    "pad_ratio_y": 0.065,
    # Aspect ratio & area bounds (supports raw, penny sleeves, toploaders, semi-rigids, slabs)
    "target_aspect_ratio": 1.40,
    "min_aspect_ratio": 1.08,
    "max_aspect_ratio": 1.95,
    "min_area_ratio": 0.012,
    "max_area_ratio": 0.48,
    # Pancake-flip spatial matching tolerances (normalized to page dimensions)
    "pancake_tol_x": 0.14,
    "pancake_tol_y": 0.14,
    "pancake_tol_angle_deg": 18.0,
    "flip_mode_bias": {
        "pancake": 0,
        "mirrored_x": 0,
    },
    "edit_stats": {
        "commits": 0,
        "resized_boxes": 0,
        "rotated_boxes": 0,
        "added_cards": 0,
        "deleted_false_positives": 0,
        "swapped_pairs": 0,
    },
    "library_bootstrap": {
        "sampled_count": 0,
        "median_aspect_ratio": None,
        "estimated_pad_ratio_x": None,
        "estimated_pad_ratio_y": None,
        "last_bootstrapped_at": None,
    },
    "updated_at": None,
}


def get_pair_color(pair_id: int) -> str:
    """Return a deterministic high-contrast hex color token for a 1-based pair_id."""
    idx = (max(1, int(pair_id)) - 1) % len(PAIR_COLOR_PALETTE)
    return PAIR_COLOR_PALETTE[idx]


def _merge_profile_defaults(raw: Optional[dict]) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_SPLITTER_PROFILE)
    if not isinstance(raw, dict):
        return merged
    for k, v in raw.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def load_splitter_profile(profile_path: Optional[Path] = None) -> dict[str, Any]:
    """Load the self-learning splitter calibration profile, merging defaults."""
    target = Path(profile_path) if profile_path is not None else Path(SPLITTER_LEARNING_PROFILE_FILE)
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return _merge_profile_defaults(data)
        except Exception:
            pass
    return _merge_profile_defaults(None)


def save_splitter_profile(profile: dict[str, Any], profile_path: Optional[Path] = None) -> dict[str, Any]:
    """Atomically persist the splitter calibration profile."""
    target = Path(profile_path) if profile_path is not None else Path(SPLITTER_LEARNING_PROFILE_FILE)
    clean = _merge_profile_defaults(profile)
    clean["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(clean, indent=2), encoding="utf-8")
    return clean


# ==============================================================================
# 2. PROCESSED LIBRARY REFERENCE BOOTSTRAPPING
# ==============================================================================
def _estimate_border_margin_ratio(img_rgb: np.ndarray) -> tuple[float, float]:
    """Estimate outer sleeve/toploader margin ratio from a downscaled processed card image."""
    h, w = img_rgb.shape[:2]
    if h < 20 or w < 20:
        return 0.06, 0.05
    scale = min(1.0, 200.0 / max(h, w))
    if scale < 1.0:
        small = cv2.resize(img_rgb, (max(20, int(w * scale)), max(20, int(h * scale))), interpolation=cv2.INTER_AREA)
    else:
        small = img_rgb
    sh, sw = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)

    border_px = np.concatenate(
        [
            lab[0, :, :],
            lab[-1, :, :],
            lab[:, 0, :],
            lab[:, -1, :],
        ],
        axis=0,
    )
    bg_lab = np.median(border_px, axis=0)
    dist = np.linalg.norm(lab - bg_lab, axis=2)
    fg = (dist > 14.0).astype(np.uint8)
    ys, xs = np.where(fg > 0)
    if len(xs) < 25:
        return 0.06, 0.05

    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    inner_w = max(1.0, float(x2 - x1 + 1))
    inner_h = max(1.0, float(y2 - y1 + 1))
    if inner_w < sw * 0.45 or inner_h < sh * 0.45:
        return 0.06, 0.05

    pad_x = max(0.02, min(0.18, (sw - inner_w) / (2.0 * inner_w)))
    pad_y = max(0.02, min(0.18, (sh - inner_h) / (2.0 * inner_h)))
    return float(pad_x), float(pad_y)


def bootstrap_profile_from_library(
    profile_path: Optional[Path] = None,
    library_dirs: Optional[list[Path]] = None,
    max_samples: int = 40,
    force: bool = False,
) -> dict[str, Any]:
    """
    Fast, cached sampler that inspects already-processed card images in the local
    library to seed/refine expected card aspect ratios and toploader margin ratios.
    """
    profile = load_splitter_profile(profile_path)
    lb = profile.get("library_bootstrap") or {}
    last_ts = lb.get("last_bootstrapped_at")
    if not force and last_ts:
        try:
            age_sec = (datetime.now() - datetime.fromisoformat(str(last_ts))).total_seconds()
            if age_sec < 86400.0 and int(lb.get("sampled_count") or 0) > 0:
                return profile
        except Exception:
            pass

    dirs_to_scan = (
        [Path(d) for d in library_dirs if d is not None]
        if library_dirs is not None
        else [Path(REVIEWED_CARDS_DIR), Path(BATCHES_DIR)]
    )

    sample_paths: list[Path] = []
    exts = {".jpg", ".jpeg", ".png"}
    for root_dir in dirs_to_scan:
        if not root_dir.exists():
            continue
        for p in root_dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            low_name = p.name.lower()
            if "thumb" in low_name or "diag" in low_name or "sheet" in low_name:
                continue
            sample_paths.append(p)
            if len(sample_paths) >= max_samples * 3:
                break
        if len(sample_paths) >= max_samples * 3:
            break

    if not sample_paths:
        return profile

    if len(sample_paths) > max_samples:
        step = max(1, len(sample_paths) // max_samples)
        sample_paths = sample_paths[::step][:max_samples]

    aspects: list[float] = []
    pad_xs: list[float] = []
    pad_ys: list[float] = []

    for img_path in sample_paths:
        try:
            with Image.open(img_path) as im:
                im_rgb = im.convert("RGB")
                w, h = im_rgb.size
                if min(w, h) < 40:
                    continue
                aspect = max(w, h) / float(min(w, h))
                if 1.05 <= aspect <= 1.95:
                    aspects.append(aspect)
                px, py = _estimate_border_margin_ratio(np.array(im_rgb))
                pad_xs.append(px)
                pad_ys.append(py)
        except Exception:
            continue

    if not aspects:
        return profile

    med_aspect = float(np.median(aspects))
    med_px = float(np.median(pad_xs)) if pad_xs else float(profile["pad_ratio_x"])
    med_py = float(np.median(pad_ys)) if pad_ys else float(profile["pad_ratio_y"])

    alpha = 0.35
    if int(profile.get("sample_count") or 0) == 0:
        profile["target_aspect_ratio"] = round(max(1.20, min(1.65, med_aspect)), 4)
        profile["pad_ratio_x"] = round(max(0.03, min(0.18, med_px)), 4)
        profile["pad_ratio_y"] = round(max(0.03, min(0.18, med_py)), 4)
    else:
        profile["target_aspect_ratio"] = round(
            max(1.20, min(1.65, (1.0 - alpha) * float(profile["target_aspect_ratio"]) + alpha * med_aspect)),
            4,
        )
        profile["pad_ratio_x"] = round(
            max(0.03, min(0.18, (1.0 - alpha) * float(profile["pad_ratio_x"]) + alpha * med_px)),
            4,
        )
        profile["pad_ratio_y"] = round(
            max(0.03, min(0.18, (1.0 - alpha) * float(profile["pad_ratio_y"]) + alpha * med_py)),
            4,
        )

    profile["library_bootstrap"] = {
        "sampled_count": len(aspects),
        "median_aspect_ratio": round(med_aspect, 4),
        "estimated_pad_ratio_x": round(med_px, 4),
        "estimated_pad_ratio_y": round(med_py, 4),
        "last_bootstrapped_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return save_splitter_profile(profile, profile_path=profile_path)


# ==============================================================================
# 3. GENERALIZED MULTI-CARD ORIENTED BOUNDING BOX (OBB) DETECTOR
# ==============================================================================
def _canonicalize_min_area_rect(rect: tuple) -> tuple[float, float, float, float, float]:
    """
    Convert cv2.minAreaRect output into `(cx, cy, width, height, angle_deg)`
    with `angle_deg` canonicalized into `[-45.0, 45.0]`.
    """
    (cx, cy), (rw, rh), angle = rect
    rw_f = float(rw)
    rh_f = float(rh)
    ang = float(angle)
    while ang > 45.0:
        rw_f, rh_f = rh_f, rw_f
        ang -= 90.0
    while ang <= -45.0:
        rw_f, rh_f = rh_f, rw_f
        ang += 90.0
    return float(cx), float(cy), rw_f, rh_f, ang


def _box_center_overlap_dup(b1: dict, b2: dict) -> bool:
    dx = abs(float(b1["cx"]) - float(b2["cx"]))
    dy = abs(float(b1["cy"]) - float(b2["cy"]))
    min_dim = min(float(b1["width"]), float(b1["height"]), float(b2["width"]), float(b2["height"]))
    return dx < 0.35 * min_dim and dy < 0.35 * min_dim


def detect_cards_on_page(
    page_img: Image.Image | np.ndarray,
    profile: Optional[dict[str, Any]] = None,
    profile_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """
    Detect any number of trading cards in any position, orientation, or holder
    (raw, penny sleeve, toploader, semi-rigid, one-touch slab) on a flatbed scan page.

    Returns a list of oriented bounding boxes:
      `{cx, cy, width, height, angle_deg, confidence, raw_width, raw_height, pair_id, color}`
    sorted top-to-bottom, left-to-right.
    """
    if profile is None:
        profile = load_splitter_profile(profile_path)

    if isinstance(page_img, Image.Image):
        rgb_full = np.array(page_img.convert("RGB"))
    else:
        arr = np.asarray(page_img)
        if arr.ndim == 2:
            rgb_full = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
        else:
            rgb_full = arr[:, :, :3].copy()

    h, w = rgb_full.shape[:2]
    if h < 32 or w < 32:
        return []

    scale = min(1.0, 1400.0 / float(max(w, h)))
    sw = max(32, int(round(w * scale)))
    sh = max(32, int(round(h * scale)))
    if scale < 1.0:
        small_rgb = cv2.resize(rgb_full, (sw, sh), interpolation=cv2.INTER_AREA)
    else:
        small_rgb = rgb_full

    # Estimate scanner bed background Lab color from the outer 2% perimeter strips
    lab = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    b_x = max(4, int(sw * 0.02))
    b_y = max(4, int(sh * 0.02))
    bg_samples = np.concatenate(
        [
            lab[:b_y, :, :].reshape(-1, 3),
            lab[-b_y:, :, :].reshape(-1, 3),
            lab[:, :b_x, :].reshape(-1, 3),
            lab[:, -b_x:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_lab = np.median(bg_samples, axis=0)

    lab_dist = np.linalg.norm(lab - bg_lab, axis=2)
    fg_color = (lab_dist > 15.0).astype(np.uint8) * 255

    gray = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (5, 5), 0)
    edges = cv2.Canny(blur, 25, 95)
    edges_dil = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)

    combined = cv2.bitwise_or(fg_color, edges_dil)
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, close_k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k, iterations=1)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    small_area = float(sw * sh)
    min_area_r = float(profile.get("min_area_ratio", 0.012))
    max_area_r = float(profile.get("max_area_ratio", 0.48))
    min_aspect = float(profile.get("min_aspect_ratio", 1.08))
    max_aspect = float(profile.get("max_aspect_ratio", 1.95))
    target_aspect = float(profile.get("target_aspect_ratio", 1.40))
    pad_x = float(profile.get("pad_ratio_x", 0.075))
    pad_y = float(profile.get("pad_ratio_y", 0.065))

    candidates: list[dict[str, Any]] = []
    for c in cnts:
        c_area = float(cv2.contourArea(c))
        if c_area < 0.5 * min_area_r * small_area:
            continue
        rect = cv2.minAreaRect(c)
        rcx, rcy, rw, rh, ang = _canonicalize_min_area_rect(rect)
        box_area = rw * rh
        if box_area <= 1.0:
            continue

        area_ratio = box_area / small_area
        if not (min_area_r <= area_ratio <= max_area_r):
            continue

        aspect = max(rw, rh) / max(1.0, min(rw, rh))
        if not (min_aspect <= aspect <= max_aspect):
            continue

        rectangularity = min(1.0, c_area / box_area)
        if rectangularity < 0.50:
            continue

        # Contrast signal inside the candidate
        x_i1 = max(0, int(rcx - rw * 0.4))
        x_i2 = min(sw, int(rcx + rw * 0.4))
        y_i1 = max(0, int(rcy - rh * 0.4))
        y_i2 = min(sh, int(rcy + rh * 0.4))
        mean_contrast = float(np.mean(lab_dist[y_i1:y_i2, x_i1:x_i2])) if (x_i2 > x_i1 and y_i2 > y_i1) else 20.0
        contrast_score = min(1.0, mean_contrast / 35.0)
        aspect_score = max(0.0, 1.0 - abs(aspect - target_aspect) / max(0.5, target_aspect))
        confidence = round(0.45 * rectangularity + 0.30 * aspect_score + 0.25 * contrast_score, 4)

        raw_w = rw / scale
        raw_h = rh / scale
        cx_full = rcx / scale
        cy_full = rcy / scale

        padded_w = min(float(w), raw_w * (1.0 + 2.0 * pad_x))
        padded_h = min(float(h), raw_h * (1.0 + 2.0 * pad_y))

        candidates.append(
            {
                "cx": round(cx_full, 2),
                "cy": round(cy_full, 2),
                "width": round(padded_w, 2),
                "height": round(padded_h, 2),
                "angle_deg": round(ang, 2),
                "confidence": confidence,
                "raw_width": round(raw_w, 2),
                "raw_height": round(raw_h, 2),
            }
        )

    # Deduplicate overlapping boxes (keep higher confidence)
    candidates.sort(key=lambda b: b["confidence"], reverse=True)
    kept: list[dict[str, Any]] = []
    for cand in candidates:
        if any(_box_center_overlap_dup(cand, k) for k in kept):
            continue
        kept.append(cand)

    if not kept:
        return []

    med_h = float(np.median([b["height"] for b in kept]))
    row_band = max(40.0, 0.55 * med_h)
    kept.sort(key=lambda b: (int(b["cy"] // row_band), b["cx"]))

    for idx, b in enumerate(kept, 1):
        b["pair_id"] = idx
        b["color"] = get_pair_color(idx)

    return kept


# ==============================================================================
# 4. PANCAKE-FLIP FRONT-TO-BACK AUTO-PAIRING
# ==============================================================================
def _solve_min_cost_assignment(cost_matrix: list[list[float]]) -> list[int]:
    """
    Solve minimum-cost assignment mapping each row i -> unique col j.
    Uses scipy.optimize.linear_sum_assignment if available, with exact
    backtracking fallback for n <= 10 and greedy fallback for larger n.
    """
    n_rows = len(cost_matrix)
    if n_rows == 0:
        return []
    n_cols = len(cost_matrix[0]) if n_rows else 0
    if n_cols == 0:
        return []

    try:
        from scipy.optimize import linear_sum_assignment
        row_ind, col_ind = linear_sum_assignment(np.asarray(cost_matrix, dtype=np.float64))
        assignment = [-1] * n_rows
        for r, c in zip(row_ind.tolist(), col_ind.tolist()):
            assignment[r] = c
        return assignment
    except Exception:
        pass

    if n_rows <= 10 and n_cols <= 10:
        best_cost = [float("inf")]
        best_assign = [-1] * n_rows
        used = [False] * n_cols

        def _bt(r: int, cur_cost: float, cur: list[int]):
            if cur_cost >= best_cost[0]:
                return
            if r == n_rows:
                best_cost[0] = cur_cost
                best_assign[:] = cur
                return
            for c in range(n_cols):
                if not used[c]:
                    used[c] = True
                    cur.append(c)
                    _bt(r + 1, cur_cost + cost_matrix[r][c], cur)
                    cur.pop()
                    used[c] = False

        _bt(0, 0.0, [])
        if -1 not in best_assign:
            return best_assign

    # Greedy fallback
    pairs: list[tuple[float, int, int]] = []
    for r in range(n_rows):
        for c in range(n_cols):
            pairs.append((cost_matrix[r][c], r, c))
    pairs.sort()
    used_r: set[int] = set()
    used_c: set[int] = set()
    assignment = [-1] * n_rows
    for _, r, c in pairs:
        if r not in used_r and c not in used_c:
            used_r.add(r)
            used_c.add(c)
            assignment[r] = c
    return assignment


def _compute_mode_assignment(
    front_boxes: list[dict],
    back_boxes: list[dict],
    front_size: tuple[int, int],
    back_size: tuple[int, int],
    mode: str,
    tol_x: float,
    tol_y: float,
    tol_ang: float,
) -> tuple[list[int], float]:
    fw = max(1.0, float(front_size[0]))
    fh = max(1.0, float(front_size[1]))
    bw = max(1.0, float(back_size[0]))
    bh = max(1.0, float(back_size[1]))

    n_f = len(front_boxes)
    n_b = len(back_boxes)
    if n_f == 0 or n_b == 0:
        return [-1] * n_f, 0.0

    # Pad matrix if counts differ
    size = max(n_f, n_b)
    cost_mat: list[list[float]] = [[100.0 for _ in range(size)] for _ in range(size)]

    for i, fb in enumerate(front_boxes):
        fx = float(fb["cx"]) / fw
        fy = float(fb["cy"]) / fh
        f_ang = float(fb.get("angle_deg", 0.0))
        f_area = (float(fb["width"]) * float(fb["height"])) / (fw * fh)

        target_x = (1.0 - fx) if mode == "mirrored_x" else fx
        target_y = fy
        # Flipping a card horizontally negates its in-plane tilt angle
        target_ang = -f_ang

        for j, bb in enumerate(back_boxes):
            bx = float(bb["cx"]) / bw
            by = float(bb["cy"]) / bh
            b_ang = float(bb.get("angle_deg", 0.0))
            b_area = (float(bb["width"]) * float(bb["height"])) / (bw * bh)

            dx = (bx - target_x) / max(0.05, tol_x)
            dy = (by - target_y) / max(0.05, tol_y)
            d_ang = abs(b_ang - target_ang) / max(5.0, tol_ang)
            d_area = abs(b_area - f_area) / max(0.02, f_area)

            cost_mat[i][j] = (dx * dx + dy * dy) + 0.15 * (d_ang * d_ang) + 0.25 * (d_area * d_area)

    full_assign = _solve_min_cost_assignment(cost_mat)
    total_cost = 0.0
    front_to_back = [-1] * n_f
    for i in range(n_f):
        j = full_assign[i]
        if 0 <= j < n_b:
            front_to_back[i] = j
            total_cost += cost_mat[i][j]
    return front_to_back, total_cost


def match_front_back_pancake(
    front_boxes: list[dict[str, Any]],
    back_boxes: list[dict[str, Any]],
    front_size: tuple[int, int],
    back_size: tuple[int, int],
    flip_mode: str = "auto",
    profile: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """
    Match Front and Back card detections for pancake-flipped or horizontally-mirrored
    flatbed scans. Assigns matching sequential `pair_id`s (1, 2, 3, ...) and
    deterministic color tokens to each Front/Back pair.
    """
    if profile is None:
        profile = load_splitter_profile()

    tol_x = float(profile.get("pancake_tol_x", 0.14))
    tol_y = float(profile.get("pancake_tol_y", 0.14))
    tol_ang = float(profile.get("pancake_tol_angle_deg", 18.0))

    paired_front = [copy.deepcopy(b) for b in front_boxes]
    paired_back_raw = [copy.deepcopy(b) for b in back_boxes]

    for idx, fb in enumerate(paired_front, 1):
        fb["pair_id"] = idx
        fb["color"] = get_pair_color(idx)

    if not paired_front or not paired_back_raw:
        for idx, bb in enumerate(paired_back_raw, 1):
            bb["pair_id"] = idx
            bb["color"] = get_pair_color(idx)
        return paired_front, paired_back_raw, "pancake"

    mode_norm = str(flip_mode or "auto").strip().lower()
    if mode_norm == "mirrored_x":
        chosen_mode = "mirrored_x"
        assign, _ = _compute_mode_assignment(
            paired_front, paired_back_raw, front_size, back_size, "mirrored_x", tol_x, tol_y, tol_ang
        )
    elif mode_norm in ("pancake", "in_place", "same_pos"):
        chosen_mode = "pancake"
        assign, _ = _compute_mode_assignment(
            paired_front, paired_back_raw, front_size, back_size, "pancake", tol_x, tol_y, tol_ang
        )
    else:
        assign_p, cost_p = _compute_mode_assignment(
            paired_front, paired_back_raw, front_size, back_size, "pancake", tol_x, tol_y, tol_ang
        )
        assign_m, cost_m = _compute_mode_assignment(
            paired_front, paired_back_raw, front_size, back_size, "mirrored_x", tol_x, tol_y, tol_ang
        )
        if cost_m < cost_p * 0.95:
            chosen_mode = "mirrored_x"
            assign = assign_m
        else:
            chosen_mode = "pancake"
            assign = assign_p

    used_backs: set[int] = set()
    paired_back: list[dict[str, Any]] = []
    for i, fb in enumerate(paired_front):
        j = assign[i] if i < len(assign) else -1
        if 0 <= j < len(paired_back_raw) and j not in used_backs:
            used_backs.add(j)
            bb = paired_back_raw[j]
            bb["pair_id"] = fb["pair_id"]
            bb["color"] = fb["color"]
            paired_back.append(bb)

    next_extra_id = len(paired_front) + 1
    for j, bb in enumerate(paired_back_raw):
        if j not in used_backs:
            bb["pair_id"] = next_extra_id
            bb["color"] = get_pair_color(next_extra_id)
            bb["unmatched"] = True
            paired_back.append(bb)
            next_extra_id += 1

    paired_back.sort(key=lambda b: int(b["pair_id"]))
    return paired_front, paired_back, chosen_mode


# ==============================================================================
# 5. ORIENTED CROPPER & USER-EDIT SELF-LEARNING FEEDBACK
# ==============================================================================
def crop_oriented_box(page_img: Image.Image, box: dict[str, Any]) -> Image.Image:
    """
    Crop an oriented bounding box `(cx, cy, width, height, angle_deg)` from `page_img`,
    rotating around `(cx, cy)` to straighten the card before slicing.
    """
    rgb = np.array(page_img.convert("RGB"))
    h, w = rgb.shape[:2]
    cx = float(box["cx"])
    cy = float(box["cy"])
    bw = max(8, int(round(float(box["width"]))))
    bh = max(8, int(round(float(box["height"]))))
    angle_deg = float(box.get("angle_deg", 0.0))

    if abs(angle_deg) >= 0.25:
        mat = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
        rotated = cv2.warpAffine(
            rgb,
            mat,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    else:
        rotated = rgb

    x1 = max(0, int(round(cx - bw * 0.5)))
    y1 = max(0, int(round(cy - bh * 0.5)))
    x2 = min(w, x1 + bw)
    y2 = min(h, y1 + bh)
    if x2 <= x1 or y2 <= y1:
        return Image.fromarray(rgb)
    return Image.fromarray(rotated[y1:y2, x1:x2])


def _match_proposed_to_approved(
    proposed: list[dict],
    approved: list[dict],
    max_dist: float,
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    used_p: set[int] = set()
    matched: list[tuple[dict, dict]] = []
    added: list[dict] = []

    for ab in approved:
        acx, acy = float(ab["cx"]), float(ab["cy"])
        best_i = -1
        best_d = max_dist
        for i, pb in enumerate(proposed):
            if i in used_p:
                continue
            d = math.hypot(acx - float(pb["cx"]), acy - float(pb["cy"]))
            if d < best_d:
                best_d = d
                best_i = i
        if best_i >= 0:
            used_p.add(best_i)
            matched.append((proposed[best_i], ab))
        else:
            added.append(ab)

    deleted = [pb for i, pb in enumerate(proposed) if i not in used_p]
    return matched, added, deleted


def record_splitter_user_feedback(
    proposed_front: list[dict],
    proposed_back: list[dict],
    approved_front: list[dict],
    approved_back: list[dict],
    front_size: tuple[int, int],
    back_size: tuple[int, int],
    profile_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Learn from the diff between auto-proposed boxes and user-approved boxes:
    updates running EMAs for padding ratios, aspect ratio priors, area bounds,
    and pancake-flip spatial tolerances.
    """
    profile = load_splitter_profile(profile_path)
    alpha = float(profile.get("ema_alpha", 0.25))
    stats = profile["edit_stats"]
    stats["commits"] = int(stats.get("commits", 0)) + 1

    fw, fh = max(1.0, float(front_size[0])), max(1.0, float(front_size[1]))
    bw, bh = max(1.0, float(back_size[0])), max(1.0, float(back_size[1]))

    pad_x_samples: list[float] = []
    pad_y_samples: list[float] = []
    aspect_samples: list[float] = []

    for prop_list, app_list, (pw, ph) in (
        (proposed_front, approved_front, (fw, fh)),
        (proposed_back, approved_back, (bw, bh)),
    ):
        max_d = 0.18 * max(pw, ph)
        matched, added, deleted = _match_proposed_to_approved(prop_list, app_list, max_d)
        stats["added_cards"] = int(stats.get("added_cards", 0)) + len(added)
        stats["deleted_false_positives"] = int(stats.get("deleted_false_positives", 0)) + len(deleted)

        for pb, ab in matched:
            app_w = max(1.0, float(ab["width"]))
            app_h = max(1.0, float(ab["height"]))
            prop_w = max(1.0, float(pb["width"]))
            prop_h = max(1.0, float(pb["height"]))

            dw_rel = abs(app_w - prop_w) / prop_w
            dh_rel = abs(app_h - prop_h) / prop_h
            if dw_rel >= 0.015 or dh_rel >= 0.015:
                stats["resized_boxes"] = int(stats.get("resized_boxes", 0)) + 1
                raw_w = float(pb.get("raw_width") or 0.0)
                raw_h = float(pb.get("raw_height") or 0.0)
                if raw_w > 0.0 and raw_h > 0.0:
                    imp_px = max(0.015, min(0.25, (app_w - raw_w) / (2.0 * raw_w)))
                    imp_py = max(0.015, min(0.25, (app_h - raw_h) / (2.0 * raw_h)))
                else:
                    cur_px = float(profile.get("pad_ratio_x", 0.075))
                    cur_py = float(profile.get("pad_ratio_y", 0.065))
                    imp_px = max(0.015, min(0.25, ((app_w / prop_w) * (1.0 + 2.0 * cur_px) - 1.0) * 0.5))
                    imp_py = max(0.015, min(0.25, ((app_h / prop_h) * (1.0 + 2.0 * cur_py) - 1.0) * 0.5))
                pad_x_samples.append(imp_px)
                pad_y_samples.append(imp_py)

            if abs(float(ab.get("angle_deg", 0.0)) - float(pb.get("angle_deg", 0.0))) >= 0.5:
                stats["rotated_boxes"] = int(stats.get("rotated_boxes", 0)) + 1

            aspect_samples.append(max(app_w, app_h) / max(1.0, min(app_w, app_h)))

        for ab in added:
            app_w = max(1.0, float(ab["width"]))
            app_h = max(1.0, float(ab["height"]))
            area_r = (app_w * app_h) / (pw * ph)
            if area_r < float(profile["min_area_ratio"]):
                profile["min_area_ratio"] = round(max(0.004, (1.0 - alpha) * float(profile["min_area_ratio"]) + alpha * area_r * 0.9), 5)
            elif area_r > float(profile["max_area_ratio"]):
                profile["max_area_ratio"] = round(min(0.75, (1.0 - alpha) * float(profile["max_area_ratio"]) + alpha * area_r * 1.05), 5)
            aspect_samples.append(max(app_w, app_h) / max(1.0, min(app_w, app_h)))

    # Count swapped pair_ids on backs
    matched_b, _, _ = _match_proposed_to_approved(proposed_back, approved_back, 0.18 * max(bw, bh))
    for pb, ab in matched_b:
        if int(ab.get("pair_id", -1)) != int(pb.get("pair_id", -2)):
            stats["swapped_pairs"] = int(stats.get("swapped_pairs", 0)) + 1

    if pad_x_samples:
        mean_px = float(np.mean(pad_x_samples))
        profile["pad_ratio_x"] = round(max(0.015, min(0.25, (1.0 - alpha) * float(profile["pad_ratio_x"]) + alpha * mean_px)), 4)
    if pad_y_samples:
        mean_py = float(np.mean(pad_y_samples))
        profile["pad_ratio_y"] = round(max(0.015, min(0.25, (1.0 - alpha) * float(profile["pad_ratio_y"]) + alpha * mean_py)), 4)
    if aspect_samples:
        mean_ar = float(np.mean(aspect_samples))
        profile["target_aspect_ratio"] = round(
            max(1.15, min(1.80, (1.0 - alpha) * float(profile["target_aspect_ratio"]) + alpha * mean_ar)),
            4,
        )
        min_seen = min(aspect_samples)
        max_seen = max(aspect_samples)
        if min_seen < float(profile["min_aspect_ratio"]):
            profile["min_aspect_ratio"] = round(max(1.02, min_seen * 0.95), 4)
        if max_seen > float(profile["max_aspect_ratio"]):
            profile["max_aspect_ratio"] = round(min(2.25, max_seen * 1.05), 4)

    # Measure pancake-flip spatial shifts from approved Front/Back pairs
    front_by_id = {int(b["pair_id"]): b for b in approved_front if "pair_id" in b}
    dx_list: list[float] = []
    dy_list: list[float] = []
    dang_list: list[float] = []
    for bb in approved_back:
        pid = int(bb.get("pair_id", -1))
        if pid not in front_by_id:
            continue
        fb = front_by_id[pid]
        fx = float(fb["cx"]) / fw
        fy = float(fb["cy"]) / fh
        bx = float(bb["cx"]) / bw
        by = float(bb["cy"]) / bh
        dx_list.append(min(abs(bx - fx), abs(bx - (1.0 - fx))))
        dy_list.append(abs(by - fy))
        dang_list.append(abs(float(bb.get("angle_deg", 0.0)) + float(fb.get("angle_deg", 0.0))))

    if dx_list:
        obs_tol_x = max(0.06, min(0.35, float(np.max(dx_list)) * 1.35))
        obs_tol_y = max(0.06, min(0.35, float(np.max(dy_list)) * 1.35))
        obs_tol_a = max(8.0, min(45.0, float(np.max(dang_list)) * 1.35))
        profile["pancake_tol_x"] = round((1.0 - alpha) * float(profile["pancake_tol_x"]) + alpha * obs_tol_x, 4)
        profile["pancake_tol_y"] = round((1.0 - alpha) * float(profile["pancake_tol_y"]) + alpha * obs_tol_y, 4)
        profile["pancake_tol_angle_deg"] = round((1.0 - alpha) * float(profile["pancake_tol_angle_deg"]) + alpha * obs_tol_a, 2)

    profile["sample_count"] = int(profile.get("sample_count", 0)) + 1
    return save_splitter_profile(profile, profile_path=profile_path)


# ==============================================================================
# 6. PRE-SPLIT STAGING, REVIEW LISTING & COMMIT WORKFLOW
# ==============================================================================
def _render_pdf_page_rgb(pdf_path: Path, page_idx: int, dpi: int) -> Optional[Image.Image]:
    try:
        doc = fitz.open(str(pdf_path))
        if page_idx >= len(doc):
            doc.close()
            return None
        page = doc.load_page(page_idx)
        zoom = float(dpi) / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return img
    except Exception:
        return None


def stage_image_pair_for_review(
    front_img_path: Path,
    back_img_path: Path,
    output_dir: Path,
    batch_name: str = "",
    stem_name: str = "",
    flip_mode: str = "auto",
    staging_dir: Optional[Path] = None,
    profile_path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """
    Detect multi-card boxes on a Front/Back image pair, auto-pair via pancake-flip
    matching, and stage in PENDING_REVIEW for human verification before cropping.
    """
    front_img_path = Path(front_img_path)
    back_img_path = Path(back_img_path)
    output_dir = Path(output_dir)
    stage_root = Path(staging_dir) if staging_dir is not None else Path(SPLITTER_STAGING_DIR)

    with Image.open(front_img_path) as im_f:
        front_im = im_f.convert("RGB")
    with Image.open(back_img_path) as im_b:
        back_im = im_b.convert("RGB")

    profile = load_splitter_profile(profile_path)
    f_boxes = detect_cards_on_page(front_im, profile=profile)
    b_boxes = detect_cards_on_page(back_im, profile=profile)
    if len(f_boxes) < 2 and len(b_boxes) < 2:
        return None

    paired_f, paired_b, chosen_mode = match_front_back_pancake(
        f_boxes, b_boxes, front_im.size, back_im.size, flip_mode=flip_mode, profile=profile
    )

    clean_stem = sanitize_filename_part(stem_name or front_img_path.stem)
    stage_id = f"{sanitize_filename_part(batch_name or output_dir.name)}_{clean_stem}_{uuid.uuid4().hex[:8]}"
    item_dir = stage_root / stage_id
    item_dir.mkdir(parents=True, exist_ok=True)

    front_preview = item_dir / "front.jpg"
    back_preview = item_dir / "back.jpg"
    front_im.save(front_preview, format="JPEG", quality=92)
    back_im.save(back_preview, format="JPEG", quality=92)

    stage_meta = {
        "stage_id": stage_id,
        "status": "PENDING_REVIEW",
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "batch_name": batch_name or output_dir.name,
        "output_dir": str(output_dir),
        "stem_name": clean_stem,
        "source_front_image": str(front_img_path),
        "source_back_image": str(back_img_path),
        "source_pdf": "",
        "front_image_url": f"/static/splitter/{stage_id}/front.jpg",
        "back_image_url": f"/static/splitter/{stage_id}/back.jpg",
        "front_size": [front_im.width, front_im.height],
        "back_size": [back_im.width, back_im.height],
        "flip_mode_detected": chosen_mode,
        "proposed_front_boxes": paired_f,
        "proposed_back_boxes": paired_b,
    }
    atomic_write_text(item_dir / "stage.json", json.dumps(stage_meta, indent=2), encoding="utf-8")
    return stage_meta


def stage_flatbed_pdfs_for_review(
    batch_folder: Path,
    pdf_files: Optional[list[Path]] = None,
    flip_mode: str = "auto",
    staging_dir: Optional[Path] = None,
    profile_path: Optional[Path] = None,
    preview_dpi: int = 200,
    log_cb: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    """
    Scan multi-card flatbed PDFs in `batch_folder`, detect oriented card boxes and
    pancake-flip pairings, and stage them in `PENDING_REVIEW` instead of blindly cropping.
    """
    batch_folder = Path(batch_folder)
    if pdf_files is None:
        pdf_files = sorted(batch_folder.glob("*.pdf"))

    stage_root = Path(staging_dir) if staging_dir is not None else Path(SPLITTER_STAGING_DIR)
    profile = load_splitter_profile(profile_path)
    staged_items: list[dict[str, Any]] = []

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

        if num_pages < 2 or (0.0 < max_pt_dim < 420.0):
            continue

        p1_img = _render_pdf_page_rgb(pdf_p, 0, dpi=preview_dpi)
        p2_img = _render_pdf_page_rgb(pdf_p, 1, dpi=preview_dpi)
        if p1_img is None or p2_img is None:
            continue

        f_boxes = detect_cards_on_page(p1_img, profile=profile)
        if len(f_boxes) < 2:
            continue
        b_boxes = detect_cards_on_page(p2_img, profile=profile)
        if not b_boxes:
            b_boxes = copy.deepcopy(f_boxes)

        paired_f, paired_b, chosen_mode = match_front_back_pancake(
            f_boxes, b_boxes, p1_img.size, p2_img.size, flip_mode=flip_mode, profile=profile
        )

        stage_id = f"{sanitize_filename_part(batch_folder.name)}_{sanitize_filename_part(pdf_p.stem)}_{uuid.uuid4().hex[:8]}"
        item_dir = stage_root / stage_id
        item_dir.mkdir(parents=True, exist_ok=True)
        p1_img.save(item_dir / "front.jpg", format="JPEG", quality=92)
        p2_img.save(item_dir / "back.jpg", format="JPEG", quality=92)

        stage_meta = {
            "stage_id": stage_id,
            "status": "PENDING_REVIEW",
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "batch_name": batch_folder.name,
            "output_dir": str(batch_folder),
            "stem_name": pdf_p.stem,
            "source_front_image": "",
            "source_back_image": "",
            "source_pdf": str(pdf_p),
            "front_image_url": f"/static/splitter/{stage_id}/front.jpg",
            "back_image_url": f"/static/splitter/{stage_id}/back.jpg",
            "front_size": [p1_img.width, p1_img.height],
            "back_size": [p2_img.width, p2_img.height],
            "flip_mode_detected": chosen_mode,
            "proposed_front_boxes": paired_f,
            "proposed_back_boxes": paired_b,
        }
        atomic_write_text(item_dir / "stage.json", json.dumps(stage_meta, indent=2), encoding="utf-8")
        staged_items.append(stage_meta)
        if log_cb:
            log_cb(f"  ⏸️ Staged '{pdf_p.name}' ({len(paired_f)} card pair(s)) for pre-split review [{stage_id}].")

    return staged_items


def list_pending_splitter_reviews(
    staging_dir: Optional[Path] = None,
    batch_name: str = "",
) -> list[dict[str, Any]]:
    """List all staged multi-card page pairs currently in PENDING_REVIEW."""
    stage_root = Path(staging_dir) if staging_dir is not None else Path(SPLITTER_STAGING_DIR)
    if not stage_root.exists():
        return []

    pending: list[dict[str, Any]] = []
    target_batch = str(batch_name or "").strip()
    for meta_file in sorted(stage_root.glob("*/stage.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("status") != "PENDING_REVIEW":
            continue
        if target_batch and str(meta.get("batch_name") or "") != target_batch:
            continue
        pending.append(meta)

    pending.sort(key=lambda m: str(m.get("created_at") or ""))
    return pending


def _scale_box(box: dict[str, Any], sx: float, sy: float) -> dict[str, Any]:
    scaled = dict(box)
    scaled["cx"] = float(box["cx"]) * sx
    scaled["cy"] = float(box["cy"]) * sy
    scaled["width"] = float(box["width"]) * sx
    scaled["height"] = float(box["height"]) * sy
    return scaled


def commit_staged_splitter_review(
    stage_id: str,
    front_boxes: list[dict[str, Any]],
    back_boxes: list[dict[str, Any]],
    staging_dir: Optional[Path] = None,
    profile_path: Optional[Path] = None,
    output_dpi: Optional[int] = None,
) -> dict[str, Any]:
    """
    Commit a user-reviewed multi-card split:
      1. Record diff between proposed and approved boxes into self-learning profile.
      2. Execute oriented crops paired strictly by `pair_id`.
      3. Write paired outputs (2-page `_FBCardNN.pdf` for PDFs, `_pairNN_F/B.jpg` for images).
      4. Mark the staged item as COMMITTED.
    """
    stage_root = Path(staging_dir) if staging_dir is not None else Path(SPLITTER_STAGING_DIR)
    meta_path = stage_root / str(stage_id).strip() / "stage.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Staged splitter review not found: {stage_id}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("status") != "PENDING_REVIEW":
        raise ValueError(f"Staged splitter review '{stage_id}' is not PENDING_REVIEW (status={meta.get('status')}).")

    front_size = tuple(int(x) for x in (meta.get("front_size") or [1, 1]))
    back_size = tuple(int(x) for x in (meta.get("back_size") or [1, 1]))

    updated_profile = record_splitter_user_feedback(
        proposed_front=list(meta.get("proposed_front_boxes") or []),
        proposed_back=list(meta.get("proposed_back_boxes") or []),
        approved_front=list(front_boxes or []),
        approved_back=list(back_boxes or []),
        front_size=(front_size[0], front_size[1]),
        back_size=(back_size[0], back_size[1]),
        profile_path=profile_path,
    )

    back_by_pid: dict[int, dict[str, Any]] = {}
    for bb in back_boxes:
        if "pair_id" in bb:
            back_by_pid[int(bb["pair_id"])] = bb

    ordered_fronts = sorted(front_boxes, key=lambda b: int(b.get("pair_id", 0)))
    output_dir = Path(meta.get("output_dir") or stage_root / stage_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem_name = str(meta.get("stem_name") or stage_id)
    dpi_val = int(output_dpi or RUNTIME_CONFIG.get("scanner_dpi", 600))

    src_pdf = Path(meta["source_pdf"]) if meta.get("source_pdf") else None
    created_files: list[str] = []

    if src_pdf and src_pdf.exists():
        p1_hi = _render_pdf_page_rgb(src_pdf, 0, dpi=dpi_val)
        p2_hi = _render_pdf_page_rgb(src_pdf, 1, dpi=dpi_val)
        if p1_hi is None or p2_hi is None:
            raise RuntimeError(f"Failed to render PDF pages for commit: {src_pdf}")

        sx_f = p1_hi.width / max(1.0, float(front_size[0]))
        sy_f = p1_hi.height / max(1.0, float(front_size[1]))
        sx_b = p2_hi.width / max(1.0, float(back_size[0]))
        sy_b = p2_hi.height / max(1.0, float(back_size[1]))

        for idx_c, fb in enumerate(ordered_fronts, 1):
            pid = int(fb.get("pair_id", idx_c))
            bb = back_by_pid.get(pid)
            if bb is None:
                continue
            c_front = crop_oriented_box(p1_hi, _scale_box(fb, sx_f, sy_f))
            c_back = crop_oriented_box(p2_hi, _scale_box(bb, sx_b, sy_b))

            out_pdf = output_dir / f"{stem_name}_FBCard{pid:02d}.pdf"
            new_doc = fitz.open()
            for side_im in (c_front, c_back):
                buf = io.BytesIO()
                side_im.save(buf, format="JPEG", quality=95)
                w_pt = side_im.width * 72.0 / float(dpi_val)
                h_pt = side_im.height * 72.0 / float(dpi_val)
                page = new_doc.new_page(width=w_pt, height=h_pt)
                page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=buf.getvalue())
            new_doc.save(str(out_pdf))
            new_doc.close()
            created_files.append(str(out_pdf))

        arc_fb_dir = output_dir / "Archive_Flatbed_Sheets"
        arc_fb_dir.mkdir(parents=True, exist_ok=True)
        try:
            src_pdf.replace(arc_fb_dir / src_pdf.name)
        except Exception:
            pass
    else:
        src_f_path = Path(meta.get("source_front_image") or (stage_root / stage_id / "front.jpg"))
        src_b_path = Path(meta.get("source_back_image") or (stage_root / stage_id / "back.jpg"))
        with Image.open(src_f_path) as im_f:
            f_hi = im_f.convert("RGB")
        with Image.open(src_b_path) as im_b:
            b_hi = im_b.convert("RGB")

        sx_f = f_hi.width / max(1.0, float(front_size[0]))
        sy_f = f_hi.height / max(1.0, float(front_size[1]))
        sx_b = b_hi.width / max(1.0, float(back_size[0]))
        sy_b = b_hi.height / max(1.0, float(back_size[1]))

        for idx_c, fb in enumerate(ordered_fronts, 1):
            pid = int(fb.get("pair_id", idx_c))
            bb = back_by_pid.get(pid)
            if bb is None:
                continue
            c_front = crop_oriented_box(f_hi, _scale_box(fb, sx_f, sy_f))
            c_back = crop_oriented_box(b_hi, _scale_box(bb, sx_b, sy_b))

            out_f = output_dir / f"{stem_name}_pair{pid:02d}_F.jpg"
            out_b = output_dir / f"{stem_name}_pair{pid:02d}_B.jpg"
            c_front.save(out_f, format="JPEG", quality=95)
            c_back.save(out_b, format="JPEG", quality=95)
            created_files.extend([str(out_f), str(out_b)])

    meta["status"] = "COMMITTED"
    meta["committed_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    meta["approved_front_boxes"] = ordered_fronts
    meta["approved_back_boxes"] = list(back_boxes)
    meta["created_files"] = created_files
    atomic_write_text(meta_path, json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "success": True,
        "stageId": stage_id,
        "createdCount": len(created_files),
        "createdFiles": created_files,
        "learningProfile": updated_profile,
    }
