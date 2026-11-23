from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from Core.maintenance_scheduler import (
    TASK_DEFINITIONS,
    _run_housekeeping_hygiene,
    is_task_due,
    load_maintenance_schedule,
    run_maintenance_task,
    tick_maintenance_scheduler,
    update_maintenance_schedule,
)
import updater


def test_maintenance_schedule_atomic_persistence(tmp_path: Path):
    sched_path = tmp_path / "Data" / "maintenance_schedule.json"
    loaded = load_maintenance_schedule(sched_path)
    assert sched_path.exists()
    assert set(loaded["tasks"].keys()) == set(TASK_DEFINITIONS.keys())

    updated = update_maintenance_schedule(
        {
            "neural_index_sync": {
                "enabled": True,
                "cron_or_interval": "every_6h",
                "time_of_day": "01:45",
            },
            "housekeeping_hygiene": {
                "enabled": True,
                "cron_or_interval": "daily",
                "time_of_day": "04:15",
            },
        },
        schedule_path=sched_path,
    )
    assert updated["tasks"]["neural_index_sync"]["enabled"] is True
    assert updated["tasks"]["neural_index_sync"]["cron_or_interval"] == "every_6h"
    assert updated["tasks"]["neural_index_sync"]["time_of_day"] == "01:45"

    reloaded = load_maintenance_schedule(sched_path)
    assert reloaded["tasks"]["neural_index_sync"]["enabled"] is True
    assert reloaded["tasks"]["housekeeping_hygiene"]["time_of_day"] == "04:15"


def test_is_task_due_variants():
    now = datetime(2026, 11, 23, 10, 0, 0)
    assert is_task_due({"enabled": False, "cron_or_interval": "daily", "time_of_day": "02:00"}, now=now) is False
    assert is_task_due({"enabled": True, "cron_or_interval": "daily", "time_of_day": "02:00", "last_run": ""}, now=now) is True
    assert is_task_due({"enabled": True, "cron_or_interval": "daily", "time_of_day": "12:00", "last_run": ""}, now=now) is False
    assert is_task_due({"enabled": True, "cron_or_interval": "daily", "time_of_day": "02:00", "last_run": "2026-11-23 02:05:00"}, now=now) is False
    assert is_task_due({"enabled": True, "cron_or_interval": "daily", "time_of_day": "02:00", "last_run": "2026-11-22 02:05:00"}, now=now) is True
    assert is_task_due({"enabled": True, "cron_or_interval": "every_6h", "time_of_day": "02:00", "last_run": "2026-11-23 03:00:00"}, now=now) is True
    assert is_task_due({"enabled": True, "cron_or_interval": "every_6h", "time_of_day": "02:00", "last_run": "2026-11-23 05:00:00"}, now=now) is False


def test_idle_guard_deferral_and_recovery(tmp_path: Path):
    sched_path = tmp_path / "Data" / "maintenance_schedule.json"
    update_maintenance_schedule(
        {
            "learned_set_priors_refresh": {
                "enabled": True,
                "cron_or_interval": "daily",
                "time_of_day": "02:00",
            }
        },
        schedule_path=sched_path,
    )

    executed: list[str] = []

    def _fake_runner(tid: str):
        executed.append(tid)
        return True, f"Ran {tid}"

    now = datetime(2026, 11, 23, 10, 0, 0)
    # 1. Worker busy -> defers cleanly without running task
    res_busy = tick_maintenance_scheduler(
        schedule_path=sched_path,
        now=now,
        busy_checker=lambda: (True, "slot_1: TCDB Scrape"),
        task_runner=_fake_runner,
    )
    assert len(res_busy) == 1
    assert res_busy[0]["deferred"] is True
    assert res_busy[0]["status"] == "deferred"
    assert executed == []

    after_defer = load_maintenance_schedule(sched_path)
    t_state = after_defer["tasks"]["learned_set_priors_refresh"]
    assert t_state["last_status"] == "deferred"
    assert t_state["deferred_count"] == 1

    # 2. Worker idle -> runs deferred due task and resets deferred_count
    res_idle = tick_maintenance_scheduler(
        schedule_path=sched_path,
        now=now + timedelta(minutes=5),
        busy_checker=lambda: (False, ""),
        task_runner=_fake_runner,
    )
    assert len(res_idle) == 1
    assert res_idle[0]["success"] is True
    assert res_idle[0]["deferred"] is False
    assert executed == ["learned_set_priors_refresh"]

    after_run = load_maintenance_schedule(sched_path)
    t_done = after_run["tasks"]["learned_set_priors_refresh"]
    assert t_done["last_status"] == "ok"
    assert t_done["deferred_count"] == 0
    assert t_done["last_run"] != ""


def test_run_now_manual_execution(tmp_path: Path):
    sched_path = tmp_path / "Data" / "maintenance_schedule.json"
    load_maintenance_schedule(sched_path)

    res = run_maintenance_task(
        "master_checklist_rollup",
        schedule_path=sched_path,
        manual=True,
        respect_idle_guard=True,
        busy_checker=lambda: (False, ""),
        task_runner=lambda tid: (True, f"Manual sync OK for {tid}"),
        now=datetime(2026, 11, 23, 11, 0, 0),
    )
    assert res["success"] is True
    assert res["status"] == "ok"
    assert "[Manual]" in res["message"]
    assert res["schedule"]["tasks"]["master_checklist_rollup"]["last_run"] == "2026-11-23 11:00:00"


def test_housekeeping_hygiene_isolated(tmp_path: Path):
    daily_logs = tmp_path / "Logs" / "Logs"
    old_log_dir = daily_logs / "20200101"
    new_log_dir = daily_logs / datetime.now().strftime("%Y%m%d")
    old_log_dir.mkdir(parents=True)
    new_log_dir.mkdir(parents=True)

    lock_dir = tmp_path / "downloaded_files"
    lock_dir.mkdir(parents=True)
    stale_lock = lock_dir / "driver_fixing.lock"
    stale_lock.write_text("stale", encoding="utf-8")
    old_mtime = time.time() - 300.0
    os.utime(stale_lock, (old_mtime, old_mtime))

    cache_dir = tmp_path / "Cache"
    cache_dir.mkdir(parents=True)
    orphan_tmp = cache_dir / "orphan.tmp"
    orphan_tmp.write_text("tmp", encoding="utf-8")
    very_old = time.time() - 90000.0
    os.utime(orphan_tmp, (very_old, very_old))

    good_json = tmp_path / "Data" / "maintenance_schedule.json"
    good_json.parent.mkdir(parents=True, exist_ok=True)
    good_json.write_text(json.dumps({"ok": True}), encoding="utf-8")

    good_csv = tmp_path / "Data" / "Inventory.csv"
    good_csv.write_text("SKU,Set,Player\n0000001,2024 Topps,Judge\n", encoding="utf-8-sig")

    res = _run_housekeeping_hygiene(
        keep_logs_days=30,
        daily_logs_dir=daily_logs,
        reports_dir=tmp_path / "Reports",
        archive_logs_dir=None,
        cache_dir=cache_dir,
        data_dir=tmp_path / "Data",
        lock_dirs=[lock_dir],
        json_files=[good_json],
        csv_files=[good_csv],
    )
    assert res["ok"] is True
    assert res["pruned_logs"] == 1
    assert not old_log_dir.exists()
    assert new_log_dir.exists()
    assert res["removed_driver_locks"] == 1
    assert not stale_lock.exists()
    assert res["removed_temps"] == 1
    assert not orphan_tmp.exists()
    assert res["checked_files"] == 2


def test_updater_parses_all_sandbox_changelog_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sandbox_updates = Path(__file__).resolve().parent.parent / "Updates"
    txt_files = sorted(sandbox_updates.glob("*.txt"))
    assert len(txt_files) >= 9

    parsed = [updater.parse_update_package_file(p) for p in txt_files]
    for pkg in parsed:
        assert pkg["is_valid_package"] is True, f"Invalid package: {pkg['package_file']}"
        assert pkg["is_changelog_only"] is True
        assert pkg["version"]
        assert len(pkg["changelog"]) >= 1

    # Verify strict ascending semantic version order across packages
    parsed.sort(key=lambda p: updater.parse_version_tuple(p["version"]))
    versions = [updater.parse_version_tuple(p["version"]) for p in parsed]
    assert all(versions[i] < versions[i + 1] for i in range(len(versions) - 1))

    # Dry-run apply against isolated temp registry
    monkeypatch.setattr(updater, "UPDATES_DIR", sandbox_updates)
    monkeypatch.setattr(updater, "SNAPSHOTS_DIR", tmp_path / ".snapshots")
    monkeypatch.setattr(updater, "REGISTRY_FILE", tmp_path / "version_registry.json")
    monkeypatch.setattr(updater, "VERIFIED_BACKUPS_DIR", tmp_path / ".verified_backups")

    for pkg in parsed:
        res = updater.apply_update_package(pkg, dry_run=True)
        assert res["success"] is True
        assert res["dry_run"] is True
        assert res["changelog_only"] is True


def test_app_jsx_skins_have_no_numeric_prefixes():
    app_jsx = (Path(__file__).resolve().parent.parent / "App.jsx").read_text(encoding="utf-8")
    block_m = re.search(r"const CHROME_PULSE_SKINS\s*=\s*\{(.*?)\n\};", app_jsx, re.DOTALL)
    assert block_m is not None
    block = block_m.group(1)
    names = re.findall(r"name:\s*['\"]([^'\"]+)['\"]", block)
    assert len(names) == 9
    for n in names:
        assert not re.match(r"^\s*(?:#?\d+\s*[\.\-\):])", n), f"Skin name still has numeric prefix: {n}"
    for key in (
        "screenshot_signature_3d",
        "classic_bronze_3d",
        "superfractor_gold",
        "sapphire_edition",
        "quant_terminal",
        "finest_refractor",
        "stadium_club",
        "bowman_turf_3d",
        "cosmic_chrome_3d",
    ):
        assert f"{key}:" in block
