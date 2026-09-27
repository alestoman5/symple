# PyInstaller spec: builds dist/Symple/ (one-folder mode, so the Qt libraries
# stay separate, replaceable files as the LGPL requires).
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    hiddenimports=["symple.engine.worker", "symple.engine.plotting", "mpl_toolkits.mplot3d"],
    excludes=["tkinter", "pytest", "IPython", "PySide6.QtWebEngineCore", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.QtMultimedia", "PySide6.Qt3DCore"],
    noarchive=False,
)
# Qt pieces a widgets-only app never loads (software OpenGL, QML/Quick, PDF viewer,
# virtual keyboard, translations); dropping them roughly halves the Qt payload.
_UNUSED = ("opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "qpdf.dll",
           "qt6opengl", "qt6network", "/translations/")


def _keep(entry):
    name = "/" + entry[0].replace("\\", "/").lower()
    return not any(u in name for u in _UNUSED)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Symple",
    icon=str(ROOT / "assets" / "symple.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Symple", upx=False)
