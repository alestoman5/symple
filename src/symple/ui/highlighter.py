"""Syntax highlighting driven by the same lexer the parser uses."""
from __future__ import annotations

from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat

from ..catalog import CATALOG
from ..lang.lexer import tokenize
from ..lang.tokens import T
from . import theme


def _fmt(color: str, bold: bool, italic: bool) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(theme.color(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    f.setFontItalic(italic)
    return f


class Highlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.formats = {k: _fmt(*v) for k, v in theme.SYNTAX.items()}

    def category(self, tok) -> str | None:
        kind = tok.kind
        if tok.error:
            return "error" if kind is T.ERROR else "string" if kind is T.STRING else "error"
        if kind is T.KEYWORD:
            return "keyword"
        if kind is T.NAME:
            entry = CATALOG.get(tok.text)
            if entry is None:
                return None
            return "constant" if entry.kind == "constant" else "builtin"
        if kind is T.NUMBER:
            return "number"
        if kind is T.STRING:
            return "string"
        if kind is T.COMMENT:
            return "comment"
        if kind is T.DITTO:
            return "ditto"
        if kind is T.OP:
            return "operator"
        return None

    def highlightBlock(self, text: str) -> None:
        for tok in tokenize(text, keep_comments=True):
            if tok.kind is T.EOF:
                break
            cat = self.category(tok)
            if cat:
                self.setFormat(tok.start, tok.end - tok.start, self.formats[cat])
