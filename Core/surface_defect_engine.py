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
    "corner_softness": "corner softness/blunting",
    "corner_crease": "corner crease/bend",
    "edge_chipping": "edge chipping",
    "edge_tear": "edge foil peel/tear",
    "ink_spot": "ink spot/splatter",
    "surface_stain": "surface stain/ink bleed",
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
    "corner_softness": "circle",
    "corner_crease": "circle",
    "edge_chipping": "arrow",
    "edge_tear": "arrow",
    "edge_dent": "arrow",
    "ink_spot": "circle",
    "surface_stain": "circle",
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
    border_l_med: float = 180.0,
) -> tuple[np.ndarray, float]:
    """
    Detects localized plastic sleeve/toploader specular glare bands so they are masked & warned,
    without misclassifying matte white paper borders as glare.
    """
    cx1, cy1, cx2, cy2 = local_box
    l_ch = lab[:, :, 0]
    s_ch = hsv[:, :, 1]
    smooth_lap = cv2.GaussianBlur(lap_abs.astype(np.float32), (9, 9), 2.0)

    l_thresh = min(253.0, max(242.0, float(border_l_med) + 12.0))
    raw_glare = ((l_ch > l_thresh) & (s_ch < 22) & (smooth_lap < 20.0)).astype(np.uint8)
    num_lbls, lbls, stats, _ = cv2.connectedComponentsWithStats(raw_glare, connectivity=8)

    card_area = max(1, (cx2 - cx1) * (cy2 - cy1))
    comps: list[tuple[float, int, int]] = []
    for idx in range(1, num_lbls):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < 140:
            continue
        comp_mask = (lbls == idx)
        mean_l = float(np.mean(l_ch[comp_mask]))
        # Reject broad matte-white paper borders that are not true specular hot-spots
        if area > 0.12 * card_area and mean_l < 251.0:
            continue
        in_card_area = int(np.count_nonzero(comp_mask[cy1:cy2, cx1:cx2]))
        comps.append((mean_l, idx, in_card_area))

    # Sort brightest specular blobs first and enforce < 18% card-face cap
    comps.sort(key=lambda t: t[0], reverse=True)
    glare_mask = np.zeros(l_ch.shape, dtype=np.uint8)
    cum_card_glare = 0
    cap_pixels = int(0.175 * card_area)
    for _, idx, in_card_area in comps:
        if cum_card_glare + in_card_area > cap_pixels and cum_card_glare > 0:
            continue
        if in_card_area > cap_pixels:
            continue
        glare_mask[lbls == idx] = 255
        cum_card_glare += in_card_area

    glare_in_card = int(np.count_nonzero(glare_mask[cy1:cy2, cx1:cx2]))
    glare_pct = round(min(17.9, 100.0 * glare_in_card / float(card_area)), 1)
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
    Detects genuine isolated duplex ADF / CIS scanner glass & sensor streaks:
      - Strictly vertical or horizontal (wobble < 0.65 px, strictly 1-3 px wide)
      - Continuous edge-to-edge (>= 95% of full ROI) OR crosses past `card_box` into `margin_ring`
        with matching signed intensity delta
      - Capped at <= 5 streaks per side; if > 8 parallel lines fire, treats them as printed
        pinstripes/border texture and suppresses the streak mask completely.
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
    cand_streaks: list[tuple[tuple[bool, float, float], dict, tuple[int, int, int, int], str, int, int]] = []

    def _scan_axis(axis: str):
        if axis == "v":
            if w < 16:
                return
            ref = 0.5 * (f_rgb[:, :-8, :] + f_rgb[:, 8:, :])
            signed_diff = f_rgb[:, 4:-4, :] - ref
            diff = np.abs(signed_diff)
            max_ch = np.max(diff, axis=2)
            hit_full = (max_ch > 18.0)
            col_frac_full = np.mean(hit_full, axis=0)
            col_frac_card = np.mean(hit_full[cy1:cy2, :], axis=0)
            med_ch_diff = np.median(diff, axis=0)
            cast_strength = np.max(med_ch_diff, axis=1) - np.min(med_ch_diff, axis=1)

            cand_idx = np.where((col_frac_card >= 0.78) & ((col_frac_full >= 0.94) | (np.mean(hit_full, axis=0) >= 0.78)))[0]
            if cand_idx.size == 0:
                return
            groups: list[list[int]] = []
            for idx in cand_idx.tolist():
                if not groups or idx - groups[-1][-1] > 1:
                    groups.append([idx])
                else:
                    groups[-1].append(idx)

            for grp in groups:
                width_px = len(grp)
                if width_px < 1 or width_px > 3:
                    continue
                x0 = grp[0] + 4
                x1 = grp[-1] + 4
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
                if wobble >= 0.65:
                    continue

                full_span_frac = float(np.max(col_frac_full[grp]))
                card_sign = float(np.median(signed_diff[cy1:cy2, grp, :]))
                crosses_margin = False
                if margin_avail.get("top") and cy1 >= 4:
                    m_top_sd = signed_diff[:cy1, grp, :]
                    if m_top_sd.size > 0:
                        m_sign = float(np.median(m_top_sd))
                        m_hit = float(np.mean(np.max(np.abs(m_top_sd), axis=2) >= 6.0))
                        if card_sign * m_sign > 0 and abs(m_sign) >= 5.0 and m_hit >= 0.65:
                            crosses_margin = True
                if margin_avail.get("bottom") and cy2 <= h - 4:
                    m_bot_sd = signed_diff[cy2:, grp, :]
                    if m_bot_sd.size > 0:
                        m_sign = float(np.median(m_bot_sd))
                        m_hit = float(np.mean(np.max(np.abs(m_bot_sd), axis=2) >= 6.0))
                        if card_sign * m_sign > 0 and abs(m_sign) >= 5.0 and m_hit >= 0.65:
                            crosses_margin = True

                if not (crosses_margin or full_span_frac >= 0.95):
                    continue

                max_cast = float(np.max(cast_strength[grp]))
                conf = round(min(0.97, 0.86 + (0.05 if crosses_margin else 0.0) + (0.04 if max_cast >= 12.0 else 0.0)), 3)
                z_lbl = _zone_label((x0 + x1) * 0.5 - cx1, ch * 0.5, cw, ch)
                item = {
                    "type": "scanner_streak",
                    "is_true_defect": False,
                    "confidence": conf,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                    "detail": "Scanner glass/sensor streak — clean scanner glass & rescan",
                }
                bbox = (int(x0), 0, max(2, int(x1 - x0 + 1)), int(h))
                cand_streaks.append(((crosses_margin, full_span_frac, max_cast), item, bbox, "v", x0, x1))
        else:
            if h < 16:
                return
            ref = 0.5 * (f_rgb[:-8, :, :] + f_rgb[8:, :, :])
            signed_diff = f_rgb[4:-4, :, :] - ref
            diff = np.abs(signed_diff)
            max_ch = np.max(diff, axis=2)
            hit_full = (max_ch > 18.0)
            row_frac_full = np.mean(hit_full, axis=1)
            row_frac_card = np.mean(hit_full[:, cx1:cx2], axis=1)
            med_ch_diff = np.median(diff, axis=1)
            cast_strength = np.max(med_ch_diff, axis=1) - np.min(med_ch_diff, axis=1)

            cand_idx = np.where((row_frac_card >= 0.78) & ((row_frac_full >= 0.94) | (np.mean(hit_full, axis=1) >= 0.78)))[0]
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
                if height_px < 1 or height_px > 3:
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
                if wobble >= 0.65:
                    continue

                full_span_frac = float(np.max(row_frac_full[grp]))
                card_sign = float(np.median(signed_diff[grp, cx1:cx2, :]))
                crosses_margin = False
                if margin_avail.get("left") and cx1 >= 4:
                    m_left_sd = signed_diff[grp, :cx1, :]
                    if m_left_sd.size > 0:
                        m_sign = float(np.median(m_left_sd))
                        m_hit = float(np.mean(np.max(np.abs(m_left_sd), axis=2) >= 6.0))
                        if card_sign * m_sign > 0 and abs(m_sign) >= 5.0 and m_hit >= 0.65:
                            crosses_margin = True
                if margin_avail.get("right") and cx2 <= w - 4:
                    m_right_sd = signed_diff[grp, cx2:, :]
                    if m_right_sd.size > 0:
                        m_sign = float(np.median(m_right_sd))
                        m_hit = float(np.mean(np.max(np.abs(m_right_sd), axis=2) >= 6.0))
                        if card_sign * m_sign > 0 and abs(m_sign) >= 5.0 and m_hit >= 0.65:
                            crosses_margin = True

                if not (crosses_margin or full_span_frac >= 0.95):
                    continue

                max_cast = float(np.max(cast_strength[grp]))
                conf = round(min(0.97, 0.86 + (0.05 if crosses_margin else 0.0) + (0.04 if max_cast >= 12.0 else 0.0)), 3)
                z_lbl = _zone_label(cw * 0.5, (y0 + y1) * 0.5 - cy1, cw, ch)
                item = {
                    "type": "scanner_streak",
                    "is_true_defect": False,
                    "confidence": conf,
                    "side": side_label,
                    "zone": z_lbl,
                    "severity": 0.0,
                    "detail": "Scanner glass/sensor streak — clean scanner glass & rescan",
                }
                bbox = (0, int(y0), int(w), max(2, int(y1 - y0 + 1)))
                cand_streaks.append(((crosses_margin, full_span_frac, max_cast), item, bbox, "h", y0, y1))

    _scan_axis("v")
    _scan_axis("h")

    # > 8 parallel lines = printed pinstripes / border texture -> suppress streak mask completely
    if len(cand_streaks) > 8:
        return [], np.zeros((h, w), dtype=bool)

    # Cap at <= 5 streaks per side
    if len(cand_streaks) > 5:
        cand_streaks.sort(key=lambda t: t[0], reverse=True)
        cand_streaks = cand_streaks[:5]

    for _, item, bbox, ax, p0, p1 in cand_streaks:
        if ax == "v":
            streak_mask[:, max(0, p0 - 2):min(w, p1 + 3)] = True
        else:
            streak_mask[max(0, p0 - 2):min(h, p1 + 3), :] = True
        found.append((item, bbox))

    return found, streak_mask


def _detect_corner_softness(
    lab: np.ndarray,
    local_box: tuple[int, int, int, int],
    margin_avail: dict[str, bool],
    glare_mask: np.ndarray,
    streak_mask: np.ndarray,
    side_label: str,
) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """
    Measures physical corner-tip rounding / blunting by extrapolating the two straight
    card edges approaching each corner to their theoretical 90-degree intersection and
    measuring the contour tip recession distance (requires >= 6px outer margin).
    """
    results: list[tuple[dict, tuple[int, int, int, int]]] = []
    h, w = lab.shape[:2]
    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)

    if not (margin_avail.get("left") and margin_avail.get("right") and margin_avail.get("top") and margin_avail.get("bottom")):
        return results

    tip_sz = max(26, int(min(cw, ch) * 0.055))
    pad_out = 10
    if cx1 < 6 or cy1 < 6 or (w - cx2) < 6 or (h - cy2) < 6:
        return results

    corners = [
        ("Top-Left", cx1, cy1, 1, 1),
        ("Top-Right", cx2, cy1, -1, 1),
        ("Bot-Left", cx1, cy2, 1, -1),
        ("Bot-Right", cx2, cy2, -1, -1),
    ]

    for c_name, vx, vy, sx, sy in corners:
        rx1 = max(0, vx - (pad_out if sx > 0 else tip_sz))
        rx2 = min(w, vx + (tip_sz if sx > 0 else pad_out))
        ry1 = max(0, vy - (pad_out if sy > 0 else tip_sz))
        ry2 = min(h, vy + (tip_sz if sy > 0 else pad_out))
        if rx2 - rx1 < 24 or ry2 - ry1 < 24:
            continue

        if np.mean(glare_mask[ry1:ry2, rx1:rx2] | streak_mask[ry1:ry2, rx1:rx2]) > 0.35:
            continue

        patch_lab = lab[ry1:ry2, rx1:rx2]
        ph, pw = patch_lab.shape[:2]

        # Sample outer background corner of this ROI (pure margin outside card)
        bg_x = slice(0, 5) if sx > 0 else slice(pw - 5, pw)
        bg_y = slice(0, 5) if sy > 0 else slice(ph - 5, ph)
        bg_ref = np.median(patch_lab[bg_y, bg_x].reshape(-1, 3), axis=0)

        # Sample inner card corner area
        in_x = slice(pw - 8, pw) if sx > 0 else slice(0, 8)
        in_y = slice(ph - 8, ph) if sy > 0 else slice(0, 8)
        in_ref = np.median(patch_lab[in_y, in_x].reshape(-1, 3), axis=0)

        light_bed_same_color = (
            float(bg_ref[0]) >= 180.0
            and float(in_ref[0]) >= 180.0
            and float(np.linalg.norm(in_ref - bg_ref)) < 16.0
        )
        if light_bed_same_color:
            # On white-bordered cards scanned on a light bed, trace the corner contour
            # using the outer drop-shadow bevel (L* < bg_ref[0] - 12) and interior fill.
            shadow_l = patch_lab[:, :, 0]
            shadow_fg = (shadow_l < float(bg_ref[0]) - 12.0).astype(np.uint8) * 255
            shadow_fg = cv2.morphologyEx(shadow_fg, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8), iterations=1)
            cnts_s, _ = cv2.findContours(shadow_fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if not cnts_s:
                continue
            main_cnt = max(cnts_s, key=cv2.contourArea)
            if cv2.contourArea(main_cnt) < 0.08 * (ph * pw):
                continue
        else:
            # Need clear separation between card corner and outer margin
            if float(np.linalg.norm(in_ref - bg_ref)) < 16.0:
                continue

            dist_bg = np.linalg.norm(patch_lab - bg_ref, axis=2)
            dist_in = np.linalg.norm(patch_lab - in_ref, axis=2)
            card_fg = ((dist_bg > 15.0) & (dist_bg >= dist_in * 0.75)).astype(np.uint8) * 255
            card_fg = cv2.morphologyEx(card_fg, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8), iterations=1)

            cnts, _ = cv2.findContours(card_fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if not cnts:
                continue
            main_cnt = max(cnts, key=cv2.contourArea)
            if cv2.contourArea(main_cnt) < 0.25 * (ph * pw):
                continue

        # Fit horizontal edge (x in [25%..80%] from corner toward card interior) and vertical edge
        pts = main_cnt.reshape(-1, 2).astype(np.float64)
        # Local coordinates relative to ROI
        lx = vx - rx1
        ly = vy - ry1

        # Points along horizontal edge: distance from lx along sx is in [0.28*tip_sz .. 0.85*tip_sz]
        dx_from_corner = (pts[:, 0] - lx) * sx
        dy_from_corner = (pts[:, 1] - ly) * sy

        h_mask = (dx_from_corner >= tip_sz * 0.28) & (dx_from_corner <= tip_sz * 0.85) & (np.abs(dy_from_corner) <= 8.0)
        v_mask = (dy_from_corner >= tip_sz * 0.28) & (dy_from_corner <= tip_sz * 0.85) & (np.abs(dx_from_corner) <= 8.0)

        if np.count_nonzero(h_mask) < 6 or np.count_nonzero(v_mask) < 6:
            continue

        hx, hy = pts[h_mask, 0], pts[h_mask, 1]
        vx_pts, vy_pts = pts[v_mask, 0], pts[v_mask, 1]

        # Fit y = mh * x + ch_line and x = mv * y + cv_line
        mh, ch_line = np.polyfit(hx, hy, 1)
        mv, cv_line = np.polyfit(vy_pts, vx_pts, 1)
        if float(np.median(np.abs(hy - (mh * hx + ch_line)))) > 1.8:
            continue
        if float(np.median(np.abs(vx_pts - (mv * vy_pts + cv_line)))) > 1.8:
            continue

        denom = 1.0 - mh * mv
        if abs(denom) < 0.5:
            continue
        p_y = (mh * cv_line + ch_line) / denom
        p_x = mv * p_y + cv_line

        if not (-2.0 <= p_x <= pw + 2.0 and -2.0 <= p_y <= ph + 2.0):
            continue

        dists = np.hypot(pts[:, 0] - p_x, pts[:, 1] - p_y)
        tip_recession = float(np.min(dists))
        recession_ratio = tip_recession / float(min(cw, ch))

        if tip_recession >= 5.0 and recession_ratio >= 0.0065:
            # Verify missing tip area matches background rather than internal art
            box_sz = max(14, int(round(tip_recession * 2.4)))
            bx = max(0, min(w - box_sz, int(round(rx1 + p_x - (box_sz * 0.25 if sx > 0 else box_sz * 0.75)))))
            by = max(0, min(h - box_sz, int(round(ry1 + p_y - (box_sz * 0.25 if sy > 0 else box_sz * 0.75)))))
            sev = 1.0 if recession_ratio >= 0.011 else 0.5
            conf = round(min(0.90, 0.74 + min(0.14, (recession_ratio - 0.0065) * 18.0)), 3)
            results.append(({
                "type": "corner_softness",
                "is_true_defect": True,
                "confidence": conf,
                "side": side_label,
                "zone": c_name,
                "severity": sev,
                "target": "corners",
            }, (bx, by, box_sz, box_sz)))

    return results


def _detect_edge_silhouette_dings(
    lab: np.ndarray,
    local_box: tuple[int, int, int, int],
    margin_avail: dict[str, bool],
    glare_mask: np.ndarray,
    streak_mask: np.ndarray,
    side_label: str,
) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """
    Detects physical edge dings / notches along all 4 card edges (both white and colored
    borders, sleeved or unsleeved) via:
      1. Silhouette indentation: inward contour dip >= 3.5 px over 8-120 px span vs. straight baseline.
      2. White/light-border dark shadow wedge/notch: localized L* drop >= 40 below local rolling
         edge median touching within 3 px of the physical outer boundary.
    """
    results: list[tuple[dict, tuple[int, int, int, int]]] = []
    h, w = lab.shape[:2]
    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)
    l_ch = lab[:, :, 0]
    excl = glare_mask | streak_mask

    c_pad_x = max(18, int(cw * 0.07))
    c_pad_y = max(18, int(ch * 0.07))
    out_pad = 12
    in_pad = 24

    sides = [
        ("Top edge", "h", cy1, 1, cx1 + c_pad_x, cx2 - c_pad_x, margin_avail.get("top", False)),
        ("Bottom edge", "h", cy2, -1, cx1 + c_pad_x, cx2 - c_pad_x, margin_avail.get("bottom", False)),
        ("Left edge", "v", cx1, 1, cy1 + c_pad_y, cy2 - c_pad_y, margin_avail.get("left", False)),
        ("Right edge", "v", cx2, -1, cy1 + c_pad_y, cy2 - c_pad_y, margin_avail.get("right", False)),
    ]

    for e_name, axis, edge_v, inward_dir, u_lo, u_hi, has_m in sides:
        if u_hi - u_lo < 40:
            continue

        if axis == "h":
            v0 = max(0, edge_v - (out_pad if inward_dir > 0 else in_pad))
            v1 = min(h, edge_v + (in_pad if inward_dir > 0 else out_pad))
            if v1 - v0 < 16:
                continue
            strip_l = l_ch[v0:v1, u_lo:u_hi]
            strip_excl = excl[v0:v1, u_lo:u_hi]
            local_edge = edge_v - v0
        else:
            v0 = max(0, edge_v - (out_pad if inward_dir > 0 else in_pad))
            v1 = min(w, edge_v + (in_pad if inward_dir > 0 else out_pad))
            if v1 - v0 < 16:
                continue
            strip_l = l_ch[u_lo:u_hi, v0:v1].T
            strip_excl = excl[u_lo:u_hi, v0:v1].T
            local_edge = edge_v - v0

        sh_s, sw_s = strip_l.shape
        # Orient strip so row 0 is outermost and row sh_s-1 is deepest inside card
        if inward_dir < 0:
            strip_l = strip_l[::-1, :]
            strip_excl = strip_excl[::-1, :]
            local_edge = (sh_s - 1) - local_edge

        # 1. Silhouette indentation (when margin is available outside edge)
        if has_m and local_edge >= 5 and (sh_s - local_edge) >= 12:
            bg_l = float(np.median(strip_l[:max(2, local_edge - 3), :]))
            in_band = strip_l[min(sh_s - 4, local_edge + 8):min(sh_s, local_edge + 20), :]
            border_l = float(np.median(in_band)) if in_band.size else bg_l
            edge_pos = np.full(sw_s, np.nan, dtype=np.float32)

            if abs(bg_l - border_l) >= 18.0:
                thr_mid = 0.5 * (bg_l + border_l)
                is_fg = (strip_l > thr_mid) if border_l > bg_l else (strip_l < thr_mid)
                for u_i in range(sw_s):
                    if np.mean(strip_excl[:, u_i]) > 0.35:
                        continue
                    hits = np.where(is_fg[max(0, local_edge - 8):min(sh_s, local_edge + 18), u_i])[0]
                    if hits.size > 0:
                        edge_pos[u_i] = float(max(0, local_edge - 8) + hits[0])
            elif bg_l >= 180.0 and border_l >= 180.0:
                # Light bed + white border: trace drop-shadow valley near local_edge
                s_lo = max(1, local_edge - 7)
                s_hi = min(sh_s - 1, local_edge + 14)
                if s_hi > s_lo + 2:
                    sub = strip_l[s_lo:s_hi, :]
                    min_idx = np.argmin(sub, axis=0)
                    min_val = sub[min_idx, np.arange(sw_s)]
                    ref_top = max(bg_l, border_l)
                    valid = (ref_top - min_val >= 12.0) & (np.mean(strip_excl[s_lo:s_hi, :], axis=0) <= 0.35)
                    edge_pos[valid] = (s_lo + min_idx[valid]).astype(np.float32)

            valid_u = np.where(~np.isnan(edge_pos))[0]
            if valid_u.size >= max(30, int(sw_s * 0.45)):
                u_pts = valid_u.astype(np.float64)
                v_pts = edge_pos[valid_u].astype(np.float64)
                m_fit, c_fit = np.polyfit(u_pts, v_pts, 1)
                res_fit = np.abs(v_pts - (m_fit * u_pts + c_fit))
                keep = res_fit <= max(2.5, float(np.percentile(res_fit, 85)))
                if np.count_nonzero(keep) >= 20:
                    m_fit, c_fit = np.polyfit(u_pts[keep], v_pts[keep], 1)
                    if float(np.median(np.abs(v_pts[keep] - (m_fit * u_pts[keep] + c_fit)))) <= 1.5:
                        base_line = m_fit * np.arange(sw_s, dtype=np.float64) + c_fit
                        indent = np.zeros(sw_s, dtype=np.float32)
                        indent[valid_u] = (edge_pos[valid_u] - base_line[valid_u]).astype(np.float32)
                        # Smooth 3-px median to suppress 1-px noise
                        if sw_s >= 5:
                            indent_s = np.pad(indent, 1, mode="edge")
                            indent = np.median(np.stack([indent_s[:-2], indent_s[1:-1], indent_s[2:]]), axis=0)
                        dip_mask = (indent >= 3.5) & (np.mean(strip_excl, axis=0) < 0.35)
                        # Find contiguous runs allowing 1-px gap
                        edge_runs: list[tuple[dict, tuple[int, int, int, int]]] = []
                        u_i = 0
                        while u_i < sw_s:
                            if not dip_mask[u_i]:
                                u_i += 1
                                continue
                            u_end = u_i
                            while u_end + 1 < sw_s and (dip_mask[u_end + 1] or (u_end + 2 < sw_s and dip_mask[u_end + 2])):
                                u_end += 1
                            span = u_end - u_i + 1
                            peak_dip = float(np.max(indent[u_i:u_end + 1]))
                            if 8 <= span <= 120 and peak_dip >= 3.5:
                                bx_u = u_lo + u_i
                                depth_px = max(8, int(round(peak_dip + 8)))
                                if axis == "h":
                                    by_v = edge_v if inward_dir > 0 else max(0, edge_v - depth_px)
                                    bbox_roi = (int(bx_u), int(by_v), int(span), int(depth_px))
                                else:
                                    bx_v = edge_v if inward_dir > 0 else max(0, edge_v - depth_px)
                                    bbox_roi = (int(bx_v), int(bx_u), int(depth_px), int(span))
                                sev = 1.0 if (peak_dip >= 7.0 or span >= 35) else 0.5
                                conf = round(min(0.92, 0.72 + min(0.18, (peak_dip - 3.5) * 0.03)), 3)
                                edge_runs.append(({
                                    "type": "edge_dent",
                                    "is_true_defect": True,
                                    "confidence": conf,
                                    "side": side_label,
                                    "zone": e_name,
                                    "severity": sev,
                                    "target": "edges",
                                }, bbox_roi))
                            u_i = u_end + 1
                        if len(edge_runs) <= 3:
                            results.extend(edge_runs)

        # 2. Localized dark shadow wedge/notch touching outer physical edge (light/white borders)
        in_start = max(0, local_edge)
        in_end = min(sh_s, local_edge + 22)
        if in_end - in_start >= 10:
            inner_band = strip_l[min(sh_s - 4, local_edge + 8):min(sh_s, local_edge + 20), :]
            if inner_band.size > 0:
                col_med = np.median(inner_band, axis=0)
                k_roll = min(101, max(15, (sw_s // 8) | 1))
                # Fast sliding median approximation via blur
                ref_l = cv2.GaussianBlur(col_med.reshape(1, -1).astype(np.float32), (k_roll, 1), 0).ravel()
                edge_sub = strip_l[in_start:in_end, :]
                excl_sub = strip_excl[in_start:in_end, :]
                notch_m = ((ref_l[None, :] >= 165.0) & (edge_sub <= ref_l[None, :] - 40.0) & (~excl_sub)).astype(np.uint8)
                n_nc, _, st_nc, _ = cv2.connectedComponentsWithStats(notch_m, connectivity=8)
                edge_notches: list[tuple[dict, tuple[int, int, int, int]]] = []
                if n_nc < 8:
                    for i_n in range(1, n_nc):
                        a_n = int(st_nc[i_n, cv2.CC_STAT_AREA])
                        if a_n < 20:
                            continue
                        bx_n = int(st_nc[i_n, cv2.CC_STAT_LEFT])
                        by_n = int(st_nc[i_n, cv2.CC_STAT_TOP])
                        bw_n = int(st_nc[i_n, cv2.CC_STAT_WIDTH])
                        bh_n = int(st_nc[i_n, cv2.CC_STAT_HEIGHT])
                        if by_n > 3 or not (4 <= bw_n <= 120) or not (3 <= bh_n <= 30):
                            continue
                        l_flank = float(ref_l[max(0, bx_n - 10)])
                        r_flank = float(ref_l[min(sw_s - 1, bx_n + bw_n + 10)])
                        if abs(l_flank - r_flank) >= 25.0 or min(l_flank, r_flank) < 165.0:
                            continue
                        if axis == "h":
                            ry = edge_v if inward_dir > 0 else max(0, edge_v - bh_n - 2)
                            bbox_roi = (int(u_lo + bx_n), int(ry), max(6, bw_n), max(6, bh_n + 2))
                        else:
                            rx = edge_v if inward_dir > 0 else max(0, edge_v - bh_n - 2)
                            bbox_roi = (int(rx), int(u_lo + bx_n), max(6, bh_n + 2), max(6, bw_n))
                        sev = 1.0 if (a_n >= 120 or bh_n >= 10) else 0.5
                        edge_notches.append(({
                            "type": "edge_dent",
                            "is_true_defect": True,
                            "confidence": 0.80,
                            "side": side_label,
                            "zone": e_name,
                            "severity": sev,
                            "target": "edges",
                        }, bbox_roi))
                if len(edge_notches) <= 3:
                    results.extend(edge_notches)

    return results


def _detect_corner_creases(
    lab: np.ndarray,
    lap_abs: np.ndarray,
    local_box: tuple[int, int, int, int],
    glare_mask: np.ndarray,
    streak_mask: np.ndarray,
    side_label: str,
) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """
    Detects diagonal corner creases / bends inside the outer 12% corner zones:
    diagonal linear luminance/shadow breaks (25-65 deg relative to corner edges,
    spanning >= 28 px across a corner margin) on continuous underlying hue.
    """
    results: list[tuple[dict, tuple[int, int, int, int]]] = []
    h, w = lab.shape[:2]
    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)
    cz_w = max(60, int(cw * 0.12))
    cz_h = max(60, int(ch * 0.12))
    excl = glare_mask | streak_mask

    # Expected diagonal slope sign in image coords (x right, y down):
    # Top-Left (/, dx*dy < 0), Top-Right (\, dx*dy > 0), Bot-Left (\, dx*dy > 0), Bot-Right (/, dx*dy < 0)
    corners = [
        ("Top-Left", cx1 + 3, cy1 + 3, min(cx2, cx1 + cz_w), min(cy2, cy1 + cz_h), -1),
        ("Top-Right", max(cx1, cx2 - cz_w), cy1 + 3, cx2 - 3, min(cy2, cy1 + cz_h), 1),
        ("Bot-Left", cx1 + 3, max(cy1, cy2 - cz_h), min(cx2, cx1 + cz_w), cy2 - 3, 1),
        ("Bot-Right", max(cx1, cx2 - cz_w), max(cy1, cy2 - cz_h), cx2 - 3, cy2 - 3, -1),
    ]

    min_len = max(28, int(min(cz_w, cz_h) * 0.20))
    for c_name, kx1, ky1, kx2, ky2, exp_sign in corners:
        if kx2 - kx1 < 36 or ky2 - ky1 < 36:
            continue
        if float(np.mean(excl[ky1:ky2, kx1:kx2])) > 0.35:
            continue

        patch_lab = lab[ky1:ky2, kx1:kx2].astype(np.float32)
        patch_lap = lap_abs[ky1:ky2, kx1:kx2]
        ph, pw = patch_lab.shape[:2]
        l_sm = cv2.GaussianBlur(patch_lab[:, :, 0], (7, 7), 0)
        edges = cv2.Canny(np.clip(l_sm, 0, 255).astype(np.uint8), 12, 36)
        art_mask = cv2.dilate((patch_lap > 140.0).astype(np.uint8), np.ones((5, 5), dtype=np.uint8), iterations=1) > 0
        edges[excl[ky1:ky2, kx1:kx2] | art_mask] = 0

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=22, minLineLength=min_len, maxLineGap=10)
        if lines is None:
            continue

        # Sort longest segments first
        sorted_lines = sorted(
            [tuple(int(v) for v in ln[0]) for ln in lines],
            key=lambda s: (s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2,
            reverse=True,
        )

        valid_segs: list[tuple[float, int, int, int, int]] = []
        for x1, y1, x2, y2 in sorted_lines[:100]:
            dx = x2 - x1
            dy = y2 - y1
            length = float(np.hypot(dx, dy))
            if length < float(min_len):
                continue
            if dx == 0 or dy == 0:
                continue
            # Check diagonal angle 25..65 deg and matching corner-cutting orientation
            ang = float(np.degrees(np.arctan2(abs(dy), abs(dx))))
            if not (25.0 <= ang <= 65.0):
                continue
            slope_sign = 1 if (dx * dy) > 0 else -1
            if slope_sign != exp_sign:
                continue

            # Perpendicular unit normal
            nx, ny = -dy / length, dx / length
            flank1_l, flank2_l = [], []
            flank1_ab, flank2_ab = [], []
            ridge_l = []
            for t in np.linspace(0.15, 0.85, 9):
                px = x1 + t * dx
                py = y1 + t * dy
                ix0, iy0 = int(round(px)), int(round(py))
                if 0 <= ix0 < pw and 0 <= iy0 < ph:
                    ridge_l.append(float(patch_lab[iy0, ix0, 0]))
                for d_off in (5.0, 8.0):
                    p1x, p1y = int(round(px + nx * d_off)), int(round(py + ny * d_off))
                    p2x, p2y = int(round(px - nx * d_off)), int(round(py - ny * d_off))
                    if 0 <= p1x < pw and 0 <= p1y < ph:
                        flank1_l.append(float(patch_lab[p1y, p1x, 0]))
                        flank1_ab.append(patch_lab[p1y, p1x, 1:3])
                    if 0 <= p2x < pw and 0 <= p2y < ph:
                        flank2_l.append(float(patch_lab[p2y, p2x, 0]))
                        flank2_ab.append(patch_lab[p2y, p2x, 1:3])

            if len(flank1_l) < 5 or len(flank2_l) < 5 or len(ridge_l) < 4:
                continue

            m_l1, m_l2 = float(np.mean(flank1_l)), float(np.mean(flank2_l))
            s_l1, s_l2 = float(np.std(flank1_l)), float(np.std(flank2_l))
            if max(s_l1, s_l2) >= 12.0:
                continue

            ab1 = np.mean(np.array(flank1_ab, dtype=np.float32), axis=0)
            ab2 = np.mean(np.array(flank2_ab, dtype=np.float32), axis=0)
            hue_diff = float(np.hypot(ab1[0] - ab2[0], ab1[1] - ab2[1]))
            if hue_diff >= 5.0:
                continue

            step_l = abs(m_l1 - m_l2)
            ridge_dev = max(abs(float(np.mean(ridge_l)) - m_l1), abs(float(np.mean(ridge_l)) - m_l2))
            contrast = max(step_l, ridge_dev)
            if not (7.5 <= contrast <= 50.0):
                continue

            valid_segs.append((length * contrast, x1, y1, x2, y2))

        if not valid_segs:
            continue
        # Reject dense parallel hatching (>= 3 distinct parallel segments)
        if len(valid_segs) >= 4:
            mids = sorted([((s[1] + s[3]) * 0.5, (s[2] + s[4]) * 0.5) for s in valid_segs])
            distinct_cnt = 1
            for k in range(1, len(mids)):
                if np.hypot(mids[k][0] - mids[k - 1][0], mids[k][1] - mids[k - 1][1]) >= 8.0:
                    distinct_cnt += 1
            if distinct_cnt >= 3:
                continue

        _, bx1_s, by1_s, bx2_s, by2_s = max(valid_segs, key=lambda t: t[0])
        rx = kx1 + min(bx1_s, bx2_s) - 4
        ry = ky1 + min(by1_s, by2_s) - 4
        rw_b = max(16, abs(bx2_s - bx1_s) + 8)
        rh_b = max(16, abs(by2_s - by1_s) + 8)
        results.append(({
            "type": "corner_crease",
            "is_true_defect": True,
            "confidence": 0.84,
            "side": side_label,
            "zone": c_name,
            "severity": 1.5,
            "target": "corners",
        }, (int(max(0, rx)), int(max(0, ry)), int(rw_b), int(rh_b))))

    return results


def _detect_edge_foil_peel_or_tear(
    lab: np.ndarray,
    hsv: np.ndarray,
    surf_resp: np.ndarray,
    local_box: tuple[int, int, int, int],
    margin_avail: dict[str, bool],
    glare_mask: np.ndarray,
    streak_mask: np.ndarray,
    side_label: str,
) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """
    Detects foil peeling / paper-core tears along the outer 0.3%-6.5% band of
    colored or foil card borders where bright neutral stock breaks into the border.
    """
    results: list[tuple[dict, tuple[int, int, int, int]]] = []
    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)
    c_span = max(16, int(min(cw, ch) * 0.06))
    band_d = max(14, int(min(cw, ch) * 0.065))
    out_skip = max(2, int(min(cw, ch) * 0.003))
    min_area = max(200, int(cw * ch * 0.00010))
    touch_tol = max(6, int(min(cw, ch) * 0.012))
    excl = glare_mask | streak_mask

    edge_zones = [
        ("Top edge", (cx1 + c_span, cy1 + out_skip, cx2 - c_span, cy1 + band_d)),
        ("Bottom edge", (cx1 + c_span, cy2 - band_d, cx2 - c_span, cy2 - out_skip)),
        ("Left edge", (cx1 + out_skip, cy1 + c_span, cx1 + band_d, cy2 - c_span)),
        ("Right edge", (cx2 - band_d, cy1 + c_span, cx2 - out_skip, cy2 - c_span)),
    ]

    for e_name, (ex1, ey1, ex2, ey2) in edge_zones:
        if ex2 <= ex1 + 12 or ey2 <= ey1 + 12:
            continue
        e_lab = lab[ey1:ey2, ex1:ex2].astype(np.float32)
        e_s = hsv[ey1:ey2, ex1:ex2, 1]
        e_gl = excl[ey1:ey2, ex1:ex2]

        med_lab = np.median(e_lab.reshape(-1, 3), axis=0)
        med_l, med_a, med_b = float(med_lab[0]), float(med_lab[1]), float(med_lab[2])
        med_s = float(np.median(e_s))
        border_chroma = float(np.hypot(med_a - 128.0, med_b - 128.0))

        # Only run on colored/foil/non-white borders
        if med_l >= 215.0 or (med_s < 20.0 and border_chroma < 8.0 and med_l >= 135.0) or (med_s < 28.0 and border_chroma < 10.0 and med_l >= 165.0):
            continue

        lab_dist = np.linalg.norm(e_lab - med_lab[None, None, :], axis=2)
        e_l = e_lab[:, :, 0]
        tear_m = (
            (e_l > 192.0)
            & (e_s < 35)
            & (((e_l - med_l) >= 32.0) | (lab_dist >= 34.0))
        ) & (~e_gl)
        tear_u8 = tear_m.astype(np.uint8)
        tear_frac = float(np.count_nonzero(tear_u8)) / float(max(1, tear_u8.size))
        if tear_frac <= 0.0 or tear_frac >= 0.25:
            continue

        n_t, lbl_t, st_t, cen_t = cv2.connectedComponentsWithStats(tear_u8, connectivity=8)
        sig_idx = [i_t for i_t in range(1, n_t) if int(st_t[i_t, cv2.CC_STAT_AREA]) >= min_area]
        if len(sig_idx) >= 8:
            continue

        best_a = 0
        best_box = None
        eh, ew = tear_u8.shape
        for i_t in sig_idx:
            a_t = int(st_t[i_t, cv2.CC_STAT_AREA])
            bx_t = int(st_t[i_t, cv2.CC_STAT_LEFT])
            by_t = int(st_t[i_t, cv2.CC_STAT_TOP])
            bw_t = int(st_t[i_t, cv2.CC_STAT_WIDTH])
            bh_t = int(st_t[i_t, cv2.CC_STAT_HEIGHT])
            touches_outer = (
                (e_name == "Top edge" and by_t <= touch_tol)
                or (e_name == "Bottom edge" and (by_t + bh_t) >= (eh - touch_tol))
                or (e_name == "Left edge" and bx_t <= touch_tol)
                or (e_name == "Right edge" and (bx_t + bw_t) >= (ew - touch_tol))
            )
            if not touches_outer or min(bw_t, bh_t) < 5:
                continue
            comp_m = (lbl_t == i_t)
            if float(np.median(e_l[comp_m])) < 218.0 or float(np.median(e_s[comp_m])) > 16.0:
                continue
            # Reject narrow border-crossing sleeve scratches that continue beyond the drop-shadow bevel
            ccx = int(ex1 + cen_t[i_t][0])
            ccy = int(ey1 + cen_t[i_t][1])
            span_along = bw_t if e_name in ("Top edge", "Bottom edge") else bh_t
            crosses_out = False
            if span_along <= 20:
                if e_name == "Left edge" and margin_avail.get("left"):
                    ext = surf_resp[max(0, ccy - 4):min(surf_resp.shape[0], ccy + 5), max(0, cx1 - 20):max(0, cx1 - 6)]
                    crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
                elif e_name == "Right edge" and margin_avail.get("right"):
                    ext = surf_resp[max(0, ccy - 4):min(surf_resp.shape[0], ccy + 5), min(surf_resp.shape[1], cx2 + 6):min(surf_resp.shape[1], cx2 + 20)]
                    crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
                elif e_name == "Top edge" and margin_avail.get("top"):
                    ext = surf_resp[max(0, cy1 - 20):max(0, cy1 - 6), max(0, ccx - 4):min(surf_resp.shape[1], ccx + 5)]
                    crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
                elif e_name == "Bottom edge" and margin_avail.get("bottom"):
                    ext = surf_resp[min(surf_resp.shape[0], cy2 + 6):min(surf_resp.shape[0], cy2 + 20), max(0, ccx - 4):min(surf_resp.shape[1], ccx + 5)]
                    crosses_out = ext.size > 0 and int(np.count_nonzero(ext > 14)) >= 4
            if crosses_out:
                continue
            if a_t > best_a:
                best_a = a_t
                best_box = (int(ex1 + bx_t), int(ey1 + by_t), max(8, bw_t), max(8, bh_t))

        if best_box is not None:
            sev = 1.5 if best_a >= 400 else 1.0
            results.append(({
                "type": "edge_tear",
                "is_true_defect": True,
                "confidence": 0.90,
                "side": side_label,
                "zone": e_name,
                "severity": sev,
                "target": "edges",
            }, best_box))

    return results


def _detect_ink_spots(
    lab: np.ndarray,
    hsv: np.ndarray,
    local_box: tuple[int, int, int, int],
    glare_mask: np.ndarray,
    streak_mask: np.ndarray,
    side_label: str,
) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """
    Detects isolated compact dark ink blobs / Sharpie splatters (L* < 45, delta_L >= 60
    darker than smooth immediate ring, high solidity/circularity to reject text strokes).
    """
    results: list[tuple[dict, tuple[int, int, int, int]]] = []
    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)
    pad = max(8, int(min(cw, ch) * 0.015))
    ix1, iy1 = cx1 + pad, cy1 + pad
    ix2, iy2 = max(ix1 + 16, cx2 - pad), max(iy1 + 16, cy2 - pad)

    sub_l = lab[iy1:iy2, ix1:ix2, 0].astype(np.float32)
    ab_chroma = np.hypot(
        lab[iy1:iy2, ix1:ix2, 1].astype(np.float32) - 128.0,
        lab[iy1:iy2, ix1:ix2, 2].astype(np.float32) - 128.0,
    )
    sub_excl = glare_mask[iy1:iy2, ix1:ix2] | streak_mask[iy1:iy2, ix1:ix2]
    dark_bin = ((sub_l < 48.0) & (ab_chroma < 22.0) & (~sub_excl)).astype(np.uint8)

    cnts, _ = cv2.findContours(dark_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cands: list[tuple[float, float, int, int, int, int, float]] = []
    sh_i, sw_i = sub_l.shape
    for cnt in cnts:
        area = float(cv2.contourArea(cnt))
        if not (25.0 <= area <= 1400.0):
            continue
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bx <= 2 or by <= 2 or (bx + bw) >= (sw_i - 2) or (by + bh) >= (sh_i - 2):
            continue
        aspect = max(bw, bh) / float(max(1, min(bw, bh)))
        if aspect > 2.8:
            continue
        hull = cv2.convexHull(cnt)
        hull_a = float(cv2.contourArea(hull))
        solidity = area / max(1.0, hull_a)
        perim = max(1.0, cv2.arcLength(cnt, True))
        circularity = float(4.0 * np.pi * area / (perim * perim))
        if solidity < 0.72 or circularity < 0.45:
            continue

        # Local annular ring check (3-8 px outside blob to avoid anti-aliased ink feathering)
        px1, py1 = max(0, bx - 12), max(0, by - 12)
        px2, py2 = min(sw_i, bx + bw + 12), min(sh_i, by + bh + 12)
        mask_p = np.zeros((py2 - py1, px2 - px1), dtype=np.uint8)
        cv2.drawContours(mask_p, [cnt - np.array([px1, py1])], -1, 255, -1)
        dil_in = cv2.dilate(mask_p, np.ones((7, 7), dtype=np.uint8), iterations=1)
        dil_out = cv2.dilate(mask_p, np.ones((17, 17), dtype=np.uint8), iterations=1)
        ring_m = (dil_out > 0) & (dil_in == 0)
        blob_m = mask_p > 0
        if np.count_nonzero(ring_m) < 16 or np.count_nonzero(blob_m) < 12:
            continue
        patch_l = sub_l[py1:py2, px1:px2]
        blob_l_med = float(np.median(patch_l[blob_m]))
        if blob_l_med >= 48.0 or float(np.mean(patch_l[blob_m] < 55.0)) < 0.70:
            continue
        ring_vals = patch_l[ring_m]
        ring_l_med = float(np.median(ring_vals))
        ring_l_std = float(np.std(ring_vals))
        ring_l_iqr = float(np.percentile(ring_vals, 75) - np.percentile(ring_vals, 25))
        if (ring_l_med - blob_l_med) < 55.0 or ring_l_std > 16.0 or ring_l_iqr > 18.0:
            continue

        cands.append((bx + bw * 0.5, by + bh * 0.5, bx, by, bw, bh, area))

    if len(cands) > 8:
        return results

    # Reject collinear text/dot rows (>= 4 blobs aligned horizontally within 12 px)
    filtered: list[tuple[float, float, int, int, int, int, float]] = []
    for c in cands:
        row_peers = sum(1 for o in cands if abs(o[1] - c[1]) < 12.0)
        if row_peers >= 4:
            continue
        filtered.append(c)

    for cx_b, cy_b, bx, by, bw, bh, area in filtered:
        z_lbl = _zone_label(cx_b + pad, cy_b + pad, cw, ch)
        sev = 1.0 if area >= 150.0 else 0.5
        results.append(({
            "type": "ink_spot",
            "is_true_defect": True,
            "confidence": 0.85,
            "side": side_label,
            "zone": z_lbl,
            "severity": sev,
            "target": "surface",
        }, (int(ix1 + bx), int(iy1 + by), max(6, int(bw)), max(6, int(bh)))))

    return results


def _detect_margin_ink_bleed(
    lab: np.ndarray,
    lap_abs: np.ndarray,
    local_box: tuple[int, int, int, int],
    glare_mask: np.ndarray,
    streak_mask: np.ndarray,
    border_l_med: float,
    side_label: str,
) -> list[tuple[dict, tuple[int, int, int, int]]]:
    """
    On neutral white margins (border_l_med >= 210, |a*| < 4.5, |b*| < 7.5), detects localized
    smooth chromatic stain/ink bleed patches (dev >= 8.0 over < 25% of margin length),
    rejecting warm parchment cardstock and painted inner-frame/ribbon shadows.
    """
    results: list[tuple[dict, tuple[int, int, int, int]]] = []
    if border_l_med < 210.0:
        return results

    cx1, cy1, cx2, cy2 = local_box
    cw = max(40, cx2 - cx1)
    ch = max(40, cy2 - cy1)
    b_in = max(10, int(min(cw, ch) * 0.032))
    b_out = max(3, int(min(cw, ch) * 0.005))
    c_span = max(16, int(min(cw, ch) * 0.06))

    # Sample neutral border baseline a*, b*
    es = max(6, int(min(cw, ch) * 0.015))
    b_a = np.concatenate([
        lab[cy1:cy1 + es, cx1:cx2, 1].ravel(),
        lab[cy2 - es:cy2, cx1:cx2, 1].ravel(),
        lab[cy1:cy2, cx1:cx1 + es, 1].ravel(),
        lab[cy1:cy2, cx2 - es:cx2, 1].ravel(),
    ]).astype(np.float32) - 128.0
    b_b = np.concatenate([
        lab[cy1:cy1 + es, cx1:cx2, 2].ravel(),
        lab[cy2 - es:cy2, cx1:cx2, 2].ravel(),
        lab[cy1:cy2, cx1:cx1 + es, 2].ravel(),
        lab[cy1:cy2, cx2 - es:cx2, 2].ravel(),
    ]).astype(np.float32) - 128.0
    med_a = float(np.median(b_a)) if b_a.size else 0.0
    med_b = float(np.median(b_b)) if b_b.size else 0.0
    if abs(med_a) >= 4.5 or abs(med_b) >= 7.5:
        return results

    excl = glare_mask | streak_mask
    strips = [
        ("Top margin", (cx1 + c_span, cy1 + b_out, cx2 - c_span, cy1 + b_in)),
        ("Bottom margin", (cx1 + c_span, cy2 - b_in, cx2 - c_span, cy2 - b_out)),
        ("Left margin", (cx1 + b_out, cy1 + c_span, cx1 + b_in, cy2 - c_span)),
        ("Right margin", (cx2 - b_in, cy1 + c_span, cx2 - b_out, cy2 - c_span)),
    ]

    h_roi, w_roi = lab.shape[:2]
    for z_name, (sx1, sy1, sx2, sy2) in strips:
        if sx2 <= sx1 + 10 or sy2 <= sy1 + 10:
            continue
        p_l = lab[sy1:sy2, sx1:sx2, 0].astype(np.float32)
        if float(np.median(p_l)) < 230.0:
            continue
        p_a = cv2.GaussianBlur(lab[sy1:sy2, sx1:sx2, 1].astype(np.float32) - 128.0, (5, 5), 0)
        p_b = cv2.GaussianBlur(lab[sy1:sy2, sx1:sx2, 2].astype(np.float32) - 128.0, (5, 5), 0)
        p_lap = cv2.GaussianBlur(lap_abs[sy1:sy2, sx1:sx2].astype(np.float32), (9, 9), 0)
        p_ex = excl[sy1:sy2, sx1:sx2]

        paper_ok = (p_l >= 185.0) & (p_lap < 55.0) & (~p_ex)
        if np.count_nonzero(paper_ok) < 150 or float(np.std(p_l[paper_ok])) >= 14.0:
            continue
        strip_a = float(np.median(p_a[paper_ok]))
        strip_b = float(np.median(p_b[paper_ok]))
        if abs(strip_a) >= 4.5 or abs(strip_b) >= 7.5:
            continue

        dev = np.maximum(np.abs(p_a - strip_a), np.abs(p_b - strip_b))
        stain_m = (paper_ok & (dev >= 6.0)).astype(np.uint8)
        paper_cnt = max(1, int(np.count_nonzero(paper_ok)))
        if float(np.count_nonzero(stain_m)) / float(paper_cnt) >= 0.25:
            continue

        sh_m, sw_m = stain_m.shape
        n_st, lbl_st, st_st, _ = cv2.connectedComponentsWithStats(stain_m, connectivity=8)
        for i_s in range(1, n_st):
            a_s = int(st_st[i_s, cv2.CC_STAT_AREA])
            if a_s < 90:
                continue
            bx_s = int(st_st[i_s, cv2.CC_STAT_LEFT])
            by_s = int(st_st[i_s, cv2.CC_STAT_TOP])
            bw_s = int(st_st[i_s, cv2.CC_STAT_WIDTH])
            bh_s = int(st_st[i_s, cv2.CC_STAT_HEIGHT])
            if z_name in ("Top margin", "Bottom margin") and bw_s >= 0.25 * sw_m:
                continue
            if z_name in ("Left margin", "Right margin") and bh_s >= 0.25 * sh_m:
                continue

            comp_dev = dev[lbl_st == i_s]
            if float(np.max(comp_dev)) < 8.0 or int(np.count_nonzero(comp_dev >= 8.0)) < 25:
                continue

            # Outer-margin-only guard: if component touches inner boundary AND inner adjacent band
            # has dark/high-edge printed frame/ribbon artwork, reject as painted frame shadow.
            touches_inner = (
                (z_name == "Top margin" and (by_s + bh_s) >= sh_m - 2)
                or (z_name == "Bottom margin" and by_s <= 2)
                or (z_name == "Left margin" and (bx_s + bw_s) >= sw_m - 2)
                or (z_name == "Right margin" and bx_s <= 2)
            )
            reaches_outer_half = (
                (z_name == "Top margin" and by_s < sh_m * 0.5)
                or (z_name == "Bottom margin" and (by_s + bh_s) > sh_m * 0.5)
                or (z_name == "Left margin" and bx_s < sw_m * 0.5)
                or (z_name == "Right margin" and (bx_s + bw_s) > sw_m * 0.5)
            )
            if touches_inner and not reaches_outer_half:
                if z_name == "Top margin":
                    iy_a, iy_b = sy2, min(h_roi, sy2 + 4)
                    ix_a, ix_b = sx1 + bx_s, sx1 + bx_s + bw_s
                elif z_name == "Bottom margin":
                    iy_a, iy_b = max(0, sy1 - 4), sy1
                    ix_a, ix_b = sx1 + bx_s, sx1 + bx_s + bw_s
                elif z_name == "Left margin":
                    iy_a, iy_b = sy1 + by_s, sy1 + by_s + bh_s
                    ix_a, ix_b = sx2, min(w_roi, sx2 + 4)
                else:
                    iy_a, iy_b = sy1 + by_s, sy1 + by_s + bh_s
                    ix_a, ix_b = max(0, sx1 - 4), sx1
                if iy_b > iy_a and ix_b > ix_a:
                    adj_l = lab[iy_a:iy_b, ix_a:ix_b, 0]
                    adj_lap = lap_abs[iy_a:iy_b, ix_a:ix_b]
                    if float(np.median(adj_l)) < 195.0 or float(np.mean(adj_lap > 35.0)) > 0.20:
                        continue

            results.append(({
                "type": "surface_stain",
                "is_true_defect": True,
                "confidence": 0.78,
                "side": side_label,
                "zone": z_name,
                "severity": 0.5,
                "target": "surface",
            }, (int(sx1 + bx_s), int(sy1 + by_s), max(8, bw_s), max(8, bh_s))))

    return results


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

    c_span = max(12, int(min(cw, ch) * 0.042))
    edge_strip = max(6, int(min(cw, ch) * 0.015))
    border_band_l = np.concatenate([
        lab[cy1:cy1 + edge_strip, cx1:cx2, 0].ravel(),
        lab[cy2 - edge_strip:cy2, cx1:cx2, 0].ravel(),
        lab[cy1:cy2, cx1:cx1 + edge_strip, 0].ravel(),
        lab[cy1:cy2, cx2 - edge_strip:cx2, 0].ravel(),
    ])
    border_l_med = float(np.median(border_band_l)) if border_band_l.size else 180.0
    border_l_std = float(np.std(border_band_l)) if border_band_l.size else 0.0

    glare_mask, glare_pct = _detect_specular_glare_mask(lab, hsv, lap_abs, local_box, border_l_med=border_l_med)
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

    thr_surf = max(26, int(np.percentile(int_resp, 99.1)))
    thr_linear = int(np.clip(np.percentile(int_resp, 98.5), 26, 62))
    cand_bin = (int_resp > thr_linear).astype(np.uint8)
    cnts, _ = cv2.findContours(cand_bin, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # Pre-collect elongated linear strokes for parallel-family / periodic-line suppression
    # (jersey pinstripes, stacked book-page borders, hatched artwork)
    cand_bin_wide = (int_resp > max(18, int(thr_linear * 0.72))).astype(np.uint8)
    cnts_wide, _ = cv2.findContours(cand_bin_wide, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    linear_strokes: list[tuple[float, float, float, float, float]] = []
    for cnt_w in cnts_wide:
        if len(cnt_w) < 4:
            continue
        rw_w, rh_w = cv2.minAreaRect(cnt_w)[1]
        maj_w = max(float(rw_w), float(rh_w))
        min_w = max(1.0, min(float(rw_w), float(rh_w)))
        if maj_w >= 12.0 and (maj_w / min_w) >= 2.5:
            vx_w, vy_w, _, _ = cv2.fitLine(cnt_w.reshape(-1, 2).astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
            th_w = float(np.degrees(np.arctan2(vy_w, vx_w))) % 180.0
            bx_w, by_w, bw_w, bh_w = cv2.boundingRect(cnt_w)
            rmask_w = cand_bin_wide[by_w:by_w + bh_w, bx_w:bx_w + bw_w] > 0
            rpatch_w = int_resp[by_w:by_w + bh_w, bx_w:bx_w + bw_w]
            resp_w = float(np.median(rpatch_w[rmask_w])) if np.any(rmask_w) and rpatch_w.shape == rmask_w.shape else 0.0
            linear_strokes.append((bx_w + bw_w * 0.5, by_w + bh_w * 0.5, th_w, maj_w, resp_w))

    for cnt in cnts:
        area = float(cv2.contourArea(cnt))
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if area < 4.0 and max(bw, bh) < 4:
            continue
        cx_c = bx + bw * 0.5 + inset
        cy_c = by + bh * 0.5 + inset
        z_lbl = _zone_label(cx_c, cy_c, cw, ch)

        cand_roi_mask = cand_bin[by:by + bh, bx:bx + bw] > 0
        cand_resp_patch = int_resp[by:by + bh, bx:bx + bw]
        cand_max_resp = int(np.max(cand_resp_patch[cand_roi_mask])) if np.any(cand_roi_mask) and cand_resp_patch.shape == cand_roi_mask.shape else 0

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
        if major >= 18.0 and aspect >= 3.4:
            # Printed-artwork texture/stripe guard: skip dense halftone/text or wide straight chromatic printed stripes
            nb_lap = lap_abs[max(iy1, rcy - 9):min(iy2, rcy + 10), max(ix1, rcx - 9):min(ix2, rcx + 10)]
            edge_density = float(np.mean(nb_lap > 30.0)) if nb_lap.size else 0.0
            cand_sat_patch = hsv[iy1 + by:iy1 + by + bh, ix1 + bx:ix1 + bx + bw, 1]
            cand_med_sat = float(np.median(cand_sat_patch[cand_roi_mask])) if np.any(cand_roi_mask) and cand_sat_patch.shape == cand_roi_mask.shape else 0.0
            arc_half = cv2.arcLength(cnt, True) * 0.5
            tortuosity = arc_half / max(1.0, major)
            fill_ratio = area / max(1.0, float(bw * bh))
            stroke_w = area / max(1.0, arc_half)
            if cand_max_resp <= thr_surf:
                if major < 32.0 or aspect < 4.5 or edge_density > 0.22 or stroke_w > 4.5:
                    continue
            if edge_density > 0.42 or (cand_med_sat > 75.0 and stroke_w >= 4.0 and tortuosity <= 1.08):
                continue

            if cand_med_sat < 35.0 and (tortuosity > 1.25 or (minor / max(1.0, major) > 0.28 and fill_ratio < 0.30)):
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

            # Parallel-family / periodic-line guard: suppress jersey pinstripes, stacked
            # book-page borders, and hatched artwork (>= 2 parallel neighbors within +-45 px)
            if len(cnt) >= 4 and len(linear_strokes) >= 3:
                vx_c, vy_c, _, _ = cv2.fitLine(cnt.reshape(-1, 2).astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
                norm_c = float(np.hypot(vx_c, vy_c))
                if norm_c > 1e-6:
                    vx_c /= norm_c
                    vy_c /= norm_c
                    nx_c, ny_c = -vy_c, vx_c
                    theta_c = float(np.degrees(np.arctan2(vy_c, vx_c))) % 180.0
                    cx_loc, cy_loc = bx + bw * 0.5, by + bh * 0.5
                    cand_med_resp = float(np.median(cand_resp_patch[cand_roi_mask])) if np.any(cand_roi_mask) and cand_resp_patch.shape == cand_roi_mask.shape else 0.0
                    par_nbrs = 0
                    for cx_o, cy_o, th_o, maj_o, resp_o in linear_strokes:
                        d_ang = abs(theta_c - th_o)
                        d_ang = min(d_ang, 180.0 - d_ang)
                        if d_ang > 12.0:
                            continue
                        dx_o, dy_o = cx_o - cx_loc, cy_o - cy_loc
                        d_perp = abs(dx_o * nx_c + dy_o * ny_c)
                        if not (3.0 <= d_perp <= 45.0):
                            continue
                        d_par = abs(dx_o * vx_c + dy_o * vy_c)
                        if d_par > max(major, maj_o) * 0.75 + 25.0:
                            continue
                        if min(cand_med_resp, resp_o) / max(1.0, max(cand_med_resp, resp_o)) >= 0.28:
                            par_nbrs += 1
                            if par_nbrs >= 2:
                                break
                    if par_nbrs >= 2:
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
            elif minor <= 42.0 and (minor <= 8.5 or stroke_w <= 6.0) and major >= 18.0:
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
        if cand_max_resp > thr_surf and np.any(cand_roi_mask) and float(np.median(cand_resp_patch[cand_roi_mask])) > thr_surf and 4.0 <= area <= 240.0 and aspect < 3.2:
            gx_c = int(ix1 + bx + bw * 0.5)
            gy_c = int(iy1 + by + bh * 0.5)
            r_core = max(2, int(round(np.sqrt(area / np.pi))))
            y_lo, y_hi = max(iy1, gy_c - r_core - 8), min(iy2, gy_c + r_core + 9)
            x_lo, x_hi = max(ix1, gx_c - r_core - 8), min(ix2, gx_c + r_core + 9)
            patch_l = lab[y_lo:y_hi, x_lo:x_hi, 0].astype(np.float32)
            halo_diff = 0.0
            outer_std = 0.0
            if patch_l.size >= 36:
                yy, xx = np.ogrid[y_lo:y_hi, x_lo:x_hi]
                dist = np.sqrt((xx - gx_c) ** 2 + (yy - gy_c) ** 2)
                r_in = max(1.5, r_core * 0.5)
                ring_m = (dist > r_in) & (dist <= r_core + 2.5)
                outer_m = (dist > r_core + 3.5) & (dist <= r_core + 8.0)
                if np.any(ring_m) and np.any(outer_m):
                    halo_diff = abs(float(np.mean(patch_l[ring_m])) - float(np.mean(patch_l[outer_m])))
                    outer_std = float(np.std(patch_l[outer_m]))

            perim = max(1.0, cv2.arcLength(cnt, True))
            circularity = float(4.0 * np.pi * area / (perim * perim))

            # True fisheye sits on a relatively uniform surrounding ink field (outer_std <= 16.0),
            # whereas printed text characters ('E', 'O', '0') or filigree edges sit inside high-variance graphics.
            if area >= 18.0 and halo_diff >= 9.5 and circularity >= 0.48 and outer_std <= 16.0:
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
    pos_lobes = [(cen_p[i], int(st_p[i, cv2.CC_STAT_AREA])) for i in range(1, n_p) if 10 <= st_p[i, cv2.CC_STAT_AREA] <= 240 and max(int(st_p[i, cv2.CC_STAT_WIDTH]), int(st_p[i, cv2.CC_STAT_HEIGHT])) <= 2.6 * max(1, min(int(st_p[i, cv2.CC_STAT_WIDTH]), int(st_p[i, cv2.CC_STAT_HEIGHT])))]
    neg_lobes = [(cen_n[i], int(st_n[i, cv2.CC_STAT_AREA])) for i in range(1, n_n) if 10 <= st_n[i, cv2.CC_STAT_AREA] <= 240 and max(int(st_n[i, cv2.CC_STAT_WIDTH]), int(st_n[i, cv2.CC_STAT_HEIGHT])) <= 2.6 * max(1, min(int(st_n[i, cv2.CC_STAT_WIDTH]), int(st_n[i, cv2.CC_STAT_HEIGHT])))]

    used_neg = set()
    for pc, _ in pos_lobes[:20]:
        for j, (nc, _) in enumerate(neg_lobes[:20]):
            if j in used_neg:
                continue
            dist_pn = float(np.hypot(pc[0] - nc[0], pc[1] - nc[1]))
            if 5.0 <= dist_pn <= 28.0:
                mx = int(ix1 + (pc[0] + nc[0]) * 0.5)
                my = int(iy1 + (pc[1] + nc[1]) * 0.5)
                ab_patch = lab[max(iy1, my - 12):min(iy2, my + 12), max(ix1, mx - 12):min(ix2, mx + 12), 1:3]
                lap_patch = lap_abs[max(iy1, my - 10):min(iy2, my + 10), max(ix1, mx - 10):min(ix2, mx + 10)]
                # True dimples are compact circular shading dipoles on continuous hue (std(ab) < 7.5),
                # whereas printed ribbons/frames are elongated or have multi-color transitions.
                if (
                    ab_patch.size > 0
                    and float(np.mean(np.std(ab_patch, axis=(0, 1)))) < 7.5
                    and (lap_patch.size == 0 or (float(np.median(lap_patch)) <= 22.0 and float(np.percentile(lap_patch, 85)) <= 45.0))
                ):
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
    # White paper-core exposure (chipping/whitening) requires a uniform dark/colored border contrast
    # (border_l_med < 162 and border_l_std < 38); on white/light borders or high-contrast filigree
    # patterned borders (border_l_std >= 38), bright spots are just printed pattern or paper.
    white_thr_edge = max(190.0, border_l_med + (58.0 if light_border_mode else 34.0))
    skip_light_border = (border_l_med >= 162.0) or (border_l_std >= 38.0) or (light_border_mode and border_l_med >= 145.0)

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
        chip_m = ((e_l > white_thr_edge) & (e_s < 34) & (~e_gl)).astype(np.uint8)
        chip_frac = float(np.count_nonzero(chip_m)) / float(max(1, e_l.size))
        n_ch, lbl_ch, st_ch, cen_ch = cv2.connectedComponentsWithStats(chip_m, connectivity=8)
        # If multiple collinear small bright blobs appear along the strip, it is printed border text
        if n_ch >= 6:
            continue
        max_chip_a = 0
        best_chip_box = (ex1, ey1, max(8, ex2 - ex1), max(8, ey2 - ey1))
        for i_c in range(1, n_ch):
            a_c = int(st_ch[i_c, cv2.CC_STAT_AREA])
            if a_c < 14:
                continue
            bx_c = int(st_ch[i_c, cv2.CC_STAT_LEFT])
            by_c = int(st_ch[i_c, cv2.CC_STAT_TOP])
            bw_c = int(st_ch[i_c, cv2.CC_STAT_WIDTH])
            bh_c = int(st_ch[i_c, cv2.CC_STAT_HEIGHT])
            # True edge chipping must touch within 4px of the physical outer boundary of that edge
            touches_outer = (
                (e_name == "Top edge" and by_c <= 4)
                or (e_name == "Bottom edge" and (by_c + bh_c) >= (ey2 - ey1 - 4))
                or (e_name == "Left edge" and bx_c <= 4)
                or (e_name == "Right edge" and (bx_c + bw_c) >= (ex2 - ex1 - 4))
            )
            if not touches_outer:
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
                    int(ex1 + bx_c),
                    int(ey1 + by_c),
                    max(6, bw_c),
                    max(6, bh_c),
                )
        if max_chip_a >= 12 and chip_frac < 0.28:
            sev = 1.0 if max_chip_a >= 65 else 0.5
            confirmed.append(_attach_meta({
                "type": "edge_chipping",
                "is_true_defect": True,
                "confidence": 0.88,
                "side": side_label,
                "zone": e_name,
                "severity": sev,
                "target": "edges",
            }, best_chip_box))

    white_thr_corner = max(195.0, border_l_med + (58.0 if light_border_mode else 36.0))
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
        k_gl = glare_mask[ky1:ky2, kx1:kx2] | streak_mask[ky1:ky2, kx1:kx2]
        if skip_light_border:
            max_wh_a = 0
            wh_frac = 0.0
            best_wh_box = (kx1, ky1, max(8, kx2 - kx1), max(8, ky2 - ky1))
        else:
            wh_m = ((k_l > white_thr_corner) & (k_s < 36) & (~k_gl)).astype(np.uint8)
            wh_frac = float(np.count_nonzero(wh_m)) / float(max(1, k_l.size))
            n_wh, _, st_wh, _ = cv2.connectedComponentsWithStats(wh_m, connectivity=8)
            max_wh_a = 0
            best_wh_box = (kx1, ky1, max(8, kx2 - kx1), max(8, ky2 - ky1))
            kw_box = kx2 - kx1
            kh_box = ky2 - ky1
            for i_w in range(1, n_wh):
                a_w = int(st_wh[i_w, cv2.CC_STAT_AREA])
                bx_w = int(st_wh[i_w, cv2.CC_STAT_LEFT])
                by_w = int(st_wh[i_w, cv2.CC_STAT_TOP])
                bw_w = int(st_wh[i_w, cv2.CC_STAT_WIDTH])
                bh_w = int(st_wh[i_w, cv2.CC_STAT_HEIGHT])
                # Must touch near the physical outer tip of that corner
                touches_tip = (
                    (c_name == "Top-Left" and bx_w <= 6 and by_w <= 6)
                    or (c_name == "Top-Right" and (bx_w + bw_w) >= (kw_box - 6) and by_w <= 6)
                    or (c_name == "Bot-Left" and bx_w <= 6 and (by_w + bh_w) >= (kh_box - 6))
                    or (c_name == "Bot-Right" and (bx_w + bw_w) >= (kw_box - 6) and (by_w + bh_w) >= (kh_box - 6))
                )
                if touches_tip and a_w > max_wh_a:
                    max_wh_a = a_w
                    best_wh_box = (
                        int(kx1 + bx_w),
                        int(ky1 + by_w),
                        max(6, bw_w),
                        max(6, bh_w),
                    )
        if max_wh_a >= 14 and wh_frac < 0.38:
            sev = 1.0 if max_wh_a >= 75 else 0.5
            confirmed.append(_attach_meta({
                "type": "corner_whitening",
                "is_true_defect": True,
                "confidence": 0.80,
                "side": side_label,
                "zone": c_name,
                "severity": sev,
                "target": "corners",
            }, best_wh_box))

    for cs_item, cs_bbox in _detect_corner_softness(lab, local_box, margin_avail, glare_mask, streak_mask, side_label):
        confirmed.append(_attach_meta(cs_item, cs_bbox))

    for cc_item, cc_bbox in _detect_corner_creases(lab, lap_abs, local_box, glare_mask, streak_mask, side_label):
        confirmed.append(_attach_meta(cc_item, cc_bbox))

    for ed_item, ed_bbox in _detect_edge_silhouette_dings(lab, local_box, margin_avail, glare_mask, streak_mask, side_label):
        confirmed.append(_attach_meta(ed_item, ed_bbox))

    for et_item, et_bbox in _detect_edge_foil_peel_or_tear(lab, hsv, surf_resp, local_box, margin_avail, glare_mask, streak_mask, side_label):
        confirmed.append(_attach_meta(et_item, et_bbox))

    for ink_item, ink_bbox in _detect_ink_spots(lab, hsv, local_box, glare_mask, streak_mask, side_label):
        confirmed.append(_attach_meta(ink_item, ink_bbox))

    for st_item, st_bbox in _detect_margin_ink_bleed(lab, lap_abs, local_box, glare_mask, streak_mask, border_l_med, side_label):
        confirmed.append(_attach_meta(st_item, st_bbox))

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
        "corner_softness": "corner softness/blunting",
        "corner_crease": "corner crease/bend",
        "edge_chipping": "edge chipping",
        "edge_tear": "edge foil peel/tear",
        "edge_dent": "edge dent/ding",
        "ink_spot": "ink spot/splatter",
        "surface_stain": "surface stain/ink bleed",
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
