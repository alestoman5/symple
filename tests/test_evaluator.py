import pytest

from symple.engine.evaluator import Evaluator


@pytest.fixture
def ev():
    return Evaluator()


def run(ev, src):
    """Texts of all outputs; errors are prefixed with 'Error'."""
    return [o.text for o in ev.run(src)]


def last(ev, src):
    outs = ev.run(src)
    assert outs, "no output"
    assert outs[-1].kind != "error", outs[-1].text
    return outs[-1].text


# ------------------------------------------------------------------ basics

def test_arithmetic_is_exact(ev):
    assert last(ev, "1/3 + 1/6;") == "1/2"
    assert last(ev, "2^100;") == str(2 ** 100)
    assert last(ev, "sqrt(8);") == "2*sqrt(2)"


def test_floats_and_digits(ev):
    assert last(ev, "evalf(Pi);") == "3.141592654"
    assert last(ev, "evalf(Pi, 20);") == "3.1415926535897932385"
    assert last(ev, "Digits := 5: evalf(1/3);") == "0.33333"
    assert last(ev, "evalf[3](Pi);") == "3.14"


def test_colon_suppresses_output(ev):
    assert run(ev, "a := 5: a + 1;") == ["6"]


def test_assignment_display_and_full_evaluation(ev):
    assert run(ev, "a := b + 1;") == ["a := b + 1"]
    assert last(ev, "b := 2: a;") == "3"


def test_unassign_with_quotes(ev):
    run(ev, "x := 5:")
    assert last(ev, "x := 'x': x^2;") == "x^2"


def test_recursive_assignment_is_an_error(ev):
    assert run(ev, "y := y + 1;")[0].startswith("Error, recursive assignment")


def test_ditto(ev):
    assert last(ev, "x^2: diff(%, x);") == "2*x"
    assert last(ev, "10; 20; %% + %;") == "30"


def test_protected(ev):
    assert run(ev, "Pi := 3;")[0].startswith("Error")


def test_error_stops_execution(ev):
    outs = ev.run("1/0; 5;")
    assert len(outs) == 1 and outs[0].kind == "error" and "division by zero" in outs[0].text


def test_syntax_error_reports_and_runs_nothing(ev):
    outs = ev.run("a := 1; diff(x^2, x")
    assert outs[0].kind == "error" and "unclosed '('" in outs[0].text
    assert "a" not in ev.session.env


# ---------------------------------------------------------------- calculus

def test_diff(ev):
    assert last(ev, "diff(sin(x), x);") == "cos(x)"
    assert last(ev, "diff(x^4, x$2);") == "12*x^2"
    assert last(ev, "diff(x^2*y^3, x, y);") == "6*x*y^2"


def test_int(ev):
    assert last(ev, "int(x^2, x);") == "x^3/3"
    assert last(ev, "int(x^2, x = 0..1);") == "1/3"
    assert last(ev, "int(exp(-x^2), x = -infinity..infinity);") == "sqrt(Pi)"


def test_limit_series_sum(ev):
    assert last(ev, "limit(sin(x)/x, x = 0);") == "1"
    assert last(ev, "limit(1/x, x = 0, right);") == "infinity"
    assert last(ev, "sum(k, k = 1..n);").replace(" ", "") in ("n^2/2+n/2", "n*(n+1)/2")
    assert last(ev, "sum(1/k^2, k = 1..infinity);") == "Pi^2/6"
    assert "O(x^4)" in last(ev, "series(exp(x), x = 0, 4);")


def test_dsolve(ev):
    out = last(ev, "dsolve(diff(y(x), x) = y(x), y(x));")
    assert out.replace(" ", "") == "Eq(y(x),C1*exp(x))" or out.replace(" ", "") == "y(x)=C1*exp(x)"
    out = last(ev, "dsolve({diff(y(x), x, x) + y(x) = 0, y(0) = 0, D(y)(0) = 1}, y(x));")
    assert out.replace(" ", "") == "y(x)=sin(x)"


def test_D_operator(ev):
    assert last(ev, "f := x -> x^3: D(f)(2);") == "12"
    assert last(ev, "D(sin);") == "x -> cos(x)"


# ----------------------------------------------------------------- algebra

def test_solve(ev):
    assert set(last(ev, "solve(x^2 = 4, x);").split(", ")) == {"-2", "2"}
    assert last(ev, "solve({x + y = 3, x - y = 1}, {x, y});") in ("{x = 2, y = 1}", "{y = 1, x = 2}")
    assert last(ev, "solve(x^2 + 1, x);") in ("-I, I", "I, -I")


def test_fsolve(ev):
    assert last(ev, "fsolve(x^2 = 2, x = 0..2);") == "1.414213562"
    assert last(ev, "fsolve(cos(x) = x, x);") == "0.7390851332"


def test_simplification_family(ev):
    assert last(ev, "simplify(sin(x)^2 + cos(x)^2);") == "1"
    assert last(ev, "expand((x + 1)^2);") == "x^2 + 2*x + 1"
    assert last(ev, "factor(x^2 - 1);") == "(x - 1)*(x + 1)"
    assert last(ev, "normal(1/x + 1/y);") == "(x + y)/(x*y)"
    assert last(ev, "convert(1/(x^2 - 1), parfrac, x);") in ("-1/(2*(x + 1)) + 1/(2*(x - 1))",
                                                             "1/(2*(x - 1)) - 1/(2*(x + 1))")


def test_subs_eval_lhs_rhs(ev):
    assert last(ev, "subs(x = 2, x^2 + 1);") == "5"
    assert last(ev, "eval(x^2 + y, {x = 1, y = 2});") == "3"
    assert last(ev, "eq := a = b + 1: rhs(eq);") == "b + 1"


def test_equation_arithmetic(ev):
    assert last(ev, "(2*x = 4)/2;") == "x = 2"


def test_ifactor_and_number_theory(ev):
    assert last(ev, "ifactor(360);") in ("2^3*3^2*5",)
    assert last(ev, "isprime(97);") == "true"
    assert last(ev, "irem(-7, 3);") == "-1"
    assert last(ev, "5!;") == "120"


# ------------------------------------------------------ functions & procs

def test_arrow_functions(ev):
    assert run(ev, "f := x -> x^2 + 1;") == ["f := x -> x^2 + 1"]
    assert last(ev, "f(3);") == "10"
    assert last(ev, "g := (a, b) -> a*b: g(2, 5);") == "10"
    assert last(ev, "f(t);") == "t^2 + 1"


def test_closures(ev):
    assert last(ev, "adder := n -> (x -> x + n): add3 := adder(3): add3(4);") == "7"


def test_unapply(ev):
    assert last(ev, "h := unapply(x^2 + y, x): h(3);") == "y + 9"


def test_procedures_and_recursion(ev):
    run(ev, "fact := proc(n) if n <= 1 then 1 else n*fact(n - 1) end if end proc:")
    assert last(ev, "fact(20);") == "2432902008176640000"


def test_proc_locals_do_not_leak(ev):
    run(ev, "p := proc(n) local i, s; s := 0; for i to n do s := s + i end do; s end proc:")
    assert last(ev, "p(10);") == "55"
    assert "s" not in ev.session.env and "i" not in ev.session.env


def test_return(ev):
    run(ev, "sgn := proc(x) if x < 0 then return -1 end if; 1 end proc:")
    assert last(ev, "sgn(-5), sgn(3);") == "-1, 1"


def test_undefined_function_stays_symbolic(ev):
    assert last(ev, "g(x) + 1;") == "g(x) + 1"


# ------------------------------------------------------------ control flow

def test_for_loop_displays_inner_results(ev):
    assert run(ev, "for i to 3 do i^2 end do;") == ["1", "4", "9"]
    assert run(ev, "for i to 3 do i^2 end do:") == []


def test_for_loop_variants(ev):
    assert last(ev, "s := 0: for i from 10 to 1 by -3 do s := s + i end do: s;") == "22"
    assert last(ev, "s := 0: for e in [1, 2, 3] do s := s + e end do: s;") == "6"
    assert last(ev, "n := 100: c := 0: while n > 1 do n := n/2; c := c + 1 end do: c;") == "7"
    assert last(ev, "for i do if i^2 > 50 then break end if end do: i;") == "8"
    assert last(ev, "s := 0: for i to 10 do if i mod 2 = 0 then next end if; s := s + i end do: s;") == "25"


def test_if_with_symbolic_condition_errors(ev):
    assert run(ev, "if z > 0 then 1 end if;")[0].startswith("Error, cannot determine")


def test_booleans(ev):
    assert last(ev, "evalb(1 < 2);") == "true"
    assert last(ev, "evalb(x = x);") == "true"
    assert last(ev, "is_ok := 2 > 1 and not 3 < 1: is_ok;") == "true"


# ---------------------------------------------------------- data structures

def test_lists_sets_seq(ev):
    assert last(ev, "L := [seq(i^2, i = 1..5)]: L[2], L[-1], nops(L);") == "4, 25, 5"
    assert last(ev, "L[2..3];") == "[4, 9]"
    assert last(ev, "{3, 1, 3, 2};") == "{3, 1, 2}"
    assert last(ev, "{1, 2} union {2, 3};") == "{1, 2, 3}"
    assert last(ev, "{1, 2, 3} minus {2};") == "{1, 3}"
    assert last(ev, "map(x -> x + 1, [1, 2]);") == "[2, 3]"
    assert last(ev, "select(isprime, [seq(i, i = 1..10)]);") == "[2, 3, 5, 7]"
    assert last(ev, "add(i, i = 1..100);") == "5050"
    assert last(ev, "op(2, [a, b, c]);") == "b"
    assert last(ev, "x$3;") == "x, x, x"


def test_indexed_names(ev):
    assert last(ev, "a[1] := 5: a[1] + a[2];") == "a_2 + 5"


# ---------------------------------------------------------- linear algebra

def test_matrices(ev):
    run(ev, "A := Matrix([[1, 2], [3, 4]]):")
    assert last(ev, "Determinant(A);") == "-2"
    assert last(ev, "A[2, 1];") == "3"
    assert last(ev, "MatrixInverse(A);") == "Matrix([[-2, 1], [3/2, -1/2]])"
    assert last(ev, "A . A;") == "Matrix([[7, 10], [15, 22]])"
    assert last(ev, "Transpose(Vector([1, 2]));") == "Matrix([[1, 2]])"
    assert last(ev, "LinearSolve(A, Vector([5, 11]));") == "Matrix([[1], [2]])"
    assert last(ev, "A[1, 1] := 10: A;") == "Matrix([[10, 2], [3, 4]])"
    assert "Matrix([[1, 0], [0, 1]])" == last(ev, "IdentityMatrix(2);")


def test_with_linear_algebra_lists_names(ev):
    assert "Determinant" in last(ev, "with(LinearAlgebra);")


# ------------------------------------------------------------ output forms

def test_latex_and_pretty_are_provided(ev):
    out = ev.run("int(1/x, x);")[0]
    assert out.kind == "math" and r"\ln" in out.latex and out.pretty
    out = ev.run("Matrix([[1, 2], [3, 4]]);")[0]
    assert out.meta["prefer_pretty"]


def test_arrow_display_is_not_evaluated(ev):
    out = ev.run("f := x -> diff(x^2, x);")[0]
    assert r"\mapsto" in out.latex and "diff" in out.latex


def test_print_and_strings(ev):
    outs = ev.run('print("hello", 1 + 1): "done";')
    assert [o.text for o in outs] == ['"hello", 2', "done"]


def test_plot_returns_png(ev):
    out = ev.run("plot(sin(x), x = 0..2*Pi);")[0]
    assert out.kind == "plot" and out.png.startswith(b"\x89PNG")
    out = ev.run("plot([sin(x), cos(x)], x = -Pi..Pi, color = [red, blue]);")[0]
    assert out.kind == "plot"
    out = ev.run("plot([cos(t), sin(t), t = 0..2*Pi]);")[0]
    assert out.kind == "plot"
    out = ev.run("plot3d(x^2 - y^2, x = -1..1, y = -1..1);")[0]
    assert out.kind == "plot"


def test_restart(ev):
    run(ev, "a := 1:")
    run(ev, "restart;")
    assert last(ev, "a;") == "a"


def test_no_python_escape(ev):
    # names are only looked up in the allow-list; nothing reaches Python
    assert last(ev, "__import__(os);") == "__import__(os)"
    assert last(ev, "eval(system);") == "system"
