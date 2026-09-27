# Symple — a Maple-style desktop front-end for SymPy

## Context
The user wants an open-source desktop CAS that feels like Maple but runs on SymPy: a clean, minimal GUI;
Maple-like input syntax; syntax highlighting; structural diagnostics (for example, unbalanced brackets or a
missing `end if`); autocompletion; and a document worksheet where each command's result appears right below it.

**Decisions made:** PySide6 GUI · MIT license · public GitHub repo `alestoman5/symple` · Maple-style document worksheet.

## Legal / open-source hygiene (researched constraints)
- **Dependency licenses.** SymPy and mpmath are BSD-3. Matplotlib uses a BSD-compatible license based on the PSF
  license. PySide6 is LGPLv3; that is fine as a normal pip dependency that we don't modify or statically bundle.
  All of these are compatible with MIT. **PyQt6 (GPL) is not used.**
- **Trademark.** "Maple" is a trademark of Waterloo Maple Inc. (Maplesoft). The project name, logo, and window title
  must not contain "Maple". The README may say "Maple-inspired syntax" plus a notice: *"Not affiliated with or
  endorsed by Maplesoft. Maple is a trademark of Waterloo Maple Inc."* No Maplesoft logos, icons, or color scheme.
- **Copyright.** A language's syntax and function names aren't protected expression (SAS Institute v. World
  Programming, CJEU 2012; Google v. Oracle, US 2021 fair use). Maple's help pages, examples, worksheets, and
  `.mw` files *are* protected, so every docstring and completion description is written from scratch. No
  Maple library code or text is copied.
- **Security.** User input is never passed to Python's `eval`/`exec`. A custom parser maps the syntax onto an
  allowlist of SymPy functions, so a worksheet can't run arbitrary code (for example, `__import__`).
- Add `THIRD_PARTY_NOTICES.md` listing each dependency and its license. Add `.gitignore` so no venvs, caches, or
  personal paths get committed.

## Architecture (`src/symple/`, GUI-free core so it can be unit-tested)
```
lang/tokens.py, lexer.py    Tokens with (line, col, span): numbers, names, `quoted names`, "strings",
                            := -> .. ^ ** <> <= >= , ; : % # comments, keywords
                            (proc local global end if then elif else fi do od for from to by while in
                             return and or not xor implies mod union intersect minus)
lang/ast.py                 Dataclass nodes: Assign, Call, BinOp, UnOp, Range, Seq/List/Set, Index,
                            If, For/While, Proc, Return, Ditto(%), Statement(terminator ';'|':')
lang/parser.py              Recursive-descent / Pratt parser with Maple precedence; error recovery that
                            syncs on ';' ':' 'end'; returns (statements, diagnostics)
lang/diagnostics.py         Diagnostic(severity, span, message, hint). Structural checks: unbalanced ()[]{},
                            unterminated string, missing terminator, unclosed proc/if/do blocks, '=' used
                            where ':=' was probably meant, unknown function (warning), wrong argument count
                            (from builtin signatures), use before assignment (info)
engine/builtins.py          Registry: name -> (sympy callable/adapter, signature, one-line doc, category).
                            Maple→SymPy adapters: diff, int (int(f,x) and int(f,x=a..b)), solve, fsolve,
                            dsolve, simplify, expand, factor, normal, collect, combine, limit, series, taylor,
                            sum, product, evalf, subs, eval, numer, denom, nops, op, seq, map, convert, sqrt,
                            exp, ln/log, trig/hyperbolic, abs, Pi, I, infinity, true/false; LinearAlgebra
                            via with(LinearAlgebra): Matrix, Vector, Determinant, Inverse, Transpose,
                            Eigenvalues, Eigenvectors, Rank; plot/plot3d; restart
engine/evaluator.py         Walks AST -> SymPy with a Session env (user vars, procs, % history,
                            loaded packages). Undefined names -> Symbol (Maple semantics).
                            Returns Result(kind: expr|plot|text|error|none, payload)
engine/worker.py            Runs the evaluator in a separate multiprocessing process so a long computation can
                            be interrupted (kill + restart session). Sends back LaTeX, plain text, and PNG bytes.
ui/main_window.py           QMainWindow: toolbar (Run, Run all, Interrupt, Restart), File new/open/save
                            (own .syw JSON format), status bar
ui/worksheet.py             QScrollArea of Cell widgets; Enter = execute + move to/create next cell,
                            Shift+Enter = newline; editing an old cell and re-running updates its output
ui/cell.py                  '>' prompt + InputEditor + OutputView
ui/editor.py                QPlainTextEdit subclass; red/yellow wavy underlines + hover tooltips from
                            diagnostics (debounced live parse, ~250 ms)
ui/highlighter.py           QSyntaxHighlighter driven by the lexer (keywords, builtins, numbers, strings,
                            comments, operators, and a matching-bracket highlight)
ui/completer.py             QCompleter popup: builtins + keywords + session variables, showing signature and doc;
                            Ctrl+Space or auto-trigger after 2 characters
ui/math_view.py             Render LaTeX via matplotlib mathtext -> QPixmap (centered, blue like the classic
                            CAS look); falls back to sympy.pretty(unicode) text
ui/theme.py                 Minimal light palette + monospace font
app.py / __main__.py        `python -m symple` / `symple` console entry point
```
`;` shows the output and `:` hides it. A missing terminator on the last line is accepted, with an info hint.

## Build steps (commit + push after each)
1. **Scaffold.** `git init`; add `pyproject.toml` (deps: sympy, PySide6, matplotlib; dev: pytest), MIT `LICENSE`
   (© 2026 Ales Toman), README with the trademark disclaimer, `THIRD_PARTY_NOTICES.md`, `.gitignore`, and
   `docs/design.md` (this design). Create a venv and install. `gh repo create symple --public --source . --push`.
2. **Lexer + parser + AST**, TDD with pytest (`tests/test_lexer.py`, `tests/test_parser.py`).
3. **Diagnostics** (`tests/test_diagnostics.py`).
4. **Evaluator + builtins** (`tests/test_evaluator.py`: `diff(sin(x),x);`, `int(x^2,x=0..1);`,
   `f := x -> x^2: f(3);`, `solve(x^2-4=0,x);`, `%` history, procs, if/for loops, Matrix ops).
5. **Worker process** with interrupt/restart (test that a timeout kills a runaway job).
6. **GUI shell**: main window, worksheet, cells, math rendering, execution flow.
7. **Editor features**: highlighter, live diagnostics underlines and tooltips, completer.
8. **Plots, save/load of `.syw`, polish, README screenshots and usage.**

## Verification
- `pytest` passes after each core step (lexer, parser, diagnostics, evaluator, worker).
- Manually launch `python -m symple` (using the `run` skill) and check: typing highlights live; `diff(sin(x),x` shows
  a red underline with an "unclosed '('" tooltip; `in` + Ctrl+Space offers `int`, `infinity`, …; Enter shows
  a typeset `cos(x)` below; `:` hides output; `%` reuses the last result; `int(exp(-x^2),x=-infinity..infinity);`
  → √π; `plot(sin(x),x=0..2*Pi);` shows an inline plot; Interrupt stops a long `factor(x^1000-1)`; save/reload
  a worksheet.
- Check `gh repo view alestoman5/symple` and confirm the commit history has one commit per step.
- Final license check: `pip-licenses` (dev-only tool, run temporarily) confirms no GPL runtime dependencies.
