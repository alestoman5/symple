"""The worksheet: a column of cells, and the bridge to the engine process."""
from __future__ import annotations

import threading
from collections import deque

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..engine.worker import EngineClient, RunResult
from .cell import Cell
from .completer import Completer

PAGE_MAX_WIDTH = 980


class EngineBridge(QObject):
    """Runs cells one at a time on a background thread and reports back via signals."""
    finished = Signal(object, object)       # (cell, RunResult)
    busyChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = EngineClient()
        self.queue: deque = deque()
        self.running = None
        self.names: list[str] = []
        threading.Thread(target=self.client.reset, daemon=True).start()  # start the engine early

    def submit(self, cell, code: str) -> None:
        self.queue.append((cell, code))
        if self.running is None:
            self._next()

    def _next(self) -> None:
        if not self.queue:
            self.running = None
            self.busyChanged.emit(False)
            return
        cell, code = self.queue.popleft()
        self.running = cell
        self.busyChanged.emit(True)

        def work():
            result = self.client.run(code)
            self.finished.emit(cell, result)
        threading.Thread(target=work, daemon=True).start()

    def on_finished(self, cell, result: RunResult) -> None:
        """Called on the GUI thread (queued connection)."""
        if result.interrupted or result.crashed:
            self.queue.clear()
            self.names = []
        else:
            self.names = result.names
        self._next()

    def interrupt(self) -> None:
        self.queue.clear()
        self.client.interrupt()

    def restart(self) -> None:
        self.queue.clear()
        if self.running is not None:
            self.client.interrupt()
        else:
            threading.Thread(target=self.client.reset, daemon=True).start()
        self.names = []

    def shutdown(self) -> None:
        self.client.shutdown()


class Worksheet(QScrollArea):
    statusMessage = Signal(str)
    busyChanged = Signal(bool)
    modifiedChanged = Signal(bool)
    diagnosticsSummary = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("worksheet")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.zoom = 1.0
        self.completer = Completer(self)
        self.cells: list[Cell] = []
        self.current: Cell | None = None
        self._modified = False

        outer = QWidget()
        outer.setObjectName("worksheet")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.page = QWidget()
        self.page.setObjectName("page")
        self.page.setMaximumWidth(PAGE_MAX_WIDTH)
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setContentsMargins(24, 18, 24, 18)
        self.page_layout.setSpacing(4)
        self.page_layout.addStretch(1)
        outer_layout.addWidget(self.page, 1, Qt.AlignmentFlag.AlignHCenter)
        self.page.setMinimumWidth(min(PAGE_MAX_WIDTH, 640))
        self.setWidget(outer)

        self.engine = EngineBridge(self)
        self.engine.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        self.engine.busyChanged.connect(self.busyChanged)

        self.add_cell()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.page.setMinimumWidth(min(PAGE_MAX_WIDTH, max(300, self.viewport().width() - 2)))

    # --------------------------------------------------------------- cells

    def known_names(self) -> list[str]:
        return self.engine.names

    def add_cell(self, after: Cell | None = None, before: Cell | None = None,
                 focus: bool = True, text: str = "") -> Cell:
        cell = Cell(self.completer, self.known_names, self.zoom)
        cell.executeRequested.connect(self.execute)
        cell.navigate.connect(self._navigate)
        cell.focused.connect(self._set_current)
        cell.editor.statusMessage.connect(self.statusMessage)
        cell.editor.diagnosticsChanged.connect(self._on_diagnostics)
        cell.editor.textChanged.connect(self._mark_modified)
        if text:
            cell.set_source(text)
        if not self.cells:
            cell.editor.setPlaceholderText("Type a command, e.g. int(x^2, x);   Enter runs · "
                                           "Shift+Enter new line · Ctrl+Space completes")
        if after is not None and after in self.cells:
            idx = self.cells.index(after) + 1
        elif before is not None and before in self.cells:
            idx = self.cells.index(before)
        else:
            idx = len(self.cells)
        self.cells.insert(idx, cell)
        self.page_layout.insertWidget(idx, cell)
        if focus:
            self.focus_cell(cell)
        return cell

    def remove_cell(self, cell: Cell | None = None) -> None:
        cell = cell or self.current
        if cell is None:
            return
        idx = self.cells.index(cell)
        self.cells.remove(cell)
        cell.setParent(None)
        cell.deleteLater()
        if not self.cells:
            self.add_cell()
        else:
            self.focus_cell(self.cells[min(idx, len(self.cells) - 1)])
        self._mark_modified()

    def focus_cell(self, cell: Cell, at_end: bool = True) -> None:
        cell.editor.setFocus()
        if at_end:
            cur = cell.editor.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cell.editor.setTextCursor(cur)
        self._set_current(cell)
        QTimer.singleShot(0, lambda: self.ensureWidgetVisible(cell, 0, 40))

    def _set_current(self, cell: Cell) -> None:
        if self.current is cell:
            return
        if self.current is not None and self.current in self.cells:
            self.current.set_current(False)
        self.current = cell
        cell.set_current(True)

    def _navigate(self, cell: Cell, direction: int) -> None:
        idx = self.cells.index(cell) + direction
        if 0 <= idx < len(self.cells):
            target = self.cells[idx]
            target.editor.setFocus()
            cur = target.editor.textCursor()
            cur.movePosition(cur.MoveOperation.End if direction < 0 else cur.MoveOperation.Start)
            target.editor.setTextCursor(cur)
            self.ensureWidgetVisible(target, 0, 40)

    def clear(self) -> None:
        for cell in list(self.cells):
            cell.setParent(None)
            cell.deleteLater()
        self.cells.clear()
        self.current = None
        self.add_cell()
        self.set_modified(False)

    # ----------------------------------------------------------- execution

    def execute(self, cell: Cell | None = None, advance: bool = True) -> None:
        cell = cell or self.current
        if cell is None:
            return
        code = cell.source
        if not code.strip():
            cell.set_outputs([])
        else:
            cell.set_busy(True)
            self.engine.submit(cell, code)
        if advance:
            idx = self.cells.index(cell)
            if idx == len(self.cells) - 1:
                self.add_cell(after=cell)
            else:
                self.focus_cell(self.cells[idx + 1])

    def execute_all(self) -> None:
        for cell in self.cells:
            if cell.source.strip():
                cell.set_busy(True)
                self.engine.submit(cell, cell.source)

    def _on_finished(self, cell: Cell, result: RunResult) -> None:
        self.engine.on_finished(cell, result)
        if result.interrupted or result.crashed:
            for c in self.cells:
                c.set_busy(False)
        if cell in self.cells:
            cell.set_busy(False)
            cell.set_outputs(result.outputs)
            if self.current is not None and self.current is not cell:
                QTimer.singleShot(0, lambda: self.ensureWidgetVisible(self.current.editor, 0, 60))
        self.completer.set_user_names(self.engine.names)
        if not (result.interrupted or result.crashed):
            self.statusMessage.emit(f"Evaluated in {result.elapsed:.2f} s")
        self._mark_modified()

    def interrupt(self) -> None:
        self.engine.interrupt()

    def restart(self) -> None:
        self.engine.restart()
        for c in self.cells:
            c.set_busy(False)
        self.statusMessage.emit("Session restarted: all variables cleared.")

    # ------------------------------------------------------------ misc

    def _on_diagnostics(self, diags) -> None:
        errors = sum(d.severity == "error" for d in diags)
        warnings = sum(d.severity == "warning" for d in diags)
        parts = []
        if errors:
            parts.append(f"{errors} error{'s' if errors > 1 else ''}")
        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings > 1 else ''}")
        self.diagnosticsSummary.emit(", ".join(parts))

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.6, min(2.5, zoom))
        for c in self.cells:
            c.set_zoom(self.zoom)

    def _mark_modified(self) -> None:
        self.set_modified(True)

    def set_modified(self, value: bool) -> None:
        if value != self._modified:
            self._modified = value
            self.modifiedChanged.emit(value)

    @property
    def modified(self) -> bool:
        return self._modified

    def to_dict(self) -> dict:
        return {"format": "symple-worksheet", "version": 1,
                "cells": [c.to_dict() for c in self.cells]}

    def load_dict(self, data: dict) -> None:
        if data.get("format") != "symple-worksheet":
            raise ValueError("not a Symple worksheet")
        for cell in list(self.cells):
            cell.setParent(None)
            cell.deleteLater()
        self.cells.clear()
        self.current = None
        for cd in data.get("cells", []):
            cell = self.add_cell(focus=False)
            cell.load_dict(cd)
        if not self.cells:
            self.add_cell()
        self.focus_cell(self.cells[0], at_end=True)
        self.set_modified(False)

    def shutdown(self) -> None:
        self.engine.shutdown()
