"""Orquesta el ciclo completo del agente: revisión proactiva -> plan -> ejecutar
cada paso -> sintetizar la respuesta final. Si un paso queda pendiente de
confirmación (una acción de escritura), se detiene ahí y le devuelve al
llamador un `resume_state` — un bulto de datos que el cliente debe guardar y
mandar de vuelta tal cual al confirmar/rechazar, para que se pueda retomar
justo donde quedó sin necesitar guardar la conversación completa del lado
del servidor (el checkpointer del ejecutor ya guarda esa parte)."""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg

from app.agent import executor, memory, planning
from app.agent.proactive import build_proactive_note
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.store import DocumentStore


log = logging.getLogger("medapp.agent.service")


def _retry_if_connection_lost(run):
    """Ejecuta `run()`; si la base de datos había cerrado la conexión (pasa tras un rato sin uso o si se reinicia),
    abre conexiones nuevas y lo intenta una vez más, en vez de devolverle un error 500 al paciente."""
    try:
        return run()
    except psycopg.OperationalError:
        log.warning("Conexión a la base perdida; se reconecta y se reintenta", exc_info=True)
        memory.reset_connections()
        return run()


@dataclass
class PendingConfirmation:
    tool: str
    args: dict[str, Any]
    description: str
    resume_state: dict[str, Any]


@dataclass
class AgentReply:
    status: str  # "done" | "needs_confirmation"
    reply: str | None = None
    pending: PendingConfirmation | None = None


def _memories(thread_id: str, settings: Settings) -> list[str]:
    """Lo que el agente recuerda de este paciente de conversaciones anteriores:
    el ejecutor lo recibe en su prompt, y aquí también el planificador y el
    sintetizador, para que el plan y la respuesta final lo tengan en cuenta."""
    user_id = executor._user_id_from_thread(thread_id)
    return memory.recall(memory.get_store(settings.database_url), user_id)


def _run_plan(
    thread_id: str,
    question: str,
    remaining: list[str],
    past_steps: list[list[str]],
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None,
) -> AgentReply:
    remaining = list(remaining)
    while remaining:
        step = remaining.pop(0)
        result = executor.run_step(step, thread_id, store, calendar, profile, settings, client)
        if not result.done:
            return AgentReply(
                status="needs_confirmation",
                pending=PendingConfirmation(
                    tool=result.pending_action.tool,
                    args=result.pending_action.args,
                    description=result.pending_action.description,
                    resume_state={
                        "thread_id": thread_id,
                        "question": question,
                        "current_step": step,
                        "remaining_plan": remaining,
                        "past_steps": past_steps,
                    },
                ),
            )
        past_steps.append([step, result.text])
    reply = planning.synthesize(
        question, [tuple(p) for p in past_steps], settings, client,
        memories=_memories(thread_id, settings),
    )
    return AgentReply(status="done", reply=reply)


def start(
    question: str,
    is_new_conversation: bool,
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None = None,
    thread_id: str | None = None,
) -> AgentReply:
    # El thread_id identifica la memoria del ejecutor (vía el checkpointer). Si
    # el llamador no manda uno, cada turno sería una conversación nueva sin
    # memoria de los turnos anteriores — por eso el frontend manda el id de su
    # conversación local, y aquí solo se genera uno nuevo como último recurso.
    thread_id = thread_id or uuid.uuid4().hex
    proactive_note = build_proactive_note(store, calendar) if is_new_conversation else None

    def run() -> AgentReply:
        steps = planning.plan(question, proactive_note, settings, client, memories=_memories(thread_id, settings))
        return _run_plan(thread_id, question, steps, [], store, calendar, profile, settings, client)

    return _retry_if_connection_lost(run)


def continue_after_confirmation(
    resume_state: dict[str, Any],
    decision: str,
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None = None,
    edited_args: dict[str, Any] | None = None,
) -> AgentReply:
    thread_id = resume_state["thread_id"]
    result = _retry_if_connection_lost(
        lambda: executor.resume_step(decision, thread_id, store, calendar, profile, settings, client, edited_args)
    )
    past_steps = list(resume_state["past_steps"])
    if not result.done:
        return AgentReply(
            status="needs_confirmation",
            pending=PendingConfirmation(
                tool=result.pending_action.tool,
                args=result.pending_action.args,
                description=result.pending_action.description,
                resume_state={**resume_state},
            ),
        )
    past_steps.append([resume_state["current_step"], result.text])
    return _retry_if_connection_lost(lambda: _run_plan(
        thread_id, resume_state["question"], resume_state["remaining_plan"], past_steps,
        store, calendar, profile, settings, client,
    ))
