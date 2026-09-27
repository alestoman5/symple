"""Application entry point."""
from __future__ import annotations

import multiprocessing
import sys


def self_test(report_path: str) -> int:
    """Exercise the engine process, plotting and math rendering; used to check packaged builds."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from .engine.worker import EngineClient
    from .ui.math_view import render_latex

    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841
    lines, ok = [], True
    client = EngineClient()
    try:
        result = client.run("int(x^2, x = 0..1); plot(sin(x), x = 0..Pi);")
        texts = [(o.kind, o.text) for o in result.outputs]
        lines.append(f"engine: {texts}")
        ok &= texts[:1] == [("math", "1/3")] and result.outputs[1].png.startswith(b"\x89PNG")
    except Exception as e:  # report instead of crashing
        lines.append(f"engine error: {e!r}")
        ok = False
    finally:
        client.shutdown()
    pix = render_latex(r"\frac{x^{2}}{2}")
    lines.append(f"mathtext: {'ok' if pix is not None else 'failed'}")
    ok &= pix is not None
    lines.append("SELF-TEST " + ("PASSED" if ok else "FAILED"))
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


def main() -> int:
    multiprocessing.freeze_support()
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        return self_test(sys.argv[2])

    from PySide6.QtWidgets import QApplication

    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Symple")
    app.setOrganizationName("Symple")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)
    win = MainWindow()
    win.show()
    args = [a for a in sys.argv[1:] if a.endswith(".syw")]
    if args:
        win.open_file(args[0])
    return app.exec()
