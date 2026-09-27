"""Runtime value types that SymPy does not already provide."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import sympy as sp


class EvalError(Exception):
    """A user-facing evaluation error ("Error, (in int) ...")."""

    def __init__(self, message: str, where: str | None = None):
        super().__init__(message)
        self.where = where

    def __str__(self) -> str:
        msg = super().__str__()
        return f"(in {self.where}) {msg}" if self.where else msg


class ExprSeq(tuple):
    """An expression sequence: a, b, c. Sequences flatten into lists, sets and calls."""

    def __repr__(self) -> str:
        return f"ExprSeq{tuple.__repr__(self)}"


NULL = ExprSeq()


class MList(list):
    """A list: [a, b, c]."""


class MSet(list):
    """A set: {a, b, c}. Duplicates are removed; insertion order is kept."""

    def __init__(self, items=()):
        super().__init__()
        for item in items:
            if not any(_same(item, x) for x in self):
                self.append(item)


def _same(a, b) -> bool:
    try:
        return bool(a == b)
    except Exception:
        return a is b


class MString(str):
    """A string literal."""


@dataclass(frozen=True)
class MRange:
    lo: Any
    hi: Any


# ------------------------------------------------------------------ callables

class Callable_:
    """Base class for values that can be called with f(args)."""

    def __call__(self, ev, args: list) -> Any:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(eq=False)
class ArrowFunction(Callable_):
    """x -> body; the body (an AST node) is evaluated at call time."""
    params: list[str]
    body: Any                          # lang.ast.Node
    closure: dict | None               # enclosing local frame (lexical scoping)
    source: str = ""
    display: Any = None                # ExprFunction used to typeset it, if available

    def __call__(self, ev, args):
        return ev.call_user(self, args)


@dataclass(eq=False)
class Procedure(Callable_):
    params: list[str]
    locals: list[str]
    globals: list[str]
    body: list                         # list of lang.ast.Stmt
    closure: dict | None
    source: str = ""

    def __call__(self, ev, args):
        return ev.call_user(self, args)


@dataclass(eq=False)
class ExprFunction(Callable_):
    """A function whose body is already a SymPy expression (unapply, D)."""
    params: tuple[sp.Symbol, ...]
    expr: Any

    def __call__(self, ev, args):
        if len(args) != len(self.params):
            raise EvalError(f"expected {len(self.params)} argument(s), got {len(args)}")
        pairs = list(zip(self.params, args))
        result = self.expr.subs(pairs, simultaneous=True) if hasattr(self.expr, "subs") else self.expr
        return result


@dataclass(eq=False)
class Builtin(Callable_):
    name: str
    fn: Callable
    raw: bool = False                  # receives unevaluated AST nodes
    extra: dict = field(default_factory=dict)

    def __call__(self, ev, args):
        return self.fn(ev, *args)


def is_callable(v) -> bool:
    return isinstance(v, Callable_)


@dataclass(frozen=True)
class Equation:
    """lhs = rhs where a side is not a SymPy object (e.g. x = 0..1, color = "red")."""
    lhs: Any
    rhs: Any


@dataclass(frozen=True)
class PlotResult:
    png: bytes
    title: str = ""


def eq_parts(v):
    """(lhs, rhs) if *v* is an equation of either kind, else None."""
    if isinstance(v, Equation):
        return v.lhs, v.rhs
    if isinstance(v, sp.Equality):
        return v.lhs, v.rhs
    return None
