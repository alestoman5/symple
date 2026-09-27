"""A worksheet cell: '>' prompt, input editor, and the outputs below it."""
from __future__ import annotations

import base64

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..engine.printing import Output
from . import theme
from .editor import InputEditor
from .math_view import render_latex, render_parts


class OutputView(QScrollArea):
    """One output. Right-click to copy it as text or LaTeX.

    Plain text wraps to the page width; content that cannot wrap (typeset math,
    pretty-printed text, plots) scrolls horizontally when it is wider than the page,
    so it is never cut off. The view is always exactly as tall as its content."""

    def __init__(self, out: Output, zoom: float, parent=None):
        super().__init__(parent)
        self.out = out
        self.setObjectName("output")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.viewport().setAutoFillBackground(False)
        self.label = QLabel()
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label.customContextMenuRequested.connect(self._menu)
        self.setWidget(self.label)
        self.label.setAutoFillBackground(False)  # setWidget() turns it on; let the cell show through
        # Refits triggered by a resize are deferred: QAbstractScrollArea ignores nested resizes.
        self._fit_timer = QTimer(self, singleShot=True, interval=0)
        self._fit_timer.timeout.connect(self._fit)
        self.render(zoom)

    def render(self, zoom: float) -> None:
        out, label = self.out, self.label
        font = theme.mono_font(10.5 * zoom)
        if out.kind == "math":
            pix = None
            ratio = self.devicePixelRatioF()
            if out.meta.get("parts"):
                pix = render_parts(out.meta["parts"], 14.5 * zoom, theme.OUTPUT_TEXT, ratio)
            elif not out.meta.get("prefer_pretty") and out.latex:
                pix = render_latex(out.latex, 14.5 * zoom, theme.OUTPUT_TEXT, ratio)
            if pix is not None:
                label.setPixmap(pix)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setToolTip(out.text if len(out.text) < 500 else "")
            else:
                label.setObjectName("textout")
                label.setFont(font)
                label.setText(out.pretty or out.text)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif out.kind == "plot":
            pix = QPixmap()
            pix.loadFromData(out.png, "PNG")
            if zoom != 1.0:
                pix = pix.scaledToWidth(int(pix.width() * zoom), Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            label.setObjectName({"error": "error", "warning": "warning"}.get(out.kind, "textout"))
            label.setFont(font)
            label.setWordWrap(True)
            label.setText(out.text)
            centered = out.kind == "text" and not out.meta.get("monospace")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter if centered else Qt.AlignmentFlag.AlignLeft)
        label.style().unpolish(label)
        label.style().polish(label)
        self._fit()

    def _fit(self) -> None:
        """Size the label for the available width and this view for the label."""
        label = self.label
        avail = max(1, self.viewport().width())
        if label.wordWrap():
            w = max(avail, label.minimumSizeHint().width())   # a single unbreakable word may be wider
            h = label.heightForWidth(w)
        else:
            hint = label.sizeHint()
            w, h = max(avail, hint.width()), hint.height()
        label.resize(w, h)
        bar = self.horizontalScrollBar().sizeHint().height() if w > avail else 0
        if (self.minimumHeight(), self.maximumHeight()) != (h + bar, h + bar):
            self.setFixedHeight(h + bar)

    def content_width(self) -> int:
        """Natural width of the output (what would be needed to show it without scrolling)."""
        if self.label.wordWrap():
            return self.label.minimumSizeHint().width()
        return self.label.sizeHint().width()

    def sizeHint(self) -> QSize:
        return QSize(self.content_width(), self.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.height())

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._fit_timer.start()

    def wheelEvent(self, e) -> None:
        # Horizontal wheel/touchpad gestures scroll the output; vertical ones scroll the worksheet.
        if abs(e.angleDelta().x()) > abs(e.angleDelta().y()):
            super().wheelEvent(e)
        else:
            e.ignore()

    def _menu(self, pos) -> None:
        menu = QMenu(self)
        a = QAction("Copy as text", menu)
        a.triggered.connect(lambda: QGuiApplication.clipboard().setText(self.out.text))
        menu.addAction(a)
        if self.out.latex:
            b = QAction("Copy as LaTeX", menu)
            b.triggered.connect(lambda: QGuiApplication.clipboard().setText(self.out.latex))
            menu.addAction(b)
        if self.out.kind == "plot":
            c = QAction("Copy image", menu)
            c.triggered.connect(lambda: QGuiApplication.clipboard().setPixmap(self.label.pixmap()))
            menu.addAction(c)
        menu.exec(self.label.mapToGlobal(pos))


class Cell(QFrame):
    executeRequested = Signal(object)
    navigate = Signal(object, int)
    focused = Signal(object)

    def __init__(self, completer, known_names_fn, zoom: float = 1.0, parent=None):
        super().__init__(parent)
        self.setObjectName("cell")
        self.zoom = zoom
        self.outputs: list[Output] = []

        self.prompt = QLabel(">")
        self.prompt.setObjectName("prompt")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.prompt.setContentsMargins(0, 3, 0, 0)

        self.editor = InputEditor(completer, known_names_fn)
        self.editor.set_font_size(11 * zoom)
        self.editor.executeRequested.connect(lambda: self.executeRequested.emit(self))
        self.editor.navigate.connect(lambda d: self.navigate.emit(self, d))
        self.editor.focusReceived.connect(lambda: self.focused.emit(self))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self.prompt)
        top.addWidget(self.editor, 1)

        self.output_box = QWidget()
        self.output_layout = QVBoxLayout(self.output_box)
        self.output_layout.setSpacing(6)
        self.output_box.hide()
        self._set_prompt_font()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        layout.addLayout(top)
        layout.addWidget(self.output_box)

    # ------------------------------------------------------------------ state

    @property
    def source(self) -> str:
        return self.editor.toPlainText()

    def set_source(self, text: str) -> None:
        self.editor.setPlainText(text)

    def set_current(self, current: bool) -> None:
        self.setProperty("current", "true" if current else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_busy(self, busy: bool) -> None:
        self.prompt.setText("*" if busy else ">")
        self.prompt.setStyleSheet(f"color: {theme.PROMPT_BUSY};" if busy else "")

    def set_outputs(self, outputs: list[Output]) -> None:
        self.outputs = list(outputs)
        while self.output_layout.count():
            w = self.output_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for out in self.outputs:
            self.output_layout.addWidget(OutputView(out, self.zoom))
        self.output_box.setVisible(bool(self.outputs))

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        self._set_prompt_font()
        self.editor.set_font_size(11 * zoom)
        self.set_outputs(self.outputs)

    def _set_prompt_font(self) -> None:
        """Scale the prompt column with the zoom so '>' / '*' are never clipped,
        and keep the outputs aligned with the input."""
        self.prompt.setFont(theme.mono_font(11 * self.zoom))
        fm = self.prompt.fontMetrics()
        width = max(22, max(fm.horizontalAdvance(c) for c in ">*") + 8)
        self.prompt.setFixedWidth(width)
        self.output_layout.setContentsMargins(width + 6, 2, 8, 4)

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> dict:
        outs = []
        for o in self.outputs:
            d = {"kind": o.kind, "text": o.text, "latex": o.latex, "pretty": o.pretty,
                 "label": o.label, "meta": o.meta}
            if o.png:
                d["png"] = base64.b64encode(o.png).decode("ascii")
            outs.append(d)
        return {"input": self.source, "outputs": outs}

    def load_dict(self, data: dict) -> None:
        self.set_source(str(data.get("input", "")))
        outs = []
        for d in data.get("outputs", []):
            if not isinstance(d, dict):
                continue
            png = base64.b64decode(d["png"]) if isinstance(d.get("png"), str) else b""
            outs.append(Output(kind=str(d.get("kind", "text")), text=str(d.get("text", "")),
                               latex=str(d.get("latex", "")), pretty=str(d.get("pretty", "")),
                               png=png, label=str(d.get("label", "")),
                               meta=d.get("meta") if isinstance(d.get("meta"), dict) else {}))
        self.set_outputs(outs)
