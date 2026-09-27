"""plot / plot3d, rendered to PNG with Matplotlib's non-interactive Agg backend."""
from __future__ import annotations

import io
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import sympy as sp  # noqa: E402

from .builtins import basic, items  # noqa: E402
from .values import EvalError, MList, MRange, MString, PlotResult, eq_parts, is_callable  # noqa: E402

PALETTE = ["#c0392b", "#2463a6", "#1e8449", "#8e44ad", "#d68910", "#17a589"]
OPTIONS = {"color", "colour", "title", "labels", "thickness", "style", "numpoints",
           "legend", "view", "discont", "scaling", "gridlines", "axes", "linestyle"}


def _split_options(args):
    main, opts = [], {}
    for a in args:
        parts = eq_parts(a)
        if parts and isinstance(parts[0], sp.Symbol) and parts[0].name in OPTIONS:
            opts[parts[0].name] = parts[1]
        else:
            main.append(a)
    return main, opts


def _color(v, i):
    if v is None:
        return PALETTE[i % len(PALETTE)]
    if isinstance(v, MList):
        return _color(v[i % len(v)], i)
    name = str(v).lower()
    return {"navy": "navy", "gold": "gold"}.get(name, name)


def _numeric(fn_expr, var, xs):
    f = sp.lambdify(var, fn_expr, modules=["numpy"])
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            ys = np.asarray(f(xs), dtype=complex)
            if ys.shape != xs.shape:
                ys = np.full_like(xs, complex(ys), dtype=complex)
        except Exception:
            ys = np.array([_point(fn_expr, var, x) for x in xs], dtype=complex)
    real = ys.real.copy()
    real[np.abs(ys.imag) > 1e-9 * (1 + np.abs(ys.real))] = np.nan
    real[~np.isfinite(real)] = np.nan
    return real


def _point(expr, var, x):
    try:
        return complex(expr.subs(var, x).evalf())
    except Exception:
        return complex("nan")


def _robust_ylim(ys_all):
    finite = np.concatenate([y[np.isfinite(y)] for y in ys_all]) if ys_all else np.array([])
    if finite.size == 0:
        return None
    lo, hi = np.percentile(finite, [2, 98])
    span = hi - lo
    full_lo, full_hi = finite.min(), finite.max()
    if span == 0 or (full_hi - full_lo) <= 4 * span:  # no poles: show everything
        pad = 0.05 * ((full_hi - full_lo) or 1)
        return full_lo - pad, full_hi + pad
    return lo - 0.5 * span, hi + 0.5 * span


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _new_axes():
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, color="#e6e6e6", linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def plot2d(ev, args) -> PlotResult:
    main, opts = _split_options(args)
    if not main:
        raise EvalError("nothing to plot", "plot")
    what = main[0]
    rng = main[1] if len(main) > 1 else None
    n = int(basic(opts.get("numpoints", sp.Integer(500)), "plot"))

    curves = items(what) if isinstance(what, MList) else [what]
    # plot([x(t), y(t), t = a..b]) is a parametric curve
    parametric = isinstance(what, MList) and len(what) == 3 and eq_parts(what[2]) \
        and isinstance(eq_parts(what[2])[1], MRange)

    fig, ax = _new_axes()
    ys_all = []
    labels = opts.get("legend")
    try:
        if parametric:
            t, (lo, hi) = eq_parts(what[2])[0], (what[2].rhs.lo, what[2].rhs.hi)
            ts = np.linspace(float(lo), float(hi), n)
            xs, ys = _numeric(basic(what[0], "plot"), t, ts), _numeric(basic(what[1], "plot"), t, ts)
            ax.plot(xs, ys, color=_color(opts.get("color"), 0), linewidth=_thickness(opts))
            ax.set_aspect("equal", adjustable="datalim")
        else:
            var, lo, hi = _range(rng, curves)
            xs = np.linspace(lo, hi, n)
            for i, c in enumerate(curves):
                if is_callable(c) or isinstance(c, sp.FunctionClass):
                    expr = basic(ev.apply(c, [var]), "plot")
                else:
                    expr = basic(c, "plot")
                ys = _numeric(expr, var, xs)
                ys_all.append(ys)
                style = str(opts.get("style", "line"))
                label = str(labels[i]) if isinstance(labels, MList) and i < len(labels) else None
                if style == "point":
                    ax.plot(xs[::10], ys[::10], "o", markersize=3, color=_color(opts.get("color"), i), label=label)
                else:
                    ax.plot(xs, ys, color=_color(opts.get("color"), i), linewidth=_thickness(opts), label=label)
            ax.set_xlim(lo, hi)
            ylim = _robust_ylim(ys_all)
            if ylim and not np.isclose(*ylim):
                ax.set_ylim(*ylim)
            ax.set_xlabel(str(var))
        _decorate(ax, opts)
        if isinstance(labels, MList):
            ax.legend(frameon=False)
    except EvalError:
        plt.close(fig)
        raise
    except Exception as e:
        plt.close(fig)
        raise EvalError(f"could not plot: {e}", "plot") from None
    return PlotResult(_to_png(fig), title=str(opts.get("title", "")))


def _thickness(opts):
    return 1.0 + 0.6 * float(basic(opts.get("thickness", sp.Integer(1)), "plot"))


def _decorate(ax, opts):
    if "title" in opts:
        ax.set_title(str(opts["title"]))
    if isinstance(opts.get("labels"), MList) and len(opts["labels"]) == 2:
        ax.set_xlabel(str(opts["labels"][0]))
        ax.set_ylabel(str(opts["labels"][1]))
    view = opts.get("view")
    if isinstance(view, MList) and len(view) == 2 and all(isinstance(v, MRange) for v in view):
        ax.set_xlim(float(view[0].lo), float(view[0].hi))
        ax.set_ylim(float(view[1].lo), float(view[1].hi))
    elif isinstance(view, MRange):
        ax.set_ylim(float(view.lo), float(view.hi))
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.axvline(0, color="#999999", linewidth=0.8)


def _range(rng, curves):
    """(variable, lo, hi) from 'x = a..b', a bare range, or a default of -10..10."""
    if rng is None or isinstance(rng, MRange):
        free = set()
        for c in curves:
            if isinstance(c, sp.Basic):
                free |= c.free_symbols
        if len(free) > 1:
            raise EvalError("give the plotting variable, e.g. plot(f, x = -1..1)", "plot")
        var = free.pop() if free else sp.Symbol("x")
        lo, hi = (rng.lo, rng.hi) if rng is not None else (-10, 10)
    else:
        parts = eq_parts(rng)
        if not parts or not isinstance(parts[1], MRange):
            raise EvalError("expected a range like x = -1..1", "plot")
        var, lo, hi = parts[0], parts[1].lo, parts[1].hi
    try:
        lo, hi = float(sp.N(lo)), float(sp.N(hi))
    except TypeError:
        raise EvalError("range bounds must be numbers", "plot") from None
    if not lo < hi:
        raise EvalError("the range must go from a smaller to a larger value", "plot")
    return var, lo, hi


def plot3d(ev, args) -> PlotResult:
    main, opts = _split_options(args)
    if len(main) < 3:
        raise EvalError("expected plot3d(f, x = a..b, y = c..d)", "plot3d")
    f = basic(main[0], "plot3d")
    (x, xr), (y, yr) = eq_parts(main[1]) or (None, None), eq_parts(main[2]) or (None, None)
    if not (isinstance(xr, MRange) and isinstance(yr, MRange)):
        raise EvalError("expected ranges like x = -1..1, y = -1..1", "plot3d")
    n = 60
    xs = np.linspace(float(sp.N(xr.lo)), float(sp.N(xr.hi)), n)
    ys = np.linspace(float(sp.N(yr.lo)), float(sp.N(yr.hi)), n)
    X, Y = np.meshgrid(xs, ys)
    fn = sp.lambdify((x, y), f, modules=["numpy"])
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            Z = np.asarray(fn(X, Y), dtype=complex)
            if Z.shape != X.shape:
                Z = np.full_like(X, complex(Z), dtype=complex)
        except Exception as e:
            raise EvalError(f"could not evaluate the function: {e}", "plot3d") from None
    Zr = Z.real.copy()
    Zr[np.abs(Z.imag) > 1e-9] = np.nan
    fig = plt.figure(figsize=(6.2, 4.6))
    ax = fig.add_subplot(projection="3d")
    ax.plot_surface(X, Y, Zr, cmap="viridis", linewidth=0, antialiased=True, alpha=0.95)
    ax.set_xlabel(str(x))
    ax.set_ylabel(str(y))
    if "title" in opts:
        ax.set_title(str(opts["title"]))
    return PlotResult(_to_png(fig), title=str(opts.get("title", "")))


