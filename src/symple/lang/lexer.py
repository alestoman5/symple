"""A tolerant lexer: it never raises, malformed input becomes tokens with ``error`` set.

This matters because the same lexer drives syntax highlighting, where the text is
usually incomplete while the user is typing.
"""
from __future__ import annotations

from .tokens import KEYWORDS, PUNCT, SYMBOL_OPERATORS, T, Token


def _is_name_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_name_char(c: str) -> bool:
    return c.isalnum() or c == "_"


def tokenize(src: str, *, keep_comments: bool = False) -> list[Token]:
    """Split *src* into tokens. The list always ends with an EOF token."""
    toks: list[Token] = []
    i, n = 0, len(src)

    while i < n:
        c = src[i]

        if c.isspace():
            i += 1
            continue

        if c == "#":
            j = src.find("\n", i)
            j = n if j == -1 else j
            if keep_comments:
                toks.append(Token(T.COMMENT, src[i:j], i, j))
            i = j
            continue

        # Numbers: 12, 1.5, .5, 1e-3, 2.5E+10.  '1..3' must lex as 1 .. 3.
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()
                           and not (i > 0 and src[i - 1] == ".")):
            j = i
            while j < n and src[j].isdigit():
                j += 1
            if j < n and src[j] == "." and not src.startswith("..", j):
                j += 1
                while j < n and src[j].isdigit():
                    j += 1
            if j < n and src[j] in "eE":
                k = j + 1
                if k < n and src[k] in "+-":
                    k += 1
                if k < n and src[k].isdigit():
                    j = k
                    while j < n and src[j].isdigit():
                        j += 1
            toks.append(Token(T.NUMBER, src[i:j], i, j))
            i = j
            continue

        if _is_name_start(c):
            j = i + 1
            while j < n and _is_name_char(src[j]):
                j += 1
            word = src[i:j]
            kind = T.KEYWORD if word in KEYWORDS else T.NAME
            toks.append(Token(kind, word, i, j))
            i = j
            continue

        if c == "`":  # quoted name: `any text`
            j = src.find("`", i + 1)
            if j == -1:
                toks.append(Token(T.NAME, src[i + 1:], i, n, error="unterminated quoted name"))
                i = n
            else:
                toks.append(Token(T.NAME, src[i + 1:j], i, j + 1))
                i = j + 1
            continue

        if c == '"':
            j = i + 1
            buf = []
            closed = False
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                    continue
                if src[j] == '"':
                    closed = True
                    break
                buf.append(src[j])
                j += 1
            if closed:
                toks.append(Token(T.STRING, "".join(buf), i, j + 1))
                i = j + 1
            else:
                toks.append(Token(T.STRING, "".join(buf), i, n, error="unterminated string"))
                i = n
            continue

        if c == "%":
            j = i
            while j < n and src[j] == "%" and j - i < 3:
                j += 1
            toks.append(Token(T.DITTO, src[i:j], i, j))
            i = j
            continue

        for op in SYMBOL_OPERATORS:
            if src.startswith(op, i):
                toks.append(Token(T.OP, op, i, i + len(op)))
                i += len(op)
                break
        else:
            if c in PUNCT:
                toks.append(Token(PUNCT[c], c, i, i + 1))
            else:
                toks.append(Token(T.ERROR, c, i, i + 1, error=f"unexpected character {c!r}"))
            i += 1

    toks.append(Token(T.EOF, "", n, n))
    return toks
