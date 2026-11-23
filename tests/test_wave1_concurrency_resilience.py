from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest


def _isolated_env_patch(tmp_path: Path, monkeypatch):
    base = tmp_path / "Base"
    lib = tmp_path / "Library"
    arch = tmp_path / "Archive"
    for d in (base, lib, arch):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CARDS_BASE_DIR", str(base))
    monkeypatch.setenv("TABULAS_SET_LIBRARY_DIR", str(lib))
    monkeypatch.setenv("TABULAS_ARCHIVE_DIR", str(arch))


def test_interprocess_file_lock_respects_live_pid_and_raises_timeout(tmp_path: Path):
    from Core.config import interprocess_file_lock

    lock_p = tmp_path / "test_live.lock"
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        lock_p.write_text(f"{proc.pid}|1|1.0\n", encoding="utf-8")
        # Backdate mtime past stale_seconds=0.05 to verify live PID is NOT broken by age alone
        old_ts = time.time() - 120.0
        os.utime(lock_p, (old_ts, old_ts))

        with pytest.raises(TimeoutError):
            with interprocess_file_lock(lock_p, timeout=0.15, stale_seconds=0.05):
                pass
        assert lock_p.exists()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_interprocess_file_lock_breaks_dead_pid_lock(tmp_path: Path):
    from Core.config import interprocess_file_lock

    lock_p = tmp_path / "test_dead.lock"
    proc = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait(timeout=5)
    dead_pid = proc.pid

    lock_p.write_text(f"{dead_pid}|1|{time.time():.6f}\n", encoding="utf-8")
    with interprocess_file_lock(lock_p, timeout=1.0, stale_seconds=60.0):
        assert lock_p.exists()
    assert not lock_p.exists()


def test_merge_inventory_updates_and_atomic_preserves_parallel_edits(tmp_path: Path, monkeypatch):
    import Core.config as cfg
    import Core.database as db

    inv_dir = tmp_path / "Inventory"
    inv_dir.mkdir(parents=True, exist_ok=True)
    inv_file = inv_dir / "Inventory.csv"
    monkeypatch.setattr(cfg, "INVENTORY_DIR", inv_dir)
    monkeypatch.setattr(cfg, "INVENTORY_FILE", inv_file)
    monkeypatch.setattr(db, "INVENTORY_DIR", inv_dir)
    monkeypatch.setattr(db, "INVENTORY_FILE", inv_file)
    monkeypatch.setattr(db, "ensure_directories", lambda: None)

    initial_rows = [
        {c: "" for c in cfg.INVENTORY_COLUMNS} | {"SKU": "1000001", "Player": "Aaron Judge", "Est_PSA": "8.0", "Status": "In Stock"},
        {c: "" for c in cfg.INVENTORY_COLUMNS} | {"SKU": "1000002", "Player": "Shohei Ohtani", "Est_PSA": "9.0", "Status": "In Stock"},
    ]
    db.save_inventory_df(pd.DataFrame(initial_rows))

    # Background worker takes a baseline snapshot before a concurrent HTTP edit & commit
    worker_baseline = db.load_inventory_df()
    worker_updated = worker_baseline.copy()
    worker_updated.loc[worker_updated["SKU"] == "1000001", "Est_PSA"] = "9.5"

    # Meanwhile, concurrent atomic update marks SKU 1000002 Sold and appends SKU 1000003
    def _concurrent_edit(df_cur: pd.DataFrame) -> pd.DataFrame:
        df_cur.loc[df_cur["SKU"] == "1000002", "Status"] = "Sold"
        new_row = {c: "" for c in cfg.INVENTORY_COLUMNS} | {"SKU": "1000003", "Player": "Paul Skenes", "Est_PSA": "10.0", "Status": "In Stock"}
        return pd.concat([df_cur, pd.DataFrame([new_row])], ignore_index=True)

    db.update_inventory_df_atomic(_concurrent_edit)

    # Worker finishes and merges only its mutated cells by SKU
    merged = db.merge_inventory_updates_by_sku(worker_updated, baseline_df=worker_baseline)
    by_sku = {r["SKU"]: r for r in merged.to_dict(orient="records")}

    assert set(by_sku.keys()) == {"1000001", "1000002", "1000003"}
    assert by_sku["1000001"]["Est_PSA"] == "9.5"
    assert by_sku["1000002"]["Status"] == "Sold"
    assert by_sku["1000003"]["Player"] == "Paul Skenes"


def test_tcdb_queued_continuation_gate_prevents_concurrent_scrapers(tmp_path: Path, monkeypatch):
    import cli

    logs_dir = tmp_path / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(cli, "ensure_directories", lambda: logs_dir.mkdir(parents=True, exist_ok=True))

    # Slot 2 has a queued TCDB job (e.g. behind a non-TCDB job)
    cli.enqueue_job_for_lane("tcdb_scrape", "Queued TCDB Job", {"sets": ["2026 Topps"]}, lane="slot_2")

    found_slot, _ = cli._find_running_heavy_tcdb_slot()
    assert found_slot == "slot_2"

    # Slot 1 is currently running a TCDB scraper
    cli.write_job_state("RUNNING", "tcdb_scrape", "Active TCDB", pid=os.getpid(), lane="slot_1")

    with mock.patch.object(cli, "start_background_job", side_effect=AssertionError("Must not launch 2nd TCDB scraper")):
        res = cli.start_or_queue_background_job(
            job_type="tcdb_scrape",
            title="Queued Continuation TCDB",
            payload={"sets": ["2026 Bowman"]},
            lane="slot_2",
            is_queued_continuation=True,
        )

    assert res["queued"] is True
    assert res["lane"] == "slot_1"
    q1 = cli.load_lane_job_queue("slot_1")
    assert len(q1) == 1
    assert q1[0]["title"] == "Queued Continuation TCDB"


def test_stop_active_job_clears_queue_and_does_not_brick_slot(tmp_path: Path, monkeypatch):
    import cli

    logs_dir = tmp_path / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(cli, "ensure_directories", lambda: logs_dir.mkdir(parents=True, exist_ok=True))

    cli.write_job_state("RUNNING", "scan_ingest", "Batch Scan", pid=0, lane="slot_3")
    cli.enqueue_job_for_lane("scan_ingest", "Queued Followup", {}, lane="slot_3")
    assert len(cli.load_lane_job_queue("slot_3")) == 1

    cli.stop_active_job(lane="slot_3")
    assert cli.load_lane_job_queue("slot_3") == []
    busy, st = cli._is_slot_currently_busy("slot_3")
    assert busy is False
    assert st["status"] == "STOPPED"

    # Even if an orphaned queue file remains on a dead/stopped slot, it must not permanently brick the slot
    cli.enqueue_job_for_lane("scan_ingest", "Orphaned Item", {}, lane="slot_4")
    cli.write_job_state("STOPPED", "scan_ingest", "Stopped", pid=0, lane="slot_4")
    busy4, _ = cli._is_slot_currently_busy("slot_4")
    assert busy4 is False
