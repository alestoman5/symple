"""Implementations of the built-in functions listed in :mod:`symple.catalog`.

Every implementation has the signature ``fn(ev, *args)`` where ``ev`` is the
running :class:`~symple.engine.evaluator.Evaluator` and ``args`` are already
evaluated (sequences flattened). "Raw" built-ins such as ``seq`` receive the
unevaluated AST nodes instead, because they bind a loop variable themselves.
"""
from __future__ import annotations

import sympy as sp
from sympy.simplify.fu import TR8

from .values import (NULL, Builtin, EvalError, ExprFunction, ExprSeq, MList, MRange, MSet,
                     MString, eq_parts, is_callable)

BUILTINS: dict[str, Builtin] = {}


def builtin(name, raw=False):
    def deco(fn):
        BUILTINS[name] = Builtin(name, fn, raw)
        return fn
    return deco


# ------------------------------------------------------------------ helpers

def basic(v, where):
    if isinstance(v, bool):
        return sp.true if v else sp.false
    if isinstance(v, (sp.Basic, sp.MatrixBase)):
        return v
    if isinstance(v, MString):
        raise EvalError(f"expected an expression but received the string {str(v)!r}", where)
    raise EvalError(f"expected an expression but received {type(v).__name__}", where)


def symbol(v, where):
    if isinstance(v, (sp.Symbol, sp.core.function.AppliedUndef)):
        return v
    raise EvalError(f"expected a variable name but received {v}", where)


def as_sympy_eq(v):
    """Equation -> expr == 0 form usable by solvers."""
    parts = eq_parts(v)
    if parts:
        return sp.Eq(basic(parts[0], "solve"), basic(parts[1], "solve"))
    return v


def var_range(v, where):
    """Split 'x = a..b' into (x, a, b)."""
    parts = eq_parts(v)
    if not parts or not isinstance(parts[1], MRange):
        raise EvalError("expected a variable with a range, e.g. x = 0..1", where)
    return symbol(parts[0], where), basic(parts[1].lo, where), basic(parts[1].hi, where)


def items(v):
    """Elements of a list, set or sequence (or a single value)."""
    if isinstance(v, (MList, MSet, ExprSeq)):
        return list(v)
    if isinstance(v, sp.FiniteSet):
        return list(v.args)
    return [v]


def map_over(fn, v):
    """Apply *fn* inside containers, equations and matrices."""
    if isinstance(v, MList):
        return MList(map_over(fn, x) for x in v)
    if isinstance(v, MSet):
        return MSet(map_over(fn, x) for x in v)
    if isinstance(v, ExprSeq):
        return ExprSeq(map_over(fn, x) for x in v)
    if isinstance(v, sp.MatrixBase):
        return v.applyfunc(fn)
    if isinstance(v, sp.Equality):
        return sp.Eq(fn(v.lhs), fn(v.rhs), evaluate=False)
    return fn(v)


def to_int(v, where) -> int:
    v = basic(v, where)
    if v.is_Integer:
        return int(v)
    raise EvalError(f"expected an integer but received {v}", where)


def simple(name, sympy_fn, n=1):
    """Register a function that just maps its arguments onto a SymPy callable."""
    def fn(ev, *args):
        if len(args) != n:
            raise EvalError(f"expects {n} argument{'s' if n > 1 else ''}, got {len(args)}", name)
        return sympy_fn(*(basic(a, name) for a in args))
    BUILTINS[name] = Builtin(name, fn)


# ---------------------------------------------------------- elementary funcs

for _maple, _sym in {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sec": sp.sec, "csc": sp.csc, "cot": sp.cot,
    "arcsin": sp.asin, "arccos": sp.acos, "arcsec": sp.asec, "arccsc": sp.acsc, "arccot": sp.acot,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "sech": sp.sech, "csch": sp.csch,
    "coth": sp.coth, "arcsinh": sp.asinh, "arccosh": sp.acosh, "arctanh": sp.atanh,
    "exp": sp.exp, "ln": sp.log, "sqrt": sp.sqrt, "abs": sp.Abs, "signum": sp.sign,
    "floor": sp.floor, "ceil": sp.ceiling, "frac": sp.frac, "Re": sp.re, "Im": sp.im,
    "conjugate": sp.conjugate, "argument": sp.arg, "GAMMA": sp.gamma, "Zeta": sp.zeta,
    "erf": sp.erf, "Heaviside": sp.Heaviside, "Dirac": sp.DiracDelta,
    "factorial": sp.factorial, "isprime": lambda n: sp.true if sp.isprime(n) else sp.false,
    "ithprime": sp.prime, "nextprime": sp.nextprime, "log10": lambda x: sp.log(x, 10),
    "ifactor": lambda n: _ifactor(n),
}.items():
    simple(_maple, _sym)

for _maple, _sym in {"binomial": sp.binomial, "surd": sp.real_root, "root": sp.root,
                     "gcd": sp.gcd, "lcm": sp.lcm}.items():
    simple(_maple, _sym, 2)


def _ifactor(n):
    if not n.is_Integer:
        raise EvalError("expected an integer", "ifactor")
    factors = sp.factorint(n)
    if not factors or n in (0, 1, -1):
        return n
    terms = [sp.Pow(p, e, evaluate=False) if e > 1 else p for p, e in factors.items()]
    sign = [sp.Integer(-1)] if n < 0 else []
    return sp.Mul(*sign, *terms, evaluate=False)


@builtin("log")
def _log(ev, x, base=None):
    x = basic(x, "log")
    return sp.log(x) if base is None else sp.log(x, basic(base, "log"))


@builtin("arctan")
def _arctan(ev, y, x=None):
    return sp.atan(basic(y, "arctan")) if x is None else sp.atan2(basic(y, "arctan"), basic(x, "arctan"))


@builtin("round")
def _round(ev, x):
    x = basic(x, "round")
    if x.is_number:
        return sp.Integer(sp.floor(x + sp.Rational(1, 2)) if x >= 0 else -sp.floor(-x + sp.Rational(1, 2)))
    return sp.Function("round")(x)


@builtin("trunc")
def _trunc(ev, x):
    x = basic(x, "trunc")
    if x.is_number:
        return sp.sign(x) * sp.floor(abs(x))
    return sp.Function("trunc")(x)


@builtin("irem")
def _irem(ev, a, b):
    a, b = to_int(a, "irem"), to_int(b, "irem")
    if b == 0:
        raise EvalError("division by zero", "irem")
    return sp.Integer(a - b * int(a / b))


@builtin("iquo")
def _iquo(ev, a, b):
    a, b = to_int(a, "iquo"), to_int(b, "iquo")
    if b == 0:
        raise EvalError("division by zero", "iquo")
    return sp.Integer(int(a / b))


@builtin("max")
def _max(ev, *args):
    return sp.Max(*(basic(a, "max") for a in args))


@builtin("min")
def _min(ev, *args):
    return sp.Min(*(basic(a, "min") for a in args))


# ------------------------------------------------------------------ calculus

@builtin("diff")
def _diff(ev, f, *vars_):
    if not vars_:
        raise EvalError("no variable given", "diff")
    vs = [symbol(v, "diff") for v in vars_]
    return map_over(lambda e: sp.diff(basic(e, "diff"), *vs), f)


@builtin("int")
def _int(ev, f, v):
    f = basic(f, "int")
    parts = eq_parts(v)
    if parts:
        x, a, b = var_range(v, "int")
        return sp.integrate(f, (x, a, b))
    return sp.integrate(f, symbol(v, "int"))


@builtin("limit")
def _limit(ev, f, point, direction=None):
    f = basic(f, "limit")
    parts = eq_parts(point)
    if not parts:
        raise EvalError("expected x = a as the second argument", "limit")
    x, a = symbol(parts[0], "limit"), basic(parts[1], "limit")
    if direction is not None:
        d = str(direction)
        if d not in ("left", "right"):
            raise EvalError("direction must be left or right", "limit")
        return sp.limit(f, x, a, "-" if d == "left" else "+")
    if a.is_infinite:
        return sp.limit(f, x, a)
    return sp.limit(f, x, a, "+-")


def _series_args(where, f, point, n):
    f = basic(f, where)
    parts = eq_parts(point)
    if parts:
        x, a = symbol(parts[0], where), basic(parts[1], where)
    else:
        x, a = symbol(point, where), sp.Integer(0)
    order = to_int(n, where) if n is not None else 6
    return f, x, a, order


@builtin("series")
def _series(ev, f, point, n=None):
    f, x, a, order = _series_args("series", f, point, n)
    return sp.series(f, x, a, order)


@builtin("taylor")
def _taylor(ev, f, point, n=None):
    return _series(ev, f, point, n)


@builtin("sum")
def _sum(ev, f, v):
    x, a, b = var_range(v, "sum")
    return sp.summation(basic(f, "sum"), (x, a, b))


@builtin("product")
def _product(ev, f, v):
    x, a, b = var_range(v, "product")
    return sp.product(basic(f, "product"), (x, a, b))


@builtin("D")
def _D(ev, f):
    x = sp.Symbol("x")
    if isinstance(f, ExprFunction):
        if len(f.params) != 1:
            raise EvalError("only functions of one variable are supported", "D")
        return ExprFunction(f.params, sp.diff(f.expr, f.params[0]))
    if isinstance(f, sp.Symbol):  # D(y) for an unknown function y
        return ExprFunction((x,), sp.Derivative(sp.Function(f.name)(x), x))
    if is_callable(f) or isinstance(f, sp.FunctionClass):
        return ExprFunction((x,), sp.diff(basic(ev.apply(f, [x]), "D"), x))
    raise EvalError(f"expected a function but received {f}", "D")


@builtin("dsolve")
def _dsolve(ev, odes, funcs=None):
    eqs, ics = [], {}
    for item in items(odes):
        parts = eq_parts(item)
        lhs = parts[0] if parts else None
        if parts and _is_initial_condition(lhs):
            ics[lhs] = basic(parts[1], "dsolve")
        else:
            eqs.append(as_sympy_eq(item))
    fs = None
    if funcs is not None:
        fs = [symbol(f, "dsolve") for f in items(funcs)]
        fs = fs[0] if len(fs) == 1 else fs
    target = eqs[0] if len(eqs) == 1 else eqs
    sol = sp.dsolve(target, fs, ics=ics or None)
    if isinstance(sol, list):
        return MSet(sol) if len(eqs) > 1 else ExprSeq(sol)
    return sol


def _is_initial_condition(lhs) -> bool:
    """y(0) or D(y)(0) (which evaluates to a Subs of a Derivative)."""
    if isinstance(lhs, sp.core.function.AppliedUndef):
        return all(a.is_number for a in lhs.args)
    return isinstance(lhs, sp.Subs)


# ------------------------------------------------------------------- algebra

@builtin("simplify")
def _simplify(ev, e, how=None):
    if how is not None and str(how) == "trig":
        return map_over(sp.trigsimp, e)
    return map_over(lambda x: sp.simplify(basic(x, "simplify")), e)


@builtin("expand")
def _expand(ev, e):
    return map_over(lambda x: sp.expand(basic(x, "expand")), e)


@builtin("factor")
def _factor(ev, e, ext=None):
    if ext is not None:
        return map_over(lambda x: sp.factor(basic(x, "factor"), extension=ext), e)
    return map_over(lambda x: sp.factor(basic(x, "factor")), e)


@builtin("normal")
def _normal(ev, e):
    return map_over(lambda x: sp.cancel(sp.together(basic(x, "normal"))), e)


@builtin("collect")
def _collect(ev, e, x):
    return map_over(lambda t: sp.collect(sp.expand(basic(t, "collect")), x), e)


@builtin("combine")
def _combine(ev, e, how=None):
    def comb(x):
        x = basic(x, "combine")
        return TR8(sp.logcombine(sp.powsimp(x, combine="all"), force=True))
    return map_over(comb, e)


@builtin("numer")
def _numer(ev, e):
    return sp.fraction(sp.together(basic(e, "numer")))[0]


@builtin("denom")
def _denom(ev, e):
    return sp.fraction(sp.together(basic(e, "denom")))[1]


@builtin("coeff")
def _coeff(ev, p, x, n=None):
    p = sp.expand(basic(p, "coeff"))
    return p.coeff(basic(x, "coeff"), 1 if n is None else to_int(n, "coeff"))


@builtin("degree")
def _degree(ev, p, x=None):
    p = basic(p, "degree")
    if x is None:
        syms = sorted(p.free_symbols, key=str)
        return sp.Integer(sp.Poly(p, *syms).total_degree()) if syms else sp.Integer(0)
    return sp.degree(p, basic(x, "degree"))


@builtin("lhs")
def _lhs(ev, e):
    parts = eq_parts(e)
    if parts:
        return parts[0]
    if isinstance(e, MRange):
        return e.lo
    if isinstance(e, sp.core.relational.Relational):
        return e.lhs
    raise EvalError("expected an equation, inequality or range", "lhs")


@builtin("rhs")
def _rhs(ev, e):
    parts = eq_parts(e)
    if parts:
        return parts[1]
    if isinstance(e, MRange):
        return e.hi
    if isinstance(e, sp.core.relational.Relational):
        return e.rhs
    raise EvalError("expected an equation, inequality or range", "rhs")


def _substitutions(eqs, where):
    pairs = []
    for spec in eqs:
        for e in items(spec):
            parts = eq_parts(e)
            if not parts:
                raise EvalError(f"expected an equation like x = a, got {e}", where)
            pairs.append((basic(parts[0], where), basic(parts[1], where)))
    return pairs


@builtin("subs")
def _subs(ev, *args):
    *eqs, e = args
    pairs = _substitutions(eqs, "subs")
    return map_over(lambda x: basic(x, "subs").subs(pairs), e)


@builtin("eval")
def _eval(ev, e, at=None):
    if at is None:
        return e
    pairs = _substitutions([at], "eval")
    return map_over(lambda x: basic(x, "eval").subs(pairs).doit(), e)


@builtin("evalf")
def _evalf(ev, e, digits=None):
    n = to_int(digits, "evalf") if digits is not None else ev.session.digits
    return map_over(lambda x: basic(x, "evalf").evalf(n), e)


@builtin("evalb")
def _evalb(ev, rel):
    try:
        return sp.true if ev.truth(rel) else sp.false
    except EvalError:
        return sp.Symbol("FAIL")


@builtin("solve")
def _solve(ev, eqs, vars_=None):
    eq_list = [as_sympy_eq(e) for e in items(eqs)]
    set_form = isinstance(eqs, (MSet, MList)) or isinstance(vars_, (MSet, MList))
    if vars_ is None:
        syms = sorted(set().union(*(basic(e, "solve").free_symbols for e in eq_list)), key=str)
    else:
        syms = [symbol(v, "solve") for v in items(vars_)]
    if any(isinstance(e, sp.core.relational.Relational) and not isinstance(e, (sp.Eq, sp.Ne))
           for e in eq_list):
        return sp.reduce_inequalities(eq_list, syms)
    sols = sp.solve(eq_list if len(eq_list) > 1 else eq_list[0], syms, dict=True)
    if not set_form and len(syms) == 1:
        return ExprSeq(s[syms[0]] for s in sols if syms[0] in s)
    return ExprSeq(MSet(sp.Eq(k, v, evaluate=False) for k, v in s.items()) for s in sols)


@builtin("fsolve")
def _fsolve(ev, eq, var=None, rng=None):
    e = as_sympy_eq(eq)
    f = basic(e.lhs - e.rhs if isinstance(e, sp.Equality) else e, "fsolve")
    if var is None:
        syms = sorted(f.free_symbols, key=str)
        if len(syms) != 1:
            raise EvalError("specify the variable to solve for", "fsolve")
        var = syms[0]
    elif eq_parts(var):  # fsolve(f, x = a..b)
        var, lo, hi = var_range(var, "fsolve")
        rng = MRange(lo, hi)
    x = symbol(var, "fsolve")
    digits = ev.session.digits
    lo = hi = None
    if isinstance(rng, MRange):
        lo, hi = sp.N(rng.lo), sp.N(rng.hi)
    if f.is_polynomial(x):
        roots = [r for r in sp.Poly(f, x).nroots(n=digits) if r.is_real]
        if lo is not None:
            roots = [r for r in roots if lo <= r <= hi]
        return ExprSeq(sp.Float(r, digits) for r in sorted(roots))
    try:
        if lo is not None:
            try:
                return sp.nsolve(f, x, (lo, hi), solver="bisect", prec=digits)
            except Exception:
                return sp.nsolve(f, x, (lo + hi) / 2, prec=digits)
        return sp.nsolve(f, x, 0, prec=digits)
    except Exception:
        raise EvalError("no solution found; try giving a range, e.g. fsolve(f, x = 0..2)", "fsolve")


_CONVERSIONS = {
    "exp": lambda e, x: e.rewrite(sp.exp), "sin": lambda e, x: e.rewrite(sp.sin),
    "cos": lambda e, x: e.rewrite(sp.cos), "tan": lambda e, x: e.rewrite(sp.tan),
    "ln": lambda e, x: e.rewrite(sp.log), "sincos": lambda e, x: e.rewrite(sp.cos),
    "expln": lambda e, x: e.rewrite(sp.exp).rewrite(sp.log),
    "float": lambda e, x: e.evalf(), "rational": lambda e, x: sp.nsimplify(e, rational=True),
    "polynom": lambda e, x: e.removeO(), "radical": lambda e, x: e.rewrite(sp.sqrt),
    "parfrac": lambda e, x: sp.apart(e, x) if x is not None else sp.apart(e),
}


@builtin("convert")
def _convert(ev, e, form, x=None):
    form = str(form)
    if form == "list":
        if isinstance(e, sp.MatrixBase):
            return MList(e)
        return MList(items(e))
    if form == "set":
        return MSet(items(e))
    if form == "string":
        from .printing import to_text
        return MString(to_text(e))
    if form not in _CONVERSIONS:
        raise EvalError(f"unsupported conversion '{form}'; try one of: list, set, string, "
                        + ", ".join(sorted(_CONVERSIONS)), "convert")
    return map_over(lambda t: _CONVERSIONS[form](basic(t, "convert"), x), e)


@builtin("rem")
def _rem(ev, a, b, x):
    return sp.rem(basic(a, "rem"), basic(b, "rem"), symbol(x, "rem"))


@builtin("quo")
def _quo(ev, a, b, x):
    return sp.quo(basic(a, "quo"), basic(b, "quo"), symbol(x, "quo"))


@builtin("piecewise")
def _piecewise(ev, *args):
    pairs = []
    for i in range(0, len(args) - 1, 2):
        pairs.append((basic(args[i + 1], "piecewise"), basic(args[i], "piecewise")))
    if len(args) % 2:
        pairs.append((basic(args[-1], "piecewise"), sp.true))
    return sp.Piecewise(*pairs)


@builtin("unapply")
def _unapply(ev, e, *vars_):
    if not vars_:
        raise EvalError("no variable given", "unapply")
    return ExprFunction(tuple(symbol(v, "unapply") for v in vars_), basic(e, "unapply"))


# --------------------------------------------------------------- sequences

def _loop_values(ev, spec_node, where):
    """For seq/add/mul: parse 'i = a..b' (or 'i = list') and return (name, values)."""
    from ..lang import ast as A
    if isinstance(spec_node, A.BinOp) and spec_node.op == "=" and isinstance(spec_node.left, A.Name):
        name = spec_node.left.id
        target = ev.eval(spec_node.right)
        if isinstance(target, MRange):
            lo, hi = basic(target.lo, where), basic(target.hi, where)
            if not (lo.is_number and hi.is_number):
                raise EvalError("range bounds must be numbers; use sum/product for symbolic bounds", where)
            values, v = [], lo
            while v <= hi:
                values.append(v)
                v += 1
            return name, values
        return name, items(target)
    raise EvalError("expected a loop specification like i = 1..n", where)


def _loop(ev, expr_node, spec_node, where):
    name, values = _loop_values(ev, spec_node, where)
    out = []
    with ev.bind(name) as set_value:
        for v in values:
            set_value(v)
            out.append(ev.eval(expr_node))
    return out


@builtin("seq", raw=True)
def _seq(ev, *nodes):
    if len(nodes) == 1:  # seq(a..b)
        r = ev.eval(nodes[0])
        if isinstance(r, MRange):
            lo, hi = to_int(r.lo, "seq"), to_int(r.hi, "seq")
            return ExprSeq(sp.Integer(i) for i in range(lo, hi + 1))
        return ExprSeq(items(r))
    if len(nodes) != 2:
        raise EvalError("expected seq(expr, i = a..b)", "seq")
    return ExprSeq(ev.flatten(_loop(ev, nodes[0], nodes[1], "seq")))


@builtin("add", raw=True)
def _add(ev, *nodes):
    if len(nodes) != 2:
        raise EvalError("expected add(expr, i = a..b)", "add")
    return sp.Add(*(basic(v, "add") for v in _loop(ev, nodes[0], nodes[1], "add")))


@builtin("mul", raw=True)
def _mul(ev, *nodes):
    if len(nodes) != 2:
        raise EvalError("expected mul(expr, i = a..b)", "mul")
    return sp.Mul(*(basic(v, "mul") for v in _loop(ev, nodes[0], nodes[1], "mul")))


@builtin("map")
def _map(ev, f, container, *extra):
    apply = lambda x: ev.apply(f, [x, *extra])  # noqa: E731
    if isinstance(container, (MList, MSet, ExprSeq)):
        return type(container)(apply(x) for x in container)
    if isinstance(container, sp.MatrixBase):
        return container.applyfunc(apply)
    if isinstance(container, sp.Equality):
        return sp.Eq(apply(container.lhs), apply(container.rhs), evaluate=False)
    if isinstance(container, (sp.Add, sp.Mul)):
        return container.func(*(apply(a) for a in container.args))
    return apply(container)


def _operands(e) -> list:
    if isinstance(e, (MList, MSet, ExprSeq)):
        return list(e)
    if isinstance(e, sp.MatrixBase):
        return list(e)
    if isinstance(e, sp.Equality) or isinstance(e, MRange):
        return list(eq_parts(e) or (e.lo, e.hi))
    if isinstance(e, sp.Basic) and e.args and not e.is_Atom:
        if isinstance(e, sp.Rational) and not e.is_Integer:
            return [e.p, e.q]
        return list(e.args)
    return [e]


@builtin("nops")
def _nops(ev, e):
    return sp.Integer(len(_operands(e)))


@builtin("op")
def _op(ev, *args):
    if len(args) == 1:
        return ExprSeq(_operands(args[0]))
    i, e = args
    ops = _operands(e)
    if isinstance(i, MRange):
        lo, hi = to_int(i.lo, "op"), to_int(i.hi, "op")
        return ExprSeq(ops[lo - 1:hi])
    k = to_int(i, "op")
    if k == 0:
        return sp.Symbol(type(e).__name__)
    if not 1 <= abs(k) <= len(ops):
        raise EvalError(f"improper op or subscript selector: {k}", "op")
    return ops[k - 1] if k > 0 else ops[k]


@builtin("select")
def _select(ev, pred, container):
    return type(container)(x for x in items(container) if ev.truth(ev.apply(pred, [x])))


@builtin("remove")
def _remove(ev, pred, container):
    return type(container)(x for x in items(container) if not ev.truth(ev.apply(pred, [x])))


@builtin("sort")
def _sort(ev, e, order=None):
    if isinstance(e, (MList, ExprSeq)):
        return type(e)(sorted(e, key=sp.default_sort_key))
    return e


@builtin("member")
def _member(ev, x, container):
    return sp.true if any(x == y for y in items(container)) else sp.false


@builtin("indets")
def _indets(ev, e):
    return MSet(sorted(basic(e, "indets").free_symbols, key=str))


@builtin("has")
def _has(ev, e, x):
    return sp.true if basic(e, "has").has(basic(x, "has")) else sp.false


_TYPES = {
    "integer": lambda v: isinstance(v, sp.Integer),
    "posint": lambda v: isinstance(v, sp.Integer) and v > 0,
    "nonnegint": lambda v: isinstance(v, sp.Integer) and v >= 0,
    "even": lambda v: isinstance(v, sp.Integer) and v % 2 == 0,
    "odd": lambda v: isinstance(v, sp.Integer) and v % 2 == 1,
    "prime": lambda v: isinstance(v, sp.Integer) and sp.isprime(v),
    "rational": lambda v: isinstance(v, sp.Rational),
    "fraction": lambda v: isinstance(v, sp.Rational) and not v.is_Integer,
    "float": lambda v: isinstance(v, sp.Float),
    "numeric": lambda v: isinstance(v, (sp.Rational, sp.Float)),
    "complex": lambda v: isinstance(v, sp.Basic) and v.is_number,
    "positive": lambda v: isinstance(v, sp.Basic) and v.is_positive is True,
    "negative": lambda v: isinstance(v, sp.Basic) and v.is_negative is True,
    "list": lambda v: isinstance(v, MList),
    "set": lambda v: isinstance(v, MSet),
    "string": lambda v: isinstance(v, MString),
    "symbol": lambda v: isinstance(v, sp.Symbol),
    "name": lambda v: isinstance(v, sp.Symbol),
    "Matrix": lambda v: isinstance(v, sp.MatrixBase),
    "equation": lambda v: eq_parts(v) is not None,
    "range": lambda v: isinstance(v, MRange),
    "procedure": is_callable,
    "polynom": lambda v: isinstance(v, sp.Basic) and v.is_polynomial(),
    "boolean": lambda v: isinstance(v, (sp.logic.boolalg.Boolean, bool)),
}


@builtin("type")
def _type(ev, e, t):
    name = str(t)
    if name not in _TYPES:
        raise EvalError(f"unknown type '{name}'; known types: {', '.join(sorted(_TYPES))}", "type")
    return sp.true if _TYPES[name](e) else sp.false


# ----------------------------------------------------------- linear algebra

def matrix(v, where) -> sp.Matrix:
    if isinstance(v, sp.MatrixBase):
        return v
    raise EvalError(f"expected a Matrix or Vector but received {v}", where)


@builtin("Matrix")
def _Matrix(ev, *args):
    if len(args) == 1:
        rows = args[0]
        if isinstance(rows, MList) and rows and all(isinstance(r, MList) for r in rows):
            return sp.Matrix([[basic(x, "Matrix") for x in r] for r in rows])
        if isinstance(rows, MList):
            return sp.Matrix([[basic(x, "Matrix") for x in rows]])
        n = to_int(rows, "Matrix")
        return sp.zeros(n, n)
    m, n = to_int(args[0], "Matrix"), to_int(args[1], "Matrix")
    if len(args) == 2:
        return sp.zeros(m, n)
    f = args[2]
    if is_callable(f) or isinstance(f, sp.FunctionClass):
        return sp.Matrix(m, n, lambda i, j: ev.apply(f, [sp.Integer(i + 1), sp.Integer(j + 1)]))
    if isinstance(f, MList):
        return sp.Matrix(m, n, [basic(x, "Matrix") for r in f for x in items(r)])
    return sp.Matrix(m, n, lambda i, j: basic(f, "Matrix"))


@builtin("Vector")
def _Vector(ev, *args):
    if len(args) == 1 and isinstance(args[0], MList):
        return sp.Matrix([basic(x, "Vector") for x in args[0]])
    n = to_int(args[0], "Vector")
    if len(args) == 2 and (is_callable(args[1]) or isinstance(args[1], sp.FunctionClass)):
        return sp.Matrix([ev.apply(args[1], [sp.Integer(i + 1)]) for i in range(n)])
    return sp.zeros(n, 1)


def _la(name, fn):
    BUILTINS[name] = Builtin(name, lambda ev, a: fn(matrix(a, name)))


_la("Determinant", lambda A: A.det())
_la("MatrixInverse", lambda A: A.inv())
_la("Transpose", lambda A: A.T)
_la("Trace", lambda A: A.trace())
_la("Rank", lambda A: sp.Integer(A.rank()))
_la("ReducedRowEchelonForm", lambda A: A.rref()[0])
_la("NullSpace", lambda A: MSet(A.nullspace()))


@builtin("Eigenvalues")
def _eigenvalues(ev, A):
    vals = []
    for val, mult in matrix(A, "Eigenvalues").eigenvals().items():
        vals.extend([val] * mult)
    return sp.Matrix(vals)


@builtin("Eigenvectors")
def _eigenvectors(ev, A):
    vals, vecs = [], []
    for val, mult, basis in matrix(A, "Eigenvectors").eigenvects():
        for vec in basis:
            vals.append(val)
            vecs.append(vec)
    return ExprSeq([sp.Matrix(vals), sp.Matrix.hstack(*vecs)])


@builtin("CharacteristicPolynomial")
def _charpoly(ev, A, x):
    return matrix(A, "CharacteristicPolynomial").charpoly(symbol(x, "CharacteristicPolynomial")).as_expr()


@builtin("LinearSolve")
def _linsolve(ev, A, b):
    A, b = matrix(A, "LinearSolve"), matrix(b, "LinearSolve")
    try:
        sol, params = A.gauss_jordan_solve(b)
    except ValueError:
        raise EvalError("inconsistent system", "LinearSolve")
    return sol


@builtin("IdentityMatrix")
def _eye(ev, n):
    return sp.eye(to_int(n, "IdentityMatrix"))


@builtin("DotProduct")
def _dot(ev, u, v):
    return matrix(u, "DotProduct").dot(matrix(v, "DotProduct"))


@builtin("CrossProduct")
def _cross(ev, u, v):
    return matrix(u, "CrossProduct").cross(matrix(v, "CrossProduct"))


@builtin("Norm")
def _norm(ev, A, p=None):
    A = matrix(A, "Norm")
    if p is None or p == sp.oo:
        return A.norm(sp.oo)
    if str(p) == "Frobenius":
        return A.norm("fro")
    return A.norm(basic(p, "Norm"))


# ------------------------------------------------------------------- session

@builtin("with")
def _with(ev, pkg):
    from ..catalog import CATALOG
    name = str(pkg)
    if name == "LinearAlgebra":
        return MList(sp.Symbol(e.name) for e in CATALOG.values() if e.category == "Linear algebra")
    if name in ("plots", "Student", "student", "VectorCalculus", "plottools"):
        return NULL
    raise EvalError(f"package '{name}' is not available", "with")


@builtin("print")
def _print(ev, *args):
    ev.emit(ExprSeq(args) if len(args) != 1 else args[0])
    return NULL


@builtin("latex")
def _latex(ev, e):
    from .printing import to_latex
    return MString(to_latex(e))


@builtin("unassign")
def _unassign(ev, *names):
    for n in names:
        if not isinstance(n, sp.Symbol):
            raise EvalError("expected quoted names, e.g. unassign('x')", "unassign")
        ev.session.env.pop(n.name, None)
    return NULL


@builtin("restart")
def _restart(ev):
    ev.reset()
    return NULL


@builtin("plot")
def _plot(ev, *args):
    from .plotting import plot2d
    return plot2d(ev, args)


@builtin("plot3d")
def _plot3d(ev, *args):
    from .plotting import plot3d
    return plot3d(ev, args)
