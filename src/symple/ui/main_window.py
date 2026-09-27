"""Main window: toolbar, menus, file handling and help."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QLabel, QMainWindow,
                               QMessageBox, QTextBrowser, QVBoxLayout)

from .. import __version__
from ..catalog import CATALOG
from . import theme
from .worksheet import Worksheet

FILE_FILTER = "Symple worksheets (*.syw);;All files (*)"


def app_icon() -> QIcon:
    """A simple original icon drawn in code (no image assets needed)."""
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#23395d"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        p.setPen(QColor("#f4d58d"))
        font = QFont("Cambria Math")
        font.setPixelSize(int(size * 0.72))
        font.setItalic(True)
        p.setFont(font)
        p.drawText(QRectF(0, -size * 0.04, size, size), Qt.AlignmentFlag.AlignCenter, "∫")
        p.setBrush(QColor("#f4d58d"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(size * 0.78, size * 0.78), size * 0.07, size * 0.07)
        p.end()
        icon.addPixmap(pix)
    return icon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.path: Path | None = None
        self.settings = QSettings("Symple", "Symple")
        self.sheet = Worksheet(self)
        self.setCentralWidget(self.sheet)
        self.setWindowIcon(app_icon())
        self.resize(1080, 780)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()

        self.diag_label = QLabel("")
        self.diag_label.setStyleSheet(f"color: {theme.ERROR}; padding-right: 8px;")
        self.engine_label = QLabel("Ready")
        self.engine_label.setStyleSheet("padding-right: 8px;")
        self.statusBar().addPermanentWidget(self.diag_label)
        self.statusBar().addPermanentWidget(self.engine_label)

        self.sheet.statusMessage.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.sheet.busyChanged.connect(self._on_busy)
        self.sheet.modifiedChanged.connect(lambda _: self._update_title())
        self.sheet.diagnosticsSummary.connect(self.diag_label.setText)
        self.sheet.set_zoom(float(self.settings.value("zoom", 1.0)))
        self._update_title()

    # -------------------------------------------------------------- actions

    def _action(self, text, slot, shortcut=None, tip=None) -> QAction:
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if tip:
            a.setStatusTip(tip)
            a.setToolTip(f"{tip} ({QKeySequence(shortcut).toString()})" if shortcut else tip)
        return a

    def _build_actions(self) -> None:
        self.act_new = self._action("New", self.new_file, QKeySequence.StandardKey.New, "New worksheet")
        self.act_open = self._action("Open…", self.open_file, QKeySequence.StandardKey.Open, "Open a worksheet")
        self.act_save = self._action("Save", self.save_file, QKeySequence.StandardKey.Save, "Save the worksheet")
        self.act_save_as = self._action("Save As…", self.save_file_as, "Ctrl+Shift+S")
        self.act_quit = self._action("Quit", self.close, QKeySequence.StandardKey.Quit)
        self.act_run = self._action("Run", lambda: self.sheet.execute(), None, "Run the current cell (Enter)")
        self.act_run_all = self._action("Run all", self.sheet.execute_all, "Ctrl+Shift+Return",
                                        "Run every cell from the top")
        self.act_stop = self._action("Interrupt", self.sheet.interrupt, "Ctrl+Break",
                                     "Stop the running computation (clears the session)")
        self.act_stop.setEnabled(False)
        self.act_restart = self._action("Restart", self.sheet.restart, "Ctrl+Shift+R",
                                        "Clear all variables (like restart;)")
        self.act_insert_above = self._action("Insert cell above", self._insert_above, "Ctrl+K")
        self.act_insert_below = self._action("Insert cell below", self._insert_below, "Ctrl+J")
        self.act_delete = self._action("Delete cell", lambda: self.sheet.remove_cell(), "Ctrl+Shift+D")
        self.act_clear_out = self._action("Clear all output", self._clear_outputs)
        self.act_zoom_in = self._action("Zoom in", lambda: self._zoom(1.1), QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_out = self._action("Zoom out", lambda: self._zoom(1 / 1.1), QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_reset = self._action("Actual size", lambda: self._zoom(None), "Ctrl+0")
        self.act_reference = self._action("Function reference", self.show_reference, "F1")
        self.act_about = self._action("About Symple", self.show_about)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.act_new, self.act_open, self.act_save, self.act_save_as):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_quit)
        m = mb.addMenu("&Edit")
        for a in (self.act_insert_above, self.act_insert_below, self.act_delete):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_clear_out)
        m = mb.addMenu("&Evaluate")
        for a in (self.act_run, self.act_run_all, self.act_stop, self.act_restart):
            m.addAction(a)
        m = mb.addMenu("&View")
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset):
            m.addAction(a)
        m = mb.addMenu("&Help")
        m.addAction(self.act_reference)
        m.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for a in (self.act_new, self.act_open, self.act_save):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_run, self.act_run_all, self.act_stop, self.act_restart):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.act_reference)

    # ------------------------------------------------------------ handlers

    def _on_busy(self, busy: bool) -> None:
        self.act_stop.setEnabled(busy)
        self.engine_label.setText("Evaluating…" if busy else "Ready")
        self.engine_label.setStyleSheet(f"padding-right: 8px; color: {theme.PROMPT_BUSY if busy else '#555'};")

    def _insert_above(self) -> None:
        self.sheet.add_cell(before=self.sheet.current)

    def _insert_below(self) -> None:
        self.sheet.add_cell(after=self.sheet.current)

    def _clear_outputs(self) -> None:
        for c in self.sheet.cells:
            c.set_outputs([])

    def _zoom(self, factor) -> None:
        zoom = 1.0 if factor is None else self.sheet.zoom * factor
        self.sheet.set_zoom(zoom)
        self.settings.setValue("zoom", self.sheet.zoom)

    def _update_title(self) -> None:
        name = self.path.name if self.path else "Untitled"
        star = "*" if self.sheet.modified else ""
        self.setWindowTitle(f"{name}{star} — Symple")

    # ---------------------------------------------------------------- files

    def _confirm_discard(self) -> bool:
        if not self.sheet.modified:
            return True
        r = QMessageBox.question(self, "Symple", "Save changes to the worksheet?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_file()
        return r == QMessageBox.StandardButton.Discard

    def new_file(self) -> None:
        if self._confirm_discard():
            self.sheet.clear()
            self.sheet.restart()
            self.path = None
            self._update_title()

    def open_file(self, path: str | None = None) -> None:
        if not self._confirm_discard():
            return
        if not path:
            start = self.settings.value("last_dir", str(Path.home()))
            path, _ = QFileDialog.getOpenFileName(self, "Open worksheet", start, FILE_FILTER)
            if not path:
                return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.sheet.load_dict(data)
        except (OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(self, "Symple", f"Could not open {path}:\n{e}")
            return
        self.sheet.restart()
        self.path = Path(path)
        self.settings.setValue("last_dir", str(self.path.parent))
        self._update_title()
        self.statusBar().showMessage("Worksheet opened. Use 'Run all' to recompute it.", 8000)

    def save_file(self) -> bool:
        if self.path is None:
            return self.save_file_as()
        try:
            self.path.write_text(json.dumps(self.sheet.to_dict(), indent=1), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Symple", f"Could not save:\n{e}")
            return False
        self.sheet.set_modified(False)
        self.statusBar().showMessage(f"Saved {self.path.name}", 4000)
        return True

    def save_file_as(self) -> bool:
        start = str(self.path) if self.path else str(Path(self.settings.value("last_dir", str(Path.home()))) / "worksheet.syw")
        path, _ = QFileDialog.getSaveFileName(self, "Save worksheet", start, FILE_FILTER)
        if not path:
            return False
        if not path.endswith(".syw"):
            path += ".syw"
        self.path = Path(path)
        self.settings.setValue("last_dir", str(self.path.parent))
        ok = self.save_file()
        self._update_title()
        return ok

    def closeEvent(self, e) -> None:
        if self._confirm_discard():
            self.sheet.shutdown()
            e.accept()
        else:
            e.ignore()

    # ----------------------------------------------------------------- help

    def show_reference(self) -> None:
        by_cat: dict[str, list] = {}
        for entry in CATALOG.values():
            by_cat.setdefault(entry.category, []).append(entry)
        html = ["<h2>Symple reference</h2>",
                "<p><b>Syntax:</b> <code>:=</code> assigns, <code>x -&gt; expr</code> defines a function, "
                "<code>a..b</code> is a range, <code>;</code> shows the result and <code>:</code> hides it, "
                "<code>%</code> is the previous result (<code>%%</code>, <code>%%%</code> go further back), "
                "<code>#</code> starts a comment, <code>'x'</code> delays evaluation "
                "(<code>x := 'x'</code> clears x).</p>",
                "<p><b>Control flow:</b> <code>if c then … elif c then … else … end if</code>, "
                "<code>for i from 1 to n by 1 do … end do</code>, <code>for e in L do … end do</code>, "
                "<code>while c do … end do</code>, <code>proc(x) local y; … end proc</code>.</p>",
                "<p><b>Keys:</b> Enter runs a cell, Shift+Enter adds a line, Ctrl+Space completes, "
                "Up/Down move between cells, Ctrl+J / Ctrl+K insert a cell below / above.</p>"]
        for cat, entries in by_cat.items():
            html.append(f"<h3>{cat}</h3><table cellspacing='4'>")
            for e in entries:
                html.append(f"<tr><td><code>{_esc(e.signature)}</code></td><td>{_esc(e.doc)}</td></tr>")
            html.append("</table>")
        dlg = QDialog(self)
        dlg.setWindowTitle("Symple reference")
        dlg.resize(760, 640)
        view = QTextBrowser()
        view.setHtml("".join(html))
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addWidget(view)
        lay.addWidget(box)
        dlg.exec()

    def show_about(self) -> None:
        QMessageBox.about(
            self, "About Symple",
            f"<h3>Symple {__version__}</h3>"
            "<p>A worksheet-style front-end for SymPy with a Maple-inspired input language.</p>"
            "<p>Released under the MIT License. Built with SymPy (BSD), PySide6/Qt (LGPLv3) "
            "and Matplotlib.</p>"
            "<p><small>Symple is an independent project and is not affiliated with, sponsored by, "
            "or endorsed by Waterloo Maple Inc. (Maplesoft). Maple is a trademark of "
            "Waterloo Maple Inc.</small></p>")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
