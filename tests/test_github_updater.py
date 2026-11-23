from __future__ import annotations

import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path

import pytest

import updater


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
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if url not in self.routes:
            return _MockResponse(status_code=404, text="Not Found")
        return self.routes[url]


def _build_zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _make_release_info(zip_name: str = "tabulas-hub-v0.25.0-beta.7.zip") -> dict:
    return {
        "update_available": True,
        "current_version": "0.25.0-beta.6",
        "latest_version": "0.25.0-beta.7",
        "tag_name": "v0.25.0-beta.7",
        "release_name": "Release v0.25.0-beta.7",
        "published_at": "2026-11-23T12:00:00Z",
        "changelog_md": "- Added GitHub Releases OTA updater",
        "html_url": "https://github.com/myorg/tabulas/releases/tag/v0.25.0-beta.7",
        "zip_asset_api_url": "https://api.github.com/repos/myorg/tabulas/releases/assets/101",
        "zip_asset_name": zip_name,
        "checksum_asset_api_url": "https://api.github.com/repos/myorg/tabulas/releases/assets/102",
        "is_prerelease": True,
        "channel": "beta",
    }


def test_stable_vs_beta_version_comparison_and_headers():
    beta_releases = [
        {
            "tag_name": "v0.26.0-rc.1",
            "name": "Draft RC",
            "draft": True,
            "prerelease": True,
            "published_at": "2026-11-23T12:00:00Z",
            "body": "Should be ignored",
            "html_url": "https://github.com/myorg/tabulas/releases/tag/v0.26.0-rc.1",
            "assets": [],
        },
        {
            "tag_name": "v0.25.0-beta.7",
            "name": "Beta 7",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-11-23T10:00:00Z",
            "body": "Beta 7 notes",
            "html_url": "https://github.com/myorg/tabulas/releases/tag/v0.25.0-beta.7",
            "assets": [
                {"name": "tabulas-hub-v0.25.0-beta.7.zip", "url": "https://api.github.com/assets/1"},
                {"name": "SHA256SUMS.txt", "url": "https://api.github.com/assets/2"},
            ],
        },
        {
            "tag_name": "v0.25.0-beta.6",
            "name": "Beta 6",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-11-22T10:00:00Z",
            "body": "Beta 6 notes",
            "assets": [],
        },
    ]
    stable_release = {
        "tag_name": "v0.26.0",
        "name": "Stable 0.26.0",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-24T09:00:00Z",
        "body": "Stable release notes",
        "html_url": "https://github.com/myorg/tabulas/releases/tag/v0.26.0",
        "assets": [
            {"name": "tabulas-hub-v0.26.0.zip", "url": "https://api.github.com/assets/10"},
            {"name": "SHA256SUMS.txt", "url": "https://api.github.com/assets/11"},
        ],
    }

    session = _MockSession({
        "https://api.github.com/repos/myorg/tabulas/releases?per_page=10": _MockResponse(200, json_data=beta_releases),
        "https://api.github.com/repos/myorg/tabulas/releases/latest": _MockResponse(200, json_data=stable_release),
    })

    beta_cfg = {"github_owner": "myorg", "github_repo": "tabulas", "channel": "beta", "github_token": "tok_secret_1234"}
    res_beta = updater.check_github_release(beta_cfg, "0.25.0-beta.6", session=session)
    assert res_beta["update_available"] is True
    assert res_beta["latest_version"] == "0.25.0-beta.7"
    assert res_beta["is_prerelease"] is True
    assert res_beta["zip_asset_api_url"] == "https://api.github.com/assets/1"
    assert res_beta["checksum_asset_api_url"] == "https://api.github.com/assets/2"

    url_called, hdrs = session.calls[0]
    assert url_called.endswith("/releases?per_page=10")
    assert hdrs["Accept"] == "application/vnd.github+json"
    assert hdrs["X-GitHub-Api-Version"] == "2026-03-10"
    assert hdrs["User-Agent"] == "TabulasCardHub-Updater"
    assert hdrs["Authorization"] == "Bearer tok_secret_1234"

    stable_cfg = {"github_owner": "myorg", "github_repo": "tabulas", "channel": "stable", "github_token": ""}
    res_stable = updater.check_github_release(stable_cfg, "0.25.0-beta.6", session=session)
    assert res_stable["update_available"] is True
    assert res_stable["latest_version"] == "0.26.0"
    assert res_stable["is_prerelease"] is False
    assert session.calls[1][0].endswith("/releases/latest")

    # Already on v0.26.0 -> not newer
    res_same = updater.check_github_release(stable_cfg, "0.26.0", session=session)
    assert res_same["update_available"] is False


def test_fallback_semver_parser_without_packaging(monkeypatch):
    monkeypatch.setattr(updater, "_PackagingVersion", None)
    assert updater.is_newer_release_version("v0.25.0-beta.7", "v0.25.0-beta.6") is True
    assert updater.is_newer_release_version("v0.26.0", "v0.25.0-beta.7") is True
    assert updater.is_newer_release_version("v0.25.0-beta.6", "v0.25.0-beta.7") is False
    assert updater.is_newer_release_version("v0.25.0-alpha.9", "v0.25.0-beta.1") is False


def test_updater_config_save_load_mask_and_env_fallback(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "Data" / "updater_config.json"
    monkeypatch.delenv("TABULAS_GITHUB_TOKEN", raising=False)

    saved = updater.save_updater_config(
        {"repo": "myorg/tabulas-hub", "channel": "stable", "github_token": "ghp_abc123xyz9"},
        config_path=cfg_path,
    )
    assert saved["github_owner"] == "myorg"
    assert saved["github_repo"] == "tabulas-hub"
    assert saved["channel"] == "stable"
    assert saved["github_token"] == "ghp_abc123xyz9"

    masked = updater.mask_updater_config(saved)
    assert "github_token" not in masked
    assert masked["has_token"] is True
    assert masked["github_token_masked"] == "••••xyz9"

    # Saving without token preserves existing token
    saved2 = updater.save_updater_config({"channel": "beta"}, config_path=cfg_path)
    assert saved2["github_token"] == "ghp_abc123xyz9"

    # Clearing token falls back to TABULAS_GITHUB_TOKEN env var
    updater.save_updater_config({"clear_token": True}, config_path=cfg_path)
    monkeypatch.setenv("TABULAS_GITHUB_TOKEN", "env_tok_9876")
    loaded_env = updater.load_updater_config(config_path=cfg_path)
    assert loaded_env["github_token"] == "env_tok_9876"
    assert loaded_env["token_source"] == "env"


def test_sha256_mismatch_leaves_app_untouched(tmp_path: Path):
    app_root = tmp_path / "App"
    app_root.mkdir()
    target_py = app_root / "hello.py"
    target_py.write_text("print('original')\n", encoding="utf-8")

    zip_bytes = _build_zip_bytes({"hello.py": b"print('updated')\n"})
    rel = _make_release_info()
    session = _MockSession({
        rel["checksum_asset_api_url"]: _MockResponse(200, text=f"{'0' * 64}  {rel['zip_asset_name']}\n"),
        rel["zip_asset_api_url"]: _MockResponse(200, content=zip_bytes),
    })

    res = updater.apply_github_release_update(
        rel,
        app_root,
        {"github_token": "tok"},
        session=session,
        busy_checker=lambda: (False, ""),
        cache_dir=tmp_path / "Cache",
        registry_path=tmp_path / "Updates" / "version_registry.json",
    )
    assert res["success"] is False
    assert "SHA-256 mismatch" in res["error"]
    assert target_py.read_text(encoding="utf-8") == "print('original')\n"
    # Verify octet-stream header was used for asset downloads
    assert session.calls[0][1]["Accept"] == "application/octet-stream"


@pytest.mark.parametrize("bad_member", ["../evil.py", "sub/../../evil.py", "/abs/evil.py"])
def test_path_traversal_rejected_without_touching_files(tmp_path: Path, bad_member: str):
    app_root = tmp_path / "App"
    app_root.mkdir()
    target_py = app_root / "hello.py"
    target_py.write_text("print('safe')\n", encoding="utf-8")

    zip_bytes = _build_zip_bytes({
        "hello.py": b"print('new')\n",
        bad_member: b"pwned",
    })
    digest = hashlib.sha256(zip_bytes).hexdigest()
    rel = _make_release_info()
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
        registry_path=tmp_path / "Updates" / "version_registry.json",
    )
    assert res["success"] is False
    assert target_py.read_text(encoding="utf-8") == "print('safe')\n"
    assert not (tmp_path / "evil.py").exists()


def test_idle_guard_refuses_when_worker_busy(tmp_path: Path, monkeypatch):
    app_root = tmp_path / "App"
    app_root.mkdir()
    monkeypatch.setattr(updater, "is_worker_pool_busy", lambda: (True, "slot_1: TCDB Scrape"))

    res = updater.apply_github_release_update(
        _make_release_info(),
        app_root,
        {},
        session=_MockSession({}),
        cache_dir=tmp_path / "Cache",
        registry_path=tmp_path / "Updates" / "version_registry.json",
    )
    assert res["success"] is False
    assert res["aborted"] is True
    assert res["reason"] == "worker_pool_busy"
    assert "slot_1" in res["error"]


def test_protected_paths_untouched_backup_pruned_and_registry_updated(tmp_path: Path):
    app_root = tmp_path / "App"
    cache_dir = tmp_path / "Cache"
    reg_path = tmp_path / "Updates" / "version_registry.json"

    # Seed existing app & protected paths
    (app_root / "Core").mkdir(parents=True)
    (app_root / "Core" / "config.py").write_text("__version__ = '0.25.0-beta.6'\n", encoding="utf-8")
    (app_root / "requirements.txt").write_text("requests==2.34.2\n", encoding="utf-8")

    (app_root / "Data").mkdir(parents=True)
    (app_root / "Data" / "Inventory.csv").write_text("SKU,Player\n1000001,LiveUser\n", encoding="utf-8")
    (app_root / "Cache").mkdir(parents=True)
    (app_root / "Cache" / "state.json").write_text('{"keep": true}', encoding="utf-8")
    (app_root / ".git").mkdir(parents=True)
    (app_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (app_root / ".agents").mkdir(parents=True)
    (app_root / ".agents" / "rules.md").write_text("keep rules", encoding="utf-8")
    (app_root / ".env").write_text("SECRET=1\n", encoding="utf-8")

    # Seed 6 older backup zips to verify pruning keeps only 5 most recent
    backups_dir = cache_dir / "Update_Backups"
    backups_dir.mkdir(parents=True)
    for idx in range(6):
        bp = backups_dir / f"pre_update_v0.25.0-beta.{idx}_2026110{idx}_000000.zip"
        bp.write_bytes(b"old")
        os.utime(bp, (1700000000 + idx * 10, 1700000000 + idx * 10))

    zip_bytes = _build_zip_bytes({
        "Core/config.py": b"__version__ = '0.25.0-beta.7'\n",
        "requirements.txt": b"requests==2.34.2\npackaging==24.2\n",
        "Data/Inventory.csv": b"OVERWRITTEN",
        "Cache/state.json": b"OVERWRITTEN",
        ".git/HEAD": b"OVERWRITTEN",
        ".agents/rules.md": b"OVERWRITTEN",
        ".env": b"OVERWRITTEN",
    })
    digest = hashlib.sha256(zip_bytes).hexdigest()
    rel = _make_release_info()
    session = _MockSession({
        rel["checksum_asset_api_url"]: _MockResponse(200, text=f"{digest}  {rel['zip_asset_name']}\n"),
        rel["zip_asset_api_url"]: _MockResponse(200, content=zip_bytes),
    })

    res = updater.apply_github_release_update(
        rel,
        app_root,
        {"github_token": "tok"},
        session=session,
        busy_checker=lambda: (False, ""),
        cache_dir=cache_dir,
        registry_path=reg_path,
    )
    assert res["success"] is True
    assert res["restart_required"] is True
    assert res["requirements_changed"] is True
    assert "Core/config.py" in res["files_updated"]
    assert "Data/Inventory.csv" in res["files_skipped_protected"]

    # Code updated
    assert (app_root / "Core" / "config.py").read_text(encoding="utf-8") == "__version__ = '0.25.0-beta.7'\n"

    # Protected files completely untouched
    assert (app_root / "Data" / "Inventory.csv").read_text(encoding="utf-8") == "SKU,Player\n1000001,LiveUser\n"
    assert (app_root / "Cache" / "state.json").read_text(encoding="utf-8") == '{"keep": true}'
    assert (app_root / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert (app_root / ".agents" / "rules.md").read_text(encoding="utf-8") == "keep rules"
    assert (app_root / ".env").read_text(encoding="utf-8") == "SECRET=1\n"

    # Backup created and pruned to 5 most recent
    remaining_backups = list(backups_dir.glob("pre_update_*.zip"))
    assert len(remaining_backups) == 5
    assert Path(res["backup_zip"]).exists()

    # Registry updated atomically
    reg_data = json.loads(reg_path.read_text(encoding="utf-8"))
    assert reg_data["current_release_version"] == "0.25.0-beta.7"
    assert "github:v0.25.0-beta.7" in reg_data["applied_packages"]
    assert reg_data["version_history"][-1]["version"] == "0.25.0-beta.7"
