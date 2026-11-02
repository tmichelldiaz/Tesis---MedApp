"""La fecha del examen de un documento, para ordenar los resultados en el tiempo.

El extractor de valores trabaja por secciones y la fecha del examen suele estar solo en el
encabezado, así que casi todos los valores salían sin fecha y el sistema tenía que adivinar
cuál era el más reciente por el orden en que se subieron los archivos. Aquí se lee UNA vez la
fecha del documento y se aplica a los valores que no traen una propia.

Reglas:
- Solo se acepta una fecha con una etiqueta clara ("fecha de toma de muestra", "fecha de
  resultado"...). Una fecha suelta no se usa: puede ser cualquier cosa.
- Se descartan las fechas administrativas o personales: nacimiento, impresión, ingreso, egreso,
  afiliación, vencimiento, expedición.
- Si no hay ninguna, devuelve None y no se inventa nada."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

MONTHS = {
    "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "mar": 3, "abril": 4, "abr": 4,
    "mayo": 5, "may": 5, "junio": 6, "jun": 6, "julio": 7, "jul": 7, "agosto": 8, "ago": 8,
    "septiembre": 9, "setiembre": 9, "sep": 9, "sept": 9, "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11, "diciembre": 12, "dic": 12,
}

# De la etiqueta más confiable a la menos: la fecha en que se tomó la muestra manda sobre
# la fecha en que se entregó el informe.
LABELS = [
    r"(?:toma|recoleccion|obtencion|extraccion|recepcion de la muestra)(?: de(?: la)?(?: muestra| sangre| orina)?)?",
    r"(?:examen|analisis|atencion|consulta|realizacion|procedimiento|estudio|valoracion)",
    r"(?:resultados?|informe|reporte|reportado|validacion|emision)",
]
EXCLUDED = re.compile(
    r"nacimiento|nacio|cumplea|impresion|imprimio|ingreso|egreso|admision|afiliacion|vencimiento|"
    r"expedicion|vigencia|orden|edad"
)

_NUMERIC = re.compile(r"(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})(?!\d)")
_ISO = re.compile(r"(?<!\d)(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?!\d)")
_SPELLED = re.compile(r"(?<!\d)(\d{1,2})\s*(?:de\s+)?([a-z]{3,10})\.?,?\s*(?:de\s+|del\s+)?(\d{4})(?!\d)")
_WINDOW = 70  # cuántos caracteres después de la etiqueta se buscan la fecha


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _valid(year: int, month: int, day: int, today: date) -> str | None:
    try:
        found = date(year, month, day)
    except ValueError:
        return None
    if found.year < 1990 or found > today + timedelta(days=1):
        return None  # un examen no es del futuro ni de antes de 1990: debe ser otra cosa
    return found.isoformat()


def _first_date(chunk: str, today: date) -> str | None:
    """La primera fecha del trozo, en cualquiera de los formatos habituales."""
    candidates: list[tuple[int, str]] = []
    for m in _ISO.finditer(chunk):
        iso = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)
        if iso:
            candidates.append((m.start(), iso))
    for m in _NUMERIC.finditer(chunk):
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Día/mes/año es lo habitual en Colombia; solo se invierte si el primer número no puede ser un día.
        day, month = (a, b) if b <= 12 else (b, a)
        iso = _valid(year, month, day, today)
        if iso:
            candidates.append((m.start(), iso))
    for m in _SPELLED.finditer(chunk):
        month = MONTHS.get(m.group(2))
        if month:
            iso = _valid(int(m.group(3)), month, int(m.group(1)), today)
            if iso:
                candidates.append((m.start(), iso))
    return min(candidates)[1] if candidates else None


def find_exam_date(text: str, today: date | None = None) -> str | None:
    """Fecha del examen en formato AAAA-MM-DD, o None si el documento no la indica con claridad."""
    if not text or not text.strip():
        return None
    today = today or datetime.now(timezone.utc).date()
    plain = _plain(text)

    for label in LABELS:
        pattern = re.compile(r"fecha(?:\s+y\s+hora)?(?:\s+de(?:l)?)?\s*(?:la\s+)?" + label + r"\b")
        for match in pattern.finditer(plain):
            chunk = plain[match.end(): match.end() + _WINDOW]
            line_end = chunk.find("\n\n")  # no cruzar a otro párrafo
            chunk = chunk if line_end < 0 else chunk[:line_end]
            found = _first_date(chunk, today)
            if found:
                return found

    # "Fecha: 02/09/2026" sin más: sirve solo si lo de antes en la línea no es una fecha personal/administrativa.
    for match in re.finditer(r"(?<![a-z])fecha\s*[:\-]\s*", plain):
        line_start = plain.rfind("\n", 0, match.start()) + 1
        if EXCLUDED.search(plain[line_start: match.start()]):
            continue
        found = _first_date(plain[match.end(): match.end() + 30], today)
        if found:
            return found
    return None
