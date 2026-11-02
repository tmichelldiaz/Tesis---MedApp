"""Prueba manual del enmascaramiento: le das un PDF y te devuelve su texto ya
enmascarado, con el mismo proceso que usa la app (capa local + Cloud DLP).

    .\\.venv\\Scripts\\python.exe scripts\\mask_pdf.py historia.pdf
    .\\.venv\\Scripts\\python.exe scripts\\mask_pdf.py historia.pdf --local   # sin DLP, solo la capa local

Escribe `historia.enmascarado.md` junto al PDF y muestra en pantalla qué líneas
cambiaron (antes -> después). Necesita `gcloud auth application-default login`
con acceso al proyecto, salvo con --local.

Solo lee PDFs CON texto seleccionable. Un escaneo o una foto no se puede
enmascarar aquí: en la app primero lo lee el modelo de visión y recién después se
enmascara lo que él devolvió.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from app.config import Settings  # noqa: E402
from app.privacy.masking import MaskingError, mask_text  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Enmascara los datos de identificación de un PDF.")
    parser.add_argument("file", type=Path, help="PDF con texto seleccionable")
    parser.add_argument("--local", action="store_true", help="solo la capa local, sin llamar a Cloud DLP")
    parser.add_argument("-o", "--output", type=Path, help="archivo de salida (.md)")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"No existe el archivo: {args.file}")
        return 1

    settings = Settings(dlp_enabled=not args.local)
    modo = "capa local" if args.local else "capa local + Cloud DLP"
    out_path = args.output or args.file.with_suffix(".enmascarado.md")

    try:
        doc = pymupdf.open(args.file)
    except Exception as exc:
        print(f"No se pudo abrir el PDF: {exc}")
        return 1

    parts: list[str] = []
    changed_total = 0
    sin_texto: list[int] = []
    with doc:
        for number, page in enumerate(doc, start=1):
            original = page.get_text().strip()
            if not original:
                sin_texto.append(number)
                parts.append(f"<!-- página {number} -->\n\n[página sin texto seleccionable]")
                continue
            try:
                masked = mask_text(original, settings)
            except MaskingError as exc:
                print(f"\nNo se pudo enmascarar la página {number}: {exc}")
                print("Revisa la autenticación (gcloud auth application-default login) o usa --local.")
                return 2
            parts.append(f"<!-- página {number} -->\n\n{masked}")

            before, after = original.splitlines(), masked.splitlines()
            if len(before) == len(after):
                diffs = [(b, a) for b, a in zip(before, after) if b != a]
            else:  # el DLP puede unir o partir líneas: se muestra la página entera
                diffs = [(original, masked)] if original != masked else []
            if diffs:
                print(f"\n=== Página {number}: {len(diffs)} cambio(s) ===")
                for b, a in diffs:
                    print(f"  ANTES  : {b}")
                    print(f"  DESPUÉS: {a}\n")
            changed_total += len(diffs)

    out_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"\nModo: {modo}. Páginas: {len(parts)}. Cambios: {changed_total}.")
    if sin_texto:
        print(f"Sin texto seleccionable (no procesadas): páginas {sin_texto}")
    print(f"Texto enmascarado completo en: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
