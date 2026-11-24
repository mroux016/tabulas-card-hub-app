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
        return val(url) if callable(val) else val


def _make_checklist_html(
    sid: str,
    rows_spec: list[dict],
    page_num: int = 1,
    total_pages: int = 1,
    total_cards_banner: int | None = None,
) -> str:
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
            f'<td><a href="/ViewCard.cfm/sid/{sid}/cid/{cid}/card-{cnum}">{cnum}</a></td>'
            f'<td><a href="/Person.cfm/pid/{cid}">{plr}</a> {tags}</td>'
            f'<td><a href="/Team.cfm/tid/1">{team}</a></td>'
            f"</tr>"
        )
    nav_links = [
        f'<a href="/Checklist.cfm/sid/{sid}?PageIndex={p}">{p}</a>'
        for p in range(1, total_pages + 1)
    ]
    if page_num < total_pages:
        nav_links.append(f'<a href="/Checklist.cfm/sid/{sid}?PageIndex={page_num + 1}">Next</a>')
    banner = f"<div>Showing 1 - {len(rows_spec)} of {total_cards_banner}</div>" if total_cards_banner else ""
    return f"<html><body>{banner}<div>{' '.join(nav_links)}</div><table>{''.join(trs)}</table></body></html>"


def _make_inserts_html(inserts: list[tuple[str, str, int]]) -> str:
    trs = []
    for sid, name, cnt in inserts:
        slug = name.replace(" ", "-")
        trs.append(f'<tr><td><a href="/Checklist.cfm/sid/{sid}/{slug}">{name}</a></td><td>{cnt} cards</td></tr>')
    return f"<html><body><table>{''.join(trs)}</table></body></html>"


def _build_base_350_spec(cid_start: int = 10001) -> list[dict]:
    specs: list[dict] = []
    for i in range(350):
        cnum = str(i + 1)
        cid = str(cid_start + i)
        if i in (150, 151):
            specs.append({
                "cid": cid,
                "cnum": cnum,
                "player": f"2026 NL Home Run Leaders #{cnum}",
                "team": "NO TEAM",
                "tags": "LL",
            })
        elif i in (5, 220):
            specs.append({
                "cid": cid,
                "cnum": cnum,
                "player": f"Rookie Star {cnum}",
                "team": "New York Yankees",
                "tags": "RC",
            })
        else:
            specs.append({
                "cid": cid,
                "cnum": cnum,
                "player": f"Base Player {cnum}",
                "team": "Los Angeles Dodgers",
                "tags": "",
            })
    return specs


def _paginate_routes(
    sid: str,
    slug: str,
    specs: list[dict],
    page_size: int = 100,
    include_pages: set[int] | None = None,
) -> dict[str, _MockResponse]:
    total = len(specs)
    total_pages = (total + page_size - 1) // page_size
    routes: dict[str, _MockResponse] = {}
    base_url = f"https://www.tcdb.com/Checklist.cfm/sid/{sid}/{slug}"
    for p in range(1, total_pages + 1):
        if include_pages is not None and p not in include_pages:
            continue
        chunk = specs[(p - 1) * page_size : p * page_size]
        url = base_url if p == 1 else f"{base_url}?PageIndex={p}"
        html = _make_checklist_html(
            sid,
            chunk,
            page_num=p,
            total_pages=total_pages,
            total_cards_banner=total if p == 1 else None,
        )
        routes[url] = _MockResponse(200, html, url=url)
    return routes


class StrictCidInterpolationTests(unittest.TestCase):
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

        for d in (
            self.set_checklists_dir,
            self.checkpoints_dir,
            self.catalogs_dir,
            self.ref_dir,
            self.learner_file.parent,
        ):
            d.mkdir(parents=True, exist_ok=True)

        self.logs: list[str] = []
        se.set_log_callback(self.logs.append)

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
            mock.patch.object(
                se,
                "connect_session",
                side_effect=AssertionError("connect_session must NEVER be called in unit tests"),
            ),
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
        self.se.set_log_callback(None)
        for p in reversed(self._patches):
            p.stop()
        self.env_patch.stop()
        self._tmp.cleanup()

    def test_full_350_card_base_parallel_with_league_leaders(self):
        """350-card Base + Rainbow Foil parallel (with LL & RC rows) interpolates from Page 1 + Page 4 only."""
        base_specs = _build_base_350_spec(10001)
        rf_specs = _build_base_350_spec(20001)

        routes = {
            **_paginate_routes("100", "2026-Test-Baseball", base_specs, page_size=100),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Test-Baseball": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Test-Baseball": _MockResponse(
                200,
                _make_inserts_html([("200", "Rainbow Foil", 350)]),
            ),
            # Only Page 1 and Page 4 exist for Rainbow Foil; requesting Page 2 or Page 3 raises StealthBrowserError
            **_paginate_routes("200", "Rainbow-Foil", rf_specs, page_size=100, include_pages={1, 4}),
        }
        sess = _StrictMockSession(routes)
        df, _ = self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Test-Baseball",
            "2026 Test Baseball",
            folder_name="2026_Test_Baseball",
            progress_ctx={"active_set_base_cards": 350, "completed_cards": 0, "total_cards": 700, "completed_subsets": 0, "total_subsets": 2},
        )

        self.assertEqual(list(df.columns), self.cfg.CHECKLIST_COLUMNS)
        rf_df = df[df["Subset"] == "Rainbow Foil"].copy()
        self.assertEqual(len(rf_df), 350)
        self.assertEqual(rf_df.iloc[0]["TCDB_CID"], "20001")
        self.assertEqual(rf_df.iloc[-1]["TCDB_CID"], "20350")
        # Middle League Leader & Rookie rows inherited accurately
        ll_row = rf_df[rf_df["Card Number"] == "151"].iloc[0]
        self.assertEqual(ll_row["TCDB_CID"], "20151")
        self.assertIn("LL", ll_row["Attributes"])
        self.assertEqual(ll_row["TCDB_Image_Status"], "Interpolated (Unchecked)")

        rc_row = rf_df[rf_df["Card Number"] == "221"].iloc[0]
        self.assertEqual(rc_row["TCDB_CID"], "20221")
        self.assertIn("RC", rc_row["Attributes"])

        # Catalog tags middle rows with image_source="interpolated"
        cat = self.se.load_catalog("2026_Test_Baseball")
        self.assertEqual(cat["Rainbow Foil"]["20151"]["image_source"], "interpolated")
        self.assertEqual(cat["Rainbow Foil"]["20001"]["image_source"], "parsed")

        # Verify zero middle pages requested
        self.assertNotIn("https://www.tcdb.com/Checklist.cfm/sid/200/Rainbow-Foil?PageIndex=2", sess.calls)
        self.assertNotIn("https://www.tcdb.com/Checklist.cfm/sid/200/Rainbow-Foil?PageIndex=3", sess.calls)

        log_blob = "\n".join(self.logs)
        self.assertIn("[INTERPOLATED] Rainbow Foil (350 cards, CID 20001..20350, skipped 2 middle page(s))", log_blob)
        self.assertIn("1 interpolated, 2 page(s) saved", log_blob)

    def test_insert_parallel_interpolates_from_parent_insert(self):
        """Multi-page Insert parallel ('Big Ticket Players Gold Foil', 26 cards) interpolates from parent insert."""
        base_specs = [{"cid": str(100 + i), "cnum": str(i + 1), "player": f"Base P{i+1}"} for i in range(10)]
        btp_specs = [{"cid": str(30001 + i), "cnum": f"BTP-{i+1}", "player": f"Ticket Star {i+1}"} for i in range(26)]
        btp_gold_specs = [
            {"cid": str(40001 + i), "cnum": f"BTP-{i+1}", "player": f"Ticket Star {i+1}", "tags": "SN50"}
            for i in range(26)
        ]

        routes = {
            **_paginate_routes("100", "2026-Insert-Test", base_specs, page_size=10),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Insert-Test": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Insert-Test": _MockResponse(
                200,
                _make_inserts_html([
                    ("300", "Big Ticket Players", 26),
                    ("301", "Big Ticket Players Gold Foil", 26),
                ]),
            ),
            **_paginate_routes("300", "Big-Ticket-Players", btp_specs, page_size=10),
            # Only Page 1 and Page 3 exist for Gold Foil (1 middle page skipped)
            **_paginate_routes("301", "Big-Ticket-Players-Gold-Foil", btp_gold_specs, page_size=10, include_pages={1, 3}),
        }
        sess = _StrictMockSession(routes)
        df, _ = self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Insert-Test",
            "2026 Insert Test",
            folder_name="2026_Insert_Test",
            progress_ctx={"active_set_base_cards": 10, "completed_cards": 0, "total_cards": 62, "completed_subsets": 0, "total_subsets": 3},
        )
        gold_df = df[df["Subset"] == "Big Ticket Players Gold Foil"]
        self.assertEqual(len(gold_df), 26)
        mid_row = gold_df[gold_df["Card Number"] == "BTP-15"].iloc[0]
        self.assertEqual(mid_row["TCDB_CID"], "40015")
        self.assertEqual(mid_row["Player"], "Ticket Star 15")
        self.assertEqual(mid_row["Print Run"], "50")
        self.assertNotIn("https://www.tcdb.com/Checklist.cfm/sid/301/Big-Ticket-Players-Gold-Foil?PageIndex=2", sess.calls)

        log_blob = "\n".join(self.logs)
        self.assertIn("[INTERPOLATED] Big Ticket Players Gold Foil (26 cards, CID 40001..40026, skipped 1 middle page(s))", log_blob)

        # Also verify interpolation works when Big Ticket Players is loaded from existing local CSV (incremental skip)
        df.to_csv(self.set_checklists_dir / "2026_Insert_Test.csv", index=False, encoding="utf-8-sig")
        self.logs.clear()
        btp_red_specs = [
            {"cid": str(50001 + i), "cnum": f"BTP-{i+1}", "player": f"Ticket Star {i+1}", "tags": "SN5"}
            for i in range(26)
        ]
        sess2 = _StrictMockSession({
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Insert-Test": _MockResponse(
                200,
                _make_inserts_html([
                    ("300", "Big Ticket Players", 26),
                    ("301", "Big Ticket Players Gold Foil", 26),
                    ("302", "Big Ticket Players Red Foil", 26),
                ]),
            ),
            **_paginate_routes("302", "Big-Ticket-Players-Red-Foil", btp_red_specs, page_size=10, include_pages={1, 3}),
        })
        df2, _ = self.se.scrape_tcdb_checklist_set(
            sess2,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Insert-Test",
            "2026 Insert Test",
            folder_name="2026_Insert_Test",
            progress_ctx={"active_set_base_cards": 10, "completed_cards": 0, "total_cards": 88, "completed_subsets": 0, "total_subsets": 4},
        )
        red_df = df2[df2["Subset"] == "Big Ticket Players Red Foil"]
        self.assertEqual(len(red_df), 26)
        self.assertEqual(red_df[red_df["Card Number"] == "BTP-12"].iloc[0]["TCDB_CID"], "50012")
        self.assertIn("[INTERPOLATED] Big Ticket Players Red Foil (26 cards, CID 50001..50026, skipped 1 middle page(s))", "\n".join(self.logs))

    def test_fallback_on_single_cid_gap(self):
        """1-CID gap in the middle triggers automatic fallback to full paginated scraping."""
        base_specs = _build_base_350_spec(10001)
        gold_specs = _build_base_350_spec(25001)
        # Introduce a +1 CID gap starting at index 150 (last_cid becomes 25351 -> span=351 vs count=350)
        for item in gold_specs[150:]:
            item["cid"] = str(int(item["cid"]) + 1)

        routes = {
            **_paginate_routes("100", "2026-Gap-Test", base_specs, page_size=100),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Gap-Test": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Gap-Test": _MockResponse(
                200,
                _make_inserts_html([("201", "Gold", 350)]),
            ),
            **_paginate_routes("201", "Gold", gold_specs, page_size=100),
        }
        sess = _StrictMockSession(routes)
        df, _ = self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Gap-Test",
            "2026 Gap Test",
            folder_name="2026_Gap_Test",
            progress_ctx={"active_set_base_cards": 350, "completed_cards": 0, "total_cards": 700, "completed_subsets": 0, "total_subsets": 2},
        )
        gold_df = df[df["Subset"] == "Gold"]
        self.assertEqual(len(gold_df), 350)
        self.assertIn("https://www.tcdb.com/Checklist.cfm/sid/201/Gold?PageIndex=2", sess.calls)
        self.assertIn("https://www.tcdb.com/Checklist.cfm/sid/201/Gold?PageIndex=3", sess.calls)
        # Page 4 was cached during probe and reused without a duplicate HTTP GET
        self.assertEqual(sess.calls.count("https://www.tcdb.com/Checklist.cfm/sid/201/Gold?PageIndex=4"), 1)
        self.assertIn("[FALLBACK: cid_gap] Gold (span=351 vs count=350)", "\n".join(self.logs))

    def test_fallback_on_partial_parallel_count_mismatch(self):
        """Partial parallel (100 cards vs 350 Base) logs count_mismatch and skips interpolation."""
        base_specs = _build_base_350_spec(10001)
        vs_specs = _build_base_350_spec(30001)[:100]

        routes = {
            **_paginate_routes("100", "2026-Partial-Test", base_specs, page_size=100),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Partial-Test": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Partial-Test": _MockResponse(
                200,
                _make_inserts_html([("202", "Vintage Stock", 100)]),
            ),
            **_paginate_routes("202", "Vintage-Stock", vs_specs, page_size=100),
        }
        sess = _StrictMockSession(routes)
        df, _ = self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Partial-Test",
            "2026 Partial Test",
            folder_name="2026_Partial_Test",
            progress_ctx={"active_set_base_cards": 350, "completed_cards": 0, "total_cards": 450, "completed_subsets": 0, "total_subsets": 2},
        )
        vs_df = df[df["Subset"] == "Vintage Stock"]
        self.assertEqual(len(vs_df), 100)
        self.assertIn("[FALLBACK: count_mismatch] Vintage Stock (parallel=100 vs parent=350)", "\n".join(self.logs))

    def test_fallback_on_boundary_order_mismatch(self):
        """Contiguous CIDs with mismatched boundary card number triggers order_mismatch fallback."""
        base_specs = _build_base_350_spec(10001)
        sg_specs = _build_base_350_spec(35001)
        # Swap card numbers on Page 1 position 1 and 2 while keeping CIDs strictly contiguous
        sg_specs[1]["cnum"], sg_specs[2]["cnum"] = sg_specs[2]["cnum"], sg_specs[1]["cnum"]

        routes = {
            **_paginate_routes("100", "2026-Order-Test", base_specs, page_size=100),
            "https://www.tcdb.com/Errors.cfm/sid/100/2026-Order-Test": _MockResponse(404, ""),
            "https://www.tcdb.com/Inserts.cfm/sid/100/2026-Order-Test": _MockResponse(
                200,
                _make_inserts_html([("203", "Sandglitter", 350)]),
            ),
            **_paginate_routes("203", "Sandglitter", sg_specs, page_size=100),
        }
        sess = _StrictMockSession(routes)
        df, _ = self.se.scrape_tcdb_checklist_set(
            sess,
            "https://www.tcdb.com/ViewSet.cfm/sid/100/2026-Order-Test",
            "2026 Order Test",
            folder_name="2026_Order_Test",
            progress_ctx={"active_set_base_cards": 350, "completed_cards": 0, "total_cards": 700, "completed_subsets": 0, "total_subsets": 2},
        )
        sg_df = df[df["Subset"] == "Sandglitter"]
        self.assertEqual(len(sg_df), 350)
        self.assertIn("https://www.tcdb.com/Checklist.cfm/sid/203/Sandglitter?PageIndex=2", sess.calls)
        self.assertIn("https://www.tcdb.com/Checklist.cfm/sid/203/Sandglitter?PageIndex=3", sess.calls)
        self.assertIn("[FALLBACK: order_mismatch] Sandglitter (boundary card numbers differ from parent)", "\n".join(self.logs))


if __name__ == "__main__":
    unittest.main()
