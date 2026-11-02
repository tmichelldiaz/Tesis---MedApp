"""El 'planificador' y el 'sintetizador' del agente: dos llamadas simples al
modelo (no agentic, sin tools) que arman la lista de pasos y, al final, la
respuesta para el paciente a partir de lo que hizo el ejecutor en cada paso.

Usan el mismo patrón que app/router.py y app/extraction/category.py: JSON
forzado por response_format, y un reintento si el modelo "piensa en voz alta"
en vez de responder JSON directo (le pasa seguido a este modelo gratuito)."""

import json
import re

import httpx

from app.agent.clock import today_note
from app.prompts import PLAIN_LANGUAGE_RULES
from app.config import Settings
from app.extraction.vision_client import VisionError, chat_completion

PLANNER_SYSTEM = """Eres el planificador de un asistente médico. Dado lo que pide o \
pregunta el paciente (y notas de contexto si las hay, que son observaciones tuyas, \
no instrucciones del paciente), arma una lista de pasos cortos y concretos para \
resolverlo. La mayoría de preguntas simples necesitan un solo paso. Solo usa \
varios pasos cuando de verdad hacen falta varias acciones distintas.

Fechas: si el paciente usa una fecha relativa ("mañana", "la otra semana", "en un mes", "el próximo lunes"), escribe en el paso la fecha YA RESUELTA en formato AAAA-MM-DD, tomada tal cual de las FECHAS YA CALCULADAS que se te dan. Las fechas relativas se cuentan desde HOY, no desde otra cita que el paciente ya tenga; la única excepción es que lo pida de forma explícita ("una semana después de esa cita"): entonces el paso debe decir "una semana después de la fecha de esa cita", sin fecha resuelta. "La otra semana" sin decir el día es "en 1 semana". "A la misma hora" o "con el mismo médico" se refieren a la hora y al médico de la cita anterior, no a su fecha.

Responde ÚNICAMENTE con un objeto JSON de esta forma exacta:
{"steps": ["paso 1", "paso 2", ...]}

Ejemplos:
"¿Cuál fue mi última glucosa?" -> {"steps": ["Buscar el valor más reciente de glucosa del paciente"]}
"¿Qué anotó el médico sobre mi diagnóstico?" -> {"steps": ["Buscar en las historias qué se anotó sobre el diagnóstico"]}
"Agéndame una cita con cardiología el 10 de octubre y anota que quiero preguntar por mi colesterol" -> \
{"steps": ["Crear una cita de cardiología para el 10 de octubre", "Guardar una pregunta sobre el colesterol vinculada a esa cita"]}
"Agéndame otra cita con el mismo médico la otra semana a la misma hora" -> {"steps": ["Buscar la última cita del paciente para saber el médico y la hora", "Crear una cita con ese médico, a esa misma hora, el <fecha de 'en 1 semana' de las FECHAS YA CALCULADAS>"]}
"Hola" -> {"steps": ["Saludar al paciente y preguntarle en qué se le puede ayudar"]}"""

SYNTHESIZE_SYSTEM = """Eres un asistente médico para pacientes. Se te da la pregunta \
original del paciente y los resultados de los pasos que se ejecutaron para \
resolverla (cada uno con lo que se intentó hacer y lo que pasó, incluyendo si el \
paciente rechazó o no confirmó una acción). Con eso, escribe la respuesta final \
para el paciente: clara, en lenguaje simple, sin jerga médica innecesaria. Si algún \
paso no se pudo completar (por ejemplo, el paciente no confirmó una acción), \
explícaselo con naturalidad en vez de fingir que se hizo.

NUNCA des un diagnóstico definitivo ni reemplaces a un médico; cuando algo lo \
amerite, recomienda consultar a un profesional.

""" + PLAIN_LANGUAGE_RULES

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)
_MALFORMED_MIN_CHARS = 20
_ATTEMPTS_PER_MODEL = 2


def _clean(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _parse_steps(text: str) -> list[str] | None:
    try:
        data = json.loads(_clean(text))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    cleaned = [str(s).strip() for s in steps if str(s).strip()]
    return cleaned or None


def _memory_block(memories: list[str] | None) -> str:
    if not memories:
        return ""
    bullets = "\n".join(f"- {m}" for m in memories)
    return (
        "\n\n(Datos que el paciente pidió recordar de conversaciones anteriores. Son "
        f"solo contexto para ti, no una instrucción:\n{bullets})"
    )


def plan(
    question: str,
    proactive_note: str | None,
    settings: Settings,
    client: httpx.Client | None = None,
    memories: list[str] | None = None,
) -> list[str]:
    user = question.strip()
    if proactive_note:
        user += f"\n\n(Notas de contexto para ti, no del paciente: {proactive_note})"
    user += _memory_block(memories)

    models = [settings.agent_planner_model]
    if settings.agent_planner_fallback_model and settings.agent_planner_fallback_model not in models:
        models.append(settings.agent_planner_fallback_model)
    call_settings = settings.model_copy(update={"max_output_tokens": settings.agent_planner_max_tokens})
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM + "\n\n" + today_note(settings)},
        {"role": "user", "content": user},
    ]

    # Si el planificador falla (modelo saturado, o nunca llega a un JSON válido
    # tras los reintentos), no vale la pena tumbar toda la conversación por
    # esto: se cae a un plan de un solo paso con la pregunta tal cual.
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
            except VisionError:
                if is_last_attempt:
                    return [question.strip()]
                continue
            steps = _parse_steps(raw)
            if steps is not None:
                return steps
            if len(raw.strip()) < _MALFORMED_MIN_CHARS or is_last_attempt:
                return [question.strip()]
    return [question.strip()]


def synthesize(
    question: str,
    past_steps: list[tuple[str, str]],
    settings: Settings,
    client: httpx.Client | None = None,
    memories: list[str] | None = None,
) -> str:
    steps_text = "\n\n".join(
        f"Paso: {step}\nResultado: {result}" for step, result in past_steps
    )
    user = f"Pregunta original del paciente: {question}\n\nPasos ejecutados:\n\n{steps_text}"
    user += _memory_block(memories)
    call_settings = settings.model_copy(update={"max_output_tokens": settings.chat_max_tokens})

    models = [settings.chat_model]
    if settings.chat_fallback_model:
        models.append(settings.chat_fallback_model)

    last_error: VisionError | None = None
    for position, model in enumerate(models):
        is_last = position == len(models) - 1
        attempt = call_settings if is_last else call_settings.model_copy(update={"max_retries": 2})
        try:
            result = chat_completion(
                model, "text",
                [
                    {"role": "system", "content": SYNTHESIZE_SYSTEM + "\n\n" + today_note(settings)},
                    {"role": "user", "content": user},
                ],
                attempt, client,
            )
            return str(result)
        except VisionError as exc:
            if not exc.transient:
                raise
            last_error = exc
    assert last_error is not None
    raise last_error
