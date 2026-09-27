"""After PyInstaller: add license texts and example worksheets to dist/Symple/."""
import shutil
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "dist" / "Symple" / "licenses"

# Runtime packages that end up in the bundle.
PACKAGES = ["sympy", "mpmath", "PySide6-Essentials", "shiboken6", "matplotlib", "numpy",
            "pillow", "fonttools", "kiwisolver", "cycler", "contourpy", "pyparsing",
            "python-dateutil", "packaging", "six"]


def main() -> int:
    if not DEST.parent.is_dir():
        print("dist/Symple not found; run PyInstaller first", file=sys.stderr)
        return 1
    DEST.mkdir(exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy(ROOT / name, DEST.parent / name)
    shutil.copytree(ROOT / "examples", DEST.parent / "examples", dirs_exist_ok=True)
    for f in (ROOT / "packaging" / "licenses").iterdir():
        shutil.copy(f, DEST / f.name)
    for pkg in PACKAGES:
        try:
            dist = metadata.distribution(pkg)
        except metadata.PackageNotFoundError:
            print(f"warning: {pkg} not installed", file=sys.stderr)
            continue
        target = DEST / dist.metadata["Name"]
        copied = 0
        for f in dist.files or []:
            parts = [p.lower() for p in f.parts]
            if ".dist-info" in parts[0] and any(k in parts[-1] for k in ("licen", "copying", "notice")) \
                    or (len(parts) > 1 and parts[1] == "licenses"):
                src = Path(f.locate())
                if src.is_file():
                    target.mkdir(exist_ok=True)
                    shutil.copy(src, target / src.name)
                    copied += 1
        (target if copied else DEST).mkdir(exist_ok=True)
        info = target / "PACKAGE.txt" if copied else DEST / f"{dist.metadata['Name']}.txt"
        info.write_text(f"{dist.metadata['Name']} {dist.version}\nLicense: "
                        f"{dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'see project'}\n"
                        f"Home: {dist.metadata.get('Home-page') or ''}\n", encoding="utf-8")
    print(f"licenses collected in {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
