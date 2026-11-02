import sys
from pathlib import Path

import pymupdf

ROWS = [
    ("Examen", "Resultado", "Unidad", "Valor de referencia"),
    ("Glucosa en ayunas", "94", "mg/dL", "70 - 100"),
    ("Colesterol total", "212", "mg/dL", "< 200"),
    ("LDL", "138", "mg/dL", "< 130"),
    ("HDL", "52", "mg/dL", "> 40"),
    ("Triglicéridos", "141", "mg/dL", "< 150"),
    ("Creatinina", "0.9", "mg/dL", "0.6 - 1.2"),
]


def build(path: Path) -> None:
    doc = pymupdf.open()

    page = doc.new_page()
    page.insert_text((60, 70), "Laboratorio Clínico Ejemplo (documento sintético)", fontsize=16)
    page.insert_text((60, 100), "Paciente: Paciente de Prueba    Documento: 000000", fontsize=11)
    page.insert_text((60, 118), "Fecha de toma de muestra: 10 de marzo de 2026", fontsize=11)
    page.insert_text((60, 160), "Analítica de sangre completa", fontsize=14)
    y = 190
    for row in ROWS:
        for x, cell in zip((60, 240, 330, 400), row):
            page.insert_text((x, y), cell, fontsize=11)
        y += 22

    page2 = doc.new_page()
    page2.insert_text((60, 70), "Observaciones", fontsize=14)
    page2.insert_text((60, 100), "Se recomienda control de perfil lipídico en 3 meses.", fontsize=11)
    page2.insert_text((60, 118), "Muestra tomada en ayunas de 12 horas.", fontsize=11)

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/muestra_laboratorio.pdf")
    build(target)
    print(f"PDF sintético -> {target}")
