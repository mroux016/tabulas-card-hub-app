from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import zipfile
from pathlib import Path

import launch_tabulas_hub
import updater

REPO_ROOT = Path(__file__).resolve().parent.parent


class _MockResponse:
    def __init__(self, status_code: int = 200, json_data=None, content: bytes = b"", text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.text = text or (content.decode("utf-8", errors="replace") if content else "")

    def json(self):
        return self._json_data


class _MockSession:
    def __init__(self, routes: dict[str, _MockResponse]):
        self.routes = routes

    def get(self, url: str, headers=None, timeout=None):
        if url not in self.routes:
            return _MockResponse(status_code=404, text="Not Found")
        return self.routes[url]


def _build_zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_parse_changelog_markdown_covers_all_back_versions():
    cl_path = REPO_ROOT / "CHANGELOG.md"
    assert cl_path.exists(), "CHANGELOG.md must exist at repo root"

    entries = updater.parse_changelog_markdown(cl_path)
    versions = [e["version"] for e in entries]
    expected_versions = [
        "0.25.0-beta.8",
        "0.25.0-beta.7",
        "0.25.0-beta.6",
        "0.25.0-beta.5",
        "0.25.0-beta.4",
        "0.25.0-beta.3",
        "0.25.0-beta.2",
        "0.25.0-beta.1",
        "0.24.0-beta.48",
        "0.24.0-beta.47",
        "0.24.0-beta.46",
        "0.24.0-beta.45",
    ]
    for ev in expected_versions:
        assert ev in versions, f"Missing historical version {ev} in CHANGELOG.md"

    # Verify newest-first ordering
    assert versions[0] == "0.25.0-beta.8"
    assert versions[-1] == "0.24.0-beta.45"

    # Verify structured sections are populated for user-facing display
    top = entries[0]
    headings = [s["heading"] for s in top["sections"]]
    assert "Features & Improvements" in headings
    assert "UI & Workflow" in headings
    assert "Bug Fixes" in headings
    assert len(top["changelog"]) >= 4


def test_extract_changelog_for_version_with_and_without_v():
    cl_path = REPO_ROOT / "CHANGELOG.md"
    e1 = updater.extract_changelog_for_version("v0.25.0-beta.4", changelog_path=cl_path)
    e2 = updater.extract_changelog_for_version("0.25.0-beta.4", changelog_path=cl_path)
    assert e1 is not None and e2 is not None
    assert e1["version"] == "0.25.0-beta.4"
    assert e1["changelog_md"] == e2["changelog_md"]
    assert updater.extract_changelog_for_version("v99.99.99", changelog_path=cl_path) is None


def test_format_release_changelog_strips_boilerplate_and_parses_sections():
    raw = (
        "### Features & Improvements\n"
        "- Added **One-Click Restart** button\n"
        "* Added `CHANGELOG.md` reader\n\n"
        "### Bug Fixes\n"
        "- Fixed cramped scrolling\n\n"
        "**Full Changelog**: https://github.com/org/repo/compare/v0.25.0-beta.7...v0.25.0-beta.8\n"
        "---\n"
    )
    fmt = updater.format_release_changelog(raw)
    assert "Full Changelog" not in fmt["markdown"]
    assert len(fmt["sections"]) == 2
    assert fmt["sections"][0]["heading"] == "Features & Improvements"
    assert fmt["sections"][1]["heading"] == "Bug Fixes"
    assert "[Bug Fixes] Fixed cramped scrolling" in fmt["lines"]


def test_check_github_release_formats_notes_and_falls_back_to_changelog(tmp_path: Path):
    cl_file = tmp_path / "CHANGELOG.md"
    cl_file.write_text(
        "## [v0.25.0-beta.8] — 2026-11-23 — Test Release\n\n"
        "### Features & Improvements\n"
        "- Fallback user-facing bullet\n",
        encoding="utf-8",
    )

    release_empty_body = {
        "tag_name": "v0.25.0-beta.8",
        "name": "Beta 8",
        "draft": False,
        "prerelease": True,
        "published_at": "2026-11-23T12:00:00Z",
        "body": "",
        "html_url": "https://github.com/myorg/tabulas/releases/tag/v0.25.0-beta.8",
        "assets": [
            {"name": "tabulas-hub-v0.25.0-beta.8.zip", "url": "https://api.github.com/assets/1"},
            {"name": "SHA256SUMS.txt", "url": "https://api.github.com/assets/2"},
        ],
    }
    session = _MockSession({
        "https://api.github.com/repos/myorg/tabulas/releases?per_page=10": _MockResponse(200, json_data=[release_empty_body]),
    })

    res = updater.check_github_release(
        {"github_owner": "myorg", "github_repo": "tabulas", "channel": "beta"},
        "0.25.0-beta.7",
        session=session,
        changelog_path=cl_file,
    )
    assert res["update_available"] is True
    assert "Fallback user-facing bullet" in res["changelog_md"]
    assert any("Fallback user-facing bullet" in ln for ln in res["changelog"])
    assert res["changelog_sections"][0]["heading"] == "Features & Improvements"


def test_apply_github_release_update_persists_formatted_changelog(tmp_path: Path):
    app_root = tmp_path / "App"
    app_root.mkdir()
    reg_path = tmp_path / "Updates" / "version_registry.json"

    zip_bytes = _build_zip_bytes({"hello.py": b"print('v8')\n"})
    digest = hashlib.sha256(zip_bytes).hexdigest()
    rel = {
        "latest_version": "0.25.0-beta.8",
        "tag_name": "v0.25.0-beta.8",
        "release_name": "Release v0.25.0-beta.8",
        "published_at": "2026-11-23T12:00:00Z",
        "changelog_md": "### Features & Improvements\n- Added Click-to-Reboot\n",
        "zip_asset_api_url": "https://api.github.com/assets/zip",
        "zip_asset_name": "tabulas-hub-v0.25.0-beta.8.zip",
        "checksum_asset_api_url": "https://api.github.com/assets/sums",
    }
    session = _MockSession({
        rel["checksum_asset_api_url"]: _MockResponse(200, text=f"{digest}  {rel['zip_asset_name']}\n"),
        rel["zip_asset_api_url"]: _MockResponse(200, content=zip_bytes),
    })

    res = updater.apply_github_release_update(
        rel,
        app_root,
        {},
        session=session,
        busy_checker=lambda: (False, ""),
        cache_dir=tmp_path / "Cache",
        registry_path=reg_path,
    )
    assert res["success"] is True
    assert "[Features & Improvements] Added Click-to-Reboot" in res["changelog"]
    assert res["changelog_sections"][0]["heading"] == "Features & Improvements"

    reg_data = json.loads(reg_path.read_text(encoding="utf-8"))
    hist_entry = reg_data["version_history"][-1]
    assert hist_entry["package_file"] == "github:v0.25.0-beta.8"
    assert "[Features & Improvements] Added Click-to-Reboot" in hist_entry["changelog"]
    assert "### Features & Improvements" in hist_entry["changelog_md"]


def test_get_unified_changelog_history_merges_and_deduplicates(tmp_path: Path):
    cl_file = tmp_path / "CHANGELOG.md"
    cl_file.write_text(
        "## [v0.25.0-beta.8] — 2026-11-23 — Beta 8\n"
        "### Features & Improvements\n"
        "- Rich changelog entry\n",
        encoding="utf-8",
    )
    reg_file = tmp_path / "version_registry.json"
    reg_file.write_text(
        json.dumps({
            "current_release_version": "0.25.0-beta.8",
            "version_history": [
                {
                    "version": "0.25.0-beta.8",
                    "timestamp": "2026-11-23 12:00:00",
                    "applied_at": "2026-11-23 12:05:00",
                    "title": "Beta 8",
                    "package_file": "github:v0.25.0-beta.8",
                    "files_modified": ["App.jsx"],
                    "changelog": ["Rich changelog entry"],
                },
                {
                    "version": "0.25.0-beta.99",
                    "timestamp": "2026-11-24 09:00:00",
                    "title": "Future GitHub Release",
                    "package_file": "github:v0.25.0-beta.99",
                    "changelog": ["Future feature"],
                },
            ],
        }),
        encoding="utf-8",
    )

    merged = updater.get_unified_changelog_history(changelog_path=cl_file, registry_path=reg_file)
    vers = [m["version"] for m in merged]
    assert vers.count("0.25.0-beta.8") == 1
    assert "0.25.0-beta.99" in vers
    b8 = next(m for m in merged if m["version"] == "0.25.0-beta.8")
    assert b8["is_current"] is True
    assert b8["source"] == "github_release"


def test_request_clean_server_restart_respects_worker_busy_and_spawns_when_idle(monkeypatch):
    monkeypatch.setattr(launch_tabulas_hub, "_RESTART_IN_PROGRESS", False)
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_HTTP_SERVER", None)

    busy_res = launch_tabulas_hub.request_clean_server_restart(
        busy_checker=lambda: (True, "slot_2: Grading Batch"),
    )
    assert busy_res["success"] is False
    assert busy_res["aborted"] is True
    assert busy_res["reason"] == "worker_pool_busy"

    spawned = threading.Event()
    exited = threading.Event()
    monkeypatch.setattr(launch_tabulas_hub, "_RESTART_IN_PROGRESS", False)

    ok_res = launch_tabulas_hub.request_clean_server_restart(
        busy_checker=lambda: (False, ""),
        spawn_fn=lambda: spawned.set(),
        exit_fn=lambda: exited.set(),
        delay_seconds=0.01,
    )
    assert ok_res["success"] is True
    assert ok_res["restarting"] is True
    assert spawned.wait(timeout=2.0)
    assert exited.wait(timeout=2.0)
    monkeypatch.setattr(launch_tabulas_hub, "_RESTART_IN_PROGRESS", False)


def test_release_workflow_uses_changelog_release_notes():
    wf = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in wf
    assert "RELEASE_NOTES.md" in wf
    assert "body_path: RELEASE_NOTES.md" in wf
    assert "generate_release_notes: false" in wf
    assert "CHANGELOG.md" in wf


def test_app_jsx_no_es_modules_and_contains_qol_features():
    jsx = (REPO_ROOT / "App.jsx").read_text(encoding="utf-8")
    # Classic React/Babel invariant: only the two pre-existing bootloader-stripped lines, zero other ES import/export statements
    es_lines = [ln.strip() for ln in re.findall(r"^\s*(?:import|export)\s+.*$", jsx, re.MULTILINE)]
    assert es_lines == [
        "import React, { useState, useEffect, useMemo, useRef } from 'react';",
        "export default function App() {",
    ]
    # Collapsible About sections & rich changelog reader
    assert "aboutSections" in jsx
    assert "renderRichChangelogBlock" in jsx
    assert "Spacious Reader" in jsx
    # Click-to-Reboot
    assert "/system/restart" in jsx
    assert "handleRestartApp" in jsx
    # Copy & Click-to-Navigate notifications
    assert "handleCopyNotification" in jsx
    assert "resolveNotificationTargetPage" in jsx
    assert "handleNavigateFromNotification" in jsx
