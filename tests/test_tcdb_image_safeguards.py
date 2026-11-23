from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


class _MockResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.content = content
        self.text = text
        self.headers = headers or {"Content-Type": "image/jpeg"}


class _MockRateLearner:
    def classify_tcdb_endpoint(self, url: str) -> str:
        return "tcdb_domain"

    def wait_before_request(self, ep_key: str) -> float:
        return 0.0

    def record_success(self, ep_key: str, elapsed_ms: float = 0.0, status_code: int = 200):
        pass

    def record_cf_challenge(self, ep_key: str):
        pass

    def record_rate_limit(self, ep_key: str, retry_after_header=None):
        return (0.0, "mocked")

    def should_probe_rep_first(self, set_key: str = "", thumb_url: str = "", force_rep_first: bool = False, preferred_tier: str = "") -> bool:
        if force_rep_first:
            return True
        if thumb_url and "rep" in thumb_url.lower():
            return True
        if str(preferred_tier).upper() == "R":
            return True
        return False

    def record_tier_outcome(self, set_key: str = "", quality_tier: str = "", skipped_rep_probe: bool = False):
        pass

    def record_subset_duration(self, *args, **kwargs):
        pass

    def record_set_run_timing(self, *args, **kwargs):
        pass

    def get_set_stats(self, key: str) -> dict:
        return {}


class _ScriptedSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[str] = []
        self.cookies = {}
        self.headers = {}

    def get(self, url: str, headers=None, timeout=30):
        self.calls.append(url)
        res = self.handler(url, len(self.calls))
        if isinstance(res, BaseException):
            raise res
        return res


class TcdbImageSafeguardsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cache_dir = self.root / "Cache"
        self.catalogs_dir = self.cache_dir / "Catalogs"
        self.checkpoints_dir = self.cache_dir / "Checkpoints"
        self.ref_dir = self.root / "SetLibrary" / "Reference_Library"
        self.dl_dir = self.root / "downloaded_files"
        for d in (self.cache_dir, self.catalogs_dir, self.checkpoints_dir, self.ref_dir, self.dl_dir):
            d.mkdir(parents=True, exist_ok=True)

        os.environ["CARDS_BASE_DIR"] = str(self.root)
        os.environ["TABULAS_SET_LIBRARY_DIR"] = str(self.root / "SetLibrary")
        os.environ["TABULAS_ARCHIVE_DIR"] = str(self.root / "Archive")

        import Core.scraper_engine as se

        self.se = se
        self.se.set_stop_check_callback(None)
        self._patches = [
            mock.patch.object(self.se, "CACHE_CATALOGS_DIR", self.catalogs_dir),
            mock.patch.object(self.se, "CACHE_CHECKPOINTS_DIR", self.checkpoints_dir),
            mock.patch.object(self.se, "REFERENCE_TEMPLATES_DIR", self.ref_dir),
            mock.patch.object(self.se, "DEAD_BACKS_CACHE_FILE", self.cache_dir / "dead_backs.json"),
            mock.patch.object(self.se, "DEAD_FRONTS_CACHE_FILE", self.cache_dir / "dead_fronts.json"),
            mock.patch.object(self.se, "TRACKING_FILE", self.root / "tracked_sets.json"),
            mock.patch.object(self.se, "DOWNLOADED_FILES_DIR", self.dl_dir),
            mock.patch.object(self.se, "get_rate_learner", return_value=_MockRateLearner()),
            mock.patch.object(self.se, "sync_set_library_download_status", lambda **_kw: None),
            mock.patch.object(self.se, "_get_directory_image_pct", return_value=100.0),
            mock.patch.object(self.se, "cleanup_orphaned_drivers", lambda: None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        self.se.set_stop_check_callback(None)
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def _seed_single_set_catalog(self, folder: str, cards: dict):
        set_url = f"https://www.tcdb.com/ViewSet.cfm/sid/100/{folder}"
        self.se.save_all_tracked_sets({set_url: {"folder_name": folder, "priority": 1}})
        self.se.save_catalog(folder, {"Base": cards})
        return {set_url: folder}

    def _make_card_entry(self, cid: str, cnum: str, player: str):
        return {
            "cid": cid,
            "card_number": cnum,
            "player": player,
            "team": "Team",
            "front_file": f"{cid}_F.jpg",
            "back_file": f"{cid}_B.jpg",
            "url_rep_front": f"https://www.tcdb.com/Images/Large/2024/{cid}RepFr.jpg",
            "url_std_front": f"https://www.tcdb.com/Images/Large/2024/{cid}Fr.jpg",
            "url_rep_back": "",
            "url_std_back": "",
            "front_tier_hint": "S",
            "referer": "https://www.tcdb.com/Checklist.cfm/sid/100",
        }

    # ------------------------------------------------------------------
    # 1. Strict 404-Only Missing Cache
    # ------------------------------------------------------------------
    def test_non_404_errors_never_write_to_404_cache(self):
        """HTTP 403, 429, 503, and network errors must NEVER write to dead_fronts/dead_backs."""
        set_dir = self.ref_dir / "2024_Non404"
        set_dir.mkdir(parents=True, exist_ok=True)
        dest = set_dir / "card_F.jpg"

        for label, exc_or_resp in [
            ("403", _MockResponse(403, text="Forbidden")),
            ("429", _MockResponse(429, text="Too Many Requests")),
            ("503", _MockResponse(503, text="Service Unavailable")),
            ("timeout", TimeoutError("read timed out")),
        ]:
            sess = _ScriptedSession(lambda _u, _n, r=exc_or_resp: r)
            cb = self.se.CloudflareImageCircuitBreaker(
                cooldown_schedule=(0.01,),
                stop_poll_interval=0.01,
                sleep_fn=lambda _s: None,
                reauth_fn=lambda **_kw: sess,
            )
            outcome: dict = {}
            with mock.patch.object(self.se.time, "sleep", lambda _s: None):
                if label == "403":
                    with self.assertRaises(self.se.CloudflareEdgeBlockPaused):
                        self.se._download_single_template_side(
                            sess,
                            "https://www.tcdb.com/Images/Large/2024/1RepFr.jpg",
                            "https://www.tcdb.com/Images/Large/2024/1Fr.jpg",
                            "https://www.tcdb.com/Checklist.cfm/sid/100",
                            dest,
                            preferred_tier="S",
                            outcome_out=outcome,
                            circuit_breaker=cb,
                        )
                else:
                    if label == "429":
                        with self.assertRaises(self.se.CloudflareEdgeBlockPaused):
                            self.se._download_single_template_side(
                                sess,
                                "https://www.tcdb.com/Images/Large/2024/1RepFr.jpg",
                                "https://www.tcdb.com/Images/Large/2024/1Fr.jpg",
                                "https://www.tcdb.com/Checklist.cfm/sid/100",
                                dest,
                                preferred_tier="S",
                                outcome_out=outcome,
                                circuit_breaker=cb,
                            )
                    else:
                        res = self.se._download_single_template_side(
                            sess,
                            "https://www.tcdb.com/Images/Large/2024/1RepFr.jpg",
                            "https://www.tcdb.com/Images/Large/2024/1Fr.jpg",
                            "https://www.tcdb.com/Checklist.cfm/sid/100",
                            dest,
                            preferred_tier="S",
                            outcome_out=outcome,
                            circuit_breaker=cb,
                        )
                        self.assertIsNone(res)
                        self.assertFalse(outcome.get("confirmed_404"), f"{label} must not set confirmed_404")

        self.assertEqual(self.se.load_dead_fronts_cache(), {})
        self.assertEqual(self.se.load_dead_backs_cache(), {})

    def test_literal_404_caches_normally(self):
        """Literal HTTP 404 on all probed tiers sets confirmed_404=True and writes to dead_fronts."""
        queue = self._seed_single_set_catalog(
            "2024_Literal404",
            {"1001": self._make_card_entry("1001", "1", "Missing Card")},
        )
        sess = _ScriptedSession(lambda _u, _n: _MockResponse(404, text="Not Found"))
        logs: list[str] = []
        self.se.set_log_callback(logs.append)
        try:
            with mock.patch.object(self.se, "connect_session", return_value=sess):
                self.se.mode_download_all_catalog_images(
                    target_queue=queue,
                    card_delay_range=(0.0, 0.0),
                )
        finally:
            self.se.set_log_callback(None)

        dead_fronts = self.se.load_dead_fronts_cache()
        self.assertIn("1001", dead_fronts)
        self.assertTrue(any("Miss(404->Cached)" in line for line in logs))

    # ------------------------------------------------------------------
    # 2. 403 Circuit Breaker & Exponential Cooldown
    # ------------------------------------------------------------------
    def test_403_circuit_breaker_trips_once_and_exponential_cooldown_pauses(self):
        """
        Consecutive 403s allow at most 1 re-auth attempt, then sleep 15m -> 30m -> 60m
        in <=2s increments, and cleanly pause without caching 403s as 404s.
        """
        cards = {str(100 + i): self._make_card_entry(str(100 + i), str(i), f"P{i}") for i in range(1, 5)}
        queue = self._seed_single_set_catalog("2024_CF403", cards)
        sess = _ScriptedSession(lambda _u, _n: _MockResponse(403, text="Cloudflare Edge Block"))

        sleep_calls: list[float] = []
        reauth_calls: list[str] = []
        progress_events: list[dict] = []

        cb = self.se.CloudflareImageCircuitBreaker(
            cooldown_schedule=(900.0, 1800.0, 3600.0),
            stop_poll_interval=2.0,
            sleep_fn=sleep_calls.append,
            reauth_fn=lambda existing_session=None, target_domain="": (reauth_calls.append(target_domain) or existing_session),
        )
        self.se.set_progress_callback(progress_events.append)
        try:
            with mock.patch.object(self.se, "connect_session", return_value=sess):
                with self.assertRaises(self.se.CloudflareEdgeBlockPaused) as ctx:
                    self.se.mode_download_all_catalog_images(
                        target_queue=queue,
                        card_delay_range=(0.0, 0.0),
                        circuit_breaker=cb,
                    )
        finally:
            self.se.set_progress_callback(None)

        self.assertIn("Cloudflare /Images/ rate-limit active", str(ctx.exception))
        # At most 1 stealth-browser re-auth attempt in the burst!
        self.assertEqual(len(reauth_calls), 1)
        # All sleep chunks must respect <= 2.0s stop-polling interval
        self.assertTrue(all(s <= 2.0 for s in sleep_calls))
        # Total sleep = 3s post-reauth + 900s + 1800s + 3600s = 6303s
        self.assertAlmostEqual(sum(sleep_calls), 3.0 + 900.0 + 1800.0 + 3600.0, places=2)
        self.assertEqual(cb.cooldown_stage, 3)
        self.assertTrue(cb.tripped_pause)
        # Progress UI received the clean pause status message
        self.assertTrue(any("Cloudflare /Images/ rate-limit active" in str(ev.get("current_item", "")) for ev in progress_events))
        # Zero 403 cards written to dead_fronts cache
        self.assertEqual(self.se.load_dead_fronts_cache(), {})

    def test_circuit_breaker_stop_signal_interrupts_cooldown_quickly(self):
        """Stop signal interrupts the 15m cooldown sleep on the next 2s poll tick."""
        ticks = {"n": 0}

        def _stop_after_5():
            ticks["n"] += 1
            return ticks["n"] >= 5

        sleep_calls: list[float] = []
        cb = self.se.CloudflareImageCircuitBreaker(
            cooldown_schedule=(900.0, 1800.0, 3600.0),
            stop_poll_interval=2.0,
            stop_check=_stop_after_5,
            sleep_fn=sleep_calls.append,
            reauth_fn=lambda existing_session=None, target_domain="": existing_session,
        )
        sess = _ScriptedSession(lambda _u, _n: _MockResponse(403))
        # 1st call: single re-auth (3s = 2 + 1)
        self.assertEqual(cb.handle_block(403, "https://www.tcdb.com/Images/Large/1Fr.jpg", sess), "retry")
        # 2nd call: enters 900s cooldown, stops immediately once stop_check returns True
        with self.assertRaises(self.se.CloudflareEdgeBlockPaused):
            cb.handle_block(403, "https://www.tcdb.com/Images/Large/1Fr.jpg", sess)
        self.assertLess(sum(sleep_calls), 10.0)

    def test_circuit_breaker_resets_after_200_recovery(self):
        """A 200 response after cooldown #1 resets consecutive block & cooldown counters."""
        jpg_bytes = b"\xff\xd8\xff\xe0" + b"A" * 1024
        state = {"n": 0}

        def _handler(_url, _call_idx):
            state["n"] += 1
            if state["n"] <= 2:
                return _MockResponse(403, text="Forbidden")
            return _MockResponse(200, content=jpg_bytes)

        sess = _ScriptedSession(_handler)
        cb = self.se.CloudflareImageCircuitBreaker(
            cooldown_schedule=(900.0, 1800.0, 3600.0),
            stop_poll_interval=2.0,
            sleep_fn=lambda _s: None,
            reauth_fn=lambda existing_session=None, target_domain="": existing_session,
        )
        queue = self._seed_single_set_catalog(
            "2024_Recover",
            {"2001": self._make_card_entry("2001", "1", "Recovered Card")},
        )
        with mock.patch.object(self.se, "connect_session", return_value=sess):
            self.se.mode_download_all_catalog_images(
                target_queue=queue,
                card_delay_range=(0.0, 0.0),
                circuit_breaker=cb,
            )
        self.assertEqual(cb.total_reauths, 1)
        self.assertEqual(cb.total_cooldowns, 1)
        self.assertEqual(cb.cooldown_stage, 0)
        self.assertEqual(cb.consecutive_blocks, 0)

    # ------------------------------------------------------------------
    # 3. Human-Like Pacing, Breathers & max_cards_per_run
    # ------------------------------------------------------------------
    def test_human_pacing_jitter_breather_and_max_cards_per_run(self):
        """Verifies 3.5-7.5s card jitter, periodic breather, and max_cards_per_run cap."""
        jpg_bytes = b"\xff\xd8\xff\xe0" + b"B" * 1024
        cards = {str(300 + i): self._make_card_entry(str(300 + i), str(i), f"P{i}") for i in range(1, 6)}
        queue = self._seed_single_set_catalog("2024_Pacing", cards)
        sess = _ScriptedSession(lambda _u, _n: _MockResponse(200, content=jpg_bytes))

        sleep_calls: list[float] = []
        cb = self.se.CloudflareImageCircuitBreaker(
            stop_poll_interval=1000.0,
            sleep_fn=sleep_calls.append,
        )
        with mock.patch.object(self.se, "connect_session", return_value=sess):
            self.se.mode_download_all_catalog_images(
                target_queue=queue,
                max_cards_per_run=4,
                card_delay_range=(3.5, 7.5),
                breather_every_cards=2,
                breather_duration_range=(180.0, 300.0),
                circuit_breaker=cb,
            )

        # Cap = 4 cards out of 5 queued
        self.assertEqual(len(sess.calls), 4)
        # Card 2 triggers breather (180..300s), Card 3 has jitter skipped because breather just ran,
        # Card 2 and Card 4 had jitter before them, and Card 4 hits max_cards_per_run cap before breather.
        breathers = [s for s in sleep_calls if 180.0 <= s <= 300.0]
        jitters = [s for s in sleep_calls if 3.5 <= s <= 7.5]
        self.assertEqual(len(breathers), 1)
        self.assertEqual(len(jitters), 2)

    # ------------------------------------------------------------------
    # 4. Lock-File Hygiene
    # ------------------------------------------------------------------
    def test_lock_file_hygiene_removes_stale_lock_and_cleans_on_sb_error(self):
        """cleanup_stale_driver_locks removes driver_fixing.lock and connect_session cleans up on SB crash."""
        lock_file = self.dl_dir / "driver_fixing.lock"
        lock_file.write_text("stale", encoding="utf-8")
        self.assertTrue(lock_file.exists())

        removed = self.se.cleanup_stale_driver_locks()
        self.assertFalse(lock_file.exists())
        self.assertTrue(any(p.name == "driver_fixing.lock" for p in removed))

        cleanup_calls = {"n": 0}

        def _fake_cleanup():
            cleanup_calls["n"] += 1

        class _BoomSB:
            def __init__(self, **_kw):
                pass

            def __enter__(self):
                raise RuntimeError("driver_fixing.lock crash")

            def __exit__(self, *args):
                return False

        with mock.patch.object(self.se, "SB", _BoomSB), \
             mock.patch.object(self.se, "cleanup_orphaned_drivers", _fake_cleanup), \
             mock.patch.object(self.se.time, "sleep", lambda _s: None):
            with self.assertRaises(self.se.StealthBrowserError):
                self.se.connect_session(max_attempts=2)

        # 2 attempts * (1 pre-launch cleanup + 1 except-block cleanup) = 4
        self.assertEqual(cleanup_calls["n"], 4)


if __name__ == "__main__":
    unittest.main()
