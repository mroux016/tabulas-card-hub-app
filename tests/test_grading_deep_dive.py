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

    def test_center_out_edge_detection_portrait_landscape_and_mini(self):
        # Test portrait & landscape cards with a bright outer penny-sleeve rim (20px outside card_box)
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

        # Non-standard mini card (~0.55 aspect) must not be clipped to 2.5:3.5
        mw, mh = 600, 1080
        mini = Image.new("RGB", (mw, mh), (18, 22, 28))
        dm = ImageDraw.Draw(mini)
        dm.rectangle([60, 40, mw - 60, mh - 40], fill=(230, 230, 232))
        dm.rectangle([90, 80, mw - 90, mh - 80], fill=(70, 110, 85))
        mbox = self.vg.detect_physical_card_box(mini)
        m_ar = (mbox[2] - mbox[0]) / max(1.0, float(mbox[3] - mbox[1]))
        self.assertLess(m_ar, 0.62, f"Mini card aspect clipped to standard: {mbox} (ar={m_ar:.3f})")


if __name__ == "__main__":
    unittest.main()
