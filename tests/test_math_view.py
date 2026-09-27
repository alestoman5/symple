from symple.engine.evaluator import Evaluator
from symple.ui.math_view import adapt_for_mathtext


def test_small_delimiters_become_plain_parentheses():
    assert adapt_for_mathtext(r"\sin{\left(x \right)}") == r"\sin{(x )}"


def test_tall_delimiters_are_kept():
    tex = r"\left(\frac{1}{x}\right)"
    assert adapt_for_mathtext(tex) == tex


def test_nested_delimiters():
    assert adapt_for_mathtext(r"\left(\left(\frac{a}{b}\right) + c\right)") == \
        r"\left(\left(\frac{a}{b}\right) + c\right)"
    assert adapt_for_mathtext(r"\left(a + \left(b\right)\right)") == "(a + (b))"


def test_assignment_symbol():
    assert r"\coloneq" in adapt_for_mathtext("f := x")


def test_matrix_outputs_carry_layout_parts():
    out = Evaluator().run("A := Matrix([[1, x], [y^2, 4]]);")[0]
    parts = out.meta["parts"]
    assert parts[0] == {"latex": "A :="}
    assert parts[1]["matrix"] == [["1", "x"], ["y^{2}", "4"]]
