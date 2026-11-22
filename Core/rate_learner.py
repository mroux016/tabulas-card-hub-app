from __future__ import annotations
# ==============================================================================
# Core/rate_learner.py - ONLINE ADAPTIVE RATE, UNIFIED DOMAIN WINDOW,
# PER-SET TELEMETRY CACHE & CARD-BASED LEARNING ETA ENGINE
# ==============================================================================
import json
import os
import random
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

__version__ = "0.24.0-beta.5"
__last_updated__ = "2026-11-19 18:20:00"

from Core.config import LOGS_DIR, SET_LIBRARY_CACHE_DIR, ensure_directories

RATE_LEARNER_STATE_FILE = LOGS_DIR / "adaptive_rate_learner.json"

DEFAULT_ENDPOINT_PROFILES: dict[str, dict] = {
    "tcdb_domain": {
        "safe_rpm": 23.5,
        "min_rpm": 8.0,
        "max_rpm": 25.0,
        "current_delay_s": 2.50,
        "min_delay_s": 2.35,
        "max_delay_s": 8.00,
        "last_429_rpm": 25.5,
    },
    "sportscardspro": {
        "safe_rpm": 35.0,
        "min_rpm": 8.0,
        "max_rpm": 90.0,
        "current_delay_s": 1.20,
        "min_delay_s": 0.35,
        "max_delay_s": 8.00,
        "last_429_rpm": 0.0,
    },
    "dugoutvault": {
        "safe_rpm": 30.0,
        "min_rpm": 6.0,
        "max_rpm": 60.0,
        "current_delay_s": 1.00,
        "min_delay_s": 0.40,
        "max_delay_s": 6.00,
        "last_429_rpm": 0.0,
    },
    "mlb_statsapi": {
        "safe_rpm": 90.0,
        "min_rpm": 15.0,
        "max_rpm": 180.0,
        "current_delay_s": 0.30,
        "min_delay_s": 0.15,
        "max_delay_s": 5.00,
        "last_429_rpm": 0.0,
    },
    "wikipedia": {
        "safe_rpm": 90.0,
        "min_rpm": 15.0,
        "max_rpm": 180.0,
        "current_delay_s": 0.30,
        "min_delay_s": 0.15,
        "max_delay_s": 5.00,
        "last_429_rpm": 0.0,
    },
}

DEFAULT_ETA_MODELS: dict[str, dict] = {
    "checklist_only": {
        "ema_sec_per_subset": 3.0,
        "ema_sec_per_card": 0.032,
        "ema_sec_per_dl_card": 0.032,
        "ema_sec_per_skip_card": 0.015,
        "subset_samples": 0,
        "card_samples": 0,
    },
    "checklist_and_images": {
        "ema_sec_per_subset": 32.0,
        "ema_sec_per_card": 0.85,
        "ema_sec_per_dl_card": 4.80,
        "ema_sec_per_skip_card": 0.035,
        "subset_samples": 0,
        "card_samples": 0,
    },
    "images_only": {
        "ema_sec_per_subset": 28.0,
        "ema_sec_per_card": 0.65,
        "ema_sec_per_dl_card": 4.60,
        "ema_sec_per_skip_card": 0.006,
        "subset_samples": 0,
        "card_samples": 0,
    },
    "upgrade": {
        "ema_sec_per_subset": 4.5,
        "ema_sec_per_card": 0.08,
        "ema_sec_per_dl_card": 2.60,
        "ema_sec_per_skip_card": 0.025,
        "subset_samples": 0,
        "card_samples": 0,
    },
    "missing_back": {
        "ema_sec_per_subset": 12.0,
        "ema_sec_per_card": 0.45,
        "ema_sec_per_dl_card": 2.60,
        "ema_sec_per_skip_card": 0.01,
        "subset_samples": 0,
        "card_samples": 0,
    },
}


class AdaptiveRateLearner:
    """
    Cross-script online rate-limit & card-based ETA learner:
      1. Unified `tcdb_domain` 60-second sliding-window governor across TCDB HTML & Images.
      2. Cliff-clamped Cubic/AIMD pacing (`last_429_rpm - 1.5`).
      3. Thumbnail-Direct R-Tier vs S-Tier selection from Card #1.
      4. Persistent per-set card-count & historical run-time cache (`set_stats`).
      5. Card-count-driven Tier-1 Overall & Tier-2 Active Parallel learning ETA models.
    """

    def __init__(self, state_file: Path = RATE_LEARNER_STATE_FILE):
        self.state_file = Path(state_file)
        self._lock = threading.RLock()
        self._windows: dict[str, deque[float]] = {}
        self._last_req_ts: dict[str, float] = {}
        self._consecutive_429: dict[str, int] = {}
        self._dirty_ops = 0
        self._state = self._load_state()

    def _make_default_endpoint(self, name: str) -> dict:
        base = dict(DEFAULT_ENDPOINT_PROFILES.get(name, {
            "safe_rpm": 30.0,
            "min_rpm": 6.0,
            "max_rpm": 90.0,
            "current_delay_s": 1.50,
            "min_delay_s": 0.35,
            "max_delay_s": 8.00,
            "last_429_rpm": 0.0,
        }))
        base.update({
            "clean_streak": 0,
            "total_requests": 0,
            "total_429s": 0,
            "total_403s": 0,
            "ema_latency_ms": 0.0,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return base

    def _load_state(self) -> dict:
        ensure_directories()
        state = {
            "endpoints": {},
            "set_tiers": {},
            "eta_models": {k: dict(v) for k, v in DEFAULT_ETA_MODELS.items()},
            "set_stats": {},
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if not self.state_file.exists():
            legacy_state = SET_LIBRARY_CACHE_DIR / "adaptive_rate_learner.json"
            if legacy_state.exists():
                try:
                    self.state_file.parent.mkdir(parents=True, exist_ok=True)
                    self.state_file.write_text(legacy_state.read_text(encoding="utf-8-sig"), encoding="utf-8")
                except Exception:
                    pass
        if self.state_file.exists():
            try:
                loaded = json.loads(self.state_file.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    state["endpoints"] = loaded.get("endpoints") if isinstance(loaded.get("endpoints"), dict) else {}
                    state["set_tiers"] = loaded.get("set_tiers") if isinstance(loaded.get("set_tiers"), dict) else {}
                    if isinstance(loaded.get("set_stats"), dict):
                        state["set_stats"] = loaded["set_stats"]
                    if isinstance(loaded.get("eta_models"), dict):
                        for mk, mv in loaded["eta_models"].items():
                            if isinstance(mv, dict):
                                base_m = dict(DEFAULT_ETA_MODELS.get(mk, DEFAULT_ETA_MODELS["checklist_and_images"]))
                                base_m.update(mv)
                                state["eta_models"][mk] = base_m
            except Exception:
                pass
        for ep_name in DEFAULT_ENDPOINT_PROFILES:
            if ep_name not in state["endpoints"]:
                state["endpoints"][ep_name] = self._make_default_endpoint(ep_name)
        return state

    def _save_state(self, force: bool = False):
        self._dirty_ops += 1
        if not force and self._dirty_ops < 10:
            return
        self._dirty_ops = 0
        try:
            ensure_directories()
            self._state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_p = self.state_file.with_suffix(".tmp")
            tmp_p.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
            os.replace(str(tmp_p), str(self.state_file))
        except Exception:
            pass

    def _ep(self, endpoint: str) -> dict:
        if endpoint not in self._state["endpoints"]:
            self._state["endpoints"][endpoint] = self._make_default_endpoint(endpoint)
        return self._state["endpoints"][endpoint]

    def _window(self, endpoint: str) -> deque[float]:
        if endpoint not in self._windows:
            self._windows[endpoint] = deque()
        return self._windows[endpoint]

    def _prune_window(self, endpoint: str, now: float) -> deque[float]:
        w = self._window(endpoint)
        cutoff = now - 60.0
        while w and w[0] < cutoff:
            w.popleft()
        return w

    def classify_tcdb_endpoint(self, url: str) -> str:
        """All TCDB HTML & Image traffic shares one unified `tcdb_domain` Cloudflare bucket."""
        return "tcdb_domain"

    def wait_before_request(self, endpoint: str) -> float:
        sleep_total = 0.0
        with self._lock:
            ep = self._ep(endpoint)
            now = time.time()
            w = self._prune_window(endpoint, now)

            delay_s = float(ep.get("current_delay_s", 2.50))
            safe_rpm = max(4.0, float(ep.get("safe_rpm", 23.5)))
            max_in_window = max(3, int(safe_rpm))

            last_ts = self._last_req_ts.get(endpoint, 0.0)
            target_gap = delay_s * random.uniform(0.95, 1.05)
            gap_wait = max(0.0, (last_ts + target_gap) - now)

            win_wait = 0.0
            if len(w) >= max_in_window:
                oldest = w[0]
                win_wait = max(0.0, (oldest + 61.0) - now)

            wait_s = max(gap_wait, win_wait)

        if wait_s > 0.01:
            time.sleep(wait_s)
            sleep_total = wait_s

        with self._lock:
            now2 = time.time()
            w2 = self._prune_window(endpoint, now2)
            w2.append(now2)
            self._last_req_ts[endpoint] = now2
        return sleep_total

    def record_success(self, endpoint: str, elapsed_ms: float = 0.0, status_code: int = 200):
        with self._lock:
            ep = self._ep(endpoint)
            ep["total_requests"] = int(ep.get("total_requests", 0)) + 1
            ep["clean_streak"] = int(ep.get("clean_streak", 0)) + 1
            self._consecutive_429[endpoint] = 0

            if elapsed_ms > 0:
                prev_lat = float(ep.get("ema_latency_ms", 0.0))
                ep["ema_latency_ms"] = round(elapsed_ms if prev_lat <= 0 else (0.85 * prev_lat + 0.15 * elapsed_ms), 1)

            streak = ep["clean_streak"]
            if streak >= 15 and streak % 15 == 0:
                safe_rpm = float(ep.get("safe_rpm", 23.5))
                min_rpm = float(ep.get("min_rpm", 8.0))
                max_rpm = float(ep.get("max_rpm", 25.0))
                last_429_rpm = float(ep.get("last_429_rpm", 0.0))
                cur_delay = float(ep.get("current_delay_s", 2.50))
                min_delay = float(ep.get("min_delay_s", 2.35))

                ceiling = max(min_rpm, min(max_rpm, last_429_rpm - 1.5)) if last_429_rpm > 0 else max_rpm
                near_cliff = last_429_rpm > 0 and safe_rpm >= (ceiling - 1.5)
                rpm_step = 0.20 if near_cliff else 0.75
                delay_factor = 0.99 if near_cliff else 0.96

                new_rpm = min(ceiling, safe_rpm + rpm_step) if ceiling > safe_rpm else min(safe_rpm, ceiling)
                min_delay_for_rpm = 60.0 / max(4.0, new_rpm)
                new_delay = max(min_delay, min_delay_for_rpm, cur_delay * delay_factor)

                ep["safe_rpm"] = round(new_rpm, 2)
                ep["current_delay_s"] = round(new_delay, 3)

            ep["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_state(force=False)

    def record_rate_limit(self, endpoint: str, retry_after_header: Optional[str] = None) -> tuple[float, str]:
        with self._lock:
            ep = self._ep(endpoint)
            now = time.time()
            w = self._prune_window(endpoint, now)
            observed_rpm = max(4.0, float(len(w)))

            ep["total_requests"] = int(ep.get("total_requests", 0)) + 1
            ep["total_429s"] = int(ep.get("total_429s", 0)) + 1
            ep["clean_streak"] = 0
            consec = self._consecutive_429.get(endpoint, 0) + 1
            self._consecutive_429[endpoint] = consec

            prev_429_rpm = float(ep.get("last_429_rpm", 0.0))
            learned_cliff = observed_rpm if prev_429_rpm <= 0 else round(0.65 * prev_429_rpm + 0.35 * observed_rpm, 2)
            ep["last_429_rpm"] = learned_cliff

            min_rpm = float(ep.get("min_rpm", 8.0))
            max_delay = float(ep.get("max_delay_s", 8.0))
            prev_rpm = float(ep.get("safe_rpm", 23.5))
            prev_delay = float(ep.get("current_delay_s", 2.50))

            new_rpm = max(min_rpm, min(prev_rpm * 0.90, learned_cliff - 2.0))
            new_delay = min(max_delay, max(prev_delay * 1.15, (60.0 / new_rpm) * 1.04))
            ep["safe_rpm"] = round(new_rpm, 2)
            ep["current_delay_s"] = round(new_delay, 3)
            ep["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ra_sec = 0.0
            if retry_after_header:
                try:
                    ra_sec = float(str(retry_after_header).strip())
                except Exception:
                    ra_sec = 0.0

            if ra_sec > 0:
                cooldown = min(180.0, max(15.0, ra_sec + 3.0))
            else:
                if w:
                    oldest_age = max(0.0, now - w[0])
                    window_clear = max(25.0, 63.0 - oldest_age)
                else:
                    window_clear = 45.0
                cooldown = min(150.0, window_clear + (20.0 * max(0, consec - 1)))

            if cooldown >= 55.0:
                w.clear()

            self._save_state(force=True)
            summary = (
                f"Learned sweet-spot -> {ep['safe_rpm']:.1f} req/min "
                f"(delay {ep['current_delay_s']:.2f}s | cliff ~{learned_cliff:.1f} rpm | 429s={ep['total_429s']})"
            )
            return round(cooldown, 1), summary

    def record_cf_challenge(self, endpoint: str):
        with self._lock:
            ep = self._ep(endpoint)
            ep["total_403s"] = int(ep.get("total_403s", 0)) + 1
            ep["clean_streak"] = 0
            ep["current_delay_s"] = round(min(float(ep.get("max_delay_s", 8.0)), float(ep.get("current_delay_s", 2.5)) * 1.10), 3)
            ep["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_state(force=True)

    # --------------------------------------------------------------------------
    # PER-SET CARD COUNT, IMAGE PROGRESS & HISTORICAL RUN TELEMETRY CACHE
    # --------------------------------------------------------------------------
    def get_set_stats(self, set_key: str) -> dict:
        sk = str(set_key or "").strip()
        if not sk:
            return {}
        with self._lock:
            return dict(self._state.setdefault("set_stats", {}).get(sk, {}))

    def update_set_stats(
        self,
        set_key: str,
        set_name: str = "",
        total_cards: Optional[int] = None,
        base_cards: Optional[int] = None,
        total_subsets: Optional[int] = None,
        imaged_cards_on_tcdb: Optional[int] = None,
        fronts_downloaded: Optional[int] = None,
        backs_downloaded: Optional[int] = None,
        subset_card_counts: Optional[dict[str, int]] = None,
        force_save: bool = True,
    ) -> dict:
        sk = str(set_key or "").strip()
        if not sk:
            return {}
        with self._lock:
            all_sets = self._state.setdefault("set_stats", {})
            rec = all_sets.setdefault(sk, {
                "set_name": set_name or sk.replace("_", " "),
                "total_cards": 0,
                "base_cards": 0,
                "total_subsets": 0,
                "imaged_cards_on_tcdb": 0,
                "fronts_downloaded": 0,
                "backs_downloaded": 0,
                "subset_card_counts": {},
                "last_runs": {},
                "updated_at": "",
            })
            if set_name:
                rec["set_name"] = set_name
            if total_cards is not None and int(total_cards) >= 0:
                rec["total_cards"] = int(total_cards)
            if base_cards is not None and int(base_cards) >= 0:
                rec["base_cards"] = int(base_cards)
            if total_subsets is not None and int(total_subsets) >= 0:
                rec["total_subsets"] = int(total_subsets)
            if imaged_cards_on_tcdb is not None and int(imaged_cards_on_tcdb) >= 0:
                rec["imaged_cards_on_tcdb"] = int(imaged_cards_on_tcdb)
            if fronts_downloaded is not None and int(fronts_downloaded) >= 0:
                rec["fronts_downloaded"] = int(fronts_downloaded)
            if backs_downloaded is not None and int(backs_downloaded) >= 0:
                rec["backs_downloaded"] = int(backs_downloaded)
            if isinstance(subset_card_counts, dict) and subset_card_counts:
                existing_sc = rec.setdefault("subset_card_counts", {})
                for sub_k, cnt_v in subset_card_counts.items():
                    if int(cnt_v or 0) > 0:
                        existing_sc[str(sub_k)] = int(cnt_v)
            rec["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_state(force=force_save)
            return dict(rec)

    def record_set_run_timing(
        self,
        set_key: str,
        mode_key: str,
        duration_sec: float,
        cards_processed: int,
        images_downloaded: int = 0,
        images_skipped: int = 0,
        set_name: str = "",
    ):
        """Records full per-set run duration and speed into `set_stats[set_key]['last_runs'][mode_key]`."""
        sk = str(set_key or "").strip()
        mk = str(mode_key or "checklist_and_images").strip()
        dur = max(0.1, float(duration_sec or 0.0))
        cards_p = max(0, int(cards_processed or 0))
        if not sk or cards_p <= 0:
            return
        with self._lock:
            all_sets = self._state.setdefault("set_stats", {})
            rec = all_sets.setdefault(sk, {
                "set_name": set_name or sk.replace("_", " "),
                "total_cards": cards_p,
                "base_cards": 0,
                "total_subsets": 0,
                "imaged_cards_on_tcdb": 0,
                "fronts_downloaded": 0,
                "backs_downloaded": 0,
                "subset_card_counts": {},
                "last_runs": {},
                "updated_at": "",
            })
            if set_name:
                rec["set_name"] = set_name
            runs = rec.setdefault("last_runs", {})
            runs[mk] = {
                "duration_sec": round(dur, 1),
                "cards_processed": cards_p,
                "images_downloaded": int(images_downloaded or 0),
                "images_skipped": int(images_skipped or 0),
                "cards_per_sec": round(cards_p / dur, 3),
                "sec_per_card": round(dur / cards_p, 4),
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            rec["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Also update global EMA model for this mode
            models = self._state.setdefault("eta_models", {})
            m = models.setdefault(mk, dict(DEFAULT_ETA_MODELS.get(mk, DEFAULT_ETA_MODELS["checklist_and_images"])))
            obs_spc = dur / float(cards_p)
            c_cnt = int(m.get("card_samples", 0))
            alpha = 0.35 if c_cnt < 250 else 0.12
            prev_spc = float(m.get("ema_sec_per_card", obs_spc))
            m["ema_sec_per_card"] = round((1.0 - alpha) * prev_spc + alpha * obs_spc, 4)
            m["card_samples"] = c_cnt + cards_p
            self._save_state(force=True)

    # --------------------------------------------------------------------------
    # CROSS-RUN LEARNING CARD-BASED TIER-1 & TIER-2 ETA ENGINE
    # --------------------------------------------------------------------------
    def get_eta_priors(self, mode_key: str) -> dict:
        mk = str(mode_key or "checklist_and_images")
        with self._lock:
            models = self._state.setdefault("eta_models", {})
            if mk not in models:
                models[mk] = dict(DEFAULT_ETA_MODELS.get(mk, DEFAULT_ETA_MODELS["checklist_and_images"]))
            return dict(models[mk])

    def record_subset_duration(
        self,
        mode_key: str,
        duration_sec: float,
        card_count: int = 0,
        downloaded_cards: int = 0,
        skipped_cards: int = 0,
    ):
        dur = max(0.05, float(duration_sec or 0.0))
        mk = str(mode_key or "checklist_and_images")
        with self._lock:
            models = self._state.setdefault("eta_models", {})
            m = models.setdefault(mk, dict(DEFAULT_ETA_MODELS.get(mk, DEFAULT_ETA_MODELS["checklist_and_images"])))
            s_cnt = int(m.get("subset_samples", 0))
            alpha_s = 0.35 if s_cnt < 10 else 0.12
            prev_s = float(m.get("ema_sec_per_subset", 25.0))
            m["ema_sec_per_subset"] = round((1.0 - alpha_s) * prev_s + alpha_s * dur, 3)
            m["subset_samples"] = s_cnt + 1

            if card_count > 0:
                obs_spc = dur / float(card_count)
                c_cnt = int(m.get("card_samples", 0))
                alpha_c = 0.30 if c_cnt < 100 else 0.10
                prev_c = float(m.get("ema_sec_per_card", 0.85))
                m["ema_sec_per_card"] = round((1.0 - alpha_c) * prev_c + alpha_c * obs_spc, 4)
                m["card_samples"] = c_cnt + int(card_count)

                # Separate download vs skip card latency priors for accurate mixed-skip runs
                if downloaded_cards > 0 and skipped_cards == 0:
                    prev_dl = float(m.get("ema_sec_per_dl_card", 4.6))
                    m["ema_sec_per_dl_card"] = round(0.80 * prev_dl + 0.20 * (dur / float(downloaded_cards)), 4)
                elif skipped_cards > 0 and downloaded_cards == 0:
                    prev_sk = float(m.get("ema_sec_per_skip_card", 0.03))
                    m["ema_sec_per_skip_card"] = round(0.80 * prev_sk + 0.20 * (dur / float(skipped_cards)), 4)

            self._save_state(force=True)

    def estimate_card_based_etas(
        self,
        mode_key: str,
        completed_cards: int,
        total_cards: int,
        run_elapsed_sec: float,
        sub_current: int,
        sub_total: int,
        sub_elapsed_sec: float,
        active_set_key: str = "",
        est_remaining_dl_cards: Optional[int] = None,
    ) -> tuple[Optional[float], Optional[float], float]:
        """
        Computes accurate card-count-driven Tier-1 Overall ETA, Tier-2 Active Parallel ETA,
        and live `cards_per_sec` speed:
          - Smoothly blends live observed `sec/card` with historical learned `sec/card`
            (preferring the set's own `last_runs[mode_key]` prior when available).
          - When `est_remaining_dl_cards` is known for download/combo jobs, weights the cold-start
            prior by `(remaining_dl * ema_sec_per_dl_card + remaining_skip * ema_sec_per_skip_card)`.
        """
        priors = self.get_eta_priors(mode_key)
        ema_spc = max(0.005, float(priors.get("ema_sec_per_card", 0.50)))
        ema_dl = max(0.05, float(priors.get("ema_sec_per_dl_card", 4.60)))
        ema_skip = max(0.002, float(priors.get("ema_sec_per_skip_card", 0.03)))

        # Incorporate per-set historical run speed prior if available
        if active_set_key:
            s_stats = self.get_set_stats(active_set_key)
            last_r = (s_stats.get("last_runs") or {}).get(mode_key)
            if isinstance(last_r, dict) and float(last_r.get("sec_per_card", 0) or 0) > 0:
                ema_spc = 0.55 * float(last_r["sec_per_card"]) + 0.45 * ema_spc

        cards_per_sec = 0.0
        if completed_cards > 0 and run_elapsed_sec > 0.25:
            cards_per_sec = round(float(completed_cards) / float(run_elapsed_sec), 3)

        # Tier 2: Active Subset / Parallel ETA (card-based)
        sub_eta = None
        if sub_total > 0:
            rem_sub_cards = max(0, int(sub_total) - int(sub_current))
            if rem_sub_cards == 0:
                sub_eta = 0.0
            else:
                if sub_current > 0 and sub_elapsed_sec > 0.25:
                    live_sub_spc = float(sub_elapsed_sec) / float(sub_current)
                    w_sub = min(0.90, float(sub_current) / (float(sub_current) + 12.0))
                    blended_sub_spc = w_sub * live_sub_spc + (1.0 - w_sub) * ema_spc
                elif completed_cards > 0 and run_elapsed_sec > 0.5:
                    blended_sub_spc = float(run_elapsed_sec) / float(completed_cards)
                else:
                    blended_sub_spc = ema_spc
                sub_eta = round(rem_sub_cards * blended_sub_spc, 1)

        # Tier 1: Overall Run ETA across all queued sets (card-based)
        overall_eta = None
        if total_cards > 0:
            rem_total_cards = max(0, int(total_cards) - int(completed_cards))
            if rem_total_cards == 0:
                overall_eta = 0.0
            else:
                # Build cold-start prior ETA (aware of already-downloaded skips when known)
                if est_remaining_dl_cards is not None and mode_key in ("images_only", "checklist_and_images"):
                    rem_dl = min(rem_total_cards, max(0, int(est_remaining_dl_cards)))
                    rem_sk = max(0, rem_total_cards - rem_dl)
                    prior_spc = ((rem_dl * ema_dl) + (rem_sk * ema_skip)) / float(max(1, rem_total_cards))
                else:
                    prior_spc = ema_spc

                if completed_cards > 0 and run_elapsed_sec > 0.5:
                    live_spc = float(run_elapsed_sec) / float(completed_cards)
                    # Converges rapidly to live pace as more cards complete (50% weight at 30 cards, 85% at 170 cards)
                    w_live = min(0.92, float(completed_cards) / (float(completed_cards) + 30.0))
                    blended_spc = w_live * live_spc + (1.0 - w_live) * prior_spc
                else:
                    blended_spc = prior_spc

                overall_eta = round(rem_total_cards * blended_spc, 1)
                if sub_eta is not None and overall_eta < sub_eta:
                    overall_eta = sub_eta

        return overall_eta, sub_eta, cards_per_sec

    def estimate_learning_etas(
        self,
        mode_key: str,
        completed_subsets: int,
        total_subsets: int,
        run_elapsed_sec: float,
        sub_current: int,
        sub_total: int,
        sub_elapsed_sec: float,
    ) -> tuple[Optional[float], Optional[float]]:
        """Backwards-compatible subset-based fallback ETA estimator."""
        priors = self.get_eta_priors(mode_key)
        ema_spc = max(0.02, float(priors.get("ema_sec_per_card", 1.5)))
        ema_sps = max(0.5, float(priors.get("ema_sec_per_subset", 25.0)))

        sub_eta = None
        if sub_total > 0:
            rem_cards = max(0, int(sub_total) - int(sub_current))
            if rem_cards == 0:
                sub_eta = 0.0
            else:
                if sub_current > 0 and sub_elapsed_sec > 0.25:
                    live_spc = float(sub_elapsed_sec) / float(sub_current)
                    w_c = min(0.88, float(sub_current) / (float(sub_current) + 8.0))
                    blended_spc = w_c * live_spc + (1.0 - w_c) * ema_spc
                else:
                    blended_spc = ema_spc
                sub_eta = round(rem_cards * blended_spc, 1)

        overall_eta = None
        if total_subsets > 0:
            active_in_progress = 1 if (sub_total > 0 and sub_current < sub_total) else 0
            rem_future_subsets = max(0, int(total_subsets) - int(completed_subsets) - active_in_progress)
            if completed_subsets > 0 and run_elapsed_sec > 1.0:
                live_sps = max(0.2, (float(run_elapsed_sec) - float(sub_elapsed_sec or 0.0)) / float(completed_subsets))
                w_s = min(0.85, float(completed_subsets) / (float(completed_subsets) + 5.0))
                blended_sps = w_s * live_sps + (1.0 - w_s) * ema_sps
            else:
                blended_sps = ema_sps
            overall_eta = round((sub_eta or 0.0) + (rem_future_subsets * blended_sps), 1)

        return overall_eta, sub_eta

    # --------------------------------------------------------------------------
    # THUMBNAIL-DIRECT & FRONT-TIER-AWARE PROBE SELECTOR
    # --------------------------------------------------------------------------
    def should_probe_rep_first(
        self,
        set_key: str,
        thumb_url: str = "",
        force_rep_first: bool = False,
        preferred_tier: str = "",
    ) -> bool:
        if force_rep_first:
            return True
        clean_thumb = str(thumb_url or "").strip()
        if clean_thumb:
            return "rep" in clean_thumb.lower()
        pref_up = str(preferred_tier or "").strip().upper()
        if pref_up in ("R", "S"):
            return pref_up == "R"
        s_k = str(set_key or "default").strip()
        with self._lock:
            st = self._state["set_tiers"].get(s_k)
            if not st:
                return False
            r_hits = int(st.get("r_hits", 0))
            s_hits = int(st.get("s_hits", 0))
            tot = r_hits + s_hits
            if tot < 10:
                return False
            return (r_hits / float(tot)) >= 0.35

    def record_tier_outcome(self, set_key: str, quality_tier: str, skipped_rep_probe: bool = False):
        if not set_key or quality_tier not in ("R", "S"):
            return
        s_k = str(set_key).strip()
        with self._lock:
            st = self._state["set_tiers"].setdefault(
                s_k, {"r_hits": 0, "s_hits": 0, "saved_404_probes": 0}
            )
            if quality_tier == "R":
                st["r_hits"] = int(st.get("r_hits", 0)) + 1
            else:
                st["s_hits"] = int(st.get("s_hits", 0)) + 1
                if skipped_rep_probe:
                    st["saved_404_probes"] = int(st.get("saved_404_probes", 0)) + 1
            self._save_state(force=False)

    def reset_all(self) -> dict:
        with self._lock:
            self._windows.clear()
            self._last_req_ts.clear()
            self._consecutive_429.clear()
            self._state = {
                "endpoints": {k: self._make_default_endpoint(k) for k in DEFAULT_ENDPOINT_PROFILES},
                "set_tiers": {},
                "eta_models": {k: dict(v) for k, v in DEFAULT_ETA_MODELS.items()},
                "set_stats": {},
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_state(force=True)
        return self.get_dashboard_summary()

    def get_dashboard_summary(self) -> dict:
        with self._lock:
            fresh = self._load_state()
            self._state = fresh
            eps = []
            for name, d in sorted(fresh.get("endpoints", {}).items()):
                if name in ("tcdb_html", "tcdb_images"):
                    continue
                eps.append({
                    "endpoint": name,
                    "safe_rpm": d.get("safe_rpm", 0),
                    "current_delay_s": d.get("current_delay_s", 0),
                    "last_429_rpm": d.get("last_429_rpm", 0),
                    "clean_streak": d.get("clean_streak", 0),
                    "total_requests": d.get("total_requests", 0),
                    "total_429s": d.get("total_429s", 0),
                    "ema_latency_ms": d.get("ema_latency_ms", 0),
                    "last_updated": d.get("last_updated", ""),
                })
            set_tiers = fresh.get("set_tiers", {})
            total_saved = sum(int(v.get("saved_404_probes", 0)) for v in set_tiers.values() if isinstance(v, dict))

            set_stats_list = []
            for sk, sv in sorted((fresh.get("set_stats") or {}).items()):
                if not isinstance(sv, dict):
                    continue
                runs = sv.get("last_runs") or {}
                set_stats_list.append({
                    "set_key": sk,
                    "set_name": sv.get("set_name") or sk.replace("_", " "),
                    "total_cards": int(sv.get("total_cards", 0) or 0),
                    "base_cards": int(sv.get("base_cards", 0) or 0),
                    "total_subsets": int(sv.get("total_subsets", 0) or 0),
                    "imaged_cards_on_tcdb": int(sv.get("imaged_cards_on_tcdb", 0) or 0),
                    "fronts_downloaded": int(sv.get("fronts_downloaded", 0) or 0),
                    "backs_downloaded": int(sv.get("backs_downloaded", 0) or 0),
                    "last_runs": runs,
                    "updated_at": sv.get("updated_at", ""),
                })

            return {
                "stateFile": str(self.state_file),
                "updatedAt": fresh.get("updated_at", ""),
                "totalSaved404Probes": total_saved,
                "endpoints": eps,
                "etaModels": fresh.get("eta_models", {}),
                "setStats": set_stats_list,
                "setTiersCount": len(set_tiers),
            }


_SINGLETON_LEARNER: Optional[AdaptiveRateLearner] = None


def get_rate_learner() -> AdaptiveRateLearner:
    global _SINGLETON_LEARNER
    if _SINGLETON_LEARNER is None:
        _SINGLETON_LEARNER = AdaptiveRateLearner()
    return _SINGLETON_LEARNER
