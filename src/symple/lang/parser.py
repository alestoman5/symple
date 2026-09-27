"""Recursive-descent parser for the Symple (Maple-inspired) input language.

The parser never raises for bad input. Syntax errors are collected as diagnostics,
and the parser resynchronises at the next statement terminator so later statements
can still be checked.

Operator precedence, lowest to highest::

    ->            arrow functions (right associative)
    implies
    or  xor
    and
    not           (prefix)
    $             sequence operator: x$3, f(i) $ i = 1..3
    = <> < <= > >=
    ..            ranges
    union minus intersect
    + -  mod
    * / .
    unary + -
    ^ **          (right associative)
    !             postfix factorial
    f(...) a[...]
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ast as A
from .diagnostics import ERROR, Diagnostic
from .lexer import tokenize
from .tokens import T, Token

# Keywords that close a block; a statement list stops when it sees one.
BLOCK_CLOSERS = frozenset({"end", "fi", "od", "elif", "else"})
RELATIONS = ("=", "<>", "<", "<=", ">", ">=")
BLOCK_NAMES = {"if": "if", "fi": "if", "do": "do", "od": "do", "proc": "proc"}


class ParseError(Exception):
    def __init__(self, message: str, start: int, end: int, hint: str | None = None):
        super().__init__(message)
        self.diag = Diagnostic(ERROR, start, end, message, hint)


@dataclass
class ParseResult:
    statements: list[A.Stmt]
    diagnostics: list[Diagnostic]
    tokens: list[Token] = field(repr=False)

    @property
    def ok(self) -> bool:
        return not any(d.severity == ERROR for d in self.diagnostics)


def parse(src: str) -> ParseResult:
    return Parser(src).parse_program()


def _describe(tok: Token) -> str:
    if tok.kind is T.EOF:
        return "end of input"
    if tok.kind is T.STRING:
        return "a string"
    return f"'{tok.text}'"


class Parser:
    def __init__(self, src: str):
        self.src = src
        self.all_tokens = tokenize(src)
        self.diags: list[Diagnostic] = []
        self.toks: list[Token] = []
        for tok in self.all_tokens:
            if tok.error:
                self.diags.append(Diagnostic(ERROR, tok.start, tok.end, tok.error))
            if tok.kind is not T.ERROR:
                self.toks.append(tok)
        self.pos = 0

    # ------------------------------------------------------------ token helpers

    @property
    def tok(self) -> Token:
        return self.toks[self.pos]

    def peek(self, k: int = 1) -> Token:
        return self.toks[min(self.pos + k, len(self.toks) - 1)]

    def advance(self) -> Token:
        tok = self.toks[self.pos]
        if tok.kind is not T.EOF:
            self.pos += 1
        return tok

    @property
    def prev_end(self) -> int:
        return self.toks[self.pos - 1].end if self.pos else 0

    def at_terminator(self) -> bool:
        return self.tok.kind in (T.SEMI, T.COLON, T.EOF) or self.tok.is_kw(*BLOCK_CLOSERS)

    def error(self, message: str, tok: Token | None = None, hint: str | None = None) -> ParseError:
        tok = tok or self.tok
        start, end = tok.start, tok.end
        if tok.kind is T.EOF:  # point at the last real character instead of past the end
            start, end = max(self.prev_end - 1, 0), max(self.prev_end, 1)
        return ParseError(message, start, end, hint)

    def expect_kw(self, word: str, context: str) -> Token:
        if self.tok.is_kw(word):
            return self.advance()
        raise self.error(f"expected '{word}' {context}, found {_describe(self.tok)}")

    def expect_close(self, kind: T, opener: Token) -> Token:
        if self.tok.kind is kind:
            return self.advance()
        closer = {T.RPAREN: ")", T.RBRACKET: "]", T.RBRACE: "}"}[kind]
        if self.at_terminator() or self.tok.kind in (T.RPAREN, T.RBRACKET, T.RBRACE):
            raise ParseError(f"unclosed '{opener.text}'", opener.start, opener.end,
                             f"add a matching '{closer}'")
        raise self.error(f"expected ',' or '{closer}', found {_describe(self.tok)}")

    def expect_end(self, block: str, opener: Token) -> None:
        """Consume the closer of an if/do/proc block: 'end if', 'fi', 'end', ..."""
        tok = self.tok
        if tok.is_kw("end"):
            self.advance()
            nxt = self.tok
            if nxt.kind is T.KEYWORD and nxt.text in BLOCK_NAMES:
                self.advance()
                if BLOCK_NAMES[nxt.text] != block:
                    raise ParseError(f"'{opener.text}' block closed by 'end {nxt.text}'",
                                     tok.start, nxt.end, f"use 'end {block}'")
            return
        if tok.is_kw("fi", "od"):
            self.advance()
            if BLOCK_NAMES[tok.text] != block:
                raise ParseError(f"'{opener.text}' block closed by '{tok.text}'",
                                 tok.start, tok.end, f"use 'end {block}'")
            return
        raise ParseError(f"unclosed '{opener.text}' block", opener.start, opener.end,
                         f"missing 'end {block}'")

    def sync(self) -> None:
        """Skip to just after the next top-level terminator (error recovery)."""
        depth = 0
        while self.tok.kind is not T.EOF:
            kind = self.tok.kind
            if kind in (T.LPAREN, T.LBRACKET, T.LBRACE):
                depth += 1
            elif kind in (T.RPAREN, T.RBRACKET, T.RBRACE):
                depth = max(depth - 1, 0)
            elif kind in (T.SEMI, T.COLON) and depth == 0:
                self.advance()
                return
            self.advance()

    # ------------------------------------------------------------- statements

    def parse_program(self) -> ParseResult:
        stmts = self.parse_block(top_level=True)
        return ParseResult(stmts, sorted(self.diags, key=lambda d: d.start), self.all_tokens)

    def parse_block(self, top_level: bool = False) -> list[A.Stmt]:
        stmts: list[A.Stmt] = []
        while True:
            while self.tok.kind in (T.SEMI, T.COLON):  # empty statements
                self.advance()
            tok = self.tok
            if tok.kind is T.EOF:
                return stmts
            if tok.is_kw(*BLOCK_CLOSERS):
                if not top_level:
                    return stmts
                self.diags.append(Diagnostic(ERROR, tok.start, tok.end,
                                             f"'{tok.text}' without a matching opening statement"))
                self.advance()
                if tok.text == "end" and self.tok.kind is T.KEYWORD and self.tok.text in BLOCK_NAMES:
                    self.advance()
                continue
            start_pos = self.pos
            try:
                stmt = self.parse_statement()
            except ParseError as e:
                self.diags.append(e.diag)
                if self.pos == start_pos:
                    self.advance()
                self.sync()
                continue
            if self.tok.kind in (T.SEMI, T.COLON):
                stmt.show = self.tok.kind is T.SEMI
                stmt.end = self.advance().end
            elif self.tok.kind is T.EOF or self.tok.is_kw(*BLOCK_CLOSERS):
                stmt.terminated = False
            else:
                self.diags.append(Diagnostic(
                    ERROR, max(self.prev_end - 1, 0), self.prev_end,
                    "missing ';' or ':' after statement",
                    f"found {_describe(self.tok)} where a new statement starts"))
                stmt.terminated = False
            stmts.append(stmt)

    def parse_statement(self) -> A.Stmt:
        tok = self.tok
        if tok.is_kw("if"):
            return self.parse_if()
        if tok.is_kw("for", "while", "do"):
            return self.parse_loop()
        if tok.is_kw("return"):
            self.advance()
            value = None if self.at_terminator() else self.parse_seq()
            return A.Return(value, start=tok.start, end=self.prev_end)
        if tok.is_kw("break"):
            self.advance()
            return A.Break(start=tok.start, end=tok.end)
        if tok.is_kw("next"):
            self.advance()
            return A.Next(start=tok.start, end=tok.end)

        expr = self.parse_seq()
        if self.tok.is_op(":="):
            op = self.advance()
            targets = expr.items if isinstance(expr, A.Seq) else [expr]
            for t in targets:
                if not isinstance(t, (A.Name, A.Index)):
                    raise ParseError("can only assign to a name or an indexed name",
                                     t.start, t.end)
            if self.at_terminator():
                raise self.error("missing value after ':='", op)
            value = self.parse_seq()
            return A.Assign(targets, value, start=expr.start, end=self.prev_end)
        return A.ExprStmt(expr, start=expr.start, end=self.prev_end)

    def parse_if(self) -> A.If:
        opener = self.advance()
        branches = []
        cond = self.parse_expr()
        self.expect_kw("then", "after the 'if' condition")
        branches.append((cond, self.parse_block()))
        orelse = None
        while True:
            if self.tok.is_kw("elif"):
                self.advance()
                cond = self.parse_expr()
                self.expect_kw("then", "after the 'elif' condition")
                branches.append((cond, self.parse_block()))
            elif self.tok.is_kw("else"):
                self.advance()
                orelse = self.parse_block()
                break
            else:
                break
        self.expect_end("if", opener)
        return A.If(branches, orelse, start=opener.start, end=self.prev_end)

    def parse_loop(self) -> A.For:
        opener = self.tok
        var = frm = by = to = in_ = cond = None
        if self.tok.is_kw("for"):
            self.advance()
            if self.tok.kind is not T.NAME:
                raise self.error("expected a loop variable after 'for'")
            var = self.advance().text
            if self.tok.is_kw("in"):
                self.advance()
                in_ = self.parse_expr()
            else:
                seen = set()
                while self.tok.is_kw("from", "by", "to"):
                    word = self.advance()
                    if word.text in seen:
                        raise self.error(f"duplicate '{word.text}' clause", word)
                    seen.add(word.text)
                    value = self.parse_expr()
                    if word.text == "from":
                        frm = value
                    elif word.text == "by":
                        by = value
                    else:
                        to = value
        if self.tok.is_kw("while"):
            self.advance()
            cond = self.parse_expr()
        do_tok = self.tok
        self.expect_kw("do", "to start the loop body")
        body = self.parse_block()
        self.expect_end("do", do_tok if opener is do_tok else opener)
        return A.For(var, frm, by, to, in_, cond, body, start=opener.start, end=self.prev_end)

    # ------------------------------------------------------------ expressions

    def parse_seq(self) -> A.Node:
        first = self.parse_expr()
        if self.tok.kind is not T.COMMA:
            return first
        items = [first]
        while self.tok.kind is T.COMMA:
            self.advance()
            items.append(self.parse_expr())
        return A.Seq(items, start=first.start, end=self.prev_end)

    def parse_expr(self) -> A.Node:
        return self.parse_arrow()

    def parse_arrow(self) -> A.Node:
        left = self.parse_implies()
        if not self.tok.is_op("->"):
            return left
        arrow = self.advance()
        if isinstance(left, A.Name):
            params = [left.id]
        elif isinstance(left, A.Seq) and all(isinstance(i, A.Name) for i in left.items):
            params = [i.id for i in left.items]
        else:
            raise ParseError("arrow function parameters must be names, e.g. (x, y) -> x*y",
                             left.start, arrow.end)
        body = self.parse_arrow()
        return A.Arrow(params, body, start=left.start, end=body.end)

    def _binary_kw(self, words: tuple[str, ...], sub) -> A.Node:
        left = sub()
        while self.tok.is_kw(*words):
            op = self.advance().text
            right = sub()
            left = A.BinOp(op, left, right, start=left.start, end=right.end)
        return left

    def parse_implies(self) -> A.Node:
        return self._binary_kw(("implies",), self.parse_or)

    def parse_or(self) -> A.Node:
        return self._binary_kw(("or", "xor"), self.parse_and)

    def parse_and(self) -> A.Node:
        return self._binary_kw(("and",), self.parse_not)

    def parse_not(self) -> A.Node:
        if self.tok.is_kw("not"):
            tok = self.advance()
            operand = self.parse_not()
            return A.UnOp("not", operand, start=tok.start, end=operand.end)
        return self.parse_dollar()

    def parse_dollar(self) -> A.Node:
        left = self.parse_rel()
        while self.tok.is_op("$"):
            self.advance()
            right = self.parse_rel()
            left = A.BinOp("$", left, right, start=left.start, end=right.end)
        return left

    def parse_rel(self) -> A.Node:
        left = self.parse_range()
        if self.tok.is_op(*RELATIONS):
            op = self.advance().text
            right = self.parse_range()
            left = A.BinOp(op, left, right, start=left.start, end=right.end)
            if self.tok.is_op(*RELATIONS):
                raise self.error("comparisons cannot be chained",
                                 hint="combine them with 'and', e.g. a < b and b < c")
        return left

    def parse_range(self) -> A.Node:
        left = self.parse_setop()
        if self.tok.is_op(".."):
            op = self.advance()
            if self.at_terminator() or self.tok.kind in (T.COMMA, T.RPAREN, T.RBRACKET):
                raise self.error("range is missing its upper end", op)
            right = self.parse_setop()
            return A.Range(left, right, start=left.start, end=right.end)
        return left

    def parse_setop(self) -> A.Node:
        return self._binary_kw(("union", "minus", "intersect"), self.parse_add)

    def parse_add(self) -> A.Node:
        left = self.parse_mul()
        while self.tok.is_op("+", "-") or self.tok.is_kw("mod"):
            op = self.advance().text
            right = self.parse_mul()
            left = A.BinOp(op, left, right, start=left.start, end=right.end)
        return left

    def parse_mul(self) -> A.Node:
        left = self.parse_unary()
        while self.tok.is_op("*", "/", "."):
            op = self.advance().text
            right = self.parse_unary()
            left = A.BinOp(op, left, right, start=left.start, end=right.end)
        return left

    def parse_unary(self) -> A.Node:
        if self.tok.is_op("-", "+"):
            tok = self.advance()
            operand = self.parse_unary()
            return A.UnOp(tok.text, operand, start=tok.start, end=operand.end)
        return self.parse_pow()

    def parse_pow(self) -> A.Node:
        base = self.parse_postfix()
        if self.tok.is_op("^", "**"):
            self.advance()
            exp = self.parse_unary()  # right associative, allows 2^-1
            return A.BinOp("^", base, exp, start=base.start, end=exp.end)
        return base

    def parse_postfix(self) -> A.Node:
        node = self.parse_primary()
        while True:
            tok = self.tok
            if tok.kind is T.LPAREN:
                self.advance()
                args = self.parse_items(T.RPAREN, tok)
                node = A.Call(node, args, start=node.start, end=self.prev_end)
            elif tok.kind is T.LBRACKET:
                self.advance()
                idx = self.parse_items(T.RBRACKET, tok)
                node = A.Index(node, idx, start=node.start, end=self.prev_end)
            elif tok.is_op("!"):
                self.advance()
                node = A.UnOp("!", node, start=node.start, end=tok.end)
            else:
                return node

    def parse_items(self, closer: T, opener: Token) -> list[A.Node]:
        items: list[A.Node] = []
        if self.tok.kind is closer:
            self.advance()
            return items
        while True:
            if self.at_terminator():
                raise ParseError(f"unclosed '{opener.text}'", opener.start, opener.end,
                                 "statement ended before the bracket was closed")
            items.append(self.parse_expr())
            if self.tok.kind is T.COMMA:
                self.advance()
                continue
            self.expect_close(closer, opener)
            return items

    def parse_primary(self) -> A.Node:
        tok = self.tok
        kind = tok.kind
        if kind is T.NUMBER:
            self.advance()
            return A.Num(tok.text, start=tok.start, end=tok.end)
        if kind is T.NAME:
            self.advance()
            return A.Name(tok.text, start=tok.start, end=tok.end)
        if kind is T.STRING:
            self.advance()
            return A.Str(tok.text, start=tok.start, end=tok.end)
        if kind is T.DITTO:
            self.advance()
            return A.Ditto(len(tok.text), start=tok.start, end=tok.end)
        if kind is T.LPAREN:
            self.advance()
            items = self.parse_items(T.RPAREN, tok)
            if len(items) == 1:
                inner = items[0]
                inner.start, inner.end = tok.start, self.prev_end
                return inner
            return A.Seq(items, start=tok.start, end=self.prev_end)
        if kind is T.LBRACKET:
            self.advance()
            items = self.parse_items(T.RBRACKET, tok)
            return A.ListLit(items, start=tok.start, end=self.prev_end)
        if kind is T.LBRACE:
            self.advance()
            items = self.parse_items(T.RBRACE, tok)
            return A.SetLit(items, start=tok.start, end=self.prev_end)
        if tok.is_kw("proc"):
            return self.parse_proc()
        if tok.is_op("'"):
            self.advance()
            if self.at_terminator():
                raise ParseError("unclosed quote", tok.start, tok.end)
            inner = self.parse_expr()
            if not self.tok.is_op("'"):
                raise ParseError("unclosed quote", tok.start, tok.end, "add a closing '")
            self.advance()
            return A.Uneval(inner, start=tok.start, end=self.prev_end)

        if kind is T.EOF:
            raise self.error("incomplete expression")
        if kind in (T.RPAREN, T.RBRACKET, T.RBRACE):
            raise self.error(f"unmatched '{tok.text}'")
        if kind in (T.SEMI, T.COLON):
            raise self.error(f"expected an expression before '{tok.text}'")
        if kind is T.OP and tok.text == ":=":
            raise self.error("missing name before ':='")
        if kind is T.KEYWORD:
            raise self.error(f"unexpected keyword '{tok.text}'")
        raise self.error(f"unexpected {_describe(tok)}")

    def parse_proc(self) -> A.Proc:
        opener = self.advance()
        if self.tok.kind is not T.LPAREN:
            raise self.error("expected '(' after 'proc'")
        lparen = self.advance()
        params: list[str] = []
        while self.tok.kind is not T.RPAREN:
            if self.tok.kind is not T.NAME:
                if self.at_terminator():
                    raise ParseError("unclosed '('", lparen.start, lparen.end)
                raise self.error(f"expected a parameter name, found {_describe(self.tok)}")
            params.append(self.advance().text)
            self._skip_type_annotation()
            if self.tok.kind is T.COMMA:
                self.advance()
            elif self.tok.kind is not T.RPAREN:
                self.expect_close(T.RPAREN, lparen)
        self.advance()
        self._skip_type_annotation()  # proc(...)::type

        locals_: list[str] = []
        globals_: list[str] = []
        while True:
            while self.tok.kind in (T.SEMI, T.COLON):
                self.advance()
            if self.tok.is_kw("local", "global"):
                target = locals_ if self.advance().text == "local" else globals_
                target.extend(self._name_list())
            elif self.tok.is_kw("description", "option", "options"):
                self.advance()
                self.parse_seq()  # accepted and ignored
            else:
                break
        body = self.parse_block()
        self.expect_end("proc", opener)
        return A.Proc(params, locals_, globals_, body, start=opener.start, end=self.prev_end)

    def _name_list(self) -> list[str]:
        names = []
        while True:
            if self.tok.kind is not T.NAME:
                raise self.error(f"expected a name, found {_describe(self.tok)}")
            names.append(self.advance().text)
            self._skip_type_annotation()
            if self.tok.is_op(":="):  # local x := 0 -- initial values are not supported
                raise self.error("initial values in declarations are not supported",
                                 hint="assign the value in the procedure body instead")
            if self.tok.kind is not T.COMMA:
                return names
            self.advance()

    def _skip_type_annotation(self) -> None:
        if self.tok.kind is T.COLON and self.peek().kind is T.COLON:
            self.advance()
            self.advance()
            self.parse_postfix()
