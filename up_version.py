#!/usr/bin/env python
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def replace_once(path, pattern, replacement):
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1)
    if count != 1:
        raise RuntimeError(f"No se pudo actualizar {path.name}: patron no encontrado")
    path.write_text(updated, encoding="utf-8", newline="\n")


def version_to_build(version):
    return f"{version}.0"


def main():
    if len(sys.argv) != 2 or not VERSION_RE.match(sys.argv[1]):
        print("Uso: python up_version.py X.Y.Z")
        return 1

    new_version = sys.argv[1]
    app_build = version_to_build(new_version)

    replace_once(
        ROOT_DIR / "version.py",
        r'__version__\s*=\s*"[^"]*"',
        f'__version__ = "{new_version}"',
    )
    replace_once(
        ROOT_DIR / "installer.nsi",
        r'!define APP_VERSION "[^"]*"',
        f'!define APP_VERSION "{new_version}"',
    )
    replace_once(
        ROOT_DIR / "installer.nsi",
        r'!define APP_BUILD "[^"]*"',
        f'!define APP_BUILD "{app_build}"',
    )

    print(f"Version actualizada a {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())