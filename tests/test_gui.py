"""GUI tests driven with real key events (run off-screen)."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QRect, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from symple.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    w = MainWindow()
    w.show()
    yield w
    w.sheet.set_modified(False)
    w.close()


def pump(ms=50):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_idle(sheet, timeout=30):
    t0 = time.time()
    while sheet.engine.running is not None or sheet.engine.queue:
        pump(50)
        assert time.time() - t0 < timeout, "engine did not finish"
    pump(50)


def test_completion_popup_and_insert(win):
    ed = win.sheet.cells[0].editor
    ed.setFocus()
    pump()
    QTest.keyClicks(ed, "Deter")
    pump()
    popup = ed.completer.popup()
    assert popup.isVisible()
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "Determinant()"
    assert ed.textCursor().position() == len("Determinant(")  # cursor inside the parentheses


def test_shift_enter_adds_line_and_enter_runs(win):
    sheet = win.sheet
    ed = sheet.cells[0].editor
    ed.setFocus()
    QTest.keyClicks(ed, "a := 2:")
    QTest.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClicks(ed, "a^10;")
    assert ed.toPlainText() == "a := 2:\na^10;"
    QTest.keyClick(ed, Qt.Key.Key_Return)
    wait_idle(sheet)
    assert [o.text for o in sheet.cells[0].outputs] == ["1024"]
    assert len(sheet.cells) == 2 and sheet.current is sheet.cells[1]
    assert "a" in sheet.known_names()


def test_live_diagnostics(win):
    ed = win.sheet.cells[0].editor
    ed.setPlainText("diff(sin(x), x")
    ed.run_diagnostics()
    assert [d.message for d in ed.diagnostics] == ["unclosed '('"]
    assert len(ed.extraSelections()) >= 1


def test_interrupt(win):
    sheet = win.sheet
    cell = sheet.cells[0]
    cell.set_source("while true do od;")
    sheet.execute(cell)
    pump(800)
    assert sheet.engine.running is cell
    win.act_stop.trigger()
    wait_idle(sheet)
    assert "interrupted" in cell.outputs[0].text


def test_save_and_load_roundtrip(win, tmp_path):
    sheet = win.sheet
    cell = sheet.cells[0]
    cell.set_source("int(x, x);")
    sheet.execute(cell)
    wait_idle(sheet)
    data = sheet.to_dict()
    sheet.load_dict(data)
    assert sheet.cells[0].source == "int(x, x);"
    assert sheet.cells[0].outputs[0].text == "x^2/2"


# ------------------------------------------------------------ nothing clipped

def _lines_height(ed):
    """Pixel height the editor's text needs, laid out at the editor's current width."""
    doc = ed.document()
    block, total = doc.begin(), 0.0
    while block.isValid():
        total += doc.documentLayout().blockBoundingRect(block).height()
        block = block.next()
    return total


def test_placeholder_fits_narrow_window(win):
    win.resize(500, 600)
    pump(200)
    ed = win.sheet.cells[0].editor
    assert ed.toPlainText() == "" and ed.placeholderText()
    margin = int(ed.document().documentMargin())
    rect = ed.fontMetrics().boundingRect(QRect(0, 0, ed.viewport().width() - margin, 100000),
                                         int(Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                                         ed.placeholderText())
    assert rect.height() > ed.fontMetrics().lineSpacing()      # it does wrap at this width
    assert ed.viewport().height() >= rect.height() + margin     # ...and every line is visible


def test_long_input_line_gets_tall_editor(win):
    win.resize(600, 600)
    pump(200)
    cell = win.sheet.cells[0]
    cell.set_source("f := (a, b, c) -> " + " + ".join(f"a*sin(b)^{k} + c*cos(a)^{k}" for k in range(1, 12)) + ";")
    for zoom in (1.0, 1.8):
        win.sheet.set_zoom(zoom)
        pump(200)
        ed = cell.editor
        lines = ed.document().begin().layout().lineCount()
        assert lines >= 3
        assert ed.viewport().height() >= _lines_height(ed) + 2 * ed.document().documentMargin()
    win.sheet.set_zoom(1.0)


def test_wide_output_scrolls_instead_of_clipping(win):
    from symple.engine.printing import Output
    win.resize(600, 700)
    pump(100)
    cell = win.sheet.cells[0]
    latex = " + ".join(f"x_{{{i}}}^{{{i}}}" for i in range(60))
    cell.set_outputs([Output(kind="math", text="wide", latex=latex),
                      Output(kind="text", text="word " * 400)])
    pump(200)
    wide, text = cell.output_layout.itemAt(0).widget(), cell.output_layout.itemAt(1).widget()
    # The wide formula stays inside the cell, and all of it can be scrolled into view.
    assert wide.geometry().right() <= cell.contentsRect().right()
    assert wide.content_width() > wide.viewport().width()
    assert wide.label.width() >= wide.content_width()
    bar = wide.horizontalScrollBar()
    assert bar.maximum() >= wide.content_width() - wide.viewport().width()
    assert wide.viewport().height() >= wide.label.height()
    # Long plain text wraps onto as many lines as it needs, with no scrolling.
    assert text.horizontalScrollBar().maximum() == 0
    assert text.label.height() > 3 * text.label.fontMetrics().lineSpacing()
    assert text.viewport().height() >= text.label.heightForWidth(text.viewport().width())
