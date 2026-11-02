"""Enmascara campos de identificación del paciente antes de que el texto salga
hacia un modelo de terceros (embeddings o contexto de chat, ambos vía
OpenRouter). Es una redacción heurística por ETIQUETA ('Nombre:', 'C.C.:',
'Tel:', 'Correo:', ...): cubre los campos de identificación que casi siempre
aparecen rotulados en el encabezado de una historia clínica colombiana.

Limitaciones deliberadas de esta versión simple:
- No detecta un nombre, cédula o teléfono mencionado SIN su etiqueta (p. ej.
  suelto en medio de una nota narrativa) — eso requiere un detector de
  entidades (NER) o un servicio dedicado como Cloud DLP, no un regex.
- No toca fechas ni valores de laboratorio: el objetivo es proteger datos de
  identificación, no los datos clínicos que la app existe para mostrar.
"""

import re

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b")

_LABELS = (
    r"nombre completo|nombre|paciente|"
    r"c\.?c\.?|c[eé]dula(?:\s+de\s+ciudadan[ií]a)?|documento de identidad|documento|"
    r"identificaci[oó]n|tel[eé]fono|tel|celular|cel|"
    r"direcci[oó]n|domicilio|correo electr[oó]nico|correo|email"
)
# Etiqueta (con o sin negrita Markdown, cerrada antes o después de ':') seguida
# del valor, hasta el final de la línea o de la celda de una tabla Markdown ('|').
_LABEL_VALUE_RE = re.compile(rf"(?im)(\**\b(?:{_LABELS})\**\s*:\s*\**\s*)([^\n|]+)")


# Cédula con etiqueta pero SIN dos puntos ("C.C. 1.023.456.789 de Bogotá"), que
# _LABEL_VALUE_RE no alcanza a ver. El número va con puntos o espacios de
# miles, o corrido (6 a 11 dígitos).
_ID_NO_COLON_RE = re.compile(
    r"(?i)(\b(?:c\.?\s?c\.?|c[eé]dula(?:\s+de\s+ciudadan[ií]a)?|documento(?:\s+de\s+identidad)?)"
    r"\s*(?:n[úu]mero|n[oº°]\.?)?\s*)(\d{1,3}(?:[.\s]\d{3}){1,3}|\d{6,11})\b"
)
# Cédula suelta con formato de puntos de 10 dígitos (1.023.456.789). Se exige
# ese largo para no confundirla con recuentos de laboratorio (250.000, 1.000.000).
_ID_DOTTED_RE = re.compile(r"\b\d\.\d{3}\.\d{3}\.\d{3}\b")
# Fecha de nacimiento rotulada. Se oculta solo la fecha, no las del examen.
_DOB_RE = re.compile(
    r"(?i)((?:fecha\s+de\s+nacimiento|f\.?\s*nac(?:imiento)?\.?|nacid[oa]\s+(?:el|en)|nac[ií]\s+(?:el|en))\s*:?\s*)"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}\s+de\s+[a-záéíóúñ]+\s+(?:de\s+)?\d{4})"
)


def redact_pii(text: str) -> str:
    """Devuelve `text` con los campos de identificación rotulados reemplazados
    por '[dato oculto]', y cualquier correo electrónico por '[correo oculto]'."""
    text = _LABEL_VALUE_RE.sub(lambda m: f"{m.group(1)}[dato oculto]", text)
    text = _ID_NO_COLON_RE.sub(lambda m: f"{m.group(1)}[dato oculto]", text)
    text = _ID_DOTTED_RE.sub("[dato oculto]", text)
    text = _DOB_RE.sub(lambda m: f"{m.group(1)}[dato oculto]", text)
    text = _EMAIL_RE.sub("[correo oculto]", text)
    return text
