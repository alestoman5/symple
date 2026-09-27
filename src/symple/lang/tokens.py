"""Token definitions for the Symple input language."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class T(Enum):
    NUMBER = auto()
    NAME = auto()
    STRING = auto()
    KEYWORD = auto()
    OP = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    SEMI = auto()      # ';'  terminator, output shown
    COLON = auto()     # ':'  terminator, output hidden
    DITTO = auto()     # '%', '%%', '%%%'
    COMMENT = auto()
    ERROR = auto()     # a character the lexer does not understand
    EOF = auto()


KEYWORDS = frozenset(
    """
    proc local global description option options end if then elif else fi
    do od for from to by while in return break next
    and or not xor implies mod union intersect minus
    """.split()
)

# Keywords that behave like binary operators.
WORD_OPERATORS = frozenset(
    {"and", "or", "not", "xor", "implies", "mod", "union", "intersect", "minus"}
)

# Longest first so that e.g. ':=' wins over ':'.
SYMBOL_OPERATORS = (
    ":=", "->", "..", "**", "<>", "<=", ">=",
    "+", "-", "*", "/", "^", "=", "<", ">", "!", "$", ".", "'",
)

PUNCT = {
    "(": T.LPAREN, ")": T.RPAREN,
    "[": T.LBRACKET, "]": T.RBRACKET,
    "{": T.LBRACE, "}": T.RBRACE,
    ",": T.COMMA, ";": T.SEMI, ":": T.COLON,
}

OPENERS = {T.LPAREN: T.RPAREN, T.LBRACKET: T.RBRACKET, T.LBRACE: T.RBRACE}


@dataclass(frozen=True, slots=True)
class Token:
    kind: T
    text: str
    start: int          # offset of first character in the source
    end: int            # offset one past the last character
    error: str | None = None   # set for malformed tokens (e.g. unterminated string)

    def is_kw(self, *words: str) -> bool:
        return self.kind is T.KEYWORD and self.text in words

    def is_op(self, *ops: str) -> bool:
        return self.kind is T.OP and self.text in ops

    def __repr__(self) -> str:  # compact, handy in test failures
        return f"{self.kind.name}({self.text!r}@{self.start})"
