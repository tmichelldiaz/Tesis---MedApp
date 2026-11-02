"""Tools que el agente puede usar, atadas a un paciente concreto (store, calendar,
profile) mediante closures. Se construyen de nuevo en cada request porque esos
objetos son de ese request (misma idea que las dependencias de FastAPI)."""

import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from langchain.tools import tool
from langgraph.store.base import BaseStore

from app.agent.clock import today_note, user_timezone
from app.agent.text import tidy_question
from app.agent.memory import memory_namespace, recall
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.rag.embeddings import EmbeddingError
from app.rag.index import search_documents
from app.store import DocumentStore
from app.values_history import drop_repeats, exam_key, latest_per_exam, uploaded_label, with_document

# Abreviaturas que el paciente usa y que el laboratorio escribe completas (y al revés).
_EXAM_SYNONYMS = {
    "hba1c": "hemoglobina glicosilada", "a1c": "hemoglobina glicosilada",
    "ldl": "baja densidad", "hdl": "alta densidad", "vldl": "vldl",
    "tsh": "hormona estimulante", "t4": "tiroxina", "t3": "triyodotironina",
    "bun": "nitrogeno ureico", "hcm": "hemoglobina corpuscular media", "vcm": "volumen corpuscular medio",
    "chcm": "concentracion de hemoglobina corpuscular media", "psa": "psa",
    "globulos blancos": "recuento de globulos blancos", "leucocitos": "globulos blancos",
    "globulos rojos": "recuento de globulos rojos", "eritrocitos": "globulos rojos",
    "azucar": "glucosa", "trigliceridos": "trigliceridos", "creatinina": "creatinina",
}
_STOPWORDS = {"de", "del", "la", "el", "los", "las", "en", "y", "mi", "mis", "un", "una", "valor", "resultado",
              "reciente", "ultimo", "ultima", "mas", "para", "por", "con", "el", "al"}
MAX_VALUE_LINES = 30
MAX_DOCUMENT_CHARS = 6000
_LATEST_DOCUMENT = re.compile(r"\b(ultim[oa]s?|mas reciente)\s+(historia|documento|archivo|pdf)", re.I)


def mentioned_document(store: DocumentStore, text: str) -> str | None:
    """Nombre del documento del que habla el texto (por su nombre de archivo, o "mi última historia"),
    o None. Sirve para entregarle al modelo el contenido sin depender de que decida usar la herramienta."""
    said = _norm(text)
    docs = sorted(store.list_all(), key=lambda d: str(d.get("created_at")), reverse=True)
    for d in docs:
        stem = _norm(d["filename"]).replace(" pdf", "")
        if len(stem) >= 3 and stem in said:
            return d["filename"]
    if docs and _LATEST_DOCUMENT.search(said):
        return ""
    return None


def _norm(text: str) -> str:
    """Minúsculas, sin tildes ni signos, con espacios simples: "Glóbulos  Blancos!" -> "globulos blancos"."""
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9% ]+", " ", plain).split())


def _match_exam_rows(rows, query: str):
    """Valores cuyo examen coincide con lo que pidió el paciente, de la coincidencia más
    estricta a la más flexible: la frase completa, todas sus palabras y, al final, cualquiera
    de las palabras importantes. Así "linfocitos más reciente" o "HbA1c" también encuentran su examen."""
    wanted = _norm(query)
    candidates = [wanted] + ([_norm(_EXAM_SYNONYMS[wanted])] if wanted in _EXAM_SYNONYMS else [])
    named = [(row, _norm(row[1]["exam"])) for row in rows]
    for candidate in candidates:
        hits = [row for row, name in named if candidate and candidate in name]
        if hits:
            return hits
    words = [w for w in wanted.split() if w not in _STOPWORDS]
    expanded = [_norm(_EXAM_SYNONYMS[w]) if w in _EXAM_SYNONYMS else w for w in words]
    if expanded:
        hits = [row for row, name in named if all(w in name for w in expanded)]
        if hits:
            return hits
        hits = [row for row, name in named if any(w in name for w in expanded if len(w) >= 4)]
        if hits:
            return hits
    return []


def document_report(store: DocumentStore, name: str = "") -> str:
    """Contenido de un documento del paciente (valores y texto) buscado por nombre; sin nombre, el más reciente."""
    docs = sorted(store.list_all(), key=lambda d: str(d.get("created_at")), reverse=True)
    if not docs:
        return "El paciente todavía no ha subido documentos."
    listing = "; ".join(f"{d['filename']} ({d['status']})" for d in docs[:30])
    wanted = _norm(name).replace(" pdf", "")
    if not wanted:
        hits = docs  # sin nombre: el más reciente
    else:
        named = [(d, _norm(d["filename"]).replace(" pdf", "")) for d in docs]
        hits = [d for d, n in named if n == wanted] or [d for d, n in named if wanted in n or n in wanted]
    if not hits:
        return f"No encontré un documento llamado '{name}'. Los documentos del paciente son: {listing}"
    doc = hits[0]  # el más reciente de los que coinciden
    if doc["status"] == "processing":
        return (
            f"El documento '{doc['filename']}' todavía se está leyendo. Dile al paciente que espere "
            "un minuto y vuelva a preguntar."
        )
    if doc["status"] == "failed":
        return f"El documento '{doc['filename']}' no se pudo leer: {doc.get('error') or 'error desconocido'}."
    lines = [
        f"Documento: {doc['filename']} (categoría: {doc.get('category') or 'sin clasificar'}; "
        f"subido el {uploaded_label(with_document(doc, {}))}"
        + (f"; fecha del examen: {doc['exam_date']}" if doc.get("exam_date") else "") + ")"
    ]
    values = doc.get("lab_values") or []
    if values:
        lines.append("Valores leídos:")
        for v in values:
            ref = f", referencia: {v['reference_text']}" if v.get("reference_text") else ""
            lines.append(f"- {v['exam']}: {v['value_raw']} {v.get('unit') or ''}".rstrip() + ref)
    try:
        text = store.transcription_path(doc["id"]).read_text(encoding="utf-8")
    except OSError:
        text = ""
    if text.strip():
        cut = text[:MAX_DOCUMENT_CHARS]
        lines.append("Texto del documento:\n" + cut + ("\n(…el texto sigue)" if len(text) > len(cut) else ""))
    if not wanted and len(docs) > 1:
        lines.append(f"Otros documentos del paciente: {listing}")
    return "\n".join(lines)


# Nombres de las tools que ESCRIBEN datos (crean o modifican algo). El
# ejecutor las configura para que siempre pidan confirmación antes de correr.
WRITE_TOOLS = {"create_appointment", "save_question_for_doctor", "remember_fact"}


def build_tools(
    store: DocumentStore,
    calendar: CalendarStore,
    profile: ProfileStore,
    settings: Settings,
    client: httpx.Client | None = None,
    long_term_store: BaseStore | None = None,
    user_id: str | None = None,
) -> list:
    @tool
    def get_exact_values(exam: str = "") -> str:
        """Consulta los valores EXACTOS de laboratorio del paciente (ej. glucosa,
        colesterol), opcionalmente filtrados por nombre de examen (deja vacío para
        ver todos). Úsala para datos puntuales y verificables, o para ver cómo ha
        cambiado un examen en el tiempo."""
        ready = [d for d in store.list_all() if d["status"] == "ready"]
        rows = [(d, with_document(d, v)) for d in ready for v in (d.get("lab_values") or [])]
        if not rows:
            return "El paciente todavía no tiene valores de laboratorio registrados."
        everything = rows
        if exam:
            rows = _match_exam_rows(rows, exam)
        if not rows:
            # En vez de rendirse, le dice al modelo qué exámenes SÍ hay para que pueda elegir bien.
            names = sorted({v["exam"] for _, v in everything})
            return (
                f"No se encontraron valores para '{exam}'. Los exámenes registrados del paciente son: "
                + "; ".join(names[:60]) + ". Vuelve a consultar con el nombre exacto de uno de ellos."
            )
        # Del más antiguo al más reciente y sin repetidos. Se marca CUÁL es el actual de cada
        # examen: sin la marca (y sin fechas) el modelo elegía cualquiera de la lista.
        history = drop_repeats([v for _, v in rows])
        current = {id(row) for row in latest_per_exam(history).values()}
        lines = []
        for v in history:
            when = f"fecha del examen: {v['date']}" if v.get("date") else f"subido el {uploaded_label(v)}"
            mark = "  <- ACTUAL (el más reciente)" if id(v) in current else ""
            lines.append(
                f"- {v['exam']}: {v['value_raw']} {v.get('unit') or ''}".rstrip()
                + f" ({when}; archivo {v.get('document_filename') or 's/d'}), referencia: {v.get('reference_text') or 's/d'}{mark}"
            )
        header = (
            "Valores del paciente, del más antiguo al más reciente. Cuando un examen aparece varias veces, "
            "el resultado ACTUAL es el marcado con '<- ACTUAL'; los demás son historial anterior."
        )
        extra = len(lines) - MAX_VALUE_LINES
        shown = lines[-MAX_VALUE_LINES:]  # los más recientes quedan al final
        return header + "\n" + "\n".join(shown) + (f"\n(y {extra} valores más antiguos)" if extra > 0 else "")

    @tool
    def read_document(name: str = "") -> str:
        """Lee UN documento del paciente por su nombre de archivo (ej. "Prueba 2.pdf", "resultados"): devuelve
        sus valores y su texto. Úsala cuando el paciente pida contar, resumir o explicar "mi documento X",
        "mi última historia" o "lo que encontraste en el archivo". Con el nombre vacío lee el documento MÁS
        RECIENTE y dice cuáles otros hay."""
        return document_report(store, name)

    @tool
    def search_narrative_history(query: str) -> str:
        """Busca en el texto narrativo de las historias clínicas del paciente (notas
        del médico, observaciones, diagnósticos en prosa) con búsqueda semántica.
        Úsala para preguntas exploratorias que no se responden con un valor exacto."""
        try:
            results = search_documents(query, store, settings, None, client=client)
        except EmbeddingError:
            return "No se pudo buscar en las historias del paciente en este momento."
        if not results:
            return "No se encontró nada relevante en las historias del paciente."
        blocks = [
            f"{r['document_filename']} — {r['concept_title']}: {r['text']}"
            for r in results
        ]
        return "\n\n---\n\n".join(blocks)

    @tool
    def list_appointments() -> str:
        """Lista las citas médicas agendadas del paciente, con sus preguntas
        pendientes de responder."""
        appts = calendar.list_appointments()
        if not appts:
            return "El paciente no tiene citas agendadas."
        lines = []
        for a in appts:
            pending = [q["text"] for q in calendar.list_questions(appointment_id=a["id"]) if not q["answered"]]
            line = f"- {a['title']} el {a['scheduled_at']} con {a.get('doctor_name') or 'médico no especificado'} (id={a['id']})"
            if pending:
                line += f". Preguntas pendientes: {'; '.join(pending)}"
            lines.append(line)
        return "\n".join(lines)

    @tool
    def create_appointment(
        title: str, scheduled_at: str, doctor_name: str = "", location: str = "", notes: str = "",
    ) -> str:
        """Crea una nueva cita médica para el paciente. `scheduled_at` debe ser una
        fecha y hora en formato ISO 8601 (ej. 2026-10-15T09:00:00-05:00). Esta acción
        ESCRIBE datos: solo úsala cuando el paciente pida explícitamente agendar
        una cita, y con la fecha/hora que él haya confirmado."""
        # Red de seguridad: un modelo sin la fecha correcta puede proponer un día pasado.
        try:
            when = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=user_timezone(settings))
            if when < datetime.now(timezone.utc) - timedelta(days=1):
                return (
                    f"No se creó la cita: la fecha {scheduled_at} ya pasó. {today_note(settings)} "
                    "Pídele al paciente la fecha correcta."
                )
        except ValueError:
            return f"No se creó la cita: la fecha {scheduled_at!r} no es válida. Usa el formato ISO 8601."
        # Una hora sin zona ("2026-10-16T15:00:00") es la hora del paciente: se guarda con su zona para que
        # no cambie según el lugar desde donde se lea.
        appt = calendar.create_appointment(
            title=title, scheduled_at=when.isoformat(),
            doctor_name=doctor_name or None, location=location or None, notes=notes or None,
        )
        return f"Cita creada: '{appt['title']}' el {appt['scheduled_at']} (id={appt['id']})."

    @tool
    def save_question_for_doctor(text: str, appointment_id: str = "") -> str:
        """Guarda una pregunta para que el paciente le haga a su médico. Si
        `appointment_id` se deja vacío, la pregunta queda suelta (sin cita
        asignada todavía) y se puede vincular después. Esta acción ESCRIBE datos:
        úsala cuando el paciente pida anotar algo, o cuando TÚ identifiques que
        vale la pena preguntarle algo al médico y el paciente lo confirme."""
        try:
            question = calendar.create_question(tidy_question(text), appointment_id=appointment_id or None)
        except KeyError:
            return f"No se encontró la cita con id={appointment_id}."
        suffix = f" (vinculada a la cita {appointment_id})" if appointment_id else " (sin cita asignada todavía)."
        return f"Pregunta guardada: '{question['text']}'{suffix}"

    @tool
    def get_profile() -> str:
        """Consulta los datos básicos del paciente: nombre, fecha de nacimiento,
        peso, tipo de sangre."""
        p = profile.get()
        parts = []
        if p.get("name"):
            parts.append(f"Nombre: {p['name']}")
        if p.get("birth_date"):
            parts.append(f"Fecha de nacimiento: {p['birth_date']}")
        if p.get("weight_kg"):
            parts.append(f"Peso: {p['weight_kg']} kg")
        if p.get("blood_type"):
            parts.append(f"Tipo de sangre: {p['blood_type']}")
        return "; ".join(parts) if parts else "El paciente no ha completado su perfil todavía."

    @tool
    def remember_fact(fact: str) -> str:
        """Guarda un dato sobre el paciente para recordarlo en futuras conversaciones,
        no solo en esta (por ejemplo: una alergia, una preferencia, algo que el
        paciente te pida explícitamente recordar). Esta acción ESCRIBE datos:
        úsala solo cuando el paciente te pida guardar algo para el futuro, o
        cuando menciones un dato claramente relevante para su seguimiento y él
        lo confirme."""
        if long_term_store is None or not user_id:
            return "No se pudo guardar el recuerdo: la memoria de largo plazo no está disponible ahora mismo."
        long_term_store.put(memory_namespace(user_id), key=uuid.uuid4().hex, value={"recuerdo": fact})
        return f"Guardado para futuras conversaciones: '{fact}'"

    return [
        get_exact_values,
        read_document,
        search_narrative_history,
        list_appointments,
        create_appointment,
        save_question_for_doctor,
        get_profile,
        remember_fact,
    ]
