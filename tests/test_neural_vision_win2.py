import os
import pickle
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import Core.compute_backend as cb
import Core.neural_vision as nv


def _make_synthetic_card(
    variant: str = "base",
    player_seed: int = 1,
    size: tuple[int, int] = (200, 280),
) -> np.ndarray:
    """
    Generates deterministic synthetic card crops for testing Base vs. Parallel vs. Variation separation:
      - `base`: matte white border + player artwork
      - `gold`: metallic gold border + same player artwork
      - `purple_holo`: purple border + sparkle dots + same player artwork
      - `rainbow_refractor`: silver/prismatic border with rainbow gradient + same player artwork
      - `black`: black border + same player artwork
      - `variation`: matte white border + DIFFERENT player pose/artwork
    """
    w, h = size
    rng = np.random.default_rng(1000 + player_seed * 37)
    img = np.full((h, w, 3), 240, dtype=np.uint8)

    # Border styling (outer 12% perimeter)
    bw = max(12, int(w * 0.11))
    bh = max(14, int(h * 0.10))
    if variant == "gold":
        img[:, :] = (205, 170, 55)
    elif variant == "purple_holo":
        img[:, :] = (135, 55, 175)
        for _ in range(90):
            ry = int(rng.integers(0, h))
            rx = int(rng.integers(0, w))
            img[max(0, ry - 1) : ry + 2, max(0, rx - 1) : rx + 2] = (245, 220, 255)
    elif variant == "rainbow_refractor":
        xs = np.linspace(0, 179, w, dtype=np.uint8)
        ys = np.linspace(0, 60, h, dtype=np.uint8)[:, None]
        hsv_bg = np.zeros((h, w, 3), dtype=np.uint8)
        hsv_bg[:, :, 0] = (xs[None, :] + ys) % 180
        hsv_bg[:, :, 1] = 165
        hsv_bg[:, :, 2] = 225
        img = cv2.cvtColor(hsv_bg, cv2.COLOR_HSV2RGB)
    elif variant == "black":
        img[:, :] = (24, 24, 28)
    else:
        # Base or Variation: clean matte off-white border
        img[:, :] = (238, 238, 236)

    # Inner player photo box
    ix1, iy1, ix2, iy2 = bw, bh, w - bw, h - bh
    img[iy1:iy2, ix1:ix2] = (45, 85, 130)

    if variant == "variation":
        # Distinct subject pose & colors inside identical white border
        cv2.rectangle(img, (ix1 + 20, iy1 + 30), (ix2 - 20, iy2 - 30), (190, 75, 45), -1)
        cv2.circle(img, (w // 2, h // 2 - 20), 28, (235, 210, 170), -1)
        cv2.line(img, (ix1 + 10, iy2 - 15), (ix2 - 10, iy1 + 20), (250, 240, 90), 5)
    else:
        # Standard player silhouette
        cv2.circle(img, (w // 2, iy1 + (iy2 - iy1) // 3), 26, (220, 185, 150), -1)
        cv2.ellipse(img, (w // 2, iy1 + 2 * (iy2 - iy1) // 3), (34, 48), 0, 0, 360, (215, 215, 225), -1)
        cv2.putText(img, f"P{player_seed}", (ix1 + 12, iy2 - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Corner logo zone (top-right)
    cv2.rectangle(img, (w - bw - 24, bh + 4), (w - bw - 4, bh + 22), (220, 40, 40), -1)
    return img


def _spatial_token_encoder_from_rgb(crop_rgb: np.ndarray) -> np.ndarray:
    """
    Deterministic 16x16 spatial token simulator `(257, 384)` that reflects actual border,
    corner, and center RGB/texture content so multi-region tests exercise real spatial math.
    """
    small = cv2.resize(crop_rgb, (224, 224), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    tokens = np.zeros((257, 384), dtype=np.float32)
    # 16x16 grid of 14x14 patches
    patch_vecs = []
    for r in range(16):
        for c in range(16):
            p = small[r * 14 : (r + 1) * 14, c * 14 : (c + 1) * 14]
            mean_rgb = p.mean(axis=(0, 1))
            std_rgb = p.std(axis=(0, 1))
            v = np.zeros(384, dtype=np.float32)
            v[0:3] = mean_rgb * 4.0
            v[3:6] = std_rgb * 6.0
            # Encode spatial position + color hash into remaining dims
            for ch in range(3):
                v[10 + ch * 32 : 10 + (ch + 1) * 32] = np.sin(np.arange(32) * (mean_rgb[ch] + 0.15) * 3.1)
            patch_vecs.append(v)
    patches = np.stack(patch_vecs, axis=0)
    tokens[1:, :] = patches
    tokens[0, :] = patches.mean(axis=0)
    return tokens


class TestNeuralVisionWin2(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.cache_file = self.tmp_dir / "neural_embeddings_v1.pkl"
        self.rev_dir = self.tmp_dir / "_My_Collection"
        self.ref_dir = self.tmp_dir / "Reference_Library"
        self.cfg_file = self.tmp_dir / "compute_settings.json"
        self.rev_dir.mkdir(parents=True, exist_ok=True)
        self.ref_dir.mkdir(parents=True, exist_ok=True)

        self._patches = [
            mock.patch.object(nv, "NEURAL_EMBEDDINGS_CACHE_FILE", self.cache_file),
            mock.patch.object(nv, "REVIEWED_CARDS_DIR", self.rev_dir),
            mock.patch.object(nv, "REFERENCE_TEMPLATES_DIR", self.ref_dir),
            mock.patch.object(cb, "COMPUTE_SETTINGS_FILE", self.cfg_file),
        ]
        for p in self._patches:
            p.start()
        nv.reset_neural_engine_cache()

    def tearDown(self):
        nv.reset_neural_engine_cache()
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def test_1_multiregion_patch_token_math_and_2d_fallback(self):
        rng = np.random.default_rng(42)
        raw_3d = rng.normal(size=(4, 257, 384)).astype(np.float32)
        mr = nv._extract_multiregion_patch_vectors(raw_3d)
        for k in ("vec", "border_vec", "corner_vec", "center_vec"):
            arr = mr[k]
            self.assertIsNotNone(arr)
            self.assertEqual(arr.shape, (4, 384))
            norms = np.linalg.norm(arr, axis=1)
            np.testing.assert_allclose(norms, 1.0, atol=1e-5)

        # 2D pooled ONNX backbone fallback (e.g., MobileNetV3 / CLIP pooled)
        raw_2d = rng.normal(size=(3, 512)).astype(np.float32)
        mr2 = nv._extract_multiregion_patch_vectors(raw_2d)
        self.assertEqual(mr2["vec"].shape, (3, 512))
        np.testing.assert_allclose(np.linalg.norm(mr2["vec"], axis=1), 1.0, atol=1e-5)
        self.assertIsNone(mr2["border_vec"])
        self.assertIsNone(mr2["corner_vec"])
        self.assertIsNone(mr2["center_vec"])

    def test_2_per_block_normalization_color_foil_descriptor(self):
        gold_card = _make_synthetic_card("gold", player_seed=1)
        purple_card = _make_synthetic_card("purple_holo", player_seed=1)
        base_card = _make_synthetic_card("base", player_seed=1)

        d_gold = nv.extract_color_foil_descriptor(gold_card)
        d_purple = nv.extract_color_foil_descriptor(purple_card)
        d_base = nv.extract_color_foil_descriptor(base_card)

        self.assertEqual(d_gold.shape, (168,))
        self.assertAlmostEqual(float(np.linalg.norm(d_gold)), 1.0, places=5)

        # Verify border-color block (first 112 dims) dominates when color differs strongly
        sim_gold_self = float(np.dot(d_gold, d_gold))
        sim_gold_base = float(np.dot(d_gold, d_base))
        sim_gold_purple = float(np.dot(d_gold, d_purple))
        self.assertGreater(sim_gold_self - sim_gold_base, 0.15)
        self.assertGreater(sim_gold_self - sim_gold_purple, 0.15)

    def test_3_static_batch_axis_one_guard(self):
        class _FakeInput:
            def __init__(self, shape):
                self.name = "pixel_values"
                self.shape = shape

        class _FakeOutput:
            def __init__(self):
                self.name = "last_hidden_state"

        seen_batches = []

        class _FakeSession:
            def get_inputs(self):
                return [_FakeInput([1, 3, 224, 224])]

            def get_outputs(self):
                return [_FakeOutput()]

            def run(self, out_names, feed):
                x = next(iter(feed.values()))
                seen_batches.append(x.shape[0])
                return [np.ones((x.shape[0], 257, 384), dtype=np.float32)]

        dummy_model = self.tmp_dir / "dinov2_vits14.onnx"
        dummy_model.write_bytes(b"0" * 2_000_000)

        with mock.patch.object(nv, "create_onnx_session", return_value=(_FakeSession(), "DmlExecutionProvider [Fake]")):
            eng = nv.NeuralEmbeddingEngine(model_path=dummy_model, prefer_gpu=True, claim_slot=False)
            self.assertTrue(eng.ensure_loaded())
            self.assertTrue(eng._static_batch_one)
            self.assertEqual(eng._effective_max_batch, 1)

            crops = [_make_synthetic_card("base", player_seed=i) for i in range(5)]
            descs = eng.extract_descriptors_batch(crops, batch_size=32)
            self.assertEqual(len(descs), 5)
            self.assertTrue(all(d is not None for d in descs))
            # Never attempted B > 1 -> zero wasted OOM/exception loops
            self.assertEqual(seen_batches, [1, 1, 1, 1, 1])

    def test_4_microbatch_bucket_padding_and_vram_backoff_to_cpu(self):
        class _FakeInput:
            def __init__(self):
                self.name = "pixel_values"
                self.shape = ["batch", 3, 224, 224]

        class _FakeOutput:
            def __init__(self):
                self.name = "last_hidden_state"

        gpu_attempts = []

        class _OomGpuSession:
            def get_inputs(self):
                return [_FakeInput()]

            def get_outputs(self):
                return [_FakeOutput()]

            def run(self, out_names, feed):
                bs = next(iter(feed.values())).shape[0]
                gpu_attempts.append(bs)
                if bs >= 8:
                    raise RuntimeError("DirectML D3D12 OOM")
                # Also fail bs == 1 on second chunk to trigger CPU fallback!
                if len(gpu_attempts) >= 4:
                    raise RuntimeError("DirectML device removed")
                return [np.ones((bs, 257, 384), dtype=np.float32)]

        cpu_batches = []

        class _CpuSession:
            def get_inputs(self):
                return [_FakeInput()]

            def get_outputs(self):
                return [_FakeOutput()]

            def run(self, out_names, feed):
                bs = next(iter(feed.values())).shape[0]
                cpu_batches.append(bs)
                return [np.ones((bs, 257, 384), dtype=np.float32)]

        dummy_model = self.tmp_dir / "dinov2_vits14.onnx"
        dummy_model.write_bytes(b"0" * 2_000_000)

        def _fake_create(path, prefer_gpu=True, purpose="neural", claim_slot=True):
            if prefer_gpu:
                return _OomGpuSession(), "DmlExecutionProvider [DXGI #0: RX 9070 XT]"
            return _CpuSession(), "CPUExecutionProvider"

        with mock.patch.object(nv, "create_onnx_session", side_effect=_fake_create):
            eng = nv.NeuralEmbeddingEngine(model_path=dummy_model, prefer_gpu=True, claim_slot=False)
            crops = [_make_synthetic_card("base", player_seed=i) for i in range(10)]
            descs = eng.extract_descriptors_batch(crops, batch_size=32)

        self.assertEqual(len(descs), 10)
        self.assertTrue(all(d is not None for d in descs))
        self.assertEqual(eng.active_provider, "CPUExecutionProvider")
        # 10 crops with batch_size=32 pads to bucket 16, then backs off 16 -> 8 -> 4 -> 2 -> 1 -> CPU
        self.assertIn(16, gpu_attempts)
        self.assertIn(8, gpu_attempts)
        self.assertIn(4, gpu_attempts)
        self.assertGreater(len(cpu_batches), 0)

    def test_5_legacy_v24_cache_compat_thread_safety_and_flush_cadence(self):
        # Write a legacy v24 pickle
        img_p = self.ref_dir / "2026_Topps_Baseball" / "2026_Topps_Baseball_Base_#1_Player1_F.jpg"
        img_p.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(_make_synthetic_card("base", player_seed=1)).save(img_p)
        mt = img_p.stat().st_mtime
        k = nv._norm_path_key(img_p)

        legacy_vec = np.ones(384, dtype=np.float16) / np.float16(np.sqrt(384.0))
        with open(self.cache_file, "wb") as f:
            pickle.dump({
                "schema": "v24_dinov2_fp16",
                "model": "dinov2_vits14.onnx",
                "embeddings": {
                    k: {
                        "path": str(img_p),
                        "mtime": mt,
                        "set_key": nv.canonical_set_key("2026 Topps Baseball"),
                        "subset": "Base",
                        "n_cnum": "1",
                        "side": "F",
                        "source": "Reference_Library",
                        "vec": legacy_vec,
                    }
                },
            }, f)

        loaded = nv.load_neural_embeddings_cache(force_reload=True)
        self.assertEqual(loaded["schema"], "v24_dinov2_fp16")
        self.assertIn(k, loaded["embeddings"])

        # Concurrent search + cache reads under _INDEX_LOCK
        errors = []

        def _worker():
            try:
                for _ in range(25):
                    hits = nv.search_set_neural_embeddings(np.asarray(legacy_vec, dtype=np.float32), "2026 Topps Baseball")
                    self.assertEqual(len(hits), 1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

        # Large-cache flush cadence: 40 dirty entries must NOT trigger disk flush yet; flush_neural_embeddings_if_dirty() does
        with mock.patch.object(nv, "save_neural_embeddings_cache", wraps=nv.save_neural_embeddings_cache) as spy_save:
            nv._MEM_EMBED_DIRTY_COUNT = 40
            nv._MEM_EMBED_LAST_FLUSH_TS = time.monotonic()
            nv._maybe_flush_lazy_cache(loaded)
            self.assertEqual(spy_save.call_count, 0)
            nv.flush_neural_embeddings_if_dirty()
            self.assertEqual(spy_save.call_count, 1)

        reloaded = nv.load_neural_embeddings_cache(force_reload=True)
        self.assertEqual(reloaded["schema"], nv.NEURAL_CACHE_SCHEMA_V25)

    def test_6_vectorized_retrieval_parity_and_speed(self):
        rng = np.random.default_rng(7)
        n_refs = 5000
        mat = nv._l2_normalize_rows(rng.normal(size=(n_refs, 384)).astype(np.float32))
        q = nv._l2_normalize_rows(rng.normal(size=(384,)).astype(np.float32))

        t0 = time.perf_counter()
        vec_hits = nv.batch_cosine_search(q, mat, top_k=10)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Brute-force reference
        brute_scores = [float(np.dot(mat[i], q)) for i in range(n_refs)]
        brute_top = sorted(range(n_refs), key=lambda i: brute_scores[i], reverse=True)[:10]
        self.assertEqual([i for i, _ in vec_hits], brute_top)
        for idx, sc in vec_hits:
            self.assertAlmostEqual(sc, brute_scores[idx], delta=1e-5)
        self.assertLess(elapsed_ms, 50.0)

    def test_7_synthetic_base_vs_parallel_and_variation_separation(self):
        variants = ("base", "gold", "purple_holo", "rainbow_refractor", "black", "variation")
        descs_p1 = {}
        descs_p2 = {}
        for v in variants:
            img1 = _make_synthetic_card(v, player_seed=1)
            tok1 = _spatial_token_encoder_from_rgb(img1)[None, ...]
            mr1 = nv._extract_multiregion_patch_vectors(tok1)
            descs_p1[v] = {
                "vec": mr1["vec"][0],
                "border_vec": mr1["border_vec"][0],
                "corner_vec": mr1["corner_vec"][0],
                "center_vec": mr1["center_vec"][0],
                "color_foil_vec": nv.extract_color_foil_descriptor(img1),
            }
            # Different player (#2) in the same parallel (for exemplar-level separation)
            img2 = _make_synthetic_card(v, player_seed=2)
            tok2 = _spatial_token_encoder_from_rgb(img2)[None, ...]
            mr2 = nv._extract_multiregion_patch_vectors(tok2)
            descs_p2[v] = {
                "vec": mr2["vec"][0],
                "border_vec": mr2["border_vec"][0],
                "corner_vec": mr2["corner_vec"][0],
                "center_vec": mr2["center_vec"][0],
                "color_foil_vec": nv.extract_color_foil_descriptor(img2),
            }

        # 1) Parallel separation across different players (e.g. Rainbow Refractor P1 vs P2 exemplars)
        for target_v in ("base", "gold", "purple_holo", "rainbow_refractor", "black"):
            scored = []
            for cand_v in ("base", "gold", "purple_holo", "rainbow_refractor", "black"):
                res = nv.score_multiregion_parallel_pair(descs_p1[target_v], descs_p2[cand_v], mode="parallel")
                scored.append((res["score"], cand_v))
            scored.sort(reverse=True)
            self.assertEqual(scored[0][1], target_v, f"Expected {target_v} to rank #1, got {scored}")
            margin = scored[0][0] - scored[1][0]
            self.assertGreater(margin, 0.03, f"Expected clear margin for {target_v}, got {scored}")

        # 2) Image/SP Variation separation vs Base (same white border, different center photo)
        var_vs_var = nv.score_multiregion_parallel_pair(descs_p1["variation"], descs_p1["variation"], mode="variation")["score"]
        var_vs_base = nv.score_multiregion_parallel_pair(descs_p1["variation"], descs_p1["base"], mode="variation")["score"]
        self.assertGreater(var_vs_var - var_vs_base, 0.15)


if __name__ == "__main__":
    unittest.main()
