import json
import re

import httpx

from app.config import Settings
from app.extraction.vision_client import VisionError, chat_completion

# Lista fija y corta a propósito: un modelo gratuito clasifica de forma mucho
# más confiable entre 5 opciones fijas que inventando categorías libres (que
# con el tiempo terminan duplicadas, ej. "Colesterol" vs "colesterol alto").
CATEGORIES = [
    "Resultados de laboratorio",
    "Medicamentos",
    "Diagnósticos",
    "Notas de consulta",
    "Otro",
]

DEFAULT_CATEGORY = "Otro"

SYSTEM_PROMPT = """Eres un clasificador de documentos clínicos. Recibes el Markdown ya \
transcrito de un documento médico y decides a cuál de estas categorías pertenece:

- "Resultados de laboratorio": exámenes de sangre, orina u otros con valores numéricos \
o resultados discretos (hemograma, química sanguínea, perfil lipídico, uroanálisis, etc.).
- "Medicamentos": fórmulas médicas, recetas, listas de medicamentos con su dosis.
- "Diagnósticos": informes centrados en un diagnóstico o hallazgo clínico (informes de \
imágenes diagnósticas, informes de especialista, resúmenes de diagnóstico), donde lo \
importante es la conclusión clínica, no un número.
- "Notas de consulta": notas generales de una consulta médica, evolución, anamnesis, \
recomendaciones del médico, sin que domine ni un resultado de laboratorio ni un \
diagnóstico puntual.
- "Otro": cualquier documento que no encaje claramente en las anteriores.

Responde ÚNICAMENTE con un objeto JSON de esta forma exacta, sin explicación ni bloque de \
código:
{"category": "<una de las 5 categorías, tal cual como está escrita arriba>"}"""

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def _clean(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _parse(text: str) -> str | None:
    """Devuelve la categoría si el texto es JSON válido con una categoría conocida,
    o None si el texto no se pudo interpretar (para que el llamador decida si vale
    la pena reintentar en vez de rendirse de una)."""
    try:
        data = json.loads(_clean(text))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    category = data.get("category")
    return category if category in CATEGORIES else None


_MALFORMED_MIN_CHARS = 20  # por debajo de esto, una respuesta rara igual se acepta
_ATTEMPTS_PER_MODEL = 2  # un reintento si el modelo "piensa en voz alta" y no llega al JSON


def classify_category(
    markdown: str,
    settings: Settings,
    client: httpx.Client | None = None,
) -> str:
    text = markdown.strip()
    if not text:
        return DEFAULT_CATEGORY

    models = [settings.category_model]
    if settings.category_fallback_model and settings.category_fallback_model not in models:
        models.append(settings.category_fallback_model)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text[: settings.category_input_chars]},
    ]
    call_settings = settings.model_copy(update={"max_output_tokens": settings.category_max_tokens})

    last_error: VisionError | None = None
    for m_pos, model in enumerate(models):
        is_last_model = m_pos == len(models) - 1
        for attempt_no in range(_ATTEMPTS_PER_MODEL):
            is_last_attempt = is_last_model and attempt_no == _ATTEMPTS_PER_MODEL - 1
            attempt = call_settings if is_last_model else call_settings.model_copy(update={"max_retries": 2})
            try:
                raw = str(chat_completion(
                    model, "text", messages, attempt, client,
                    response_format={"type": "json_object"},
                ))
            except VisionError as exc:
                if not exc.transient or is_last_attempt:
                    raise
                last_error = exc
                continue
            category = _parse(raw)
            if category is not None:
                return category
            if len(raw.strip()) < _MALFORMED_MIN_CHARS or is_last_attempt:
                return DEFAULT_CATEGORY
            # respuesta no vacía pero no parseable (el modelo "pensó" y no llegó
            # al JSON): se reintenta antes de rendirse a "Otro"
    return DEFAULT_CATEGORY
