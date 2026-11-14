from __future__ import annotations

from bisect import bisect_left, bisect_right
from functools import partial

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .diff import Line, Rendered
from .overview import ChangeOverview, OverviewData


class Highlighter(QSyntaxHighlighter):
    def __init__(self, editor):
        super().__init__(editor.document())
        self.editor = editor
        self.formats: dict[tuple, QTextCharFormat] = {}

    def highlightBlock(self, text):
        row = self.currentBlock().blockNumber()
        if row >= len(self.editor.lines):
            return
        for span in self.editor.lines[row].syntax:
            key = (span.color, span.bold, span.italic)
            fmt = self.formats.get(key)
            if fmt is None:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(span.color))
                if span.bold:
                    fmt.setFontWeight(QFont.Weight.Bold)
                fmt.setFontItalic(span.italic)
                self.formats[key] = fmt
            self.setFormat(span.start, span.length, fmt)


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lines: tuple[Line, ...] = ()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.setTabStopDistance(32)
        self.gutter = Gutter(self)
        self.overview = ChangeOverview(self)
        self.setVerticalScrollBar(self.overview)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.highlighter = Highlighter(self)
        self.blockCountChanged.connect(self.update_gutter_width)
        self.updateRequest.connect(self.update_gutter)
        self.set_code_font(11)
        self.update_gutter_width()

    def set_code_font(self, size):
        font = QFont("Consolas" if __import__("os").name == "nt" else "DejaVu Sans Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSizeF(size)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.update_gutter_width()

    def gutter_width(self):
        return 24 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(len(self.lines))))

    def update_gutter_width(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        self.overview.update()
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.viewport().geometry()
        self.gutter.setGeometry(QRect(0, area.top(), self.gutter_width(), area.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor("#171d28"))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            row = block.blockNumber()
            if block.isVisible() and top + height >= event.rect().top() and row < len(self.lines):
                line = self.lines[row]
                if line.kind in ("added", "removed"):
                    painter.fillRect(
                        0, top, 3, height, QColor("#4bc599" if line.kind == "added" else "#ee7989")
                    )
                painter.setPen(QColor("#7f8ca4"))
                if line.number is not None:
                    painter.drawText(
                        0,
                        top,
                        self.gutter.width() - 10,
                        height,
                        Qt.AlignmentFlag.AlignRight,
                        str(line.number),
                    )
            top += height
            block = block.next()

    def set_lines(self, lines: tuple[Line, ...]):
        self.setUpdatesEnabled(False)
        try:
            self.lines = lines
            self.setPlainText("\n".join(line.text for line in lines))
            selections = []
            colors = {"added": "#18382f", "removed": "#3b242e", "gap": "#1b2230"}
            for i, line in enumerate(lines):
                block = self.document().findBlockByNumber(i)
                if line.kind in colors:
                    selection = QTextEdit.ExtraSelection()
                    selection.cursor = QTextCursor(block)
                    selection.format.setBackground(QColor(colors[line.kind]))
                    selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                    selections.append(selection)
                for start, length in line.emphasis:
                    selection = QTextEdit.ExtraSelection()
                    selection.cursor = QTextCursor(block)
                    selection.cursor.setPosition(block.position() + start)
                    selection.cursor.setPosition(
                        block.position() + start + length, QTextCursor.MoveMode.KeepAnchor
                    )
                    selection.format.setBackground(
                        QColor("#285c48" if line.kind == "added" else "#713444")
                    )
                    selections.append(selection)
            self.setExtraSelections(selections)
            self.highlighter.rehighlight()
            self.update_gutter_width()
        finally:
            self.setUpdatesEnabled(True)
        self.gutter.update()

    def goto(self, row: int):
        self.setTextCursor(QTextCursor(self.document().findBlockByNumber(row)))
        self.centerCursor()


class DiffView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.old_label = QLabel("  Current working file")
        self.new_label = QLabel("  After patch")
        self.removed_count = QLabel()
        self.added_count = QLabel()
        self.removed_count.setObjectName("removedCount")
        self.added_count.setObjectName("addedCount")
        self.change_count = QLabel()
        self.change_count.setObjectName("section")
        self.summary = QWidget()
        summary_layout = QHBoxLayout(self.summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(6)
        for label in (self.change_count, self.removed_count, self.added_count):
            summary_layout.addWidget(label)
        layout.addWidget(self.summary)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left, self.right = CodeEditor(), CodeEditor()
        self._search_editor = self.right
        self.left.installEventFilter(self)
        self.right.installEventFilter(self)
        self.left.setAccessibleName("Current file")
        self.right.setAccessibleName("File after applying patch")
        for editor, label in (
            (self.left, self.old_label),
            (self.right, self.new_label),
        ):
            pane = QWidget()
            column = QVBoxLayout(pane)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            label.setObjectName("paneTitle")
            header = QWidget()
            header.setObjectName("paneHeader")
            row = QHBoxLayout(header)
            row.setContentsMargins(0, 0, 10, 0)
            row.addWidget(label, 1)
            column.addWidget(header)
            column.addWidget(editor, 1)
            splitter.addWidget(pane)
            editor.overview.setAccessibleName(f"{editor.accessibleName()} change overview")
            editor.overview.row_requested.connect(partial(self._overview_jump, editor))
        splitter.setSizes([600, 600])
        layout.addWidget(splitter, 1)
        self.note = QLabel("Open a patch to review its changes.")
        self.note.setObjectName("diffNote")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self._syncing = False
        for a, b in ((self.left, self.right), (self.right, self.left)):
            a.verticalScrollBar().valueChanged.connect(partial(self._sync, b.verticalScrollBar()))
            a.horizontalScrollBar().valueChanged.connect(
                partial(self._sync, b.horizontalScrollBar())
            )
        self.rendered = Rendered((), (), (), "")
        self.change_index = -1

    def _sync(self, target, value):
        # keep Qt's internal scroll/repaint signals; suppress only our feedback loop
        if self._syncing:
            return
        self._syncing = True
        try:
            target.setValue(value)
        finally:
            self._syncing = False

    def show_render(self, rendered: Rendered, line_counts: tuple[int, int] | None = None):
        self.rendered = rendered
        data = OverviewData.from_render(rendered)
        self.left.set_lines(rendered.left)
        self.right.set_lines(rendered.right)
        for editor in (self.left, self.right):
            editor.overview.set_data(data)
        if line_counts is None and not rendered.limited and data.rows:
            line_counts = (
                sum(block.removed for block in data.blocks),
                sum(block.added for block in data.blocks),
            )
        for label, sign, count, word in (
            (self.removed_count, "−", line_counts[0] if line_counts else None, "removed"),
            (self.added_count, "+", line_counts[1] if line_counts else None, "added"),
        ):
            label.setText(f"{sign}{count:,}" if count is not None else "")
            label.setToolTip(f"{count:,} lines {word} in this file" if count is not None else "")
            label.setAccessibleName(label.toolTip())
            label.setVisible(count is not None)
        self.note.setText(rendered.note)
        self.change_index = -1
        if rendered.changes:
            self.change_index = 0
            self._jump(rendered.changes[0])
        else:
            self._update_change_count()

    def _update_change_count(self):
        total = len(self.rendered.changes)
        noun = "change" if total == 1 else "changes"
        self.change_count.setText(
            f"{self.change_index + 1} / {total} {noun}"
            if total and self.change_index >= 0
            else f"{total} {noun}"
            if total
            else "Metadata preview"
            if self.rendered.limited
            else "No line changes"
            if self.rendered.left or self.rendered.right
            else ""
        )
        self.change_count.setToolTip("Highlighted change blocks in the selected file")

    def clear(self, message: str):
        self.show_render(Rendered((), (), (), message))

    def navigate(self, direction: int):
        if not self.rendered.changes or not direction:
            return
        if self.change_index >= 0:
            index = self.change_index + direction
        else:
            row = self._search_editor.textCursor().blockNumber()
            index = (
                bisect_right(self.rendered.changes, row)
                if direction > 0
                else bisect_left(self.rendered.changes, row) - 1
            )
        self.change_index = index % len(self.rendered.changes)
        row = self.rendered.changes[self.change_index]
        self._jump(row)

    def _jump(self, row: int):
        # navigating a marker must preserve the user's horizontal position
        positions = [editor.horizontalScrollBar().value() for editor in (self.left, self.right)]
        self._syncing = True
        try:
            for editor, position in zip((self.left, self.right), positions, strict=True):
                editor.goto(row)
                editor.horizontalScrollBar().setValue(position)
        finally:
            self._syncing = False
        self._update_change_count()

    def _overview_jump(self, editor, row: int):
        self._search_editor = editor
        inside_change = any(
            lines[row].kind in ("added", "removed")
            for lines in (self.rendered.left, self.rendered.right)
            if 0 <= row < len(lines)
        )
        # free seeking must not mark the preceding change as already selected
        self.change_index = bisect_right(self.rendered.changes, row) - 1 if inside_change else -1
        self._jump(row)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn and watched in (self.left, self.right):
            self._search_editor = watched
        return super().eventFilter(watched, event)

    def find(self, text: str) -> bool:
        if not text:
            return False
        other = self.right if self._search_editor is self.left else self.left
        for editor in (self._search_editor, other):
            if editor.find(text):
                self._search_editor = editor
                return True
            editor.moveCursor(QTextCursor.MoveOperation.Start)
            if editor.find(text):
                self._search_editor = editor
                return True
        return False
