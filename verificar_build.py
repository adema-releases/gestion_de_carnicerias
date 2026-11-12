"""Verifica que el paquete de PyInstaller tenga todo lo que la app lee del disco.

Lo corre build_release.bat después de PyInstaller: si falta algo, el build
falla en vez de generar un instalador que da error 500 al abrir una pantalla.
"""

import sys
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent
PAQUETE = PROYECTO / "dist" / "GestionDeCarnicerias" / "_internal"
EXCLUIDAS = {"venv", "dist", "build", "staticfiles"}


def faltantes():
    """Plantillas del proyecto que no están en el paquete (rutas relativas)."""
    faltan = []
    for carpeta in sorted(PROYECTO.glob("*/templates")):
        if carpeta.parent.name in EXCLUIDAS:
            continue
        for plantilla in carpeta.rglob("*.html"):
            relativa = plantilla.relative_to(PROYECTO)
            if not (PAQUETE / relativa).is_file():
                faltan.append(str(relativa))
    for plantilla in (PROYECTO / "templates").rglob("*.html"):
        relativa = plantilla.relative_to(PROYECTO)
        if not (PAQUETE / relativa).is_file():
            faltan.append(str(relativa))
    return faltan


def main():
    if not PAQUETE.is_dir():
        print(f"No existe el paquete: {PAQUETE}")
        return 1
    faltan = faltantes()
    if faltan:
        print("Faltan plantillas en el paquete (revisar DIRS_TO_INCLUDE en el .spec):")
        for ruta in faltan:
            print("  -", ruta)
        return 1
    print("Verificacion del paquete OK: estan todas las plantillas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
