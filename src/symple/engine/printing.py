"""Turn runtime values into display forms: LaTeX, Maple-style plain text, and a
Unicode "pretty" fallback for things LaTeX renderers can't handle (e.g. matrices).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp
from sympy.printing.latex import LatexPrinter
from sympy.printing.str import StrPrinter

from .values import (ArrowFunction, Builtin, Equation, ExprFunction, ExprSeq, MList, MRange,
                     MSet, MString, PlotResult, Procedure)

# SymPy function name -> name shown to the user
_FUNC_NAMES = {
    "asin": "arcsin", "acos": "arccos", "atan": "arctan", "asec": "arcsec",
    "acsc": "arccsc", "acot": "arccot", "asinh": "arcsinh", "acosh": "arccosh",
    "atanh": "arctanh", "atan2": "arctan", "gamma": "GAMMA", "zeta": "Zeta",
    "sign": "signum", "ceiling": "ceil", "Abs": "abs", "re": "Re", "im": "Im",
    "arg": "argument", "DiracDelta": "Dirac", "real_root": "surd",
}


@dataclass
class Output:
    """One displayable result, independent of SymPy so it can cross process boundaries."""
    kind: str                 # "math", "text", "plot", "error", "warning"
    text: str = ""            # plain text (Maple syntax where possible)
    latex: str = ""           # LaTeX, empty if not applicable
    pretty: str = ""          # Unicode 2-D fallback
    png: bytes = b""          # rendered image for plots
    label: str = ""           # assignment target, e.g. "f"
    meta: dict = field(default_factory=dict)


class _Latex(LatexPrinter):
    def __init__(self, settings=None):
        s = {"ln_notation": True, "inv_trig_style": "full", "mul_symbol": None,
             "imaginary_unit": r"\mathrm{I}"}
        s.update(settings or {})
        super().__init__(s)

    def _print_BooleanTrue(self, expr):
        return r"\mathrm{true}"

    def _print_BooleanFalse(self, expr):
        return r"\mathrm{false}"

    def _print_Order(self, expr):
        return r"O\left(%s\right)" % self._print(expr.expr)

    def _print_Function(self, expr, exp=None):
        name = type(expr).__name__
        if name in _FUNC_NAMES and name not in ("Abs",):
            args = ", ".join(self._print(a) for a in expr.args)
            tex = r"\operatorname{%s}{\left(%s \right)}" % (_FUNC_NAMES[name], args)
            return f"{tex}^{{{exp}}}" if exp else tex
        return super()._print_Function(expr, exp)


class _Text(StrPrinter):
    def _print_Pow(self, expr, rational=False):
        if expr.exp == sp.S.Half:
            return f"sqrt({self._print(expr.base)})"
        return super()._print_Pow(expr, rational).replace("**", "^")

    def _print_Pi(self, expr):
        return "Pi"

    def _print_Exp1(self, expr):
        return "exp(1)"

    def _print_Infinity(self, expr):
        return "infinity"

    def _print_NegativeInfinity(self, expr):
        return "-infinity"

    def _print_ComplexInfinity(self, expr):
        return "undefined"

    def _print_NaN(self, expr):
        return "undefined"

    def _print_EulerGamma(self, expr):
        return "gamma"

    def _print_BooleanTrue(self, expr):
        return "true"

    def _print_BooleanFalse(self, expr):
        return "false"

    def _print_log(self, expr):
        return f"ln({self._print(expr.args[0])})"

    def _print_Equality(self, expr):
        return f"{self._print(expr.lhs)} = {self._print(expr.rhs)}"

    def _print_Unequality(self, expr):
        return f"{self._print(expr.lhs)} <> {self._print(expr.rhs)}"

    def _print_Relational(self, expr):
        return f"{self._print(expr.lhs)} {expr.rel_op} {self._print(expr.rhs)}"

    def _print_Function(self, expr):
        name = type(expr).__name__
        if name in _FUNC_NAMES:
            return f"{_FUNC_NAMES[name]}({', '.join(self._print(a) for a in expr.args)})"
        return super()._print_Function(expr)

    def _print_Derivative(self, expr):
        vars_ = ", ".join(self._print(v) if n == 1 else f"{self._print(v)}${n}"
                          for v, n in expr.variable_count)
        return f"diff({self._print(expr.expr)}, {vars_})"

    def _print_Integral(self, expr):
        (var, *lims), = expr.limits
        if lims:
            return f"int({self._print(expr.function)}, {self._print(var)} = " \
                   f"{self._print(lims[0])}..{self._print(lims[1])})"
        return f"int({self._print(expr.function)}, {self._print(var)})"

    def _print_MatrixBase(self, expr):
        rows = ", ".join("[" + ", ".join(self._print(x) for x in expr.row(i)) + "]"
                         for i in range(expr.rows))
        return f"Matrix([{rows}])"

    _print_MutableDenseMatrix = _print_ImmutableDenseMatrix = _print_MatrixBase


_LATEX = _Latex()
_TEXT = _Text({"order": None})


def to_text(v) -> str:
    if isinstance(v, ExprSeq):
        return ", ".join(to_text(x) for x in v)
    if isinstance(v, MList):
        return "[" + ", ".join(to_text(x) for x in v) + "]"
    if isinstance(v, MSet):
        return "{" + ", ".join(to_text(x) for x in v) + "}"
    if isinstance(v, MString):
        return f'"{v}"'
    if isinstance(v, MRange):
        return f"{to_text(v.lo)} .. {to_text(v.hi)}"
    if isinstance(v, Equation):
        return f"{to_text(v.lhs)} = {to_text(v.rhs)}"
    if isinstance(v, (ArrowFunction, Procedure)):
        return v.source
    if isinstance(v, ExprFunction):
        params = ", ".join(str(p) for p in v.params)
        params = params if len(v.params) == 1 else f"({params})"
        return f"{params} -> {to_text(v.expr)}"
    if isinstance(v, Builtin):
        return v.name
    if isinstance(v, bool):
        return "true" if v else "false"
    try:
        return _TEXT.doprint(v)
    except Exception:
        return str(v)


def to_latex(v) -> str:
    if isinstance(v, ExprSeq):
        return ", ".join(to_latex(x) for x in v)
    if isinstance(v, MList):
        return r"\left[" + ", ".join(to_latex(x) for x in v) + r"\right]"
    if isinstance(v, MSet):
        return r"\left\{" + ", ".join(to_latex(x) for x in v) + r"\right\}"
    if isinstance(v, MString):
        return r'\mathrm{"%s"}' % v.replace("\\", "").replace(" ", r"\ ")
    if isinstance(v, MRange):
        return f"{to_latex(v.lo)} \\,..\\, {to_latex(v.hi)}"
    if isinstance(v, Equation):
        return f"{to_latex(v.lhs)} = {to_latex(v.rhs)}"
    if isinstance(v, ExprFunction):
        params = ", ".join(_LATEX.doprint(p) for p in v.params)
        params = params if len(v.params) == 1 else f"\\left({params}\\right)"
        return f"{params} \\mapsto {to_latex(v.expr)}"
    if isinstance(v, bool):
        return r"\mathrm{true}" if v else r"\mathrm{false}"
    return _LATEX.doprint(v)


def to_pretty(v) -> str:
    if isinstance(v, ExprSeq) and any(needs_pretty(x) for x in v):
        return _hjoin([to_pretty(x) for x in v], ", ")
    if isinstance(v, (ExprSeq, MList, MSet, MString, MRange, Equation, ArrowFunction, Procedure, Builtin)):
        return to_text(v)
    try:
        return sp.pretty(v, use_unicode=True, wrap_line=False)
    except Exception:
        return to_text(v)


def needs_pretty(v) -> bool:
    """True if the value contains something simple math renderers can't typeset."""
    if isinstance(v, (sp.MatrixBase, sp.Piecewise)):
        return True
    if isinstance(v, (ExprSeq, MList, MSet)):
        return any(needs_pretty(x) for x in v)
    if isinstance(v, sp.Basic):
        return v.has(sp.Piecewise) or any(isinstance(a, sp.MatrixBase) for a in sp.preorder_traversal(v))
    return False


def _parts(v):
    """Split a value into typesetting parts so the UI can draw matrices itself.

    Returns None if the value has a matrix nested somewhere it can't lay out.
    """
    if isinstance(v, sp.MatrixBase):
        return [{"matrix": [[to_latex(v[i, j]) for j in range(v.cols)] for i in range(v.rows)]}]
    if isinstance(v, sp.Piecewise):
        rows = []
        for expr, cond in v.args:
            label = r"\mathrm{otherwise}" if cond is sp.true else r"\mathrm{if}\ " + to_latex(cond)
            rows.append([to_latex(expr), label])
        return [{"cases": rows}]
    if isinstance(v, sp.Equality) and (isinstance(v.rhs, sp.Piecewise) or isinstance(v.rhs, sp.MatrixBase)):
        lhs = _parts(v.lhs)
        rhs = _parts(v.rhs)
        if lhs is None or rhs is None:
            return None
        return lhs + [{"latex": "="}] + rhs
    if isinstance(v, ExprSeq):
        out = []
        for k, item in enumerate(v):
            sub = _parts(item)
            if sub is None:
                return None
            if k:
                out.append({"latex": ",", "sep": True})
            out.extend(sub)
        return out
    if needs_pretty(v):
        return None
    return [{"latex": to_latex(v)}]


def make_output(value, label: str | None = None) -> Output:
    if isinstance(value, PlotResult):
        return Output("plot", text=value.title or "plot", png=value.png)
    if isinstance(value, MString) and label is None:
        return Output("text", text=str(value))
    if isinstance(value, Procedure) or isinstance(value, ArrowFunction) and value.display is None:
        text = value.source
        return Output("text", text=f"{label} := {text}" if label else text,
                      meta={"monospace": True})
    display = value.display if isinstance(value, ArrowFunction) else value
    text = to_text(value)
    try:
        latex = to_latex(display)
    except Exception:
        latex = ""
    pretty = to_pretty(display)
    meta = {"prefer_pretty": needs_pretty(display)}
    if meta["prefer_pretty"]:
        parts = _parts(display)
        if parts is not None:
            meta["parts"] = parts
    if label:
        label_tex = _LATEX.doprint(sp.Symbol(label))
        text = f"{label} := {text}"
        latex = f"{label_tex} := {latex}" if latex else ""
        pretty = _prefix_pretty(f"{label} := ", pretty)
        if "parts" in meta:
            meta["parts"] = [{"latex": f"{label_tex} :="}] + meta["parts"]
    return Output("math", text=text, latex=latex, pretty=pretty, label=label or "", meta=meta)


def _hjoin(blocks: list[str], sep: str) -> str:
    """Place multi-line text blocks side by side, vertically centred."""
    split = [b.split("\n") for b in blocks]
    height = max(len(b) for b in split)
    cols = []
    for k, lines in enumerate(split):
        width = max(len(line) for line in lines)
        top = (height - len(lines)) // 2
        padded = [" " * width] * top + [line.ljust(width) for line in lines]
        padded += [" " * width] * (height - len(padded))
        if k:
            cols.append([(sep if i == height // 2 else " " * len(sep)) for i in range(height)])
        cols.append(padded)
    return "\n".join("".join(col[i] for col in cols).rstrip() for i in range(height))


def _prefix_pretty(prefix: str, block: str) -> str:
    lines = block.split("\n")
    mid = len(lines) // 2
    pad = " " * len(prefix)
    return "\n".join((prefix if i == mid else pad) + line for i, line in enumerate(lines))
