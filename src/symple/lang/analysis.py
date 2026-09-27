"""Checks that run on top of the parser: problems that are syntactically valid
but almost certainly mistakes (wrong argument counts, typos in function names,
'=' where ':=' was intended, ...).
"""
from __future__ import annotations

import difflib
from collections.abc import Iterable

from ..catalog import CATALOG, PROTECTED
from . import ast as A
from .diagnostics import ERROR, INFO, WARNING, Diagnostic
from .parser import ParseResult, parse

# Functions whose variable argument must look like  x = a..b  rather than a bare range.
_RANGE_FUNCS = {"int", "sum", "product", "add", "mul", "seq", "plot", "plot3d"}
_LOWER_CATALOG = {name.lower(): name for name in CATALOG}


def analyze(src: str, known_names: Iterable[str] = ()) -> ParseResult:
    """Parse *src* and add semantic diagnostics.

    *known_names* are names already defined in the session (earlier worksheet
    cells), so calls to user functions are not reported as typos.
    """
    result = parse(src)
    checker = _Checker(set(known_names))
    checker.check_block(result.statements, top_level=True)
    diags = result.diagnostics + checker.diags
    if result.statements and not result.statements[-1].terminated and result.ok:
        last = result.statements[-1]
        diags.append(Diagnostic(INFO, max(last.end - 1, last.start), last.end,
                                "statement has no terminator; ';' is assumed",
                                "end with ';' to show the result or ':' to hide it"))
    result.diagnostics = sorted(diags, key=lambda d: (d.start, d.end))
    return result


class _Checker:
    def __init__(self, known: set[str]):
        self.defined = set(known)
        self.diags: list[Diagnostic] = []
        self.loop_depth = 0
        self.proc_depth = 0

    def add(self, severity, node, message, hint=None):
        self.diags.append(Diagnostic(severity, node.start, node.end, message, hint))

    # ------------------------------------------------------------ statements

    def check_block(self, stmts: list[A.Stmt], top_level: bool = False) -> None:
        # Collect names assigned anywhere in this block first, so a function
        # defined later in the same cell is not reported as unknown.
        for stmt in stmts:
            for node in A.walk(stmt):
                if isinstance(node, A.Assign):
                    for t in node.targets:
                        if isinstance(t, A.Name):
                            self.defined.add(t.id)
        for stmt in stmts:
            self.check_stmt(stmt, top_level)

    def check_stmt(self, stmt: A.Stmt, top_level: bool) -> None:
        if isinstance(stmt, A.Assign):
            for t in stmt.targets:
                name = t.id if isinstance(t, A.Name) else None
                if name in PROTECTED:
                    self.add(ERROR, t, f"'{name}' is a protected built-in name and cannot be assigned")
                self.check_expr(t.base if isinstance(t, A.Index) else None)
                if isinstance(t, A.Index):
                    for i in t.indices:
                        self.check_expr(i)
            self.check_expr(stmt.value)
        elif isinstance(stmt, A.ExprStmt):
            e = stmt.expr
            if top_level and isinstance(e, A.BinOp) and e.op == "=" and isinstance(e.left, A.Name) \
                    and e.left.id not in self.defined:
                self.add(WARNING, e, f"'{e.left.id} = ...' is an equation, not an assignment",
                         f"use '{e.left.id} := ...' to assign a value")
            self.check_expr(e)
        elif isinstance(stmt, A.If):
            for cond, body in stmt.branches:
                self.check_expr(cond)
                self.check_block(body)
            if stmt.orelse:
                self.check_block(stmt.orelse)
        elif isinstance(stmt, A.For):
            if stmt.var:
                self.defined.add(stmt.var)
            for part in (stmt.frm, stmt.by, stmt.to, stmt.in_, stmt.cond):
                self.check_expr(part)
            self.loop_depth += 1
            self.check_block(stmt.body)
            self.loop_depth -= 1
        elif isinstance(stmt, A.Return):
            if self.proc_depth == 0:
                self.add(WARNING, stmt, "'return' outside a procedure")
            self.check_expr(stmt.value)
        elif isinstance(stmt, (A.Break, A.Next)):
            if self.loop_depth == 0:
                word = "break" if isinstance(stmt, A.Break) else "next"
                self.add(ERROR, stmt, f"'{word}' outside a loop")

    # ----------------------------------------------------------- expressions

    def check_expr(self, node: A.Node | None) -> None:
        if node is None:
            return
        if isinstance(node, A.Call):
            self.check_call(node)
            for a in node.args:
                self.check_expr(a)
            if not isinstance(node.func, A.Name):
                self.check_expr(node.func)
        elif isinstance(node, A.Arrow):
            self._check_params(node.params, node)
            saved = set(self.defined)
            self.defined.update(node.params)
            self.check_expr(node.body)
            self.defined = saved
        elif isinstance(node, A.Proc):
            self._check_params(node.params + node.locals, node)
            saved, depth = set(self.defined), self.loop_depth
            self.defined.update(node.params, node.locals)
            self.proc_depth += 1
            self.loop_depth = 0
            self.check_block(node.body)
            self.proc_depth -= 1
            self.defined, self.loop_depth = saved, depth
        elif isinstance(node, A.Name):
            if node.id == "pi" and "pi" not in self.defined:
                self.add(INFO, node, "'pi' is an ordinary symbol here", "use 'Pi' for 3.14159...")
        elif isinstance(node, A.BinOp):
            if node.op == "^" and isinstance(node.left, A.Name) and node.left.id == "e" \
                    and "e" not in self.defined:
                self.add(INFO, node.left, "'e' is an ordinary symbol here",
                         "use exp(x) for the exponential function")
            self.check_expr(node.left)
            self.check_expr(node.right)
        else:
            for child in _children(node):
                self.check_expr(child)

    def _check_params(self, names: list[str], node: A.Node) -> None:
        seen = set()
        for name in names:
            if name in seen:
                self.add(ERROR, node, f"parameter or local '{name}' is declared twice")
            seen.add(name)

    def check_call(self, call: A.Call) -> None:
        if not isinstance(call.func, A.Name):
            return
        name = call.func.id
        if name in self.defined:
            return
        entry = CATALOG.get(name)
        if entry is None:
            suggestion = _suggest(name)
            if suggestion:
                self.add(WARNING, call.func, f"unknown function '{name}'",
                         f"did you mean '{suggestion}'? Unknown functions stay unevaluated")
            return
        if entry.kind == "constant":
            self.add(WARNING, call.func, f"'{name}' is a constant, not a function")
            return

        n = len(call.args)
        variadic = any(isinstance(a, (A.Seq, A.Ditto)) or (isinstance(a, A.BinOp) and a.op == "$")
                       for a in call.args)
        if not variadic:
            if n < entry.min_args:
                self.add(ERROR, call, f"{name} expects at least {entry.min_args} argument"
                         f"{'s' if entry.min_args != 1 else ''}, got {n}", f"usage: {entry.signature}")
            elif entry.max_args is not None and n > entry.max_args:
                self.add(ERROR, call, f"{name} expects at most {entry.max_args} argument"
                         f"{'s' if entry.max_args != 1 else ''}, got {n}", f"usage: {entry.signature}")
        if name in _RANGE_FUNCS:
            for a in call.args[1:]:
                if isinstance(a, A.Range):
                    self.add(WARNING, a, "range is missing its variable",
                             "write it as  x = a..b")


def _children(node: A.Node):
    for value in vars(node).values():
        if isinstance(value, A.Node):
            yield value
        elif isinstance(value, list):
            yield from (v for v in value if isinstance(v, A.Node))


def _suggest(name: str) -> str | None:
    if name.lower() in _LOWER_CATALOG and _LOWER_CATALOG[name.lower()] != name:
        return _LOWER_CATALOG[name.lower()]
    if len(name) < 3:
        return None
    close = difflib.get_close_matches(name, CATALOG, n=1, cutoff=0.8)
    return close[0] if close else None
