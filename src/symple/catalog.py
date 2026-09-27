"""Catalog of built-in names: signatures and short descriptions.

This module is pure data (no SymPy import). The diagnostics use it to check calls,
and the editor uses it for autocompletion. The engine
(:mod:`symple.engine.builtins`) provides one implementation per function entry.

All descriptions here are original text written for Symple.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Entry:
    name: str
    signature: str
    doc: str
    category: str
    min_args: int = 0
    max_args: int | None = None   # None = unlimited
    kind: str = "function"        # "function" or "constant"


def _f(name, signature, doc, category, min_args=1, max_args=1):
    return Entry(name, signature, doc, category, min_args, max_args)


def _c(name, doc):
    return Entry(name, name, doc, "Constants", 0, 0, "constant")


_ENTRIES = [
    # --- Calculus
    _f("diff", "diff(expr, x, ...)", "Derivative of expr with respect to x; repeat variables or use x$n for higher order.", "Calculus", 2, None),
    _f("int", "int(expr, x)  |  int(expr, x = a..b)", "Indefinite integral, or definite integral over a..b.", "Calculus", 2, 2),
    _f("limit", "limit(expr, x = a [, left|right])", "Limit of expr as x approaches a.", "Calculus", 2, 3),
    _f("series", "series(expr, x = a [, n])", "Power-series expansion about a up to order n (default 6).", "Calculus", 2, 3),
    _f("taylor", "taylor(expr, x = a [, n])", "Taylor expansion about a up to order n (default 6).", "Calculus", 2, 3),
    _f("sum", "sum(expr, k = a..b)", "Symbolic sum of expr for k from a to b.", "Calculus", 2, 2),
    _f("product", "product(expr, k = a..b)", "Symbolic product of expr for k from a to b.", "Calculus", 2, 2),
    _f("add", "add(expr, k = a..b)", "Adds the terms expr for integer k from a to b (explicit loop).", "Calculus", 2, 2),
    _f("mul", "mul(expr, k = a..b)", "Multiplies the terms expr for integer k from a to b (explicit loop).", "Calculus", 2, 2),
    _f("D", "D(f)", "Derivative operator applied to a function f.", "Calculus", 1, 1),
    _f("dsolve", "dsolve(ode [, y(x)])", "Solves an ordinary differential equation (or a set with initial conditions).", "Calculus", 1, 2),
    # --- Algebra & simplification
    _f("simplify", "simplify(expr)", "Tries to find a simpler equivalent form of expr.", "Algebra", 1, 2),
    _f("expand", "expand(expr)", "Multiplies out products and powers.", "Algebra", 1, 1),
    _f("factor", "factor(expr)", "Factors a polynomial or rational expression.", "Algebra", 1, 2),
    _f("normal", "normal(expr)", "Puts a rational expression over a common denominator, cancelling common factors.", "Algebra", 1, 1),
    _f("collect", "collect(expr, x)", "Groups the terms of expr by powers of x.", "Algebra", 2, 2),
    _f("combine", "combine(expr)", "Combines powers, logarithms and trigonometric terms into fewer terms.", "Algebra", 1, 2),
    _f("numer", "numer(expr)", "Numerator of a rational expression.", "Algebra", 1, 1),
    _f("denom", "denom(expr)", "Denominator of a rational expression.", "Algebra", 1, 1),
    _f("coeff", "coeff(p, x [, n])", "Coefficient of x^n (default n = 1) in polynomial p.", "Algebra", 2, 3),
    _f("degree", "degree(p [, x])", "Degree of polynomial p.", "Algebra", 1, 2),
    _f("lhs", "lhs(eq)", "Left-hand side of an equation or range.", "Algebra", 1, 1),
    _f("rhs", "rhs(eq)", "Right-hand side of an equation or range.", "Algebra", 1, 1),
    _f("subs", "subs(x = a, expr)", "Substitutes a for x in expr (several substitutions allowed).", "Algebra", 2, None),
    _f("eval", "eval(expr [, x = a])", "Evaluates expr, optionally at the point x = a.", "Algebra", 1, 2),
    _f("evalf", "evalf(expr [, digits])", "Numerical (floating-point) value of expr.", "Algebra", 1, 2),
    _f("evalb", "evalb(relation)", "Evaluates a relation to true or false.", "Algebra", 1, 1),
    _f("solve", "solve(eqs [, vars])", "Solves an equation or a set of equations exactly.", "Algebra", 1, 2),
    _f("fsolve", "fsolve(eq [, x [, a..b]])", "Finds a numerical solution of an equation.", "Algebra", 1, 3),
    _f("convert", "convert(expr, form [, x])", "Rewrites expr in another form: parfrac, exp, sin, cos, tan, list, set, float, rational.", "Algebra", 2, 3),
    _f("gcd", "gcd(a, b)", "Greatest common divisor of integers or polynomials.", "Algebra", 2, 2),
    _f("lcm", "lcm(a, b)", "Least common multiple of integers or polynomials.", "Algebra", 2, 2),
    _f("rem", "rem(a, b, x)", "Remainder of polynomial division of a by b.", "Algebra", 3, 3),
    _f("quo", "quo(a, b, x)", "Quotient of polynomial division of a by b.", "Algebra", 3, 3),
    _f("piecewise", "piecewise(cond1, val1, ..., [otherwise])", "A function defined by cases.", "Algebra", 1, None),
    # --- Number theory
    _f("ifactor", "ifactor(n)", "Prime factorisation of the integer n.", "Number theory", 1, 1),
    _f("isprime", "isprime(n)", "true if n is a prime number.", "Number theory", 1, 1),
    _f("ithprime", "ithprime(i)", "The i-th prime number.", "Number theory", 1, 1),
    _f("nextprime", "nextprime(n)", "Smallest prime larger than n.", "Number theory", 1, 1),
    _f("binomial", "binomial(n, k)", "Binomial coefficient n choose k.", "Number theory", 2, 2),
    _f("factorial", "factorial(n)", "n! = 1*2*...*n.", "Number theory", 1, 1),
    _f("irem", "irem(a, b)", "Integer remainder of a divided by b.", "Number theory", 2, 2),
    _f("iquo", "iquo(a, b)", "Integer quotient of a divided by b.", "Number theory", 2, 2),
    # --- Elementary functions
    _f("sqrt", "sqrt(x)", "Square root.", "Functions"),
    _f("surd", "surd(x, n)", "Real n-th root of x.", "Functions", 2, 2),
    _f("root", "root(x, n)", "Principal n-th root of x.", "Functions", 2, 2),
    _f("exp", "exp(x)", "Exponential function e^x.", "Functions"),
    _f("ln", "ln(x)", "Natural logarithm.", "Functions"),
    _f("log", "log(x)  |  log[b](x)", "Natural logarithm, or logarithm to base b.", "Functions", 1, 2),
    _f("log10", "log10(x)", "Base-10 logarithm.", "Functions"),
    _f("abs", "abs(x)", "Absolute value.", "Functions"),
    _f("signum", "signum(x)", "Sign of x: -1, 0 or 1.", "Functions"),
    _f("floor", "floor(x)", "Largest integer not greater than x.", "Functions"),
    _f("ceil", "ceil(x)", "Smallest integer not less than x.", "Functions"),
    _f("round", "round(x)", "Nearest integer to x.", "Functions"),
    _f("trunc", "trunc(x)", "Integer part of x (rounds toward zero).", "Functions"),
    _f("frac", "frac(x)", "Fractional part of x.", "Functions"),
    _f("max", "max(a, b, ...)", "Largest of the arguments.", "Functions", 1, None),
    _f("min", "min(a, b, ...)", "Smallest of the arguments.", "Functions", 1, None),
    _f("Re", "Re(z)", "Real part of a complex number.", "Functions"),
    _f("Im", "Im(z)", "Imaginary part of a complex number.", "Functions"),
    _f("conjugate", "conjugate(z)", "Complex conjugate.", "Functions"),
    _f("argument", "argument(z)", "Argument (angle) of a complex number.", "Functions"),
    _f("GAMMA", "GAMMA(x)", "The gamma function; GAMMA(n) = (n-1)! for positive integers.", "Functions"),
    _f("Zeta", "Zeta(s)", "The Riemann zeta function.", "Functions"),
    _f("erf", "erf(x)", "The error function.", "Functions"),
    _f("Heaviside", "Heaviside(x)", "Unit step function.", "Functions"),
    _f("Dirac", "Dirac(x)", "Dirac delta distribution.", "Functions"),
    *[_f(n, f"{n}(x)", d, "Trigonometric") for n, d in [
        ("sin", "Sine (radians)."), ("cos", "Cosine (radians)."), ("tan", "Tangent (radians)."),
        ("sec", "Secant."), ("csc", "Cosecant."), ("cot", "Cotangent."),
        ("arcsin", "Inverse sine."), ("arccos", "Inverse cosine."),
        ("arcsec", "Inverse secant."), ("arccsc", "Inverse cosecant."), ("arccot", "Inverse cotangent."),
        ("sinh", "Hyperbolic sine."), ("cosh", "Hyperbolic cosine."), ("tanh", "Hyperbolic tangent."),
        ("sech", "Hyperbolic secant."), ("csch", "Hyperbolic cosecant."), ("coth", "Hyperbolic cotangent."),
        ("arcsinh", "Inverse hyperbolic sine."), ("arccosh", "Inverse hyperbolic cosine."),
        ("arctanh", "Inverse hyperbolic tangent."),
    ]],
    _f("arctan", "arctan(x)  |  arctan(y, x)", "Inverse tangent; the two-argument form gives the angle of the point (x, y).", "Trigonometric", 1, 2),
    # --- Lists, sets, sequences
    _f("seq", "seq(expr, i = a..b)", "Sequence of expr for i from a to b.", "Data", 1, 2),
    _f("map", "map(f, container)", "Applies f to every element of a list, set or matrix.", "Data", 2, None),
    _f("nops", "nops(expr)", "Number of operands (e.g. elements of a list).", "Data", 1, 1),
    _f("op", "op(expr)  |  op(i, expr)", "Operands of expr, or the i-th operand.", "Data", 1, 2),
    _f("select", "select(pred, list)", "Elements of list for which pred returns true.", "Data", 2, 2),
    _f("remove", "remove(pred, list)", "Elements of list for which pred returns false.", "Data", 2, 2),
    _f("sort", "sort(list)", "Sorts a list (or the terms of a polynomial).", "Data", 1, 2),
    _f("member", "member(x, container)", "true if x is an element of the list or set.", "Data", 2, 2),
    _f("indets", "indets(expr)", "Set of the unknowns (symbols) in expr.", "Data", 1, 1),
    _f("has", "has(expr, x)", "true if x occurs anywhere in expr.", "Data", 2, 2),
    _f("type", "type(expr, t)", "Checks the type of expr: integer, rational, float, numeric, list, set, symbol, polynom ...", "Data", 2, 2),
    # --- Linear algebra
    _f("Matrix", "Matrix([[a, b], [c, d]])  |  Matrix(m, n [, f])", "Creates a matrix from a list of rows, or of size m x n.", "Linear algebra", 1, 3),
    _f("Vector", "Vector([a, b, c])", "Creates a column vector.", "Linear algebra", 1, 2),
    _f("Determinant", "Determinant(A)", "Determinant of a square matrix.", "Linear algebra"),
    _f("MatrixInverse", "MatrixInverse(A)", "Inverse of a square matrix.", "Linear algebra"),
    _f("Transpose", "Transpose(A)", "Transpose of a matrix.", "Linear algebra"),
    _f("Trace", "Trace(A)", "Sum of the diagonal entries.", "Linear algebra"),
    _f("Rank", "Rank(A)", "Rank of a matrix.", "Linear algebra"),
    _f("Eigenvalues", "Eigenvalues(A)", "Eigenvalues of a square matrix.", "Linear algebra"),
    _f("Eigenvectors", "Eigenvectors(A)", "Eigenvalues together with their eigenvectors.", "Linear algebra"),
    _f("CharacteristicPolynomial", "CharacteristicPolynomial(A, x)", "Characteristic polynomial det(x*I - A).", "Linear algebra", 2, 2),
    _f("NullSpace", "NullSpace(A)", "Basis of the null space (kernel).", "Linear algebra"),
    _f("LinearSolve", "LinearSolve(A, b)", "Solves the linear system A.x = b.", "Linear algebra", 2, 2),
    _f("ReducedRowEchelonForm", "ReducedRowEchelonForm(A)", "Reduced row echelon form of A.", "Linear algebra"),
    _f("IdentityMatrix", "IdentityMatrix(n)", "n x n identity matrix.", "Linear algebra"),
    _f("DotProduct", "DotProduct(u, v)", "Dot product of two vectors.", "Linear algebra", 2, 2),
    _f("CrossProduct", "CrossProduct(u, v)", "Cross product of two 3-vectors.", "Linear algebra", 2, 2),
    _f("Norm", "Norm(v [, p])", "Norm of a vector or matrix (default 2-norm... Frobenius for matrices).", "Linear algebra", 1, 2),
    # --- Plotting
    _f("plot", "plot(f, x = a..b)  |  plot([f, g], x = a..b)", "2-D plot of one or more expressions.", "Plotting", 1, None),
    _f("plot3d", "plot3d(f, x = a..b, y = c..d)", "3-D surface plot.", "Plotting", 3, None),
    # --- Session
    _f("with", "with(package)", "Loads a package. All packages are always available in Symple; this is accepted for compatibility.", "Session", 1, 1),
    _f("restart", "restart", "Clears all variables and definitions.", "Session", 0, 0),
    _f("unassign", "unassign('x', ...)", "Removes the value of one or more variables.", "Session", 1, None),
    _f("print", "print(expr, ...)", "Displays the arguments.", "Session", 0, None),
    _f("latex", "latex(expr)", "LaTeX source for expr.", "Session", 1, 1),
    # --- Constants
    _c("Pi", "The circle constant 3.14159..."),
    _c("I", "The imaginary unit, I^2 = -1."),
    _c("infinity", "Positive infinity (use -infinity for negative)."),
    _c("true", "Boolean true."),
    _c("false", "Boolean false."),
    _c("gamma", "Euler's constant 0.57721..."),
    _c("Digits", "Number of significant digits used by evalf (default 10)."),
]

CATALOG: dict[str, Entry] = {e.name: e for e in _ENTRIES}

# Names the user may not assign to.
PROTECTED = frozenset(name for name in CATALOG if name != "Digits")


def functions() -> list[Entry]:
    return [e for e in _ENTRIES if e.kind == "function"]
