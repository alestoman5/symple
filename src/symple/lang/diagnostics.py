"""Diagnostics: problems found in the source, with a location the editor can underline."""
from __future__ import annotations

from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: str        # ERROR, WARNING or INFO
    start: int           # source offset of the first character
    end: int             # source offset one past the last character
    message: str
    hint: str | None = None

    def describe(self, src: str) -> str:
        line, col = line_col(src, self.start)
        text = f"{line}:{col}: {self.severity}: {self.message}"
        return f"{text} ({self.hint})" if self.hint else text


def line_col(src: str, offset: int) -> tuple[int, int]:
    """1-based line and column of *offset* in *src*."""
    line = src.count("\n", 0, offset) + 1
    col = offset - (src.rfind("\n", 0, offset) + 1) + 1
    return line, col
