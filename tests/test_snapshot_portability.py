"""Windows metadata differences must not look like concurrent edits."""

import os
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from test_ui import make_window, ready

from patchtorepo.engine import snapshot
from patchtorepo.patch import PatchError


def changed_stat(info, **values):
    fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
    return SimpleNamespace(**(fields | values))


@pytest.mark.parametrize("field", ["st_ctime_ns", "st_ino", "st_dev"])
def test_different_path_and_descriptor_metadata(monkeypatch, repo, field):
    original = os.fstat

    def fstat(fd):
        info = original(fd)
        return changed_stat(info, **{field: getattr(info, field) + 100})

    monkeypatch.setattr(os, "fstat", fstat)
    result = snapshot(repo, ("hello.cpp",))
    assert result[0].content == (repo / "hello.cpp").read_bytes()


@pytest.mark.parametrize("field", ["st_ctime_ns", "st_mtime_ns", "st_size"])
def test_descriptor_change_during_read_is_rejected(monkeypatch, repo, field):
    original = os.fstat
    calls = 0

    def fstat(fd):
        nonlocal calls
        calls += 1
        info = original(fd)
        return changed_stat(info, **{field: getattr(info, field) + (calls - 1)})

    monkeypatch.setattr(os, "fstat", fstat)
    with pytest.raises(PatchError, match="changed while being read"):
        snapshot(repo, ("hello.cpp",))


@pytest.mark.parametrize("operation", ["replace", "delete"])
@pytest.mark.skipif(os.name == "nt", reason="Windows denies replacement of this open handle")
def test_path_changes_during_read_are_rejected(monkeypatch, repo, operation):
    original = os.fstat
    calls = 0
    path = repo / "hello.cpp"

    def fstat(fd):
        nonlocal calls
        calls += 1
        info = original(fd)
        if calls == 2:
            if operation == "delete":
                path.unlink()
            else:
                replacement = repo / "replacement"
                replacement.write_bytes(path.read_bytes())
                os.replace(replacement, path)
        return info

    monkeypatch.setattr(os, "fstat", fstat)
    with pytest.raises(PatchError, match="while being read"):
        snapshot(repo, ("hello.cpp",))


def test_previously_modified_file_can_be_read(tmp_path):
    path = tmp_path / "previously-edited.cpp"
    path.write_bytes(b"before\n")
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    path.write_bytes(b"after\n")
    assert snapshot(tmp_path, (path.name,))[0].content == b"after\n"


def test_preview_failure_shows_selected_repo_only(qtbot, tmp_path, repo, patch, monkeypatch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.diagnostics.appendPlainText("unrelated-repo: No such file or directory")
    original_review = window.engine.review

    def fail(*args):
        raise PatchError("File changed while being read: hello.cpp. Run Check again.")

    monkeypatch.setattr(window.engine, "review", fail)
    window.check()
    qtbot.waitUntil(lambda: window._job is None)
    assert "unrelated-repo" not in window.diagnostics.toPlainText()
    assert str(repo) in window.diagnostics.toPlainText()
    assert "File changed" in window.diagnostics.toPlainText()
    assert "check failed" in window.repos.currentText()
    assert "ready" not in window.repos.currentText()
    assert window.file_title.text() == "Preview could not be built"
    assert not window.apply_button.isEnabled()
    monkeypatch.setattr(window.engine, "review", original_review)
    window.check()
    ready(qtbot, window)
    assert "ready" in window.repos.currentText()
    assert window.repos.currentData(Qt.ItemDataRole.ToolTipRole) == "Check passed"
