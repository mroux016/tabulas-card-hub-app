from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from PIL import Image

# Isolate all paths strictly inside %TEMP% before importing any Core module
_TEMP_ROOT = Path(tempfile.gettempdir()) / "tabulas_win4_tests"
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["CARDS_BASE_DIR"] = str(_TEMP_ROOT / "Hub")
os.environ["TABULAS_SET_LIBRARY_DIR"] = str(_TEMP_ROOT / "SetLibrary")
os.environ["TABULAS_ARCHIVE_DIR"] = str(_TEMP_ROOT / "Archive")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Core.compute_backend import get_active_gpu_worker_claims, run_compute_benchmark
from Core.surface_defect_engine import _cluster_and_nms_defects, inspect_card_surface_through_sleeve
from Core.vision_grader import estimate_card_pregrade


def _make_clean_card_in_sleeve(
    w: int = 750,
    h: int = 1050,
    margin: int = 40,
    border_rgb: tuple[int, int, int] = (45, 52, 68),
    interior_rgb: tuple[int, int, int] = (75, 105, 140),
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Creates a clean card inside a clear sleeve with realistic subtle paper grain."""
    rng = np.random.default_rng(42)
    canvas = np.full((h, w, 3), 232, dtype=np.uint8)
    x1, y1, x2, y2 = margin, margin, w - margin, h - margin
    canvas[y1:y2, x1:x2] = border_rgb
    b_pad = 32
    canvas[y1 + b_pad:y2 - b_pad, x1 + b_pad:x2 - b_pad] = interior_rgb
    # Subtle uniform texture so Laplacian variance is realistic for a crisp printed card
    noise = rng.integers(-4, 5, size=(y2 - y1, x2 - x1, 3), dtype=np.int16)
    card_sl = np.clip(canvas[y1:y2, x1:x2].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    canvas[y1:y2, x1:x2] = card_sl
    # Crisp printed player silhouette + border line
    cv2.rectangle(canvas, (x1 + b_pad, y1 + b_pad), (x2 - b_pad, y2 - b_pad), (210, 195, 160), 2)
    return Image.fromarray(canvas), (x1, y1, x2, y2)


def test_clean_card():
    f_im, f_box = _make_clean_card_in_sleeve()
    b_im, b_box = _make_clean_card_in_sleeve(border_rgb=(60, 62, 70), interior_rgb=(95, 100, 110))
    res = inspect_card_surface_through_sleeve(f_im, b_im, front_box=f_box, back_box=b_box, enable_onnx_anomaly=False)
    assert res["sub_surface"] >= 9.5, res
    assert res["sub_corners"] >= 9.5, res
    assert res["sub_edges"] >= 9.5, res
    assert len(res["confirmed_defects"]) == 0, res["confirmed_defects"]
    assert res["artifact_warning"] == "", res["artifact_warning"]

    pg = estimate_card_pregrade(f_im, b_im, front_box=f_box, back_box=b_box)
    assert float(pg["Sub_Surface"]) >= 9.5, pg
    assert "[Sleeve/Dust Check]" not in pg["Grading_Notes"], pg["Grading_Notes"]


def test_true_defects():
    # 1. Surface scratch
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im)
    cv2.line(arr, (260, 320), (430, 440), (242, 242, 242), 2)
    res_scr = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    types_scr = [d["type"] for d in res_scr["confirmed_defects"]]
    assert "surface_scratch" in types_scr, res_scr
    assert res_scr["sub_surface"] < 9.5, res_scr

    # 2. Factory print line (axis-aligned long line inside card)
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im)
    cv2.line(arr, (120, 520), (630, 520), (235, 235, 235), 2)
    res_pl = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    types_pl = [d["type"] for d in res_pl["confirmed_defects"]]
    assert "print_line" in types_pl, res_pl
    assert res_pl["sub_surface"] < 9.5, res_pl

    # 3. Dimple / dent (bright/dark shading dipole with continuous hue)
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im).astype(np.int16)
    cv2.circle(arr, (360, 500), 8, (45, 45, 45), -1)
    cv2.circle(arr, (370, 500), 8, (-45, -45, -45), -1)
    # Re-apply around base color cleanly
    base = np.array(f_im).astype(np.int16)
    yy, xx = np.ogrid[:arr.shape[0], :arr.shape[1]]
    lobe_p = np.exp(-((xx - 355) ** 2 + (yy - 500) ** 2) / 36.0) * 55.0
    lobe_n = np.exp(-((xx - 371) ** 2 + (yy - 500) ** 2) / 36.0) * 55.0
    dent_arr = np.clip(base + (lobe_p - lobe_n)[..., None], 0, 255).astype(np.uint8)
    res_dent = inspect_card_surface_through_sleeve(Image.fromarray(dent_arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    types_dent = [d["type"] for d in res_dent["confirmed_defects"]]
    assert "dimple_dent" in types_dent, res_dent

    # 4. Fisheye print spot (dark core + pale annular halo)
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im)
    cv2.circle(arr, (380, 420), 9, (220, 225, 230), -1)
    cv2.circle(arr, (380, 420), 4, (25, 30, 35), -1)
    res_fish = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    types_fish = [d["type"] for d in res_fish["confirmed_defects"]]
    assert "print_spot_fisheye" in types_fish, res_fish

    # 5. Edge chipping & Corner whitening (on Back side to verify 2-sided inspection)
    f_im, f_box = _make_clean_card_in_sleeve()
    b_im, b_box = _make_clean_card_in_sleeve()
    b_arr = np.array(b_im)
    # Corner whitening at Back Top-Left
    cv2.circle(b_arr, (b_box[0] + 8, b_box[1] + 8), 8, (238, 238, 238), -1)
    # Edge chipping on Back Right edge
    cv2.rectangle(b_arr, (b_box[2] - 8, 450), (b_box[2], 472), (235, 235, 235), -1)
    res_ec = inspect_card_surface_through_sleeve(f_im, Image.fromarray(b_arr), front_box=f_box, back_box=b_box, enable_onnx_anomaly=False)
    types_ec = [d["type"] for d in res_ec["confirmed_defects"]]
    assert "corner_whitening" in types_ec, res_ec
    assert "edge_chipping" in types_ec, res_ec
    assert res_ec["sub_corners"] < 9.5 and res_ec["sub_edges"] < 9.5, res_ec


def test_superficial_artifacts_no_penalty():
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im)
    # 1. Border-crossing sleeve scratch (starts in outer margin x=10, crosses card edge x=40 into x=160)
    cv2.line(arr, (10, 300), (180, 340), (248, 248, 248), 2)
    # 2. Curved hair / fiber
    pts = np.array([[280, 620], [310, 590], [350, 600], [380, 640], [340, 670]], dtype=np.int32)
    cv2.polylines(arr, [pts], False, (18, 18, 18), 2)
    # 3. Loose dust specks (tiny 2x2 dots) + margin dust
    for dx, dy in [(220, 240), (450, 280), (500, 700), (20, 120), (18, 600)]:
        cv2.circle(arr, (dx, dy), 2, (248, 248, 248), -1)
    # 4. Bright specular glare band (smooth L>235, S<24)
    cv2.rectangle(arr, (200, 760), (550, 840), (246, 246, 246), -1)

    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    assert len(res["confirmed_defects"]) == 0, f"False confirmed defects: {res['confirmed_defects']}"
    assert res["sub_surface"] >= 9.5, res
    assert "[Sleeve/Dust Check]" in res["artifact_warning"], res["artifact_warning"]

    pg = estimate_card_pregrade(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box)
    assert float(pg["Sub_Surface"]) >= 9.5, pg
    assert "[Sleeve/Dust Check]" in pg["Grading_Notes"], pg["Grading_Notes"]


def test_mixed_defect_and_artifact():
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im)
    # Real interior scratch
    cv2.line(arr, (250, 300), (440, 390), (245, 245, 245), 2)
    # Plus specular glare + dust
    cv2.rectangle(arr, (180, 740), (540, 820), (246, 246, 246), -1)
    cv2.circle(arr, (520, 250), 2, (248, 248, 248), -1)

    pg = estimate_card_pregrade(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box)
    assert float(pg["Sub_Surface"]) < 9.5, pg
    assert "[Sleeve/Dust Check]" in pg["Grading_Notes"], pg["Grading_Notes"]


def test_tight_crop_fallback():
    # Tightly cropped card with 0-2px margin outside card_box
    f_im, f_box = _make_clean_card_in_sleeve(w=670, h=970, margin=2)
    arr = np.array(f_im)
    cv2.line(arr, (220, 300), (400, 400), (245, 245, 245), 2)
    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    assert res["has_holder_margin_front"] is False
    assert any(d["type"] == "surface_scratch" for d in res["confirmed_defects"]), res


def test_precomputed_patch_tokens_reuse():
    f_im, f_box = _make_clean_card_in_sleeve()
    fake_tokens = np.ones((256, 64), dtype=np.float32)
    with mock.patch("Core.surface_defect_engine.is_neural_embeddings_enabled", return_value=True), \
         mock.patch("Core.surface_defect_engine.get_neural_embedding_engine") as mock_eng:
        res = inspect_card_surface_through_sleeve(
            f_im, None, front_box=f_box, front_patch_tokens=fake_tokens, enable_onnx_anomaly=True
        )
        mock_eng.assert_not_called()
        assert res["sub_surface"] >= 9.5


def test_cpu_parity_and_benchmark_no_slot_leak():
    f_im, f_box = _make_clean_card_in_sleeve()
    arr = np.array(f_im)
    cv2.line(arr, (250, 300), (440, 390), (245, 245, 245), 2)
    im_d = Image.fromarray(arr)
    res_auto = inspect_card_surface_through_sleeve(im_d, f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False, force_cpu=False)
    res_cpu = inspect_card_surface_through_sleeve(im_d, f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False, force_cpu=True)
    assert res_auto["sub_surface"] == res_cpu["sub_surface"]
    assert len(res_auto["confirmed_defects"]) == len(res_cpu["confirmed_defects"])

    claims_before = len(get_active_gpu_worker_claims())
    bench = run_compute_benchmark()
    claims_after = len(get_active_gpu_worker_claims())
    assert bench.get("defect_ai", {}).get("ready") is True, bench
    assert claims_after == claims_before, f"GPU slot leaked: before={claims_before}, after={claims_after}"


def test_scanner_streaks_vs_true_defects():
    # 1. Full-frame margin-crossing bright vertical CIS scanner streak -> scanner_streak (zero penalty)
    f_im, f_box = _make_clean_card_in_sleeve()
    arr_v = np.array(f_im)
    cv2.line(arr_v, (310, 0), (310, arr_v.shape[0] - 1), (242, 242, 242), 2)
    res_v = inspect_card_surface_through_sleeve(Image.fromarray(arr_v), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    assert len(res_v["confirmed_defects"]) == 0, f"Margin-crossing scanner streak misclassified as defect: {res_v['confirmed_defects']}"
    assert res_v["sub_surface"] >= 9.5, res_v
    assert any(a["type"] == "scanner_streak" and len(a.get("bbox_norm", [])) == 4 for a in res_v["superficial_artifacts"]), res_v["superficial_artifacts"]
    assert "scanner glass" in res_v["artifact_warning"].lower(), res_v["artifact_warning"]

    # 2. Full-frame single-channel RGB/CIS color-cast streak (green/cyan offset) -> scanner_streak (zero penalty)
    arr_rgb = np.array(f_im).astype(np.int16)
    arr_rgb[:, 420:422, 1] = np.clip(arr_rgb[:, 420:422, 1] + 55, 0, 255)
    res_rgb = inspect_card_surface_through_sleeve(Image.fromarray(arr_rgb.astype(np.uint8)), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    assert len(res_rgb["confirmed_defects"]) == 0, f"RGB CIS streak misclassified: {res_rgb['confirmed_defects']}"
    assert res_rgb["sub_surface"] >= 9.5, res_rgb
    assert any(a["type"] == "scanner_streak" for a in res_rgb["superficial_artifacts"]), res_rgb["superficial_artifacts"]

    # 3. Tight-cropped edge-to-edge constant-column scanner streak (no margin_ring) -> scanner_streak (zero penalty)
    t_im, t_box = _make_clean_card_in_sleeve(w=670, h=970, margin=2)
    arr_t = np.array(t_im)
    cv2.line(arr_t, (290, 0), (290, arr_t.shape[0] - 1), (245, 245, 245), 2)
    res_t = inspect_card_surface_through_sleeve(Image.fromarray(arr_t), t_im, front_box=t_box, back_box=t_box, enable_onnx_anomaly=False)
    assert len(res_t["confirmed_defects"]) == 0, f"Tight-cropped scanner streak misclassified: {res_t['confirmed_defects']}"
    assert res_t["sub_surface"] >= 9.5, res_t
    assert any(a["type"] == "scanner_streak" for a in res_t["superficial_artifacts"]), res_t["superficial_artifacts"]


def test_nms_clustering_and_edge_dent():
    # 1. Spatial NMS collapses nearby detections within 3.5% normalized distance into 1 union defect
    clustered = _cluster_and_nms_defects([
        {"id": "d1", "side": "Front", "type": "surface_scratch", "category": "surface", "severity": 0.5, "confidence": 0.75, "bbox_norm": [0.40, 0.40, 0.02, 0.02]},
        {"id": "d2", "side": "Front", "type": "surface_scratch", "category": "surface", "severity": 1.0, "confidence": 0.88, "bbox_norm": [0.415, 0.41, 0.02, 0.02]},
        {"id": "d3", "side": "Front", "type": "dimple_dent", "category": "surface", "severity": 0.5, "confidence": 0.80, "bbox_norm": [0.75, 0.75, 0.02, 0.02]},
    ])
    assert len(clustered) == 2, f"Expected 2 clusters, got {len(clustered)}: {clustered}"
    merged = next(d for d in clustered if d["id"] == "d2")
    assert merged["bbox_norm"] == [0.4, 0.4, 0.035, 0.03], merged
    assert merged["severity"] == 1.0 and merged["confidence"] == 0.88

    # 2. Edge-band dent (within 3.5% of card edge, outside corner tips) -> edge_dent under edges
    f_im, f_box = _make_clean_card_in_sleeve()
    base = np.array(f_im).astype(np.int16)
    yy, xx = np.ogrid[:base.shape[0], :base.shape[1]]
    # Place dipole in outer 3.5% edge band (13px..23px from edge, outside corner tips)
    ex = f_box[0] + 18
    ey = 520
    lobe_p = np.exp(-((xx - ex) ** 2 + (yy - (ey - 6)) ** 2) / 28.0) * 58.0
    lobe_n = np.exp(-((xx - ex) ** 2 + (yy - (ey + 6)) ** 2) / 28.0) * 58.0
    dent_arr = np.clip(base + (lobe_p - lobe_n)[..., None], 0, 255).astype(np.uint8)
    res_ed = inspect_card_surface_through_sleeve(Image.fromarray(dent_arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    edge_dents = [d for d in res_ed["confirmed_defects"] if d["type"] == "edge_dent"]
    assert len(edge_dents) >= 1, res_ed["confirmed_defects"]
    assert edge_dents[0]["category"] == "edges" and edge_dents[0]["marker_style"] == "arrow", edge_dents[0]


def test_white_border_pinstripes_no_glare_or_streak_explosion():
    # White-bordered card (L* ~244) with subtle vertical pinstripes must NOT trigger >15% glare or >3 streaks
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(244, 244, 242), interior_rgb=(238, 240, 242))
    arr = np.array(f_im)
    x1, y1, x2, y2 = f_box
    for px in range(x1 + 45, x2 - 45, 22):
        cv2.line(arr, (px, y1 + 36), (px, y2 - 36), (205, 208, 215), 2)
    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    streaks = [a for a in res["superficial_artifacts"] if a["type"] == "scanner_streak"]
    assert res["glare_pct_front"] <= 15.0, f"White border misclassified as glare: {res['glare_pct_front']}%"
    assert len(streaks) <= 3, f"Pinstripes triggered runaway scanner streaks: {len(streaks)}"


def test_corner_softness_and_scratch_lower_grade():
    # Real corner blunting/ding + surface scratch on a light-bordered card (with dark margin)
    # must be caught by _detect_corner_softness & scratch detector and lower grade below PSA 10
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(240, 240, 238), interior_rgb=(120, 145, 175))
    arr = np.array(f_im)
    x1, y1, x2, y2 = f_box
    # Darken outer margin slightly so white card border has clean edge contrast
    arr[:y1, :] = (40, 44, 52)
    arr[y2:, :] = (40, 44, 52)
    arr[:, :x1] = (40, 44, 52)
    arr[:, x2:] = (40, 44, 52)
    # Blunt/round the Top-Left corner by painting outer background color over the sharp tip
    pts = np.array([[x1 - 2, y1 - 2], [x1 + 18, y1 - 2], [x1 - 2, y1 + 18]], dtype=np.int32)
    cv2.fillPoly(arr, [pts], (40, 44, 52))
    # Plus a genuine surface scratch
    cv2.line(arr, (250, 380), (420, 470), (242, 242, 242), 2)

    card_im = Image.fromarray(arr)
    res = inspect_card_surface_through_sleeve(card_im, f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    types = [d["type"] for d in res["confirmed_defects"]]
    assert "corner_softness" in types, f"Expected corner_softness, got: {types}"
    assert "surface_scratch" in types, f"Expected surface_scratch, got: {types}"
    assert res["sub_corners"] < 9.5, res
    assert res["sub_surface"] < 9.5, res

    pg = estimate_card_pregrade(card_im, f_im, front_box=f_box, back_box=f_box)
    assert float(pg["Est_PSA"]) < 10.0, pg


def test_psa_bgs_grading_ceilings_on_confirmed_defects():
    from Core.vision_grader import recompute_grades_from_diagnostics

    base_diag = {
        "centering": {
            "front": {"lr": "50/50", "tb": "50/50", "lr_left": 50, "lr_right": 50, "tb_top": 50, "tb_bottom": 50, "sub_centering": 10.0},
            "back": {"lr": "50/50", "tb": "50/50", "lr_left": 50, "lr_right": 50, "tb_top": 50, "tb_bottom": 50, "sub_centering": 10.0},
        },
        "raw_confirmed_defects": [],
        "confirmed_defects": [],
        "superficial_artifacts": [],
    }
    # 1 defect -> Est_PSA <= 9.0, Est_BGS <= 9.5
    d1 = dict(base_diag, raw_confirmed_defects=[{"id": "f-1", "type": "surface_scratch", "category": "surface", "severity": 0.5, "penalty": 0.5}])
    g1, _ = recompute_grades_from_diagnostics(d1)
    assert float(g1["Est_PSA"]) <= 9.0 and float(g1["Est_BGS"]) <= 9.5, g1

    # >= 3 defects or total_penalty >= 1.5 -> Est_PSA <= 8.0
    d3 = dict(base_diag, raw_confirmed_defects=[
        {"id": "f-1", "type": "surface_scratch", "category": "surface", "severity": 0.5, "penalty": 0.5},
        {"id": "f-2", "type": "edge_dent", "category": "edges", "severity": 0.5, "penalty": 0.5},
        {"id": "f-3", "type": "ink_spot", "category": "surface", "severity": 0.5, "penalty": 0.5},
    ])
    g3, _ = recompute_grades_from_diagnostics(d3)
    assert float(g3["Est_PSA"]) <= 8.0, g3

    # Heavy structural (corner_crease or edge_tear or total_penalty >= 2.5) -> Est_PSA <= 7.0
    dc = dict(base_diag, raw_confirmed_defects=[{"id": "f-c", "type": "corner_crease", "category": "corners", "severity": 1.5, "penalty": 1.5}])
    gc, _ = recompute_grades_from_diagnostics(dc)
    assert float(gc["Est_PSA"]) <= 7.0, gc


def test_white_border_edge_silhouette_ding():
    # White-bordered card on light bed with a localized dark shadow notch on Right edge
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(242, 242, 240), interior_rgb=(120, 145, 175))
    arr = np.array(f_im)
    x1, y1, x2, y2 = f_box
    # Subtle drop-shadow bevel around physical card
    cv2.rectangle(arr, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (185, 185, 188), 2)
    # Plant localized dark notch touching outer Right edge at y=500..520
    cv2.rectangle(arr, (x2 - 12, 500), (x2, 520), (80, 82, 85), -1)
    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    edge_dents = [d for d in res["confirmed_defects"] if d["type"] == "edge_dent" and d["category"] == "edges"]
    assert len(edge_dents) >= 1, res["confirmed_defects"]


def test_corner_crease_detection():
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(240, 240, 238), interior_rgb=(240, 240, 238))
    arr = np.array(f_im)
    x1, y1, x2, y2 = f_box
    # Diagonal luminance crease across Bot-Right corner zone (slope /)
    pts = np.array([[x2 - 80, y2 - 6], [x2 - 6, y2 - 80], [x2 - 6, y2 - 6]], dtype=np.int32)
    cv2.fillPoly(arr, [pts], (216, 216, 214))
    cv2.line(arr, (x2 - 78, y2 - 8), (x2 - 8, y2 - 78), (195, 195, 193), 2)
    card_im = Image.fromarray(arr)
    res = inspect_card_surface_through_sleeve(card_im, f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    creases = [d for d in res["confirmed_defects"] if d["type"] == "corner_crease"]
    assert len(creases) >= 1, res["confirmed_defects"]
    assert creases[0]["category"] == "corners" and creases[0]["marker_style"] == "circle" and creases[0]["severity"] >= 1.5
    pg = estimate_card_pregrade(card_im, f_im, front_box=f_box, back_box=f_box)
    assert float(pg["Est_PSA"]) <= 7.0, pg


def test_edge_foil_peel_tear():
    # Colored/foil border with bright neutral irregular paper-core tear along bottom 0.5%-5% band
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(70, 130, 195), interior_rgb=(85, 110, 145))
    arr = np.array(f_im)
    x1, y1, x2, y2 = f_box
    pts = np.array([[340, y2 - 4], [375, y2 - 28], [405, y2 - 4]], dtype=np.int32)
    cv2.fillPoly(arr, [pts], (244, 244, 242))
    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    tears = [d for d in res["confirmed_defects"] if d["type"] == "edge_tear" and d["category"] == "edges"]
    assert len(tears) >= 1, res["confirmed_defects"]


def test_dark_ink_spot_and_thin_blue_pen_stroke():
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(240, 240, 238), interior_rgb=(140, 150, 160))
    arr = np.array(f_im)
    # 1. Isolated compact black ink blob (L* < 45)
    cv2.circle(arr, (220, 420), 9, (4, 5, 6), -1)
    # 2. Thin 2-px curved blue pen stroke
    pen_pts = np.array([[320, 520], [335, 555], [342, 595], [340, 635]], dtype=np.int32)
    cv2.polylines(arr, [pen_pts], False, (18, 45, 195), 2)
    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    types = [d["type"] for d in res["confirmed_defects"]]
    assert "ink_spot" in types, res["confirmed_defects"]
    assert "surface_scratch" in types, res["confirmed_defects"]
    ink = next(d for d in res["confirmed_defects"] if d["type"] == "ink_spot")
    assert ink["category"] == "surface" and ink["marker_style"] == "circle"


def test_white_margin_pink_bleed():
    f_im, f_box = _make_clean_card_in_sleeve(border_rgb=(244, 244, 244), interior_rgb=(120, 140, 160))
    arr = np.array(f_im)
    x1, y1, x2, y2 = f_box
    # Localized smooth pink ink bleed on right white margin (a* shift >= 8 over >= 200 px^2)
    cv2.rectangle(arr, (x2 - 26, 420), (x2 - 8, 520), (245, 212, 224), -1)
    res = inspect_card_surface_through_sleeve(Image.fromarray(arr), f_im, front_box=f_box, back_box=f_box, enable_onnx_anomaly=False)
    stains = [d for d in res["confirmed_defects"] if d["type"] == "surface_stain" and d["category"] == "surface"]
    assert len(stains) >= 1, res["confirmed_defects"]


if __name__ == "__main__":
    test_clean_card()
    print("[PASS] test_clean_card")
    test_true_defects()
    print("[PASS] test_true_defects")
    test_superficial_artifacts_no_penalty()
    print("[PASS] test_superficial_artifacts_no_penalty")
    test_mixed_defect_and_artifact()
    print("[PASS] test_mixed_defect_and_artifact")
    test_tight_crop_fallback()
    print("[PASS] test_tight_crop_fallback")
    test_precomputed_patch_tokens_reuse()
    print("[PASS] test_precomputed_patch_tokens_reuse")
    test_cpu_parity_and_benchmark_no_slot_leak()
    print("[PASS] test_cpu_parity_and_benchmark_no_slot_leak")
    test_scanner_streaks_vs_true_defects()
    print("[PASS] test_scanner_streaks_vs_true_defects")
    test_nms_clustering_and_edge_dent()
    print("[PASS] test_nms_clustering_and_edge_dent")
    test_white_border_pinstripes_no_glare_or_streak_explosion()
    print("[PASS] test_white_border_pinstripes_no_glare_or_streak_explosion")
    test_corner_softness_and_scratch_lower_grade()
    print("[PASS] test_corner_softness_and_scratch_lower_grade")
    test_psa_bgs_grading_ceilings_on_confirmed_defects()
    print("[PASS] test_psa_bgs_grading_ceilings_on_confirmed_defects")
    test_white_border_edge_silhouette_ding()
    print("[PASS] test_white_border_edge_silhouette_ding")
    test_corner_crease_detection()
    print("[PASS] test_corner_crease_detection")
    test_edge_foil_peel_tear()
    print("[PASS] test_edge_foil_peel_tear")
    test_dark_ink_spot_and_thin_blue_pen_stroke()
    print("[PASS] test_dark_ink_spot_and_thin_blue_pen_stroke")
    test_white_margin_pink_bleed()
    print("[PASS] test_white_margin_pink_bleed")
    print("ALL WIN #4 TESTS PASSED")
