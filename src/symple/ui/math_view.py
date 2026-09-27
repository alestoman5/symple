"""Typeset LaTeX with Matplotlib's built-in mathtext engine (no TeX install needed).

Mathtext has no matrix environment, so matrices arrive as separate "parts" and
are laid out here as a grid of individually rendered entries.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache

import matplotlib
from matplotlib.mathtext import math_to_image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap

matplotlib.rcParams["mathtext.fontset"] = "cm"

MAX_LATEX = 4000   # longer expressions are shown as text
_TALL = re.compile(r"\\(frac|int|sum|prod|binom|sqrt\[|lim)")


def adapt_for_mathtext(latex: str) -> str:
    """Small rewrites that make SymPy's LaTeX look right in mathtext."""
    latex = latex.replace(":=", r"\coloneq ")
    return _flatten_small_delims(latex)


def _flatten_small_delims(s: str) -> str:
    r"""Replace \left( ... \right) by plain parentheses when the content is not tall.

    Mathtext draws \left( \right) around short content noticeably smaller than
    ordinary parentheses, which makes sin(x) look cramped.
    """
    out, stack = [], []   # stack of (index in out, delimiter)
    i = 0
    while i < len(s):
        if s.startswith(r"\left", i) and i + 5 < len(s) and s[i + 5] in "([|":
            stack.append((len(out), s[i + 5]))
            out.append(s[i:i + 6])
            i += 6
            continue
        if s.startswith(r"\right", i) and i + 6 < len(s) and s[i + 6] in ")]|" and stack:
            start, delim = stack.pop()
            inner = "".join(out[start + 1:])
            closing = s[i:i + 7]
            if not _TALL.search(inner) and delim != "|":
                out[start] = delim
                closing = s[i + 6]
            out.append(closing)
            i += 7
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


@lru_cache(maxsize=1024)
def _render_png(latex: str, fontsize: float, color: str, dpi: int) -> bytes | None:
    if not latex or len(latex) > MAX_LATEX:
        return None
    prop = matplotlib.font_manager.FontProperties(size=fontsize)
    buf = io.BytesIO()
    try:
        math_to_image(f"${adapt_for_mathtext(latex)}$", buf, prop=prop, dpi=dpi, format="png", color=color)
    except Exception:
        return None
    return buf.getvalue()


def _image(latex: str, fontsize: float, color: str, ratio: float) -> QImage | None:
    png = _render_png(latex, fontsize, color, int(round(100 * ratio)))
    if png is None:
        return None
    img = QImage()
    if not img.loadFromData(png, "PNG"):
        return None
    return img


def render_latex(latex: str, fontsize: float = 14, color: str = "#23395d",
                 device_ratio: float = 1.0) -> QPixmap | None:
    """Return a pixmap of *latex*, or None if mathtext cannot typeset it."""
    ratio = max(1.0, device_ratio)
    img = _image(latex, fontsize, color, ratio)
    if img is None:
        return None
    pix = QPixmap.fromImage(img)
    pix.setDevicePixelRatio(ratio)
    return pix


def render_parts(parts: list[dict], fontsize: float = 14, color: str = "#23395d",
                 device_ratio: float = 1.0) -> QPixmap | None:
    """Render a row of parts: {"latex": ...} pieces and {"matrix": [[latex]]} grids."""
    ratio = max(1.0, device_ratio)
    images = []   # (image, is_separator)
    for part in parts:
        if "matrix" in part:
            img = _matrix_image(part["matrix"], fontsize, color, ratio)
        elif "cases" in part:
            img = _matrix_image(part["cases"], fontsize, color, ratio, cases=True)
        elif part["latex"].strip():
            img = _image(part["latex"], fontsize, color, ratio)
        else:
            continue
        if img is None:
            return None
        images.append((img, bool(part.get("sep"))))
    if not images:
        return None
    gap = int(5 * ratio)
    drop = int(fontsize * 0.3 * ratio)          # separators sit on the text baseline
    width = sum(i.width() for i, _ in images) + gap * (len(images) - 1)
    height = max(i.height() for i, _ in images) + drop
    canvas = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    x = 0
    for img, sep in images:
        y = (height - img.height()) // 2 + (drop // 2 if sep else 0)
        p.drawImage(x, y, img)
        x += img.width() + gap
    p.end()
    pix = QPixmap.fromImage(canvas)
    pix.setDevicePixelRatio(ratio)
    return pix


def _matrix_image(rows: list[list[str]], fontsize: float, color: str, ratio: float,
                  cases: bool = False) -> QImage | None:
    cells = [[_image(tex, fontsize, color, ratio) for tex in row] for row in rows]
    if any(c is None for row in cells for c in row):
        return None
    ncols = max((len(r) for r in rows), default=0)
    if not rows or ncols == 0:
        return None
    col_w = [max(row[j].width() for row in cells if j < len(row)) for j in range(ncols)]
    row_h = [max(c.height() for c in row) for row in cells]
    pad_x, pad_y, bracket = int((24 if cases else 14) * ratio), int(5 * ratio), int(6 * ratio)
    width = sum(col_w) + pad_x * (ncols - 1) + 2 * (bracket + int(6 * ratio))
    height = sum(row_h) + pad_y * (len(rows) - 1) + int(8 * ratio)
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    y = int(4 * ratio)
    for i, row in enumerate(cells):
        x = bracket + int(6 * ratio)
        for j, c in enumerate(row):
            dx = 0 if cases else (col_w[j] - c.width()) // 2
            p.drawImage(x + dx, y + (row_h[i] - c.height()) // 2, c)
            x += col_w[j] + pad_x
        y += row_h[i] + pad_y
    pen = QPen(QColor(color))
    pen.setWidthF(1.3 * ratio)
    p.setPen(pen)
    top, bottom, lw = 1.0 * ratio, height - 1.0 * ratio, 1.0 * ratio
    if cases:
        _draw_brace(p, bracket + 2 * ratio, top, bottom, bracket)
        p.end()
        return img
    for x0, sign in ((lw + 1, 1), (width - lw - 1, -1)):
        p.drawLine(QPointF(x0, top), QPointF(x0, bottom))
        p.drawLine(QPointF(x0, top), QPointF(x0 + sign * bracket, top))
        p.drawLine(QPointF(x0, bottom), QPointF(x0 + sign * bracket, bottom))
    p.end()
    return img


def _draw_brace(p: QPainter, x: float, top: float, bottom: float, w: float) -> None:
    """A left curly brace spanning top..bottom with its tip pointing left at x - w."""
    mid = (top + bottom) / 2
    path = QPainterPath(QPointF(x, top))
    path.cubicTo(QPointF(x - w * 0.6, top), QPointF(x - w * 0.4, mid), QPointF(x - w, mid))
    path.cubicTo(QPointF(x - w * 0.4, mid), QPointF(x - w * 0.6, bottom), QPointF(x, bottom))
    p.drawPath(path)
