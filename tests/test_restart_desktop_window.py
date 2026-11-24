from __future__ import annotations

import errno
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import launch_tabulas_hub


def _reset_restart_globals(monkeypatch, *, port: int = 5000, force_browser: bool = False, open_window: bool = True):
    monkeypatch.setattr(launch_tabulas_hub, "_RESTART_IN_PROGRESS", False)
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_HTTP_SERVER", None)
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_WEBVIEW_WINDOW", None)
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_SERVER_PORT", port)
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_FORCE_BROWSER", force_browser)
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_OPEN_WINDOW", open_window)


def test_restart_from_desktop_mode_spawns_with_window_enabled(monkeypatch):
    _reset_restart_globals(monkeypatch, port=5000, force_browser=False, open_window=True)
    events: list[str] = []

    class _StubServer:
        def shutdown(self):
            events.append("server.shutdown")

        def server_close(self):
            events.append("server.server_close")

    class _StubWindow:
        def destroy(self):
            events.append("window.destroy")

    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_HTTP_SERVER", _StubServer())
    monkeypatch.setattr(launch_tabulas_hub, "_ACTIVE_WEBVIEW_WINDOW", _StubWindow())

    captured: dict = {}
    spawned = threading.Event()
    exited = threading.Event()

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = dict(kwargs)
        events.append("subprocess.Popen")
        spawned.set()
        return object()

    monkeypatch.setattr(launch_tabulas_hub.subprocess, "Popen", _fake_popen)

    res = launch_tabulas_hub.request_clean_server_restart(
        busy_checker=lambda: (False, ""),
        exit_fn=lambda: (events.append("exit"), exited.set()),
        delay_seconds=0.01,
    )

    assert res["success"] is True
    assert res["restarting"] is True
    assert spawned.wait(timeout=2.0)
    assert exited.wait(timeout=2.0)

    expected_script = str(Path(launch_tabulas_hub.__file__).resolve())
    cmd = captured["cmd"]
    assert cmd == [sys.executable, expected_script, "--port", "5000"]
    for forbidden in ("--no-open", "--no-window", "--headless", "--browser"):
        assert forbidden not in cmd

    flags = captured["kwargs"].get("creationflags", 0)
    assert not (flags & getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    assert not (flags & getattr(subprocess, "DETACHED_PROCESS", 0x00000008))

    assert events.index("server.shutdown") < events.index("subprocess.Popen")
    assert events.index("server.server_close") < events.index("subprocess.Popen")
    assert events.index("subprocess.Popen") < events.index("window.destroy")
    assert events.index("window.destroy") < events.index("exit")


def test_restart_from_explicit_headless_mode_preserves_headless_flags(monkeypatch):
    _reset_restart_globals(monkeypatch, port=5051, force_browser=False, open_window=False)

    captured: dict = {}
    spawned = threading.Event()
    exited = threading.Event()

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        spawned.set()
        return object()

    monkeypatch.setattr(launch_tabulas_hub.subprocess, "Popen", _fake_popen)

    res = launch_tabulas_hub.request_clean_server_restart(
        busy_checker=lambda: (False, ""),
        exit_fn=lambda: exited.set(),
        delay_seconds=0.01,
    )

    assert res["success"] is True
    assert spawned.wait(timeout=2.0)
    assert exited.wait(timeout=2.0)
    assert "--no-open" in captured["cmd"]
    assert "--browser" not in captured["cmd"]
    assert ["--port", "5051"] == captured["cmd"][2:4]


def test_restart_from_explicit_browser_mode_preserves_browser_and_suppresses_window(monkeypatch):
    _reset_restart_globals(monkeypatch, port=5051, force_browser=True, open_window=True)

    captured: dict = {}
    spawned = threading.Event()
    exited = threading.Event()

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        spawned.set()
        return object()

    monkeypatch.setattr(launch_tabulas_hub.subprocess, "Popen", _fake_popen)

    res = launch_tabulas_hub.request_clean_server_restart(
        busy_checker=lambda: (False, ""),
        exit_fn=lambda: exited.set(),
        delay_seconds=0.01,
    )

    assert res["success"] is True
    assert spawned.wait(timeout=2.0)
    assert exited.wait(timeout=2.0)
    assert "--browser" in captured["cmd"]
    assert "--no-open" in captured["cmd"]


def test_restart_blocked_when_worker_pool_busy(monkeypatch):
    _reset_restart_globals(monkeypatch, port=5000, force_browser=False, open_window=True)
    popen_called = False

    def _fake_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        return object()

    monkeypatch.setattr(launch_tabulas_hub.subprocess, "Popen", _fake_popen)

    res = launch_tabulas_hub.request_clean_server_restart(
        busy_checker=lambda: (True, "slot_1: Active Scrape"),
    )

    assert res["success"] is False
    assert res["aborted"] is True
    assert res["reason"] == "worker_pool_busy"
    assert popen_called is False


def test_bind_http_server_with_retry_handles_port_handoff():
    attempts = 0
    sleeps: list[float] = []
    now = [0.0]

    def _fake_monotonic():
        return now[0]

    def _fake_sleep(dt: float):
        sleeps.append(dt)
        now[0] += dt

    def _flaky_server(addr, handler):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        return ("SERVER_OK", addr, handler)

    srv = launch_tabulas_hub._bind_http_server_with_retry(
        "127.0.0.1",
        5051,
        object(),
        timeout_seconds=5.0,
        initial_backoff=0.1,
        max_backoff=0.5,
        server_cls=_flaky_server,
        sleep_fn=_fake_sleep,
        monotonic_fn=_fake_monotonic,
    )
    assert srv[0] == "SERVER_OK"
    assert attempts == 3
    assert len(sleeps) == 2

    def _perm_error_server(addr, handler):
        raise OSError(errno.EACCES, "Permission denied")

    with pytest.raises(OSError) as exc_info:
        launch_tabulas_hub._bind_http_server_with_retry(
            "127.0.0.1",
            5051,
            object(),
            timeout_seconds=5.0,
            server_cls=_perm_error_server,
            sleep_fn=_fake_sleep,
            monotonic_fn=_fake_monotonic,
        )
    assert exc_info.value.errno == errno.EACCES

    now[0] = 0.0

    def _always_busy_server(addr, handler):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    with pytest.raises(OSError) as timeout_exc:
        launch_tabulas_hub._bind_http_server_with_retry(
            "127.0.0.1",
            5051,
            object(),
            timeout_seconds=0.3,
            initial_backoff=0.2,
            server_cls=_always_busy_server,
            sleep_fn=_fake_sleep,
            monotonic_fn=_fake_monotonic,
        )
    assert timeout_exc.value.errno == errno.EADDRINUSE
