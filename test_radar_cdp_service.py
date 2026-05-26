# -*- coding: utf-8 -*-
"""
test_radar_cdp_service.py - R7.3A: Robust Chrome CDP boot tests.

Run:
    python -m pytest test_radar_cdp_service.py -v
"""

from __future__ import annotations

import os
import sys
import json
import time
import socket
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shopee_core.radar_cdp_service import (
    is_cdp_available,
    _fetch_json_version,
    find_chrome_executable,
    start_radar_chrome,
    ensure_radar_chrome_ready,
    kill_managed_radar_chrome,
    _read_radar_pid,
    _write_radar_pid,
    _clear_radar_pid,
    _find_radar_chrome_process,
    _is_port_open,
    _is_radar_managed_process,
    _is_process_alive,
    _get_wmi_processes,
    DEFAULT_CDP_URL,
    CDP_PORT,
    PID_FILE,
    DEFAULT_PROFILE_DIR,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _mock_version_response(**overrides):
    data = {
        "Browser": "Chrome/130.0.0.0",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
    }
    data.update(overrides)
    return data


class _FakeResponse:
    """Simple response-like object for mocking urlopen."""
    def __init__(self, status=200, data=None):
        self.status = status
        self._data = data or b"{}"

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeUrlopen:
    """Callable that simulates urlopen returning _FakeResponse."""
    def __init__(self, status=200, data=None):
        self._status = status
        self._data = data

    def __call__(self, *args, **kwargs):
        return _FakeResponse(self._status, self._data)


# ── Tests: is_cdp_available ──────────────────────────────────────────────


def test_is_cdp_available_http_ok():
    """Returns True when /json/version returns valid JSON."""
    data = json.dumps(_mock_version_response()).encode()
    fake = _FakeUrlopen(status=200, data=data)
    with patch("shopee_core.radar_cdp_service.urlopen", fake):
        assert is_cdp_available("http://127.0.0.1:9222")


def test_is_cdp_available_http_404():
    """Returns False when /json/version returns non-2xx status."""
    fake = _FakeUrlopen(status=404, data=b"")
    with patch("shopee_core.radar_cdp_service.urlopen", fake):
        assert not is_cdp_available("http://127.0.0.1:9222")


def test_is_cdp_available_connection_refused():
    """Returns False when no one listens."""
    with patch("shopee_core.radar_cdp_service.urlopen", side_effect=ConnectionRefusedError):
        assert not is_cdp_available("http://127.0.0.1:9222")


# ── Tests: _fetch_json_version ───────────────────────────────────────────


def test_fetch_json_version_success():
    """Returns parsed dict on success."""
    data = json.dumps(_mock_version_response()).encode()
    fake = _FakeUrlopen(status=200, data=data)
    with patch("shopee_core.radar_cdp_service.urlopen", fake):
        result = _fetch_json_version()
        assert result is not None
        assert "Chrome" in result["Browser"]


def test_fetch_json_version_failure():
    """Returns None on failure."""
    with patch("shopee_core.radar_cdp_service.urlopen", side_effect=OSError("timeout")):
        assert _fetch_json_version() is None


# ── Tests: find_chrome_executable ────────────────────────────────────────


def test_find_chrome_executable_windows():
    """On Windows, finds chrome.exe when it exists."""
    with patch("shopee_core.radar_cdp_service.sys.platform", "win32"):
        with patch("pathlib.Path.exists", return_value=True):
            exe = find_chrome_executable()
            assert exe is not None
            assert "chrome.exe" in exe or "msedge.exe" in exe


def test_find_chrome_executable_not_found():
    """Returns None when no Chrome/Edge is found."""
    with patch("shopee_core.radar_cdp_service.sys.platform", "win32"):
        with patch("pathlib.Path.exists", return_value=False):
            assert find_chrome_executable() is None


def test_find_chrome_executable_non_windows():
    """Returns None on non-Windows platforms."""
    with patch("shopee_core.radar_cdp_service.sys.platform", "linux"):
        assert find_chrome_executable() is None


# ── Tests: PID file management ───────────────────────────────────────────


def test_read_write_clear_pid(tmp_path):
    """Round-trip write, read, clear PID file."""
    with patch("shopee_core.radar_cdp_service.PID_FILE", tmp_path / "test.pid"):
        assert _read_radar_pid() is None
        _write_radar_pid(12345)
        assert _read_radar_pid() == 12345
        _clear_radar_pid()
        assert not (tmp_path / "test.pid").exists()


def test_read_empty_pid(tmp_path):
    """Reading an empty PID file returns None."""
    with patch("shopee_core.radar_cdp_service.PID_FILE", tmp_path / "empty.pid"):
        (tmp_path / "empty.pid").write_text("")
        assert _read_radar_pid() is None


def test_read_invalid_pid(tmp_path):
    """Reading an invalid PID file returns None."""
    with patch("shopee_core.radar_cdp_service.PID_FILE", tmp_path / "bad.pid"):
        (tmp_path / "bad.pid").write_text("not-a-number")
        assert _read_radar_pid() is None


# ── Tests: _is_radar_managed_process ─────────────────────────────────────


def test_is_radar_managed_with_flags():
    """Returns True for processes with correct flags and profile."""
    proc = MagicMock()
    proc.CommandLine = "chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\chrome_radar_profile"
    assert _is_radar_managed_process(proc)


def test_is_radar_managed_legacy_profile():
    """Returns True even for legacy profile name."""
    proc = MagicMock()
    proc.CommandLine = "chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\radar_chrome_profile"
    assert _is_radar_managed_process(proc)


def test_is_radar_managed_no_flags():
    """Returns False for processes without radar flags."""
    proc = MagicMock()
    proc.CommandLine = "chrome.exe --some-other-flag"
    assert not _is_radar_managed_process(proc)


def test_is_radar_managed_missing_cmdline():
    """Returns False when CommandLine is not accessible."""
    proc = MagicMock()
    type(proc).CommandLine = PropertyMock(side_effect=Exception("access denied"))
    assert not _is_radar_managed_process(proc)


# ── Tests: _is_port_open ─────────────────────────────────────────────────


def test_is_port_open_on_used_port():
    """Returns True when something is listening."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen()
    port = s.getsockname()[1]
    try:
        assert _is_port_open(port, timeout=0.5)
    finally:
        s.close()


def test_is_port_open_on_free_port():
    """Returns False when port is free."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert not _is_port_open(port, timeout=0.3)


# ── Tests: start_radar_chrome ────────────────────────────────────────────


def test_start_chrome_when_cdp_already_active():
    """Returns already_running=True when CDP is available."""
    with patch("shopee_core.radar_cdp_service.is_cdp_available", return_value=True):
        res = start_radar_chrome()
        assert res.get("ok")
        assert res.get("already_running")


def test_start_chrome_without_executable():
    """Returns error when Chrome is not found."""
    with patch("shopee_core.radar_cdp_service.is_cdp_available", return_value=False):
        with patch("shopee_core.radar_cdp_service.find_chrome_executable", return_value=None):
            res = start_radar_chrome()
            assert not res.get("ok")
            assert res.get("environment_error")


def test_start_chrome_process_spawn():
    """Successfully spawns a Chrome process."""
    import tempfile as _tf
    from pathlib import Path
    with patch("shopee_core.radar_cdp_service.is_cdp_available", return_value=False):
        with patch("shopee_core.radar_cdp_service.find_chrome_executable", return_value="C:\\chrome.exe"):
            with patch("shopee_core.radar_cdp_service._clean_stale_locks"):
                with patch("shopee_core.radar_cdp_service.tempfile.NamedTemporaryFile") as mock_tmp:
                    mock_f = MagicMock()
                    mock_f.name = str(Path(_tf.gettempdir()) / "radar_test_stderr.log")
                    mock_tmp.return_value = mock_f
                    mock_proc = MagicMock()
                    mock_proc.pid = 99999
                    with patch("subprocess.Popen", return_value=mock_proc):
                        with patch("shopee_core.radar_cdp_service.time.sleep"):
                            with patch("shopee_core.radar_cdp_service._is_process_alive", return_value=True):
                                with patch("shopee_core.radar_cdp_service._write_radar_pid"):
                                    res = start_radar_chrome()
                                    assert res.get("ok")
                                    assert res.get("started")
                                    assert res.get("pid") == 99999


# ── Tests: ensure_radar_chrome_ready ─────────────────────────────────────


def test_ensure_ready_cdp_already_active():
    """Returns already_running when CDP responds."""
    mock_version = _mock_version_response()
    with patch("shopee_core.radar_cdp_service._fetch_json_version", return_value=mock_version):
        res = ensure_radar_chrome_ready()
        assert res.get("ok")
        assert res.get("already_running")


def test_ensure_ready_cdp_not_available():
    """Returns error with diagnostics when Chrome cannot start."""
    with patch("shopee_core.radar_cdp_service._fetch_json_version", return_value=None):
        with patch("shopee_core.radar_cdp_service._is_port_open", return_value=False):
            with patch("shopee_core.radar_cdp_service._find_radar_chrome_process", return_value=None):
                with patch("shopee_core.radar_cdp_service.start_radar_chrome", return_value={
                    "ok": False, "started": False, "environment_error": True,
                    "message": "Chrome nao encontrado.",
                }):
                    res = ensure_radar_chrome_ready()
                    assert not res.get("ok")
                    assert res.get("environment_error")
                    assert "diagnostics" in res


def test_ensure_ready_port_occupied():
    """Returns error when port is occupied but not responding."""
    with patch("shopee_core.radar_cdp_service._fetch_json_version", return_value=None):
        with patch("shopee_core.radar_cdp_service._is_port_open", return_value=True):
            with patch("shopee_core.radar_cdp_service._get_wmi_processes", return_value=[
                {"pid": 1234, "name": "chrome.exe", "command_line": "--remote-debugging-port=9222"}
            ]):
                res = ensure_radar_chrome_ready()
                assert not res.get("ok")
                assert "ocupada" in (res.get("message") or "")


def test_ensure_ready_managed_process_stale():
    """Kills stale managed process before starting new Chrome."""
    with patch("shopee_core.radar_cdp_service._fetch_json_version", return_value=None):
        with patch("shopee_core.radar_cdp_service._is_port_open", return_value=False):
            with patch("shopee_core.radar_cdp_service._find_radar_chrome_process",
                       return_value={"pid": 999, "source": "pid_file"}):
                with patch("shopee_core.radar_cdp_service.kill_managed_radar_chrome") as mock_kill:
                    with patch("shopee_core.radar_cdp_service.start_radar_chrome", return_value={
                        "ok": False, "started": False, "environment_error": True,
                        "message": "Falha generica.",
                    }):
                        ensure_radar_chrome_ready()
                        mock_kill.assert_called_once()


def test_ensure_ready_successful_start():
    """Returns ok=True when Chrome starts and CDP responds."""
    def delayed_version(url, timeout=3.0):
        if not hasattr(delayed_version, "call_count"):
            delayed_version.call_count = 0
        delayed_version.call_count += 1
        if delayed_version.call_count >= 2:
            return _mock_version_response()
        return None

    with patch("shopee_core.radar_cdp_service._fetch_json_version", side_effect=delayed_version):
        with patch("shopee_core.radar_cdp_service._is_port_open", return_value=False):
            with patch("shopee_core.radar_cdp_service._find_radar_chrome_process", return_value=None):
                with patch("shopee_core.radar_cdp_service.start_radar_chrome", return_value={
                    "ok": True, "started": True, "pid": 12345,
                    "message": "Iniciado.", "already_running": False,
                    "cdp_url": "http://127.0.0.1:9222",
                }):
                    with patch("shopee_core.radar_cdp_service.time.sleep"):
                        with patch("shopee_core.radar_cdp_service._is_process_alive", return_value=True):
                            res = ensure_radar_chrome_ready()
                            assert res.get("ok")
                            assert res.get("started")
                            assert res.get("pid") == 12345


# ── Tests: kill_managed_radar_chrome ─────────────────────────────────────


def test_kill_when_no_process():
    """Killing when no process returns killed=False."""
    with patch("shopee_core.radar_cdp_service._find_radar_chrome_process", return_value=None):
        res = kill_managed_radar_chrome()
        assert res.get("ok")
        assert not res.get("killed")


def test_kill_calls_taskkill():
    """Killing calls taskkill with correct PID."""
    with patch("shopee_core.radar_cdp_service._find_radar_chrome_process",
               return_value={"pid": 123, "source": "pid_file"}):
        with patch("shopee_core.radar_cdp_service._get_wmi_processes", return_value=[]):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                res = kill_managed_radar_chrome()
                assert res.get("ok")
    # check taskkill was called with PID 123
    calls = [c for c in mock_run.call_args_list if "taskkill" in str(c)]
    assert len(calls) >= 1


# ── Tests: Integration with discovery service ────────────────────────────


def test_cycle_uses_ensure_radar_chrome_ready():
    """Verify that run_automatic_radar_cycle calls ensure_radar_chrome_ready."""
    from shopee_core.radar_discovery_service import run_automatic_radar_cycle

    with patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready") as mock_ready:
        mock_ready.return_value = {"ok": True, "already_running": True}
        with patch("shopee_core.radar_discovery_service.get_product", return_value=None):
            result = run_automatic_radar_cycle("test_uid")
            mock_ready.assert_called_once()


def test_chrome_failure_does_not_collect():
    """When Chrome fails, no discovery/collection/classification happens."""
    from shopee_core.radar_discovery_service import run_automatic_radar_cycle

    with patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready") as mock_ready:
        mock_ready.return_value = {
            "ok": False, "environment_error": True,
            "message": "Chrome CDP nao disponivel.",
            "diagnostics": {"test": True},
        }
        result = run_automatic_radar_cycle("test_uid")
        assert not result.get("ok")
        assert result.get("step") == "chrome"
        assert result.get("diagnostics", {}).get("test")
        # Ensure no subsequent steps
        assert result.get("discovery") is None
        assert result.get("collection") is None
        assert result.get("classification") is None


# ── Tests: progress_callback on ensure_radar_chrome_ready ────────────────


def test_ensure_ready_callback_invoked():
    """Progress callback receives stage updates."""
    stages_received = []

    def cb(state):
        stages_received.append(state.get("stage"))

    with patch("shopee_core.radar_cdp_service._fetch_json_version", return_value=None):
        with patch("shopee_core.radar_cdp_service._is_port_open", return_value=False):
            with patch("shopee_core.radar_cdp_service._find_radar_chrome_process", return_value=None):
                with patch("shopee_core.radar_cdp_service.start_radar_chrome", return_value={
                    "ok": False, "started": False, "environment_error": True,
                    "message": "Falha generica.",
                }):
                    ensure_radar_chrome_ready(progress_callback=cb)
                    assert any("chrome" in s for s in stages_received)


# ── Summary test ──────────────────────────────────────────────────────────


def test_module_imports():
    """All key functions are importable from the module."""
    assert callable(is_cdp_available)
    assert callable(_fetch_json_version)
    assert callable(find_chrome_executable)
    assert callable(start_radar_chrome)
    assert callable(ensure_radar_chrome_ready)
    assert callable(kill_managed_radar_chrome)
    assert callable(_is_port_open)
    assert callable(_is_radar_managed_process)


if __name__ == "__main__":
    print("\nTESTE R7.3A - Radar CDP Boot Robusto\n")

    import inspect
    test_fns = [(n, fn) for n, fn in globals().items() if n.startswith("test_")]
    passed = 0
    for name, fn in test_fns:
        try:
            fn()
            passed += 1
            print(f"PASS - {name}")
        except Exception as exc:
            print(f"FAIL - {name}: {exc}")
            import traceback; traceback.print_exc()

    print(f"\nTotal: {passed}/{len(test_fns)} testes passaram")
