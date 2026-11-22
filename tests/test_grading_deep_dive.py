import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SANDBOX_ROOT = Path(__file__).resolve().parent.parent
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))


def _make_synthetic_card_image(
    width: int = 800,
    height: int = 1120,
    with_scratch: bool = False,
    with_corner_whitening: bool = False,
) -> Image.Image:
    """Generates a crisp synthetic card inside a dark holder margin with optional planted defects."""
    img = Image.new("RGB", (width, height), (22, 26, 34))
    draw = ImageDraw.Draw(img)

    # Card outer border (light gray/white) inside holder margin
    cx1, cy1, cx2, cy2 = 40, 40, width - 40, height - 40
    draw.rectangle([cx1, cy1, cx2, cy2], fill=(232, 234, 238))

    # Inner colored design frame
    ix1, iy1, ix2, iy2 = 85, 95, width - 85, height - 95
    draw.rectangle([ix1, iy1, ix2, iy2], fill=(54, 92, 138))

    # Uniform interior artwork block (continuous mid-tone so planted scratch stands out cleanly)
    draw.rectangle([130, 160, width - 130, height - 160], fill=(176, 182, 190))

    if with_scratch:
        # Plant a sharp 160px diagonal dark scratch in the uniform interior
        draw.line([(260, 420), (420, 520)], fill=(38, 40, 44), width=4)

    if with_corner_whitening:
        # Plant a bright whitening chip on a darker corner border
        draw.rectangle([cx1, cy1, cx1 + 52, cy1 + 52], fill=(42, 46, 56))
        draw.rectangle([cx1 + 6, cy1 + 6, cx1 + 22, cy1 + 22], fill=(250, 250, 252))

    return img


class TestGradingDeepDive(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.set_lib = self.base / "SetLibrary"
        self.archive = self.base / "Archive"
        (self.base / "Data" / "Inventory_Management").mkdir(parents=True, exist_ok=True)
        (self.base / "Cache").mkdir(parents=True, exist_ok=True)
        (self.set_lib / "_My_Collection" / "Test Set").mkdir(parents=True, exist_ok=True)
        (self.set_lib / "Unprocessed_Cards" / "Batches" / "Batch_01").mkdir(parents=True, exist_ok=True)

        os.environ["CARDS_BASE_DIR"] = str(self.base)
        os.environ["TABULAS_SET_LIBRARY_DIR"] = str(self.set_lib)
        os.environ["TABULAS_ARCHIVE_DIR"] = str(self.archive)

        # Reload config & dependent modules against isolated temp dirs
        import importlib
        import Core.config as cfg
        import Core.database as db
        import Core.surface_defect_engine as sde
        import Core.vision_grader as vg

        importlib.reload(cfg)
        importlib.reload(db)
        importlib.reload(sde)
        importlib.reload(vg)
        self.cfg = cfg
        self.db = db
        self.vg = vg
        self.cfg.ensure_directories()

        # Seed isolated Inventory.csv with 1 uncomped card (blank Raw_Price, Valuation_Source="Uncomped")
        self.sku = "1000901"
        self.front_name = "Test_Set_Base_1_Player_1000901_F.jpg"
        self.back_name = "Test_Set_Base_1_Player_1000901_B.jpg"
        set_dir = self.cfg.REVIEWED_CARDS_DIR / "Test Set"
        set_dir.mkdir(parents=True, exist_ok=True)
        _make_synthetic_card_image(with_scratch=True).save(set_dir / self.front_name, format="JPEG", quality=95)
        _make_synthetic_card_image(with_scratch=False).save(set_dir / self.back_name, format="JPEG", quality=95)

        import pandas as pd
        row = {col: "" for col in self.cfg.INVENTORY_COLUMNS}
        row.update({
            "SKU": self.sku,
            "Status": "In Stock",
            "Hold_Tag": "For Sale",
            "Set": "Test Set",
            "Subset": "Base",
            "Card Number": "1",
            "Player": "Test Player",
            "Front_File": self.front_name,
            "Back_File": self.back_name,
            "Raw_Price": "",
            "Valuation_Source": "Uncomped",
        })
        df = pd.DataFrame([row])
        self.db.save_inventory_df(df)

    def tearDown(self):
        self._tmp.cleanup()

    def test_batch_sidecar_key_fallback(self):
        p_blank = self.vg.get_grading_diagnostics_path(
            sku="",
            target_type="batch",
            batch_name="2026-11-22_Batch A",
            front_file="Scan_001_F.jpg",
        )
        self.assertTrue(p_blank.name.startswith("batch_"))
        self.assertIn("Scan_001_F", p_blank.name)
        self.assertTrue(p_blank.name.endswith(".json"))

    def test_sidecar_geometry_flag_error_and_reset(self):
        # 1. Inspect card -> computes & caches sidecar JSON atomically
        res = self.vg.inspect_card_grading_diagnostics("inventory", self.sku)
        self.assertTrue(res["success"], res)
        self.assertFalse(res["cached"])
        diag = res["diagnostics"]

        diag_path = self.vg.get_grading_diagnostics_path(sku=self.sku, target_type="inventory")
        self.assertTrue(diag_path.exists())

        # Verify normalized centering geometry on both Front & Back
        for side_k in ("front", "back"):
            c = diag["centering"][side_k]
            self.assertEqual(len(c["outer_card_rect"]), 4)
            self.assertEqual(len(c["inner_frame_rect"]), 4)
            for v in c["outer_card_rect"] + c["inner_frame_rect"]:
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)

        # Verify planted surface scratch was detected with bbox_norm & marker_style
        surf_defs = [d for d in diag["confirmed_defects"] if d.get("category") == "surface"]
        self.assertGreaterEqual(len(surf_defs), 1, f"Expected planted scratch, got: {diag['confirmed_defects']}")
        scratch = surf_defs[0]
        self.assertEqual(scratch["marker_style"], "box")
        self.assertEqual(len(scratch["bbox_norm"]), 4)
        self.assertTrue(scratch["id"].startswith("front-"))

        sub_surf_before = float(diag["grades"]["psa"]["subgrades"]["surface"])
        self.assertLess(sub_surf_before, 9.5)

        # Second call hits cache
        res_cached = self.vg.inspect_card_grading_diagnostics("inventory", self.sku)
        self.assertTrue(res_cached["cached"])

        # 2. Flag Error: dismiss the false-positive scratch -> immediate re-evaluation
        flag_res = self.vg.flag_grading_error_and_reevaluate(
            target_type="inventory",
            sku=self.sku,
            payload={
                "errorType": "false_positive_artifact",
                "side": "Front",
                "targetItemId": scratch["id"],
                "notes": "Synthetic sleeve reflection",
            },
        )
        self.assertTrue(flag_res["success"], flag_res)
        self.assertTrue(flag_res["feedbackLogged"])

        sub_surf_after = float(flag_res["card"]["Sub_Surface"])
        self.assertGreater(sub_surf_after, sub_surf_before)
        self.assertEqual(sub_surf_after, 9.5)
        self.assertEqual(flag_res["card"].get("Valuation_Source"), "Uncomped")
        self.assertEqual(flag_res["card"].get("Raw_Price"), "")

        # Verify JSONL feedback log
        fb_log = self.cfg.GRADING_FEEDBACK_LOG_FILE
        self.assertTrue(fb_log.exists())
        lines = [json.loads(ln) for ln in fb_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["target_item_id"], scratch["id"])

        # Verify force_recompute=True preserves overrides
        res_re = self.vg.inspect_card_grading_diagnostics("inventory", self.sku, force_recompute=True)
        self.assertIn(scratch["id"], res_re["diagnostics"]["overrides"]["dismissed_defect_ids"])
        self.assertEqual(float(res_re["diagnostics"]["grades"]["psa"]["subgrades"]["surface"]), 9.5)

        # 3. Flag centering_sleeve_rim -> updates sleeve_inset_pct & re-measures centering
        cent_res = self.vg.flag_grading_error_and_reevaluate(
            target_type="inventory",
            sku=self.sku,
            payload={"errorType": "centering_sleeve_rim", "side": "Front"},
        )
        self.assertTrue(cent_res["success"])
        self.assertGreater(cent_res["diagnostics"]["overrides"]["sleeve_inset_pct"], 0.0)

        # 4. Reset Overrides -> restores original detection & subgrades
        rst_res = self.vg.flag_grading_error_and_reevaluate(
            target_type="inventory",
            sku=self.sku,
            payload={"errorType": "reset_overrides", "resetOverrides": True},
        )
        self.assertTrue(rst_res["success"])
        self.assertEqual(rst_res["diagnostics"]["overrides"]["dismissed_defect_ids"], [])
        self.assertEqual(float(rst_res["card"]["Sub_Surface"]), sub_surf_before)

        # 5. Flag Error with errorType="scanner_streak" -> dismisses misclassified defect & restores Sub_Surface
        sc_res = self.vg.flag_grading_error_and_reevaluate(
            target_type="inventory",
            sku=self.sku,
            payload={
                "errorType": "scanner_streak",
                "side": "Front",
                "targetItemId": scratch["id"],
                "notes": "CIS glass streak",
            },
        )
        self.assertTrue(sc_res["success"])
        self.assertEqual(float(sc_res["card"]["Sub_Surface"]), 9.5)
        self.assertIn(scratch["id"], sc_res["diagnostics"]["overrides"]["dismissed_defect_ids"])

        # 6. Manual Geometry Update (outer_card_rect, inner_frame_rect, and 4 corners)
        geom_res = self.vg.update_card_grading_geometry(
            target_type="inventory",
            sku=self.sku,
            payload={
                "side": "Front",
                "outer_card_rect": [0.05, 0.04, 0.90, 0.92],
                "inner_frame_rect": [0.12, 0.09, 0.76, 0.82],
                "corners": {"tl": [0.05, 0.04], "tr": [0.95, 0.04], "bl": [0.05, 0.96], "br": [0.95, 0.96]},
            },
        )
        self.assertTrue(geom_res["success"])
        f_cent = geom_res["diagnostics"]["centering"]["front"]
        for a, b in zip(f_cent["outer_card_rect"], [0.05, 0.04, 0.90, 0.92]):
            self.assertAlmostEqual(a, b, places=2)
        for a, b in zip(f_cent["inner_frame_rect"], [0.12, 0.09, 0.76, 0.82]):
            self.assertAlmostEqual(a, b, places=2)
        self.assertEqual(f_cent["corners"]["tl"], [0.05, 0.04])

        # 7. Flag Error with errorType="not_a_defect_artwork" -> resets first, then dismisses & logs
        self.vg.flag_grading_error_and_reevaluate(
            target_type="inventory",
            sku=self.sku,
            payload={"errorType": "reset_overrides", "resetOverrides": True},
        )
        art_res = self.vg.flag_grading_error_and_reevaluate(
            target_type="inventory",
            sku=self.sku,
            payload={
                "errorType": "not_a_defect_artwork",
                "side": "Front",
                "targetItemId": scratch["id"],
                "notes": "Printed pinstripe",
            },
        )
        self.assertTrue(art_res["success"])
        self.assertEqual(float(art_res["card"]["Sub_Surface"]), 9.5)
        self.assertIn(scratch["id"], art_res["diagnostics"]["overrides"]["dismissed_defect_ids"])

    def test_center_out_edge_detection_portrait_landscape_and_mini(self):
        # Test portrait & landscape cards with a bright outer penny-sleeve rim + verify non-collapsed outer/inner
        for w, h, label in [(800, 1120, "portrait"), (1120, 800, "landscape")]:
            img = Image.new("RGB", (w, h), (18, 22, 28))
            d = ImageDraw.Draw(img)
            # Outer bright penny-sleeve rim
            d.rectangle([16, 16, w - 16, h - 16], outline=(245, 245, 248), width=3)
            # True physical card stock
            cx1, cy1, cx2, cy2 = 55, 55, w - 55, h - 55
            d.rectangle([cx1, cy1, cx2, cy2], fill=(228, 230, 234))
            d.rectangle([cx1 + 45, cy1 + 45, cx2 - 45, cy2 - 45], fill=(48, 92, 145))
            box = self.vg.detect_physical_card_box(img)
            # Must stay near true card stock [55..w-55], NOT snap outward to sleeve rim [16..w-16]
            self.assertGreaterEqual(box[0], 35, f"{label} left snapped to sleeve: {box}")
            self.assertLessEqual(box[2], w - 35, f"{label} right snapped to sleeve: {box}")
            self.assertGreaterEqual(box[1], 35, f"{label} top snapped to sleeve: {box}")
            self.assertLessEqual(box[3], h - 35, f"{label} bottom snapped to sleeve: {box}")
            cent = self.vg._measure_side_centering(img, box)
            oc, ic = cent["outer_card_rect"], cent["inner_frame_rect"]
            self.assertGreater(ic[0] - oc[0], 0.015, f"{label} outer/inner collapsed on left: {oc} vs {ic}")
            self.assertGreater((oc[0] + oc[2]) - (ic[0] + ic[2]), 0.015, f"{label} outer/inner collapsed on right: {oc} vs {ic}")

        # Allen & Ginter Mini (~0.571) sitting off-center inside a larger cool-gray standard sleeve
        sw, sh = 790, 1080
        mini_in_sleeve = Image.new("RGB", (sw, sh), (180, 190, 204))
        dm = ImageDraw.Draw(mini_in_sleeve)
        # Off-center mini card on right side (width=440, height=770 -> ar=0.571)
        dm.rectangle([280, 150, 720, 920], fill=(225, 226, 214))
        dm.rectangle([315, 195, 685, 875], fill=(64, 105, 82))
        mbox = self.vg.detect_physical_card_box(mini_in_sleeve)
        m_ar = (mbox[2] - mbox[0]) / max(1.0, float(mbox[3] - mbox[1]))
        self.assertGreaterEqual(mbox[0], 220, f"Mini snapped to empty left sleeve: {mbox}")
        self.assertLess(m_ar, 0.63, f"Mini card aspect clipped to standard: {mbox} (ar={m_ar:.3f})")

    def test_light_bed_sleeve_glare_full_bleed_centering_and_patterned_border_defects(self):
        # 1. Light scanner bed (RGB ~226) with bright neutral specular sleeve glare at bottom/right edge
        w, h = 800, 1120
        light_bed = Image.new("RGB", (w, h), (225, 226, 228))
        dl = ImageDraw.Draw(light_bed)
        # Specular neutral sleeve glare along right & bottom scan rim
        dl.rectangle([w - 18, 0, w - 1, h - 1], fill=(252, 252, 253))
        dl.rectangle([0, h - 18, w - 1, h - 1], fill=(252, 252, 253))
        # Physical card inside [45, 45, w-45, h-45] with warm ivory paper border
        dl.rectangle([45, 45, w - 45, h - 45], fill=(232, 228, 210))
        dl.rectangle([85, 85, w - 85, h - 85], fill=(42, 78, 128))
        lbox = self.vg.detect_physical_card_box(light_bed)
        self.assertLessEqual(lbox[2], w - 30, f"Light-bed right edge grabbed specular sleeve glare: {lbox}")
        self.assertLessEqual(lbox[3], h - 30, f"Light-bed bottom edge grabbed specular sleeve glare: {lbox}")

        # 2. Full-bleed / borderless card with high outer-strip texture and asymmetric interior element
        import numpy as np
        rng = np.random.default_rng(42)
        bleed_arr = rng.integers(35, 215, size=(h, w, 3), dtype=np.uint8)
        bleed_im = Image.fromarray(bleed_arr)
        cent_bleed = self.vg._measure_side_centering(bleed_im, (40, 40, w - 40, h - 40))
        self.assertTrue(cent_bleed.get("borderless_detected"), f"Expected borderless_detected=True: {cent_bleed}")
        self.assertEqual(cent_bleed["lr"], "50/50")
        self.assertEqual(cent_bleed["tb"], "50/50")

        # 3. Neutral patterned white/gray border (high grayscale variance, low chroma) must NOT trigger borderless_detected
        pat_gray = rng.integers(145, 245, size=(h, w), dtype=np.uint8)
        pat_rgb = np.stack([pat_gray, pat_gray, pat_gray], axis=-1)
        pat_im = Image.fromarray(pat_rgb)
        dp = ImageDraw.Draw(pat_im)
        # Asymmetric inner printed frame inside patterned white/gray border (left=56px, right=34px -> ~62/38)
        dp.rectangle([40 + 56, 40 + 44, w - 40 - 34, h - 40 - 44], fill=(35, 70, 120), outline=(15, 20, 30), width=3)
        cent_pat = self.vg._measure_side_centering(pat_im, (40, 40, w - 40, h - 40))
        self.assertFalse(cent_pat.get("borderless_detected"), f"Patterned neutral border falsely flagged borderless: {cent_pat}")
        self.assertNotEqual(cent_pat["lr"], "50/50")

    def test_skewed_drop_shadow_detection_and_gauge_update(self):
        import cv2
        import numpy as np
        w, h = 800, 1120
        canvas = np.full((h, w, 3), 240, dtype=np.uint8)
        cx1, cy1, cx2, cy2 = 60, 60, w - 60, h - 60
        # Thin gray drop-shadow bevel around physical card on white scanner bed
        cv2.rectangle(canvas, (cx1 - 2, cy1 - 2), (cx2 + 2, cy2 + 2), (175, 175, 178), 3)
        # White card border
        cv2.rectangle(canvas, (cx1, cy1), (cx2, cy2), (242, 242, 240), -1)
        # Inner printed frame
        cv2.rectangle(canvas, (cx1 + 48, cy1 + 52), (cx2 - 48, cy2 - 52), (45, 78, 128), -1)

        # Rotate clockwise by +2.0° (OpenCV getRotationMatrix2D uses -2.0 for CW)
        M = cv2.getRotationMatrix2D((w * 0.5, h * 0.5), -2.0, 1.0)
        skewed_arr = cv2.warpAffine(canvas, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(240, 240, 240))
        skewed_im = Image.fromarray(skewed_arr)

        box = self.vg.detect_physical_card_box(skewed_im)
        # Physical box should stay outside inner printed frame (x1 <= 85, x2 >= w - 85)
        self.assertLessEqual(box[0], 85, f"Outer box collapsed inward: {box}")
        self.assertGreaterEqual(box[2], w - 85, f"Outer box collapsed inward: {box}")

        skew_est = self.vg.estimate_card_skew_deg(skewed_im, box)
        self.assertAlmostEqual(skew_est, 2.0, delta=0.65, msg=f"Expected ~+2.0° skew, got {skew_est}°")

        # Persist manual gauge update (skew_deg + card_format + nudged outer_card_rect) via update_card_grading_geometry
        res_upd = self.vg.update_card_grading_geometry(
            target_type="inventory",
            sku=self.sku,
            payload={
                "side": "Front",
                "source": "centering_gauge",
                "skew_deg": 2.0,
                "card_format": "standard",
                "outer_card_rect": [0.055, 0.04, 0.89, 0.92],
            },
        )
        self.assertTrue(res_upd["success"], res_upd)
        diag_after = res_upd["diagnostics"]
        self.assertEqual(diag_after["centering"]["front"]["skew_deg"], 2.0)
        self.assertEqual(diag_after["centering"]["front"]["card_format"], "standard")
        self.assertEqual(diag_after["overrides"]["manual_geometry"]["front"]["skew_deg"], 2.0)
        self.assertEqual(res_upd["card"]["Valuation_Source"], "Uncomped")
        self.assertEqual(str(res_upd["card"]["Raw_Price"] or ""), "")
        self.assertTrue(self.vg.GRADING_FEEDBACK_LOG_FILE.exists())


if __name__ == "__main__":
    unittest.main()
