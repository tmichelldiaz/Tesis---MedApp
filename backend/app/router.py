import json
import re
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.extraction.vision_client import VisionError, chat_completion

SYSTEM_PROMPT = """Eres un enrutador de consultas para un asistente médico. Dada la \
pregunta de un paciente, decides qué fuentes de información hay que consultar antes de \
responder.

Responde ÚNICAMENTE con un objeto JSON de esta forma exacta, sin explicación ni bloque de \
código:
{"use_values": <true|false>, "use_rag": <true|false>}

- "use_values" = true cuando la pregunta pide un dato exacto, puntual y verificable de la \
historia del paciente: un resultado de laboratorio, un medicamento y su dosis, una \
alergia, el tipo de sangre, un diagnóstico, o una comparación entre resultados de \
distintas fechas.
- "use_rag" = true cuando la pregunta es exploratoria o busca algo en el texto libre de \
las notas: síntomas mencionados en el pasado, observaciones o recomendaciones del \
médico, contexto narrativo, o cualquier cosa que no se responda con un valor exacto.
- Ambas pueden ser true a la vez (ej: "compara mi glucosa con la anterior y dime si \
debería preocuparme" necesita el valor exacto Y el contexto).
- Ambas son false solo cuando la pregunta es de conocimiento general y no depende de la \
historia clínica de este paciente (ej: "¿qué es la glucosa?").

Ejemplos:
"¿Cuál fue mi resultado de LDL?" -> {"use_values": true, "use_rag": false}
"¿Qué medicamentos tomo actualmente?" -> {"use_values": true, "use_rag": false}
"¿Alguna vez mencioné mareos en consultas anteriores?" -> {"use_values": false, "use_rag": true}
"¿Qué anotó el médico sobre mi dolor de espalda?" -> {"use_values": false, "use_rag": true}
"¿Cómo voy con mi colesterol, ha mejorado?" -> {"use_values": true, "use_rag": true}
"¿Qué es la hemoglobina glicosilada?" -> {"use_values": false, "use_rag": false}"""

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


@dataclass(frozen=True)
class RouteDecision:
    use_values: bool
    use_rag: bool


def _clean(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _parse(text: str) -> RouteDecision:
    try:
        data = json.loads(_clean(text))
    except ValueError:
        return RouteDecision(use_values=True, use_rag=True)
    if not isinstance(data, dict):
        return RouteDecision(use_values=True, use_rag=True)
    return RouteDecision(
        use_values=bool(data.get("use_values", True)),
        use_rag=bool(data.get("use_rag", True)),
    )


def classify(
    question: str,
    settings: Settings,
    client: httpx.Client | None = None,
) -> RouteDecision:
    question = question.strip()
    if not question:
        return RouteDecision(use_values=False, use_rag=False)

    models = [settings.router_model]
    if settings.router_fallback_model and settings.router_fallback_model not in models:
        models.append(settings.router_fallback_model)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    call_settings = settings.model_copy(update={"max_output_tokens": settings.router_max_tokens})

    last_error: VisionError | None = None
    for position, model in enumerate(models):
        is_last = position == len(models) - 1
        attempt = call_settings if is_last else call_settings.model_copy(update={"max_retries": 2})
        try:
            result = chat_completion(
                model, "text", messages, attempt, client,
                response_format={"type": "json_object"},
            )
        except VisionError as exc:
            if not exc.transient or is_last:
                raise
            last_error = exc
            continue
        return _parse(str(result))
    assert last_error is not None
    raise last_error
