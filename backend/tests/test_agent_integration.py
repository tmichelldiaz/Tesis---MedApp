"""Pruebas de integración de verdad contra OpenRouter (requieren
OPENROUTER_API_KEY en el entorno). No corren en `pytest` normal —
usa `pytest -m integration` para incluirlas."""

import uuid

import pytest

from app.agent import executor, service
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.store import DocumentStore

pytestmark = pytest.mark.integration


def make_settings(tmp_path, **kw) -> Settings:
    # A diferencia del resto de tests (que mockean el cliente HTTP y por eso
    # usan una api_key falsa con _env_file=None), estas pruebas sí llaman a
    # OpenRouter de verdad, así que necesitan la key real del .env.
    return Settings(data_dir=tmp_path, **kw)


def make_stores(tmp_path):
    return DocumentStore(tmp_path), CalendarStore(tmp_path), ProfileStore(tmp_path)


class TestRunStep:
    def test_a_read_only_step_completes_without_interruption(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        result = executor.run_step(
            "Saluda al paciente brevemente.", uuid.uuid4().hex, store, calendar, profile, settings,
        )
        assert result.done is True
        assert result.pending_action is None

    def test_a_write_step_pauses_for_confirmation(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        result = executor.run_step(
            "Agenda una cita de cardiología para el 2026-11-15T09:00:00-05:00.",
            uuid.uuid4().hex, store, calendar, profile, settings,
        )
        assert result.done is False
        assert result.pending_action is not None
        assert result.pending_action.tool == "create_appointment"
        assert calendar.list_appointments() == []  # no se creó hasta confirmar

    def test_approving_resumes_and_creates_the_appointment(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        thread_id = uuid.uuid4().hex
        paused = executor.run_step(
            "Agenda una cita de cardiología para el 2026-11-15T09:00:00-05:00.",
            thread_id, store, calendar, profile, settings,
        )
        assert paused.done is False

        resumed = executor.resume_step("approve", thread_id, store, calendar, profile, settings)
        assert resumed.done is True
        assert len(calendar.list_appointments()) == 1

    def test_rejecting_does_not_create_the_appointment(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        thread_id = uuid.uuid4().hex
        executor.run_step(
            "Agenda una cita de cardiología para el 2026-11-15T09:00:00-05:00.",
            thread_id, store, calendar, profile, settings,
        )
        resumed = executor.resume_step("reject", thread_id, store, calendar, profile, settings)
        assert resumed.done is True
        assert calendar.list_appointments() == []


class TestServiceStart:
    def test_a_simple_question_completes_in_one_pass(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        reply = service.start("Hola, ¿quién eres?", True, store, calendar, profile, settings)
        assert reply.status == "done"
        assert reply.reply

    def test_reusing_the_same_thread_id_keeps_memory_across_turns(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        thread_id = uuid.uuid4().hex

        first = service.start(
            "Recuerda este número clave: 7742. Solo confírmame que lo anotaste.",
            True, store, calendar, profile, settings, thread_id=thread_id,
        )
        assert first.status == "done"

        second = service.start(
            "¿Cuál era el número clave que te dije?",
            False, store, calendar, profile, settings, thread_id=thread_id,
        )
        assert second.status == "done"
        assert "7742" in second.reply

    def test_a_write_request_pauses_and_can_be_confirmed(self, tmp_path):
        store, calendar, profile = make_stores(tmp_path)
        settings = make_settings(tmp_path)
        reply = service.start(
            "Agéndame una cita de cardiología para el 2026-11-15T09:00:00-05:00.",
            True, store, calendar, profile, settings,
        )
        assert reply.status == "needs_confirmation"
        assert reply.pending.tool == "create_appointment"

        final = service.continue_after_confirmation(
            reply.pending.resume_state, "approve", store, calendar, profile, settings,
        )
        assert final.status == "done"
        assert len(calendar.list_appointments()) == 1
