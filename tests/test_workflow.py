import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QLabel, QMessageBox
from test_ui import make_window, ready

from patchtorepo.diff import Line, Rendered
from patchtorepo.engine import Applied
from patchtorepo.patch import PatchError
from patchtorepo.widgets import DiffView
from patchtorepo.window import MainWindow


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
def test_partner_editor_scrolls_without_focus_change(qtbot, side, axis):
    view = DiffView()
    qtbot.addWidget(view)
    view.resize(900, 500)
    view.show()
    rows = tuple(Line(f"{i:04d} " + "abcdef " * 100, i + 1) for i in range(150))
    view.show_render(Rendered(rows, rows, (), ""))
    source = getattr(view, side)
    target = view.right if side == "left" else view.left
    source.setFocus()
    get_bar = f"{axis}ScrollBar"
    a, b = getattr(source, get_bar)(), getattr(target, get_bar)()
    qtbot.waitUntil(lambda: min(a.maximum(), b.maximum()) > 30)
    updates = QSignalSpy(target.updateRequest)
    a.setValue(30)
    assert b.value() == 30
    assert updates.count() > 0  # Qt must scroll the viewport, not just move the thumb
    a.setValue(0)
    assert b.value() == 0
    assert updates.count() > 1


@pytest.mark.parametrize("enabled,queued", [(False, False), (True, False), (True, True)])
def test_close_after_verified_apply(qtbot, tmp_path, repo, patch, enabled, queued):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.close_after_apply.setChecked(enabled)
    if queued:
        window.enqueue(str(tmp_path / "next.patch"))
    window.ack.setChecked(True)
    window.apply()
    qtbot.waitUntil(lambda: window._job is None and window._applied)
    if enabled and not queued:
        qtbot.waitUntil(lambda: not window.isVisible())
    else:
        qtbot.wait(30)
        assert window.isVisible()
    assert b"return 2" in (repo / "hello.cpp").read_bytes()


@pytest.mark.parametrize("result", ["failure", "unverified"])
def test_close_option_does_not_hide_apply_problems(
    qtbot, tmp_path, repo, patch, monkeypatch, result
):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.close_after_apply.setChecked(True)

    def apply(_):
        if result == "failure":
            raise PatchError("simulated apply failure")
        return Applied(tmp_path / "backup.zip", "verification mismatch", False)

    monkeypatch.setattr(window.engine, "apply", apply)
    window.ack.setChecked(True)
    window.apply()
    qtbot.waitUntil(lambda: window._job is None)
    qtbot.wait(30)
    assert window.isVisible()
    assert not window.apply_button.isEnabled()


def test_close_preference_persists_and_save_failure_reverts(
    qtbot, tmp_path, repo, patch, monkeypatch
):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.close_after_apply.setChecked(True)
    other = MainWindow(window.store)
    qtbot.addWidget(other)
    other.show()
    qtbot.waitUntil(lambda: other._job is None and other.engine is not None)
    assert other.close_after_apply.isChecked()
    other.close()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(window.store, "set", fail)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    window.close_after_apply.setChecked(False)
    assert window.close_after_apply.isChecked()
    assert "could not be saved" in window.status_label.text()


def test_footer_controls_are_adjacent_and_tagline_removed(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.resize(960, 620)
    qtbot.wait(30)
    assert not any(label.text() == "Review. Check. Apply." for label in window.findChildren(QLabel))
    ack_right = window.ack.mapTo(window, window.ack.rect().topRight()).x()
    apply_left = window.apply_button.mapTo(window, window.apply_button.rect().topLeft()).x()
    assert 0 <= apply_left - ack_right <= 25
    assert window.ack.nextInFocusChain() == window.apply_button
