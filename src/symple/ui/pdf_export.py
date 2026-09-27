"""Export a worksheet to PDF with QPdfWriter (no print-support module needed)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPageLayout, QPageSize,
                           QPainter, QPdfWriter, QPen, QPixmap, QTextCharFormat, QTextLayout, QTextOption)

from ..engine.printing import Output
from ..lang.lexer import tokenize
from ..lang.tokens import T
from . import theme
from .highlighter import Highlighter
from .math_view import render_latex, render_parts

RESOLUTION = 600          # device units per inch
MARGIN_MM = 18.0
MATH_RATIO = 4.0          # math is rasterised at 400 dpi
MATH_SIZE = 12.5          # pt
INPUT_SIZE = 9.5          # pt
TEXT_SIZE = 9.0           # pt
MIN_MATH_SCALE = 0.6      # wider math falls back to wrapped text
PLOT_DPI = 110            # dpi the engine renders plots at
FOOTER_SIZE = 7.5         # pt
FOOTER_COLOR = "#8a8f95"

PDF_MONO = ["Consolas", "DejaVu Sans Mono", "Menlo", "Liberation Mono", "Courier New"]

Draw = Callable[[QPainter, float, float, float], None]


@dataclass
class _Block:
    """A piece of content that is never split across pages."""
    height: float
    draw: Draw                  # draw(painter, x, y, scale)
    width: float = 0.0          # natural width (0 = uses the full column)
    indent: float = 0.0
    centered: bool = False
    space_before: float = 0.0
    keep_with_next: bool = False


def _pt(value: float) -> float:
    return value * RESOLUTION / 72.0


def _pdf_mono(size: float) -> QFont:
    """Like theme.mono_font, but avoids variable fonts, which Qt embeds at the wrong weight."""
    families = set(QFontDatabase.families())
    for name in PDF_MONO:
        if name in families:
            font = QFont(name)
            font.setPointSizeF(size)
            font.setStyleHint(QFont.StyleHint.Monospace)
            return font
    return theme.mono_font(size)


def _category(tok) -> str | None:
    return Highlighter.category(None, tok)


def _source_formats(text: str) -> list[QTextLayout.FormatRange]:
    ranges = []
    try:
        tokens = tokenize(text, keep_comments=True)
    except Exception:
        return ranges
    for tok in tokens:
        if tok.kind is T.EOF:
            break
        cat = _category(tok)
        if not cat:
            continue
        color, bold, italic = theme.SYNTAX[cat]
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontItalic(italic)
        r = QTextLayout.FormatRange()
        r.start, r.length, r.format = tok.start, tok.end - tok.start, fmt
        ranges.append(r)
    return ranges


def _text_layout(text: str, font: QFont, device, width: float | None, color: str,
                 align=Qt.AlignmentFlag.AlignLeft,
                 formats: list[QTextLayout.FormatRange] | None = None) -> tuple[QTextLayout, float, float]:
    """Lay out *text* (wrapped to *width*, or unwrapped if None); return (layout, width, height)."""
    layout = QTextLayout(text.replace("\n", "\u2028"), font, device)
    opt = QTextOption(align)
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if width
                    else QTextOption.WrapMode.NoWrap)
    layout.setTextOption(opt)
    base = QTextCharFormat()
    base.setForeground(QColor(color))
    whole = QTextLayout.FormatRange()
    whole.start, whole.length, whole.format = 0, len(text), base
    layout.setFormats([whole] + list(formats or []))
    leading = QFontMetricsF(font, device).leading()
    y, natural = 0.0, 0.0
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width if width else 1e9)
        line.setPosition(QPointF(0, y))
        y += line.height() + max(0.0, leading)
        natural = max(natural, line.naturalTextWidth())
    layout.endLayout()
    return layout, (width or natural), y


def _layout_block(layout: QTextLayout, width: float, height: float, **kw) -> _Block:
    def draw(p: QPainter, x: float, y: float, s: float) -> None:
        p.save()
        p.translate(x, y)
        p.scale(s, s)
        layout.draw(p, QPointF(0, 0))
        p.restore()
    return _Block(height, draw, width, **kw)


def _on_white(pix: QPixmap) -> QImage:
    """Flatten transparency: soft-masked images show seams in some PDF viewers."""
    img = QImage(pix.width(), pix.height(), QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    src = pix.toImage()
    src.setDevicePixelRatio(1.0)
    p = QPainter(img)
    p.drawImage(0, 0, src)
    p.end()
    return img


def _pixmap_block(pix: QPixmap, width: float, height: float, **kw) -> _Block:
    img = _on_white(pix)

    def draw(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawImage(QRectF(x, y, width * s, height * s), img, QRectF(img.rect()))
    return _Block(height, draw, width, centered=True, **kw)


def _cells_of(source) -> list[tuple[str, list[Output]]]:
    cells = getattr(source, "cells", source)
    result = []
    for c in cells:
        if isinstance(c, tuple):
            text, outs = c
        else:
            text, outs = c.source, c.outputs
        if text.strip() or outs:
            result.append((text, list(outs)))
    return result


class _Builder:
    def __init__(self, device: QPdfWriter, column: float):
        self.device = device
        self.column = column
        self.prompt_w = _pt(16)
        self.out_indent = _pt(20)
        self.mono = _pdf_mono(INPUT_SIZE)
        self.text_font = _pdf_mono(TEXT_SIZE)

    def title(self, text: str) -> list[_Block]:
        font = QFont(self.mono)
        font.setFamily(QFont().defaultFamily())
        font.setPointSizeF(15)
        font.setWeight(QFont.Weight.DemiBold)
        layout, w, h = _text_layout(text, font, self.device, self.column, theme.INPUT_TEXT)
        rule_gap = _pt(6)
        column = self.column

        def draw(p: QPainter, x: float, y: float, s: float) -> None:
            layout.draw(p, QPointF(x, y))
            pen = QPen(QColor("#d9d9d6"))
            pen.setWidthF(_pt(0.6))
            p.setPen(pen)
            p.drawLine(QPointF(x, y + h + rule_gap), QPointF(x + column, y + h + rule_gap))
        return [_Block(h + rule_gap + _pt(2), draw, column)]

    def cell(self, text: str, outputs: list[Output]) -> list[_Block]:
        blocks = []
        if text.strip():
            blocks.append(self.input_block(text, keep=bool(outputs)))
        for i, out in enumerate(outputs):
            b = self.output_block(out)
            if b is not None:
                b.space_before = _pt(6) if i or not blocks else _pt(4)
                blocks.append(b)
        if blocks:
            blocks[0].space_before = _pt(12)
        return blocks

    def input_block(self, text: str, keep: bool) -> _Block:
        width = self.column - self.prompt_w
        layout, _, h = _text_layout(text, self.mono, self.device, width, theme.INPUT_TEXT,
                                    formats=_source_formats(text))
        prompt_font = QFont(self.mono)
        prompt_font.setWeight(QFont.Weight.Bold)
        prompt_w = self.prompt_w

        def draw(p: QPainter, x: float, y: float, s: float) -> None:
            p.save()
            p.translate(x, y)
            p.scale(s, s)
            p.setFont(prompt_font)
            p.setPen(QColor(theme.PROMPT))
            fm = QFontMetricsF(prompt_font, p.device())
            p.drawText(QPointF(0, fm.ascent()), ">")
            layout.draw(p, QPointF(prompt_w, 0))
            p.restore()
        return _Block(h, draw, self.column, keep_with_next=keep)

    def output_block(self, out: Output) -> _Block | None:
        avail = self.column - self.out_indent
        if out.kind == "math":
            pix = None
            if out.meta.get("parts"):
                pix = render_parts(out.meta["parts"], MATH_SIZE, theme.OUTPUT_TEXT, MATH_RATIO)
            elif not out.meta.get("prefer_pretty") and out.latex:
                pix = render_latex(out.latex, MATH_SIZE, theme.OUTPUT_TEXT, MATH_RATIO)
            k = RESOLUTION / (100.0 * MATH_RATIO)   # image pixels -> device units
            if pix is not None and (pix.width() * k * MIN_MATH_SCALE <= avail or not out.text):
                return _pixmap_block(pix, pix.width() * k, pix.height() * k, indent=self.out_indent)
            if pix is not None:   # far too wide to shrink legibly: wrap the plain text instead
                layout, _, h = _text_layout(out.text, self.text_font, self.device, avail, theme.OUTPUT_TEXT)
                return _layout_block(layout, avail, h, indent=self.out_indent)
            layout, w, h = _text_layout(out.pretty or out.text, self.text_font, self.device, None,
                                        theme.OUTPUT_TEXT)
            return _layout_block(layout, w, h, indent=self.out_indent, centered=True)
        if out.kind == "plot":
            pix = QPixmap()
            if not out.png or not pix.loadFromData(out.png, "PNG"):
                return None
            k = RESOLUTION / PLOT_DPI
            return _pixmap_block(pix, pix.width() * k, pix.height() * k, indent=self.out_indent)
        color = {"error": theme.ERROR, "warning": theme.WARNING}.get(out.kind, theme.OUTPUT_TEXT)
        centered = out.kind == "text" and not out.meta.get("monospace")
        align = Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft
        layout, _, h = _text_layout(out.text, self.text_font, self.device, avail, color, align)
        return _layout_block(layout, avail, h, indent=self.out_indent)


def _scale(b: _Block, column: float, page_h: float) -> float:
    """Shrink factor so that *b* fits both the column width and one page."""
    s = 1.0
    avail = column - b.indent
    if b.width > avail > 0:
        s = avail / b.width
    if b.height * s > page_h > 0:
        s = page_h / b.height
    return s


def _paginate(blocks: list[_Block], column: float,
              page_h: float) -> list[list[tuple[_Block, float, float]]]:
    """Assign blocks to pages; returns per page a list of (block, y, scale)."""
    scales = [_scale(b, column, page_h) for b in blocks]
    heights = [b.height * s for b, s in zip(blocks, scales)]
    pages: list[list[tuple[_Block, float, float]]] = [[]]
    y = 0.0
    for i, b in enumerate(blocks):
        gap = b.space_before if pages[-1] else 0.0
        need = heights[i]
        if b.keep_with_next and i + 1 < len(blocks):
            with_next = need + blocks[i + 1].space_before + heights[i + 1]
            if with_next <= page_h:
                need = with_next
        if pages[-1] and y + gap + need > page_h:
            pages.append([])
            y, gap = 0.0, 0.0
        pages[-1].append((b, y + gap, scales[i]))
        y += gap + heights[i]
    return pages


def export_pdf(source, path: str | Path, title: str = "Worksheet") -> int:
    """Write *source* (a Worksheet, or cells / (input, outputs) pairs) to *path*.

    Returns the number of pages written. Raises OSError if the file cannot be written.
    """
    path = Path(path)
    writer = QPdfWriter(str(path))
    writer.setResolution(RESOLUTION)
    writer.setTitle(title)
    writer.setCreator("Symple")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM),
                                     QPageLayout.Unit.Millimeter))
    painter = QPainter()
    if not painter.begin(writer):
        raise OSError(f"cannot write {path}")
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        area = writer.pageLayout().paintRectPixels(RESOLUTION)
        column, full_h = float(area.width()), float(area.height())
        footer_font = QFont()
        footer_font.setPointSizeF(FOOTER_SIZE)
        footer_h = QFontMetricsF(footer_font, writer).height() + _pt(10)
        body_h = full_h - footer_h

        builder = _Builder(writer, column)
        blocks = builder.title(title)
        for text, outs in _cells_of(source):
            blocks += builder.cell(text, outs)
        pages = _paginate(blocks, column, body_h)

        for n, page in enumerate(pages, 1):
            if n > 1:
                writer.newPage()
            for b, y, s in page:
                x = b.indent
                if b.centered:
                    x += (column - b.indent - b.width * s) / 2
                b.draw(painter, x, y, s)
            painter.setFont(footer_font)
            painter.setPen(QColor(FOOTER_COLOR))
            foot = QRectF(0, full_h - QFontMetricsF(footer_font, writer).height(), column, footer_h)
            painter.drawText(foot, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "Created with Symple")
            painter.drawText(foot, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                             f"Page {n} of {len(pages)}")
        return len(pages)
    finally:
        painter.end()

