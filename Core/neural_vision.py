from __future__ import annotations
# ==============================================================================
# Core/neural_vision.py - GPU WIN #2 (DINOV2-SMALL DEEP VISUAL EMBEDDINGS)
#                         & WIN #4 (LOCAL OFFLINE DEFECT AI FOUNDATION)
#   - 1-Click Verified Hugging Face ONNX Downloader (dinov2_vits14.onnx, ~88 MB)
#   - Batched DirectML / CUDA / CPU Vision Transformer Embedding Extractor
#   - Incremental Float16 Persistent Index (Reference_Library + _My_Collection)
#   - Sub-2ms Vectorized Set-Wide Cosine Search for Tier-4 Visual Recovery
#   - 100% Optional & Safe Fallback (Classical pipeline runs cleanly if absent)
# ==============================================================================
import os
import pickle
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image

__version__ = "0.25.0-beta.2"
__last_updated__ = "2026-11-21 22:40:00"

from Core.compute_backend import (
    create_onnx_session,
    get_recommended_neural_batch_size,
    load_compute_settings,
    release_gpu_worker_slot,
)
from Core.config import (
    NEURAL_EMBEDDINGS_CACHE_FILE,
    NEURAL_MODELS_DIR,
    REFERENCE_TEMPLATES_DIR,
    REVIEWED_CARDS_DIR,
    atomic_write_bytes,
    canonical_set_key,
    ensure_directories,
    norm,
    parse_unified_card_filename,
)

DINOV2_MODEL_FILENAME = "dinov2_vits14.onnx"
DINOV2_DOWNLOAD_MIRRORS = [
    "https://huggingface.co/Xenova/dinov2-small/resolve/main/onnx/model.onnx",
    "https://huggingface.co/onnx-community/dinov2-small-ONNX/resolve/main/onnx/model.onnx",
    "https://huggingface.co/onnx-community/dinov2-small/resolve/main/onnx/model.onnx",
]

RECOMMENDED_ONNX_MODELS = [
    {
        "key": "dinov2_small",
        "filename": DINOV2_MODEL_FILENAME,
        "role": "Win #2: DINOv2-small Semantic Visual Embeddings (384-d — Variations, Soft TCDB Scans & Tier-4 Search)",
        "input_size": (224, 224),
        "embedding_dim": 384,
    },
    {
        "key": "clip_vit_b32",
        "filename": "clip_vit_b32_visual.onnx",
        "role": "Win #2: Visual-Semantic Embeddings (512-d — Optional Alternate Backbone)",
        "input_size": (224, 224),
        "embedding_dim": 512,
    },
    {
        "key": "mobilenetv3_embed",
        "filename": "mobilenetv3_large.onnx",
        "role": "Win #2: Lightweight Fast Embeddings (Optional CPU-Friendly Backbone)",
        "input_size": (224, 224),
        "embedding_dim": 960,
    },
    {
        "key": "card_defect_detector",
        "filename": "card_defect_v1.onnx",
        "role": "Win #4: Local Offline Pre-Grading Defect AI (Scratches, Print Lines, Whitening)",
        "input_size": (512, 512),
        "embedding_dim": 0,
    },
]

NEURAL_CACHE_SCHEMA_V24 = "v24_dinov2_fp16"
NEURAL_CACHE_SCHEMA_V25 = "v25_dinov2_multiregion_fp16"

_LAZY_FLUSH_DIRTY_THRESHOLD = 1500
_LAZY_FLUSH_INTERVAL_SEC = 60.0
_INDEX_CHECKPOINT_INTERVAL_ITEMS = 1500
_INDEX_CHECKPOINT_INTERVAL_SEC = 60.0

_DML_BATCH_BUCKETS = (1, 4, 8, 16, 32, 64)

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

# Precomputed 16x16 spatial patch masks for DINOv2-small (256 patch tokens)
_GRID_R, _GRID_C = np.meshgrid(np.arange(16), np.arange(16), indexing="ij")
_PATCH_BORDER_MASK = ((_GRID_R <= 1) | (_GRID_R >= 14) | (_GRID_C <= 1) | (_GRID_C >= 14)).reshape(-1)
_PATCH_CORNER_MASK = (((_GRID_R <= 3) | (_GRID_R >= 12)) & ((_GRID_C <= 3) | (_GRID_C >= 12))).reshape(-1)
_PATCH_CENTER_MASK = ((_GRID_R >= 3) & (_GRID_R <= 12) & (_GRID_C >= 3) & (_GRID_C <= 12)).reshape(-1)

_ENGINE_LOCK = threading.Lock()
_INDEX_LOCK = threading.RLock()
_SINGLETON_ENGINE: Optional["NeuralEmbeddingEngine"] = None
_MEM_EMBED_CACHE: Optional[dict] = None
_MEM_EMBED_MTIME: float = -1.0
_MEM_EMBED_DIRTY_COUNT: int = 0
_MEM_EMBED_LAST_FLUSH_TS: float = 0.0
_SET_MATRIX_CACHE: dict[tuple[str, str], tuple[int, list[dict], np.ndarray]] = {}
_PAR_GROUP_MATRIX_CACHE: dict[tuple[str, ...], tuple[int, dict[str, np.ndarray]]] = {}


def _choose_dml_bucket(n: int, max_bs: int) -> int:
    """Rounds chunk size `n` up to a power-of-2 DirectML bucket <= `max_bs` to avoid shader recompilation."""
    for b in _DML_BATCH_BUCKETS:
        if b >= n and b <= max_bs:
            return b
    return min(max(1, n), max_bs)


def preprocess_card_tensor(crop_rgb: np.ndarray, input_size: tuple[int, int] = (224, 224)) -> np.ndarray:
    """Converts a single RGB card crop into an ImageNet-normalized NCHW float32 tensor `(1, 3, H, W)`."""
    resized = cv2.resize(crop_rgb, input_size, interpolation=cv2.INTER_AREA)
    arr = resized.astype(np.float32) * (1.0 / 255.0)
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    return (arr - _IMAGENET_MEAN) / _IMAGENET_STD


def preprocess_card_batch(crops_rgb: list[np.ndarray], input_size: tuple[int, int] = (224, 224)) -> np.ndarray:
    """Packs a list of RGB card crops into a contiguous `(B, 3, H, W)` float32 NCHW tensor for GPU batching."""
    batch_list = [cv2.resize(c, input_size, interpolation=cv2.INTER_AREA) for c in crops_rgb]
    arr = np.stack(batch_list, axis=0).astype(np.float32) * (1.0 / 255.0)
    arr = np.transpose(arr, (0, 3, 1, 2))
    return np.ascontiguousarray((arr - _IMAGENET_MEAN) / _IMAGENET_STD, dtype=np.float32)


def _pool_and_normalize_model_output(raw_out: np.ndarray) -> np.ndarray:
    """
    Converts raw DINOv2 / ViT / CNN ONNX output into L2-normalized `(B, D)` float32 vectors:
      - 3D `[B, tokens, D]` (e.g. DINOv2 `last_hidden_state` `[B, 257, 384]`):
        blends `0.60 * norm(CLS) + 0.40 * norm(patch_mean)` for superior card-pose + background retrieval!
      - 2D `[B, D]`: L2-normalizes directly.
    """
    arr = np.asarray(raw_out, dtype=np.float32)
    if arr.ndim == 3 and arr.shape[1] >= 2:
        cls_tok = arr[:, 0, :]
        patch_mean = arr[:, 1:, :].mean(axis=1)
        cls_norm = cls_tok / np.maximum(1e-6, np.linalg.norm(cls_tok, axis=1, keepdims=True))
        pm_norm = patch_mean / np.maximum(1e-6, np.linalg.norm(patch_mean, axis=1, keepdims=True))
        blended = 0.60 * cls_norm + 0.40 * pm_norm
        return blended / np.maximum(1e-6, np.linalg.norm(blended, axis=1, keepdims=True))
    if arr.ndim == 1:
        arr = arr[None, :]
    elif arr.ndim > 2:
        arr = arr.reshape(arr.shape[0], -1)
    return arr / np.maximum(1e-6, np.linalg.norm(arr, axis=1, keepdims=True))


def _l2_normalize_rows(mat: np.ndarray) -> np.ndarray:
    arr = np.asarray(mat, dtype=np.float32)
    if arr.ndim == 1:
        n = float(np.linalg.norm(arr))
        return (arr / n) if n > 1e-6 else arr
    norms = np.maximum(1e-6, np.linalg.norm(arr, axis=1, keepdims=True))
    return arr / norms


def _extract_multiregion_patch_vectors(raw_out: np.ndarray) -> dict[str, Optional[np.ndarray]]:
    """
    Extracts global + spatial multi-region embeddings from DINOv2 `[B, 257, D]` token output
    in zero extra forward passes:
      - `vec`:        `norm(0.60 * norm(CLS) + 0.40 * norm(patch_mean))`
      - `border_vec`: L2-normalized outer 2-ring border patches (112 tokens on 16x16)
      - `corner_vec`: L2-normalized four 4x4 corner/logo/stamp zones (64 tokens on 16x16)
      - `center_vec`: L2-normalized inner 10x10 subject core (100 tokens on 16x16)
    Gracefully returns `None` for spatial regions if the ONNX backbone only outputs 2D `[B, D]`.
    """
    arr = np.asarray(raw_out, dtype=np.float32)
    global_vecs = _pool_and_normalize_model_output(arr)
    if arr.ndim != 3 or arr.shape[1] < 6:
        return {"vec": global_vecs, "border_vec": None, "corner_vec": None, "center_vec": None}

    patches = arr[:, 1:, :]
    n_patches = patches.shape[1]
    if n_patches == 256:
        b_mask, c_mask, m_mask = _PATCH_BORDER_MASK, _PATCH_CORNER_MASK, _PATCH_CENTER_MASK
    else:
        side = int(round(np.sqrt(n_patches)))
        if side * side != n_patches or side < 4:
            return {"vec": global_vecs, "border_vec": None, "corner_vec": None, "center_vec": None}
        gr, gc = np.meshgrid(np.arange(side), np.arange(side), indexing="ij")
        bw = max(1, side // 8)
        cw = max(1, side // 4)
        b_mask = ((gr < bw) | (gr >= side - bw) | (gc < bw) | (gc >= side - bw)).reshape(-1)
        c_mask = (((gr < cw) | (gr >= side - cw)) & ((gc < cw) | (gc >= side - cw))).reshape(-1)
        m_mask = ((gr >= bw + 1) & (gr < side - bw - 1) & (gc >= bw + 1) & (gc < side - bw - 1)).reshape(-1)
        if not np.any(m_mask):
            m_mask = ~b_mask

    border_vec = _l2_normalize_rows(patches[:, b_mask, :].mean(axis=1))
    corner_vec = _l2_normalize_rows(patches[:, c_mask, :].mean(axis=1))
    center_vec = _l2_normalize_rows(patches[:, m_mask, :].mean(axis=1))
    return {
        "vec": global_vecs,
        "border_vec": border_vec,
        "corner_vec": corner_vec,
        "center_vec": center_vec,
    }


def compute_dinov2_patch_anomaly_map(patch_tokens: np.ndarray) -> Optional[np.ndarray]:
    """
    Computes a local 8-neighbor cosine distance anomaly map (float32 in [0, 1]) from
    L2-normalized DINOv2 spatial patch tokens `[N, D]` (e.g. `256 = 16x16`), highlighting
    localized structural breaks (creases, gouges, spots) with zero extra ONNX forward passes.
    """
    if patch_tokens is None:
        return None
    pts = np.asarray(patch_tokens, dtype=np.float32)
    if pts.ndim != 2 or pts.shape[0] < 16:
        return None
    side = int(round(np.sqrt(pts.shape[0])))
    if side * side != pts.shape[0]:
        return None
    norms = np.maximum(1e-6, np.linalg.norm(pts, axis=1, keepdims=True))
    grid = (pts / norms).reshape(side, side, pts.shape[1])
    anom = np.zeros((side, side), dtype=np.float32)
    for r in range(side):
        r0, r1 = max(0, r - 1), min(side, r + 2)
        for c in range(side):
            c0, c1 = max(0, c - 1), min(side, c + 2)
            nbrs = grid[r0:r1, c0:c1, :].reshape(-1, pts.shape[1])
            cos_vals = nbrs @ grid[r, c]
            # Exclude self-similarity (~1.0) when neighbors exist
            if len(cos_vals) > 1:
                mean_cos = float((np.sum(cos_vals) - 1.0) / float(len(cos_vals) - 1))
                anom[r, c] = float(np.clip(1.0 - mean_cos, 0.0, 1.0))
    return anom


def extract_color_foil_descriptor(crop_rgb: np.ndarray) -> np.ndarray:
    """
    Extracts an L2-normalized 168-d color, border, corner-chroma, and refractor/foil-specular
    descriptor with per-block L2 normalization before weighted concatenation so high-magnitude
    Laplacian sparkle values never drown out border color.
    """
    small_rgb = cv2.resize(crop_rgb, (160, 224), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2LAB)
    gray = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2GRAY)

    # Outer 12% perimeter border band
    mask_border = np.ones((224, 160), dtype=np.uint8)
    mask_border[26:198, 20:140] = 0
    border_bool = mask_border.astype(bool)

    # Sub-block 1: Border Color Histograms (36 + 20 + 16 + 20 + 20 = 112-d)
    h_hist = _l2_normalize_rows(cv2.calcHist([hsv], [0], mask_border, [36], [0, 180]).flatten())
    s_hist = _l2_normalize_rows(cv2.calcHist([hsv], [1], mask_border, [20], [0, 256]).flatten())
    v_hist = _l2_normalize_rows(cv2.calcHist([hsv], [2], mask_border, [16], [0, 256]).flatten())
    a_hist = _l2_normalize_rows(cv2.calcHist([lab], [1], mask_border, [20], [0, 256]).flatten())
    b_hist = _l2_normalize_rows(cv2.calcHist([lab], [2], mask_border, [20], [0, 256]).flatten())
    border_color_blk = _l2_normalize_rows(np.concatenate([
        h_hist * 1.45,
        s_hist * 1.25,
        v_hist * 0.85,
        a_hist * 1.35,
        b_hist * 1.35,
    ]))

    # Sub-block 2: Refractor / Holo Specular & Sparkle Energy (16 + 12 + 16 = 44-d)
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(sx, sy)
    lap_abs = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))

    grad_vals = np.clip(grad_mag[border_bool], 0.0, 255.0)
    lap_vals = np.clip(lap_abs[border_bool], 0.0, 255.0)
    g_hist_raw, _ = np.histogram(grad_vals, bins=16, range=(0.0, 255.0))
    l_hist_raw, _ = np.histogram(lap_vals, bins=12, range=(0.0, 255.0))
    g_hist = _l2_normalize_rows(g_hist_raw.astype(np.float32))
    l_hist = _l2_normalize_rows(l_hist_raw.astype(np.float32))

    # Hue Shannon entropy (distinguishes rainbow/prismatic refractors from single-hue/matte borders)
    def _norm_hue_entropy(h_vals: np.ndarray) -> float:
        hist_e, _ = np.histogram(h_vals, bins=18, range=(0, 180))
        tot = float(np.sum(hist_e))
        if tot <= 0.0:
            return 0.0
        p = hist_e.astype(np.float32) / tot
        p = p[p > 0.0]
        return float(-np.sum(p * np.log2(p)) / np.log2(18.0))

    h_ent_border = _norm_hue_entropy(hsv[:, :, 0][border_bool])
    h_ent_full = _norm_hue_entropy(hsv[:, :, 0].reshape(-1))

    # 4x4 spatial grid variance of S, a*, b* across the card (captures prismatic rainbow gradients)
    s_grid = hsv[:, :, 1].reshape(4, 56, 4, 40).mean(axis=(1, 3)).astype(np.float32) / 255.0
    a_grid = lab[:, :, 1].reshape(4, 56, 4, 40).mean(axis=(1, 3)).astype(np.float32) / 255.0
    b_grid = lab[:, :, 2].reshape(4, 56, 4, 40).mean(axis=(1, 3)).astype(np.float32) / 255.0

    s_b = hsv[:, :, 1][border_bool].astype(np.float32) / 255.0
    v_b = hsv[:, :, 2][border_bool].astype(np.float32) / 255.0
    spec_stats = _l2_normalize_rows(np.array([
        float(np.mean(s_b)),
        float(np.std(s_b)),
        float(np.percentile(s_b, 90)),
        float(np.mean(v_b)),
        float(np.std(v_b)),
        float(np.percentile(v_b, 90)),
        h_ent_border,
        h_ent_full,
        float(np.std(s_grid)),
        float(np.std(a_grid)),
        float(np.std(b_grid)),
        float(np.mean(grad_vals) / 255.0),
        float(np.std(grad_vals) / 255.0),
        float(np.percentile(grad_vals, 90) / 255.0),
        float(np.mean(lap_vals) / 255.0),
        float(np.percentile(lap_vals, 90) / 255.0),
    ], dtype=np.float32))
    foil_spec_blk = _l2_normalize_rows(np.concatenate([
        g_hist * 1.00,
        l_hist * 0.90,
        spec_stats * 1.15,
    ]))

    # Sub-block 3: 4 Corner/Logo Chroma Summary (4 x 3 = 12-d)
    corner_slices = (
        (slice(0, 56), slice(0, 40)),
        (slice(0, 56), slice(120, 160)),
        (slice(168, 224), slice(0, 40)),
        (slice(168, 224), slice(120, 160)),
    )
    c_feats: list[float] = []
    for ys, xs in corner_slices:
        c_feats.append(float(np.mean(lab[ys, xs, 1])) / 255.0)
        c_feats.append(float(np.mean(lab[ys, xs, 2])) / 255.0)
        c_feats.append(float(np.mean(hsv[ys, xs, 1])) / 255.0)
    corner_chroma_blk = _l2_normalize_rows(np.array(c_feats, dtype=np.float32))

    # Final concatenation & L2-normalization (112 + 44 + 12 = 168-d)
    return _l2_normalize_rows(np.concatenate([
        border_color_blk * 1.30,
        foil_spec_blk * 1.10,
        corner_chroma_blk * 0.85,
    ])).astype(np.float32)


def batch_cosine_search_matrix(
    query_mat: np.ndarray,
    ref_mat: np.ndarray,
    top_k: int = 10,
) -> list[list[tuple[int, float]]]:
    """
    Vectorized BLAS SGEMM cosine similarity search for 1D `(D,)` or 2D `(Q, D)` queries
    against L2-normalized `(N, D)` reference embeddings.
    """
    if query_mat is None or ref_mat is None or ref_mat.size == 0:
        return []
    q = np.asarray(query_mat, dtype=np.float32)
    single_q = (q.ndim == 1)
    if single_q:
        q = q.reshape(1, -1)
    q = _l2_normalize_rows(q)
    r = np.asarray(ref_mat, dtype=np.float32)
    scores_mat = q @ r.T
    k = min(max(1, int(top_k)), r.shape[0])
    out: list[list[tuple[int, float]]] = []
    for row_s in scores_mat:
        top_idx = np.argpartition(row_s, -k)[-k:]
        top_sorted = top_idx[np.argsort(row_s[top_idx])[::-1]]
        out.append([(int(i), round(float(row_s[i]), 5)) for i in top_sorted])
    return out


def batch_cosine_search(query_vec: np.ndarray, matrix_vecs: np.ndarray, top_k: int = 10) -> list[tuple[int, float]]:
    """Vectorized cosine similarity search across `N` L2-normalized reference embeddings (< 2 ms)."""
    if query_vec is None or matrix_vecs is None or matrix_vecs.size == 0:
        return []
    res = batch_cosine_search_matrix(query_vec, matrix_vecs, top_k=top_k)
    return res[0] if res else []


_MULTIREGION_MODE_WEIGHTS = {
    "variation": (("center_vec", 0.50), ("vec", 0.30), ("corner_vec", 0.12), ("color_foil_vec", 0.08)),
    "parallel": (("border_vec", 0.34), ("corner_vec", 0.16), ("color_foil_vec", 0.36), ("vec", 0.14)),
    "back_diff": (("vec", 0.45), ("border_vec", 0.25), ("color_foil_vec", 0.20), ("corner_vec", 0.10)),
    "identity": (("vec", 0.75), ("center_vec", 0.25)),
}


def score_multiregion_parallel_pair(q_desc: dict, r_desc: dict, mode: str = "parallel") -> dict:
    """
    Task-aware multi-region similarity between query & reference descriptors.
    Re-normalizes weights automatically over whichever sub-vectors are present so
    legacy v24 entries (only `vec`) or 2D ONNX backbones still score cleanly.
    """
    weights = _MULTIREGION_MODE_WEIGHTS.get(mode, _MULTIREGION_MODE_WEIGHTS["parallel"])
    sims: dict[str, Optional[float]] = {}
    num = 0.0
    den = 0.0
    for key, wt in weights:
        qv = q_desc.get(key) if isinstance(q_desc, dict) else None
        rv = r_desc.get(key) if isinstance(r_desc, dict) else None
        if qv is not None and rv is not None:
            qf = np.asarray(qv, dtype=np.float32).reshape(-1)
            rf = np.asarray(rv, dtype=np.float32).reshape(-1)
            if qf.shape == rf.shape and qf.size > 0:
                cos_raw = float(np.dot(qf, rf))
                sim_val = float(np.clip(cos_raw, 0.0, 1.0)) if key == "color_foil_vec" else calibrate_neural_cosine_to_card_sim(cos_raw)
                sims[key] = round(sim_val, 5)
                num += wt * sim_val
                den += wt
    score = round(float(np.clip(num / den, 0.0, 1.0)), 4) if den > 1e-6 else 0.0
    return {
        "score": score,
        "global_sim": sims.get("vec"),
        "border_sim": sims.get("border_vec"),
        "corner_sim": sims.get("corner_vec"),
        "center_sim": sims.get("center_vec"),
        "color_foil_sim": sims.get("color_foil_vec"),
    }


def calibrate_neural_cosine_to_card_sim(cos_val: float) -> float:
    """
    Calibrates raw DINOv2 cosine similarity onto Tabulas's `[0.0 .. 1.0]` whole-image scale:
      - Different players/cards typically score ~0.35 - 0.62 -> maps below 0.65
      - Same card across blurry/soft TCDB scan vs 600 DPI Ricoh typically scores ~0.78 - 0.96 -> maps to 0.80 - 0.99
    """
    c = float(np.clip(cos_val, 0.0, 1.0))
    if c >= 0.72:
        # Smooth upward calibration in the confirmed-match band
        mapped = 0.72 + (c - 0.72) * 1.08
    else:
        mapped = c * 0.98
    return round(float(np.clip(mapped, 0.0, 1.0)), 4)


class NeuralEmbeddingEngine:
    """
    GPU-accelerated ONNX Vision Transformer embedding extractor (Win #2).
    Runs fixed-shape `[B, 3, 224, 224]` DINOv2-small inference via DirectML / CUDA
    with automatic batch-size backoff and 100% seamless CPU fallback.
    """

    def __init__(self, model_path: Optional[Path] = None, prefer_gpu: bool = True, claim_slot: bool = True):
        ensure_directories()
        self.prefer_gpu = bool(prefer_gpu)
        self.claim_slot = bool(claim_slot)
        self.model_path: Optional[Path] = Path(model_path) if model_path else self._discover_best_model()
        self.session = None
        self.active_provider = "None"
        self.input_name = ""
        self.output_name = ""
        self.input_size = (224, 224)
        self.model_key = "dinov2_small"
        self._effective_max_batch: int = get_recommended_neural_batch_size()
        self._static_batch_one: bool = False
        self._dml_bucket_padding: bool = True

    def _discover_best_model(self) -> Optional[Path]:
        if not NEURAL_MODELS_DIR.exists():
            return None
        for spec in RECOMMENDED_ONNX_MODELS:
            if spec["embedding_dim"] <= 0:
                continue
            cand = NEURAL_MODELS_DIR / spec["filename"]
            if cand.exists() and cand.is_file() and cand.stat().st_size > 1_000_000:
                self.input_size = tuple(spec["input_size"])
                self.model_key = spec["key"]
                return cand
        return None

    @property
    def is_ready(self) -> bool:
        return self.model_path is not None and self.model_path.exists() and self.model_path.stat().st_size > 1_000_000

    def ensure_loaded(self) -> bool:
        if self.session is not None:
            return True
        if not self.is_ready:
            self.model_path = self._discover_best_model()
            if not self.is_ready:
                return False
        try:
            self.session, self.active_provider = create_onnx_session(
                self.model_path, prefer_gpu=self.prefer_gpu, purpose="neural", claim_slot=self.claim_slot
            )
            inp0 = self.session.get_inputs()[0]
            self.input_name = inp0.name
            inp_shape = getattr(inp0, "shape", None) or []
            if len(inp_shape) >= 1 and isinstance(inp_shape[0], int):
                if inp_shape[0] == 1:
                    self._static_batch_one = True
                    self._effective_max_batch = 1
                elif inp_shape[0] > 1:
                    self._effective_max_batch = min(self._effective_max_batch, int(inp_shape[0]))
            outs = self.session.get_outputs()
            # Prefer last_hidden_state (3D token output) when present; otherwise first output
            pref_out = next((o for o in outs if "last_hidden_state" in str(o.name).lower()), outs[0])
            self.output_name = pref_out.name
            return True
        except Exception:
            self.session = None
            return False

    def extract_descriptors_batch(
        self,
        crops_rgb: list[np.ndarray],
        batch_size: Optional[int] = None,
        include_color_foil: bool = True,
        include_patch_tokens: bool = False,
    ) -> list[Optional[dict]]:
        """
        Extracts multi-region descriptors (`vec`, `border_vec`, `corner_vec`, `center_vec`,
        `color_foil_vec`, and optional in-memory `patch_tokens`) for a list of RGB crops using
        micro-batched DirectML/CUDA inference with power-of-2 bucket padding, automatic VRAM
        backoff, and clean CPU fallback.
        """
        if not crops_rgb or not self.ensure_loaded():
            return [None] * len(crops_rgb)

        n_total = len(crops_rgb)
        results: list[Optional[dict]] = [None] * n_total
        req_bs = int(batch_size or self._effective_max_batch)
        cur_bs = 1 if self._static_batch_one else max(1, min(req_bs, self._effective_max_batch))
        pos = 0

        while pos < n_total:
            chunk = crops_rgb[pos : pos + cur_bs]
            chunk_n = len(chunk)
            try:
                tensor = preprocess_card_batch(chunk, input_size=self.input_size)
                is_dml = "DmlExecutionProvider" in str(self.active_provider)
                if is_dml and self._dml_bucket_padding and not self._static_batch_one and chunk_n < cur_bs:
                    bucket_bs = _choose_dml_bucket(chunk_n, cur_bs)
                    if bucket_bs > chunk_n:
                        pad_cnt = bucket_bs - chunk_n
                        pad_frames = np.repeat(tensor[-1:], pad_cnt, axis=0)
                        tensor = np.ascontiguousarray(np.concatenate([tensor, pad_frames], axis=0), dtype=np.float32)

                raw_out = self.session.run([self.output_name], {self.input_name: tensor})[0]
                if raw_out.shape[0] > chunk_n:
                    raw_out = raw_out[:chunk_n]
                mr = _extract_multiregion_patch_vectors(raw_out)
                vecs = mr["vec"]
                b_vecs = mr["border_vec"]
                c_vecs = mr["corner_vec"]
                m_vecs = mr["center_vec"]
                has_spatial = bool(include_patch_tokens and raw_out.ndim == 3 and raw_out.shape[1] >= 17)

                for j in range(chunk_n):
                    cf_vec = extract_color_foil_descriptor(chunk[j]) if include_color_foil else None
                    pt_toks = _l2_normalize_rows(raw_out[j, 1:, :]).astype(np.float32) if has_spatial else None
                    results[pos + j] = {
                        "vec": vecs[j],
                        "border_vec": b_vecs[j] if b_vecs is not None else None,
                        "corner_vec": c_vecs[j] if c_vecs is not None else None,
                        "center_vec": m_vecs[j] if m_vecs is not None else None,
                        "color_foil_vec": cf_vec,
                        "patch_tokens": pt_toks,
                        "schema_v": 2,
                    }
                pos += chunk_n
            except Exception:
                if cur_bs > 1:
                    cur_bs = max(1, cur_bs // 2)
                    self._effective_max_batch = min(self._effective_max_batch, cur_bs)
                elif self.active_provider != "CPUExecutionProvider":
                    # Auto-fallback to CPU session on GPU/DirectML runtime error
                    try:
                        self.prefer_gpu = False
                        self.session, self.active_provider = create_onnx_session(
                            self.model_path, prefer_gpu=False, purpose="neural", claim_slot=False
                        )
                        inp0 = self.session.get_inputs()[0]
                        self.input_name = inp0.name
                        outs = self.session.get_outputs()
                        pref_out = next((o for o in outs if "last_hidden_state" in str(o.name).lower()), outs[0])
                        self.output_name = pref_out.name
                        if self.claim_slot:
                            release_gpu_worker_slot()
                    except Exception:
                        pos += 1
                else:
                    pos += 1
        return results

    def extract_descriptor(
        self,
        crop_rgb: np.ndarray,
        include_color_foil: bool = True,
        include_patch_tokens: bool = False,
    ) -> Optional[dict]:
        if crop_rgb is None or crop_rgb.size == 0 or not self.ensure_loaded():
            return None
        res = self.extract_descriptors_batch(
            [crop_rgb],
            batch_size=1,
            include_color_foil=include_color_foil,
            include_patch_tokens=include_patch_tokens,
        )
        return res[0] if res else None

    def extract_embeddings_batch(self, crops_rgb: list[np.ndarray], batch_size: Optional[int] = None) -> list[Optional[np.ndarray]]:
        """Extracts L2-normalized float32 global embeddings for a list of RGB crops using GPU batching."""
        descs = self.extract_descriptors_batch(crops_rgb, batch_size=batch_size, include_color_foil=False)
        return [d["vec"] if isinstance(d, dict) else None for d in descs]

    def extract_embedding(self, crop_rgb: np.ndarray) -> Optional[np.ndarray]:
        if crop_rgb is None or crop_rgb.size == 0 or not self.ensure_loaded():
            return None
        res = self.extract_embeddings_batch([crop_rgb], batch_size=1)
        return res[0] if res else None


def is_neural_embeddings_enabled() -> bool:
    """Returns True only when DINOv2 (or another embedding ONNX) is installed AND enabled in Compute Settings."""
    cfg = load_compute_settings()
    if not bool(cfg.get("enable_neural_embeddings", True)):
        return False
    eng = get_neural_embedding_engine(load_now=False)
    return eng is not None and eng.is_ready


def get_neural_embedding_engine(load_now: bool = True) -> Optional[NeuralEmbeddingEngine]:
    global _SINGLETON_ENGINE
    with _ENGINE_LOCK:
        if _SINGLETON_ENGINE is None:
            _SINGLETON_ENGINE = NeuralEmbeddingEngine(prefer_gpu=True)
        elif not _SINGLETON_ENGINE.is_ready:
            # Re-discover in case user just clicked Download DINOv2
            _SINGLETON_ENGINE = NeuralEmbeddingEngine(prefer_gpu=True)
        if load_now and _SINGLETON_ENGINE.is_ready:
            _SINGLETON_ENGINE.ensure_loaded()
        return _SINGLETON_ENGINE


def reset_neural_engine_cache():
    global _SINGLETON_ENGINE, _MEM_EMBED_CACHE, _MEM_EMBED_MTIME, _MEM_EMBED_DIRTY_COUNT, _MEM_EMBED_LAST_FLUSH_TS
    with _ENGINE_LOCK:
        _SINGLETON_ENGINE = None
    with _INDEX_LOCK:
        _MEM_EMBED_CACHE = None
        _MEM_EMBED_MTIME = -1.0
        _MEM_EMBED_DIRTY_COUNT = 0
        _MEM_EMBED_LAST_FLUSH_TS = 0.0
        _SET_MATRIX_CACHE.clear()
        _PAR_GROUP_MATRIX_CACHE.clear()


# ==============================================================================
# 1-CLICK VERIFIED DINOV2-SMALL ONNX DOWNLOADER
# ==============================================================================
def download_dinov2_small_model(
    force_redownload: bool = False,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """
    Downloads the verified `facebook/dinov2-small` ONNX model (~88 MB) into
    `C:\\Tabulas Card Hub\\Cache\\Library\\Models\\dinov2_vits14.onnx` with streaming progress,
    mirror fallback, integrity verification, and an immediate DirectML/CUDA smoke test!
    """
    import requests

    ensure_directories()
    NEURAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = NEURAL_MODELS_DIR / DINOV2_MODEL_FILENAME

    if dest_path.exists() and dest_path.stat().st_size > 40_000_000 and not force_redownload:
        size_mb = round(dest_path.stat().st_size / (1024.0 * 1024.0), 1)
        if log_cb:
            log_cb(f"✅ DINOv2-small ONNX already installed ({size_mb} MB): {dest_path}")
        reset_neural_engine_cache()
        eng = get_neural_embedding_engine(load_now=True)
        return {
            "success": True,
            "already_installed": True,
            "model_path": str(dest_path),
            "size_mb": size_mb,
            "active_provider": eng.active_provider if eng else "Unknown",
        }

    tmp_path = dest_path.with_suffix(".onnx.tmp")
    last_err = ""
    downloaded_ok = False
    headers = {"User-Agent": "TabulasCardHub/0.24 (ONNX-DirectML-Downloader)"}

    for m_idx, url in enumerate(DINOV2_DOWNLOAD_MIRRORS, 1):
        try:
            if log_cb:
                log_cb(f"[Mirror {m_idx}/{len(DINOV2_DOWNLOAD_MIRRORS)}] Downloading DINOv2-small ONNX from {url} ...")
            with requests.get(url, headers=headers, stream=True, timeout=(15, 180), allow_redirects=True) as resp:
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code} from {url}"
                    if log_cb:
                        log_cb(f"  ⚠️ {last_err}")
                    continue
                total_bytes = int(resp.headers.get("Content-Length") or 0)
                total_mb = round(total_bytes / (1024.0 * 1024.0), 1) if total_bytes > 0 else 88.0
                got_bytes = 0
                last_pct_logged = -1
                with open(tmp_path, "wb") as f_out:
                    for chunk in resp.iter_content(chunk_size=1024 * 512):
                        if not chunk:
                            continue
                        f_out.write(chunk)
                        got_bytes += len(chunk)
                        if total_bytes > 0:
                            pct_i = int(round(100.0 * got_bytes / float(total_bytes)))
                            if pct_i >= last_pct_logged + 10 or pct_i == 100:
                                last_pct_logged = pct_i
                                got_mb = got_bytes / (1024.0 * 1024.0)
                                if progress_callback:
                                    progress_callback(pct_i, 100, f"Downloading DINOv2-small ({got_mb:.1f} / {total_mb:.1f} MB)")
                                elif log_cb:
                                    log_cb(f"  [{pct_i}/100] Downloaded {got_mb:.1f} / {total_mb:.1f} MB...")

                if got_bytes < 40_000_000:
                    last_err = f"Downloaded file too small ({got_bytes:,} bytes) — skipping mirror."
                    if log_cb:
                        log_cb(f"  ⚠️ {last_err}")
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                    continue

                os.replace(str(tmp_path), str(dest_path))
                downloaded_ok = True
                break
        except Exception as e:
            last_err = str(e)
            if log_cb:
                log_cb(f"  ⚠️ Mirror error: {last_err}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    if not downloaded_ok:
        raise RuntimeError(f"Failed to download DINOv2-small ONNX from all mirrors. Last error: {last_err}")

    size_mb = round(dest_path.stat().st_size / (1024.0 * 1024.0), 1)
    if log_cb:
        log_cb(f"📦 Saved {dest_path.name} ({size_mb} MB). Running GPU DirectML/CUDA smoke test...")

    reset_neural_engine_cache()
    eng = get_neural_embedding_engine(load_now=True)
    if eng is None or not eng.ensure_loaded():
        raise RuntimeError("DINOv2-small downloaded, but ONNX Runtime failed to initialize the session.")

    dummy_card = np.random.randint(20, 235, (356, 256, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    vec = eng.extract_embedding(dummy_card)
    ms = (time.perf_counter() - t0) * 1000.0
    if vec is None or vec.size < 128:
        raise RuntimeError("DINOv2-small smoke test returned invalid embedding output.")

    if log_cb:
        log_cb(
            f"✅ DINOv2-small verified on {eng.active_provider}! "
            f"Output dim={vec.size} | Single-card inference={ms:.1f} ms | Ready for GPU library indexing."
        )
    return {
        "success": True,
        "already_installed": False,
        "model_path": str(dest_path),
        "size_mb": size_mb,
        "embedding_dim": int(vec.size),
        "active_provider": eng.active_provider,
        "smoke_ms": round(ms, 1),
    }


# ==============================================================================
# INCREMENTAL PERSISTENT NEURAL EMBEDDING CACHE (FLOAT16, ~768 BYTES / IMAGE)
# ==============================================================================
def _norm_path_key(p: Path | str) -> str:
    try:
        return str(Path(p).resolve()).lower()
    except Exception:
        return str(p).strip().lower()


def load_neural_embeddings_cache(force_reload: bool = False) -> dict:
    global _MEM_EMBED_CACHE, _MEM_EMBED_MTIME
    with _INDEX_LOCK:
        if not NEURAL_EMBEDDINGS_CACHE_FILE.exists():
            _MEM_EMBED_CACHE = {"schema": NEURAL_CACHE_SCHEMA_V25, "model": DINOV2_MODEL_FILENAME, "embeddings": {}}
            _MEM_EMBED_MTIME = -1.0
            return _MEM_EMBED_CACHE
        try:
            mt = NEURAL_EMBEDDINGS_CACHE_FILE.stat().st_mtime
            if not force_reload and _MEM_EMBED_CACHE is not None and _MEM_EMBED_MTIME == mt:
                return _MEM_EMBED_CACHE
            with open(NEURAL_EMBEDDINGS_CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict) and isinstance(data.get("embeddings"), dict):
                _MEM_EMBED_CACHE = data
                _MEM_EMBED_MTIME = mt
                _SET_MATRIX_CACHE.clear()
                _PAR_GROUP_MATRIX_CACHE.clear()
                return _MEM_EMBED_CACHE
        except Exception:
            pass
        _MEM_EMBED_CACHE = {"schema": NEURAL_CACHE_SCHEMA_V25, "model": DINOV2_MODEL_FILENAME, "embeddings": {}}
        return _MEM_EMBED_CACHE


def save_neural_embeddings_cache(cache_obj: dict):
    global _MEM_EMBED_CACHE, _MEM_EMBED_MTIME, _MEM_EMBED_DIRTY_COUNT, _MEM_EMBED_LAST_FLUSH_TS
    with _INDEX_LOCK:
        try:
            cache_obj["schema"] = NEURAL_CACHE_SCHEMA_V25
            cache_obj["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            def _dump_embs(tmp_p: Path):
                with open(tmp_p, "wb") as f:
                    pickle.dump(cache_obj, f, protocol=pickle.HIGHEST_PROTOCOL)

            atomic_write_bytes(NEURAL_EMBEDDINGS_CACHE_FILE, _dump_embs)
            _MEM_EMBED_CACHE = cache_obj
            _MEM_EMBED_MTIME = NEURAL_EMBEDDINGS_CACHE_FILE.stat().st_mtime
            _MEM_EMBED_DIRTY_COUNT = 0
            _MEM_EMBED_LAST_FLUSH_TS = time.monotonic()
            _SET_MATRIX_CACHE.clear()
            _PAR_GROUP_MATRIX_CACHE.clear()
        except Exception:
            pass


def _record_to_descriptor(rec: dict) -> Optional[dict]:
    if not isinstance(rec, dict) or rec.get("vec") is None:
        return None
    out = {
        "vec": np.asarray(rec["vec"], dtype=np.float32),
        "border_vec": np.asarray(rec["border_vec"], dtype=np.float32) if rec.get("border_vec") is not None else None,
        "corner_vec": np.asarray(rec["corner_vec"], dtype=np.float32) if rec.get("corner_vec") is not None else None,
        "center_vec": np.asarray(rec["center_vec"], dtype=np.float32) if rec.get("center_vec") is not None else None,
        "color_foil_vec": np.asarray(rec["color_foil_vec"], dtype=np.float32) if rec.get("color_foil_vec") is not None else None,
        "schema_v": int(rec.get("schema_v", 1)),
    }
    return out


def _rec_has_multiregion(rec: dict) -> bool:
    return (
        isinstance(rec, dict)
        and rec.get("vec") is not None
        and rec.get("color_foil_vec") is not None
        and (rec.get("border_vec") is not None or int(rec.get("schema_v", 1)) >= 2)
    )


def _maybe_flush_lazy_cache(cache: dict):
    global _MEM_EMBED_DIRTY_COUNT, _MEM_EMBED_LAST_FLUSH_TS
    now_m = time.monotonic()
    if _MEM_EMBED_LAST_FLUSH_TS <= 0.0:
        _MEM_EMBED_LAST_FLUSH_TS = now_m
    if _MEM_EMBED_DIRTY_COUNT >= _LAZY_FLUSH_DIRTY_THRESHOLD or (
        _MEM_EMBED_DIRTY_COUNT >= 100 and (now_m - _MEM_EMBED_LAST_FLUSH_TS) >= _LAZY_FLUSH_INTERVAL_SEC
    ):
        save_neural_embeddings_cache(cache)


def _build_cache_entry(p_obj: Path, k: str, cur_mt: float, desc: dict) -> dict:
    parsed = parse_unified_card_filename(p_obj.name) or {}
    s_name = parsed.get("set") or p_obj.parent.name.replace("_", " ")
    entry = {
        "path": str(p_obj),
        "mtime": cur_mt,
        "set_key": canonical_set_key(s_name),
        "subset": parsed.get("subset") or "Base",
        "n_cnum": norm(parsed.get("card_number") or ""),
        "side": parsed.get("side") or ("B" if p_obj.name.upper().endswith("_B.JPG") else "F"),
        "source": "My_Collection" if str(REVIEWED_CARDS_DIR).lower() in k else "Reference_Library",
        "schema_v": 2,
        "vec": desc["vec"].astype(np.float16),
    }
    for sub_k in ("border_vec", "corner_vec", "center_vec", "color_foil_vec"):
        if desc.get(sub_k) is not None:
            entry[sub_k] = np.asarray(desc[sub_k], dtype=np.float16)
    return entry


def precompute_batch_image_descriptors(
    img_paths: list[Path | str],
    batch_size: Optional[int] = None,
    require_multiregion: bool = True,
    auto_persist: bool = True,
) -> dict[str, dict]:
    """
    Micro-batches any uncached or legacy-v24 image paths in `img_paths` through DirectML
    in a single parallel decode + GPU batch pass, returning `{norm_path_key: descriptor}`.
    """
    global _MEM_EMBED_DIRTY_COUNT
    if not img_paths or not is_neural_embeddings_enabled():
        return {}

    cfg = load_compute_settings()
    want_mr = bool(require_multiregion) and bool(cfg.get("enable_multiregion_neural", True))
    results: dict[str, dict] = {}
    to_compute: list[tuple[Path, str, float]] = []
    seen_keys: set[str] = set()

    with _INDEX_LOCK:
        cache = load_neural_embeddings_cache()
        embs = cache.setdefault("embeddings", {})
        for raw_p in img_paths:
            if not raw_p:
                continue
            p_obj = Path(raw_p)
            k = _norm_path_key(p_obj)
            if k in seen_keys:
                continue
            seen_keys.add(k)
            if not p_obj.exists():
                continue
            try:
                cur_mt = p_obj.stat().st_mtime
            except Exception:
                cur_mt = 0.0
            rec = embs.get(k)
            if isinstance(rec, dict) and rec.get("vec") is not None and abs(float(rec.get("mtime", 0.0)) - cur_mt) < 2.0:
                if not want_mr or _rec_has_multiregion(rec):
                    d_hit = _record_to_descriptor(rec)
                    if d_hit is not None:
                        results[k] = d_hit
                        continue
            to_compute.append((p_obj, k, cur_mt))

    if not to_compute:
        return results

    eng = get_neural_embedding_engine(load_now=True)
    if eng is None or not eng.is_ready:
        return results

    from concurrent.futures import ThreadPoolExecutor

    def _load_rgb(item):
        p_o, k_s, mt_v = item
        try:
            with Image.open(p_o) as im:
                return np.array(im.convert("RGB")), p_o, k_s, mt_v
        except Exception:
            return None, p_o, k_s, mt_v

    decoded_crops: list[np.ndarray] = []
    decoded_metas: list[tuple[Path, str, float]] = []
    if len(to_compute) >= 4:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for rgb, p_o, k_s, mt_v in pool.map(_load_rgb, to_compute):
                if rgb is not None:
                    decoded_crops.append(rgb)
                    decoded_metas.append((p_o, k_s, mt_v))
    else:
        for item in to_compute:
            rgb, p_o, k_s, mt_v = _load_rgb(item)
            if rgb is not None:
                decoded_crops.append(rgb)
                decoded_metas.append((p_o, k_s, mt_v))

    if not decoded_crops:
        return results

    eff_bs = int(batch_size or get_recommended_neural_batch_size(cfg))
    descs = eng.extract_descriptors_batch(decoded_crops, batch_size=eff_bs, include_color_foil=want_mr)

    new_entries: dict[str, dict] = {}
    for (p_o, k_s, mt_v), desc in zip(decoded_metas, descs):
        if desc is not None:
            results[k_s] = desc
            new_entries[k_s] = _build_cache_entry(p_o, k_s, mt_v, desc)

    if new_entries:
        with _INDEX_LOCK:
            cache = load_neural_embeddings_cache()
            embs = cache.setdefault("embeddings", {})
            embs.update(new_entries)
            _MEM_EMBED_DIRTY_COUNT += len(new_entries)
            if auto_persist:
                _maybe_flush_lazy_cache(cache)

    return results


def get_or_compute_image_descriptor(
    img_path: Path | str,
    auto_persist: bool = True,
    require_multiregion: bool = True,
) -> Optional[dict]:
    """
    Retrieves a card image's multi-region descriptor from the RAM/disk neural index in <0.01ms,
    or computes it on DirectML GPU if not yet indexed (or upgrades legacy v24 entries).
    """
    if not img_path or not is_neural_embeddings_enabled():
        return None
    p_obj = Path(img_path)
    k = _norm_path_key(p_obj)
    res = precompute_batch_image_descriptors(
        [p_obj], batch_size=1, require_multiregion=require_multiregion, auto_persist=auto_persist
    )
    return res.get(k)


def get_or_compute_image_embedding(img_path: Path | str, auto_persist: bool = True) -> Optional[np.ndarray]:
    """
    Retrieves a card image's 384-d DINOv2 embedding from the RAM/disk neural index in <0.01ms,
    or computes it lazily on DirectML GPU if not yet indexed.
    """
    desc = get_or_compute_image_descriptor(img_path, auto_persist=auto_persist, require_multiregion=False)
    return desc["vec"] if isinstance(desc, dict) else None


def flush_neural_embeddings_if_dirty():
    global _MEM_EMBED_DIRTY_COUNT
    if _MEM_EMBED_DIRTY_COUNT > 0 and _MEM_EMBED_CACHE is not None:
        save_neural_embeddings_cache(_MEM_EMBED_CACHE)


def build_or_update_neural_embedding_index(
    set_filter: Optional[str] = None,
    batch_size: Optional[int] = None,
    force_rebuild: bool = False,
    upgrade_legacy: bool = True,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """
    Batched GPU Neural Index Builder (RX 9070 XT DirectML):
      - Incrementally embeds all new/changed Front (`_F.jpg`) & Back (`_B.jpg`) images across
        `D:\\Tabulas Set Library\\_My_Collection\\` and `D:\\Tabulas Set Library\\Reference_Library\\`.
      - Upgrades legacy v24 entries in-place to v25 multi-region descriptors (`border_vec`,
        `corner_vec`, `center_vec`, `color_foil_vec`) when `upgrade_legacy=True`.
      - Uses double-buffered CPU decode + GPU inference and large-cache checkpoint cadence
        (1,500 items or 60s) into `neural_embeddings_v1.pkl`.
    """
    ensure_directories()
    eng = get_neural_embedding_engine(load_now=True)
    if eng is None or not eng.is_ready or not eng.ensure_loaded():
        raise RuntimeError(
            "DINOv2-small ONNX model is not installed yet. Click 'Download DINOv2-small ONNX' in Settings -> Hardware & GPU first."
        )

    cfg = load_compute_settings()
    want_mr = bool(cfg.get("enable_multiregion_neural", True))
    eff_bs = max(4, min(64, int(batch_size or get_recommended_neural_batch_size(cfg))))

    clean_set_f = str(set_filter or "").strip()
    if clean_set_f in ("All Sets", "ALL"):
        clean_set_f = ""
    target_sk = canonical_set_key(clean_set_f) if clean_set_f else ""

    cache = (
        {"schema": NEURAL_CACHE_SCHEMA_V25, "model": eng.model_path.name, "embeddings": {}}
        if force_rebuild
        else load_neural_embeddings_cache(force_reload=True)
    )
    embs: dict = cache.setdefault("embeddings", {})
    cache["model"] = eng.model_path.name
    cache["schema"] = NEURAL_CACHE_SCHEMA_V25

    if log_cb:
        log_cb(
            f"🧬 Scanning Reference_Library & _My_Collection for neural indexing "
            f"(provider={eng.active_provider}, batch={eff_bs}, multiregion={want_mr}, set={clean_set_f or 'All Sets'})..."
        )

    # Discover candidate Front & Back .jpg images (skip _C.jpg corner sheets!)
    candidates: list[tuple[Path, str, float, dict]] = []
    skipped_cached = 0
    upgrading_legacy = 0
    roots = [(REVIEWED_CARDS_DIR, "My_Collection"), (REFERENCE_TEMPLATES_DIR, "Reference_Library")]

    for root_dir, src_lbl in roots:
        if not root_dir.exists():
            continue
        for sub_dir in sorted(root_dir.iterdir()):
            if not sub_dir.is_dir():
                continue
            if sub_dir.name.lower() in ("logs", "reports", ".verified_backups", "_my_collection", "unprocessed_cards", "reference_library"):
                continue
            dir_sk = canonical_set_key(sub_dir.name.replace("_", " "))
            if target_sk and dir_sk != target_sk:
                continue
            for img_p in sub_dir.glob("*.jpg"):
                up_n = img_p.name.upper()
                if up_n.endswith("_C.JPG"):
                    continue
                k = _norm_path_key(img_p)
                try:
                    mt = img_p.stat().st_mtime
                except Exception:
                    continue
                existing = embs.get(k)
                if not force_rebuild and isinstance(existing, dict) and existing.get("vec") is not None and abs(float(existing.get("mtime", 0.0)) - mt) < 2.0:
                    if not (upgrade_legacy and want_mr) or _rec_has_multiregion(existing):
                        skipped_cached += 1
                        continue
                    upgrading_legacy += 1
                parsed = parse_unified_card_filename(img_p.name) or {}
                s_name = parsed.get("set") or sub_dir.name.replace("_", " ")
                side_c = parsed.get("side") or ("B" if up_n.endswith("_B.JPG") else "F")
                meta = {
                    "key": k,
                    "path": str(img_p),
                    "mtime": mt,
                    "set_key": canonical_set_key(s_name),
                    "subset": parsed.get("subset") or "Base",
                    "n_cnum": norm(parsed.get("card_number") or ""),
                    "side": side_c,
                    "source": src_lbl,
                }
                candidates.append((img_p, k, mt, meta))

    total_new = len(candidates)
    if total_new == 0:
        msg = f"Neural index already 100% up to date ({len(embs):,} cached embeddings; {skipped_cached:,} unchanged)."
        if log_cb:
            log_cb(f"✅ {msg}")
        return {
            "success": True,
            "newly_embedded": 0,
            "upgraded_legacy": 0,
            "skipped_cached": skipped_cached,
            "total_cached": len(embs),
            "provider": eng.active_provider,
            "message": msg,
        }

    if log_cb:
        upg_note = f", including {upgrading_legacy:,} legacy v24->v25 upgrades" if upgrading_legacy else ""
        log_cb(
            f"⚡ Embedding {total_new:,} card image(s) on {eng.active_provider} "
            f"(skipping {skipped_cached:,} up-to-date{upg_note})..."
        )

    from concurrent.futures import ThreadPoolExecutor

    t0 = time.perf_counter()
    embedded_ok = 0
    failed_cnt = 0
    bs = eff_bs
    items_since_flush = 0
    last_flush_ts = time.monotonic()

    def _load_rgb_fast(item_tuple):
        img_p, _, _, meta = item_tuple
        try:
            with Image.open(img_p) as im:
                # Resize to 224x224 on decode threads (also valid for 160x224 color_foil_vec)
                arr = np.array(im.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR))
            return arr, meta
        except Exception:
            return None, meta

    def _decode_slice(pool: ThreadPoolExecutor, batch_slice: list) -> tuple[list[np.ndarray], list[dict], int]:
        crops: list[np.ndarray] = []
        metas: list[dict] = []
        errs = 0
        for arr_c, meta_c in pool.map(_load_rgb_fast, batch_slice):
            if arr_c is not None:
                crops.append(arr_c)
                metas.append(meta_c)
            else:
                errs += 1
        return crops, metas, errs

    slices = [candidates[i : i + bs] for i in range(0, total_new, bs)]
    with ThreadPoolExecutor(max_workers=4) as decode_pool:
        next_future = decode_pool.submit(_decode_slice, decode_pool, slices[0]) if slices else None
        done_n = 0
        for s_idx, cur_slice in enumerate(slices):
            crops_rgb, valid_metas, dec_errs = next_future.result() if next_future else ([], [], 0)
            failed_cnt += dec_errs
            if s_idx + 1 < len(slices):
                next_future = decode_pool.submit(_decode_slice, decode_pool, slices[s_idx + 1])
            else:
                next_future = None

            if crops_rgb:
                descs = eng.extract_descriptors_batch(crops_rgb, batch_size=bs, include_color_foil=want_mr)
                for meta, desc in zip(valid_metas, descs):
                    if desc is not None:
                        rec_entry = {
                            "path": meta["path"],
                            "mtime": meta["mtime"],
                            "set_key": meta["set_key"],
                            "subset": meta["subset"],
                            "n_cnum": meta["n_cnum"],
                            "side": meta["side"],
                            "source": meta["source"],
                            "schema_v": 2,
                            "vec": desc["vec"].astype(np.float16),
                        }
                        for sub_k in ("border_vec", "corner_vec", "center_vec", "color_foil_vec"):
                            if desc.get(sub_k) is not None:
                                rec_entry[sub_k] = np.asarray(desc[sub_k], dtype=np.float16)
                        embs[meta["key"]] = rec_entry
                        embedded_ok += 1
                        items_since_flush += 1
                    else:
                        failed_cnt += 1

            done_n = min(total_new, done_n + len(cur_slice))
            elapsed = max(0.05, time.perf_counter() - t0)
            rate_ips = done_n / elapsed
            if progress_callback:
                progress_callback(
                    done_n,
                    total_new,
                    f"Embedded {done_n:,}/{total_new:,} images ({rate_ips:.1f} img/s on {eng.active_provider})",
                )
            elif log_cb and (done_n % (bs * 8) == 0 or done_n == total_new):
                log_cb(f"  [{done_n}/{total_new}] Embedded {embedded_ok:,} images @ {rate_ips:.1f} img/s ({eng.active_provider})")

            now_m = time.monotonic()
            if s_idx + 1 < len(slices) and items_since_flush > 0 and (
                items_since_flush >= _INDEX_CHECKPOINT_INTERVAL_ITEMS
                or (now_m - last_flush_ts) >= _INDEX_CHECKPOINT_INTERVAL_SEC
            ):
                save_neural_embeddings_cache(cache)
                items_since_flush = 0
                last_flush_ts = time.monotonic()

    save_neural_embeddings_cache(cache)
    total_sec = round(time.perf_counter() - t0, 1)
    final_ips = round(embedded_ok / max(0.1, total_sec), 1)
    msg = (
        f"Indexed {embedded_ok:,} card image(s) in {total_sec}s ({final_ips} img/s on {eng.active_provider}) | "
        f"Total neural index: {len(embs):,} embeddings."
    )
    if log_cb:
        log_cb(f"✅ {msg}")
    return {
        "success": True,
        "newly_embedded": embedded_ok,
        "upgraded_legacy": upgrading_legacy,
        "skipped_cached": skipped_cached,
        "failed": failed_cnt,
        "total_cached": len(embs),
        "elapsed_sec": total_sec,
        "images_per_sec": final_ips,
        "provider": eng.active_provider,
        "message": msg,
    }


def search_set_neural_embeddings(
    query_front_emb: np.ndarray,
    set_name: str,
    side: str = "F",
    top_k: int = 12,
) -> list[tuple[float, dict]]:
    """
    Runs an instant (<2ms) vectorized matrix multiply (`M @ q`) across ALL indexed
    `_My_Collection` and `Reference_Library` card images for `set_name`.
    """
    if query_front_emb is None or not set_name:
        return []
    cache = load_neural_embeddings_cache()
    embs = cache.get("embeddings") or {}
    if not embs:
        return []

    s_key = canonical_set_key(set_name)
    side_u = str(side or "F").upper()
    mat_key = (s_key, side_u)
    cache_len = len(embs)

    with _INDEX_LOCK:
        cached_mat = _SET_MATRIX_CACHE.get(mat_key)
        if cached_mat is not None and cached_mat[0] == cache_len:
            metas, mat = cached_mat[1], cached_mat[2]
        else:
            metas = []
            vecs_list = []
            for rec in embs.values():
                if not isinstance(rec, dict) or rec.get("vec") is None:
                    continue
                if rec.get("set_key") == s_key and str(rec.get("side", "F")).upper() == side_u and rec.get("n_cnum"):
                    metas.append(rec)
                    vecs_list.append(np.asarray(rec["vec"], dtype=np.float32))
            if not vecs_list:
                return []
            mat = np.stack(vecs_list, axis=0)
            _SET_MATRIX_CACHE[mat_key] = (cache_len, metas, mat)

    hits = batch_cosine_search(query_front_emb, mat, top_k=top_k)
    return [(score, metas[idx]) for idx, score in hits]


def score_parallel_group_vectorized(
    q_desc: dict,
    ref_paths: list[str],
    top_k: int = 5,
) -> Optional[float]:
    """
    Vectorized multi-region parallel exemplar group scoring:
    Stacks `border_vec`, `corner_vec`, and `color_foil_vec` for all cached `ref_paths`
    and computes `M @ q` in one BLAS pass, returning the mean of the Top-K scores.
    """
    if not isinstance(q_desc, dict) or not ref_paths:
        return None
    cache = load_neural_embeddings_cache()
    embs = cache.get("embeddings") or {}
    if not embs:
        return None

    norm_keys = tuple(_norm_path_key(p) for p in ref_paths if p)
    if not norm_keys:
        return None
    cache_len = len(embs)

    with _INDEX_LOCK:
        cached_grp = _PAR_GROUP_MATRIX_CACHE.get(norm_keys)
        if cached_grp is not None and cached_grp[0] == cache_len:
            mats = cached_grp[1]
        else:
            recs = [embs.get(k) for k in norm_keys]
            recs = [r for r in recs if isinstance(r, dict) and r.get("vec") is not None]
            if not recs:
                return None
            mats = {}
            for ch in ("border_vec", "corner_vec", "color_foil_vec"):
                ch_vecs = [np.asarray(r[ch], dtype=np.float32) for r in recs if r.get(ch) is not None]
                if len(ch_vecs) == len(recs):
                    mats[ch] = np.stack(ch_vecs, axis=0)
            if not mats:
                return None
            if len(_PAR_GROUP_MATRIX_CACHE) >= 256:
                _PAR_GROUP_MATRIX_CACHE.clear()
            _PAR_GROUP_MATRIX_CACHE[norm_keys] = (cache_len, mats)

    ch_weights = (("border_vec", 0.38), ("corner_vec", 0.17), ("color_foil_vec", 0.45))
    total_scores = None
    total_w = 0.0
    for ch, wt in ch_weights:
        mat = mats.get(ch)
        qv = q_desc.get(ch)
        if mat is None or qv is None:
            continue
        q = np.asarray(qv, dtype=np.float32).reshape(-1)
        if q.shape[0] != mat.shape[1]:
            continue
        raw_s = mat @ q
        if ch == "color_foil_vec":
            s_vec = np.clip(raw_s, 0.0, 1.0)
        else:
            s_vec = np.where(raw_s >= 0.72, 0.72 + (raw_s - 0.72) * 1.08, raw_s * 0.98)
            s_vec = np.clip(s_vec, 0.0, 1.0)
        total_scores = (s_vec * wt) if total_scores is None else (total_scores + s_vec * wt)
        total_w += wt

    if total_scores is None or total_w <= 1e-6:
        return None
    blended = total_scores / total_w
    k = min(max(1, int(top_k)), len(blended))
    top_vals = np.partition(blended, -k)[-k:]
    return float(np.mean(top_vals))


def benchmark_dinov2_gpu_vs_cpu(batch_size: Optional[int] = None) -> dict:
    """Benchmarks DINOv2-small micro-batched multi-region extraction on CPU vs. DirectML/CUDA GPU."""
    eff_bs = max(4, min(64, int(batch_size or get_recommended_neural_batch_size())))
    out = {
        "installed": False,
        "batch_size": eff_bs,
        "multiregion_enabled": True,
        "cpu_ms_per_batch": None,
        "gpu_ms_per_batch": None,
        "cpu_cards_per_sec": None,
        "gpu_cards_per_sec": None,
        "gpu_provider": "CPUExecutionProvider",
        "speedup": None,
        "note": "",
    }
    model_p = NEURAL_MODELS_DIR / DINOV2_MODEL_FILENAME
    if not model_p.exists() or model_p.stat().st_size < 1_000_000:
        out["note"] = "Download DINOv2-small ONNX (~88 MB) first to benchmark GPU Win #2."
        return out

    out["installed"] = True
    synth_batch = [np.random.randint(20, 235, (256, 200, 3), dtype=np.uint8) for _ in range(eff_bs)]

    try:
        eng_cpu = NeuralEmbeddingEngine(model_path=model_p, prefer_gpu=False, claim_slot=False)
        if eng_cpu.ensure_loaded():
            eng_cpu.extract_descriptors_batch(synth_batch[:4], batch_size=4)  # warmup
            t0 = time.perf_counter()
            eng_cpu.extract_descriptors_batch(synth_batch, batch_size=eff_bs)
            cpu_ms = (time.perf_counter() - t0) * 1000.0
            out["cpu_ms_per_batch"] = round(cpu_ms, 1)
            out["cpu_cards_per_sec"] = round((eff_bs * 1000.0) / max(0.1, cpu_ms), 1)

        eng_gpu = NeuralEmbeddingEngine(model_path=model_p, prefer_gpu=True, claim_slot=False)
        if eng_gpu.ensure_loaded():
            out["gpu_provider"] = eng_gpu.active_provider
            if eng_gpu.active_provider != "CPUExecutionProvider":
                # Warmup DirectML shader compilation for fixed shape [B, 3, 224, 224]
                eng_gpu.extract_descriptors_batch(synth_batch, batch_size=eff_bs)
                t1 = time.perf_counter()
                for _ in range(3):
                    eng_gpu.extract_descriptors_batch(synth_batch, batch_size=eff_bs)
                gpu_ms = ((time.perf_counter() - t1) / 3.0) * 1000.0
                out["gpu_ms_per_batch"] = round(gpu_ms, 1)
                out["gpu_cards_per_sec"] = round((eff_bs * 1000.0) / max(0.1, gpu_ms), 1)
                if out["cpu_ms_per_batch"]:
                    out["speedup"] = round(out["cpu_ms_per_batch"] / max(0.1, gpu_ms), 2)
    except Exception as e:
        out["note"] = f"DINOv2 benchmark note: {e}"
    return out


_DEFECT_MODEL_LOCK = threading.Lock()
_SINGLETON_DEFECT_MODEL: Optional["LocalDefectModelInterface"] = None
_DEFECT_CLASS_LABELS = (
    ("surface_scratch", True),
    ("print_line", True),
    ("dimple_dent", True),
    ("print_spot_fisheye", True),
    ("corner_whitening", True),
    ("edge_chipping", True),
    ("loose_dust_speck", False),
    ("hair_fiber", False),
    ("sleeve_smudge", False),
    ("specular_glare", False),
    ("clean", False),
)


class LocalDefectModelInterface:
    """
    Win #4 Local Offline Defect AI ONNX Classifier (`card_defect_v1.onnx`).
    Runs batched `[B, 3, 128, 128]` candidate patch classification via DirectML / CUDA
    with automatic batch-size backoff and 100% CPU fallback. When `card_defect_v1.onnx` is
    not installed, `is_ready` is False and the hybrid OpenCL + DINOv2 engine handles
    inspection cleanly with zero errors.
    """

    def __init__(self, model_path: Optional[Path] = None, prefer_gpu: bool = True, claim_slot: bool = True):
        self.model_path = Path(model_path) if model_path else (NEURAL_MODELS_DIR / "card_defect_v1.onnx")
        self.prefer_gpu = bool(prefer_gpu)
        self.claim_slot = bool(claim_slot)
        self.session = None
        self.active_provider = "None"
        self.input_name = ""
        self.output_name = ""
        self.input_size = (128, 128)

    @property
    def is_ready(self) -> bool:
        return self.model_path.exists() and self.model_path.is_file() and self.model_path.stat().st_size > 500_000

    def ensure_loaded(self) -> bool:
        if self.session is not None:
            return True
        if not self.is_ready:
            return False
        try:
            self.session, self.active_provider = create_onnx_session(
                self.model_path, prefer_gpu=self.prefer_gpu, purpose="defect", claim_slot=self.claim_slot
            )
            inp0 = self.session.get_inputs()[0]
            self.input_name = inp0.name
            shape = getattr(inp0, "shape", None)
            if isinstance(shape, (list, tuple)) and len(shape) == 4:
                h_v, w_v = shape[2], shape[3]
                if isinstance(h_v, int) and isinstance(w_v, int) and h_v >= 32 and w_v >= 32:
                    self.input_size = (int(w_v), int(h_v))
            self.output_name = self.session.get_outputs()[0].name
            return True
        except Exception:
            self.session = None
            return False

    def classify_candidate_patches(self, patches_rgb: list[np.ndarray], batch_size: int = 16) -> list[Optional[dict]]:
        if not patches_rgb or not self.ensure_loaded():
            return [None] * len(patches_rgb)
        results: list[Optional[dict]] = [None] * len(patches_rgb)
        cur_bs = max(1, int(batch_size))
        pos = 0
        while pos < len(patches_rgb):
            chunk = patches_rgb[pos : pos + cur_bs]
            try:
                tensor = preprocess_card_batch(chunk, input_size=self.input_size)
                logits = np.asarray(self.session.run([self.output_name], {self.input_name: tensor})[0], dtype=np.float32)
                if logits.ndim == 1:
                    logits = logits[None, :]
                exps = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                probs = exps / np.maximum(1e-6, np.sum(exps, axis=1, keepdims=True))
                for j in range(len(chunk)):
                    row_p = probs[j]
                    cls_idx = int(np.argmax(row_p))
                    conf = float(row_p[cls_idx])
                    if cls_idx < len(_DEFECT_CLASS_LABELS):
                        lbl, is_true = _DEFECT_CLASS_LABELS[cls_idx]
                    else:
                        lbl, is_true = (f"class_{cls_idx}", cls_idx < 6)
                    results[pos + j] = {"label": lbl, "is_true_defect": bool(is_true), "confidence": round(conf, 4)}
                pos += len(chunk)
            except Exception:
                if cur_bs > 1:
                    cur_bs = max(1, cur_bs // 2)
                elif self.active_provider != "CPUExecutionProvider":
                    try:
                        self.prefer_gpu = False
                        self.session, self.active_provider = create_onnx_session(
                            self.model_path, prefer_gpu=False, purpose="defect", claim_slot=False
                        )
                        self.input_name = self.session.get_inputs()[0].name
                        self.output_name = self.session.get_outputs()[0].name
                    except Exception:
                        pos += 1
                else:
                    pos += 1
        return results


def get_local_defect_model(load_now: bool = False, claim_slot: bool = True) -> LocalDefectModelInterface:
    global _SINGLETON_DEFECT_MODEL
    with _DEFECT_MODEL_LOCK:
        if _SINGLETON_DEFECT_MODEL is None:
            _SINGLETON_DEFECT_MODEL = LocalDefectModelInterface(prefer_gpu=True, claim_slot=claim_slot)
        if load_now and _SINGLETON_DEFECT_MODEL.is_ready:
            _SINGLETON_DEFECT_MODEL.ensure_loaded()
        return _SINGLETON_DEFECT_MODEL


def get_neural_foundation_status() -> dict:
    ensure_directories()
    installed_models = []
    dinov2_installed = False
    defect_ai_model_installed = False
    for spec in RECOMMENDED_ONNX_MODELS:
        p = NEURAL_MODELS_DIR / spec["filename"]
        min_sz = 500_000 if spec["key"] == "card_defect_detector" else 1_000_000
        is_inst = p.exists() and p.is_file() and p.stat().st_size > min_sz
        if spec["key"] == "dinov2_small" and is_inst:
            dinov2_installed = True
        if spec["key"] == "card_defect_detector" and is_inst:
            defect_ai_model_installed = True
        installed_models.append({
            "key": spec["key"],
            "filename": spec["filename"],
            "role": spec["role"],
            "installed": is_inst,
            "size_mb": round(p.stat().st_size / (1024.0 * 1024.0), 1) if is_inst else 0.0,
        })
    emb_cache_count = 0
    mr_cache_count = 0
    cache_schema = NEURAL_CACHE_SCHEMA_V25
    cache_updated = ""
    if NEURAL_EMBEDDINGS_CACHE_FILE.exists():
        try:
            c_obj = load_neural_embeddings_cache()
            embs_d = c_obj.get("embeddings") or {}
            emb_cache_count = len(embs_d)
            mr_cache_count = sum(1 for r in embs_d.values() if _rec_has_multiregion(r))
            cache_schema = str(c_obj.get("schema") or NEURAL_CACHE_SCHEMA_V24)
            cache_updated = str(c_obj.get("updated_at") or "")
        except Exception:
            pass
    defect_tier = (
        "ONNX+DINOv2+OpenCL" if (defect_ai_model_installed and dinov2_installed) else
        ("DINOv2+OpenCL" if dinov2_installed else "OpenCL/CPU Hybrid")
    )
    return {
        "models_dir": str(NEURAL_MODELS_DIR),
        "embeddings_cache_file": str(NEURAL_EMBEDDINGS_CACHE_FILE),
        "dinov2_installed": dinov2_installed,
        "defect_ai_model_installed": defect_ai_model_installed,
        "defect_ai_ready": True,
        "defect_ai_tier": defect_tier,
        "cached_embeddings_count": emb_cache_count,
        "multiregion_embeddings_count": mr_cache_count,
        "cache_schema": cache_schema,
        "recommended_batch_size": get_recommended_neural_batch_size(),
        "cache_updated_at": cache_updated,
        "installed_models_count": sum(1 for m in installed_models if m["installed"]),
        "models": installed_models,
    }
