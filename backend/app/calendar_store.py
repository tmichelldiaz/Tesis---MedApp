import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.fsutil import read_json_safe, write_json_atomic

_UNSET = object()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CalendarStore:
    """Citas y preguntas para el médico. Las preguntas son su propia colección
    (no viven dentro de una cita): `appointment_id` puede ser None, para cuando
    el paciente (o el agente) anota algo que preguntar antes de tener una cita
    agendada. Se pueden asignar a una cita más tarde."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "appointments.json"
        # El archivo se crea al guardar la primera cita, no aquí: crearlo en cada petición hacía que dos peticiones
        # simultáneas se pisaran y dejaran el archivo vacío.

    def _write(self, data: dict) -> None:
        write_json_atomic(self.path, data)

    def _read(self) -> dict:
        data = read_json_safe(self.path, lambda: {"appointments": [], "questions": []})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("appointments", [])
        data.setdefault("questions", [])
        return data

    # ------------------------------------------------------------------ #
    # Citas
    # ------------------------------------------------------------------ #

    def list_appointments(self) -> list[dict]:
        return sorted(self._read()["appointments"], key=lambda a: a["scheduled_at"])

    def get_appointment(self, appt_id: str) -> dict | None:
        return next((a for a in self._read()["appointments"] if a["id"] == appt_id), None)

    def create_appointment(
        self,
        title: str,
        scheduled_at: str,
        doctor_name: str | None = None,
        location: str | None = None,
        notes: str | None = None,
    ) -> dict:
        data = self._read()
        appt = {
            "id": uuid.uuid4().hex,
            "title": title,
            "doctor_name": doctor_name,
            "location": location,
            "scheduled_at": scheduled_at,
            "notes": notes,
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["appointments"].append(appt)
        self._write(data)
        return appt

    def update_appointment(self, appt_id: str, **fields) -> dict:
        data = self._read()
        for appt in data["appointments"]:
            if appt["id"] == appt_id:
                appt.update(fields)
                appt["updated_at"] = _now()
                self._write(data)
                return appt
        raise KeyError(appt_id)

    def delete_appointment(self, appt_id: str) -> None:
        data = self._read()
        remaining = [a for a in data["appointments"] if a["id"] != appt_id]
        if len(remaining) == len(data["appointments"]):
            raise KeyError(appt_id)
        data["appointments"] = remaining
        # las preguntas de esa cita no se pierden: quedan sueltas de nuevo
        for question in data["questions"]:
            if question["appointment_id"] == appt_id:
                question["appointment_id"] = None
                question["updated_at"] = _now()
        self._write(data)

    # ------------------------------------------------------------------ #
    # Preguntas (colección propia, con o sin cita asignada)
    # ------------------------------------------------------------------ #

    def list_questions(self, appointment_id: str | None = _UNSET) -> list[dict]:
        questions = self._read()["questions"]
        if appointment_id is _UNSET:
            return questions
        return [q for q in questions if q["appointment_id"] == appointment_id]

    def get_question(self, question_id: str) -> dict | None:
        return next((q for q in self._read()["questions"] if q["id"] == question_id), None)

    def create_question(self, text: str, appointment_id: str | None = None) -> dict:
        data = self._read()
        if appointment_id is not None and not any(
            a["id"] == appointment_id for a in data["appointments"]
        ):
            raise KeyError(appointment_id)
        question = {
            "id": uuid.uuid4().hex,
            "text": text,
            "answered": False,
            "appointment_id": appointment_id,
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["questions"].append(question)
        self._write(data)
        return question

    def update_question(self, question_id: str, **fields) -> dict:
        data = self._read()
        new_appt_id = fields.get("appointment_id", _UNSET)
        if new_appt_id is not _UNSET and new_appt_id is not None and not any(
            a["id"] == new_appt_id for a in data["appointments"]
        ):
            raise KeyError(new_appt_id)
        for question in data["questions"]:
            if question["id"] == question_id:
                question.update(fields)
                question["updated_at"] = _now()
                self._write(data)
                return question
        raise KeyError(question_id)

    def delete_question(self, question_id: str) -> None:
        data = self._read()
        remaining = [q for q in data["questions"] if q["id"] != question_id]
        if len(remaining) == len(data["questions"]):
            raise KeyError(question_id)
        data["questions"] = remaining
        self._write(data)
