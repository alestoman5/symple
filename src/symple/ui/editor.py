"""The input editor of a worksheet cell: highlighting, live diagnostics,
bracket matching and autocompletion."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QSizePolicy, QTextEdit, QToolTip

from ..catalog import CATALOG
from ..lang.analysis import analyze
from ..lang.diagnostics import ERROR, WARNING
from ..lang.lexer import tokenize
from ..lang.tokens import OPENERS, T
from . import theme
from .completer import KIND_ROLE, NAME_ROLE, Completer
from .highlighter import Highlighter

_CLOSERS = {v: k for k, v in OPENERS.items()}


class InputEditor(QPlainTextEdit):
    executeRequested = Signal()
    navigate = Signal(int)                 # -1 = previous cell, +1 = next cell
    focusReceived = Signal()
    diagnosticsChanged = Signal(list)
    statusMessage = Signal(str)

    def __init__(self, completer: Completer, known_names_fn, parent=None):
        super().__init__(parent)
        self.setObjectName("input")
        self.setFont(theme.mono_font())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setTabChangesFocus(False)
        self.document().setDocumentMargin(2)
        self.highlighter = Highlighter(self.document())
        self.completer = completer
        self.known_names_fn = known_names_fn
        self.diagnostics = []
        self._diag_selections: list = []
        self._bracket_selections: list = []

        self._lint_timer = QTimer(self, singleShot=True, interval=350)
        self._lint_timer.timeout.connect(self.run_diagnostics)
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.document().documentLayout().documentSizeChanged.connect(lambda *_: self._fit_height())
        self._fit_height()

    # ---------------------------------------------------------------- sizing

    def _fit_height(self) -> None:
        lines = max(1, int(self.document().size().height()))
        h = lines * self.fontMetrics().lineSpacing() + 2 * self.document().documentMargin() + 6
        self.setFixedHeight(int(h))

    def sizeHint(self) -> QSize:
        return QSize(400, self.height())

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._fit_height()

    def set_font_size(self, size: float) -> None:
        self.setFont(theme.mono_font(size))
        self._fit_height()

    # ----------------------------------------------------------------- keys

    def keyPressEvent(self, e) -> None:
        popup = self.completer.popup()
        key, mods = e.key(), e.modifiers()
        if popup.isVisible() and self.completer.widget() is self:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                index = popup.currentIndex()
                if not index.isValid():
                    index = self.completer.completionModel().index(0, 0)
                if index.isValid():
                    self._insert_completion(index)
                popup.hide()
                return
            if key == Qt.Key.Key_Escape:
                popup.hide()
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.textCursor().insertText("\n")
            else:
                self.executeRequested.emit()
            return
        if key == Qt.Key.Key_Space and mods & Qt.KeyboardModifier.ControlModifier:
            self.show_completions(force=True)
            return
        cur = self.textCursor()
        if key == Qt.Key.Key_Up and not mods and cur.blockNumber() == 0 \
                and cur.block().layout().lineForTextPosition(cur.positionInBlock()).lineNumber() == 0:
            self.navigate.emit(-1)
            return
        if key == Qt.Key.Key_Down and not mods and cur.blockNumber() == self.document().blockCount() - 1:
            layout = cur.block().layout()
            if layout.lineForTextPosition(cur.positionInBlock()).lineNumber() == layout.lineCount() - 1:
                self.navigate.emit(+1)
                return

        super().keyPressEvent(e)

        text = e.text()
        if text and (text.isalnum() or text == "_"):
            prefix = self._word_prefix()
            if len(prefix) >= 2 and not prefix[0].isdigit():
                self.show_completions()
            elif popup.isVisible():
                popup.hide()
        elif popup.isVisible() and key not in (Qt.Key.Key_Backspace, Qt.Key.Key_Up, Qt.Key.Key_Down):
            popup.hide()
        elif popup.isVisible() and key == Qt.Key.Key_Backspace:
            self.show_completions()

    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        self.completer.setWidget(self)
        signal = self.completer.activated[QModelIndex]
        try:
            signal.disconnect()
        except (RuntimeError, TypeError):
            pass
        signal.connect(self._insert_completion)  # mouse clicks in the popup
        self.focusReceived.emit()

    # ----------------------------------------------------------- completion

    def _word_prefix(self) -> str:
        cur = self.textCursor()
        text = cur.block().text()[:cur.positionInBlock()]
        i = len(text)
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
            i -= 1
        return text[i:]

    def show_completions(self, force: bool = False) -> None:
        self.completer.set_user_names(self.known_names_fn())
        prefix = self._word_prefix()
        if not prefix and not force:
            return
        self.completer.setCompletionPrefix(prefix)
        if self.completer.completionCount() == 0:
            self.completer.popup().hide()
            return
        popup = self.completer.popup()
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(360, popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 16))
        self.completer.complete(rect)
        try:
            popup.selectionModel().currentChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        popup.selectionModel().currentChanged.connect(
            lambda idx, _prev: self.statusMessage.emit(self.completer.doc_for(idx.data(NAME_ROLE) or "")))
        self.statusMessage.emit(self.completer.doc_for(prefix))

    def _insert_completion(self, index) -> None:
        name = index.data(NAME_ROLE)
        kind = index.data(KIND_ROLE)
        cur = self.textCursor()
        prefix = self._word_prefix()
        cur.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        entry = CATALOG.get(name)
        next_char = self.document().characterAt(self.textCursor().position())
        if kind == "function" and entry and entry.max_args != 0 and next_char != "(":
            cur.insertText(name + "()")
            cur.movePosition(QTextCursor.MoveOperation.Left)
        else:
            cur.insertText(name)
        self.setTextCursor(cur)
        if entry:
            self.statusMessage.emit(f"{entry.signature} — {entry.doc}")

    # ---------------------------------------------------------- diagnostics

    def _on_text_changed(self) -> None:
        self._lint_timer.start()

    def run_diagnostics(self) -> None:
        text = self.toPlainText()
        self.diagnostics = analyze(text, self.known_names_fn()).diagnostics if text.strip() else []
        sels = []
        for d in self.diagnostics:
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            if d.severity == ERROR:
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setUnderlineColor(theme.color(theme.ERROR))
            elif d.severity == WARNING:
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setUnderlineColor(theme.color(theme.WARNING))
            else:
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DotLine)
                fmt.setUnderlineColor(theme.color(theme.INFO))
            sel.format = fmt
            cur = QTextCursor(self.document())
            start = min(d.start, len(text))
            end = min(max(d.end, start + 1), len(text))
            if end <= start:  # empty span at the very end: underline the last character
                start = max(0, end - 1)
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sels.append(sel)
        self._diag_selections = sels
        self._apply_selections()
        self.diagnosticsChanged.emit(self.diagnostics)

    def diagnostic_at(self, pos: int):
        best = None
        for d in self.diagnostics:
            if d.start <= pos <= max(d.end, d.start + 1):
                if best is None or ["info", "warning", "error"].index(d.severity) > \
                        ["info", "warning", "error"].index(best.severity):
                    best = d
        return best

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            pos = self.cursorForPosition(e.pos()).position()
            d = self.diagnostic_at(pos)
            if d:
                text = f"<b>{d.severity.capitalize()}:</b> {_esc(d.message)}"
                if d.hint:
                    text += f"<br><i>{_esc(d.hint)}</i>"
                QToolTip.showText(e.globalPos(), text, self)
            else:
                word = self._word_at(pos)
                entry = CATALOG.get(word)
                if entry:
                    QToolTip.showText(e.globalPos(), f"<b>{_esc(entry.signature)}</b><br>{_esc(entry.doc)}", self)
                else:
                    QToolTip.hideText()
            return True
        return super().event(e)

    def _word_at(self, pos: int) -> str:
        text = self.toPlainText()
        i = j = pos
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
            i -= 1
        while j < len(text) and (text[j].isalnum() or text[j] == "_"):
            j += 1
        return text[i:j]

    # -------------------------------------------------------- bracket match

    def _on_cursor_moved(self) -> None:
        self._bracket_selections = self._match_brackets()
        self._apply_selections()
        d = self.diagnostic_at(self.textCursor().position())
        if d:
            self.statusMessage.emit(f"{d.severity}: {d.message}" + (f" — {d.hint}" if d.hint else ""))

    def _match_brackets(self) -> list:
        text = self.toPlainText()
        pos = self.textCursor().position()
        toks = [t for t in tokenize(text) if t.kind in OPENERS or t.kind in _CLOSERS]
        target = None
        for idx, t in enumerate(toks):
            if t.start == pos or t.end == pos:
                target = idx
                if t.start == pos:
                    break
        if target is None:
            return []
        t = toks[target]
        depth, match = 0, None
        if t.kind in OPENERS:
            for u in toks[target:]:
                depth += 1 if u.kind in OPENERS else -1
                if depth == 0:
                    match = u if u.kind is OPENERS[t.kind] else None
                    break
        else:
            for u in reversed(toks[:target + 1]):
                depth += 1 if u.kind in _CLOSERS else -1
                if depth == 0:
                    match = u if OPENERS.get(u.kind) is t.kind else None
                    break
        if match is None:
            return []
        sels = []
        for tok in (t, match):
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(theme.color(theme.SELECTION_BRACKET))
            sel.format = fmt
            cur = QTextCursor(self.document())
            cur.setPosition(tok.start)
            cur.setPosition(tok.end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sels.append(sel)
        return sels

    def _apply_selections(self) -> None:
        self.setExtraSelections(self._bracket_selections + self._diag_selections)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

