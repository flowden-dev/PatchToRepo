"""Whole-file map navigation, rendering bounds and trustworthy count displays."""

from itertools import pairwise

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
from test_ui import make_window, ready

from patchtorepo.diff import Line, Rendered, render
from patchtorepo.engine import FileState
from patchtorepo.overview import ChangeBlock, Marker, OverviewData
from patchtorepo.theme import STYLE
from patchtorepo.widgets import DiffView


def long_comparison(changes=(0, 500, 999)):
    left, right = [], []
    for i in range(1000):
        changed = i in changes
        left.append(
            Line(f"{i:04d} old " + "original " * 100, i + 1, "removed" if changed else "equal")
        )
        right.append(
            Line(f"{i:04d} new " + "updated " * 100, i + 1, "added" if changed else "equal")
        )
    return Rendered(tuple(left), tuple(right), changes, "test comparison")


@pytest.fixture
def view(qtbot):
    widget = DiffView()
    qtbot.addWidget(widget)
    widget.resize(1100, 550)
    widget.show()
    widget.show_render(long_comparison())
    qtbot.waitUntil(lambda: widget.left.verticalScrollBar().maximum() > 900)
    return widget


def test_unequal_replacement_counts_exclude_alignment_gaps():
    before = "\n".join(f"old {i}" for i in range(7)).encode()
    after = "\n".join(f"new {i}" for i in range(80)).encode()
    result = render(FileState("x", before), FileState("x", after), "x.txt")
    overview = OverviewData.from_render(result)
    assert overview.rows == 80
    assert overview.markers == (Marker(0, 7, "removed"), Marker(0, 80, "added"))
    assert overview.blocks == (ChangeBlock(0, 80, 7, 80),)


@pytest.mark.parametrize(
    "old,new,removed,added",
    [
        (None, b"a\nb\n", 0, 2),
        (b"a\nb\n", None, 2, 0),
        (b"a\n", b"a\n", 0, 0),
        (b"abc", b"abc\n", 0, 0),
    ],
)
def test_add_delete_equal_and_eof_metadata(old, new, removed, added):
    data = OverviewData.from_render(render(FileState("x", old), FileState("x", new), "x.txt"))
    assert sum(b.removed for b in data.blocks) == removed
    assert sum(b.added for b in data.blocks) == added


@pytest.mark.parametrize("content", [b"\0binary", b"x" * (2 * 1024 * 1024 + 1), b"x" * 10001])
def test_unavailable_text_previews_have_no_invented_markers(content):
    result = render(FileState("x", b"old"), FileState("x", content), "x.txt")
    assert result.limited
    assert OverviewData.from_render(result) == OverviewData()


@pytest.mark.parametrize("side", ["left", "right"])
def test_click_marker_moves_both_panes_and_preserves_horizontal_scroll(qtbot, view, side):
    view.right.horizontalScrollBar().setValue(90)
    positions = [editor.horizontalScrollBar().value() for editor in (view.left, view.right)]
    overview = getattr(view, side).overview
    target = overview.marker_rect(Marker(999, 1000, "added")).center()
    qtbot.mouseClick(overview, Qt.MouseButton.LeftButton, pos=target)
    for editor, position in zip((view.left, view.right), positions, strict=True):
        assert editor.textCursor().blockNumber() == 999
        assert editor.horizontalScrollBar().value() == position
        assert editor.firstVisibleBlock().blockNumber() <= 999
        assert editor.cursorForPosition(editor.viewport().rect().bottomLeft()).blockNumber() == 999
    assert view.change_index == 2
    view.navigate(1)
    assert view.left.textCursor().blockNumber() == 0
    assert view.right.textCursor().blockNumber() == 0
    assert view.change_index == 0


def test_marker_keyboard_navigation_wraps_and_supports_file_ends(qtbot, view):
    rail = view.left.overview
    rail.setFocus()
    for key, expected in [
        (Qt.Key.Key_Down, 500),
        (Qt.Key.Key_Down, 999),
        (Qt.Key.Key_Down, 0),
        (Qt.Key.Key_Up, 999),
        (Qt.Key.Key_Home, 0),
        (Qt.Key.Key_End, 999),
    ]:
        qtbot.keyClick(rail, key)
        assert view.left.textCursor().blockNumber() == expected
        assert view.right.textCursor().blockNumber() == expected


def test_click_blank_track_jumps_to_that_file_position(qtbot, view):
    rail = view.right.overview
    track = rail.track_rect()
    point = QPoint(track.center().x(), track.top() + track.height() // 4)
    assert rail.block_at(point.y()) is None
    expected = rail.row_at(point.y())
    qtbot.mouseClick(rail, Qt.MouseButton.LeftButton, pos=point)
    assert view.left.textCursor().blockNumber() == expected
    assert view.right.textCursor().blockNumber() == expected


@pytest.mark.parametrize(
    "row,direction,expected",
    [(25, 1, 100), (25, -1, 900), (250, -1, 100), (250, 1, 500), (950, -1, 900), (950, 1, 100)],
)
def test_navigation_after_seeking_unchanged_code_does_not_skip_changes(
    qtbot, view, row, direction, expected
):
    view.show_render(long_comparison((100, 500, 900)))
    view._overview_jump(view.left, row)
    assert view.change_count.text() == "3 changes"
    view.navigate(direction)
    assert view.left.textCursor().blockNumber() == expected
    assert view.right.textCursor().blockNumber() == expected


def test_drag_overview_and_wheel_continue_to_scroll(qtbot, view):
    rail = view.right.overview
    track = rail.track_rect()
    start = QPoint(track.center().x(), track.top())
    finish = QPoint(track.center().x(), track.bottom())
    qtbot.mousePress(rail, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(rail, finish)
    qtbot.mouseRelease(rail, Qt.MouseButton.LeftButton, pos=finish)
    assert view.right.textCursor().blockNumber() >= 990
    before = view.right.verticalScrollBar().value()
    event = QWheelEvent(
        QPointF(finish),
        QPointF(rail.mapToGlobal(finish)),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(rail, event)
    assert view.right.verticalScrollBar().value() < before
    assert view.left.verticalScrollBar().value() == view.right.verticalScrollBar().value()


@pytest.mark.parametrize("height", [40, 120, 550])
def test_first_last_markers_remain_inside_track_and_clickable(qtbot, view, height):
    rail = view.left.overview
    rail.resize(24, height)
    rail.set_data(
        OverviewData(
            40000,
            (Marker(0, 1, "removed"), Marker(39999, 40000, "added")),
            (ChangeBlock(0, 1, 1, 0), ChangeBlock(39999, 40000, 0, 1)),
        )
    )
    for marker in rail.data.markers:
        rect = rail.marker_rect(marker)
        assert rect.height() >= 3
        assert rail.track_rect().contains(rect)
        assert rail.block_at(rect.center().y()).start == marker.start
    assert rail.row_at(-100) == 0
    assert rail.row_at(100000) == 39999


def test_cached_markers_clear_on_resize_file_change_and_clear(qtbot, view):
    rail = view.left.overview
    rail.grab()
    first = rail._paint_markers
    assert first
    view.left.verticalScrollBar().setValue(200)
    rail.grab()
    assert rail._paint_markers is first
    view.resize(1000, 700)
    qtbot.wait(20)
    rail.grab()
    assert rail._paint_markers != first
    view.clear("No repository check")
    assert not rail.isEnabled()
    assert rail.data == OverviewData()
    assert view.removed_count.text() == ""
    assert view.added_count.text() == ""


def test_only_one_line_change_no_scrollbar_still_has_marker(qtbot, view):
    result = render(FileState("x", b"old\n"), FileState("x", b"new\n"), "x.txt")
    view.show_render(result)
    qtbot.wait(20)
    assert view.left.verticalScrollBar().maximum() == 0
    rail = view.left.overview
    assert rail.isEnabled()
    qtbot.mouseClick(
        rail, Qt.MouseButton.LeftButton, pos=rail.marker_rect(rail.data.markers[0]).center()
    )
    assert view.left.textCursor().blockNumber() == 0
    assert view.removed_count.text() == "−1"
    assert view.added_count.text() == "+1"


def test_patch_counts_remain_exact_for_eof_only_and_limited_previews(qtbot, view):
    result = render(FileState("x", b"abc"), FileState("x", b"abc\n"), "x.txt")
    view.show_render(result, (1, 1))
    assert not view.left.overview.data.markers
    assert view.removed_count.text() == "−1"
    assert view.added_count.text() == "+1"
    limited = Rendered(
        (Line("large file", None),), (Line("large file", None),), (), "Limited preview", True
    )
    view.show_render(limited, (7, 80))
    assert view.removed_count.text() == "−7"
    assert view.added_count.text() == "+80"
    assert not view.left.overview.isEnabled()
    view.show_render(limited)
    assert view.removed_count.text() == ""
    assert view.added_count.text() == ""


def test_window_counts_match_patch_and_cached_selection(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    change = patch.files[0]
    assert window.diff.removed_count.text() == f"−{change.removed}"
    assert window.diff.added_count.text() == f"+{change.added}"
    assert window.files.topLevelItem(0).data(1, Qt.ItemDataRole.UserRole) == (
        change.removed,
        change.added,
    )
    assert "#ee7989" in window.summary.text()
    assert "#4bc599" in window.summary.text()
    original = window.diff.left.overview.data
    window._file_changed(window.files.currentItem(), None)
    assert window.diff.left.overview.data == original
    assert window.diff.removed_count.text() == f"−{change.removed}"


def test_scrollbar_sync_still_emits_viewport_updates_with_overview(qtbot, view):
    spy = QSignalSpy(view.right.updateRequest)
    view.left.horizontalScrollBar().setValue(150)
    assert view.right.horizontalScrollBar().value() == 150
    assert spy.count() > 0
    assert view.left.verticalScrollBar() is view.left.overview
    assert (
        view.left.overview.mapTo(view.left, QPoint()).x() > view.left.viewport().geometry().right()
    )
    assert view.left.overview.height() == view.left.viewport().height()


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("styled", [False, True])
def test_integrated_thumb_drags_both_viewports_without_jumping(qtbot, view, side, styled):
    if styled:
        view.setStyleSheet(STYLE)
    qtbot.wait(20)
    source = getattr(view, side)
    target = view.right if source is view.left else view.left
    rail = source.overview
    source.horizontalScrollBar().setValue(90)
    rail.setValue(200)
    horizontal = [e.horizontalScrollBar().value() for e in (source, target)]
    before = rail.value()
    updates = [QSignalSpy(e.updateRequest) for e in (source, target)]
    jumps = QSignalSpy(rail.row_requested)
    start = QPoint(rail.track_rect().left() + 2, rail.thumb_rect().center().y())
    finish = start + QPoint(0, 100)
    qtbot.mousePress(rail, Qt.MouseButton.LeftButton, pos=start)
    assert rail.value() == before  # grabbing the thumb must retain the current position
    qtbot.mouseMove(rail, finish)
    qtbot.mouseRelease(rail, Qt.MouseButton.LeftButton, pos=finish)
    assert jumps.count() == 0
    assert rail.value() > before
    assert target.verticalScrollBar().value() == rail.value()
    assert source.firstVisibleBlock().blockNumber() == target.firstVisibleBlock().blockNumber()
    assert all(spy.count() for spy in updates)
    assert [e.horizontalScrollBar().value() for e in (source, target)] == horizontal
    assert not rail.isSliderDown()


@pytest.mark.parametrize("surface", ["viewport", "overview"])
def test_wheel_over_text_and_scrollbar_scrolls_once_without_recursion(qtbot, view, surface):
    view.setStyleSheet(STYLE)
    view.left.verticalScrollBar().setValue(300)
    widget = view.left.viewport() if surface == "viewport" else view.left.overview
    point = widget.rect().center()
    event = QWheelEvent(
        QPointF(point),
        QPointF(widget.mapToGlobal(point)),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    expected = 300 + QApplication.wheelScrollLines() * view.left.overview.singleStep()
    assert view.left.overview.value() == expected
    assert view.right.overview.value() == expected


def test_marker_remains_clickable_when_thumb_overlaps_it(qtbot, view):
    view.setStyleSheet(STYLE)
    view._jump(5)
    rail = view.left.overview
    point = rail.marker_rect(Marker(0, 1, "removed")).center()
    assert rail.thumb_rect().contains(point)
    qtbot.mouseClick(rail, Qt.MouseButton.LeftButton, pos=point)
    assert view.left.textCursor().blockNumber() == 0
    assert view.right.textCursor().blockNumber() == 0
    assert view.change_count.text() == "1 / 3 changes"


def test_change_counter_tracks_navigation_and_clears_with_preview(qtbot, view):
    assert view.change_count.text() == "1 / 3 changes"
    view.navigate(1)
    assert view.change_count.text() == "2 / 3 changes"
    view.navigate(-1)
    view.navigate(-1)
    assert view.change_count.text() == "3 / 3 changes"
    view.clear("Repository check required")
    assert view.change_count.text() == ""
    assert view.removed_count.isHidden()
    assert view.added_count.isHidden()
    view.show_render(render(FileState("x", b"old"), FileState("x", b"new"), "x.txt"))
    assert view.change_count.text() == "1 / 1 change"
    assert not view.removed_count.isHidden()


def test_panes_remain_aligned_when_only_one_side_has_long_lines(qtbot, view):
    left = tuple(Line(f"line {i}", i + 1) for i in range(150))
    right = tuple(Line(f"line {i} " + "wide " * 100, i + 1) for i in range(150))
    view.show_render(Rendered(left, right, (), ""))
    qtbot.waitUntil(lambda: view.right.horizontalScrollBar().maximum() > 100)
    assert view.left.horizontalScrollBar().maximum() == 0
    assert view.left.viewport().height() == view.right.viewport().height()
    view.right.overview.setValue(view.right.overview.maximum())
    assert view.left.overview.value() == view.right.overview.value()
    assert (
        view.left.firstVisibleBlock().blockNumber() == view.right.firstVisibleBlock().blockNumber()
    )


def test_compact_toolbar_counts_and_navigation_follow_review_state(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.setStyleSheet(STYLE)
    window.resize(960, 620)
    qtbot.wait(30)
    assert window.prev_change.isEnabled() and window.next_change.isEnabled()
    controls = [
        window.prev_change,
        window.next_change,
        window.diff.change_count,
        window.diff.removed_count,
        window.diff.added_count,
        window.find_text,
        window.encoding,
    ]
    rectangles = [c.rect().translated(c.mapTo(window, QPoint())) for c in controls]
    for a, b in pairwise(rectangles):
        assert a.right() < b.left()
        assert abs(a.center().y() - b.center().y()) <= 1
    assert all(window.rect().contains(rect) for rect in rectangles)
    window._invalidate_review("Repository check required")
    assert not window.prev_change.isEnabled() and not window.next_change.isEnabled()
    assert window.diff.change_count.text() == ""


def test_both_marker_colors_render_and_disappear_when_cleared(qtbot, view):
    rail = view.left.overview
    image = rail.grab().toImage()
    colors = {
        image.pixelColor(x, y).name() for y in range(image.height()) for x in range(image.width())
    }
    assert "#ee7989" in colors
    assert "#4bc599" in colors
    view.clear("No preview")
    image = rail.grab().toImage()
    colors = {
        image.pixelColor(x, y).name() for y in range(image.height()) for x in range(image.width())
    }
    assert "#ee7989" not in colors
    assert "#4bc599" not in colors


def test_binary_patch_summary_does_not_claim_zero_text_changes(qtbot, tmp_path, repo):
    from conftest import run

    from patchtorepo.patch import Patch

    binary = repo / "data.bin"
    binary.write_bytes(b"\0old")
    run(repo, "add", "data.bin")
    run(repo, "commit", "-qm", "binary base")
    binary.write_bytes(b"\0new")
    patch = Patch.parse(run(repo, "diff", "--binary"))
    run(repo, "checkout", "--", "data.bin")
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    assert "1 binary" in window.summary.text()
    assert "−0" not in window.summary.text()
    assert "+0" not in window.summary.text()
    assert window.files.topLevelItem(0).text(1) == "binary"
    assert not window.diff.left.overview.isEnabled()
    assert window.diff.removed_count.text() == ""
    assert window.diff.added_count.text() == ""
