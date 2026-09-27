# Third-party notices

Symple is distributed under the MIT License (see `LICENSE`). It does not bundle
third-party source code; the following packages are installed as ordinary,
unmodified runtime dependencies from PyPI and remain under their own licenses.

| Package             | License                                   | Project page                    |
|---------------------|-------------------------------------------|---------------------------------|
| SymPy               | BSD 3-Clause                              | https://www.sympy.org           |
| mpmath              | BSD 3-Clause (SymPy dependency)           | https://mpmath.org              |
| PySide6-Essentials  | LGPL v3 (used under LGPL; also offered as GPL v2/v3) | https://doc.qt.io/qtforpython/ |
| shiboken6 / Qt 6    | LGPL v3 (shipped with PySide6)            | https://www.qt.io               |
| Matplotlib          | Matplotlib License (PSF-based, BSD-compatible) | https://matplotlib.org     |
| NumPy               | BSD 3-Clause (Matplotlib dependency)      | https://numpy.org               |
| Pillow, fontTools, kiwisolver, cycler, contourpy, pyparsing, python-dateutil, packaging, six | MIT / BSD / HPND-style permissive licenses (Matplotlib dependencies) | https://pypi.org |

Mathematical output is typeset with Matplotlib's built-in "mathtext" engine
using the Computer Modern fonts that ship with Matplotlib (distributed under
their own permissive license as part of Matplotlib). Symple does not include
copies of these fonts.

Development-only tools (not needed to run Symple): pytest (MIT).

## Notes on LGPL (PySide6 / Qt)

Symple links to PySide6/Qt dynamically through the normal Python import
mechanism and does not modify them. Users are free to replace the installed
PySide6/Qt libraries with other compatible versions. If you redistribute a
frozen/bundled binary of Symple (e.g. built with PyInstaller), you must keep
the Qt libraries as replaceable shared libraries and include the LGPL v3 text
and a way to obtain the corresponding Qt/PySide6 source.

## Windows installer (binary distribution)

The Windows installer bundles Python, the packages above and the Qt/PySide6
libraries in unmodified form. The Qt/PySide6 libraries are kept as separate,
replaceable DLL files in the installation folder (`_internal/PySide6`), so you
can swap in your own compatible build. The full LGPL v3 and GPL v3 texts and each
bundled package's license file are installed in the `licenses` folder.
The corresponding source code of Qt for Python (PySide6/shiboken6) and Qt is
available from https://download.qt.io/official_releases/QtForPython/ and
https://code.qt.io; Symple's own source is at https://github.com/alestoman5/symple.
The bundling tool, PyInstaller, is GPL-licensed with an exception that allows
distributing the resulting applications under any license.

## Trademarks

Maple is a trademark of Waterloo Maple Inc. Symple is an independent project
and is not affiliated with, sponsored by, or endorsed by Waterloo Maple Inc.
(Maplesoft). References to Maple describe only the style of the input language.
No Maplesoft code, documentation, examples or artwork are included.
