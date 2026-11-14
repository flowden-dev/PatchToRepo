"""Whole-file change markers and compact, accessible line counts."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QScrollBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionSlider,
    QStyleOptionViewItem,
    QToolTip,
)

from .diff import Rendered

REMOVED_COLOR = "#ee7989"
ADDED_COLOR = "#4bc599"
OVERVIEW_WIDTH = 22


def counts_html(removed: int, added: int) -> str:
    return (
        f'<span style="color:{REMOVED_COLOR}">−{removed:,}</span>'
        f'&nbsp;&nbsp; <span style="color:{ADDED_COLOR}">+{added:,}</span>'
    )


@dataclass(frozen=True)
class Marker:
    start: int
    end: int
    kind: str


@dataclass(frozen=True)
class ChangeBlock:
    start: int
    end: int
    removed: int
    added: int


@dataclass(frozen=True)
class OverviewData:
    rows: int = 0
    markers: tuple[Marker, ...] = ()
    blocks: tuple[ChangeBlock, ...] = ()

    @classmethod
    def from_render(cls, rendered: Rendered) -> OverviewData:
        if rendered.limited:
            return cls()
        markers = []
        for lines, kind in ((rendered.left, "removed"), (rendered.right, "added")):
            start = None
            for i in range(len(lines) + 1):
                changed = i < len(lines) and lines[i].kind == kind
                if changed and start is None:
                    start = i
                elif not changed and start is not None:
                    markers.append(Marker(start, i, kind))
                    start = None
        # merge overlapping/touching lane runs into clickable change blocks
        blocks = []
        for marker in sorted(markers, key=lambda m: (m.start, m.end)):
            removed = marker.end - marker.start if marker.kind == "removed" else 0
            added = marker.end - marker.start if marker.kind == "added" else 0
            if blocks and marker.start <= blocks[-1].end:
                old = blocks.pop()
                blocks.append(
                    ChangeBlock(
                        old.start,
                        max(old.end, marker.end),
                        old.removed + removed,
                        old.added + added,
                    )
                )
            else:
                blocks.append(ChangeBlock(marker.start, marker.end, removed, added))
        return cls(max(len(rendered.left), len(rendered.right)), tuple(markers), tuple(blocks))


class ChangeOverview(QScrollBar):
    row_requested = Signal(int)

    def __init__(self, editor):
        super().__init__(Qt.Orientation.Vertical, editor)
        self.editor = editor
        self.data = OverviewData()
        self._dragging = False
        self._paint_markers: tuple[tuple[QRect, str], ...] | None = None
        self.setObjectName("changeOverview")
        self.setFixedWidth(OVERVIEW_WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("File change overview")
        self.setMouseTracking(True)

    def set_data(self, data: OverviewData):
        self.data = data
        self._dragging = False
        self._paint_markers = None
        self.setEnabled(data.rows > 0)
        self.setAccessibleDescription(
            f"{len(data.blocks)} change blocks. Red: removed; green: added. "
            "Click a marker to jump; drag the thumb's left edge to scroll. "
            "Up/Down: previous/next change; Home/End: file start/end."
        )
        self.update()

    def track_rect(self) -> QRect:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return (
            self.style()
            .subControlRect(
                QStyle.ComplexControl.CC_ScrollBar,
                option,
                QStyle.SubControl.SC_ScrollBarGroove,
                self,
            )
            .adjusted(1, 1, -1, -1)
        )

    def thumb_rect(self) -> QRect:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarSlider,
            self,
        )

    def row_at(self, y: float) -> int:
        track = self.track_rect()
        if self.data.rows <= 1 or track.height() <= 0:
            return 0
        return max(
            0, min(self.data.rows - 1, int((y - track.top()) * self.data.rows / track.height()))
        )

    def marker_rect(self, marker: Marker) -> QRect:
        return self._marker_rect(marker, self.track_rect())

    def _marker_rect(self, marker: Marker, track: QRect) -> QRect:
        if not self.data.rows or track.height() <= 0:
            return QRect()
        top = track.top() + marker.start * track.height() // self.data.rows
        bottom = track.top() + ceil(marker.end * track.height() / self.data.rows)
        height = min(track.height(), max(3, bottom - top))
        top = min(top, track.bottom() - height + 1)
        lane = 0 if marker.kind == "removed" else 1
        width = max(1, (track.width() - 11) // 2)
        return QRect(track.left() + 7 + lane * (width + 2), top, width, height)

    def block_at(self, y: float) -> ChangeBlock | None:
        track = self.track_rect()
        if not self.data.rows or track.height() <= 0:
            return None
        candidates = []
        for block in self.data.blocks:
            rect = self._marker_rect(Marker(block.start, block.end, "removed"), track)
            distance = max(rect.top() - y, y - rect.bottom(), 0)
            if distance <= 4:
                center_distance = abs(y - (rect.top() + rect.bottom()) / 2)
                candidates.append((distance, center_distance, block.start, block))
        return min(candidates, key=lambda c: c[:3])[3] if candidates else None

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        track = self.track_rect()
        if self.data.rows == 0 or track.height() <= 0:
            return
        # cache/deduplicate sub-pixel runs so repaint work is bounded by rail height
        if self._paint_markers is None:
            rects = {
                (r.x(), r.y(), r.width(), r.height(), marker.kind)
                for marker in self.data.markers
                if not (r := self._marker_rect(marker, track)).isEmpty()
            }
            self._paint_markers = tuple(
                (QRect(x, y, w, h), kind) for x, y, w, h, kind in sorted(rects)
            )
        for rect, kind in self._paint_markers:
            painter.fillRect(rect, QColor(REMOVED_COLOR if kind == "removed" else ADDED_COLOR))
        if self.hasFocus():
            painter.setPen(QColor("#ab98f5"))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def resizeEvent(self, event):
        self._paint_markers = None
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.data.rows:
            super().mousePressEvent(event)
            return
        block = self.block_at(event.position().y())
        if self.thumb_rect().contains(event.position().toPoint()) and (
            block is None or event.position().x() < self.track_rect().left() + 7
        ):
            self._dragging = False
            super().mousePressEvent(event)
            return
        self._dragging = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.row_requested.emit(block.start if block else self.row_at(event.position().y()))
        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.row_requested.emit(self.row_at(event.position().y()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        row = self.editor.textCursor().blockNumber()
        starts = [b.start for b in self.data.blocks]
        key = event.key()
        if key == Qt.Key.Key_Down and starts:
            row = next((start for start in starts if start > row), starts[0])
        elif key == Qt.Key.Key_Up and starts:
            row = next((start for start in reversed(starts) if start < row), starts[-1])
        elif key == Qt.Key.Key_Home:
            row = 0
        elif key == Qt.Key.Key_End:
            row = max(0, self.data.rows - 1)
        else:
            super().keyPressEvent(event)
            return
        self.row_requested.emit(row)
        event.accept()

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            block = self.block_at(event.pos().y())
            if block:
                text = f"−{block.removed:,} removed · +{block.added:,} added\nClick to jump to this change."
            else:
                text = (
                    "Red: removed · Green: added\nClick or drag to navigate the file. "
                    "Up/Down selects changes."
                )
            QToolTip.showText(event.globalPos(), text, self)
            return True
        if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.update()
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange):
            self._paint_markers = None
            self.update()
        return super().event(event)


class ChangeCountDelegate(QStyledItemDelegate):
    """Paint separate count colors while keeping ordinary accessible cell text."""

    def paint(self, painter, option, index):
        counts = index.data(Qt.ItemDataRole.UserRole)
        if counts is None:
            return super().paint(painter, option, index)
        removed, added = counts
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        painter.save()
        painter.setClipRect(option.rect)
        painter.setFont(opt.font)
        red, green = f"−{removed:,}", f"+{added:,}"
        width = opt.fontMetrics.horizontalAdvance(green)
        right = option.rect.adjusted(4, 0, -6, 0)
        painter.setPen(QColor(ADDED_COLOR))
        painter.drawText(right, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, green)
        right.adjust(0, 0, -(width + 10), 0)
        painter.setPen(QColor(REMOVED_COLOR))
        painter.drawText(right, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, red)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        counts = index.data(Qt.ItemDataRole.UserRole)
        if counts is not None:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            removed, added = counts
            width = (
                sum(
                    opt.fontMetrics.horizontalAdvance(text)
                    for text in (f"−{removed:,}", f"+{added:,}")
                )
                + 20
            )
            size = QSize(max(size.width(), width), size.height())
        return size
