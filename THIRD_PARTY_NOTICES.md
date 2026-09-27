# Third-party notices

Symple is distributed under the MIT License (see `LICENSE`). It does not bundle
third-party source code; the following packages are installed as ordinary,
unmodified runtime dependencies from PyPI and remain under their own licenses.

| Package    | License                        | Project page                          |
|------------|--------------------------------|---------------------------------------|
| SymPy      | BSD 3-Clause                   | https://www.sympy.org                 |
| mpmath     | BSD 3-Clause (SymPy dependency)| https://mpmath.org                    |
| PySide6    | LGPL v3 (Qt for Python)        | https://doc.qt.io/qtforpython/        |
| Qt 6       | LGPL v3 (shipped with PySide6) | https://www.qt.io                     |
| Matplotlib | Matplotlib License (PSF-based, BSD-compatible) | https://matplotlib.org |

## Notes on LGPL (PySide6 / Qt)

Symple links to PySide6/Qt dynamically through the normal Python import
mechanism and does not modify them. Users are free to replace the installed
PySide6/Qt libraries with other compatible versions. If you redistribute a
frozen/bundled binary of Symple (e.g. built with PyInstaller), you must keep
the Qt libraries as replaceable shared libraries and include the LGPL v3 text
and a way to obtain the corresponding Qt/PySide6 source.

## Trademarks

Maple is a trademark of Waterloo Maple Inc. Symple is an independent project
and is not affiliated with, sponsored by, or endorsed by Waterloo Maple Inc.
(Maplesoft). References to Maple describe only the style of the input language.
No Maplesoft code, documentation, examples or artwork are included.
