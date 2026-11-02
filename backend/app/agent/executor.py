"""Ejecuta UN paso del plan usando un agente ReAct real de LangGraph
(`create_agent`), con las tools del paciente y confirmación humana antes de
cualquier acción de escritura (crear cita, guardar una pregunta, recordar un
dato para el futuro).

La memoria tiene dos piezas separadas (ver app/agent/memory.py), ambas sobre
el mismo Postgres del resto del sistema cuando hay una conexión disponible:
- El checkpointer (por thread_id) permite que una confirmación pendiente
  siga viva entre la llamada a /chat que la generó y la siguiente que la
  resuelve, y sobrevive a un reinicio del backend.
- El store (por paciente) es memoria de largo plazo: lo que el agente guarda
  ahí con la tool `remember_fact` sigue disponible en conversaciones nuevas,
  no solo en la que se guardó."""

from dataclasses import dataclass
from typing import Any

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI
from langgraph.types import Command

from app.agent import memory
from app.agent.clock import is_past, today_note
from app.agent.tools import WRITE_TOOLS, build_tools, document_report, mentioned_document
from app.calendar_store import CalendarStore
from app.config import Settings
from app.extraction.vision_client import provider_routing
from app.profile_store import ProfileStore
from app.store import DocumentStore

EXECUTOR_SYSTEM = """Eres el ejecutor de un asistente médico. Se te da UN paso \
concreto de un plan más grande (no la conversación completa); resuélvelo usando \
las herramientas disponibles si hace falta, y responde de forma breve con el \
resultado. No hables del "plan" ni de "pasos", solo resuelve lo que se te pide.

Fechas: si el paso trae una fecha ya resuelta (AAAA-MM-DD), úsala tal cual para `scheduled_at`; no la recalcules a partir de la fecha de otras citas del paciente. De una cita anterior copia solo lo que el paso pida (el médico, la hora), nunca su fecha.

Preguntas para el médico: redáctalas como preguntas claras y cortas, una sola idea por \
pregunta, en español normal (primera letra en mayúscula y el resto en minúsculas). Si citas \
exámenes, escribe sus nombres en minúsculas ("glóbulos blancos", no "GLOBULOS BLANCOS"); si son \
varios, haz una pregunta por examen o agrúpalos en una frase breve.

Datos del paciente: ante CUALQUIER pregunta sobre un resultado, valor o examen del paciente (linfocitos, glucosa, colesterol, plaquetas, "mi último examen"...), llama SIEMPRE primero a la herramienta get_exact_values, antes de responder. Nunca digas que no encontraste o que no tienes un dato sin haber consultado la herramienta. Si la herramienta responde que no encontró el examen, te da la lista de exámenes registrados: elige el que corresponde y vuelve a consultar. Si la pregunta es sobre lo que dijo el médico en las notas, usa search_narrative_history.

Documentos: si el paciente pide contar, resumir o explicar un documento por su nombre ("mi documento Prueba 2.pdf", "mi última historia", "lo que encontraste"), llama SIEMPRE a read_document con ese nombre (o con el nombre vacío para ver cuáles hay) y responde con lo que contiene. NUNCA digas que no puedes abrir o leer archivos: tienes esa herramienta.

Memoria: si en el paso el paciente cuenta un dato DURADERO sobre su salud que sirva \
para futuras conversaciones (una alergia, una enfermedad crónica, un medicamento que \
toma de forma habitual, una preferencia de atención) y todavía no está entre los \
recuerdos guardados, usa la herramienta remember_fact para proponer guardarlo; el \
paciente siempre debe confirmarlo. No la uses para datos pasajeros (un síntoma de hoy, \
una cita puntual) ni para datos que ya estén guardados."""


def _user_id_from_thread(thread_id: str) -> str:
    # main.py arma el thread_id como "{user_id}:{id_de_conversación}" antes de
    # llegar aquí (ver /agent/chat) — nunca lo manda el cliente directamente.
    return thread_id.split(":", 1)[0]


@dataclass
class PendingAction:
    tool: str
    args: dict[str, Any]
    description: str


@dataclass
class StepResult:
    done: bool
    text: str
    pending_action: PendingAction | None = None


def _build_agent(
    thread_id: str,
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None = None,
):
    user_id = _user_id_from_thread(thread_id)
    long_term_store = memory.get_store(settings.database_url)
    remembered = memory.recall(long_term_store, user_id)

    system_prompt = EXECUTOR_SYSTEM + "\n\n" + today_note(settings)
    if remembered:
        bullet_list = "\n".join(f"- {r}" for r in remembered)
        system_prompt += (
            "\n\nRecuerdos guardados de este paciente en conversaciones anteriores "
            f"(úsalos como contexto, no los repitas a menos que venga al caso):\n{bullet_list}"
        )

    # Este agente llama al modelo directo (no por chat_completion), así que el
    # enrutamiento por proveedor y "no guardar datos" se aplican aquí también: sin
    # esto la política de datos que se documenta no cubriría al agente.
    routing = provider_routing(settings)
    model = ChatOpenAI(
        model=settings.agent_model or settings.chat_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        max_tokens=settings.agent_max_output_tokens,
        timeout=settings.request_timeout_s,
        max_retries=1,
        temperature=0,  # el agente consulta datos y ejecuta acciones: mejor sin aleatoriedad
        extra_body={"provider": routing} if routing else None,
        # Una acción por turno: la tarjeta de confirmación muestra una sola, así que si el modelo
        # pidiera dos a la vez, la segunda quedaría sin respuesta del paciente.
        model_kwargs={"parallel_tool_calls": False},
    )
    tools = build_tools(store, calendar, profile, settings, client, long_term_store, user_id)
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[HumanInTheLoopMiddleware(interrupt_on={name: True for name in WRITE_TOOLS})],
        checkpointer=memory.get_checkpointer(settings.database_url),
        store=long_term_store,
    )


def _extract(result: dict) -> StepResult:
    interrupts = result.get("__interrupt__")
    if interrupts:
        request = interrupts[0].value["action_requests"][0]
        return StepResult(
            done=False,
            text=f"Esperando confirmación para: {request['name']}",
            pending_action=PendingAction(
                tool=request["name"],
                args=request.get("args", {}),
                description=request.get("description", ""),
            ),
        )
    last = result["messages"][-1]
    return StepResult(done=True, text=str(last.content or ""))


def run_step(
    step_text: str,
    thread_id: str,
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None = None,
) -> StepResult:
    agent = _build_agent(thread_id, store, calendar, profile, settings, client)
    config = {"configurable": {"thread_id": thread_id}}
    # Si el paso habla de un documento concreto ("Prueba 2.pdf", "mi última historia"), su contenido se le
    # entrega ya leído: así responde con él aunque no decida usar la herramienta, o aunque en esta misma
    # conversación haya dicho antes que no podía abrir archivos y tienda a repetirlo.
    named = mentioned_document(store, step_text)
    if named is not None:
        step_text += (
            "\n\n[Contenido del documento, ya leído por el sistema; úsalo para responder]\n"
            + document_report(store, named)
        )
    result = agent.invoke({"messages": [{"role": "user", "content": step_text}]}, config=config)
    return _correct_past_dates(agent, config, _extract(result), settings)


EXTRA_ACTION_REJECTED = (
    "Solo se confirma una acción a la vez y el paciente solo respondió por la primera. "
    "Si todavía hace falta esta otra, propónla de nuevo después."
)


def _hanging_count(agent, config: dict) -> int:
    """Cuántas acciones esperan confirmación en este hilo (el modelo puede haber pedido varias)."""
    count = 0
    for task in agent.get_state(config).tasks:
        for interrupt in task.interrupts:
            count += len(interrupt.value["action_requests"])
    return max(count, 1)


def _resume(agent, config: dict, first_decision: dict):
    """Responde a la primera acción pendiente con la decisión del paciente. LangChain exige una decisión
    por cada acción que quedó esperando; las demás se rechazan para que el hilo no quede trabado
    (antes, dos acciones pedidas a la vez daban error 500 al confirmar)."""
    extra = _hanging_count(agent, config) - 1
    decisions = [first_decision] + [{"type": "reject", "message": EXTRA_ACTION_REJECTED}] * extra
    return agent.invoke(Command(resume={"decisions": decisions}), config=config)


def _correct_past_dates(agent, config: dict, result: StepResult, settings: Settings) -> StepResult:
    """Si el modelo propone una cita en el pasado (se equivocó de año o de mes), se le
    rechaza ANTES de mostrarle la tarjeta al paciente y se le pide que la corrija."""
    for _ in range(2):
        pending = result.pending_action
        if not pending or pending.tool != "create_appointment":
            break
        if not is_past(pending.args.get("scheduled_at", ""), settings):
            break
        message = (
            f"La fecha {pending.args.get('scheduled_at')} ya pasó, así que no se agendó. "
            f"{today_note(settings)} Propón de nuevo la cita con la fecha futura correcta."
        )
        result = _extract(_resume(agent, config, {"type": "reject", "message": message}))
    return result


def _pending_tool_name(agent, config: dict) -> str:
    """Nombre de la acción que está esperando confirmación en este hilo."""
    for task in agent.get_state(config).tasks:
        for interrupt in task.interrupts:
            return interrupt.value["action_requests"][0]["name"]
    raise KeyError("No hay ninguna acción pendiente de confirmar en este hilo.")


def resume_step(
    decision: str,
    thread_id: str,
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None = None,
    edited_args: dict[str, Any] | None = None,
) -> StepResult:
    agent = _build_agent(thread_id, store, calendar, profile, settings, client)
    config = {"configurable": {"thread_id": thread_id}}
    if decision == "edit":
        # LangChain exige la acción completa (nombre + argumentos), no solo los
        # argumentos: sin `edited_action` la edición fallaba al leerse y el
        # paciente veía que "Confirmar cambios" no hacía nada.
        payload = {
            "type": "edit",
            "edited_action": {"name": _pending_tool_name(agent, config), "args": edited_args or {}},
        }
    elif decision == "reject":
        payload = {"type": "reject", "message": "El paciente no confirmó esta acción."}
    else:
        payload = {"type": "approve"}
    result = _resume(agent, config, payload)
    return _correct_past_dates(agent, config, _extract(result), settings)
