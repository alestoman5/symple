"""Colors and fonts. A minimal, light look with an original palette."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

BACKGROUND = "#fbfbfa"
PAPER = "#ffffff"
RULE = "#ececea"
PROMPT = "#9a6b3f"
PROMPT_BUSY = "#d68910"
INPUT_TEXT = "#1f2328"
OUTPUT_TEXT = "#23395d"
ERROR = "#c0392b"
WARNING = "#b9770e"
INFO = "#7f8c8d"
SELECTION_BRACKET = "#dce8f7"

SYNTAX = {
    "keyword": ("#7d3c98", True, False),
    "builtin": ("#1f618d", False, False),
    "constant": ("#a04000", False, False),
    "number": ("#117a65", False, False),
    "string": ("#a93226", False, False),
    "comment": ("#808b96", False, True),
    "operator": ("#5d6d7e", False, False),
    "ditto": ("#a04000", True, False),
    "error": ("#c0392b", False, False),
}

_MONO_CANDIDATES = ["Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono",
                    "Menlo", "Liberation Mono", "Courier New"]


def mono_font(size: float = 11) -> QFont:
    families = set(QFontDatabase.families())
    for name in _MONO_CANDIDATES:
        if name in families:
            font = QFont(name)
            break
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSizeF(size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def color(hex_: str) -> QColor:
    return QColor(hex_)


STYLESHEET = f"""
QMainWindow, QScrollArea, #worksheet {{ background: {BACKGROUND}; }}
#page {{ background: {PAPER}; border-left: 1px solid {RULE}; border-right: 1px solid {RULE}; }}
QToolBar {{ background: {BACKGROUND}; border: none; border-bottom: 1px solid {RULE}; spacing: 4px; padding: 3px; }}
QToolButton {{ padding: 4px 8px; border-radius: 4px; color: #333; }}
QToolButton:hover {{ background: #efefec; }}
QToolButton:disabled {{ color: #bbb; }}
QStatusBar {{ background: {BACKGROUND}; border-top: 1px solid {RULE}; color: #555; }}
QPlainTextEdit#input {{ background: transparent; border: none; color: {INPUT_TEXT};
    selection-background-color: #cfe0f5; selection-color: {INPUT_TEXT}; }}
QLabel#prompt {{ color: {PROMPT}; font-weight: bold; }}
QLabel#error {{ color: {ERROR}; }}
QLabel#warning {{ color: {WARNING}; }}
QLabel#textout {{ color: {OUTPUT_TEXT}; }}
QFrame#cell[current="true"] {{ background: #f7f9fc; border-radius: 4px; }}
QListView#completer {{ border: 1px solid #d0d0d0; background: white; selection-background-color: #dce8f7;
    selection-color: black; padding: 2px; }}
"""
