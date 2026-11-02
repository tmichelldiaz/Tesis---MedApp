"""Confirmar, editar o rechazar una acción del agente, con el mecanismo REAL de
confirmación de LangChain (HumanInTheLoopMiddleware) y un modelo simulado.

Antes, la edición llegaba con un formato que la librería no acepta y "Confirmar
cambios" respondía 400 sin hacer nada; las pruebas anteriores solo simulaban la
función completa y no podían verlo."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import executor
from app.agent.clock import add_months, today_note
from app.agent.tools import build_tools
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.store import DocumentStore

# Fechas relativas a hoy para que las pruebas no caduquen.
PAST = "2025-10-20T14:00:00-05:00"
PROPOSED = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT14:00:00+00:00")
EDITED = (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%dT09:00:00+00:00")


class ScriptedModel(BaseChatModel):
    """Pide agendar una cita; cuando ya vio el resultado de la herramienta, cierra con texto.

    `first_date` es la fecha que propone. Con `fix_dates`, si se la rechazan por pasada,
    corrige y propone `PROPOSED`."""

    first_date: str = PROPOSED
    fix_dates: bool = False
    parallel: int = 1  # cuántas acciones pide a la vez en el primer turno

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _call(self, when: str, call_id: str) -> AIMessage:
        return AIMessage(content="", tool_calls=[{
            "name": "create_appointment", "id": call_id,
            "args": {"title": "Consulta médica", "scheduled_at": when, "doctor_name": "Dr. Luis"},
        }])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1]
        if isinstance(last, ToolMessage) and "ya pasó" in str(last.content) and self.fix_dates:
            message = self._call(PROPOSED, "call-2")
        elif isinstance(last, ToolMessage):
            message = AIMessage(content="Listo, resuelto.")
        else:
            message = self._call(self.first_date, "call-1")
            for extra in range(1, self.parallel):
                message.tool_calls.append({**message.tool_calls[0], "id": f"call-1-{extra}"})
        return ChatResult(generations=[ChatGeneration(message=message)])


def make_env(tmp_path, monkeypatch, **model_kwargs):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return ScriptedModel(**model_kwargs)

    monkeypatch.setattr(executor, "ChatOpenAI", fake_chat_openai)
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    return (
        DocumentStore(tmp_path), CalendarStore(tmp_path), ProfileStore(tmp_path), settings, captured,
        f"user-1:{uuid.uuid4().hex}",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)


def pause(env):
    store, calendar, profile, settings, _, thread_id = env
    step = executor.run_step("Agenda la cita", thread_id, store, calendar, profile, settings)
    assert step.done is False and step.pending_action.tool == "create_appointment"
    return step


class TestConfirmationFlow:
    def test_nothing_is_written_until_the_patient_confirms(self, env):
        pause(env)
        assert env[1].list_appointments() == []

    def test_editing_the_date_creates_the_appointment_with_the_edited_values(self, env):
        store, calendar, profile, settings, _, thread_id = env
        step = pause(env)
        edited = {**step.pending_action.args, "scheduled_at": EDITED}
        result = executor.resume_step("edit", thread_id, store, calendar, profile, settings, edited_args=edited)
        assert result.done is True
        appointments = calendar.list_appointments()
        assert len(appointments) == 1 and appointments[0]["scheduled_at"] == EDITED

    def test_approving_creates_it_with_the_proposed_values(self, env):
        store, calendar, profile, settings, _, thread_id = env
        pause(env)
        result = executor.resume_step("approve", thread_id, store, calendar, profile, settings)
        assert result.done is True
        assert [a["scheduled_at"] for a in calendar.list_appointments()] == [PROPOSED]

    def test_rejecting_creates_nothing(self, env):
        store, calendar, profile, settings, _, thread_id = env
        pause(env)
        result = executor.resume_step("reject", thread_id, store, calendar, profile, settings)
        assert result.done is True and calendar.list_appointments() == []

    def test_resuming_an_edit_with_nothing_pending_is_a_key_error(self, env):
        store, calendar, profile, settings, _, _ = env
        with pytest.raises(KeyError):
            executor.resume_step("edit", f"user-1:{uuid.uuid4().hex}", store, calendar, profile, settings,
                                 edited_args={"title": "x"})


class TestSeveralActionsAtOnce:
    """El modelo a veces pide dos acciones en el mismo turno; la tarjeta muestra una y el paciente responde
    una. Antes eso daba error 500 ("hay 1 decisión para 2 acciones")."""

    def test_confirming_with_two_pending_actions_does_not_fail(self, tmp_path, monkeypatch):
        store, calendar, profile, settings, _, thread_id = make_env(tmp_path, monkeypatch, parallel=2)
        step = executor.run_step("Agenda la cita", thread_id, store, calendar, profile, settings)
        assert step.pending_action.tool == "create_appointment"
        result = executor.resume_step("approve", thread_id, store, calendar, profile, settings)
        assert result.done is True
        assert len(calendar.list_appointments()) == 1  # solo la que el paciente confirmó

    def test_editing_with_two_pending_actions_does_not_fail(self, tmp_path, monkeypatch):
        store, calendar, profile, settings, _, thread_id = make_env(tmp_path, monkeypatch, parallel=2)
        step = executor.run_step("Agenda la cita", thread_id, store, calendar, profile, settings)
        edited = {**step.pending_action.args, "scheduled_at": EDITED}
        result = executor.resume_step("edit", thread_id, store, calendar, profile, settings, edited_args=edited)
        assert result.done is True
        assert [a["scheduled_at"] for a in calendar.list_appointments()] == [EDITED]

    def test_the_model_is_asked_for_one_action_per_turn(self, env):
        pause(env)
        assert env[4]["model_kwargs"] == {"parallel_tool_calls": False}


class TestPastDateCorrection:
    def test_a_proposal_in_the_past_is_rejected_before_the_patient_sees_it(self, tmp_path, monkeypatch):
        env = make_env(tmp_path, monkeypatch, first_date=PAST, fix_dates=True)
        step = pause(env)
        assert step.pending_action.args["scheduled_at"] == PROPOSED  # la tarjeta ya trae la fecha corregida
        assert env[1].list_appointments() == []

    def test_if_the_model_insists_on_the_past_no_card_is_shown_and_nothing_is_written(self, tmp_path, monkeypatch):
        env = make_env(tmp_path, monkeypatch, first_date=PAST, fix_dates=False)
        store, calendar, profile, settings, _, thread_id = env
        step = executor.run_step("Agenda la cita", thread_id, store, calendar, profile, settings)
        assert step.done is True and step.pending_action is None
        assert calendar.list_appointments() == []

    def test_a_future_date_is_never_touched(self, env):
        assert pause(env).pending_action.args["scheduled_at"] == PROPOSED


class TestTodayAndRouting:
    def test_the_executor_knows_what_day_it_is(self, env, monkeypatch):
        store, calendar, profile, settings, _, thread_id = env
        seen = {}
        original = executor.create_agent

        def spy(**kwargs):
            seen["system"] = kwargs["system_prompt"]
            return original(**kwargs)

        monkeypatch.setattr(executor, "create_agent", spy)
        executor.run_step("Agenda la cita", thread_id, store, calendar, profile, settings)
        assert "FECHA Y HORA ACTUALES" in seen["system"]
        # Debe consultar siempre la herramienta de valores antes de decir que no tiene un dato.
        assert "llama SIEMPRE" in seen["system"] and "get_exact_values" in seen["system"]
        assert str(datetime.now(timezone.utc).year) in seen["system"]

    def test_the_agent_model_goes_through_the_same_provider_policy(self, tmp_path, monkeypatch):
        captured = {}
        monkeypatch.setattr(executor, "ChatOpenAI", lambda **kw: captured.update(kw) or ScriptedModel())
        settings = Settings(
            openrouter_api_key="k", data_dir=tmp_path, _env_file=None,
            openrouter_providers="google-vertex", openrouter_data_collection="deny",
        )
        executor.run_step("Agenda", f"u:{uuid.uuid4().hex}", DocumentStore(tmp_path), CalendarStore(tmp_path),
                          ProfileStore(tmp_path), settings)
        assert captured["extra_body"] == {
            "provider": {"only": ["google-vertex"], "allow_fallbacks": False, "data_collection": "deny"}
        }


class TestClock:
    def settings(self):
        return Settings(openrouter_api_key="k", _env_file=None)

    def test_the_note_names_the_day_month_year_and_timezone(self):
        moment = datetime(2026, 10, 10, 22, 30, tzinfo=timezone(timedelta(hours=-5)))
        note = today_note(self.settings(), moment)
        assert "sábado 10 de octubre de 2026" in note and "22:30" in note and "UTC-05:00" in note
        assert "Nunca agendes una cita en el pasado" in note

    def test_relative_dates_are_already_calculated(self):
        note = today_note(self.settings(), datetime(2026, 10, 10, 23, 40, tzinfo=timezone(timedelta(hours=-5))))
        assert "mañana = 2026-10-11 (domingo)" in note
        assert "en 2 semanas = 2026-10-24" in note
        assert "en 1 mes = 2026-11-10" in note  # el caso que el modelo resolvió hacia atrás en una prueba real
        assert "próximo lunes = 2026-10-12" in note

    def test_months_clamp_to_the_last_day_of_a_shorter_month(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)

    def test_utc_time_is_shown_in_the_patients_zone(self):
        note = today_note(self.settings(), datetime(2026, 10, 11, 3, 30, tzinfo=timezone.utc))
        assert "sábado 10 de octubre de 2026" in note and "22:30" in note


class TestPastDateSafetyNet:
    def tools(self, tmp_path):
        settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
        calendar = CalendarStore(tmp_path)
        built = build_tools(DocumentStore(tmp_path), calendar, ProfileStore(tmp_path), settings, None)
        return {t.name: t for t in built}, calendar

    def test_the_tool_refuses_a_date_in_the_past(self, tmp_path):
        tools, calendar = self.tools(tmp_path)
        result = tools["create_appointment"].invoke({"title": "Control", "scheduled_at": PAST})
        assert "No se creó la cita" in result and "ya pasó" in result
        assert calendar.list_appointments() == []

    def test_the_tool_refuses_a_malformed_date(self, tmp_path):
        tools, _ = self.tools(tmp_path)
        assert "no es válida" in tools["create_appointment"].invoke({"title": "x", "scheduled_at": "mañana"})
