import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.extraction.vision_client import NO_REASONING, VisionError, chat_completion
from app.okf.segmenter import segment

SYSTEM_PROMPT = """Eres un extractor de datos clínicos discretos. Recibes el Markdown ya \
transcrito de un documento clínico (puede tener tablas de laboratorio, signos vitales, \
medicamentos, alergias o diagnósticos) y devuelves ÚNICAMENTE un objeto JSON con los \
valores discretos y verificables que encuentres.

La respuesta debe tener esta forma exacta:
{"values": [ <elemento>, <elemento>, ... ]}

Cada elemento del array "values" tiene esta forma exacta:
{
  "exam": "<nombre del examen o dato, ej. 'Glucosa en ayunas'>",
  "value_raw": "<el valor tal como aparece en el texto, ej. '94' o 'Penicilina'>",
  "value_numeric": <número si el valor es numérico, o null>,
  "unit": "<unidad, ej. 'mg/dL', o null>",
  "date": "<fecha del EXAMEN (toma de muestra o resultado) en formato YYYY-MM-DD si el documento la indica para este dato, o null>",
  "reference_low": <límite inferior del rango de referencia como número, o null>,
  "reference_high": <límite superior del rango de referencia como número, o null>,
  "reference_text": "<el rango tal como aparece en el texto, ej. '70 - 100', o null>"
}

Reglas:
- Incluye TODOS los datos CLÍNICOS discretos y verificables que encuentres, sin excepción: \
cada fila de cada tabla de resultados de laboratorio, signos vitales, medicamentos con su \
dosis, alergias, tipo de sangre (como dato clínico, ej. grupo sanguíneo O+), diagnóstico \
principal. No incluyas observaciones generales, recomendaciones ni texto narrativo.
- NUNCA incluyas datos de identificación del paciente ni datos administrativos del \
documento, aunque aparezcan en una tabla o encabezado. Esto incluye (sin limitarse a): \
nombre del paciente, número o tipo de documento de identidad, fecha de nacimiento, edad, \
número de historia clínica, número de orden, fecha/hora de ingreso, fecha de impresión del \
documento, médico tratante o que atiende, servicio o especialidad, sede o institución, \
procedencia, EPS o afiliación, y cualquier otro dato que identifique a la persona o describa \
el trámite administrativo en vez de un resultado clínico.
- Nunca inventes un valor que no esté en el texto. Si un campo no tiene suficiente \
información, usa null en ese campo (no omitas el campo).
- Cada dato va UNA sola vez, aunque el documento lo repita (en la tabla y otra vez en la conclusión, por ejemplo). \
No incluyas las leyendas o escalas de referencia que explican qué significa cada categoría (por ejemplo la lista \
"PI-RADS 1, 2, 3, 4, 5" con su significado): solo el resultado del paciente.
- "value_raw" es SOLO el valor, sin repetir el nombre del examen: si el texto dice "PIRADS 2" \
para el examen PIRADS, value_raw es "2" (no "PIRADS 2").
- Si no encuentras ningún dato discreto, responde exactamente: {"values": []}
- Responde ÚNICAMENTE con el objeto JSON. Sin explicación, sin comentarios, sin bloque de \
código que lo envuelva, sin describir los campos en prosa."""

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class LabValue:
    exam: str
    value_raw: str
    value_numeric: float | None = None
    unit: str | None = None
    date: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    reference_text: str | None = None

    def to_dict(self) -> dict:
        return {
            "exam": self.exam,
            "value_raw": self.value_raw,
            "value_numeric": self.value_numeric,
            "unit": self.unit,
            "date": self.date,
            "reference_low": self.reference_low,
            "reference_high": self.reference_high,
            "reference_text": self.reference_text,
        }


def _clean(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else None


# El modelo (gratuito, no siempre obedece el prompt al pie de la letra) a veces
# captura datos de identificación del paciente o del trámite administrativo como
# si fueran un "examen". Esto es una segunda línea de defensa además del prompt:
# se descarta cualquier entrada cuyo campo "exam" coincida con estos patrones,
# sin importar lo que haya respondido el modelo.
_NOISE_TERMS = {
    "paciente", "nombre", "identificacion", "cedula", "documento", "fecha de nacimiento",
    "edad", "historia", "orden no", "numero de orden", "fecha de ingreso",
    "fecha y hora de ingreso", "fecha de impresion", "sede", "medico", "servicio",
    "procedencia", "fuerza", "eps", "afiliacion", "aseguradora", "regimen", "direccion",
    "telefono", "acompanante", "ocupacion", "estado civil", "religion", "nacionalidad",
}
_ACCENTS = str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")


def _is_noise(exam: str) -> bool:
    normalized = exam.translate(_ACCENTS).lower().strip()
    return any(term in normalized for term in _NOISE_TERMS)


def _compact(text: str) -> str:
    """Solo letras y números en minúscula y sin tildes: "PI-RADS" y "Pirads" quedan iguales."""
    plain = unicodedata.normalize("NFD", text)
    plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", plain.lower())


def strip_exam_prefix(value_raw: str, exam: str) -> str:
    """Quita el nombre del examen si el modelo lo dejó pegado al valor ("PIRADS 2" → "2").
    Solo se quita si después queda algo; un valor que ES el nombre se deja como está."""
    target = _compact(exam)
    if not target:
        return value_raw
    tokens = value_raw.strip().split()
    for k in range(1, len(tokens)):
        if _compact(" ".join(tokens[:k])) == target:
            rest = re.sub(r"^[:\-–]\s*", "", " ".join(tokens[k:])).strip()
            return rest or value_raw
    return value_raw


def _entry(raw: object) -> LabValue | None:
    if not isinstance(raw, dict):
        return None
    exam = _text(raw.get("exam"), 120)
    value_raw = _text(raw.get("value_raw"), 80)
    if not exam or not value_raw or _is_noise(exam):
        return None
    value_raw = strip_exam_prefix(value_raw, exam)
    date = raw.get("date")
    date = date.strip() if isinstance(date, str) and _DATE.match(date.strip()) else None
    return LabValue(
        exam=exam,
        value_raw=value_raw,
        value_numeric=_number(raw.get("value_numeric")),
        unit=_text(raw.get("unit"), 20),
        date=date,
        reference_low=_number(raw.get("reference_low")),
        reference_high=_number(raw.get("reference_high")),
        reference_text=_text(raw.get("reference_text"), 40),
    )


def dedupe_values(values: list[LabValue]) -> list[LabValue]:
    """Quita los valores idénticos (mismo examen, valor, unidad, fecha y referencia): el mismo dato repetido en
    varias partes del documento (tabla y conclusión) se muestra una sola vez."""
    seen: set[tuple] = set()
    unique: list[LabValue] = []
    for v in values:
        key = (_compact(v.exam), _compact(v.value_raw), (v.unit or "").lower(), v.date or "", v.reference_text or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return unique


def parse_values(text: str) -> list[LabValue]:
    try:
        data = json.loads(_clean(text))
    except ValueError:
        return []
    if isinstance(data, dict):
        data = data.get("values")
    if isinstance(data, dict):
        data = [data]  # el modelo a veces devuelve un solo objeto en vez de una lista
    if not isinstance(data, list):
        return []
    return [entry for item in data if (entry := _entry(item)) is not None]


_MALFORMED_MIN_CHARS = 30  # por debajo de esto, "{"values": []}" cuenta como respuesta genuina
_ATTEMPTS_PER_MODEL = 2  # un reintento si el modelo devuelve algo no vacío pero mal formado


def _call(
    model: str,
    text: str,
    settings: Settings,
    client: httpx.Client | None,
) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    call_settings = settings.model_copy(update={"max_output_tokens": settings.values_max_tokens})
    result = chat_completion(
        model, "text", messages, call_settings, client,
        response_format={"type": "json_object"},
        reasoning=NO_REASONING if settings.values_no_reasoning else None,
    )
    return str(result)


def _extract_from_section(
    text: str,
    settings: Settings,
    client: httpx.Client | None,
) -> list[LabValue]:
    if not text.strip():
        return []

    models = [settings.values_model]
    if settings.values_fallback_model and settings.values_fallback_model not in models:
        models.append(settings.values_fallback_model)

    last_error: VisionError | None = None
    for m_pos, model in enumerate(models):
        is_last_model = m_pos == len(models) - 1
        # Con un modelo de respaldo disponible no vale la pena esperar el
        # presupuesto completo de reintentos de uno saturado: se pasa al siguiente.
        model_settings = (
            settings if is_last_model else settings.model_copy(update={"max_retries": 2})
        )
        for attempt_no in range(_ATTEMPTS_PER_MODEL):
            is_last_attempt = is_last_model and attempt_no == _ATTEMPTS_PER_MODEL - 1
            try:
                raw = _call(model, text, model_settings, client)
            except VisionError as exc:
                if not exc.transient or is_last_attempt:
                    raise
                last_error = exc
                continue
            values = parse_values(raw)
            if values or len(raw.strip()) < _MALFORMED_MIN_CHARS:
                return values
            # el modelo respondió algo sustancial pero no parseable como JSON
            # (prosa, truncado): se reintenta antes de rendirse con esta sección
    return []


def extract_values(
    markdown: str,
    settings: Settings,
    client: httpx.Client | None = None,
) -> list[LabValue]:
    if not markdown.strip():
        return []

    # Se extrae sección por sección (el mismo corte que usa el bundle OKF) en vez de
    # mandar el documento completo de una vez: un documento con muchos exámenes hace
    # que el modelo trunque o deforme un JSON único demasiado largo.
    units = segment(markdown).units
    workers = max(1, min(settings.parallel_workers, len(units)))
    if workers == 1:
        per_section = [_extract_from_section(unit.text, settings, client) for unit in units]
    else:
        # Cada sección es una llamada independiente al modelo: en serie, un
        # documento con muchas secciones tarda la suma de todas.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            per_section = list(
                pool.map(lambda unit: _extract_from_section(unit.text, settings, client), units)
            )
    return dedupe_values([value for section in per_section for value in section])
