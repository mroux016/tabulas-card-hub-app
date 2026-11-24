from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class DirectoryAndTrackedOverhaulTests(unittest.TestCase):
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
        import Core.scraper_engine as se

        self.cfg = cfg
        self.se = se

        self.cache_dir = self.root / "Cache" / "Checklists"
        self.data_dir = self.root / "Data" / "Checklists_and_Resources"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tracking_file = self.cache_dir / "tracked_sets.json"
        self.dir_file = self.data_dir / "TCDB_Set_Directory.csv"

        self._patches = [
            mock.patch.object(se, "TRACKING_FILE", self.tracking_file),
            mock.patch.object(se, "MASTER_DIRECTORY_FILE", self.dir_file),
            mock.patch.object(se, "SET_CART_FILE", self.cache_dir / "tcdb_set_cart.json"),
        ]
        for p in self._patches:
            p.start()
        se._DIR_RELEASE_DATE_CACHE.update({"mtime": -1.0, "by_sid": {}, "by_key": {}})

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self.env_patch.stop()
        self._tmp.cleanup()

    def test_release_date_extraction_from_viewset_html(self):
        html_dl = """
        <html><body>
          <dl class="dl-horizontal">
            <dt>Release Date</dt><dd>February 12, 2025</dd>
            <dt>Cards</dt><dd>350</dd>
          </dl>
        </body></html>
        """
        iso, unrel = self.se.extract_release_date_from_viewset_html(html_dl)
        self.assertEqual(iso, "2025-02-12")
        self.assertFalse(unrel)

        html_tbl = """
        <html><body>
          <table>
            <tr><th>Expected Release Date:</th><td>03/19/2027</td></tr>
          </table>
        </body></html>
        """
        iso2, unrel2 = self.se.extract_release_date_from_viewset_html(html_tbl)
        self.assertEqual(iso2, "2027-03-19")
        self.assertFalse(unrel2)

        html_unrel = """
        <html><body>
          <p><strong>Release Date:</strong> TBD (Not Yet Released)</p>
        </body></html>
        """
        iso3, unrel3 = self.se.extract_release_date_from_viewset_html(html_unrel)
        self.assertEqual(iso3, "")
        self.assertTrue(unrel3)

    def test_pre_release_future_date_classification(self):
        ref = date(2026, 6, 15)
        future_iso = (ref + timedelta(days=30)).isoformat()
        past_iso = (ref - timedelta(days=30)).isoformat()

        self.assertTrue(self.se.is_pre_release_set(future_iso, reference_date=ref))
        self.assertEqual(self.se.compute_set_release_status(future_iso, reference_date=ref), "Pre-Release")

        self.assertFalse(self.se.is_pre_release_set(past_iso, reference_date=ref))
        self.assertEqual(self.se.compute_set_release_status(past_iso, reference_date=ref), "Released")

        self.assertFalse(self.se.is_pre_release_set(ref.isoformat(), reference_date=ref))
        self.assertTrue(self.se.is_pre_release_set("", is_unreleased_flag=True, reference_date=ref))
        self.assertEqual(self.se.compute_set_release_status("", is_unreleased_flag=True, reference_date=ref), "Pre-Release")

    def test_newest_to_oldest_and_alphabetical_sorting(self):
        rows = [
            {"Set_Name": "2024_Topps_Chrome", "Release_Date": ""},
            {"Set_Name": "2025_Bowman_Draft", "Release_Date": "2025-12-01"},
            {"Set_Name": "2025_Topps_Series_1", "Release_Date": "2025-02-12"},
            {"Set_Name": "2025_Donruss_Baseball", "Release_Date": "2025-02-12"},
            {"Set_Name": "2023_Select_Football", "Release_Date": ""},
        ]
        sorted_rows = self.se.sort_sets_by_release_date(rows, date_key="Release_Date", name_key="Set_Name")
        self.assertEqual(
            [r["Set_Name"] for r in sorted_rows],
            [
                "2025_Bowman_Draft",
                "2025_Donruss_Baseball",
                "2025_Topps_Series_1",
                "2023_Select_Football",
                "2024_Topps_Chrome",
            ],
        )

    def test_brand_normalization_consistency(self):
        cases = [
            ("2025 Donruss Baseball", "", "", "Donruss"),
            ("2025 Panini Donruss Optic Football", "", "Panini", "Optic"),
            ("2025 Panini Prizm Basketball", "", "Panini", "Prizm"),
            ("2025 Panini Select Football", "", "Panini", "Select"),
            ("2025 Bowman Chrome Baseball", "", "Topps", "Bowman"),
            ("2025 Topps Chrome Baseball", "", "", "Topps"),
            ("2024 Topps Finest Baseball", "", "Topps", "Finest"),
            ("2024-25 Upper Deck Series 1 Hockey", "", "", "Upper Deck"),
            ("1989 Fleer Baseball", "", "", "Fleer"),
            ("2025 Panini Instant NFL", "", "", "Panini"),
        ]
        for title, url, existing, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(self.cfg.normalize_brand_name(title, url=url, existing_mfg=existing), expected)
                self.assertEqual(self.se._infer_manufacturer(title, url=url, existing_mfg=existing), expected)

    def test_underscore_display_masking_preserves_storage_keys(self):
        self.assertEqual(self.cfg.format_display_set_name("2025_Topps_Series_1_Baseball"), "2025 Topps Series 1 Baseball")

        u = "https://www.tcdb.com/ViewSet.cfm/sid/999001/2025-Donruss-Baseball"
        self.se.save_all_tracked_sets({
            u: {
                "folder_name": "2025_Donruss_Baseball",
                "sport": "Baseball",
                "year": "2025",
                "manufacturer": "Panini",
                "release_date": "2025-03-05",
            }
        })
        raw_saved = json.loads(self.tracking_file.read_text(encoding="utf-8"))
        self.assertEqual(raw_saved[u]["folder_name"], "2025_Donruss_Baseball")
        self.assertEqual(raw_saved[u]["manufacturer"], "Donruss")
        self.assertEqual(raw_saved[u]["release_date"], "2025-03-05")

        # Also verify directory persistence round-trip
        df_init = pd.DataFrame([{
            "SID": "999001",
            "Year": "2025",
            "Era": "2025",
            "Sport": "Baseball",
            "Set_Name": "2025 Donruss Baseball",
            "Manufacturer": "Panini",
            "Category": "Major Releases",
            "Release_Date": "",
            "Release_Status": "",
            "Image_Pct": "50%",
            "Folder_Name": "2025_Donruss_Baseball",
            "TCDB_URL": u,
            "Last_Crawled": "2026-11-23",
        }], columns=self.se.MASTER_DIRECTORY_COLUMNS)
        df_init.to_csv(self.dir_file, index=False, encoding="utf-8-sig")

        self.se.persist_set_release_date(u, "2028-04-01", is_unreleased=False)
        df_after = pd.read_csv(self.dir_file, dtype=str, keep_default_na=False)
        self.assertEqual(df_after.loc[0, "Release_Date"], "2028-04-01")
        self.assertEqual(df_after.loc[0, "Release_Status"], "Pre-Release")
        self.assertEqual(df_after.loc[0, "Manufacturer"], "Donruss")
        self.assertEqual(df_after.loc[0, "Folder_Name"], "2025_Donruss_Baseball")

    def test_app_jsx_classic_babel_and_ui_requirements(self):
        app_src = (REPO_ROOT / "App.jsx").read_text(encoding="utf-8")
        # Only line 2 may have the classic bootloader React import; zero new ES imports/exports
        import_lines = [ln for ln in app_src.splitlines() if re.match(r"^\s*import\s+", ln)]
        self.assertEqual(len(import_lines), 1, f"Unexpected ES imports: {import_lines}")
        export_lines = [ln for ln in app_src.splitlines() if re.match(r"^\s*export\s+(?!default\s+function\s+App\b)", ln)]
        self.assertEqual(export_lines, [], f"Unexpected ES exports: {export_lines}")

        # Default Categories filter in Master Set Directory
        self.assertIn("useState(['Major Releases', 'On-Demand'])", app_src)
        # Maintenance moved out of Checklist Builder into Developer Tools
        cb_start = app_src.index("activePage === 'checklist_builder'")
        cb_end = app_src.index("activePage === 'unified_checklist_viewer'")
        self.assertNotIn("showMaintenanceWidget", app_src[cb_start:cb_end])
        dev_start = app_src.index("title=\"Developer & Debugging Tools\"")
        self.assertIn("showMaintenanceWidget", app_src[dev_start:])
        # Folder Name column hidden from Master Set Directory table
        dir_start = app_src.index("activePage === 'set_browser'")
        dir_end = app_src.index("activePage === 'grading_engine'")
        dir_block = app_src[dir_start:dir_end]
        self.assertNotIn(">Folder Name<", dir_block)
        self.assertIn("Pre-Release", dir_block)


if __name__ == "__main__":
    unittest.main()
