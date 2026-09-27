import io
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from broken_handson import launcher


@pytest.fixture
def sync_runtime(monkeypatch, tmp_path):
    source = tmp_path / "app.py"
    edit = tmp_path / "edit.py"
    edit.write_text("new defense")
    monkeypatch.setattr(launcher, "ensure_edit_targets", lambda: None)
    monkeypatch.setattr(launcher, "_editable_pairs", lambda: [(source, edit, tmp_path / "baseline.py")])
    monkeypatch.setattr(launcher, "edit_targets_revision", lambda: "new")
    monkeypatch.setattr(launcher, "_ACTIVE_PROCESS", Mock(poll=lambda: None))
    monkeypatch.setattr(launcher, "_ACTIVE_RELOAD", True)
    monkeypatch.setattr(launcher.time, "sleep", lambda delay: None)
    return source


def test_sync_waits_for_loaded_revision(monkeypatch, sync_runtime):
    responses = iter([
        io.BytesIO(b'{"edit_targets_revision": "old"}'),
        OSError("server reloading"),
        io.BytesIO(b'{"edit_targets_revision": "new"}'),
    ])

    def open_revision(url, timeout):
        response = next(responses)
        if isinstance(response, OSError):
            raise response
        return response

    open_mock = Mock(side_effect=open_revision)
    monkeypatch.setattr(launcher.urllib.request, "urlopen", open_mock)
    launcher.sync_edit_targets()
    assert sync_runtime.read_text() == "new defense"
    assert open_mock.call_count == 3


def test_sync_without_server_only_copies(monkeypatch, sync_runtime):
    monkeypatch.setattr(launcher, "_ACTIVE_PROCESS", None)
    open_mock = Mock()
    monkeypatch.setattr(launcher.urllib.request, "urlopen", open_mock)
    launcher.sync_edit_targets()
    assert sync_runtime.read_text() == "new defense"
    open_mock.assert_not_called()


def test_sync_reports_reload_timeout(monkeypatch, sync_runtime):
    clock = iter([0, 41])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="再読み込み"):
        launcher.sync_edit_targets()


def test_sync_without_reload_does_not_wait(monkeypatch, sync_runtime):
    monkeypatch.setattr(launcher, "_ACTIVE_RELOAD", False)
    open_mock = Mock()
    monkeypatch.setattr(launcher.urllib.request, "urlopen", open_mock)
    launcher.sync_edit_targets()
    assert sync_runtime.read_text() == "new defense"
    open_mock.assert_not_called()