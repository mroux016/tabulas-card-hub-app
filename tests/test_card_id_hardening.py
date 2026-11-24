import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Core import vision_grader as vg


def _make_synthetic_card(border_rgb: tuple[int, int, int], center_rgb: tuple[int, int, int], w: int = 200, h: int = 280) -> np.ndarray:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :] = border_rgb
    arr[36 : h - 36, 26 : w - 26] = center_rgb
    # Add deterministic texture inside center photo so center artwork is identical across Base & Parallel
    for y in range(44, h - 44, 12):
        arr[y : y + 4, 34 : w - 34] = (40, 80, 140)
    return arr


def _make_checklist_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["norm_cnum"] = df["Card Number"].astype(str).apply(vg.norm)
    df["norm_player"] = df["Player"].astype(str).apply(vg.norm)
    df["norm_team"] = df["Team"].astype(str).apply(vg.norm)
    df["attr_tags"] = [[] for _ in range(len(df))]
    df["is_multi_player"] = False
    df["norm_player_parts"] = [() for _ in range(len(df))]
    df["norm_player_lasts"] = [() for _ in range(len(df))]
    return df


def test_180_upside_down_orientation_recovery(monkeypatch):
    # Create a landscape card back (width > height) so we also verify aspect ratio preservation
    upright_img = Image.new("RGB", (360, 250), (245, 245, 240))
    upside_down_img = upright_img.rotate(180, expand=True)

    # Mock RapidOCR to return upright card tokens only when rotated 180° back to upright
    def fake_ocr_detailed(img_np):
        # Use a pixel marker on top-left vs bottom-right to distinguish 0° vs 180°
        # Or simply inspect image orientation & a deterministic corner pixel
        h, w = img_np.shape[:2]
        if w <= h:
            return []
        tl_mean = float(np.mean(img_np[:20, :20]))
        if tl_mean < 120.0:
            # Upright orientation has dark header marker at top-left
            return [
                {"text": "TOPPS BASEBALL SERIES ONE", "conf": 0.98, "bw": 220, "bh": 22, "cy": 0.14},
                {"text": "BATTING RECORD", "conf": 0.96, "bw": 160, "bh": 20, "cy": 0.30},
                {"text": "BORN 05/12/1999", "conf": 0.95, "bw": 150, "bh": 18, "cy": 0.42},
                {"text": "THE TOPPS COMPANY MLBPA", "conf": 0.97, "bw": 240, "bh": 18, "cy": 0.86},
            ]
        # Upside-down orientation (0°): footer is at top, low confidence gibberish
        return [
            {"text": "X", "conf": 0.35, "bw": 20, "bh": 18, "cy": 0.12},
        ]

    # Paint dark marker in top-left of upright_img -> moves to bottom-right in upside_down_img
    arr = np.array(upright_img)
    arr[:40, :40] = (20, 20, 20)
    upside_down_img = Image.fromarray(arr).rotate(180, expand=True)

    monkeypatch.setattr(vg, "_run_rapidocr_detailed", fake_ocr_detailed)
    monkeypatch.setattr(vg, "_run_rapidocr_lines", lambda np_im: [it["text"] for it in fake_ocr_detailed(np_im)])

    oriented_back, bundle = vg.extract_back_ocr_and_orient(upside_down_img, preferred_angle=0, force_all_angles=False)
    assert bundle["back_rotation_angle"] == 180
    assert oriented_back.width == 360 and oriented_back.height == 250
    assert bundle["back_is_landscape"] is True

    oriented_front, front_ang, meta = vg.normalize_card_orientation_for_id(upside_down_img, side="front")
    assert front_ang == 180
    assert oriented_front.width == 360 and oriented_front.height == 250
    assert meta["best_score"] > meta["score_0"]


def test_inner_card_crop_and_border_ring_parallel_scorer(tmp_path):
    # Create a yellow-bordered parallel card inside a dark scanner-mat / toploader margin
    yellow_card = _make_synthetic_card(border_rgb=(245, 210, 35), center_rgb=(180, 190, 200), w=200, h=280)
    base_card = _make_synthetic_card(border_rgb=(242, 242, 242), center_rgb=(180, 190, 200), w=200, h=280)

    # Wrap yellow_card in a 30px dark scanner mat margin (260x340)
    canvas = np.full((340, 260, 3), 18, dtype=np.uint8)
    canvas[30:310, 30:230] = yellow_card

    cropped = vg._crop_inner_card_for_id(canvas)
    # Dark margin must be stripped in-memory without touching disk
    assert cropped.shape[0] < 320 and cropped.shape[1] < 240
    assert cropped.shape[0] >= 260 and cropped.shape[1] >= 180

    # Save references in tmp_path
    base_p = tmp_path / "base_F.jpg"
    yel_p = tmp_path / "yellow_F.jpg"
    Image.fromarray(base_card).save(base_p, format="JPEG", quality=95)
    Image.fromarray(yellow_card).save(yel_p, format="JPEG", quality=95)

    # Border-ring scorer must separate Yellow parallel from White-bordered Base
    res_base = vg.score_border_ring_parallel(cropped, subset_name="Base", base_ref=base_card)
    res_yel = vg.score_border_ring_parallel(cropped, subset_name="Yellow", base_ref=base_card, candidate_ref=yellow_card)
    assert res_base["is_colored_border"] is True
    assert res_base["dominant_color"] == "yellow_gold"
    assert res_base["score_delta"] < 0
    assert res_yel["score_delta"] > 0.10

    # End-to-end tournament check: verify_and_correct_parallel_match picks Yellow over Base
    monkeypatch_disable_neural = False
    old_neural = vg.is_neural_embeddings_enabled
    vg.is_neural_embeddings_enabled = lambda: False
    try:
        tmpl_cat = {
            vg.canonical_set_key("2026 Topps Baseball"): {
                "Base": {"front_vecs": [], "back_vecs": [], "cards": {"10": [{"front_path": str(base_p), "back_path": ""}]}},
                "Yellow": {"front_vecs": [], "back_vecs": [], "cards": {"10": [{"front_path": str(yel_p), "back_path": ""}]}},
            }
        }
        ver = vg.verify_and_correct_parallel_match(
            front_img=Image.fromarray(canvas),
            front_box=(0, 0, canvas.shape[1], canvas.shape[0]),
            back_img=None,
            back_box=None,
            set_name="2026 Topps Baseball",
            card_number="10",
            current_subset="Base",
            valid_subsets=["Base", "Yellow"],
            ordinary_roots={"Base"},
            template_catalog=tmpl_cat,
            reviewed_by_card={},
            reviewed_parallels={},
        )
        assert ver["subset"] == "Yellow"
    finally:
        vg.is_neural_embeddings_enabled = old_neural


def test_serial_number_regex_and_base_disqualification(tmp_path):
    # Valid serials
    assert vg._parse_serial_denominator_from_lines(["174/399"]) == "399"
    assert vg._parse_serial_denominator_from_lines(["017/099"]) == "99"
    assert vg._parse_serial_denominator_from_lines(["0412/2026"]) == "2026"
    # Invalid / non-serials (dates, heights, batting lines)
    assert vg._parse_serial_denominator_from_lines(["Born 3/11/1998"]) is None
    assert vg._parse_serial_denominator_from_lines(["Date 03/11"]) is None
    assert vg._parse_serial_denominator_from_lines(["03/11"]) is None
    assert vg._parse_serial_denominator_from_lines(["HT 6/2 WT 210"]) is None
    assert vg._parse_serial_denominator_from_lines(["Batting 3/4 with 2 RBI"]) is None

    # Disqualify Base in favor of /399 parallel when 174/399 is detected
    base_card = _make_synthetic_card(border_rgb=(240, 240, 240), center_rgb=(170, 170, 170))
    base_p = tmp_path / "base_F.jpg"
    Image.fromarray(base_card).save(base_p, format="JPEG", quality=95)

    old_neural = vg.is_neural_embeddings_enabled
    vg.is_neural_embeddings_enabled = lambda: False
    try:
        tmpl_cat = {
            vg.canonical_set_key("2026 Topps Baseball"): {
                "Base": {"front_vecs": [], "back_vecs": [], "cards": {"42": [{"front_path": str(base_p), "back_path": ""}]}},
            }
        }
        pr_map = {("2026 Topps Baseball", "Green Foil", "42"): "399"}
        ver = vg.verify_and_correct_parallel_match(
            front_img=Image.fromarray(base_card),
            front_box=(0, 0, base_card.shape[1], base_card.shape[0]),
            back_img=None,
            back_box=None,
            set_name="2026 Topps Baseball",
            card_number="42",
            current_subset="Base",
            valid_subsets=["Base", "Green Foil"],
            ordinary_roots={"Base"},
            template_catalog=tmpl_cat,
            reviewed_by_card={},
            reviewed_parallels={},
            print_run_map=pr_map,
            detected_serial_denom="399",
        )
        assert ver["subset"] == "Green Foil"
        assert "SN_BaseDisqualified" in ver["top3_str"] or "SN_Match" in ver["top3_str"]
    finally:
        vg.is_neural_embeddings_enabled = old_neural


def test_sport_guardrail_stacked_alphanumeric_and_autograph_boost():
    root_df = _make_checklist_df([
        {
            "Set": "2025-26 Topps Basketball",
            "Subset": "Base",
            "Card Number": "91A-JC",
            "Player": "John Collins",
            "Team": "Jazz",
            "Attributes": "",
        },
        {
            "Set": "2026 Topps Baseball",
            "Subset": "Base",
            "Card Number": "91A-JC",
            "Player": "Junior Caminero",
            "Team": "Rays",
            "Attributes": "",
        },
        {
            "Set": "2026 Topps Baseball",
            "Subset": "1991 Topps Baseball Autographs",
            "Card Number": "91A-JC",
            "Player": "Junior Caminero",
            "Team": "Rays",
            "Attributes": "AU",
        },
    ])

    ocr_bundle = {
        "full_lines": [
            "TOPPS BASEBALL",
            "91A-",
            "JC",
            "JUNIOR CAMINERO",
            "TOPPS CERTIFIED AUTOGRAPH ISSUE",
            "MAJOR LEAGUE BASEBALL MLBPA",
        ],
        "header_norm": ["91A-", "JC", "JUNIOR CAMINERO"],
        "header_inv": [],
        "corner_zoom": ["91A-", "JC"],
        "ricoh_0deg": [],
    }

    best_row, score, reasons = vg.match_card_identity(ocr_bundle, root_df)
    assert best_row is not None
    assert best_row["Set"] == "2026 Topps Baseball"
    assert best_row["Card Number"] == "91A-JC"
    assert best_row["Subset"] == "1991 Topps Baseball Autographs"
    assert "AutoOCRBoost" in reasons


def test_multi_angle_rotate_and_reprocess_ignores_stale_set(tmp_path, monkeypatch):
    # 1. Multi-angle rotate (+90, 180, -90 -> 270)
    im = Image.new("RGB", (120, 200), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.rectangle([0, 0, 59, 99], fill=(220, 30, 30))  # Top-left red quadrant
    img_p = tmp_path / "card_F.jpg"
    im.save(img_p, format="JPEG", quality=96)

    # Seed lazy caches to verify invalidation
    vg._LAZY_VEC_CACHE[str(img_p)] = np.ones(4, dtype=np.float32)

    res_90 = vg.rotate_card_image_file(img_p, 90)
    assert res_90["rotatedDegrees"] == 90
    assert (res_90["width"], res_90["height"]) == (200, 120)
    assert str(img_p) not in vg._LAZY_VEC_CACHE
    with Image.open(img_p) as r1:
        assert r1.size == (200, 120)
        # 90° CW moves top-left red quadrant to top-right
        assert r1.getpixel((170, 25))[0] > 180

    res_neg90 = vg.rotate_card_image_file(img_p, -90)
    assert res_neg90["rotatedDegrees"] == 270
    assert (res_neg90["width"], res_neg90["height"]) == (120, 200)

    res_180 = vg.rotate_card_image_file(img_p, 180)
    assert res_180["rotatedDegrees"] == 180
    assert (res_180["width"], res_180["height"]) == (120, 200)

    # 2. Reprocess batch card ignores stale wrong Set ("2025-26 Topps Basketball") and routes to Baseball
    batch_dir = tmp_path / "Batch_Test"
    batch_dir.mkdir()
    f_file = batch_dir / "Card_0001_F.jpg"
    b_file = batch_dir / "Card_0001_B.jpg"
    Image.new("RGB", (200, 280), (240, 240, 240)).save(f_file, format="JPEG", quality=94)
    Image.new("RGB", (200, 280), (240, 240, 240)).save(b_file, format="JPEG", quality=94)

    man_df = pd.DataFrame([{
        "SKU": "0000001",
        "Set": "2025-26 Topps Basketball",
        "Card_Number": "#999",
        "Player": "Wrong Player",
        "Team": "Wrong Team",
        "Subset_Parallel": "Base",
        "Print_Run": "",
        "Attributes": "",
        "Front_File": f_file.name,
        "Back_File": b_file.name,
        "Corners_File": "Card_0001_C.jpg",
        "OCR_Confidence": "40",
        "OCR_Signals": "",
        "Template_Similarity": "0.000",
        "Top_3_Template_Candidates": "",
        "Matched_Template_Front": "",
        "Matched_Template_Back": "",
        "Needs_Review": "True",
    }])
    man_df.to_csv(batch_dir / "Batch_Inventory_Manifest.csv", index=False)

    chk_df = _make_checklist_df([
        {
            "Set": "2025-26 Topps Basketball",
            "Subset": "Base",
            "Card Number": "999",
            "Player": "Wrong Player",
            "Team": "Lakers",
            "Attributes": "",
        },
        {
            "Set": "2026 Topps Baseball",
            "Subset": "1991 Topps Baseball Autographs",
            "Card Number": "91A-JC",
            "Player": "Junior Caminero",
            "Team": "Rays",
            "Attributes": "AU",
        },
    ])

    monkeypatch.setattr(vg, "REFERENCE_TEMPLATES_DIR", tmp_path / "RefLib")
    monkeypatch.setattr(vg, "REVIEWED_CARDS_DIR", tmp_path / "Reviewed")
    monkeypatch.setattr(vg, "CHECKLIST_PATH", tmp_path / "Master_Checklist.csv")
    monkeypatch.setattr(
        vg,
        "load_master_checklist",
        lambda *a, **kw: (chk_df, {("2026 Topps Baseball", "91AJC", "JUNIORCAMINERO"): ["1991 Topps Baseball Autographs"]}, {"Base"}, {}),
    )
    monkeypatch.setattr(vg, "index_set_templates_and_reviewed_cards", lambda *a, **kw: ({}, {}, {}))
    monkeypatch.setattr(
        vg,
        "extract_back_ocr_and_orient",
        lambda b_im, **kw: (
            b_im,
            {
                "full_lines": ["TOPPS BASEBALL", "91A-", "JC", "JUNIOR CAMINERO", "TOPPS CERTIFIED AUTOGRAPH ISSUE", "MLBPA"],
                "header_norm": ["91A-", "JC", "JUNIOR CAMINERO"],
                "header_inv": [],
                "corner_zoom": ["91A-", "JC"],
                "ricoh_0deg": [],
                "back_rotation_angle": 0,
                "back_score_0": 150.0,
                "back_best_score": 150.0,
                "back_is_landscape": False,
            },
        ),
    )
    monkeypatch.setattr(vg, "orient_front_card_image", lambda front_img, **kw: (front_img, 0, "Default"))
    monkeypatch.setattr(vg, "detect_physical_card_box", lambda im_x, **kw: (0, 0, im_x.width, im_x.height))
    monkeypatch.setattr(
        vg,
        "apply_manifest_overrides_and_rename",
        lambda b_dir, df_override=None, **kw: (df_override, 0, 0),
    )

    reproc_res = vg.reprocess_single_batch_card(batch_dir=batch_dir, sku="0000001", regrade_too=False)
    assert reproc_res["success"] is True
    assert reproc_res["card"]["Set"] == "2026 Topps Baseball"
    assert reproc_res["card"]["Player"] == "Junior Caminero"
    assert reproc_res["card"]["Card_Number"] == "#91A-JC"
