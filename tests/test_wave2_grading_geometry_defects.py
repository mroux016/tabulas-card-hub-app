from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from Core.market_engine import compute_tier_aware_roi_and_recommendation
from Core.surface_defect_engine import _cluster_and_nms_defects, _inspect_single_side, _stable_defect_id
from Core.vision_grader import (
    _deskew_image_and_box,
    _map_bbox_norm_inverse,
    _measure_side_centering,
    estimate_card_pregrade,
    recompute_grades_from_diagnostics,
)


def _make_synthetic_skewed_card(w: int = 700, h: int = 1000, skew_deg: float = 4.0) -> tuple[Image.Image, dict]:
    """Creates a synthetic card rotated by `-skew_deg` and returns `(pil_img, orig_corners_norm)`."""
    arr = np.full((h, w, 3), 25, dtype=np.uint8)
    cx, cy = w * 0.5, h * 0.5
    card_w, card_h = 500.0, 700.0
    # Unrotated card box centered at (cx, cy)
    x1, y1 = cx - card_w * 0.5, cy - card_h * 0.5
    x2, y2 = cx + card_w * 0.5, cy + card_h * 0.5
    in_x1, in_y1 = x1 + 40.0, y1 + 50.0
    in_x2, in_y2 = x2 - 40.0, y2 - 50.0

    cv2.rectangle(arr, (int(x1), int(y1)), (int(x2), int(y2)), (240, 240, 240), -1)
    cv2.rectangle(arr, (int(in_x1), int(in_y1)), (int(in_x2), int(in_y2)), (40, 90, 180), -1)

    # Rotate image by -skew_deg so deskewing by +skew_deg restores axis alignment
    M_rot = cv2.getRotationMatrix2D((cx, cy), -skew_deg, 1.0)
    rot_arr = cv2.warpAffine(arr, M_rot, (w, h), flags=cv2.INTER_LINEAR, borderValue=(25, 25, 25))

    def _xf(px: float, py: float) -> list[float]:
        nx = float(M_rot[0, 0] * px + M_rot[0, 1] * py + M_rot[0, 2]) / float(w)
        ny = float(M_rot[1, 0] * px + M_rot[1, 1] * py + M_rot[1, 2]) / float(h)
        return [round(nx, 4), round(ny, 4)]

    corners_norm = {
        "tl": _xf(x1, y1),
        "tr": _xf(x2, y1),
        "bl": _xf(x1, y2),
        "br": _xf(x2, y2),
    }
    return Image.fromarray(rot_arr), corners_norm


def test_skewed_manual_corners_forward_mapped_without_inflating_outer_box():
    w, h = 700, 1000
    img, orig_corners = _make_synthetic_skewed_card(w=w, h=h, skew_deg=4.0)
    box = (50, 100, w - 50, h - 100)
    deskewed_img, work_box, m_inv = _deskew_image_and_box(img, box, 4.0, min_abs_deg=0.05)
    assert m_inv is not None

    cent = _measure_side_centering(
        deskewed_img,
        work_box,
        manual_corners=orig_corners,
        skew_deg=4.0,
        inv_matrix=m_inv,
    )
    outer_w_px = cent["outer_card_rect"][2] * w
    # True physical card width is 500 px; without forward-mapping, skewed AABB would inflate to ~548 px
    assert abs(outer_w_px - 500.0) <= 4.0


def test_manual_fine_skew_override_applies_below_auto_deadzone():
    img = Image.new("RGB", (400, 560), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 360, 520], fill=(245, 245, 245), outline=(30, 30, 30), width=3)
    draw.rectangle([70, 80, 330, 480], fill=(50, 100, 190))

    # Un-overridden 0.2 deg stays in 0.35 deg auto-deskew deadzone
    _, _, m_auto = _deskew_image_and_box(img, (40, 40, 360, 520), 0.2, min_abs_deg=0.35)
    assert m_auto is None

    # Explicit manual 0.2 deg override applies deskew down to 0.05 deg
    _, _, m_manual = _deskew_image_and_box(img, (40, 40, 360, 520), 0.2, min_abs_deg=0.05)
    assert m_manual is not None


def test_dismissed_defect_stays_dismissed_when_skew_deg_changes():
    # Build a synthetic card with one clear dark spot and verify its canonical ID survives skew_deg change
    front = Image.new("RGB", (600, 840), (242, 242, 242))
    draw = ImageDraw.Draw(front)
    draw.rectangle([40, 40, 560, 800], fill=(240, 240, 240))
    draw.rectangle([80, 80, 520, 760], fill=(230, 230, 230))
    # Clear dark ink spot at (200, 300)
    draw.ellipse([190, 290, 214, 314], fill=(10, 10, 10))
    back = front.copy()

    _, diag_0 = estimate_card_pregrade(
        front,
        back,
        front_box=(40, 40, 560, 800),
        back_box=(40, 40, 560, 800),
        overrides={"manual_geometry": {"front": {"skew_deg": 0.0}, "back": {"skew_deg": 0.0}}},
        return_diagnostics=True,
    )
    front_inks = [d for d in diag_0["confirmed_defects"] if d["side"] == "Front" and d["type"] == "ink_spot"]
    assert len(front_inks) == 1
    target_id = front_inks[0]["id"]

    # Re-evaluate with 2.0 deg skew AND target_id dismissed
    _, diag_2 = estimate_card_pregrade(
        front,
        back,
        front_box=(40, 40, 560, 800),
        back_box=(40, 40, 560, 800),
        overrides={
            "dismissed_defect_ids": [target_id],
            "manual_geometry": {"front": {"skew_deg": 2.0}, "back": {"skew_deg": 0.0}},
        },
        return_diagnostics=True,
    )
    surviving_inks = [d for d in diag_2["confirmed_defects"] if d["side"] == "Front" and d["type"] == "ink_spot"]
    assert surviving_inks == []


def test_cross_category_nms_preserves_overlapping_surface_and_edge_defects():
    defects = [
        {
            "type": "surface_scratch",
            "side": "Front",
            "category": "surface",
            "target": "surface",
            "severity": 1.0,
            "confidence": 0.90,
            "bbox_norm": [0.02, 0.40, 0.08, 0.04],
        },
        {
            "type": "edge_chipping",
            "side": "Front",
            "category": "edges",
            "target": "edges",
            "severity": 0.5,
            "confidence": 0.85,
            "bbox_norm": [0.01, 0.41, 0.02, 0.03],
        },
    ]
    merged = _cluster_and_nms_defects(defects, dist_thresh=0.035)
    types = {d["type"] for d in merged}
    assert types == {"surface_scratch", "edge_chipping"}


def test_manual_raw_price_preserved_even_with_verified_comp():
    res = compute_tier_aware_roi_and_recommendation(
        card_row={"Valuation_Source": "Manual", "Raw_Price": "42.50", "Est_PSA": "9.0", "Est_BGS": "9.0"},
        comp_row={"Ungraded": "12.00", "Match_Confidence": "Exact", "PSA_10": "90.00", "PSA_9": "35.00"},
    )
    assert res["Valuation_Source"] == "Manual"
    assert float(res["Raw_Price"]) == 42.50


def test_high09_back_emblem_suppression_and_flawed_card_recall():
    fixtures_dir = Path("tests/fixtures/real_cards")
    clean_backs = [
        "MLB - AL - East - Blue Jays - Base_008-back.jpg",
        "MLB - AL - Central - Twins - Limited_001-back.jpg",
        "[2026_Topps_Baseball]_[Base]_[#1]_[Aaron_Judge]_[1000003]_B.jpg",
    ]
    for fn in clean_backs:
        im = Image.open(fixtures_dir / fn).convert("RGB")
        cb = (0, 0, im.size[0], im.size[1])
        res = _inspect_single_side(im, cb, "Back")
        inks = [d for d in res["confirmed"] if d["type"] == "ink_spot"]
        assert inks == [], f"Expected 0 ink_spot FPs on {fn}, got {inks}"

    flawed = Image.open(fixtures_dir / "FLAWED_Card004726_F.jpg").convert("RGB")
    flawed_res = _inspect_single_side(flawed, (0, 0, *flawed.size), "Front")
    flawed_inks = [d for d in flawed_res["confirmed"] if d["type"] == "ink_spot"]
    assert len(flawed_inks) == 1


def test_map_bbox_norm_inverse_clamping_and_bgs_ceilings():
    M = cv2.getRotationMatrix2D((500.0, 700.0), 5.0, 1.0)
    M_inv = cv2.invertAffineTransform(M)
    clamped = _map_bbox_norm_inverse([0.99, 0.99, 0.05, 0.05], 1000, 1400, M_inv)
    assert 0.0 <= clamped[0] <= 0.998
    assert 0.0 <= clamped[1] <= 0.998
    assert clamped[0] + clamped[2] <= 1.0001
    assert clamped[1] + clamped[3] <= 1.0001

    base_diag = {
        "sku": "TEST-MED01",
        "target_type": "inventory",
        "source_images": {"front_size": [700, 1000], "back_size": [700, 1000]},
        "centering": {
            "front": {"lr": "50/50", "tb": "50/50", "worst_axis": 50.0, "sub_centering": 10.0},
            "back": {"lr": "50/50", "tb": "50/50", "worst_axis": 50.0, "sub_centering": 10.0},
        },
        "raw_confirmed_defects": [
            {
                "id": "front-corner_crease-1-1",
                "type": "corner_crease",
                "side": "Front",
                "category": "corners",
                "target": "corners",
                "severity": 1.5,
                "penalty": 1.5,
                "confidence": 0.95,
                "is_true_defect": True,
                "bbox_norm": [0.02, 0.02, 0.05, 0.05],
            }
        ],
        "confirmed_defects": [],
        "superficial_artifacts": [],
        "overrides": {},
    }
    _, out = recompute_grades_from_diagnostics(base_diag)
    assert out["grades"]["psa"]["overall"] == 7.0
    assert out["grades"]["bgs"]["overall"] <= 7.5
    assert out["grades"]["bgs"]["tier"] == "NM"
