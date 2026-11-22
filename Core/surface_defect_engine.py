from __future__ import annotations
# ==============================================================================
# Core/surface_defect_engine.py - GPU WIN #4: THROUGH-SLEEVE SURFACE DEFECT &
#                                 SUPERFICIAL ARTIFACT DISCRIMINATION ENGINE
#   - Inspects Front & Back scans inside penny sleeves, toploaders & Card Saver 1
#   - Uses OpenCV OpenCL (cv2.UMat) filter bank + DINOv2 patch-token anomaly
#     + optional card_defect_v1.onnx classifier with 100% automatic CPU fallback
#   - Separates permanent card defects (scratches, print lines, dimples/dents,
#     fisheyes, edge chipping, 8-corner whitening) from removable artifacts
#     (specular glare, border-crossing sleeve scratches, hairs, dust, smudges)
# ==============================================================================
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from Core.compute_backend import load_compute_settings, opencl_defect_filter_bank
from Core.neural_vision import (
    compute_dinov2_patch_anomaly_map,
    get_local_defect_model,
    get_neural_embedding_engine,
    is_neural_embeddings_enabled,
)

__version__ = "0.25.0-beta.2"
__last_updated__ = "2026-11-21 23:15:00"

_CONFIRMED_DEFECT_CONF_MIN = 0.60
_MARGIN_MIN_PX = 8
_MARGIN_PAD_PX = 28


_DEFECT_LABEL_MAP = {
    "surface_scratch": "surface scratch",
    "print_line": "print line",
    "dimple_dent": "dimple/dent",
    "print_spot_fisheye": "print spot/fisheye",
    "corner_whitening": "corner whitening",
    "edge_chipping": "edge chipping",
    "specular_glare": "specular glare",
    "loose_dust_speck": "loose dust speck",
    "hair_fiber": "hair/fiber",
    "sleeve_scratch_or_static_streak": "sleeve scratch/streak",
    "sleeve_smudge": "sleeve smudge/haze",
    "scanner_streak": "scanner glass/sensor streak",
    "edge_dent": "edge dent/ding",
}

_MARKER_STYLE_MAP = {
    "surface_scratch": "box",
    "print_line": "box",
    "print_spot_fisheye": "circle",
    "dimple_dent": "circle",
    "corner_whitening": "circle",
    "edge_chipping": "arrow",
    "edge_dent": "arrow",
}


def _cluster_and_nms_defects(defects: list[dict], dist_thresh: float = 0.035) -> list[dict]:
    """
    Spatial clustering / Non-Maximum Suppression on same-side defects:
    merges overlapping or nearby detections (normalized center distance <= `dist_thresh`)
    into a single defect with union `bbox_norm` and highest severity/confidence.
    """
    if len(defects) <= 1:
        return defects

    def _boxes_close(a: dict, b: dict) -> bool:
        if str(a.get("side") or "") != str(b.get("side") or ""):
            return False
        ba = a.get("bbox_norm")
        bb = b.get("bbox_norm")
        if not (isinstance(ba, list) and len(ba) == 4 and isinstance(bb, list) and len(bb) == 4):
            return False
        ax1, ay1, aw, ah = ba
        bx1, by1, bw, bh = bb
        ax2, ay2 = ax1 + aw, ay1 + ah
        bx2, by2 = bx1 + bw, by1 + bh
        # Overlap check
        if ax1 <= bx2 and ax2 >= bx1 and ay1 <= by2 and ay2 >= by1:
            return True
        # Center distance check
        acx, acy = ax1 + aw * 0.5, ay1 + ah * 0.5
        bcx, bcy = bx1 + bw * 0.5, by1 + bh * 0.5
        return float(np.hypot(acx - bcx, acy - bcy)) <= dist_thresh

    n = len(defects)
    visited = [False] * n
    merged: list[dict] = []

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        cluster = [defects[i]]
        queue = [i]
        while queue:
            cur = queue.pop(0)
            for j in range(n):
                if not visited[j] and _boxes_close(defects[cur], defects[j]):
                    visited[j] = True
                    cluster.append(defects[j])
                    queue.append(j)

        if len(cluster) == 1:
            merged.append(cluster[0])
            continue

        # Pick representative with highest severity, then highest confidence
        rep = dict(max(cluster, key=lambda d: (float(d.get("severity", 0.5)), float(d.get("confidence", 0.0)))))
        valid_boxes = [d["bbox_norm"] for d in cluster if isinstance(d.get("bbox_norm"), list) and len(d["bbox_norm"]) == 4]
        if valid_boxes:
            ux1 = min(b[0] for b in valid_boxes)
            uy1 = min(b[1] for b in valid_boxes)
            ux2 = max(b[0] + b[2] for b in valid_boxes)
            uy2 = max(b[1] + b[3] for b in valid_boxes)
            rep["bbox_norm"] = [round(ux1, 4), round(uy1, 4), round(max(0.002, ux2 - ux1), 4), round(max(0.002, uy2 - uy1), 4)]
        rep["confidence"] = round(max(float(d.get("confidence", 0.0)) for d in cluster), 3)
        rep["severity"] = max(float(d.get("severity", 0.5)) for d in cluster)
        rep["penalty"] = round(float(rep["severity"]), 2)
        merged.append(rep)

    return merged


def _round_half_grade(val: float, lo: float = 5.0, hi: float = 10.0) -> float:
    clamped = float(np.clip(val, lo, hi))
    return round(round(clamped * 2.0) / 2.0, 1)


def _zone_label(cx: float, cy: float, cw: int, ch: int) -> str:
    v = "top" if cy < ch * 0.33 else ("bot" if cy > ch * 0.67 else "mid")
    h = "left" if cx < cw * 0.33 else ("right" if cx > cw * 0.67 else "center")
    return f"{v}-{h}"


def _roi_bbox_to_norm(
    bbox_roi: tuple[int, int, int, int],
    roi_origin: tuple[int, int],
    img_size: tuple[int, int],
) -> list[float]:
    """Converts ROI-local `(x, y, w, h)` to full-image normalized `[x, y, w, h]` in `[0.0, 1.0]`."""
    iw = max(1.0, float(img_size[0]))
    ih = max(1.0, float(img_size[1]))
    ox, oy = roi_origin
    bx, by, bw, bh = bbox_roi
    nx1 = float(np.clip((ox + bx) / iw, 0.0, 0.998))
    ny1 = float(np.clip((oy + by) / ih, 0.0, 0.998))
    nx2 = float(np.clip((ox + bx + max(1, bw)) / iw, nx1 + 0.002, 1.0))
    ny2 = float(np.clip((oy + by + max(1, bh)) / ih, ny1 + 0.002, 1.0))
    return [round(nx1, 4), round(ny1, 4), round(nx2 - nx1, 4), round(ny2 - ny1, 4)]


def _stable_defect_id(side_label: str, dtype: str, bbox_norm: list[float], used_ids: set[str]) -> str:
    """Deterministic ID from side + type + quantized center so overrides survive re-runs."""
    cx = bbox_norm[0] + bbox_norm[2] * 0.5
    cy = bbox_norm[1] + bbox_norm[3] * 0.5
    base = f"{side_label.lower()}-{dtype}-{int(round(cx * 50)):02d}-{int(round(cy * 50)):02d}"
    if base not in used_ids:
        used_ids.add(base)
        return base
    idx = 2
    while f"{base}-{idx}" in used_ids:
        idx += 1
    cand = f"{base}-{idx}"
    used_ids.add(cand)
    return cand


def _extract_roi_with_margin(
    img: Image.Image,
    card_box: tuple[int, int, int, int],
    pad_px: int = _MARGIN_PAD_PX,
) -> tuple[np.ndarray, tuple[int, int, int, int], dict[str, bool], tuple[int, int]]:
    w, h = img.size
    x1, y1, x2, y2 = [int(v) for v in card_box]
    x1 = max(0, min(w - 20, x1))
    y1 = max(0, min(h - 20, y1))
    x2 = max(x1 + 20, min(w, x2))
    y2 = max(y1 + 20, min(h, y2))

    ml, mt, mr, mb = x1, y1, w - x2, h - y2
    margin_avail = {
        "left": ml >= _MARGIN_MIN_PX,
        "top": mt >= _MARGIN_MIN_PX,
        "right": mr >= _MARGIN_MIN_PX,
        "bottom": mb >= _MARGIN_MIN_PX,
    }

    rx1 = max(0, x1 - pad_px)
    ry1 = max(0, y1 - pad_px)
    rx2 = min(w, x2 + pad_px)
    ry2 = min(h, y2 + pad_px)

    roi_rgb = np.array(img.crop((rx1, ry1, rx2, ry2)).convert("RGB"))
    local_box = (x1 - rx1, y1 - ry1, x2 - rx1, y2 - ry1)
    return roi_rgb, local_box, margin_avail, (rx1, ry1)


def _detect_specular_glare_mask(
    lab: np.ndarray,
    hsv: np.ndarray,
    lap_abs: np.ndarray,
    local_box: tuple[int, int, int, int],
) -> tuple[np.ndarray, float]:
    """Detects broad plastic sleeve/toploader specular glare bands so they are masked & warned."""
    cx1, cy1, cx2, cy2 = local_box
    l_ch = lab[:, :, 0]
    s_ch = hsv[:, :, 1]
    smooth_lap = cv2.GaussianBlur(lap_abs.astype(np.float32), (9, 9), 2.0)

    raw_glare = ((l_ch > 235) & (s_ch < 24) & (smooth_lap < 22.0)).astype(np.uint8)
    num_lbls, lbls, stats, _ = cv2.connectedComponentsWithStats(raw_glare, connectivity=8)

    glare_mask = np.zeros(l_ch.shape, dtype=np.uint8)
    for idx in range(1, num_lbls):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area >= 120:
            glare_mask[lbls == idx] = 255

    card_area = max(1, (cx2 - cx1) * (cy2 - cy1))
    glare_in_card = int(np.count_nonzero(glare_mask[cy1:cy2, cx1:cx2]))
    glare_pct = round(100.0 * glare_in_card / float(card_area), 1)
    glare_dilated = cv2.dilate(glare_mask, np.ones((5, 5), dtype=np.uint8), iterations=1)
    return glare_dilated > 0, glare_pct


def _estimate_margin_dust_density(
    tophat: np.ndarray,
    blackhat: np.ndarray,
    local_box: tuple[int, int, int, int],
    margin_avail: dict[str, bool],
) -> float:
    """Samples outer holder margin ring (when >= 8 px available) for loose dust specks."""
    if not any(margin_avail.values()):
        return 0.0
    h, w = tophat.shape
    cx1, cy1, cx2, cy2 = local_box
    ring_mask = np.ones((h, w), dtype=bool)
    ring_mask[max(0, cy1 - 3):min(h, cy2 + 3), max(0, cx1 - 3):min(w, cx2 + 3)] = False
    ring_area = int(np.count_nonzero(ring_mask))
    if ring_area < 200:
        return 0.0

    resp = np.maximum(tophat, blackhat)
    specks = ((resp > 28) & ring_mask).astype(np.uint8)
    num_l, _, stats, _ = cv2.connectedComponentsWithStats(specks, connectivity=8)
    dust_cnt = 0
    for i in range(1, num_l):
        a = int(stats[i, cv2.CC_STAT_AREA])
        if 2 <= a <= 32:
            dust_cnt += 1
    return round(dust_cnt * 10000.0 / float(ring_area), 3)


def _check_line_crosses_margin(
    resp: np.ndarray,
    cnt: np.ndarray,
    local_box: tuple[int, int, int, int],
    margin_avail: dict[str, bool],
    offset_xy: tuple[int, int],
) -> bool:
    """Traces an elongated candidate along its major axis to see if it crosses into holder margin."""
    if not any(margin_avail.values()):
        return False
    cx1, cy1, cx2, cy2 = local_box
    ox, oy = offset_xy
    pts = cnt.reshape(-1, 2).astype(np.float32)
    pts[:, 0] += ox
    pts[:, 1] += oy
    if len(pts) < 4:
        return False

    vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
    h, w = resp.shape

    def _probe_side(sign: float) -> bool:
        hits = 0
        steps = 0
        for d in range(4, 30, 2):
            px = int(round(x0 + sign * vx * d))
            py = int(round(y0 + sign * vy * d))
            if px < 0 or px >= w or py < 0 or py >= h:
                break
            in_card = (cx1 <= px < cx2) and (cy1 <= py < cy2)
            if in_card:
                continue
            side_ok = (
                (px < cx1 and margin_avail["left"])
                or (px >= cx2 and margin_avail["right"])
                or (py < cy1 and margin_avail["top"])
                or (py >= cy2 and margin_avail["bottom"])
            )
            if not side_ok:
                break
            steps += 1
            patch = resp[max(0, py - 2):min(h, py + 3), max(0, px - 2):min(w, px + 3)]
            if patch.size > 0 and int(np.max(patch)) > 24:
                hits += 1
        return steps >= 3 and (hits / float(steps)) >= 0.35

    # Only probe if the component is reasonably near a card border (< 36 px)
    min_x, max_x = float(np.min(pts[:, 0])), float(np.max(pts[:, 0]))
    min_y, max_y = float(np.min(pts[:, 1])), float(np.max(pts[:, 1]))
    near_border = (
        (min_x - cx1 < 36 and margin_avail["left"])
        or (cx2 - max_x < 36 and margin_avail["right"])
        or (min_y - cy1 < 36 and margin_avail["top"])
        or (cy2 - max_y < 36 and margin_avail["bottom"])
    )
    if not near_border:
        return False
    return _probe_side(1.0) or _probe_side(-1.0)


def _detect_scanner_streaks(
    roi_rgb: np.ndarray,
    local_box: tuple[int, int, int, int],
    margin_avail: dict[str, bool],
    side_label: str,
) -> tuple[list[tuple[dict, tuple[int, int, int, int]]], np.ndarray]:
    """
    Detects duplex ADF / CIS scanner glass & sensor streaks:
      - Strictly vertical or horizontal (zero lateral wobble < 0.8 px, 1-4 px wide)
      - Continuous edge-to-edge (>= 92% of full ROI) OR crosses past `card_box` into `margin_ring`
      - Uniform intensity offset or single-channel RGB/CIS color cast independent of artwork.
    Returns `(list_of_(artifact_dict, roi_bbox), boolean_mask_to_suppress)`.
    """
    h, w = roi_rgb.shape[:2]
    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)
    streak_mask = np.zeros((h, w), dtype=bool)
    found: list[tuple[dict, tuple[int, int, int, int]]] = []

    if h < 40 or w < 40:
        return found, streak_mask

    f_rgb = roi_rgb.astype(np.float32)

    # Helper to scan 1 axis: vertical streaks (axis='v') or horizontal streaks (axis='h')
    def _scan_axis(axis: str):
        if axis == "v":
            if w < 16:
                return
            ref = 0.5 * (f_rgb[:, :-8, :] + f_rgb[:, 8:, :])
            diff = np.abs(f_rgb[:, 4:-4, :] - ref)
            max_ch = np.max(diff, axis=2)
            # 1D fraction along full ROI height & inside card height
            hit_full = (max_ch > 15.0)
            col_frac_full = np.mean(hit_full, axis=0)
            col_frac_card = np.mean(hit_full[cy1:cy2, :], axis=0)
            # Single-channel color cast (CIS RGB offset)
            med_ch_diff = np.median(diff, axis=0)  # (W-8, 3)
            cast_strength = np.max(med_ch_diff, axis=1) - np.min(med_ch_diff, axis=1)

            cand_idx = np.where((col_frac_card >= 0.72) & ((col_frac_full >= 0.90) | (np.mean(hit_full, axis=0) >= 0.72)))[0]
            if cand_idx.size == 0:
                return
            # Group contiguous columns (within 1 px)
            groups: list[list[int]] = []
            for idx in cand_idx.tolist():
                if not groups or idx - groups[-1][-1] > 1:
                    groups.append([idx])
                else:
                    groups[-1].append(idx)

            for grp in groups:
                width_px = len(grp)
                if width_px < 1 or width_px > 5:
                    continue
                x0 = grp[0] + 4
                x1 = grp[-1] + 4
                # Check straightness / wobble: peak column inside [x0-1 .. x1+1] across 8 vertical slices
                band_l = max(0, x0 - 1)
                band_r = min(w, x1 + 2)
                slice_peaks = []
                for s_i in range(8):
                    sy0 = int(s_i * h / 8)
                    sy1 = int((s_i + 1) * h / 8)
                    if sy1 <= sy0:
                        continue
                    prof = np.mean(np.abs(f_rgb[sy0:sy1, band_l:band_r, :] - np.median(f_rgb[sy0:sy1, max(0, x0 - 4):min(w, x1 + 5), :], axis=1, keepdims=True)), axis=(0, 2))
                    if prof.size > 0:
                        slice_peaks.append(band_l + float(np.argmax(prof)))
                wobble = float(np.std(slice_peaks)) if len(slice_peaks) >= 4 else 0.0
                if wobble >= 0.8:
                    continue

                # Check margin continuity OR >= 92% edge-to-edge continuity
                full_span_frac = float(np.max(col_frac_full[grp]))
                crosses_margin = False
                if margin_avail.get("top") and cy1 >= 4:
                    m_top = hit_full[:cy1, [g for g in grp]]
                    if m_top.size > 0 and float(np.mean(np.max(m_top, axis=1))) >= 0.50:
                        crosses_margin = True
                if margin_avail.get("bottom") and cy2 <= h - 4:
                    m_bot = hit_full[cy2:, [g for g in grp]]
                    if m_bot.size > 0 and float(np.mean(np.max(m_bot, axis=1))) >= 0.50:
                        crosses_margin = True

                if not (crosses_margin or full_span_frac >= 0.92):
                    continue

                max_cast = float(np.max(cast_strength[grp]))
                conf = round(min(0.97, 0.86 + (0.05 if crosses_margin else 0.0) + (0.04 if max_cast >= 12.0 else 0.0)), 3)
                pad_l = max(0, x0 - 3)
                pad_r = min(w, x1 + 4)
                streak_mask[:, pad_l:pad_r] = True
                z_lbl = _zone_label((x0 + x1) * 0.5 - cx1, ch * 0.5, cw, ch)
                found.append(({
                    "type": "scanner_streak",
                    "is_true_defect": False,
                    "confidence": conf,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                    "detail": "Scanner glass/sensor streak — clean scanner glass & rescan",
                }, (int(x0), 0, max(2, int(x1 - x0 + 1)), int(h))))
        else:
            if h < 16:
                return
            ref = 0.5 * (f_rgb[:-8, :, :] + f_rgb[8:, :, :])
            diff = np.abs(f_rgb[4:-4, :, :] - ref)
            max_ch = np.max(diff, axis=2)
            hit_full = (max_ch > 15.0)
            row_frac_full = np.mean(hit_full, axis=1)
            row_frac_card = np.mean(hit_full[:, cx1:cx2], axis=1)
            med_ch_diff = np.median(diff, axis=1)
            cast_strength = np.max(med_ch_diff, axis=1) - np.min(med_ch_diff, axis=1)

            cand_idx = np.where((row_frac_card >= 0.72) & ((row_frac_full >= 0.90) | (np.mean(hit_full, axis=1) >= 0.72)))[0]
            if cand_idx.size == 0:
                return
            groups = []
            for idx in cand_idx.tolist():
                if not groups or idx - groups[-1][-1] > 1:
                    groups.append([idx])
                else:
                    groups[-1].append(idx)

            for grp in groups:
                height_px = len(grp)
                if height_px < 1 or height_px > 5:
                    continue
                y0 = grp[0] + 4
                y1 = grp[-1] + 4
                band_t = max(0, y0 - 1)
                band_b = min(h, y1 + 2)
                slice_peaks = []
                for s_i in range(8):
                    sx0 = int(s_i * w / 8)
                    sx1 = int((s_i + 1) * w / 8)
                    if sx1 <= sx0:
                        continue
                    prof = np.mean(np.abs(f_rgb[band_t:band_b, sx0:sx1, :] - np.median(f_rgb[max(0, y0 - 4):min(h, y1 + 5), sx0:sx1, :], axis=0, keepdims=True)), axis=(1, 2))
                    if prof.size > 0:
                        slice_peaks.append(band_t + float(np.argmax(prof)))
                wobble = float(np.std(slice_peaks)) if len(slice_peaks) >= 4 else 0.0
                if wobble >= 0.8:
                    continue

                full_span_frac = float(np.max(row_frac_full[grp]))
                crosses_margin = False
                if margin_avail.get("left") and cx1 >= 4:
                    m_left = hit_full[[g for g in grp], :cx1]
                    if m_left.size > 0 and float(np.mean(np.max(m_left, axis=0))) >= 0.50:
                        crosses_margin = True
                if margin_avail.get("right") and cx2 <= w - 4:
                    m_right = hit_full[[g for g in grp], cx2:]
                    if m_right.size > 0 and float(np.mean(np.max(m_right, axis=0))) >= 0.50:
                        crosses_margin = True

                if not (crosses_margin or full_span_frac >= 0.92):
                    continue

                max_cast = float(np.max(cast_strength[grp]))
                conf = round(min(0.97, 0.86 + (0.05 if crosses_margin else 0.0) + (0.04 if max_cast >= 12.0 else 0.0)), 3)
                pad_t = max(0, y0 - 3)
                pad_b = min(h, y1 + 4)
                streak_mask[pad_t:pad_b, :] = True
                z_lbl = _zone_label(cw * 0.5, (y0 + y1) * 0.5 - cy1, cw, ch)
                found.append(({
                    "type": "scanner_streak",
                    "is_true_defect": False,
                    "confidence": conf,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                    "detail": "Scanner glass/sensor streak — clean scanner glass & rescan",
                }, (0, int(y0), int(w), max(2, int(y1 - y0 + 1)))))

    _scan_axis("v")
    _scan_axis("h")
    return found, streak_mask


def _inspect_single_side(
    img: Image.Image,
    card_box: tuple[int, int, int, int],
    side_label: str,
    patch_tokens: Optional[np.ndarray] = None,
    enable_onnx_anomaly: bool = True,
    force_cpu: bool = False,
    overrides: Optional[dict] = None,
) -> dict:
    ov = overrides if isinstance(overrides, dict) else {}
    light_border_mode = bool(ov.get("light_border_mode", False))
    dismissed_ids = {str(x).strip() for x in (ov.get("dismissed_defect_ids") or []) if str(x).strip()}
    img_size = img.size

    roi_rgb, local_box, margin_avail, roi_origin = _extract_roi_with_margin(img, card_box)
    fb = opencl_defect_filter_bank(roi_rgb, force_cpu=force_cpu)
    lab = fb["lab"]
    hsv = fb["hsv"]
    gray = fb["gray"]
    tophat = fb["tophat"]
    blackhat = fb["blackhat"]
    lap_abs = fb["lap_abs"]
    dog_signed = fb["dog_signed"]
    backend_used = fb["backend"]

    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)

    glare_mask, glare_pct = _detect_specular_glare_mask(lab, hsv, lap_abs, local_box)
    margin_dust_density = _estimate_margin_dust_density(tophat, blackhat, local_box, margin_avail)
    scanner_streaks, streak_mask = _detect_scanner_streaks(roi_rgb, local_box, margin_avail, side_label)

    # Optional DINOv2 patch-token spatial anomaly map (reuses Track 2A tokens when provided)
    anom_map = None
    if enable_onnx_anomaly:
        if patch_tokens is not None:
            anom_map = compute_dinov2_patch_anomaly_map(patch_tokens)
        elif is_neural_embeddings_enabled():
            try:
                eng = get_neural_embedding_engine(load_now=True)
                if eng is not None and eng.is_ready:
                    card_rgb = roi_rgb[cy1:cy2, cx1:cx2]
                    desc = eng.extract_descriptor(card_rgb, include_color_foil=False, include_patch_tokens=True)
                    if isinstance(desc, dict) and desc.get("patch_tokens") is not None:
                        anom_map = compute_dinov2_patch_anomaly_map(desc["patch_tokens"])
            except Exception:
                anom_map = None

    def _anom_boost(x_card: float, y_card: float) -> float:
        if anom_map is None:
            return 0.0
        gh, gw = anom_map.shape
        gx = int(np.clip((x_card / float(cw)) * gw, 0, gw - 1))
        gy = int(np.clip((y_card / float(ch)) * gh, 0, gh - 1))
        return 0.08 if float(anom_map[gy, gx]) > 0.28 else 0.0

    confirmed: list[dict] = []
    artifacts: list[dict] = []
    used_ids: set[str] = set()

    def _attach_meta(item: dict, bbox_roi: tuple[int, int, int, int]) -> dict:
        b_norm = _roi_bbox_to_norm(bbox_roi, roi_origin, img_size)
        dtype = str(item.get("type") or "defect")
        is_true = bool(item.get("is_true_defect"))
        item["bbox"] = tuple(int(v) for v in bbox_roi)
        item["bbox_norm"] = b_norm
        item["id"] = _stable_defect_id(side_label, dtype, b_norm, used_ids)
        if is_true:
            tgt = str(item.get("target") or "surface").lower()
            item["category"] = tgt
            item["penalty"] = round(float(item.get("severity", 0.5)), 2)
            item["marker_style"] = _MARKER_STYLE_MAP.get(dtype, "circle")
            pretty = _DEFECT_LABEL_MAP.get(dtype, dtype.replace("_", " "))
            item["label"] = f"{side_label} {pretty} ({item.get('zone', 'surface')})"
        else:
            pretty = _DEFECT_LABEL_MAP.get(dtype, dtype.replace("_", " "))
            item["label"] = f"{side_label} {pretty} (ignored)"
        return item

    if glare_pct >= 3.5:
        gl_in = glare_mask[cy1:cy2, cx1:cx2]
        ys_g, xs_g = np.where(gl_in)
        if xs_g.size > 0 and ys_g.size > 0:
            gx1 = int(cx1 + np.min(xs_g))
            gy1 = int(cy1 + np.min(ys_g))
            gw_g = max(8, int(np.max(xs_g) - np.min(xs_g) + 1))
            gh_g = max(8, int(np.max(ys_g) - np.min(ys_g) + 1))
            glare_bbox = (gx1, gy1, gw_g, gh_g)
        else:
            glare_bbox = (cx1, cy1, cw, ch)
        artifacts.append(_attach_meta({
            "type": "specular_glare",
            "is_true_defect": False,
            "confidence": round(min(0.98, 0.65 + glare_pct / 40.0), 3),
            "side": side_label,
            "zone": "surface",
            "severity": 0.0,
            "detail": f"{glare_pct:.0f}% glare",
        }, glare_bbox))

    for st_item, st_bbox in scanner_streaks:
        artifacts.append(_attach_meta(st_item, st_bbox))

    # Interior region inset from card border to avoid printed border edge lines
    inset = max(6, int(min(cw, ch) * 0.02))
    ix1, iy1 = cx1 + inset, cy1 + inset
    ix2, iy2 = max(ix1 + 16, cx2 - inset), max(iy1 + 16, cy2 - inset)

    surf_resp = np.maximum(tophat, blackhat)
    int_resp = surf_resp[iy1:iy2, ix1:ix2].copy()
    int_glare = glare_mask[iy1:iy2, ix1:ix2] | streak_mask[iy1:iy2, ix1:ix2]
    int_resp[int_glare] = 0

    thr_surf = max(32, int(np.percentile(int_resp, 99.3)))
    cand_bin = (int_resp > thr_surf).astype(np.uint8)
    cnts, _ = cv2.findContours(cand_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in cnts:
        area = float(cv2.contourArea(cnt))
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if area < 4.0 and max(bw, bh) < 4:
            continue
        cx_c = bx + bw * 0.5 + inset
        cy_c = by + bh * 0.5 + inset
        z_lbl = _zone_label(cx_c, cy_c, cw, ch)

        # Printed design/artwork boundary check: a surface defect or dust speck sits on a
        # locally continuous background (flanks on both sides have similar luminance), whereas
        # a printed card frame/artwork edge separates two different regions (large flank step-edge).
        rcx = int(np.clip(ix1 + bx + bw * 0.5, ix1 + 6, ix2 - 7))
        rcy = int(np.clip(iy1 + by + bh * 0.5, iy1 + 6, iy2 - 7))
        flank_x = abs(float(lab[rcy, rcx + 6, 0]) - float(lab[rcy, rcx - 6, 0]))
        flank_y = abs(float(lab[rcy + 6, rcx, 0]) - float(lab[rcy - 6, rcx, 0]))
        if max(flank_x, flank_y) > 22.0:
            continue

        rect = cv2.minAreaRect(cnt)
        rw, rh = rect[1]
        major = max(float(rw), float(rh))
        minor = max(1.0, min(float(rw), float(rh)))
        aspect = major / minor

        # A. Linear candidates (Scratches, Print Lines, Sleeve Scratches, Hairs/Fibers)
        if major >= 18.0 and aspect >= 3.2:
            # Printed-artwork texture/stripe guard: skip dense halftone/text or wide chromatic printed stripes
            nb_lap = lap_abs[max(iy1, rcy - 9):min(iy2, rcy + 10), max(ix1, rcx - 9):min(ix2, rcx + 10)]
            edge_density = float(np.mean(nb_lap > 30.0)) if nb_lap.size else 0.0
            cand_roi_mask = cand_bin[by:by + bh, bx:bx + bw] > 0
            cand_sat_patch = hsv[iy1 + by:iy1 + by + bh, ix1 + bx:ix1 + bx + bw, 1]
            cand_med_sat = float(np.median(cand_sat_patch[cand_roi_mask])) if np.any(cand_roi_mask) and cand_sat_patch.shape == cand_roi_mask.shape else 0.0
            if edge_density > 0.42 or (cand_med_sat > 75.0 and minor >= 3.5):
                continue

            arc_half = cv2.arcLength(cnt, True) * 0.5
            tortuosity = arc_half / max(1.0, major)
            fill_ratio = area / max(1.0, float(bw * bh))

            if tortuosity > 1.18 or (minor / max(1.0, major) > 0.24 and fill_ratio < 0.35):
                artifacts.append(_attach_meta({
                    "type": "hair_fiber",
                    "is_true_defect": False,
                    "confidence": 0.82,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                }, (int(bx + ix1), int(by + iy1), int(bw), int(bh))))
                continue

            crosses_margin = _check_line_crosses_margin(
                surf_resp, cnt, local_box, margin_avail, (ix1, iy1)
            )
            if crosses_margin:
                artifacts.append(_attach_meta({
                    "type": "sleeve_scratch_or_static_streak",
                    "is_true_defect": False,
                    "confidence": 0.86,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                }, (int(bx + ix1), int(by + iy1), int(bw), int(bh))))
                continue

            # Check axis alignment for factory print lines (horizontal or vertical)
            ang = abs(float(rect[2])) % 90.0
            is_axis_aligned = (ang <= 2.5) or (abs(ang - 90.0) <= 2.5)
            is_long_span = (
                (bw >= cw * 0.32 and bh <= 10)
                or (bh >= ch * 0.32 and bw <= 10)
            )
            if is_axis_aligned and is_long_span and minor <= 8.5:
                conf = min(0.96, 0.78 + _anom_boost(cx_c, cy_c))
                confirmed.append(_attach_meta({
                    "type": "print_line",
                    "is_true_defect": True,
                    "confidence": round(conf, 3),
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.5,
                    "target": "surface",
                }, (int(bx + ix1), int(by + iy1), int(bw), int(bh))))
            elif minor <= 9.0 and major >= 22.0:
                conf = min(0.95, 0.72 + min(0.18, major / 250.0) + _anom_boost(cx_c, cy_c))
                sev = 1.0 if major >= 75.0 else 0.5
                confirmed.append(_attach_meta({
                    "type": "surface_scratch",
                    "is_true_defect": True,
                    "confidence": round(conf, 3),
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": sev,
                    "target": "surface",
                }, (int(bx + ix1), int(by + iy1), int(bw), int(bh))))
            continue

        # B. Compact blobs: Fisheye Print Spot vs. Loose Dust Speck
        if 4.0 <= area <= 240.0 and aspect < 3.2:
            gx_c = int(ix1 + bx + bw * 0.5)
            gy_c = int(iy1 + by + bh * 0.5)
            r_core = max(2, int(round(np.sqrt(area / np.pi))))
            y_lo, y_hi = max(iy1, gy_c - r_core - 8), min(iy2, gy_c + r_core + 9)
            x_lo, x_hi = max(ix1, gx_c - r_core - 8), min(ix2, gx_c + r_core + 9)
            patch_l = lab[y_lo:y_hi, x_lo:x_hi, 0].astype(np.float32)
            halo_diff = 0.0
            if patch_l.size >= 36:
                yy, xx = np.ogrid[y_lo:y_hi, x_lo:x_hi]
                dist = np.sqrt((xx - gx_c) ** 2 + (yy - gy_c) ** 2)
                r_in = max(1.5, r_core * 0.5)
                ring_m = (dist > r_in) & (dist <= r_core + 2.5)
                outer_m = (dist > r_core + 3.5) & (dist <= r_core + 8.0)
                if np.any(ring_m) and np.any(outer_m):
                    halo_diff = abs(float(np.mean(patch_l[ring_m])) - float(np.mean(patch_l[outer_m])))

            perim = max(1.0, cv2.arcLength(cnt, True))
            circularity = float(4.0 * np.pi * area / (perim * perim))

            if area >= 18.0 and halo_diff >= 9.5 and circularity >= 0.48:
                conf = min(0.94, 0.68 + min(0.18, halo_diff / 60.0) + _anom_boost(cx_c, cy_c))
                confirmed.append(_attach_meta({
                    "type": "print_spot_fisheye",
                    "is_true_defect": True,
                    "confidence": round(conf, 3),
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.5,
                    "target": "surface",
                }, (int(bx + ix1), int(by + iy1), int(bw), int(bh))))
            elif area <= 32.0 or margin_dust_density >= 0.25 or halo_diff < 9.5:
                artifacts.append(_attach_meta({
                    "type": "loose_dust_speck",
                    "is_true_defect": False,
                    "confidence": 0.78,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                }, (int(bx + ix1), int(by + iy1), int(bw), int(bh))))

    # C. Dimple / Dent (paired positive/negative DoG shading dipole with continuous ink hue)
    int_dog = dog_signed[iy1:iy2, ix1:ix2].copy()
    int_dog[int_glare] = 0.0
    pos_bin = (int_dog > 14.0).astype(np.uint8)
    neg_bin = (int_dog < -14.0).astype(np.uint8)
    n_p, _, st_p, cen_p = cv2.connectedComponentsWithStats(pos_bin, connectivity=8)
    n_n, _, st_n, cen_n = cv2.connectedComponentsWithStats(neg_bin, connectivity=8)
    pos_lobes = [(cen_p[i], int(st_p[i, cv2.CC_STAT_AREA])) for i in range(1, n_p) if 10 <= st_p[i, cv2.CC_STAT_AREA] <= 420]
    neg_lobes = [(cen_n[i], int(st_n[i, cv2.CC_STAT_AREA])) for i in range(1, n_n) if 10 <= st_n[i, cv2.CC_STAT_AREA] <= 420]

    used_neg = set()
    for pc, _ in pos_lobes[:20]:
        for j, (nc, _) in enumerate(neg_lobes[:20]):
            if j in used_neg:
                continue
            dist_pn = float(np.hypot(pc[0] - nc[0], pc[1] - nc[1]))
            if 5.0 <= dist_pn <= 34.0:
                mx = int(ix1 + (pc[0] + nc[0]) * 0.5)
                my = int(iy1 + (pc[1] + nc[1]) * 0.5)
                ab_patch = lab[max(iy1, my - 12):min(iy2, my + 12), max(ix1, mx - 12):min(ix2, mx + 12), 1:3]
                lap_patch = lap_abs[max(iy1, my - 10):min(iy2, my + 10), max(ix1, mx - 10):min(ix2, mx + 10)]
                if ab_patch.size > 0 and float(np.mean(np.std(ab_patch, axis=(0, 1)))) < 10.5 and (lap_patch.size == 0 or float(np.median(lap_patch)) <= 26.0):
                    used_neg.add(j)
                    # Check if dent lies inside the outer 3.5% edge strip (outside corner tips) -> edge_dent
                    edge_band_x = max(8, int(cw * 0.035))
                    edge_band_y = max(8, int(ch * 0.035))
                    c_tip = max(16, int(min(cw, ch) * 0.08))
                    near_left = (mx - cx1) <= edge_band_x and (cy1 + c_tip <= my <= cy2 - c_tip)
                    near_right = (cx2 - mx) <= edge_band_x and (cy1 + c_tip <= my <= cy2 - c_tip)
                    near_top = (my - cy1) <= edge_band_y and (cx1 + c_tip <= mx <= cx2 - c_tip)
                    near_bot = (cy2 - my) <= edge_band_y and (cx1 + c_tip <= mx <= cx2 - c_tip)
                    if near_left or near_right or near_top or near_bot:
                        e_zone = "Left edge" if near_left else ("Right edge" if near_right else ("Top edge" if near_top else "Bottom edge"))
                        conf = min(0.92, 0.70 + _anom_boost(mx - cx1, my - cy1))
                        confirmed.append(_attach_meta({
                            "type": "edge_dent",
                            "is_true_defect": True,
                            "confidence": round(conf, 3),
                            "side": side_label,
                            "zone": e_zone,
                            "severity": 0.5,
                            "target": "edges",
                        }, (max(cx1, mx - 12), max(cy1, my - 12), 24, 24)))
                    else:
                        z_lbl = _zone_label(mx - cx1, my - cy1, cw, ch)
                        conf = min(0.92, 0.68 + _anom_boost(mx - cx1, my - cy1))
                        confirmed.append(_attach_meta({
                            "type": "dimple_dent",
                            "is_true_defect": True,
                            "confidence": round(conf, 3),
                            "side": side_label,
                            "zone": z_lbl,
                            "severity": 0.5,
                            "target": "surface",
                        }, (max(ix1, mx - 12), max(iy1, my - 12), 24, 24)))
                    break

    # D. Sleeve Smudge / Haze (low-frequency saturation drop + lifted black floor without sharp edges)
    int_l = lab[iy1:iy2, ix1:ix2, 0]
    int_s = hsv[iy1:iy2, ix1:ix2, 1]
    int_lap = lap_abs[iy1:iy2, ix1:ix2]
    valid_int = ~int_glare
    if np.count_nonzero(valid_int) > 400:
        med_l = float(np.median(int_l[valid_int]))
        med_s = float(np.median(int_s[valid_int]))
        med_lap = max(1.0, float(np.median(int_lap[valid_int])))
        gh_c, gw_c = 6, 4
        cell_h = max(16, (iy2 - iy1) // gh_c)
        cell_w = max(16, (ix2 - ix1) // gw_c)
        for r_i in range(gh_c):
            for c_i in range(gw_c):
                ry0, ry1 = r_i * cell_h, min(iy2 - iy1, (r_i + 1) * cell_h)
                rx0, rx1 = c_i * cell_w, min(ix2 - ix1, (c_i + 1) * cell_w)
                c_mask = valid_int[ry0:ry1, rx0:rx1]
                if np.count_nonzero(c_mask) < 150:
                    continue
                cl = float(np.mean(int_l[ry0:ry1, rx0:rx1][c_mask]))
                cs = float(np.mean(int_s[ry0:ry1, rx0:rx1][c_mask]))
                clap = float(np.mean(int_lap[ry0:ry1, rx0:rx1][c_mask]))
                if (med_s - cs) >= 20.0 and (cl - med_l) >= 12.0 and clap < med_lap * 0.65:
                    artifacts.append(_attach_meta({
                        "type": "sleeve_smudge",
                        "is_true_defect": False,
                        "confidence": 0.75,
                        "side": side_label,
                        "zone": _zone_label(rx0 + cell_w * 0.5, ry0 + cell_h * 0.5, cw, ch),
                        "severity": 0.0,
                    }, (int(ix1 + rx0), int(iy1 + ry0), max(8, int(rx1 - rx0)), max(8, int(ry1 - ry0)))))
                    break

    # E. Edge Chipping (4 edge strips) & Corner Whitening (4 corners)
    c_span = max(16, int(min(cw, ch) * 0.08))
    edge_strip = max(8, int(min(cw, ch) * 0.025))
    border_band_l = np.concatenate([
        lab[cy1:cy1 + edge_strip, cx1:cx2, 0].ravel(),
        lab[cy2 - edge_strip:cy2, cx1:cx2, 0].ravel(),
        lab[cy1:cy2, cx1:cx1 + edge_strip, 0].ravel(),
        lab[cy1:cy2, cx2 - edge_strip:cx2, 0].ravel(),
    ])
    border_l_med = float(np.median(border_band_l)) if border_band_l.size else 180.0

    white_thr_edge = max(188.0, border_l_med + (59.0 if light_border_mode else 34.0))
    skip_light_border = light_border_mode and border_l_med >= 175.0

    edge_zones = [
        ("Top edge", (cx1 + c_span, cy1, cx2 - c_span, cy1 + edge_strip)),
        ("Bottom edge", (cx1 + c_span, cy2 - edge_strip, cx2 - c_span, cy2)),
        ("Left edge", (cx1, cy1 + c_span, cx1 + edge_strip, cy2 - c_span)),
        ("Right edge", (cx2 - edge_strip, cy1 + c_span, cx2, cy2 - c_span)),
    ]
    for e_name, (ex1, ey1, ex2, ey2) in edge_zones:
        if skip_light_border or ex2 <= ex1 + 4 or ey2 <= ey1 + 4:
            continue
        e_l = lab[ey1:ey2, ex1:ex2, 0]
        e_s = hsv[ey1:ey2, ex1:ex2, 1]
        e_gl = glare_mask[ey1:ey2, ex1:ex2] | streak_mask[ey1:ey2, ex1:ex2]
        chip_m = ((e_l > white_thr_edge) & (e_s < 36) & (~e_gl)).astype(np.uint8)
        chip_frac = float(np.count_nonzero(chip_m)) / float(max(1, e_l.size))
        n_ch, lbl_ch, st_ch, cen_ch = cv2.connectedComponentsWithStats(chip_m, connectivity=8)
        max_chip_a = 0
        best_chip_box = (ex1, ey1, max(8, ex2 - ex1), max(8, ey2 - ey1))
        for i_c in range(1, n_ch):
            a_c = int(st_ch[i_c, cv2.CC_STAT_AREA])
            if a_c < 14:
                continue
            # If this edge notch continues into the outer holder margin, it is a sleeve scratch/streak
            ccx = int(ex1 + cen_ch[i_c][0])
            ccy = int(ey1 + cen_ch[i_c][1])
            crosses_out = False
            if e_name == "Left edge" and margin_avail["left"]:
                ext = surf_resp[max(0, ccy - 4):min(surf_resp.shape[0], ccy + 5), max(0, cx1 - 16):max(0, cx1 - 2)]
                crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
            elif e_name == "Right edge" and margin_avail["right"]:
                ext = surf_resp[max(0, ccy - 4):min(surf_resp.shape[0], ccy + 5), min(surf_resp.shape[1], cx2 + 2):min(surf_resp.shape[1], cx2 + 16)]
                crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
            elif e_name == "Top edge" and margin_avail["top"]:
                ext = surf_resp[max(0, cy1 - 16):max(0, cy1 - 2), max(0, ccx - 4):min(surf_resp.shape[1], ccx + 5)]
                crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
            elif e_name == "Bottom edge" and margin_avail["bottom"]:
                ext = surf_resp[min(surf_resp.shape[0], cy2 + 2):min(surf_resp.shape[0], cy2 + 16), max(0, ccx - 4):min(surf_resp.shape[1], ccx + 5)]
                crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
            if not crosses_out and a_c > max_chip_a:
                max_chip_a = a_c
                best_chip_box = (
                    int(ex1 + st_ch[i_c, cv2.CC_STAT_LEFT]),
                    int(ey1 + st_ch[i_c, cv2.CC_STAT_TOP]),
                    max(6, int(st_ch[i_c, cv2.CC_STAT_WIDTH])),
                    max(6, int(st_ch[i_c, cv2.CC_STAT_HEIGHT])),
                )
        if max_chip_a >= 14 and chip_frac < 0.35:
            sev = 1.0 if max_chip_a >= 65 else 0.5
            confirmed.append(_attach_meta({
                "type": "edge_chipping",
                "is_true_defect": True,
                "confidence": 0.78,
                "side": side_label,
                "zone": e_name,
                "severity": sev,
                "target": "edges",
            }, best_chip_box))

    white_thr_corner = max(188.0, border_l_med + (55.0 if light_border_mode else 30.0))
    manual_geom = (ov.get("manual_geometry") or {}).get(side_label.lower(), {}) if isinstance(ov.get("manual_geometry"), dict) else {}
    manual_corners = manual_geom.get("corners") if isinstance(manual_geom.get("corners"), dict) else {}
    ox_roi, oy_roi = roi_origin
    iw_full, ih_full = img_size

    def _corner_box_from_pt(pt_norm, default_box):
        if not (isinstance(pt_norm, (list, tuple)) and len(pt_norm) == 2):
            return default_box
        px = int(round(float(pt_norm[0]) * iw_full)) - ox_roi
        py = int(round(float(pt_norm[1]) * ih_full)) - oy_roi
        half = max(12, c_span // 2)
        kx1 = max(0, min(roi_rgb.shape[1] - 16, px - half))
        ky1 = max(0, min(roi_rgb.shape[0] - 16, py - half))
        kx2 = min(roi_rgb.shape[1], kx1 + c_span)
        ky2 = min(roi_rgb.shape[0], ky1 + c_span)
        return (kx1, ky1, kx2, ky2)

    corner_zones = [
        ("Top-Left", _corner_box_from_pt(manual_corners.get("tl"), (cx1, cy1, cx1 + c_span, cy1 + c_span))),
        ("Top-Right", _corner_box_from_pt(manual_corners.get("tr"), (cx2 - c_span, cy1, cx2, cy1 + c_span))),
        ("Bot-Left", _corner_box_from_pt(manual_corners.get("bl"), (cx1, cy2 - c_span, cx1 + c_span, cy2))),
        ("Bot-Right", _corner_box_from_pt(manual_corners.get("br"), (cx2 - c_span, cy2 - c_span, cx2, cy2))),
    ]
    for c_name, (kx1, ky1, kx2, ky2) in corner_zones:
        if kx2 <= kx1 + 8 or ky2 <= ky1 + 8:
            continue
        k_l = lab[ky1:ky2, kx1:kx2, 0]
        k_s = hsv[ky1:ky2, kx1:kx2, 1]
        k_g = gray[ky1:ky2, kx1:kx2]
        k_gl = glare_mask[ky1:ky2, kx1:kx2] | streak_mask[ky1:ky2, kx1:kx2]
        if skip_light_border:
            max_wh_a = 0
            wh_frac = 0.0
            best_wh_box = (kx1, ky1, max(8, kx2 - kx1), max(8, ky2 - ky1))
        else:
            wh_m = ((k_l > white_thr_corner) & (k_s < 38) & (~k_gl)).astype(np.uint8)
            wh_frac = float(np.count_nonzero(wh_m)) / float(max(1, k_l.size))
            n_wh, _, st_wh, _ = cv2.connectedComponentsWithStats(wh_m, connectivity=8)
            max_wh_a = 0
            best_wh_box = (kx1, ky1, max(8, kx2 - kx1), max(8, ky2 - ky1))
            for i_w in range(1, n_wh):
                a_w = int(st_wh[i_w, cv2.CC_STAT_AREA])
                if a_w > max_wh_a:
                    max_wh_a = a_w
                    best_wh_box = (
                        int(kx1 + st_wh[i_w, cv2.CC_STAT_LEFT]),
                        int(ky1 + st_wh[i_w, cv2.CC_STAT_TOP]),
                        max(6, int(st_wh[i_w, cv2.CC_STAT_WIDTH])),
                        max(6, int(st_wh[i_w, cv2.CC_STAT_HEIGHT])),
                    )
        lap_v = float(cv2.Laplacian(k_g, cv2.CV_64F).var())
        if (max_wh_a >= 14 and wh_frac < 0.45) or lap_v < 42.0:
            sev = 1.0 if (max_wh_a >= 75 or lap_v < 28.0) else 0.5
            confirmed.append(_attach_meta({
                "type": "corner_whitening",
                "is_true_defect": True,
                "confidence": 0.80,
                "side": side_label,
                "zone": c_name,
                "severity": sev,
                "target": "corners",
            }, best_wh_box))

    # Optional dedicated card_defect_v1.onnx patch refinement when installed
    defect_model = get_local_defect_model(load_now=False, claim_slot=False)
    if enable_onnx_anomaly and defect_model.is_ready and confirmed:
        patches = []
        patch_indices = []
        for idx_c, d_item in enumerate(confirmed):
            bb = d_item.get("bbox")
            if bb is None:
                continue
            bx, by, bw, bh = bb
            px1 = max(0, bx - 16)
            py1 = max(0, by - 16)
            px2 = min(roi_rgb.shape[1], bx + bw + 16)
            py2 = min(roi_rgb.shape[0], by + bh + 16)
            if px2 > px1 + 8 and py2 > py1 + 8:
                patches.append(roi_rgb[py1:py2, px1:px2])
                patch_indices.append(idx_c)
        if patches:
            preds = defect_model.classify_candidate_patches(patches)
            for idx_c, pred in zip(patch_indices, preds):
                if isinstance(pred, dict) and pred.get("confidence", 0.0) >= 0.72:
                    if not pred["is_true_defect"]:
                        moved = confirmed[idx_c]
                        moved["is_true_defect"] = False
                        moved["type"] = pred["label"]
                        artifacts.append(moved)
                    else:
                        confirmed[idx_c]["confidence"] = round(max(confirmed[idx_c]["confidence"], pred["confidence"]), 3)

    raw_confirmed = [c for c in confirmed if c.get("is_true_defect") and c.get("confidence", 0.0) >= _CONFIRMED_DEFECT_CONF_MIN]
    raw_confirmed = _cluster_and_nms_defects(raw_confirmed, dist_thresh=0.035)
    confirmed = [c for c in raw_confirmed if c.get("id") not in dismissed_ids]

    return {
        "confirmed": confirmed,
        "raw_confirmed": raw_confirmed,
        "artifacts": artifacts,
        "glare_pct": glare_pct,
        "margin_dust_density": margin_dust_density,
        "has_holder_margin": any(margin_avail.values()),
        "backend": backend_used,
    }


def inspect_card_surface_through_sleeve(
    front_img: Image.Image,
    back_img: Optional[Image.Image] = None,
    front_box: Optional[tuple[int, int, int, int]] = None,
    back_box: Optional[tuple[int, int, int, int]] = None,
    front_patch_tokens: Optional[np.ndarray] = None,
    back_patch_tokens: Optional[np.ndarray] = None,
    enable_onnx_anomaly: bool = True,
    claim_slot: bool = True,
    force_cpu: bool = False,
    overrides: Optional[dict] = None,
) -> dict:
    """
    Inspects Front & Back card images through penny sleeves, toploaders, and Card Saver 1 holders,
    separating genuine card defects from removable superficial artifacts.
    """
    cfg = load_compute_settings()
    if force_cpu or str(cfg.get("compute_mode") or "auto").lower() == "cpu":
        force_cpu = True

    if front_box is None:
        fw, fh = front_img.size
        front_box = (int(fw * 0.04), int(fh * 0.03), int(fw * 0.96), int(fh * 0.97))

    f_res = _inspect_single_side(
        front_img,
        front_box,
        side_label="Front",
        patch_tokens=front_patch_tokens,
        enable_onnx_anomaly=enable_onnx_anomaly,
        force_cpu=force_cpu,
        overrides=overrides,
    )

    if back_img is not None:
        if back_box is None:
            bw, bh = back_img.size
            back_box = (int(bw * 0.04), int(bh * 0.03), int(bw * 0.96), int(bh * 0.97))
        b_res = _inspect_single_side(
            back_img,
            back_box,
            side_label="Back",
            patch_tokens=back_patch_tokens,
            enable_onnx_anomaly=enable_onnx_anomaly,
            force_cpu=force_cpu,
            overrides=overrides,
        )
    else:
        b_res = {"confirmed": [], "raw_confirmed": [], "artifacts": [], "glare_pct": 0.0, "has_holder_margin": False, "backend": f_res["backend"]}

    confirmed_all = f_res["confirmed"] + b_res["confirmed"]
    raw_confirmed_all = f_res["raw_confirmed"] + b_res["raw_confirmed"]
    artifacts_all = f_res["artifacts"] + b_res["artifacts"]

    surf_pen = sum(float(d.get("severity", 0.5)) for d in confirmed_all if d.get("target") == "surface")
    corn_pen = sum(float(d.get("severity", 0.5)) for d in confirmed_all if d.get("target") == "corners")
    edge_pen = sum(float(d.get("severity", 0.5)) for d in confirmed_all if d.get("target") == "edges")

    sub_surface = _round_half_grade(9.5 - min(4.0, surf_pen))
    sub_corners = _round_half_grade(9.5 - min(4.0, corn_pen))
    sub_edges = _round_half_grade(9.5 - min(4.0, edge_pen))

    defect_notes: list[str] = []
    _lbl_map = {
        "surface_scratch": "scratch",
        "print_line": "print line",
        "dimple_dent": "dimple/dent",
        "print_spot_fisheye": "print spot/fisheye",
        "corner_whitening": "corner whitening",
        "edge_chipping": "edge chipping",
        "edge_dent": "edge dent/ding",
    }
    for d in confirmed_all[:6]:
        t_lbl = _lbl_map.get(d["type"], d["type"])
        tgt = str(d.get("target", "surface")).capitalize()
        defect_notes.append(f"{tgt}: {d['side']} {t_lbl} ({d['zone']}, -{d.get('severity', 0.5):.1f})")

    artifact_warning = ""
    if artifacts_all:
        counts: dict[str, int] = {}
        for a in artifacts_all:
            k = str(a.get("type", "artifact"))
            counts[k] = counts.get(k, 0) + 1
        bits = []
        if counts.get("specular_glare"):
            max_g = max(f_res["glare_pct"], b_res["glare_pct"])
            bits.append(f"glare ({max_g:.0f}%)")
        if counts.get("loose_dust_speck"):
            bits.append(f"{counts['loose_dust_speck']} dust speck(s)")
        if counts.get("hair_fiber"):
            bits.append(f"{counts['hair_fiber']} hair/fiber")
        if counts.get("sleeve_scratch_or_static_streak"):
            bits.append(f"{counts['sleeve_scratch_or_static_streak']} sleeve scratch/streak")
        if counts.get("sleeve_smudge"):
            bits.append("sleeve smudge/haze")
        if counts.get("scanner_streak"):
            bits.append(f"{counts['scanner_streak']} scanner glass/sensor streak(s)")
        if bits:
            if counts.get("scanner_streak"):
                artifact_warning = f"[Sleeve/Dust Check] {', '.join(bits)} — clean scanner glass & rescan to verify"
            else:
                artifact_warning = f"[Sleeve/Dust Check] {', '.join(bits)} — wipe holder & rescan to verify"

    return {
        "sub_surface": sub_surface,
        "sub_corners": sub_corners,
        "sub_edges": sub_edges,
        "confirmed_defects": confirmed_all,
        "raw_confirmed_defects": raw_confirmed_all,
        "superficial_artifacts": artifacts_all,
        "defect_notes": defect_notes,
        "artifact_warning": artifact_warning,
        "glare_pct_front": f_res["glare_pct"],
        "glare_pct_back": b_res["glare_pct"],
        "has_holder_margin_front": f_res["has_holder_margin"],
        "has_holder_margin_back": b_res["has_holder_margin"],
        "backend_used": f_res["backend"],
    }
