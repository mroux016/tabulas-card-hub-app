from __future__ import annotations

import os
import sys
import tempfile
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


class _CapturingMockSession:
    def __init__(self, routes: dict[str, object], user_agent: str = ""):
        self.routes = routes
        self.calls: list[dict] = []
        self.cookies: dict[str, str] = {"cf_clearance": "test_cf_token"}
        self.headers: dict[str, str] = {"User-Agent": user_agent} if user_agent else {}
        self.proxies: dict[str, str] = {}

    def get(self, url: str, headers=None, cookies=None, timeout=30):
        import Core.scraper_engine as se

        self.calls.append({
            "url": url,
            "headers": dict(headers or {}),
            "cookies": dict(cookies or {}),
            "proxies": dict(self.proxies),
        })
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
        imgs = []
        if r.get("front_thumb"):
            imgs.append(f'<img src="{r["front_thumb"]}" alt="Front" />')
        if r.get("back_thumb"):
            imgs.append(f'<img src="{r["back_thumb"]}" alt="Back" />')
        trs.append(
            f"<tr>"
            f"<td>{''.join(imgs)}</td>"
            f'<td><a href="/ViewCard.cfm/sid/100/cid/{cid}/card-{cnum}">{cnum}</a></td>'
            f'<td><a href="/Person.cfm/pid/{cid}">{plr}</a></td>'
            f'<td><a href="/Team.cfm/tid/1">{team}</a></td>'
            f"</tr>"
        )
    return f"<html><body><table>{''.join(trs)}</table></body></html>"


def _make_inserts_html_with_totals(inserts: list[tuple[str, str, int]], include_header_total: bool = True) -> str:
    thead = "<thead><tr><th>Insert / Parallel <a href='/Checklist.cfm/sid/999'>201 cards</a></th><th>Cards</th></tr></thead>" if include_header_total else ""
    tfoot = "<tfoot><tr><td>Total <a href='/Checklist.cfm/sid/998'>201</a></td><td>201</td></tr></tfoot>" if include_header_total else ""
    trs = []
    for sid, name, cnt in inserts:
        slug = name.replace(" ", "-")
        trs.append(f'<tr><td><a href="/Checklist.cfm/sid/{sid}/{slug}">{name}</a></td><td>{cnt} cards</td></tr>')
    return f"<html><body><table>{thead}<tbody>{''.join(trs)}</tbody>{tfoot}</table></body></html>"


class ScraperHygieneAndProxyTests(unittest.TestCase):
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

        self.cfg = cfg
        self.rl = rl
        self.se = se
        self.se.reset_proxy_pool_state()

        self.set_checklists_dir = self.root / "Data" / "Checklists_and_Resources" / "Set_Checklists"
        self.master_csv = self.root / "Data" / "Checklists_and_Resources" / "Master_Checklist.csv"
        self.checkpoints_dir = self.root / "Cache" / "Checklists" / "Checkpoints"
        self.catalogs_dir = self.root / "Cache" / "Library" / "Catalogs"
        self.ref_dir = self.root / "SetLibrary" / "Reference_Library"
        self.logs_dir = self.root / "Logs"
        self.proxy_dir = self.root / "Proxy"
        self.scraper_settings_file = self.logs_dir / "scraper_settings.json"
        self.learner_file = self.logs_dir / "adaptive_rate_learner.json"

        for d in (
            self.set_checklists_dir,
            self.checkpoints_dir,
            self.catalogs_dir,
            self.ref_dir,
            self.logs_dir,
            self.proxy_dir,
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
            mock.patch.object(cfg, "PROXY_DIR", str(self.proxy_dir)),
            mock.patch.object(cfg, "SCRAPER_SETTINGS_FILE", self.scraper_settings_file),
            mock.patch.object(rl, "RATE_LEARNER_STATE_FILE", self.learner_file),
            mock.patch.object(rl, "_SINGLETON_LEARNER", rl.AdaptiveRateLearner(state_file=self.learner_file)),
            mock.patch.object(rl.AdaptiveRateLearner, "wait_before_request", lambda _self, _ep: 0.0),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        self.se.reset_proxy_pool_state()
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
    # 1. Dynamic curl_cffi impersonation ("chrome" + "chrome120" fallback)
    # ------------------------------------------------------------------
    def test_create_http_session_uses_chrome_with_chrome120_fallback(self):
        seen_impersonates: list[str] = []

        class _FakeCffiMod:
            @staticmethod
            def Session(impersonate: str = ""):
                seen_impersonates.append(impersonate)
                if impersonate == "chrome" and len(seen_impersonates) > 1:
                    raise ValueError("Unsupported impersonate: chrome")
                s = _CapturingMockSession({})
                s.impersonate = impersonate
                return s

        with mock.patch.object(self.se, "cffi_requests", _FakeCffiMod):
            s1 = self.se._create_http_session(proxy_url="http://127.0.0.1:8881")
            self.assertEqual(s1.impersonate, "chrome")
            self.assertEqual(s1.proxies, {"http": "http://127.0.0.1:8881", "https": "http://127.0.0.1:8881"})

            s2 = self.se._create_http_session()
            self.assertEqual(s2.impersonate, "chrome120")
        self.assertEqual(seen_impersonates, ["chrome", "chrome", "chrome120"])

    # ------------------------------------------------------------------
    # 2. Browser-standard /Images/Large/ headers (uncorrupted by safe_get)
    # ------------------------------------------------------------------
    def test_image_requests_send_browser_standard_headers(self):
        probe_url = "https://www.tcdb.com/Images/Large/Baseball/100/100-1Fr.jpg"
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
        jpg_bytes = b"\xff\xd8\xff\xe0" + b"0" * 600

        # Preflight probe headers
        sess_probe = _CapturingMockSession({probe_url: _MockResponse(200, content=jpg_bytes)}, user_agent=ua)
        res = self.se.preflight_probe_tcdb_images(sess_probe, test_image_url=probe_url, user_agent=ua)
        self.assertTrue(res["ok"])
        hdrs_p = sess_probe.calls[0]["headers"]
        self.assertEqual(hdrs_p.get("Accept"), "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8")
        self.assertEqual(hdrs_p.get("Sec-Fetch-Dest"), "image")
        self.assertEqual(hdrs_p.get("Sec-Fetch-Mode"), "no-cors")
        self.assertEqual(hdrs_p.get("Sec-Fetch-Site"), "same-origin")
        self.assertEqual(hdrs_p.get("Accept-Language"), "en-US,en;q=0.9")
        self.assertEqual(hdrs_p.get("Referer"), "https://www.tcdb.com/")
        self.assertEqual(hdrs_p.get("User-Agent"), ua)

        # Download call headers via safe_get (ensuring commas/semicolons/spaces are NOT percent-encoded!)
        img_url = "https://www.tcdb.com/Images/Large/2024/1Fr.jpg"
        sess_dl = _CapturingMockSession({img_url: _MockResponse(200, content=jpg_bytes)}, user_agent=ua)
        dest = self.ref_dir / "Test_Headers" / "card_F.jpg"
        with mock.patch.object(self.se.time, "sleep", lambda _s: None):
            tier = self.se._download_single_template_side(
                sess_dl,
                "https://www.tcdb.com/Images/Large/2024/1RepFr.jpg",
                img_url,
                "https://www.tcdb.com/Checklist.cfm/sid/100",
                dest,
                preferred_tier="S",
            )
        self.assertEqual(tier, "S")
        hdrs_d = sess_dl.calls[0]["headers"]
        self.assertEqual(hdrs_d.get("Accept"), "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8")
        self.assertEqual(hdrs_d.get("Sec-Fetch-Dest"), "image")
        self.assertEqual(hdrs_d.get("Sec-Fetch-Mode"), "no-cors")
        self.assertEqual(hdrs_d.get("Sec-Fetch-Site"), "same-origin")
        self.assertEqual(hdrs_d.get("Accept-Language"), "en-US,en;q=0.9")
        self.assertEqual(hdrs_d.get("Referer"), "https://www.tcdb.com/Checklist.cfm/sid/100")
        self.assertEqual(hdrs_d.get("User-Agent"), ua)

    # ------------------------------------------------------------------
    # 3. Jitter skipped on Skip(Exists) & applied + breather on downloads
    # ------------------------------------------------------------------
    def test_card_by_card_jitter_skipped_on_existing_and_applied_on_downloads(self):
        set_name = "2026 Pacing Test"
        folder = "2026_Pacing_Test"
        set_dir = self.ref_dir / folder
        set_dir.mkdir(parents=True, exist_ok=True)

        # Card 1 & 2 already exist on disk -> Skip(Exists) -> ZERO jitter!
        f1, _ = self.se.build_template_image_filenames(set_name, "Base", "1", "SkipOne", "101")
        f2, _ = self.se.build_template_image_filenames(set_name, "Base", "2", "SkipTwo", "102")
        (set_dir / f1).write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 512)
        (set_dir / f2).write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 512)

        # Cards 3, 4, 5 need network download
        rows = [
            {"cid": "101", "cnum": "1", "player": "SkipOne", "front_thumb": "/Images/Thumbs/101Fr.jpg"},
            {"cid": "102", "cnum": "2", "player": "SkipTwo", "front_thumb": "/Images/Thumbs/102Fr.jpg"},
            {"cid": "103", "cnum": "3", "player": "DlThree", "front_thumb": "/Images/Thumbs/103Fr.jpg"},
            {"cid": "104", "cnum": "4", "player": "DlFour", "front_thumb": "/Images/Thumbs/104Fr.jpg"},
            {"cid": "105", "cnum": "5", "player": "DlFive", "front_thumb": "/Images/Thumbs/105Fr.jpg"},
        ]
        base_html = _make_checklist_html(rows)
        jpg_bytes = b"\xff\xd8\xff\xe0" + b"1" * 600
        sess = _CapturingMockSession({
            "https://www.tcdb.com/Checklist.cfm/sid/100/2026-Pacing-Test": _MockResponse(200, base_html),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Pacing-Test": _MockResponse(404, ""),
            "https://www.tcdb.com/Images/Large/103Fr.jpg": _MockResponse(200, content=jpg_bytes),
            "https://www.tcdb.com/Images/Large/104Fr.jpg": _MockResponse(200, content=jpg_bytes),
            "https://www.tcdb.com/Images/Large/105Fr.jpg": _MockResponse(200, content=jpg_bytes),
        })

        sleep_calls: list[float] = []
        self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Pacing-Test",
            set_name,
            folder_name=folder,
            include_inserts=False,
            download_images_card_by_card=True,
            card_delay_range=(0.5, 1.4),
            breather_every_cards=2,
            breather_duration_range=(5.0, 10.0),
            pacer_sleep_fn=sleep_calls.append,
        )
        # Card 1 & 2 skipped (0 sleeps). Card 3 downloads (1st), Card 4 gets jitter + triggers breather (2nd),
        # Card 5 has jitter skipped because breather just ran!
        jitters = [s for s in sleep_calls if 0.5 <= s <= 1.4]
        breathers = [s for s in sleep_calls if 5.0 <= s <= 10.0]
        self.assertEqual(len(jitters), 1)
        self.assertEqual(len(breathers), 1)

    # ------------------------------------------------------------------
    # 4. Proxy-pool persistence & rotation on 403 before Auto-Pause
    # ------------------------------------------------------------------
    def test_proxy_pool_persistence_and_rotation_on_403_before_autopause(self):
        saved = self.cfg.save_scraper_settings({
            "scraper_proxy_pool": "http://127.0.0.1:8881\n# comment\n127.0.0.1:8882\nhttp://127.0.0.1:8881\n"
        })
        self.assertEqual(saved["scraper_proxy_pool"], ["http://127.0.0.1:8881", "http://127.0.0.1:8882"])
        loaded = self.cfg.load_scraper_settings()
        self.assertEqual(loaded["scraper_proxy_pool"], ["http://127.0.0.1:8881", "http://127.0.0.1:8882"])

        seen_sb_kwargs: list[dict] = []
        seen_cffi_proxies: list[dict] = []
        probe_state = {"calls": 0}

        class _FakeDriver:
            window_handles = ["h1"]
            title = "TCDB"
            page_source = "<html><body>" + ("ok" * 100) + "</body></html>"

            class _SW:
                def window(self, _h):
                    pass

            switch_to = _SW()

            def get_cookies(self):
                return [{"name": "cf_clearance", "value": "cf_proxy_tok"}]

            def execute_script(self, script: str):
                return "complete" if "readyState" in script else "Mozilla/5.0 ProxyUA"

        class _ProxySB:
            def __init__(self, **kwargs):
                seen_sb_kwargs.append(dict(kwargs))
                self.driver = _FakeDriver()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def uc_open_with_reconnect(self, _url, _t):
                pass

            def sleep(self, _s):
                pass

        class _ProxySession:
            def __init__(self):
                self.cookies: dict[str, str] = {}
                self.headers: dict[str, str] = {}
                self.proxies: dict[str, str] = {}

            def get(self, url: str, headers=None, cookies=None, timeout=15):
                seen_cffi_proxies.append(dict(self.proxies))
                probe_state["calls"] += 1
                if probe_state["calls"] == 1:
                    return _MockResponse(403, text="Forbidden on proxy 1")
                return _MockResponse(200, content=b"\xff\xd8\xff\xe0" + b"0" * 600)

        logs: list[str] = []
        self.se.set_log_callback(logs.append)
        sess = _ProxySession()
        fake_pm_ok = {
            "healthy_proxies": ["http://127.0.0.1:8881", "http://127.0.0.1:8882"],
            "results": [
                {"proxy": "http://127.0.0.1:8881", "ok": True, "ip": "198.51.100.1", "loc": "CA", "colo": "YYZ", "latency_ms": 10, "error": ""},
                {"proxy": "http://127.0.0.1:8882", "ok": True, "ip": "198.51.100.2", "loc": "US", "colo": "SJC", "latency_ms": 12, "error": ""},
            ],
            "relaunched": False,
        }
        with mock.patch.object(self.se, "SB", _ProxySB), mock.patch.object(self.se, "ensure_proxies_ready", return_value=fake_pm_ok), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            out = self.se.connect_session(existing_session=sess, max_attempts=1, require_image_probe=True)

        self.assertIs(out, sess)
        self.assertEqual(seen_sb_kwargs[0].get("chromium_arg"), "--proxy-server=http://127.0.0.1:8881")
        self.assertEqual(seen_sb_kwargs[1].get("chromium_arg"), "--proxy-server=http://127.0.0.1:8882")
        self.assertIn("user_data_dir", seen_sb_kwargs[1])
        self.assertEqual(seen_cffi_proxies[0], {"http": "http://127.0.0.1:8881", "https": "http://127.0.0.1:8881"})
        self.assertEqual(seen_cffi_proxies[1], {"http": "http://127.0.0.1:8882", "https": "http://127.0.0.1:8882"})
        self.assertTrue(any("[PROXY ROTATE] Switching to proxy 2/2 (127.0.0.1:8882)" in ln for ln in logs))

        # Exhausting all proxies in pool triggers Auto-Pause
        self.se.reset_proxy_pool_state()
        always_403 = _CapturingMockSession({self.se.DEFAULT_PREFLIGHT_IMAGE_URL: _MockResponse(403, text="Forbidden")})
        pause_calls: list[tuple[bool, str]] = []
        self.se.set_pause_state_callback(lambda paused, reason="": pause_calls.append((paused, reason)))
        with mock.patch.object(self.se, "SB", _ProxySB), mock.patch.object(self.se, "ensure_proxies_ready", return_value=fake_pm_ok), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            with self.assertRaises(self.se.CloudflareEdgeBlockPaused) as ctx:
                self.se.connect_session(existing_session=always_403, max_attempts=1, require_image_probe=True)
        self.assertIn("exhausting all 2 configured proxies", str(ctx.exception))
        self.assertTrue(any(p[0] is True for p in pause_calls))

    # ------------------------------------------------------------------
    # 5. Off-by-1 tcdb_reported_count (200 parsed vs 201 overview)
    # ------------------------------------------------------------------
    def test_off_by_one_tcdb_reported_count_skips_cleanly_after_initial_scrape(self):
        set_name = "2026 Topps Holiday Baseball"
        folder = "2026_Topps_Holiday_Baseball"
        base_rows_spec = [{"cid": str(1000 + i), "cnum": str(i), "player": f"Base {i}"} for i in range(1, 3)]
        par_rows_spec = [{"cid": str(2000 + i), "cnum": str(i), "player": f"Holiday {i}"} for i in range(1, 201)]

        base_html = _make_checklist_html(base_rows_spec)
        par_html = _make_checklist_html(par_rows_spec)
        ins_html = _make_inserts_html_with_totals([("201", "Metallic Snowflake", 201)], include_header_total=True)

        # Verify header/footer total rows in Inserts.cfm are excluded from count extraction
        sess_run1 = _CapturingMockSession({
            "https://www.tcdb.com/Checklist.cfm/sid/100/2026-Topps-Holiday-Baseball": _MockResponse(200, base_html),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Topps-Holiday-Baseball": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Topps-Holiday-Baseball": _MockResponse(200, ins_html),
            "https://www.tcdb.com/Checklist.cfm/sid/201/Metallic-Snowflake": _MockResponse(200, par_html),
        })
        ins_map, ins_counts = self.se._fetch_inserts_index_with_counts(
            sess_run1,
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Topps-Holiday-Baseball",
            set_name,
        )
        self.assertNotIn("999", ins_map)
        self.assertNotIn("998", ins_map)
        self.assertEqual(ins_counts.get("201"), 201)

        # Run 1: Scrapes 200 actual cards while overview reported 201
        df1, _ = self.se.scrape_tcdb_checklist_set(
            sess_run1,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Topps-Holiday-Baseball",
            set_name,
            folder_name=folder,
            progress_ctx={"active_set_base_cards": 2, "completed_cards": 0, "total_cards": 203, "completed_subsets": 0, "total_subsets": 2},
        )
        df1.to_csv(self.set_checklists_dir / f"{folder}.csv", index=False, encoding="utf-8-sig")
        cp = self.se.load_set_checkpoint(set_name, alt_folder_name=folder)
        self.assertEqual(cp["subsets"]["201"]["tcdb_reported_count"], 201)
        self.assertEqual(cp["subsets"]["201"]["local_deduped_count"], 200)

        # Run 2: Overview still reports 201 -> must SKIP with ZERO Checklist.cfm requests!
        sess_run2 = _CapturingMockSession({
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Topps-Holiday-Baseball": _MockResponse(200, ins_html),
        })
        logs2: list[str] = []
        self.se.set_log_callback(logs2.append)
        df2, _ = self.se.scrape_tcdb_checklist_set(
            sess_run2,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Topps-Holiday-Baseball",
            set_name,
            folder_name=folder,
            progress_ctx={"active_set_base_cards": 2, "completed_cards": 0, "total_cards": 203, "completed_subsets": 0, "total_subsets": 2},
        )
        self.assertEqual(len(df2), 202)
        self.assertTrue(all("Checklist.cfm" not in c["url"] for c in sess_run2.calls))
        self.assertTrue(any("[SKIP] Metallic Snowflake (local=200, tcdb_reported=201)" in ln for ln in logs2))

    # ------------------------------------------------------------------
    # 6. Dynamic discovery of wp*.conf files & BindAddress parsing in %TEMP%
    # ------------------------------------------------------------------
    def test_discover_wireproxy_configs_dynamic_parsing(self):
        import Core.proxy_manager as pm

        exe = self.proxy_dir / "wireproxy.exe"
        exe.write_bytes(b"MZ")
        (self.proxy_dir / "wp_alpha.conf").write_text(
            "WGConfig = wg_ca.conf\n\n[http]\nBindAddress = 127.0.0.1:9101\n",
            encoding="utf-8",
        )
        (self.proxy_dir / "wp_beta.conf").write_text(
            "WGConfig = wg_us.conf\n\n[Socks5]\nBindAddress = 127.0.0.1:9102\n",
            encoding="utf-8",
        )
        (self.proxy_dir / "other.conf").write_text(
            "[http]\nBindAddress = 127.0.0.1:9999\n",
            encoding="utf-8",
        )

        disc = pm.discover_wireproxy_configs(self.proxy_dir)
        self.assertEqual(disc["exe_path"], str(exe))
        self.assertEqual(
            disc["proxies"],
            {
                "http://127.0.0.1:9101": str(self.proxy_dir / "wp_alpha.conf"),
                "socks5://127.0.0.1:9102": str(self.proxy_dir / "wp_beta.conf"),
            },
        )
        self.assertEqual(disc["configs"]["http://127.0.0.1:9101"]["wg_config"], "wg_ca.conf")
        self.assertEqual(disc["configs"]["socks5://127.0.0.1:9102"]["wg_config"], "wg_us.conf")

    # ------------------------------------------------------------------
    # 7. ensure_proxies_ready relaunches stopped proxies & filters timed-out port
    # ------------------------------------------------------------------
    def test_ensure_proxies_ready_relaunches_and_filters_unhealthy_port(self):
        import Core.proxy_manager as pm

        (self.proxy_dir / "wireproxy.exe").write_bytes(b"MZ")
        (self.proxy_dir / "wp_a.conf").write_text("WGConfig = wg1.conf\n[http]\nBindAddress = 127.0.0.1:8881\n", encoding="utf-8")
        (self.proxy_dir / "wp_b.conf").write_text("WGConfig = wg2.conf\n[http]\nBindAddress = 127.0.0.1:8882\n", encoding="utf-8")

        state = {"launched": False}
        run_calls: list[list[str]] = []
        popen_calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            run_calls.append(list(cmd))
            return mock.Mock(returncode=0, stdout="", stderr="")

        def fake_popen(cmd, **kwargs):
            popen_calls.append(list(cmd))
            state["launched"] = True
            return mock.Mock(pid=42420 + len(popen_calls))

        def fake_tcp(host, port, timeout=1.0):
            return bool(state["launched"] and port == 8882)

        def fake_get(url, proxies=None, timeout=6.0):
            p_url = (proxies or {}).get("https", "")
            if "8882" in p_url:
                return _MockResponse(200, text="ip=203.0.113.88\nloc=CA\ncolo=YYZ\n")
            raise TimeoutError("timed out")

        with mock.patch.object(pm.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(pm.subprocess, "Popen", side_effect=fake_popen), \
             mock.patch.object(pm, "_tcp_port_open", side_effect=fake_tcp), \
             mock.patch.object(pm.requests, "get", side_effect=fake_get), \
             mock.patch.object(pm.time, "sleep", lambda _s: None):
            res = pm.ensure_proxies_ready(["http://127.0.0.1:8881", "http://127.0.0.1:8882"], proxy_dir=self.proxy_dir, startup_wait_s=0.1)

        self.assertTrue(res["relaunched"])
        self.assertEqual(res["healthy_proxies"], ["http://127.0.0.1:8882"])
        self.assertEqual(len(popen_calls), 2)
        self.assertTrue(any("-n" in c for c in run_calls))

    # ------------------------------------------------------------------
    # 8. connect_session detects Cloudflare WAF hard block without /Images/Large/
    # ------------------------------------------------------------------
    def test_connect_session_detects_cf_hard_block_skips_probe_and_rotates_or_pauses(self):
        self.cfg.save_scraper_settings({"scraper_proxy_pool": ["http://127.0.0.1:8881", "http://127.0.0.1:8882"]})
        fake_pm_ok = {
            "healthy_proxies": ["http://127.0.0.1:8881", "http://127.0.0.1:8882"],
            "results": [
                {"proxy": "http://127.0.0.1:8881", "ok": True, "ip": "198.51.100.1", "loc": "US", "colo": "LAX", "latency_ms": 10, "error": ""},
                {"proxy": "http://127.0.0.1:8882", "ok": True, "ip": "198.51.100.2", "loc": "CA", "colo": "YYZ", "latency_ms": 12, "error": ""},
            ],
            "relaunched": False,
        }

        class _HardBlockedDriver:
            window_handles = ["h1"]
            title = "Attention Required! | Cloudflare"
            page_source = '<html><body><div id="cf-error-details"><h1>Sorry, you have been blocked</h1></div></body></html>'

            class _SW:
                def window(self, _h):
                    pass

            switch_to = _SW()

            def get_cookies(self):
                return []

            def execute_script(self, script: str):
                return "complete" if "readyState" in script else "Mozilla/5.0 TestUA"

        class _HealthyDriver:
            window_handles = ["h1"]
            title = "TCDB"
            page_source = "<html><body>" + ("ok" * 100) + "</body></html>"

            class _SW:
                def window(self, _h):
                    pass

            switch_to = _SW()

            def get_cookies(self):
                return [{"name": "cf_clearance", "value": "cf_ok_2"}]

            def execute_script(self, script: str):
                return "complete" if "readyState" in script else "Mozilla/5.0 TestUA"

        sb_calls = {"n": 0}

        class _RotSB:
            def __init__(self, **kwargs):
                sb_calls["n"] += 1
                self.driver = _HardBlockedDriver() if sb_calls["n"] == 1 else _HealthyDriver()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def uc_open_with_reconnect(self, _url, _t):
                pass

            def sleep(self, _s):
                pass

        probe_calls = []

        class _NoProbeSess:
            def __init__(self):
                self.cookies = {}
                self.headers = {}
                self.proxies = {}

            def get(self, url, **kwargs):
                probe_calls.append(url)
                return _MockResponse(200, content=b"\xff\xd8\xff\xe0" + b"0" * 600)

        logs: list[str] = []
        self.se.set_log_callback(logs.append)
        with mock.patch.object(self.se, "SB", _RotSB), \
             mock.patch.object(self.se, "ensure_proxies_ready", return_value=fake_pm_ok), \
             mock.patch.object(self.se.time, "sleep", lambda _s: None):
            out = self.se.connect_session(existing_session=_NoProbeSess(), max_attempts=1, require_image_probe=True)

        self.assertEqual(len(probe_calls), 1)
        self.assertTrue(any("[CF HARD BLOCK]" in ln for ln in logs))
        self.assertTrue(any("[PROXY ROTATE]" in ln for ln in logs))
        self.assertEqual(sum("TCDB page ready" in ln for ln in logs), 1)
        self.assertFalse(any("cf_clearance=False" in ln for ln in logs))
        self.assertEqual(out.proxies.get("https"), "http://127.0.0.1:8882")

        # When all connections are hard-blocked (e.g. direct connection), immediately auto-pause with WAF message
        self.se.reset_proxy_pool_state()
        sb_calls["n"] = 0
        logs.clear()

        class _AlwaysBlockedSB(_RotSB):
            def __init__(self, **kwargs):
                self.driver = _HardBlockedDriver()

        probe_calls.clear()
        with mock.patch.object(self.se, "SB", _AlwaysBlockedSB), mock.patch.object(self.se.time, "sleep", lambda _s: None):
            with self.assertRaises(self.se.CloudflareEdgeBlockPaused) as ctx:
                self.se.connect_session(existing_session=_NoProbeSess(), proxy_pool=[], max_attempts=2, require_image_probe=True)
        self.assertEqual(probe_calls, [])
        self.assertFalse(any("TCDB page ready" in ln for ln in logs))
        self.assertIn("IP hard-blocked by Cloudflare WAF", str(ctx.exception))

    # ------------------------------------------------------------------
    # 9. connect_session detects ERR_PROXY_CONNECTION_FAILED and self-heals
    # ------------------------------------------------------------------
    def test_connect_session_detects_browser_proxy_error_and_triggers_relaunch(self):
        self.cfg.save_scraper_settings({"scraper_proxy_pool": ["http://127.0.0.1:8881"]})
        initial_ok = {
            "healthy_proxies": ["http://127.0.0.1:8881"],
            "results": [{"proxy": "http://127.0.0.1:8881", "ok": True, "ip": "198.51.100.1", "loc": "CA", "colo": "YYZ", "latency_ms": 10, "error": ""}],
            "relaunched": False,
        }
        relaunch_ok = {
            "healthy_proxies": ["http://127.0.0.1:8881"],
            "results": [{"proxy": "http://127.0.0.1:8881", "ok": True, "ip": "198.51.100.1", "loc": "CA", "colo": "YYZ", "latency_ms": 10, "error": ""}],
            "relaunched": True,
        }

        class _ProxyErrDriver:
            window_handles = ["h1"]
            title = "www.tcdb.com"
            page_source = "<html><body><h1>No internet</h1><div>ERR_PROXY_CONNECTION_FAILED</div></body></html>"

            class _SW:
                def window(self, _h):
                    pass

            switch_to = _SW()

            def get_cookies(self):
                return []

            def execute_script(self, script: str):
                return "complete" if "readyState" in script else "Mozilla/5.0 TestUA"

        class _GoodDriver:
            window_handles = ["h1"]
            title = "TCDB"
            page_source = "<html><body>" + ("ok" * 100) + "</body></html>"

            class _SW:
                def window(self, _h):
                    pass

            switch_to = _SW()

            def get_cookies(self):
                return [{"name": "cf_clearance", "value": "cf_healed"}]

            def execute_script(self, script: str):
                return "complete" if "readyState" in script else "Mozilla/5.0 TestUA"

        sb_calls = {"n": 0}

        class _HealSB:
            def __init__(self, **kwargs):
                sb_calls["n"] += 1
                self.driver = _ProxyErrDriver() if sb_calls["n"] == 1 else _GoodDriver()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def uc_open_with_reconnect(self, _url, _t):
                pass

            def sleep(self, _s):
                pass

        sess = _CapturingMockSession({self.se.DEFAULT_PREFLIGHT_IMAGE_URL: _MockResponse(200, content=b"\xff\xd8\xff\xe0" + b"0" * 600)})
        logs: list[str] = []
        self.se.set_log_callback(logs.append)
        with mock.patch.object(self.se, "SB", _HealSB), \
             mock.patch.object(self.se, "ensure_proxies_ready", side_effect=[initial_ok, relaunch_ok]) as pm_mock, \
             mock.patch.object(self.se.time, "sleep", lambda _s: None):
            out = self.se.connect_session(existing_session=sess, max_attempts=1, require_image_probe=True)

        self.assertIs(out, sess)
        self.assertEqual(pm_mock.call_count, 2)
        self.assertTrue(pm_mock.call_args_list[1].kwargs.get("force_relaunch"))
        self.assertTrue(any("[PROXY SELF-HEAL]" in ln for ln in logs))

    # ------------------------------------------------------------------
    # 10. Windows SHELL32.dll icon helpers degrade gracefully when mocked/unavailable
    # ------------------------------------------------------------------
    def test_windows_shell32_icon_helpers_graceful_degradation(self):
        import launch_tabulas_hub as hub

        fake_shell32 = mock.Mock()
        fake_shell32.SetCurrentProcessExplicitAppUserModelID.return_value = 0
        fake_shell32.ExtractIconExW.side_effect = lambda _dll, _idx, large, small, _n: (
            large.__setitem__(0, 111) or small.__setitem__(0, 222) or 1
        )
        fake_user32 = mock.Mock()
        fake_windll = mock.Mock(shell32=fake_shell32, user32=fake_user32)

        with mock.patch("ctypes.windll", fake_windll, create=True), mock.patch.object(hub.sys, "platform", "win32"):
            self.assertTrue(hub.set_windows_app_user_model_id())
            self.assertTrue(hub.apply_windows_window_icon(98765, dll_path=r"C:\Windows\System32\SHELL32.dll"))
            self.assertEqual(fake_user32.SendMessageW.call_count, 2)

        # Non-Windows / failing Win32 calls must return False without raising
        with mock.patch.object(hub.sys, "platform", "linux"):
            self.assertFalse(hub.set_windows_app_user_model_id())
            self.assertEqual(hub.extract_shell32_icon_handles(), (0, 0))
            self.assertFalse(hub.apply_windows_window_icon(98765))


if __name__ == "__main__":
    unittest.main()
