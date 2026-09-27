import pytest

from symple.catalog import CATALOG
from symple.lang.analysis import analyze
from symple.lang.diagnostics import line_col


def diags(src, known=()):
    return [(d.severity, d.message) for d in analyze(src, known).diagnostics]


def messages(src, known=()):
    return [m for _, m in diags(src, known)]


def test_clean_input_has_no_diagnostics():
    src = "f := x -> x^2: diff(f(x), x); int(sin(x), x = 0..Pi); solve(x^2 = 4, x);"
    assert diags(src) == []


def test_wrong_argument_count():
    assert "diff expects at least 2 arguments, got 1" in messages("diff(x^2);")
    assert "sqrt expects at most 1 argument, got 2" in messages("sqrt(4, 2);")


def test_dollar_or_sequence_arguments_skip_count_check():
    assert messages("diff(f, x$2);") == []


def test_typo_and_case_suggestions():
    d = analyze("Sin(x); intt(x, x);").diagnostics
    assert d[0].message == "unknown function 'Sin'" and "'sin'" in d[0].hint
    assert d[1].message == "unknown function 'intt'" and "'int'" in d[1].hint


def test_unknown_function_without_close_match_is_fine():
    # y(x) is an ordinary undefined function, e.g. in dsolve
    assert messages("dsolve(diff(y(x), x) = y(x), y(x));") == []


def test_user_functions_are_not_typos():
    assert messages("sinn := x -> x: sinn(2);") == []
    assert messages("sinn(2);", known={"sinn"}) == []


def test_equation_vs_assignment():
    d = analyze("a = 5;").diagnostics
    assert d[0].severity == "warning" and "a := " in d[0].hint


def test_protected_names():
    assert "'Pi' is a protected built-in name and cannot be assigned" in messages("Pi := 3;")
    assert messages("Digits := 20;") == []


def test_break_and_return_placement():
    assert "'break' outside a loop" in messages("break;")
    assert messages("for i to 3 do if i = 2 then break end if end do;") == []
    assert "'return' outside a procedure" in messages("return 1;")
    assert messages("f := proc(x) return x end proc;") == []


def test_duplicate_params():
    assert "parameter or local 'x' is declared twice" in messages("f := (x, x) -> x;")


def test_range_without_variable():
    assert "range is missing its variable" in messages("int(x, 0..1);")


def test_pi_and_e_hints():
    assert diags("pi;") == [("info", "'pi' is an ordinary symbol here")]
    assert ("info", "'e' is an ordinary symbol here") in diags("e^x;")


def test_missing_terminator_info():
    assert diags("x + 1") == [("info", "statement has no terminator; ';' is assumed")]


def test_constant_called_as_function():
    assert "'Pi' is a constant, not a function" in messages("Pi(2);")


def test_parser_errors_are_included_with_positions():
    src = "x := 1;\ndiff(sin(x), x"
    d = analyze(src).diagnostics[0]
    assert d.message == "unclosed '('"
    assert line_col(src, d.start) == (2, 5)


def test_uneval_quotes():
    assert messages("x := 'x';") == []
    assert "unclosed quote" in messages("x := 'x;")


@pytest.mark.parametrize("entry", list(CATALOG.values()), ids=lambda e: e.name)
def test_catalog_entries_are_well_formed(entry):
    assert entry.doc and entry.signature.startswith(entry.name)
    assert entry.max_args is None or entry.max_args >= entry.min_args
