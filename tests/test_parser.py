import pytest

from symple.lang import ast as A
from symple.lang.parser import parse


def one(src):
    res = parse(src)
    assert res.ok, [d.message for d in res.diagnostics]
    assert len(res.statements) == 1
    return res.statements[0]


def expr(src):
    stmt = one(src)
    assert isinstance(stmt, A.ExprStmt)
    return stmt.expr


def errors(src):
    return [d.message for d in parse(src).diagnostics if d.severity == "error"]


def test_precedence_power_binds_tighter_than_unary_minus():
    e = expr("-x^2;")
    assert isinstance(e, A.UnOp) and e.op == "-"
    assert isinstance(e.operand, A.BinOp) and e.operand.op == "^"


def test_power_is_right_associative_and_allows_negative_exponent():
    e = expr("2^-1;")
    assert e.op == "^" and isinstance(e.right, A.UnOp)
    e = expr("a^b^c;")
    assert e.right.op == "^"


def test_sum_and_product():
    e = expr("a + b*c - d;")
    assert e.op == "-" and e.left.op == "+" and e.left.right.op == "*"


def test_terminators():
    res = parse("a; b: c")
    assert [s.show for s in res.statements] == [True, False, True]
    assert res.statements[2].terminated is False
    assert res.ok


def test_assignment_and_multiple_assignment():
    s = one("a, b := 1, 2;")
    assert isinstance(s, A.Assign) and len(s.targets) == 2 and isinstance(s.value, A.Seq)


def test_arrow_functions():
    s = one("f := (x, y) -> x*y;")
    assert isinstance(s.value, A.Arrow) and s.value.params == ["x", "y"]
    s = one("g := x -> y -> x + y;")
    assert isinstance(s.value.body, A.Arrow)


def test_calls_ranges_equations():
    e = expr("int(x^2, x = 0..1);")
    assert isinstance(e, A.Call) and e.func.id == "int"
    eq = e.args[1]
    assert eq.op == "=" and isinstance(eq.right, A.Range)


def test_lists_sets_index_and_factorial():
    e = expr("[1, 2, {3}][2] + n!;")
    assert isinstance(e.left, A.Index) and isinstance(e.left.base, A.ListLit)
    assert isinstance(e.right, A.UnOp) and e.right.op == "!"


def test_dollar_and_ditto():
    e = expr("diff(f, x$2) + %;")
    assert e.left.args[1].op == "$" and isinstance(e.right, A.Ditto)


def test_boolean_operators():
    e = expr("not a and b or c;")
    assert e.op == "or" and e.left.op == "and" and e.left.left.op == "not"


def test_if_elif_else_and_fi():
    s = one("if x < 0 then -x elif x = 0 then 0 else x end if;")
    assert isinstance(s, A.If) and len(s.branches) == 2 and s.orelse is not None
    assert isinstance(one("if a then b fi;"), A.If)


def test_for_loops():
    s = one("for i from 1 to 10 by 2 do s := s + i end do;")
    assert s.var == "i" and s.frm and s.to and s.by and len(s.body) == 1
    s = one("for e in [1,2] do print(e) od;")
    assert s.in_ is not None
    s = one("while n > 1 do n := n/2; end do;")
    assert s.var is None and s.cond is not None


def test_proc():
    s = one("f := proc(n::integer) local i, r; r := 1; for i to n do r := r*i end do; r end proc;")
    p = s.value
    assert isinstance(p, A.Proc) and p.params == ["n"] and p.locals == ["i", "r"]
    assert len(p.body) == 3


def test_spans_point_into_source():
    src = "y := sin(x);"
    s = one(src)
    assert src[s.value.start:s.value.end] == "sin(x)"


@pytest.mark.parametrize("src, msg", [
    ("diff(sin(x), x", "unclosed '('"),
    ("f(", "unclosed '('"),
    ("[1, 2;", "unclosed '['"),
    ("x)", "unmatched ')'"),
    ("if x then y", "unclosed 'if' block"),
    ("for i to 3 do i", "unclosed 'for' block"),
    ("if x then y end do", "'if' block closed by 'end do'"),
    ("end if;", "'end' without a matching opening statement"),
    ("x := ;", "missing value after ':='"),
    ("1..;", "range is missing its upper end"),
    ('"abc', "unterminated string"),
    ("a < b < c;", "comparisons cannot be chained"),
    ("x := 1 y := 2;", "missing ';' or ':' after statement"),
    ("if x y end if;", "expected 'then' after the 'if' condition, found 'y'"),
])
def test_errors(src, msg):
    assert msg in errors(src)


def test_recovery_continues_after_error():
    res = parse("x := (1 + ; y := 2;")
    assert not res.ok
    assert any(isinstance(s, A.Assign) and s.targets[0].id == "y" for s in res.statements)


def test_never_raises_on_garbage():
    for src in ["", ";;;", ")))", "proc(", "if if if", "@#$", "x := -> ;", "`", "end end od fi"]:
        parse(src)
