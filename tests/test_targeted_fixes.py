from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _FakeHandler:
    """Minimal mock of _TabulasPythonApiAndReactHandler for isolated endpoint tests."""

    @staticmethod
    def create(hub_mod):
        class _Handler(hub_mod._TabulasPythonApiAndReactHandler):
            def __init__(self):
                self.responses = []
                self.wfile = io.BytesIO()
                self.headers = {}
                self.rfile = io.BytesIO()

            def _send_json(self, data, status: int = 200):
                self.responses.append((status, data))

        return _Handler()


class TargetedFixesTests(unittest.TestCase):
    def test_tcdb_checklist_row_preserves_erick_the_architect_and_stage_names(self):
        from Core.scraper_engine import (
            _strip_inline_tags_errors_and_occupations,
            parse_tcdb_checklist_table_rows,
        )

        # Direct helper checks for stage names vs real occupation suffixes
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("Erick the Architect", team_str="NO TEAM")[0],
            "Erick the Architect",
        )
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("Erick the Architect Rapper", team_str="NO TEAM")[0],
            "Erick the Architect",
        )
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("The Undertaker", team_str="NO TEAM")[0],
            "The Undertaker",
        )
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("Chance the Rapper", team_str="NO TEAM")[0],
            "Chance the Rapper",
        )
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("Tyler, The Creator", team_str="NO TEAM")[0],
            "Tyler, The Creator",
        )
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("David Spade Comedian, Actor", team_str="NO TEAM")[0],
            "David Spade",
        )
        self.assertEqual(
            _strip_inline_tags_errors_and_occupations("Aaron Judge", team_str="New York Yankees")[0],
            "Aaron Judge",
        )

        # Full HTML <tr> parsing (both Person.cfm linked and unlinked non-athlete rows)
        html = """
        <table>
          <tr>
            <td><a href="/ViewCard.cfm/sid/600001/cid/40000001/2026-Topps-Allen-&amp;-Ginter-32-Erick-the-Architect">32</a></td>
            <td><a href="/Person.cfm/pid/99001/Erick-the-Architect">Erick the Architect</a> Rapper</td>
            <td></td>
          </tr>
          <tr>
            <td><a href="/ViewCard.cfm/sid/600001/cid/40000002/2026-Topps-Allen-&amp;-Ginter-33-Erick-the-Architect">33</a></td>
            <td>Erick the Architect</td>
            <td></td>
          </tr>
          <tr>
            <td><a href="/ViewCard.cfm/sid/600001/cid/40000003/2026-Topps-Allen-&amp;-Ginter-99-Aaron-Judge">99</a></td>
            <td><a href="/Person.cfm/pid/10001/Aaron-Judge">Aaron Judge</a></td>
            <td><a href="/Team.cfm/tid/19/New-York-Yankees">New York Yankees</a></td>
          </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = parse_tcdb_checklist_table_rows(soup, subset_name="Base")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Card Number"], "32")
        self.assertEqual(rows[0]["Player"], "Erick the Architect")
        self.assertEqual(rows[0]["Team"], "NO TEAM")
        self.assertEqual(rows[1]["Card Number"], "33")
        self.assertEqual(rows[1]["Player"], "Erick the Architect")
        self.assertEqual(rows[2]["Player"], "Aaron Judge")
        self.assertEqual(rows[2]["Team"], "New York Yankees")

    def test_audit_and_repair_inventory_names_endpoints(self):
        import Core.config as cfg
        import Core.database as db
        import launch_tabulas_hub as hub

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inv_csv = root / "Inventory.csv"
            chk_csv = root / "Master_Checklist.csv"
            reviewed_dir = root / "_My_Collection"
            set_name = "2025 Topps Baseball"
            set_dir = reviewed_dir / cfg.sanitize_filename_part(set_name)
            set_dir.mkdir(parents=True, exist_ok=True)

            # Build Master_Checklist.csv with unambiguous + ambiguous rows
            chk_rows = [
                {
                    "Set": set_name,
                    "Subset": "Base",
                    "Card Number": "10",
                    "Player": "Heliot Ramos",
                    "Team": "San Francisco Giants",
                },
                {
                    "Set": set_name,
                    "Subset": "Base",
                    "Card Number": "15",
                    "Player": "Ronald Acuna Jr",
                    "Team": "Atlanta Braves",
                },
                {
                    "Set": set_name,
                    "Subset": "Base",
                    "Card Number": "20",
                    "Player": "Aaron Judge",
                    "Team": "New York Yankees",
                },
                # Ambiguous (2 rows for same Set + Subset + Card Number)
                {
                    "Set": set_name,
                    "Subset": "Base",
                    "Card Number": "99",
                    "Player": "Player A",
                    "Team": "Team A",
                },
                {
                    "Set": set_name,
                    "Subset": "Base",
                    "Card Number": "99",
                    "Player": "Player B",
                    "Team": "Team B",
                },
            ]
            pd.DataFrame(chk_rows).to_csv(chk_csv, index=False, encoding="utf-8-sig")

            # Create _F, _B, _C files for 1000001 (Jung Hoo Lee -> Heliot Ramos)
            old_f, old_b, old_c = cfg.build_card_image_filenames(set_name, "Base", "10", "Jung Hoo Lee", "1000001")
            (set_dir / old_f).write_bytes(b"FRONT_BYTES_1")
            (set_dir / old_b).write_bytes(b"BACK_BYTES_1")
            (set_dir / old_c).write_bytes(b"CORNERS_BYTES_1")

            # Create _F file for 1000002 (Ronald Acuna Jr. -> Ronald Acuna Jr)
            old2_f, old2_b, old2_c = cfg.build_card_image_filenames(set_name, "Base", "15", "Ronald Acuna Jr.", "1000002")
            (set_dir / old2_f).write_bytes(b"FRONT_BYTES_2")

            inv_rows = []
            for idx_row, (sku, cnum, player, team, ff, bf, cf) in enumerate([
                ("1000001", "10", "Jung Hoo Lee", "Old Team", old_f, old_b, old_c),
                ("1000002", "15", "Ronald Acuna Jr.", "Atlanta Braves", old2_f, "", ""),
                ("1000003", "20", "Aaron Judge", "New York Yankees", "", "", ""),
                ("1000004", "99", "Wrong Name", "Team X", "", "", ""),
            ]):
                rec = {col: "" for col in cfg.INVENTORY_COLUMNS}
                rec.update({
                    "SKU": sku,
                    "Status": "In Inventory",
                    "Set": set_name,
                    "Subset": "Base",
                    "Card Number": cnum,
                    "Player": player,
                    "Team": team,
                    "Front_File": ff,
                    "Back_File": bf,
                    "Corners_File": cf,
                    "Label_Printed": "True",
                })
                inv_rows.append(rec)
            pd.DataFrame(inv_rows, columns=cfg.INVENTORY_COLUMNS).to_csv(inv_csv, index=False, encoding="utf-8-sig")

            logged_actions = []
            with mock.patch.object(cfg, "INVENTORY_FILE", inv_csv), \
                 mock.patch.object(db, "INVENTORY_FILE", inv_csv), \
                 mock.patch.object(hub, "INVENTORY_FILE", inv_csv), \
                 mock.patch.object(cfg, "CHECKLIST_PATH", chk_csv), \
                 mock.patch.object(cfg, "SET_CHECKLISTS_DIR", root / "Set_Checklists"), \
                 mock.patch.object(cfg, "REVIEWED_CARDS_DIR", reviewed_dir), \
                 mock.patch.object(db, "REVIEWED_CARDS_DIR", reviewed_dir), \
                 mock.patch.object(hub, "_log_ui_action_to_file", lambda cat, act, det="": logged_actions.append((cat, act, det))):

                # 1. GET /api/maintenance/audit-inventory-names
                h_get = _FakeHandler.create(hub)
                h_get.path = "/api/maintenance/audit-inventory-names"
                h_get.do_GET()
                self.assertEqual(h_get.responses[0][0], 200)
                audit = h_get.responses[0][1]
                self.assertTrue(audit["success"])
                self.assertEqual(audit["total_inventory"], 4)
                self.assertEqual(audit["matched_unique"], 3)
                self.assertEqual(audit["ambiguous_skipped"], 1)
                self.assertEqual(audit["mismatch_count"], 2)
                self.assertEqual(audit["name_mismatch_count"], 1)
                self.assertEqual(audit["punctuation_only_count"], 1)

                by_sku = {m["sku"]: m for m in audit["mismatches"]}
                self.assertEqual(by_sku["1000001"]["category"], "name_mismatch")
                self.assertEqual(by_sku["1000001"]["checklist_player"], "Heliot Ramos")
                self.assertEqual(by_sku["1000002"]["category"], "punctuation_only")
                self.assertEqual(by_sku["1000002"]["checklist_player"], "Ronald Acuna Jr")

                # 2. POST /api/maintenance/repair-inventory-names for 1000001 only (1000002 excluded)
                body = json.dumps({"skus": ["1000001"]}).encode("utf-8")
                h_post = _FakeHandler.create(hub)
                h_post.path = "/api/maintenance/repair-inventory-names"
                h_post.headers = {"Content-Length": str(len(body))}
                h_post.rfile = io.BytesIO(body)
                h_post.do_POST()
                self.assertEqual(h_post.responses[0][0], 200)
                rep = h_post.responses[0][1]
                self.assertTrue(rep["success"])
                self.assertEqual(rep["repaired_count"], 1)
                self.assertEqual(rep["renamed_files_count"], 3)
                self.assertEqual(rep["repaired_skus"], ["1000001"])

                # Verify CSV updates
                updated_df = pd.read_csv(inv_csv, dtype=str, keep_default_na=False)
                row1 = updated_df[updated_df["SKU"] == "1000001"].iloc[0]
                row2 = updated_df[updated_df["SKU"] == "1000002"].iloc[0]
                new_f, new_b, new_c = cfg.build_card_image_filenames(set_name, "Base", "10", "Heliot Ramos", "1000001")
                self.assertEqual(row1["Player"], "Heliot Ramos")
                self.assertEqual(row1["Team"], "San Francisco Giants")
                self.assertEqual(row1["Front_File"], new_f)
                self.assertEqual(row1["Back_File"], new_b)
                self.assertEqual(row1["Corners_File"], new_c)
                self.assertEqual(row1["Label_Printed"], "False")
                # Excluded SKU-0002 remains untouched
                self.assertEqual(row2["Player"], "Ronald Acuna Jr.")
                self.assertTrue((set_dir / old2_f).exists())

                # Verify atomic renames on disk
                self.assertFalse((set_dir / old_f).exists())
                self.assertFalse((set_dir / old_b).exists())
                self.assertFalse((set_dir / old_c).exists())
                self.assertEqual((set_dir / new_f).read_bytes(), b"FRONT_BYTES_1")
                self.assertEqual((set_dir / new_b).read_bytes(), b"BACK_BYTES_1")
                self.assertEqual((set_dir / new_c).read_bytes(), b"CORNERS_BYTES_1")
                self.assertEqual(len(logged_actions), 3)

    def test_split_and_commit_register_inline_active_tasks(self):
        import Core.database as db
        import Core.flatbed_splitter as fs
        import launch_tabulas_hub as hub

        observed_mid_flight = []

        def _fake_find_batches():
            snapshot = hub._get_live_lanes_and_logs()
            observed_mid_flight.append(snapshot.get("inline_tasks", []))
            return []

        def _fake_commit(stage_id, front_boxes, back_boxes):
            snapshot = hub._get_live_lanes_and_logs()
            observed_mid_flight.append(snapshot.get("inline_tasks", []))
            return {"success": True, "createdCount": 2}

        with mock.patch.object(db, "find_unarchived_scan_batches", side_effect=_fake_find_batches), \
             mock.patch.object(fs, "commit_staged_splitter_review", side_effect=_fake_commit), \
             mock.patch.object(fs, "list_pending_splitter_reviews", return_value=[]), \
             mock.patch.object(hub, "_discover_incoming_scans", return_value=[]), \
             mock.patch.object(hub, "_log_ui_action_to_file", lambda *_a, **_kw: None):

            # 1. POST /api/batches/split-flatbed
            b1 = json.dumps({"batchName": "Batch_Test"}).encode("utf-8")
            h1 = _FakeHandler.create(hub)
            h1.path = "/api/batches/split-flatbed"
            h1.headers = {"Content-Length": str(len(b1))}
            h1.rfile = io.BytesIO(b1)
            h1.do_POST()
            self.assertEqual(h1.responses[0][0], 200)
            self.assertEqual(len(observed_mid_flight[0]), 1)
            self.assertEqual(observed_mid_flight[0][0]["job_type"], "split_flatbed")
            self.assertEqual(observed_mid_flight[0][0]["status"], "RUNNING")
            self.assertEqual(hub._get_live_lanes_and_logs()["inline_tasks"], [])

            # 2. POST /api/splitter/commit
            b2 = json.dumps({"stageId": "stage_test_1", "front_boxes": [], "back_boxes": []}).encode("utf-8")
            h2 = _FakeHandler.create(hub)
            h2.path = "/api/splitter/commit"
            h2.headers = {"Content-Length": str(len(b2))}
            h2.rfile = io.BytesIO(b2)
            h2.do_POST()
            self.assertEqual(h2.responses[0][0], 200)
            self.assertEqual(len(observed_mid_flight[1]), 1)
            self.assertEqual(observed_mid_flight[1][0]["job_type"], "splitter_commit")
            self.assertEqual(observed_mid_flight[1][0]["status"], "RUNNING")
            self.assertEqual(hub._get_live_lanes_and_logs()["inline_tasks"], [])
