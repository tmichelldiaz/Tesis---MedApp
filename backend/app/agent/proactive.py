"""Revisión proactiva: qué debería contarle el agente al paciente sin que se lo
pida, apenas empieza una conversación nueva. Es determinística (sin LLM) a
propósito: son hechos que se pueden calcular directamente, no algo que valga
la pena gastar una llamada al modelo en decidir."""

from datetime import datetime, timezone

from app.calendar_store import CalendarStore
from app.store import DocumentStore


def _parse(iso: str) -> datetime | None:
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)  # sin zona no se puede comparar con "ahora"


def build_proactive_note(store: DocumentStore, calendar: CalendarStore) -> str | None:
    now = datetime.now(timezone.utc)
    notes: list[str] = []

    appointments = {a["id"]: a for a in calendar.list_appointments()}

    for appt in appointments.values():
        when = _parse(appt["scheduled_at"])
        if when and when < now:
            notes.append(
                f"La cita '{appt['title']}' del {appt['scheduled_at']} ya pasó; "
                "pregúntale al paciente cómo le fue o si necesita reagendar."
            )

    for question in calendar.list_questions():
        if question["answered"]:
            continue
        appt_id = question["appointment_id"]
        if appt_id is None:
            notes.append(
                f"El paciente tiene una pregunta suelta sin cita asignada: "
                f"'{question['text']}'. Considera preguntarle si ya agendó una cita para hacerla."
            )
            continue
        appt = appointments.get(appt_id)
        when = _parse(appt["scheduled_at"]) if appt else None
        if appt and when and when < now:
            notes.append(
                f"El paciente tenía pendiente preguntarle a su médico: '{question['text']}' "
                f"en la cita '{appt['title']}', que ya pasó. Pregúntale si ya tuvo respuesta."
            )

    ready = [d for d in store.list_all() if d["status"] == "ready"]
    out_of_range: list[str] = []
    seen: set[str] = set()
    for doc in ready:
        for value in doc.get("lab_values") or []:
            exam = value["exam"]
            if exam in seen:
                continue
            num = value.get("value_numeric")
            low, high = value.get("reference_low"), value.get("reference_high")
            if num is None or (low is None and high is None):
                continue
            if (low is not None and num < low) or (high is not None and num > high):
                out_of_range.append(exam)
                seen.add(exam)
    if out_of_range:
        notes.append(
            f"Estos exámenes del paciente están fuera de rango: {', '.join(out_of_range[:5])}."
        )

    return "\n".join(notes) if notes else None


def build_user_notices(store: DocumentStore, calendar: CalendarStore) -> list[dict]:
    """Misma detección que build_proactive_note, pero en texto dirigido
    al propio paciente (no instrucciones para el agente) y como lista
    estructurada — para mostrarse en la campana de notificaciones."""
    now = datetime.now(timezone.utc)
    notices: list[dict] = []

    appointments = {a["id"]: a for a in calendar.list_appointments()}

    for appt in appointments.values():
        when = _parse(appt["scheduled_at"])
        if when and when < now:
            notices.append({
                "type": "appointment",
                "text": f"Tu cita '{appt['title']}' ya pasó. ¿Cómo te fue? Puedes reagendarla si la necesitas.",
            })

    for question in calendar.list_questions():
        if question["answered"]:
            continue
        appt_id = question["appointment_id"]
        if appt_id is None:
            notices.append({
                "type": "question",
                "text": f"Tienes una pregunta pendiente sin cita asignada: '{question['text']}'.",
            })
            continue
        appt = appointments.get(appt_id)
        when = _parse(appt["scheduled_at"]) if appt else None
        if appt and when and when < now:
            notices.append({
                "type": "question",
                "text": f"Tenías pendiente preguntarle a tu médico: '{question['text']}' en tu cita '{appt['title']}'.",
            })

    ready = [d for d in store.list_all() if d["status"] == "ready"]
    out_of_range: list[str] = []
    seen: set[str] = set()
    for doc in ready:
        for value in doc.get("lab_values") or []:
            exam = value["exam"]
            if exam in seen:
                continue
            num = value.get("value_numeric")
            low, high = value.get("reference_low"), value.get("reference_high")
            if num is None or (low is None and high is None):
                continue
            if (low is not None and num < low) or (high is not None and num > high):
                out_of_range.append(exam)
                seen.add(exam)
    if out_of_range:
        notices.append({
            "type": "lab",
            "text": f"Estos exámenes están fuera de rango: {', '.join(out_of_range[:5])}. Coméntalo con tu médico.",
        })

    return notices
