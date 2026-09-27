"""Abstract syntax tree for the Symple input language.

Every node carries ``start``/``end`` source offsets so diagnostics can point at it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    start: int = field(default=0, kw_only=True)
    end: int = field(default=0, kw_only=True)


# ---------------------------------------------------------------- expressions

@dataclass(eq=False)
class Num(Node):
    text: str


@dataclass(eq=False)
class Str(Node):
    value: str


@dataclass(eq=False)
class Name(Node):
    id: str


@dataclass(eq=False)
class Ditto(Node):
    depth: int  # 1 for %, 2 for %%, 3 for %%%


@dataclass(eq=False)
class Uneval(Node):
    """'expr' -- delays evaluation, e.g. x := 'x' unassigns x."""
    expr: Node


@dataclass(eq=False)
class Call(Node):
    func: Node
    args: list[Node]


@dataclass(eq=False)
class Index(Node):
    base: Node
    indices: list[Node]


@dataclass(eq=False)
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass(eq=False)
class UnOp(Node):
    op: str       # '-', '+', 'not', '!'(postfix factorial)
    operand: Node


@dataclass(eq=False)
class Range(Node):
    lo: Node
    hi: Node


@dataclass(eq=False)
class Seq(Node):
    items: list[Node]


@dataclass(eq=False)
class ListLit(Node):
    items: list[Node]


@dataclass(eq=False)
class SetLit(Node):
    items: list[Node]


@dataclass(eq=False)
class Arrow(Node):
    params: list[str]
    body: Node


@dataclass(eq=False)
class Proc(Node):
    params: list[str]
    locals: list[str]
    globals: list[str]
    body: list["Stmt"]


# ----------------------------------------------------------------- statements

@dataclass(eq=False)
class Stmt(Node):
    show: bool = field(default=True, kw_only=True)  # False when terminated by ':'
    terminated: bool = field(default=True, kw_only=True)  # False when ';'/':' was omitted


@dataclass(eq=False)
class ExprStmt(Stmt):
    expr: Node


@dataclass(eq=False)
class Assign(Stmt):
    targets: list[Node]
    value: Node


@dataclass(eq=False)
class If(Stmt):
    branches: list[tuple[Node, list[Stmt]]]
    orelse: list[Stmt] | None


@dataclass(eq=False)
class For(Stmt):
    var: str | None
    frm: Node | None
    by: Node | None
    to: Node | None
    in_: Node | None
    cond: Node | None
    body: list[Stmt]


@dataclass(eq=False)
class Return(Stmt):
    value: Node | None


@dataclass(eq=False)
class Break(Stmt):
    pass


@dataclass(eq=False)
class Next(Stmt):
    pass


def walk(node):
    """Yield *node* and every node below it (depth first)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, Node):
            yield cur
            for value in vars(cur).values():
                stack.append(value)
        elif isinstance(cur, (list, tuple)):
            stack.extend(reversed(cur))
