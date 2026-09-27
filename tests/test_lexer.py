from symple.lang.lexer import tokenize
from symple.lang.tokens import T


def kinds(src):
    return [(t.kind, t.text) for t in tokenize(src)[:-1]]


def test_assignment_and_arrow():
    assert kinds("f := x -> x^2;") == [
        (T.NAME, "f"), (T.OP, ":="), (T.NAME, "x"), (T.OP, "->"),
        (T.NAME, "x"), (T.OP, "^"), (T.NUMBER, "2"), (T.SEMI, ";"),
    ]


def test_range_does_not_eat_number_dot():
    assert kinds("1..10") == [(T.NUMBER, "1"), (T.OP, ".."), (T.NUMBER, "10")]
    assert kinds("a..b") == [(T.NAME, "a"), (T.OP, ".."), (T.NAME, "b")]


def test_floats_and_exponents():
    assert [t for _, t in kinds("1.5 .25 2e-3 3.0E+10")] == ["1.5", ".25", "2e-3", "3.0E+10"]


def test_keywords_strings_and_quoted_names():
    toks = tokenize('if x then "hi" end if; `my var`')
    assert toks[0].kind is T.KEYWORD and toks[0].text == "if"
    assert toks[3].kind is T.STRING and toks[3].text == "hi"
    assert toks[-2].kind is T.NAME and toks[-2].text == "my var"


def test_comments_skipped_unless_requested():
    assert kinds("x # note\n y") == [(T.NAME, "x"), (T.NAME, "y")]
    toks = tokenize("x # note", keep_comments=True)
    assert toks[1].kind is T.COMMENT and toks[1].text == "# note"


def test_ditto_and_colon_terminator():
    assert kinds("%%: %") == [(T.DITTO, "%%"), (T.COLON, ":"), (T.DITTO, "%")]


def test_errors_are_tokens_not_exceptions():
    toks = tokenize('"abc')
    assert toks[0].kind is T.STRING and toks[0].error == "unterminated string"
    toks = tokenize("x @ y")
    assert toks[1].kind is T.ERROR


def test_offsets():
    toks = tokenize("ab + cd")
    assert [(t.start, t.end) for t in toks] == [(0, 2), (3, 4), (5, 7), (7, 7)]
