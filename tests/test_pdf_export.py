"""PDF export (run off-screen)."""
import os
import re
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from symple.engine.printing import Output  # noqa: E402
from symple.ui.main_window import MainWindow  # noqa: E402
from symple.ui.pdf_export import export_pdf  # noqa: E402


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


def wait_idle(sheet, timeout=60):
    t0 = time.time()
    while sheet.engine.running is not None or sheet.engine.queue:
        pump(50)
        assert time.time() - t0 < timeout, "engine did not finish"
    pump(50)


def page_count(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def test_export_worksheet(win, tmp_path):
    sheet = win.sheet
    sources = ["int(1/(1+x^2), x);",
               "Matrix([[1, 2], [3, 4]]);",
               "plot(sin(x), x = 0..2*Pi);",
               "sin(x, y);",
               "expand((a+b)^3) + " + " + ".join(f"c{i}*x^{i}" for i in range(60)) + ";"]
    cell = sheet.cells[0]
    for i, src in enumerate(sources):
        if i:
            cell = sheet.add_cell(after=cell)
        cell.set_source(src)
    sheet.execute_all()
    wait_idle(sheet)
    kinds = [o.kind for c in sheet.cells for o in c.outputs]
    assert {"math", "plot", "error"} <= set(kinds)

    path = tmp_path / "sheet.pdf"
    last_dir = win.settings.value("last_dir")
    try:
        assert win.export_pdf(str(tmp_path / "sheet"))
    finally:
        if last_dir is None:
            win.settings.remove("last_dir")
        else:
            win.settings.setValue("last_dir", last_dir)
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert page_count(data) >= 1


def test_long_content_paginates(app, tmp_path):
    long_line = "f := x -> " + " + ".join(f"a{i}*x^{i}" for i in range(400)) + ";"
    cells = [(f"x{i} := {i};", [Output(kind="math", text=str(i), latex=str(i))]) for i in range(40)]
    cells.append((long_line, [Output(kind="error", text="Error, something went wrong")]))
    cells.append(("tall := 1;", [Output(kind="text", text="\n".join(["line"] * 400), meta={"monospace": True})]))
    path = tmp_path / "long.pdf"
    pages = export_pdf(cells, path, title="long.syw")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert pages > 1
    assert page_count(data) == pages
