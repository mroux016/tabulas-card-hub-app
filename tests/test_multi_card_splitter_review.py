from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _draw_rotated_card(
    canvas: np.ndarray,
    cx: float,
    cy: float,
    w: int,
    h: int,
    angle_deg: float,
    fill_rgb: tuple[int, int, int],
    border_rgb: tuple[int, int, int] = (25, 25, 25),
) -> None:
    """Draw a synthetic card rectangle rotated around `(cx, cy)` onto `canvas`."""
    box = cv2.boxPoints(((float(cx), float(cy)), (float(w), float(h)), float(angle_deg)))
    pts = np.int32(np.round(box))
    cv2.fillPoly(canvas, [pts], fill_rgb)
    cv2.polylines(canvas, [pts], isClosed=True, color=border_rgb, thickness=3)

    # Inner frame to simulate card artwork / border contrast
    inner_box = cv2.boxPoints(((float(cx), float(cy)), (float(w) * 0.72, float(h) * 0.72), float(angle_deg)))
    inner_pts = np.int32(np.round(inner_box))
    inner_col = tuple(max(0, min(255, int(c * 0.7 + 40))) for c in fill_rgb)
    cv2.fillPoly(canvas, [inner_pts], inner_col)


def _synthesize_flatbed_page(
    specs: list[dict],
    page_size: tuple[int, int] = (1200, 1600),
    bg_rgb: tuple[int, int, int] = (242, 242, 242),
) -> Image.Image:
    w, h = page_size
    canvas = np.full((h, w, 3), bg_rgb, dtype=np.uint8)
    for sp in specs:
        _draw_rotated_card(
            canvas,
            cx=sp["cx"],
            cy=sp["cy"],
            w=sp["w"],
            h=sp["h"],
            angle_deg=sp.get("angle", 0.0),
            fill_rgb=sp["rgb"],
        )
    return Image.fromarray(canvas, mode="RGB")


def _dominant_rgb(img: Image.Image) -> tuple[float, float, float]:
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    center = arr[int(h * 0.25) : int(h * 0.75), int(w * 0.25) : int(w * 0.75)]
    if center.size == 0:
        center = arr
    return tuple(float(x) for x in np.mean(center, axis=(0, 1)))


class MultiCardSplitterReviewTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.staging_dir = self.root / "Splitter_Review"
        self.profile_path = self.root / "splitter_learning_profile.json"
        self.output_dir = self.root / "Batch_Out"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        import Core.flatbed_splitter as fs
        self.fs = fs

    def tearDown(self):
        self._tmp.cleanup()

    def test_arbitrary_count_position_rotation_detection_and_toploader_padding(self):
        """Verify 2, 3, and 5 cards at arbitrary positions/angles are detected with toploader padding."""
        layouts = [
            # 2 cards (mixed portrait + landscape)
            [
                {"cx": 330, "cy": 460, "w": 220, "h": 310, "angle": -14.0, "rgb": (200, 40, 40)},
                {"cx": 820, "cy": 1050, "w": 310, "h": 220, "angle": 11.0, "rgb": (40, 160, 60)},
            ],
            # 3 cards (scattered triangle layout)
            [
                {"cx": 300, "cy": 380, "w": 210, "h": 295, "angle": 8.0, "rgb": (40, 80, 210)},
                {"cx": 860, "cy": 440, "w": 210, "h": 295, "angle": -17.0, "rgb": (210, 150, 30)},
                {"cx": 560, "cy": 1140, "w": 295, "h": 210, "angle": 5.0, "rgb": (150, 50, 190)},
            ],
            # 5 cards (non-grid mixed placement & rotations)
            [
                {"cx": 260, "cy": 310, "w": 200, "h": 280, "angle": -12.0, "rgb": (210, 50, 50)},
                {"cx": 640, "cy": 350, "w": 200, "h": 280, "angle": 9.0, "rgb": (50, 180, 70)},
                {"cx": 960, "cy": 420, "w": 200, "h": 280, "angle": -6.0, "rgb": (50, 90, 215)},
                {"cx": 360, "cy": 1080, "w": 280, "h": 200, "angle": 15.0, "rgb": (215, 160, 40)},
                {"cx": 860, "cy": 1160, "w": 200, "h": 280, "angle": -19.0, "rgb": (170, 50, 195)},
            ],
        ]

        profile = self.fs.load_splitter_profile(self.profile_path)
        for specs in layouts:
            page_img = _synthesize_flatbed_page(specs)
            boxes = self.fs.detect_cards_on_page(page_img, profile=profile)
            self.assertEqual(len(boxes), len(specs), f"Expected {len(specs)} cards, got {len(boxes)}: {boxes}")
            for b in boxes:
                for key in ("cx", "cy", "width", "height", "angle_deg", "confidence", "pair_id", "color"):
                    self.assertIn(key, b)
                self.assertGreater(b["width"], b["raw_width"])
                self.assertGreater(b["height"], b["raw_height"])
                self.assertGreater(b["confidence"], 0.4)

    def test_pancake_flip_front_back_auto_pairing(self):
        """Verify pancake-flip (in-place with slight shift/rotation) & mirrored_x auto-pairing."""
        front_specs = [
            {"cx": 310, "cy": 400, "w": 210, "h": 295, "angle": 10.0, "rgb": (210, 40, 40)},
            {"cx": 860, "cy": 450, "w": 210, "h": 295, "angle": -12.0, "rgb": (40, 180, 60)},
            {"cx": 580, "cy": 1150, "w": 210, "h": 295, "angle": 6.0, "rgb": (40, 80, 220)},
        ]
        # Pancake flip: each card flipped in place with minor x/y shift & negated angle
        back_pancake_specs = [
            {"cx": 592, "cy": 1138, "w": 210, "h": 295, "angle": -6.0, "rgb": (40, 80, 220)},
            {"cx": 324, "cy": 412, "w": 210, "h": 295, "angle": -10.0, "rgb": (210, 40, 40)},
            {"cx": 848, "cy": 460, "w": 210, "h": 295, "angle": 12.0, "rgb": (40, 180, 60)},
        ]

        f_img = _synthesize_flatbed_page(front_specs)
        b_img = _synthesize_flatbed_page(back_pancake_specs)
        profile = self.fs.load_splitter_profile(self.profile_path)
        f_boxes = self.fs.detect_cards_on_page(f_img, profile=profile)
        b_boxes = self.fs.detect_cards_on_page(b_img, profile=profile)

        paired_f, paired_b, mode = self.fs.match_front_back_pancake(
            f_boxes, b_boxes, f_img.size, b_img.size, flip_mode="auto", profile=profile
        )
        self.assertEqual(mode, "pancake")
        self.assertEqual([b["pair_id"] for b in paired_f], [1, 2, 3])
        self.assertEqual([b["pair_id"] for b in paired_b], [1, 2, 3])
        self.assertEqual([b["color"] for b in paired_f], [b["color"] for b in paired_b])

        # Verify each paired back center is near its corresponding front center
        for fb, bb in zip(paired_f, paired_b):
            self.assertLess(abs(fb["cx"] - bb["cx"]), 45.0)
            self.assertLess(abs(fb["cy"] - bb["cy"]), 45.0)

        # Also verify horizontal mirror auto-detection
        back_mirror_specs = [
            {"cx": 1200 - sp["cx"], "cy": sp["cy"] + 8, "w": sp["w"], "h": sp["h"], "angle": -sp["angle"], "rgb": sp["rgb"]}
            for sp in front_specs
        ]
        b_mir_img = _synthesize_flatbed_page(back_mirror_specs)
        b_mir_boxes = self.fs.detect_cards_on_page(b_mir_img, profile=profile)
        _, paired_b_mir, mode_mir = self.fs.match_front_back_pancake(
            f_boxes, b_mir_boxes, f_img.size, b_mir_img.size, flip_mode="auto", profile=profile
        )
        self.assertEqual(mode_mir, "mirrored_x")
        for fb, bb in zip(paired_f, paired_b_mir):
            self.assertAlmostEqual(fb["cx"], 1200.0 - bb["cx"], delta=35.0)

    def test_repairing_swapped_pair_ids_produces_correctly_paired_crops(self):
        """Swapping pair_id on back boxes during review produces swapped back crops."""
        front_specs = [
            {"cx": 320, "cy": 500, "w": 220, "h": 310, "angle": -8.0, "rgb": (220, 30, 30)},   # Red -> pair 1
            {"cx": 860, "cy": 500, "w": 220, "h": 310, "angle": 10.0, "rgb": (30, 60, 220)},   # Blue -> pair 2
        ]
        back_specs = [
            {"cx": 320, "cy": 500, "w": 220, "h": 310, "angle": 8.0, "rgb": (220, 30, 30)},    # Red
            {"cx": 860, "cy": 500, "w": 220, "h": 310, "angle": -10.0, "rgb": (30, 60, 220)},  # Blue
        ]
        f_path = self.root / "sheet_front.png"
        b_path = self.root / "sheet_back.png"
        _synthesize_flatbed_page(front_specs).save(f_path)
        _synthesize_flatbed_page(back_specs).save(b_path)

        staged = self.fs.stage_image_pair_for_review(
            f_path,
            b_path,
            output_dir=self.output_dir,
            batch_name="TestBatch",
            stem_name="Sheet01",
            staging_dir=self.staging_dir,
            profile_path=self.profile_path,
        )
        self.assertIsNotNone(staged)
        self.assertEqual(staged["status"], "PENDING_REVIEW")

        pending = self.fs.list_pending_splitter_reviews(staging_dir=self.staging_dir)
        self.assertEqual(len(pending), 1)

        # Swap pair_id on the two back boxes (1 <-> 2)
        f_boxes = list(staged["proposed_front_boxes"])
        b_boxes = list(staged["proposed_back_boxes"])
        self.assertEqual(len(f_boxes), 2)
        self.assertEqual(len(b_boxes), 2)
        b_boxes[0]["pair_id"], b_boxes[1]["pair_id"] = b_boxes[1]["pair_id"], b_boxes[0]["pair_id"]

        res = self.fs.commit_staged_splitter_review(
            staged["stage_id"],
            front_boxes=f_boxes,
            back_boxes=b_boxes,
            staging_dir=self.staging_dir,
            profile_path=self.profile_path,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["createdCount"], 4)
        self.assertEqual(self.fs.list_pending_splitter_reviews(staging_dir=self.staging_dir), [])

        # Pair 1 Front should be Red, Pair 1 Back should now be Blue!
        p1_f = _dominant_rgb(Image.open(self.output_dir / "Sheet01_pair01_F.jpg"))
        p1_b = _dominant_rgb(Image.open(self.output_dir / "Sheet01_pair01_B.jpg"))
        p2_f = _dominant_rgb(Image.open(self.output_dir / "Sheet01_pair02_F.jpg"))
        p2_b = _dominant_rgb(Image.open(self.output_dir / "Sheet01_pair02_B.jpg"))

        self.assertGreater(p1_f[0], p1_f[2] + 60)  # Red front
        self.assertGreater(p1_b[2], p1_b[0] + 60)  # Blue back (swapped)
        self.assertGreater(p2_f[2], p2_f[0] + 60)  # Blue front
        self.assertGreater(p2_b[0], p2_b[2] + 60)  # Red back (swapped)

    def test_user_edits_update_learning_profile_and_influence_future_padding(self):
        """User box edits update EMA padding ratios and enlarge subsequent auto-detected boxes."""
        specs = [
            {"cx": 330, "cy": 500, "w": 220, "h": 310, "angle": 0.0, "rgb": (200, 50, 50)},
            {"cx": 850, "cy": 500, "w": 220, "h": 310, "angle": 0.0, "rgb": (50, 180, 70)},
        ]
        f_path = self.root / "learn_front.png"
        b_path = self.root / "learn_back.png"
        f_img = _synthesize_flatbed_page(specs)
        b_img = _synthesize_flatbed_page(specs)
        f_img.save(f_path)
        b_img.save(b_path)

        before_profile = self.fs.load_splitter_profile(self.profile_path)
        before_boxes = self.fs.detect_cards_on_page(f_img, profile=before_profile)
        before_avg_w = float(np.mean([b["width"] for b in before_boxes]))

        staged = self.fs.stage_image_pair_for_review(
            f_path,
            b_path,
            output_dir=self.output_dir,
            stem_name="LearnSheet",
            staging_dir=self.staging_dir,
            profile_path=self.profile_path,
        )
        # User expands boxes by +20% width/height and nudges angle
        edited_f = []
        for b in staged["proposed_front_boxes"]:
            nb = dict(b)
            nb["width"] = float(b["width"]) * 1.20
            nb["height"] = float(b["height"]) * 1.20
            nb["angle_deg"] = float(b["angle_deg"]) + 2.5
            edited_f.append(nb)

        edited_b = [dict(b) for b in staged["proposed_back_boxes"]]
        res = self.fs.commit_staged_splitter_review(
            staged["stage_id"],
            front_boxes=edited_f,
            back_boxes=edited_b,
            staging_dir=self.staging_dir,
            profile_path=self.profile_path,
        )
        learned = res["learningProfile"]
        self.assertGreater(learned["pad_ratio_x"], before_profile["pad_ratio_x"])
        self.assertGreater(learned["pad_ratio_y"], before_profile["pad_ratio_y"])
        self.assertGreaterEqual(learned["edit_stats"]["resized_boxes"], 2)
        self.assertGreaterEqual(learned["edit_stats"]["rotated_boxes"], 2)

        after_boxes = self.fs.detect_cards_on_page(f_img, profile=learned)
        after_avg_w = float(np.mean([b["width"] for b in after_boxes]))
        self.assertGreater(after_avg_w, before_avg_w + 5.0)

        # Also verify processed library bootstrapping against isolated temp samples
        lib_dir = self.root / "Processed_Library"
        lib_dir.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            sample = Image.new("RGB", (300, 420), (240, 240, 240))
            arr = np.array(sample)
            arr[25:395, 22:278] = (40, 90, 190)
            Image.fromarray(arr).save(lib_dir / f"sample_{i}_F.jpg")

        bootstrapped = self.fs.bootstrap_profile_from_library(
            profile_path=self.profile_path,
            library_dirs=[lib_dir],
            force=True,
        )
        self.assertEqual(bootstrapped["library_bootstrap"]["sampled_count"], 4)
        self.assertIsNotNone(bootstrapped["library_bootstrap"]["median_aspect_ratio"])

    def test_splitter_rest_endpoints_pending_and_commit(self):
        """Verify GET /api/splitter/pending and POST /api/splitter/commit via TabulasHubHandler."""
        import launch_tabulas_hub as hub

        specs = [
            {"cx": 320, "cy": 500, "w": 220, "h": 310, "angle": 0.0, "rgb": (200, 40, 40)},
            {"cx": 860, "cy": 500, "w": 220, "h": 310, "angle": 0.0, "rgb": (40, 160, 60)},
        ]
        f_path = self.root / "rest_f.png"
        b_path = self.root / "rest_b.png"
        _synthesize_flatbed_page(specs).save(f_path)
        _synthesize_flatbed_page(specs).save(b_path)

        staged = self.fs.stage_image_pair_for_review(
            f_path,
            b_path,
            output_dir=self.output_dir,
            batch_name="RestBatch",
            stem_name="RestSheet",
            staging_dir=self.staging_dir,
            profile_path=self.profile_path,
        )

        class _FakeHandler(hub._TabulasPythonApiAndReactHandler):
            def __init__(self):
                self.responses = []
                self.wfile = io.BytesIO()

            def _send_json(self, data, status: int = 200):
                self.responses.append((status, data))

        with mock.patch.object(self.fs, "SPLITTER_STAGING_DIR", self.staging_dir), \
             mock.patch.object(self.fs, "SPLITTER_LEARNING_PROFILE_FILE", self.profile_path), \
             mock.patch.object(hub, "_log_ui_action_to_file", lambda *_a, **_kw: None):
            h_get = _FakeHandler()
            h_get.path = "/api/splitter/pending?batch=RestBatch"
            h_get.do_GET()
            self.assertEqual(h_get.responses[0][0], 200)
            self.assertEqual(h_get.responses[0][1]["count"], 1)
            self.assertEqual(h_get.responses[0][1]["pending"][0]["stage_id"], staged["stage_id"])

            commit_body = json.dumps({
                "stageId": staged["stage_id"],
                "front_boxes": staged["proposed_front_boxes"],
                "back_boxes": staged["proposed_back_boxes"],
            }).encode("utf-8")
            h_post = _FakeHandler()
            h_post.path = "/api/splitter/commit"
            h_post.headers = {"Content-Length": str(len(commit_body))}
            h_post.rfile = io.BytesIO(commit_body)
            h_post.do_POST()
            self.assertEqual(h_post.responses[0][0], 200)
            self.assertTrue(h_post.responses[0][1]["success"])
            self.assertEqual(h_post.responses[0][1]["createdCount"], 4)
            self.assertEqual(h_post.responses[0][1]["pending"], [])

    def test_dark_noisy_mat_tight_grid_separates_all_cards(self):
        """Dark scanner mat with realistic grain/noise and tightly spaced cards must not fuse."""
        rng = np.random.default_rng(42)
        w, h = 1200, 1600
        canvas = np.full((h, w, 3), (34, 34, 34), dtype=np.int16)
        noise = rng.integers(-12, 13, size=(h, w, 3), dtype=np.int16)
        canvas = np.clip(canvas + noise, 0, 255).astype(np.uint8)

        specs = [
            {"cx": 270, "cy": 330, "w": 220, "h": 310, "angle": -1.5, "rgb": (210, 210, 210)},
            {"cx": 540, "cy": 330, "w": 220, "h": 310, "angle": 0.5, "rgb": (200, 70, 70)},
            {"cx": 810, "cy": 330, "w": 220, "h": 310, "angle": 1.0, "rgb": (60, 150, 210)},
            {"cx": 270, "cy": 720, "w": 220, "h": 310, "angle": 0.0, "rgb": (220, 190, 80)},
            {"cx": 540, "cy": 720, "w": 220, "h": 310, "angle": -0.8, "rgb": (80, 185, 110)},
            {"cx": 810, "cy": 720, "w": 220, "h": 310, "angle": 1.2, "rgb": (195, 195, 205)},
        ]
        for sp in specs:
            _draw_rotated_card(
                canvas,
                cx=sp["cx"],
                cy=sp["cy"],
                w=sp["w"],
                h=sp["h"],
                angle_deg=sp["angle"],
                fill_rgb=sp["rgb"],
                border_rgb=(230, 230, 230),
            )

        profile = self.fs.load_splitter_profile(self.profile_path)
        boxes = self.fs.detect_cards_on_page(Image.fromarray(canvas, mode="RGB"), profile=profile)
        self.assertEqual(len(boxes), 6, f"Expected 6 cards on noisy dark mat, got {len(boxes)}: {boxes}")

    def test_white_lid_with_thin_dark_outer_bezel_detects_all_cards(self):
        """White flatbed lid framed by a thin black outer scanner bezel must not return 0 boxes."""
        w, h = 1200, 1600
        canvas = np.full((h, w, 3), (244, 244, 244), dtype=np.uint8)
        # Thin 2.5% black scanner bezel around all 4 edges
        bx, by = int(w * 0.025), int(h * 0.025)
        canvas[:by, :] = (28, 28, 28)
        canvas[-by:, :] = (28, 28, 28)
        canvas[:, :bx] = (28, 28, 28)
        canvas[:, -bx:] = (28, 28, 28)

        specs = [
            {"cx": 330, "cy": 420, "w": 220, "h": 310, "angle": -6.0, "rgb": (200, 50, 50)},
            {"cx": 840, "cy": 450, "w": 220, "h": 310, "angle": 8.0, "rgb": (45, 130, 210)},
            {"cx": 560, "cy": 1100, "w": 310, "h": 220, "angle": -4.0, "rgb": (60, 175, 85)},
        ]
        for sp in specs:
            _draw_rotated_card(
                canvas,
                cx=sp["cx"],
                cy=sp["cy"],
                w=sp["w"],
                h=sp["h"],
                angle_deg=sp["angle"],
                fill_rgb=sp["rgb"],
            )

        profile = self.fs.load_splitter_profile(self.profile_path)
        boxes = self.fs.detect_cards_on_page(Image.fromarray(canvas, mode="RGB"), profile=profile)
        self.assertEqual(len(boxes), 3, f"Expected 3 cards inside white lid + black bezel, got {len(boxes)}: {boxes}")

    def test_tight_grid_boxes_never_overlap_and_deduplicate_high_iou(self):
        """Tightly spaced 3x3 grid & rotated grid must have zero inter-box overlap and deduplicate high-IoU boxes."""
        # Direct unit check for _is_duplicate_box on high-IoU / nested detections
        base = {"cx": 300.0, "cy": 400.0, "width": 230.0, "height": 320.0, "raw_width": 200.0, "raw_height": 280.0, "angle_deg": 2.0}
        near_dup = {"cx": 315.0, "cy": 410.0, "width": 225.0, "height": 315.0, "raw_width": 195.0, "raw_height": 275.0, "angle_deg": 2.5}
        nested_dup = {"cx": 305.0, "cy": 405.0, "width": 180.0, "height": 240.0, "raw_width": 160.0, "raw_height": 210.0, "angle_deg": 1.0}
        neighbor = {"cx": 560.0, "cy": 400.0, "width": 230.0, "height": 320.0, "raw_width": 200.0, "raw_height": 280.0, "angle_deg": 0.0}
        self.assertTrue(self.fs._is_duplicate_box(base, near_dup))
        self.assertTrue(self.fs._is_duplicate_box(base, nested_dup))
        self.assertFalse(self.fs._is_duplicate_box(base, neighbor))

        profile = self.fs.load_splitter_profile(self.profile_path)
        # Tight 3x3 axis-aligned grid where naive 7.5%/6.5% padding would overlap
        tight_specs = []
        colors = [
            (200, 50, 50), (50, 175, 70), (50, 90, 210),
            (215, 160, 40), (170, 55, 195), (45, 175, 185),
            (210, 95, 50), (120, 185, 55), (90, 110, 215),
        ]
        idx = 0
        for row in range(3):
            for col in range(3):
                tight_specs.append({
                    "cx": 260 + col * 245,
                    "cy": 280 + row * 335,
                    "w": 225,
                    "h": 310,
                    "angle": 0.0 if (row + col) % 2 == 0 else 1.5,
                    "rgb": colors[idx],
                })
                idx += 1

        page_img = _synthesize_flatbed_page(tight_specs, page_size=(1020, 1260))
        boxes = self.fs.detect_cards_on_page(page_img, profile=profile)
        self.assertEqual(len(boxes), 9, f"Expected 9 cards on tight 3x3 grid, got {len(boxes)}")
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                oa = self.fs.compute_rotated_box_overlap_area(boxes[i], boxes[j], use_raw=False)
                self.assertEqual(oa, 0.0, f"Boxes {i + 1} and {j + 1} overlapped by {oa} px^2")

    def test_expand_flatbed_pdfs_splits_all_sheet_pairs_in_multipage_pdf(self):
        """Multi-sheet flatbed PDF (6 pages = 3 sheet pairs) must split ALL pairs, not just pages 0-1."""
        import fitz
        import Core.vision_grader as vg

        batch_dir = self.root / "MultiSheetBatch"
        batch_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = batch_dir / "multi_sheet_scan.pdf"

        sheet_layouts = [
            [  # Sheet 1 (p0-1): 3 cards
                {"cx": 280, "cy": 380, "w": 210, "h": 295, "angle": 0.0, "rgb": (200, 45, 45)},
                {"cx": 600, "cy": 380, "w": 210, "h": 295, "angle": 0.0, "rgb": (45, 170, 65)},
                {"cx": 920, "cy": 380, "w": 210, "h": 295, "angle": 0.0, "rgb": (45, 85, 210)},
            ],
            [  # Sheet 2 (p2-3): 4 cards
                {"cx": 300, "cy": 360, "w": 210, "h": 295, "angle": 0.0, "rgb": (210, 150, 35)},
                {"cx": 860, "cy": 360, "w": 210, "h": 295, "angle": 0.0, "rgb": (165, 50, 190)},
                {"cx": 300, "cy": 1080, "w": 210, "h": 295, "angle": 0.0, "rgb": (40, 175, 185)},
                {"cx": 860, "cy": 1080, "w": 210, "h": 295, "angle": 0.0, "rgb": (210, 95, 50)},
            ],
            [  # Sheet 3 (p4-5): 2 cards
                {"cx": 330, "cy": 600, "w": 210, "h": 295, "angle": 0.0, "rgb": (110, 180, 50)},
                {"cx": 850, "cy": 600, "w": 210, "h": 295, "angle": 0.0, "rgb": (95, 95, 215)},
            ],
        ]

        doc = fitz.open()
        for specs in sheet_layouts:
            for _side in range(2):
                im = _synthesize_flatbed_page(specs, page_size=(1200, 1500))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=92)
                w_pt, h_pt = 612.0, 792.0  # US Letter (> 420pt flatbed threshold)
                page = doc.new_page(width=w_pt, height=h_pt)
                page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=buf.getvalue())
        doc.save(str(pdf_path))
        doc.close()

        with mock.patch.dict(vg.RUNTIME_CONFIG, {"scanner_dpi": 150}), \
             mock.patch.object(self.fs, "SPLITTER_LEARNING_PROFILE_FILE", self.profile_path):
            final_pdfs, created_count = vg.expand_flatbed_pdfs_in_batch_folder(
                batch_dir,
                stage_for_review=False,
                profile_path=self.profile_path,
            )

        self.assertEqual(created_count, 9)
        self.assertEqual(len(final_pdfs), 9)
        self.assertTrue((batch_dir / "Archive_Flatbed_Sheets" / "multi_sheet_scan.pdf").exists())
        expected_names = [
            "multi_sheet_scan_s01_FBCard01.pdf",
            "multi_sheet_scan_s01_FBCard02.pdf",
            "multi_sheet_scan_s01_FBCard03.pdf",
            "multi_sheet_scan_s02_FBCard01.pdf",
            "multi_sheet_scan_s02_FBCard02.pdf",
            "multi_sheet_scan_s02_FBCard03.pdf",
            "multi_sheet_scan_s02_FBCard04.pdf",
            "multi_sheet_scan_s03_FBCard01.pdf",
            "multi_sheet_scan_s03_FBCard02.pdf",
        ]
        for name in expected_names:
            out_p = batch_dir / name
            self.assertTrue(out_p.exists(), f"Missing split output {name}")
            d = fitz.open(str(out_p))
            self.assertEqual(len(d), 2)
            d.close()

    def test_fixture_multicard_pdf_all_sheets_and_zero_overlaps(self):
        """Verify real multi-sheet fixture PDF has zero overlapping boxes on all 8 pages and splits all 4 sheet pairs."""
        import shutil
        import fitz
        import Core.vision_grader as vg

        fixture_pdf = REPO_ROOT / "tests" / "fixtures" / "multicard_pdfs" / "Combined Test Batch (Scanned 061826).pdf"
        if not fixture_pdf.exists():
            self.skipTest("Fixture multi-card PDF not present")

        # Check zero overlaps on all 8 pages
        profile = self.fs.load_splitter_profile(self.profile_path)
        doc = fitz.open(str(fixture_pdf))
        self.assertEqual(len(doc), 8)
        expected_counts = [9, 9, 6, 6, 6, 6, 6, 6]
        for page_idx in range(len(doc)):
            pix = doc[page_idx].get_pixmap(matrix=fitz.Matrix(200.0 / 72.0, 200.0 / 72.0), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            boxes = self.fs.detect_cards_on_page(img, profile=profile)
            self.assertEqual(len(boxes), expected_counts[page_idx], f"Page {page_idx} box count mismatch")
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    oa = self.fs.compute_rotated_box_overlap_area(boxes[i], boxes[j], use_raw=False)
                    self.assertEqual(oa, 0.0, f"Page {page_idx} boxes {i + 1} & {j + 1} overlap by {oa}")
        doc.close()

        # Copy fixture to isolated temp dir and verify full 4-sheet immediate split (9 + 6 + 6 + 6 = 27 cards)
        batch_dir = self.root / "FixtureBatch"
        batch_dir.mkdir(parents=True, exist_ok=True)
        temp_pdf = batch_dir / fixture_pdf.name
        shutil.copy2(fixture_pdf, temp_pdf)

        with mock.patch.dict(vg.RUNTIME_CONFIG, {"scanner_dpi": 150}), \
             mock.patch.object(self.fs, "SPLITTER_LEARNING_PROFILE_FILE", self.profile_path):
            final_pdfs, created_count = vg.expand_flatbed_pdfs_in_batch_folder(
                batch_dir,
                stage_for_review=False,
                profile_path=self.profile_path,
            )

        self.assertEqual(created_count, 27)
        self.assertEqual(len(final_pdfs), 27)
        self.assertTrue((batch_dir / "Archive_Flatbed_Sheets" / fixture_pdf.name).exists())


if __name__ == "__main__":
    unittest.main()
