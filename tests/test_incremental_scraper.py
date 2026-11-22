from __future__ import annotations

import json
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
    def __init__(self, status_code: int = 200, text: str = "", content: bytes = b"", url: str = ""):
        self.status_code = status_code
        self.text = text
        self.content = content if content else text.encode("utf-8")
        self.url = url
        self.headers = {"Content-Type": "image/jpeg" if content else "text/html; charset=utf-8"}


class _StrictMockSession:
    """Mock HTTP session that raises StealthBrowserError immediately on any unexpected URL."""

    def __init__(self, routes: dict[str, _MockResponse]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, headers=None, timeout=30):
        import Core.scraper_engine as se
        self.calls.append(url)
        if url not in self.routes:
            raise se.StealthBrowserError(f"Unexpected HTTP GET to {url}")
        val = self.routes[url]
        if callable(val):
            return val(url)
        return val


def _make_checklist_html(rows_spec: list[dict], next_page: int | None = None, max_page_bar: int = 1) -> str:
    trs = []
    for r in rows_spec:
        cid = r["cid"]
        cnum = r["cnum"]
        plr = r["player"]
        team = r.get("team", "Los Angeles Dodgers")
        tags = r.get("tags", "")
        imgs = []
        if r.get("front_thumb"):
            imgs.append(f'<img src="{r["front_thumb"]}" alt="Front" />')
        if r.get("back_thumb"):
            imgs.append(f'<img src="{r["back_thumb"]}" alt="Back" />')
        trs.append(
            f"<tr>"
            f"<td>{''.join(imgs)}</td>"
            f'<td><a href="/ViewCard.cfm/sid/100/cid/{cid}/card-{cnum}">{cnum}</a></td>'
            f'<td><a href="/Person.cfm/pid/{cid}">{plr}</a> {tags}</td>'
            f'<td><a href="/Team.cfm/tid/1">{team}</a></td>'
            f"</tr>"
        )
    nav_links = [f'<a href="/Checklist.cfm/sid/100?PageIndex={p}">{p}</a>' for p in range(1, max_page_bar + 1)]
    if next_page is not None:
        nav_links.append(f'<a href="/Checklist.cfm/sid/100?PageIndex={next_page}">Next</a>')
    return f"<html><body><div>{' '.join(nav_links)}</div><table>{''.join(trs)}</table></body></html>"


def _make_inserts_html(inserts: list[tuple[str, str, int]]) -> str:
    trs = []
    for sid, name, cnt in inserts:
        slug = name.replace(" ", "-")
        trs.append(f'<tr><td><a href="/Checklist.cfm/sid/{sid}/{slug}">{name}</a></td><td>{cnt} cards</td></tr>')
    return f"<html><body><table>{''.join(trs)}</table></body></html>"


class IncrementalScraperTests(unittest.TestCase):
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
        self.se = se
        self.rl = rl
        se._PLAN_SET_STATS_CACHE.clear()

        # Redirect module-level paths in config, rate_learner, and scraper_engine to isolated temp dirs
        self.set_checklists_dir = self.root / "Data" / "Checklists_and_Resources" / "Set_Checklists"
        self.master_csv = self.root / "Data" / "Checklists_and_Resources" / "Master_Checklist.csv"
        self.checkpoints_dir = self.root / "Cache" / "Checklists" / "Checkpoints"
        self.catalogs_dir = self.root / "Cache" / "Library" / "Catalogs"
        self.ref_dir = self.root / "SetLibrary" / "Reference_Library"
        self.dead_backs = self.root / "Cache" / "Library" / "tcdb_dead_backs_cache.json"
        self.dead_fronts = self.root / "Cache" / "Library" / "tcdb_dead_fronts_cache.json"
        self.tracked_file = self.root / "Cache" / "Checklists" / "tracked_sets.json"
        self.resume_file = self.root / "Cache" / "Checklists" / "scraper_resume_state.json"
        self.learner_file = self.root / "Cache" / "System" / "adaptive_rate_learner.json"

        for d in (self.set_checklists_dir, self.checkpoints_dir, self.catalogs_dir, self.ref_dir, self.learner_file.parent):
            d.mkdir(parents=True, exist_ok=True)

        self._patches = [
            mock.patch.object(se, "SET_CHECKLISTS_DIR", self.set_checklists_dir),
            mock.patch.object(se, "CHECKLIST_PATH", self.master_csv),
            mock.patch.object(se, "CACHE_CHECKPOINTS_DIR", self.checkpoints_dir),
            mock.patch.object(se, "CACHE_CATALOGS_DIR", self.catalogs_dir),
            mock.patch.object(se, "SET_LIBRARY_CACHE_DIR", self.root / "Cache" / "Library"),
            mock.patch.object(se, "REFERENCE_TEMPLATES_DIR", self.ref_dir),
            mock.patch.object(se, "DEAD_BACKS_CACHE_FILE", self.dead_backs),
            mock.patch.object(se, "DEAD_FRONTS_CACHE_FILE", self.dead_fronts),
            mock.patch.object(se, "TRACKING_FILE", self.tracked_file),
            mock.patch.object(se, "RESUME_FILE", self.resume_file),
            mock.patch.object(se, "IS_REORGANIZED_V24", True),
            mock.patch.object(cfg, "SET_CHECKLISTS_DIR", self.set_checklists_dir),
            mock.patch.object(cfg, "CHECKLIST_PATH", self.master_csv),
            mock.patch.object(cfg, "CACHE_CHECKPOINTS_DIR", self.checkpoints_dir),
            mock.patch.object(cfg, "REFERENCE_TEMPLATES_DIR", self.ref_dir),
            mock.patch.object(se, "ensure_directories", lambda: None),
            mock.patch.object(se, "connect_session", side_effect=AssertionError("connect_session / Stealth Browser must NEVER be invoked in unit tests")),
            mock.patch.object(se, "cleanup_orphaned_drivers", lambda: None),
            mock.patch.object(se, "SB", None),
            mock.patch.object(se.time, "sleep", lambda _s: None),
            mock.patch.object(rl, "RATE_LEARNER_STATE_FILE", self.learner_file),
            mock.patch.object(rl, "_SINGLETON_LEARNER", rl.AdaptiveRateLearner(state_file=self.learner_file)),
            mock.patch.object(rl.AdaptiveRateLearner, "wait_before_request", lambda _self, _ep: 0.0),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self.env_patch.stop()
        self._tmp.cleanup()

    def test_pagination_safety_truncated_page1_bar(self):
        """Page 1 shows only PageIndex=1..2 in bar, but Next link leads to Page 3, stopping on empty Page 4."""
        p1 = _make_checklist_html([{"cid": "1001", "cnum": "1", "player": "Player One"}], next_page=2, max_page_bar=2)
        p2 = _make_checklist_html([{"cid": "1002", "cnum": "2", "player": "Player Two"}], next_page=3, max_page_bar=2)
        p3 = _make_checklist_html([{"cid": "1003", "cnum": "3", "player": "Player Three"}], next_page=4, max_page_bar=3)
        p4 = "<html><body><table></table></body></html>"
        sess = _StrictMockSession({
            "https://www.tcdb.com/Checklist.cfm/sid/100": _MockResponse(200, p1, url="https://www.tcdb.com/Checklist.cfm/sid/100"),
            "https://www.tcdb.com/Checklist.cfm/sid/100?PageIndex=2": _MockResponse(200, p2, url="https://www.tcdb.com/Checklist.cfm/sid/100?PageIndex=2"),
            "https://www.tcdb.com/Checklist.cfm/sid/100?PageIndex=3": _MockResponse(200, p3, url="https://www.tcdb.com/Checklist.cfm/sid/100?PageIndex=3"),
            "https://www.tcdb.com/Checklist.cfm/sid/100?PageIndex=4": _MockResponse(200, p4, url="https://www.tcdb.com/Checklist.cfm/sid/100?PageIndex=4"),
        })
        rows = self.se._scrape_tcdb_subset_checklist_pages(sess, "https://www.tcdb.com/Checklist.cfm/sid/100", "Base", "2024 Test Set")
        self.assertEqual([r["TCDB_CID"] for r in rows], ["1001", "1002", "1003"])

    def test_canonical_subset_checksum_order_independent(self):
        r1 = {"Card Number": "1", "TCDB_CID": "101", "Player": "A", "Subset": "Base"}
        r2 = {"Card Number": "2", "TCDB_CID": "102", "Player": "B", "Subset": "Base"}
        self.assertEqual(
            self.se.compute_subset_rows_checksum([r1, r2]),
            self.se.compute_subset_rows_checksum([r2, r1]),
        )

    def test_existing_csv_bootstrap_and_incremental_skip(self):
        """Bootstraps checkpoint from existing Set_Checklists CSV when checkpoint JSON is missing, skipping Checklist.cfm."""
        set_name = "2024 Test Set"
        csv_path = self.set_checklists_dir / "2024_Test_Set.csv"
        pd.DataFrame([
            {
                "Set": set_name, "Subset": "Base", "Card Number": "1", "Player": "Alpha",
                "Team": "Team A", "Print Run": "", "Attributes": "", "TCDB_CID": "5001",
                "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "Front Only on TCDB",
            },
            {
                "Set": set_name, "Subset": "Chrome Refractors", "Card Number": "1", "Player": "Alpha",
                "Team": "Team A", "Print Run": "", "Attributes": "", "TCDB_CID": "6001",
                "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "No Image on TCDB",
            },
        ]).to_csv(csv_path, index=False, encoding="utf-8-sig")

        # Only Inserts.cfm should be requested; ZERO Checklist.cfm and ZERO Errors.cfm!
        ins_html = _make_inserts_html([("200", "Chrome Refractors", 1)])
        sess = _StrictMockSession({
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Test-Set": _MockResponse(200, ins_html),
        })
        df, _ = self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Test-Set",
            set_name,
            folder_name="2024_Test_Set",
            progress_ctx={"active_set_base_cards": 1, "completed_cards": 0, "total_cards": 2, "completed_subsets": 0, "total_subsets": 2},
        )
        self.assertEqual(len(df), 2)
        self.assertTrue(all("Checklist.cfm" not in u for u in sess.calls))
        cp = self.se.load_set_checkpoint(set_name)
        self.assertEqual(cp["subsets"]["100"]["status"], "complete")
        self.assertTrue(cp["subsets"]["100"]["bootstrapped_from_csv"])
        self.assertEqual(cp["subsets"]["200"]["status"], "complete")

    def test_incremental_partial_update_and_midset_no_master_merge(self):
        """Only changed/new subsets are fetched; unchanged subsets preserved; mid-set flush never merges Master_Checklist.csv."""
        set_name = "2024 Partial Set"
        base_html = _make_checklist_html([{"cid": "11", "cnum": "1", "player": "Base P1"}])
        ins_a_html = _make_checklist_html([{"cid": "21", "cnum": "1", "player": "InsA P1"}])
        ins_b_html_v1 = _make_checklist_html([{"cid": "31", "cnum": "1", "player": "InsB P1"}])
        ins_b_html_v2 = _make_checklist_html([
            {"cid": "31", "cnum": "1", "player": "InsB P1"},
            {"cid": "32", "cnum": "2", "player": "InsB P2"},
        ])
        ins_c_html = _make_checklist_html([{"cid": "41", "cnum": "1", "player": "InsC P1"}])

        sess1 = _StrictMockSession({
            "https://www.tcdb.com/Checklist.cfm/sid/100/2024-Partial-Set": _MockResponse(200, base_html),
            "https://www.tcdb.com/Errors.cfm/sid/100/2024-Partial-Set": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Partial-Set": _MockResponse(200, _make_inserts_html([("201", "Insert A", 1), ("202", "Insert B", 1)])),
            "https://www.tcdb.com/Checklist.cfm/sid/201/Insert-A": _MockResponse(200, ins_a_html),
            "https://www.tcdb.com/Checklist.cfm/sid/202/Insert-B": _MockResponse(200, ins_b_html_v1),
        })
        df1, _ = self.se.scrape_tcdb_checklist_set(sess1, "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Partial-Set", set_name, folder_name="2024_Partial_Set")
        df1.to_csv(self.set_checklists_dir / "2024_Partial_Set.csv", index=False, encoding="utf-8-sig")

        # Second run: Insert A unchanged (1 card), Insert B changed (1 -> 2 cards), Insert C added (1 card)
        sess2 = _StrictMockSession({
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Partial-Set": _MockResponse(200, _make_inserts_html([
                ("201", "Insert A", 1),
                ("202", "Insert B", 2),
                ("203", "Insert C", 1),
            ])),
            "https://www.tcdb.com/Checklist.cfm/sid/202/Insert-B": _MockResponse(200, ins_b_html_v2),
            "https://www.tcdb.com/Checklist.cfm/sid/203/Insert-C": _MockResponse(200, ins_c_html),
        })
        with mock.patch.object(self.se, "_merge_set_checklist_into_master") as merge_mock:
            df2, _ = self.se.scrape_tcdb_checklist_set(
                sess2,
                "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Partial-Set",
                set_name,
                folder_name="2024_Partial_Set",
                progress_ctx={"active_set_base_cards": 1, "completed_cards": 0, "total_cards": 5, "completed_subsets": 0, "total_subsets": 4},
            )
            merge_mock.assert_not_called()
        self.assertEqual(len(df2), 5)
        self.assertNotIn("https://www.tcdb.com/Checklist.cfm/sid/201/Insert-A", sess2.calls)
        self.assertIn("https://www.tcdb.com/Checklist.cfm/sid/202/Insert-B", sess2.calls)
        self.assertIn("https://www.tcdb.com/Checklist.cfm/sid/203/Insert-C", sess2.calls)

    def test_midset_interruption_and_checkpoint_resume(self):
        """An exception on subset #2 preserves subset #1 in checkpoint so resume skips subset #1."""
        set_name = "2024 Resume Set"
        base_html = _make_checklist_html([{"cid": "11", "cnum": "1", "player": "Base P1"}])
        ins1_html = _make_checklist_html([{"cid": "21", "cnum": "1", "player": "Ins1 P1"}])
        ins2_html = _make_checklist_html([{"cid": "31", "cnum": "1", "player": "Ins2 P1"}])

        def _boom(_url):
            raise self.se.StealthBrowserError("Simulated mid-set interruption")

        sess_fail = _StrictMockSession({
            "https://www.tcdb.com/Checklist.cfm/sid/100/2024-Resume-Set": _MockResponse(200, base_html),
            "https://www.tcdb.com/Errors.cfm/sid/100/2024-Resume-Set": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Resume-Set": _MockResponse(200, _make_inserts_html([("201", "Ins 1", 1), ("202", "Ins 2", 1)])),
            "https://www.tcdb.com/Checklist.cfm/sid/201/Ins-1": _MockResponse(200, ins1_html),
            "https://www.tcdb.com/Checklist.cfm/sid/202/Ins-2": _boom,
        })
        with self.assertRaises(self.se.StealthBrowserError):
            self.se.scrape_tcdb_checklist_set(sess_fail, "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Resume-Set", set_name, folder_name="2024_Resume_Set")

        # Save partial CSV as mid-set flush would, then resume
        pd.DataFrame([
            {"Set": set_name, "Subset": "Base", "Card Number": "1", "Player": "Base P1", "Team": "T", "Print Run": "", "Attributes": "", "TCDB_CID": "11", "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "No Image on TCDB"},
            {"Set": set_name, "Subset": "Ins 1", "Card Number": "1", "Player": "Ins1 P1", "Team": "T", "Print Run": "", "Attributes": "", "TCDB_CID": "21", "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "No Image on TCDB"},
        ]).to_csv(self.set_checklists_dir / "2024_Resume_Set.csv", index=False, encoding="utf-8-sig")

        sess_resume = _StrictMockSession({
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Resume-Set": _MockResponse(200, _make_inserts_html([("201", "Ins 1", 1), ("202", "Ins 2", 1)])),
            "https://www.tcdb.com/Checklist.cfm/sid/202/Ins-2": _MockResponse(200, ins2_html),
        })
        df_res, _ = self.se.scrape_tcdb_checklist_set(
            sess_resume,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Resume-Set",
            set_name,
            folder_name="2024_Resume_Set",
            progress_ctx={"active_set_base_cards": 1, "completed_cards": 0, "total_cards": 3, "completed_subsets": 0, "total_subsets": 3},
        )
        self.assertEqual(len(df_res), 3)
        self.assertEqual(sess_resume.calls, [
            "https://www.tcdb.com/Inserts.cfm/sid/100/2024-Resume-Set",
            "https://www.tcdb.com/Checklist.cfm/sid/202/Ins-2",
        ])

    def test_smart_image_acceleration_and_zero_fabricated_back_probes(self):
        """S-tier front_tier_hint hits Fr.jpg directly (1 call), Front-Only cards never probe Bk.jpg, and missing_back skips empty sets."""
        folder = "2024_Img_Set"
        set_dir = self.ref_dir / folder
        set_dir.mkdir(parents=True, exist_ok=True)
        # Pre-populate CID 7001 front on disk
        f1, _ = self.se.build_template_image_filenames("2024 Img Set", "Base", "1", "OnDisk", "7001")
        (set_dir / f1).write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 512)

        catalog = {
            "Base": {
                "7001": {
                    "cid": "7001", "card_number": "1", "player": "OnDisk", "team": "T",
                    "front_file": f1, "back_file": "b1.jpg",
                    "url_rep_front": "https://www.tcdb.com/Images/Large/2024/7001RepFr.jpg",
                    "url_std_front": "https://www.tcdb.com/Images/Large/2024/7001Fr.jpg",
                    "url_rep_back": "", "url_std_back": "",
                    "front_tier_hint": "S",
                    "referer": "https://www.tcdb.com/Checklist.cfm/sid/100",
                },
                "7002": {
                    "cid": "7002", "card_number": "2", "player": "NeedFront", "team": "T",
                    "front_file": "f2.jpg", "back_file": "b2.jpg",
                    "url_rep_front": "https://www.tcdb.com/Images/Large/2024/7002RepFr.jpg",
                    "url_std_front": "https://www.tcdb.com/Images/Large/2024/7002Fr.jpg",
                    "url_rep_back": "", "url_std_back": "",
                    "front_thumb": "https://www.tcdb.com/Images/Thumbs/2024/7002_Thumb.jpg",
                    "front_tier_hint": "S",
                    "referer": "https://www.tcdb.com/Checklist.cfm/sid/100",
                },
            }
        }
        self.se.save_catalog(folder, catalog)
        jpg_bytes = b"\xff\xd8\xff\xe0" + b"1" * 1024
        sess = _StrictMockSession({
            "https://www.tcdb.com/Images/Large/2024/7002Fr.jpg": _MockResponse(200, content=jpg_bytes),
        })
        with mock.patch.object(self.se, "connect_session", return_value=sess), \
             mock.patch.object(self.se, "sync_set_library_download_status", lambda **_kw: None), \
             mock.patch.object(self.se, "cleanup_orphaned_drivers", lambda: None):
            self.se.mode_download_all_catalog_images(target_queue={"https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Img-Set": folder})

        # Strictly 1 HTTP call (directly to 7002Fr.jpg, zero RepFr 404 probe, zero 7001 call, zero Bk.jpg call)
        self.assertEqual(sess.calls, ["https://www.tcdb.com/Images/Large/2024/7002Fr.jpg"])

        # Missing back audit must NOT open a session or fabricate Bk.jpg when url_*_back are empty
        with mock.patch.object(self.se, "connect_session", side_effect=AssertionError("Should not connect for 0 eligible backs")), \
             mock.patch.object(self.se, "sync_set_library_download_status", lambda **_kw: None):
            self.se.mode_missing_back_audit(target_queue={"https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Img-Set": folder})

    def test_plan_first_execution_preview_zero_network(self):
        """build_scraper_execution_plan computes accurate skip/update/missing image counts with 0 HTTP calls."""
        folder = "2024_Plan_Set"
        set_name = "2024 Plan Set"
        set_url = "https://www.tcdb.com/ViewSet.cfm/sid/100/2024-Plan-Set"
        self.se.save_all_tracked_sets({set_url: {"folder_name": folder, "priority": 1}})

        rows_base = [{"Set": set_name, "Subset": "Base", "Card Number": "1", "Player": "P1", "Team": "T", "Print Run": "", "Attributes": "", "TCDB_CID": "8001", "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "Front Only on TCDB"}]
        pd.DataFrame(rows_base).to_csv(self.set_checklists_dir / f"{folder}.csv", index=False, encoding="utf-8-sig")
        self.se.save_set_checkpoint(set_name, {
            "schema_version": 1,
            "subsets": {
                "100": {
                    "subset_name": "Base", "subset_url": "https://www.tcdb.com/Checklist.cfm/sid/100",
                    "expected_cards": 1, "scraped_cards": 1, "status": "complete",
                    "rows_sha256": self.se.compute_subset_rows_checksum(rows_base),
                }
            },
        })
        self.se.save_catalog(folder, {
            "Base": {
                "8001": {
                    "cid": "8001", "card_number": "1", "player": "P1",
                    "front_file": "8001_F.jpg", "back_file": "8001_B.jpg",
                    "url_rep_front": "https://www.tcdb.com/Images/Large/8001RepFr.jpg",
                    "url_std_front": "https://www.tcdb.com/Images/Large/8001Fr.jpg",
                    "front_tier_hint": "R",
                }
            }
        })

        plan = self.se.build_scraper_execution_plan(target_queue={set_url: folder}, mode_key="checklist_and_images", force_refresh=False)
        self.assertEqual(plan["subsets_unchanged_skipped"], 1)
        self.assertEqual(plan["subsets_to_update"], 0)
        self.assertEqual(plan["missing_front_images_queued"], 1)
        self.assertEqual(plan["missing_back_images_queued"], 0)
        self.assertGreater(plan["estimated_http_requests"], 0)

    def test_plan_all_modes_single_pass_and_mtime_cache_invalidation(self):
        """build_scraper_execution_plan(all_modes=True) returns all 5 modes in 1 pass and caches by file mtime/size."""
        folder = "2024_Cache_Set"
        set_name = "2024 Cache Set"
        set_url = "https://www.tcdb.com/ViewSet.cfm/sid/101/2024-Cache-Set"
        self.se.save_all_tracked_sets({set_url: {"folder_name": folder, "priority": 1}})

        csv_p = self.set_checklists_dir / f"{folder}.csv"
        rows_base = [{"Set": set_name, "Subset": "Base", "Card Number": "1", "Player": "P1", "Team": "T", "Print Run": "", "Attributes": "", "TCDB_CID": "9001", "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "Front & Back on TCDB"}]
        pd.DataFrame(rows_base).to_csv(csv_p, index=False, encoding="utf-8-sig")
        self.se.save_catalog(folder, {
            "Base": {
                "9001": {
                    "cid": "9001", "card_number": "1", "player": "P1",
                    "front_file": "9001_F.jpg", "back_file": "9001_B.jpg",
                    "url_rep_front": "https://www.tcdb.com/Images/Large/9001RepFr.jpg",
                    "url_std_front": "https://www.tcdb.com/Images/Large/9001Fr.jpg",
                    "url_rep_back": "https://www.tcdb.com/Images/Large/9001RepBk.jpg",
                    "url_std_back": "https://www.tcdb.com/Images/Large/9001Bk.jpg",
                    "front_tier_hint": "R", "back_tier_hint": "R",
                }
            }
        })

        res1 = self.se.build_scraper_execution_plan(target_queue={set_url: folder}, mode_key="checklist_only", all_modes=True)
        pbm = res1["plans_by_mode"]
        for mk in ("checklist_only", "checklist_and_images", "images_only", "upgrade", "image_update", "missing_back"):
            self.assertIn(mk, pbm)
        self.assertEqual(pbm["checklist_only"]["subsets_unchanged_skipped"], 1)
        self.assertEqual(pbm["checklist_and_images"]["missing_front_images_queued"], 1)
        self.assertEqual(pbm["checklist_and_images"]["missing_back_images_queued"], 1)
        self.assertEqual(pbm["images_only"]["missing_images_queued"], 2)

        # Second call with unchanged files MUST hit mtime/size cache (0 CSV re-parses)
        with mock.patch.object(self.se, "_fast_scan_set_csv_for_plan", side_effect=AssertionError("Should hit mtime cache!")) as _:
            res2 = self.se.build_scraper_execution_plan(target_queue={set_url: folder}, mode_key="images_only", all_modes=True)
        self.assertEqual(res2["plan"]["missing_images_queued"], 2)

        # Modify CSV (new subset row + different size/mtime) -> cache must invalidate and re-scan
        rows_updated = rows_base + [{"Set": set_name, "Subset": "Inserts", "Card Number": "1", "Player": "P2", "Team": "T", "Print Run": "", "Attributes": "", "TCDB_CID": "9002", "Front_Downloaded": "No", "Back_Downloaded": "No", "TCDB_Image_Status": "No Image on TCDB"}]
        pd.DataFrame(rows_updated).to_csv(csv_p, index=False, encoding="utf-8-sig")
        res3 = self.se.build_scraper_execution_plan(target_queue={set_url: folder}, mode_key="checklist_only", all_modes=True)
        self.assertEqual(res3["plans_by_mode"]["checklist_only"]["subsets_unchanged_skipped"], 2)


if __name__ == "__main__":
    unittest.main()
