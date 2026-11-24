from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _MockResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        content: bytes = b"",
        url: str = "",
        headers: dict | None = None,
    ):
        self.status_code = status_code
        self.text = text
        self.content = content if content else text.encode("utf-8")
        self.url = url
        default_ct = "image/jpeg" if content else "text/html; charset=utf-8"
        self.headers = headers if headers is not None else {"Content-Type": default_ct}


class _StrictMockSession:
    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[str] = []
        self.cookies = {"cf_clearance": "test_clearance_token"}
        self.headers = {"User-Agent": "TestUA/1.0"}

    def get(self, url: str, headers=None, timeout=30):
        import Core.scraper_engine as se

        self.calls.append(url)
        if url not in self.routes:
            raise se.StealthBrowserError(f"Unexpected HTTP GET to {url}")
        val = self.routes[url]
        if callable(val):
            val = val(url)
        if isinstance(val, BaseException):
            raise val
        return val


def _make_checklist_html(rows_spec: list[dict]) -> str:
    trs = []
    for r in rows_spec:
        cid = r["cid"]
        cnum = r["cnum"]
        plr = r["player"]
        team = r.get("team", "Los Angeles Dodgers")
        trs.append(
            f"<tr>"
            f"<td></td>"
            f'<td><a href="/ViewCard.cfm/sid/100/cid/{cid}/card-{cnum}">{cnum}</a></td>'
            f'<td><a href="/Person.cfm/pid/{cid}">{plr}</a></td>'
            f'<td><a href="/Team.cfm/tid/1">{team}</a></td>'
            f"</tr>"
        )
    return f"<html><body><table>{''.join(trs)}</table></body></html>"


def _make_inserts_html(inserts: list[tuple[str, str, int]]) -> str:
    trs = []
    for sid, name, cnt in inserts:
        slug = name.replace(" ", "-")
        trs.append(f'<tr><td><a href="/Checklist.cfm/sid/{sid}/{slug}">{name}</a></td><td>{cnt} cards</td></tr>')
    return f"<html><body><table>{''.join(trs)}</table></body></html>"


class ScraperResilienceAndPauseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.env_patch = mock.patch.dict(
            os.environ,
            {
                "CARDS_BASE_DIR": str(self.root),
                "TABULAS_SET_LIBRARY_DIR": str(self.root / "SetLibrary"),
                "TABULAS_ARCHIVE_DIR": str(self.root / "Archive"),
            },
        )
        self.env_patch.start()

        import Core.config as cfg
        import Core.rate_learner as rl
        import Core.scraper_engine as se
        import cli

        self.cfg = cfg
        self.rl = rl
        self.se = se
        self.cli = cli

        self.set_checklists_dir = self.root / "Data" / "Checklists_and_Resources" / "Set_Checklists"
        self.master_csv = self.root / "Data" / "Checklists_and_Resources" / "Master_Checklist.csv"
        self.checkpoints_dir = self.root / "Cache" / "Checklists" / "Checkpoints"
        self.catalogs_dir = self.root / "Cache" / "Library" / "Catalogs"
        self.ref_dir = self.root / "SetLibrary" / "Reference_Library"
        self.logs_dir = self.root / "Logs"
        self.learner_file = self.logs_dir / "adaptive_rate_learner.json"

        for d in (
            self.set_checklists_dir,
            self.checkpoints_dir,
            self.catalogs_dir,
            self.ref_dir,
            self.logs_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        self.se.set_log_callback(None)
        self.se.set_progress_callback(None)
        self.se.set_stop_check_callback(None)
        self.se.set_pause_check_callback(None)
        self.se.set_pause_state_callback(None)

        self._patches = [
            mock.patch.object(se, "SET_CHECKLISTS_DIR", self.set_checklists_dir),
            mock.patch.object(se, "CHECKLIST_PATH", self.master_csv),
            mock.patch.object(se, "CACHE_CHECKPOINTS_DIR", self.checkpoints_dir),
            mock.patch.object(se, "CACHE_CATALOGS_DIR", self.catalogs_dir),
            mock.patch.object(se, "SET_LIBRARY_CACHE_DIR", self.root / "Cache" / "Library"),
            mock.patch.object(se, "REFERENCE_TEMPLATES_DIR", self.ref_dir),
            mock.patch.object(se, "DEAD_BACKS_CACHE_FILE", self.root / "Cache" / "Library" / "dead_backs.json"),
            mock.patch.object(se, "DEAD_FRONTS_CACHE_FILE", self.root / "Cache" / "Library" / "dead_fronts.json"),
            mock.patch.object(se, "TRACKING_FILE", self.root / "Cache" / "Checklists" / "tracked_sets.json"),
            mock.patch.object(se, "RESUME_FILE", self.root / "Cache" / "Checklists" / "resume.json"),
            mock.patch.object(se, "IS_REORGANIZED_V24", True),
            mock.patch.object(se, "ensure_directories", lambda: None),
            mock.patch.object(se, "cleanup_orphaned_drivers", lambda: None),
            mock.patch.object(cfg, "SET_CHECKLISTS_DIR", self.set_checklists_dir),
            mock.patch.object(cfg, "CHECKLIST_PATH", self.master_csv),
            mock.patch.object(cfg, "CACHE_CHECKPOINTS_DIR", self.checkpoints_dir),
            mock.patch.object(cfg, "REFERENCE_TEMPLATES_DIR", self.ref_dir),
            mock.patch.object(cfg, "LOGS_DIR", self.logs_dir),
            mock.patch.object(cli, "LOGS_DIR", self.logs_dir),
            mock.patch.object(cli, "ACTIVE_JOB_STATE_FILE", self.logs_dir / "active_job_state.json"),
            mock.patch.object(cli, "ACTIVE_JOB_LOG_FILE", self.logs_dir / "active_job.log"),
            mock.patch.object(cli, "ensure_directories", lambda: None),
            mock.patch.object(rl, "RATE_LEARNER_STATE_FILE", self.learner_file),
            mock.patch.object(rl, "_SINGLETON_LEARNER", rl.AdaptiveRateLearner(state_file=self.learner_file)),
            mock.patch.object(rl.AdaptiveRateLearner, "wait_before_request", lambda _self, _ep: 0.0),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        self.se.set_log_callback(None)
        self.se.set_progress_callback(None)
        self.se.set_stop_check_callback(None)
        self.se.set_pause_check_callback(None)
        self.se.set_pause_state_callback(None)
        for p in reversed(self._patches):
            p.stop()
        self.env_patch.stop()
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # 1. Multiline-deduped subset, normalization, diff logs, & ETA split
    # ------------------------------------------------------------------
    def test_multiline_deduped_subset_not_requeued_and_diff_logged(self):
        set_name = "2024 Deduped Set"
        # TCDB Base page has 3 rows, but two share TCDB_CID=1001 (multiline/combo card) -> dedupes to 2 rows!
        base_html = _make_checklist_html([
            {"cid": "1001", "cnum": "1", "player": "Player Alpha"},
            {"cid": "1001", "cnum": "1", "player": "Player Beta"},
            {"cid": "1002", "cnum": "2", "player": "Player Gamma"},
        ])
        ins_html = _make_inserts_html([("201", "Stars & Stripes", 1)])
        ins_sub_html = _make_checklist_html([{"cid": "2001", "cnum": "SS1", "player": "Insert Star"}])

        sess1 = _StrictMockSession({
            "https://www.tcdb.com/Checklist.cfm/sid/100/2024-Deduped-Set": _MockResponse(200, base_html),
            "https://www.tcdb.com/Errors.cfm/sid/100/2024-Deduped-Set": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Deduped-Set": _MockResponse(200, ins_html),
            "https://www.tcdb.com/Checklist.cfm/sid/201/Stars-&-Stripes": _MockResponse(200, ins_sub_html),
            "https://www.tcdb.com/Checklist.cfm/sid/201/Stars-%26-Stripes": _MockResponse(200, ins_sub_html),
        })

        logs1: list[str] = []
        self.se.set_log_callback(logs1.append)
        df1, _ = self.se.scrape_tcdb_checklist_set(
            sess1,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Deduped-Set",
            set_name,
            folder_name="2024_Deduped_Set",
            progress_ctx={"active_set_base_cards": 3, "completed_cards": 0, "total_cards": 4, "completed_subsets": 0, "total_subsets": 2},
        )
        df1.to_csv(self.set_checklists_dir / "2024_Deduped_Set.csv", index=False, encoding="utf-8-sig")

        # Verify Base deduped to 2 rows while checkpoint preserves tcdb_reported_count=3 and local_deduped_count=2
        self.assertEqual(len(df1[df1["Subset"] == "Base"]), 2)
        cp = self.se.load_set_checkpoint(set_name)
        self.assertEqual(cp["subsets"]["100"]["tcdb_reported_count"], 3)
        self.assertEqual(cp["subsets"]["100"]["local_deduped_count"], 2)
        self.assertTrue(any("[QUEUE: missing_locally] Base" in ln for ln in logs1))

        # Second run: TCDB still reports 3 Base cards and "Stars and Stripes" (normalized & -> and)
        # ZERO Checklist.cfm calls must be made!
        sess2 = _StrictMockSession({
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Deduped-Set": _MockResponse(
                200,
                _make_inserts_html([("201", "Stars   and  Stripes", 1)]),
            ),
        })
        logs2: list[str] = []
        self.se.set_log_callback(logs2.append)
        df2, _ = self.se.scrape_tcdb_checklist_set(
            sess2,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Deduped-Set",
            set_name,
            folder_name="2024_Deduped_Set",
            progress_ctx={"active_set_base_cards": 3, "completed_cards": 0, "total_cards": 4, "completed_subsets": 0, "total_subsets": 2},
        )
        self.assertEqual(len(df2), 3)
        self.assertTrue(all("Checklist.cfm" not in u for u in sess2.calls))
        self.assertTrue(any("[SKIP] Base (local=2, tcdb_reported=3)" in ln for ln in logs2))
        self.assertTrue(any("[SKIP] Stars and Stripes" in ln for ln in logs2))

    def test_subset_name_normalization_and_separate_eta_averages(self):
        self.assertEqual(
            self.se.normalize_subset_name_for_diff("  Stars  &   Stripes "),
            self.se.normalize_subset_name_for_diff("Stars and Stripes"),
        )
        self.assertEqual(
            self.se.normalize_subset_name_for_diff("Héritage Chrome"),
            self.se.normalize_subset_name_for_diff("Heritage Chrome"),
        )

        learner = self.rl.get_rate_learner()
        learner.record_subset_duration("checklist_only", 0.05, card_count=100, was_skipped=True)
        learner.record_subset_duration("checklist_only", 6.00, card_count=100, was_skipped=False)
        priors = learner.get_eta_priors("checklist_only")
        self.assertEqual(priors["skipped_subset_samples"], 1)
        self.assertEqual(priors["deep_dived_subset_samples"], 1)
        self.assertLess(priors["ema_sec_per_skipped_subset"], priors["ema_sec_per_deep_dived_subset"])
        eta_all_skipped = learner.estimate_incremental_subsets_eta("checklist_only", 10, 0)
        eta_all_deep = learner.estimate_incremental_subsets_eta("checklist_only", 0, 10)
        self.assertLess(eta_all_skipped, eta_all_deep)

    # ------------------------------------------------------------------
    # 2. Pre-flight /Images/Large/ probe classifications (200, 403, 503, timeout)
    # ------------------------------------------------------------------
    def test_preflight_probe_distinguishes_200_403_503_and_timeout(self):
        probe_url = "https://www.tcdb.com/Images/Large/Baseball/100/100-1Fr.jpg"
        logs: list[str] = []
        self.se.set_log_callback(logs.append)

        # 200 OK
        r200 = self.se.preflight_probe_tcdb_images(
            _StrictMockSession({probe_url: _MockResponse(200, content=b"\xff\xd8\xff\xe0" + b"0" * 600)}),
            test_image_url=probe_url,
        )
        self.assertTrue(r200["ok"])
        self.assertEqual(r200["classification"], "200_ok")
        self.assertTrue(any("[PREFLIGHT OK]" in ln for ln in logs))

        # 403 CF Block
        r403 = self.se.preflight_probe_tcdb_images(
            _StrictMockSession({probe_url: _MockResponse(403, text="Forbidden")}),
            test_image_url=probe_url,
        )
        self.assertFalse(r403["ok"])
        self.assertEqual(r403["classification"], "403_cf_block")
        self.assertTrue(any("[PREFLIGHT BLOCKED: /Images/Large/ returned HTTP 403]" in ln for ln in logs))

        # 503 Origin Overload
        r503 = self.se.preflight_probe_tcdb_images(
            _StrictMockSession({probe_url: _MockResponse(503, text="Service Unavailable")}),
            test_image_url=probe_url,
        )
        self.assertFalse(r503["ok"])
        self.assertEqual(r503["classification"], "503_origin_overload")

        # Timeout
        rto = self.se.preflight_probe_tcdb_images(
            _StrictMockSession({probe_url: TimeoutError("curl: (28) Operation timed out")}),
            test_image_url=probe_url,
        )
        self.assertFalse(rto["ok"])
        self.assertEqual(rto["classification"], "timeout")

    # ------------------------------------------------------------------
    # 3. Skip Rep fallback on 503/timeout + 3-consecutive breather
    # ------------------------------------------------------------------
    def test_skip_rep_fallback_on_503_and_timeout(self):
        dest = self.ref_dir / "Test_Set" / "card_F.jpg"
        for err_resp in (
            _MockResponse(503, text="Service Unavailable"),
            TimeoutError("curl: (28) Operation timed out"),
        ):
            sess = _StrictMockSession({
                "https://www.tcdb.com/Images/Large/2024/1Fr.jpg": err_resp,
                # Rep URL intentionally omitted or would fail; must NEVER be called!
            })
            outcome: dict = {}
            with mock.patch.object(self.se.time, "sleep", lambda _s: None):
                res = self.se._download_single_template_side(
                    sess,
                    "https://www.tcdb.com/Images/Large/2024/1RepFr.jpg",
                    "https://www.tcdb.com/Images/Large/2024/1Fr.jpg",
                    "https://www.tcdb.com/Checklist.cfm/sid/100",
                    dest,
                    preferred_tier="S",
                    outcome_out=outcome,
                )
            self.assertIsNone(res)
            self.assertTrue(outcome.get("transient_overload"))
            self.assertTrue(all("RepFr.jpg" not in u for u in sess.calls))

    # ------------------------------------------------------------------
    # 4. Manual Pause / Resume & Auto-Pause after 3 clearance failures
    # ------------------------------------------------------------------
    def test_manual_pause_resume_and_wait_if_paused(self):
        self.cli.write_job_state("RUNNING", "scrape_tcdb_images", "Test Scrape", pid=0, lane="slot_1")
        self.assertFalse(self.cli.is_lane_paused("slot_1"))

        self.cli.pause_active_job(lane="slot_1", reason="Manual user pause")
        self.assertTrue(self.cli.is_lane_paused("slot_1"))
        self.assertEqual(self.cli.get_active_job_state(lane="slot_1")["status"], "PAUSED")

        self.se.set_pause_check_callback(lambda: self.cli.is_lane_paused("slot_1"))
        resumed_flag = {"done": False}

        def _resume_soon():
            time.sleep(0.15)
            self.cli.resume_active_job(lane="slot_1")
            resumed_flag["done"] = True

        t = threading.Thread(target=_resume_soon, daemon=True)
        t.start()
        ok = self.se.wait_if_paused(poll_interval=0.05)
        t.join(timeout=2.0)

        self.assertTrue(ok)
        self.assertTrue(resumed_flag["done"])
        self.assertFalse(self.cli.is_lane_paused("slot_1"))
        self.assertEqual(self.cli.get_active_job_state(lane="slot_1")["status"], "RUNNING")

    def test_auto_pause_after_three_clearance_failures(self):
        self.cli.write_job_state("RUNNING", "scrape_tcdb_images", "Auto-Pause Scrape", pid=0, lane="slot_1")
        self.se.set_pause_check_callback(lambda: self.cli.is_lane_paused("slot_1"))
        self.se.set_pause_state_callback(
            lambda paused, reason="": self.cli.pause_active_job("slot_1", reason) if paused else self.cli.resume_active_job("slot_1")
        )

        class _AlwaysFailSB:
            def __init__(self, **_kw):
                pass

            def __enter__(self):
                raise RuntimeError("Cloudflare Turnstile stuck")

            def __exit__(self, *args):
                return False

        # Resume after auto-pause, then stop so connect_session exits cleanly without infinite loop
        def _stop_after_pause():
            deadline = time.time() + 3.0
            while time.time() < deadline:
                st = self.cli.get_active_job_state(lane="slot_1")
                if st.get("status") == "PAUSED":
                    self.cli.stop_active_job(lane="slot_1")
                    return
                time.sleep(0.05)

        self.se.set_stop_check_callback(lambda: self.cli.get_active_job_state(lane="slot_1").get("status") == "STOPPED")
        watcher = threading.Thread(target=_stop_after_pause, daemon=True)
        watcher.start()

        with mock.patch.object(self.se, "SB", _AlwaysFailSB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            with self.assertRaises(self.se.CloudflareEdgeBlockPaused) as ctx:
                self.se.connect_session(max_attempts=5, max_clearance_failures=3)

        watcher.join(timeout=2.0)
        self.assertIn("Auto-paused after 3 clearance failures", str(ctx.exception))

    # ------------------------------------------------------------------
    # 5. Profile rotation tempfile, scoped preflight, & UI pause sync
    # ------------------------------------------------------------------
    def test_connect_session_profile_rotation_no_nameerror_and_cleanup(self):
        seen_profile_dirs: list[str] = []
        attempts = {"count": 0}

        class _FakeDriver:
            window_handles = ["h1"]
            title = "TCDB | Trading Card Database"
            page_source = "<html><body>" + ("x" * 200) + "</body></html>"

            class _SwitchTo:
                def window(self, _h):
                    pass

            switch_to = _SwitchTo()

            def get_cookies(self):
                return [{"name": "cf_clearance", "value": "cf_rot_ok"}]

            def execute_script(self, script: str):
                if "readyState" in script:
                    return "complete"
                if "userAgent" in script:
                    return "Mozilla/5.0 RotationTestUA"
                return ""

        class _RotateTestSB:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.driver = _FakeDriver()

            def __enter__(self):
                if "user_data_dir" in self.kwargs:
                    seen_profile_dirs.append(self.kwargs["user_data_dir"])
                attempts["count"] += 1
                if attempts["count"] == 1 and not self.kwargs.get("_force_ok"):
                    raise RuntimeError("Transient launch failure on attempt 1")
                return self

            def __exit__(self, *args):
                return False

            def uc_open_with_reconnect(self, _url, _t):
                pass

            def sleep(self, _s):
                pass

        # Case A: attempt > 1 triggers profile rotation without NameError and cleans up temp dir
        sess_a = _StrictMockSession({})
        with mock.patch.object(self.se, "SB", _RotateTestSB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            out_a = self.se.connect_session(
                existing_session=sess_a,
                max_attempts=3,
                run_preflight=False,
                rotate_profile=False,
            )
        self.assertIs(out_a, sess_a)
        self.assertEqual(len(seen_profile_dirs), 1)
        self.assertIn("tcdb_uc_prof_", Path(seen_profile_dirs[0]).name)
        self.assertFalse(Path(seen_profile_dirs[0]).exists())

        # Case B: rotate_profile=True on first attempt creates & cleans up temp dir
        attempts["count"] = 1  # Next enter is count=2 -> succeeds immediately
        seen_profile_dirs.clear()
        sess_b = _StrictMockSession({})
        with mock.patch.object(self.se, "SB", _RotateTestSB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            out_b = self.se.connect_session(
                existing_session=sess_b,
                max_attempts=2,
                run_preflight=False,
                rotate_profile=True,
            )
        self.assertIs(out_b, sess_b)
        self.assertEqual(len(seen_profile_dirs), 1)
        self.assertIn("tcdb_uc_prof_", Path(seen_profile_dirs[0]).name)
        self.assertFalse(Path(seen_profile_dirs[0]).exists())

    def test_checklist_only_mode_does_not_fail_when_images_large_returns_403(self):
        class _HealthySB:
            def __init__(self, **_kwargs):
                class _D:
                    window_handles = ["h1"]
                    title = "TCDB"
                    page_source = "<html><body>" + ("ok" * 100) + "</body></html>"

                    class _SW:
                        def window(self, _h):
                            pass

                    switch_to = _SW()

                    def get_cookies(self):
                        return [{"name": "cf_clearance", "value": "cf_chk_tok"}]

                    def execute_script(self, script: str):
                        return "complete" if "readyState" in script else "Mozilla/5.0 ChecklistUA"

                self.driver = _D()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def uc_open_with_reconnect(self, _url, _t):
                pass

            def sleep(self, _s):
                pass

        probe_url = self.se.DEFAULT_PREFLIGHT_IMAGE_URL
        sess = _StrictMockSession({probe_url: _MockResponse(403, text="Forbidden")})

        with mock.patch.object(self.se, "SB", _HealthySB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            out_sess = self.se.connect_session(
                existing_session=sess,
                max_attempts=1,
                require_image_probe=False,
            )
        self.assertIs(out_sess, sess)
        self.assertIs(getattr(out_sess, "_require_image_probe", None), False)
        self.assertEqual(sess.calls, [])

        # Verify run_tcdb_checklist_pipeline passes require_image_probe=False
        captured_kwargs: dict = {}

        def _fake_connect(**kwargs):
            captured_kwargs.update(kwargs)
            return sess

        with (
            mock.patch.object(self.se, "connect_session", side_effect=_fake_connect),
            mock.patch.object(self.se, "prescan_queue_card_metrics", return_value={"total_cards": 0, "total_subsets": 0, "per_set_metrics": {}, "prefetched_inserts": {}, "prefetched_insert_counts": {}, "prefetched_base_html": {}}),
            mock.patch.object(self.se, "scrape_tcdb_checklist_set", return_value=(pd.DataFrame(), [])),
            mock.patch.object(self.se, "sync_set_library_download_status", lambda **_kw: None),
        ):
            self.se.run_tcdb_checklist_pipeline(
                selected_tcdb_sets={"https://www.tcdb.com/ViewSet.cfm/sid/100/Test-Set": "Test_Set"}
            )
        self.assertIs(captured_kwargs.get("require_image_probe"), False)

    def test_image_download_preflight_sends_referer_ua_and_cf_clearance(self):
        class _HealthySB:
            def __init__(self, **_kwargs):
                class _D:
                    window_handles = ["h1"]
                    title = "TCDB"
                    page_source = "<html><body>" + ("ok" * 100) + "</body></html>"

                    class _SW:
                        def window(self, _h):
                            pass

                    switch_to = _SW()

                    def get_cookies(self):
                        return [{"name": "cf_clearance", "value": "cf_tok_123"}]

                    def execute_script(self, script: str):
                        return "complete" if "readyState" in script else "Mozilla/5.0 SeleniumBaseTestUA"

                self.driver = _D()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def uc_open_with_reconnect(self, _url, _t):
                pass

            def sleep(self, _s):
                pass

        captured_reqs: list[dict] = []

        class _CapturingSession:
            def __init__(self, status_code: int = 200):
                self.status_code = status_code
                self.cookies: dict[str, str] = {}
                self.headers: dict[str, str] = {}

            def get(self, url: str, headers=None, cookies=None, timeout=15):
                captured_reqs.append({"url": url, "headers": dict(headers or {}), "cookies": dict(cookies or {})})
                if self.status_code == 200:
                    return _MockResponse(200, content=b"\xff\xd8\xff\xe0" + b"0" * 600)
                return _MockResponse(self.status_code, text="Forbidden")

        sess_ok = _CapturingSession(status_code=200)
        with mock.patch.object(self.se, "SB", _HealthySB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            self.se.connect_session(existing_session=sess_ok, max_attempts=1, require_image_probe=True)

        self.assertEqual(len(captured_reqs), 1)
        self.assertIn("/Images/Large/", captured_reqs[0]["url"])
        self.assertEqual(captured_reqs[0]["headers"].get("Referer"), "https://www.tcdb.com/")
        self.assertEqual(captured_reqs[0]["headers"].get("User-Agent"), "Mozilla/5.0 SeleniumBaseTestUA")
        self.assertEqual(captured_reqs[0]["cookies"].get("cf_clearance"), "cf_tok_123")

        # When /Images/Large/ returns 403 and require_image_probe=True, handshake must fail
        sess_403 = _CapturingSession(status_code=403)
        with mock.patch.object(self.se, "SB", _HealthySB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            with self.assertRaises(self.se.CloudflareEdgeBlockPaused):
                self.se.connect_session(
                    existing_session=sess_403,
                    max_attempts=1,
                    max_clearance_failures=1,
                    require_image_probe=True,
                )

    def test_job_status_endpoint_reflects_auto_pause_immediately_and_dedupes_logs(self):
        import launch_tabulas_hub

        self.cli.write_job_state("RUNNING", "scrape_tcdb_images", "Live Scrape", pid=0, lane="slot_1")
        self.se.set_pause_state_callback(
            lambda paused, reason="": self.cli.pause_active_job("slot_1", reason) if paused else self.cli.resume_active_job("slot_1")
        )

        reason = "Auto-paused after 3 clearance failures"
        self.se.request_auto_pause(reason)

        # Even if a progress callback writes RUNNING afterward while pause flag exists, status stays PAUSED
        self.cli.write_job_state("RUNNING", "scrape_tcdb_images", "Live Scrape", current=2, total=10, pid=0, lane="slot_1")

        st = self.cli.get_active_job_state("slot_1")
        self.assertEqual(st["status"], "PAUSED")
        self.assertEqual(st["pause_reason"], reason)

        live_payload = launch_tabulas_hub._get_live_lanes_and_logs()
        slot_1 = live_payload["lanes"]["slot_1"]
        self.assertEqual(slot_1["status"], "PAUSED")
        self.assertEqual(slot_1["pause_reason"], reason)
        self.assertTrue(slot_1["is_paused"])
        self.assertFalse(slot_1["is_terminal"])

        # Repeated pause calls must NOT spam "Pause requested"
        self.cli.pause_active_job("slot_1", reason=reason)
        logs_txt = self.cli.get_active_job_logs(lane="slot_1")
        self.assertEqual(logs_txt.count("Pause requested"), 1)


if __name__ == "__main__":
    unittest.main()
