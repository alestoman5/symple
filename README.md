# Symple

A minimal, worksheet-style desktop front-end for [SymPy](https://www.sympy.org)
with a **Maple-inspired input language**.

Type a command at the `>` prompt, press **Enter**, and the typeset result appears
directly underneath — just like a classic computer-algebra worksheet.

```
> f := x -> x^2*sin(x):
> diff(f(x), x);
                  x² cos(x) + 2 x sin(x)
> int(exp(-x^2), x = -infinity..infinity);
                           √π
```

## Features

- **Worksheet interface** – editable input cells, output rendered below each one,
  re-run any cell at any time.
- **Maple-inspired syntax** – `:=` assignment, `->` arrow functions, `a..b` ranges,
  `;` to show / `:` to suppress output, `%` for the previous result, `proc … end proc`,
  `if … then … end if`, `for … do … end do`, `with(LinearAlgebra)` and more.
- **Syntax highlighting** of keywords, built-in functions, numbers, strings and comments.
- **Structural diagnostics** while you type: unbalanced brackets, unclosed blocks,
  missing terminators, unknown functions, wrong argument counts, `=` vs `:=` hints.
- **Autocompletion** of built-ins, keywords and your own variables with signatures.
- **Safe evaluation** – input is parsed by Symple's own parser and mapped onto an
  allow-list of SymPy functions; it is never passed to Python's `eval`.
- **Interruptible** – long computations run in a separate process and can be stopped.

## Install & run

```bash
git clone https://github.com/alestoman5/symple.git
cd symple
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
symple            # or: python -m symple
```

Run the tests with `pytest`.

## License

Symple is released under the [MIT License](LICENSE). Its dependencies keep their
own licenses — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Disclaimer

Symple is an independent open-source project. It is **not affiliated with,
sponsored by, or endorsed by Waterloo Maple Inc. (Maplesoft)**. Maple is a
trademark of Waterloo Maple Inc. The term is used only to describe the style of
the input language. All documentation and help text in Symple is original.
