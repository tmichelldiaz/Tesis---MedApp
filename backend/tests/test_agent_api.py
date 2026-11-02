import pytest
from fastapi.testclient import TestClient

from app.agent.service import AgentReply, PendingConfirmation
from app.calendar_store import CalendarStore
from app.config import Settings
from app.extraction.vision_client import VisionError
from app.main import (
    app, get_agent_resume, get_agent_start, get_calendar, get_current_user,
    get_profile, get_settings, get_store,
)
from app.profile_store import ProfileStore
from app.store import DocumentStore

FAKE_USER_ID = "user-1"


@pytest.fixture
def client(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: DocumentStore(tmp_path)
    app.dependency_overrides[get_calendar] = lambda: CalendarStore(tmp_path)
    app.dependency_overrides[get_profile] = lambda: ProfileStore(tmp_path)
    app.dependency_overrides[get_current_user] = lambda: {"id": FAKE_USER_ID, "email": "user@example.com"}
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestAgentChat:
    def test_returns_done_reply(self, client):
        app.dependency_overrides[get_agent_start] = lambda: (
            lambda question, is_new, store, calendar, profile, settings, **kw: AgentReply(status="done", reply="Hola, ¿en qué te ayudo?")
        )
        response = client.post("/agent/chat", json={"question": "Hola"})
        assert response.status_code == 200
        assert response.json() == {"status": "done", "reply": "Hola, ¿en qué te ayudo?"}

    def test_returns_needs_confirmation_with_pending_action(self, client):
        pending = PendingConfirmation(
            tool="create_appointment",
            args={"title": "Cardiología", "scheduled_at": "2099-10-15T09:00:00Z"},
            description="Tool execution requires approval",
            resume_state={"thread_id": "t1", "question": "Agenda una cita", "current_step": "Crear cita", "remaining_plan": [], "past_steps": []},
        )
        app.dependency_overrides[get_agent_start] = lambda: (
            lambda question, is_new, store, calendar, profile, settings, **kw: AgentReply(status="needs_confirmation", pending=pending)
        )
        response = client.post("/agent/chat", json={"question": "Agenda una cita"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "needs_confirmation"
        assert body["action"]["tool"] == "create_appointment"
        assert body["resume_state"]["thread_id"] == "t1"

    def test_forwards_thread_id_for_conversation_memory(self, client):
        seen = {}

        def fake_start(question, is_new, store, calendar, profile, settings, thread_id=None):
            seen["thread_id"] = thread_id
            return AgentReply(status="done", reply="ok")

        app.dependency_overrides[get_agent_start] = lambda: fake_start
        client.post("/agent/chat", json={"question": "Hola", "thread_id": "conv-42"})
        assert seen["thread_id"] == f"{FAKE_USER_ID}:conv-42"

    def test_rejects_blank_question(self, client):
        response = client.post("/agent/chat", json={"question": "   "})
        assert response.status_code == 400

    def test_model_saturation_is_503(self, client):
        def boom(*args, **kwargs):
            raise VisionError("El modelo está saturado (429).", transient=True)

        app.dependency_overrides[get_agent_start] = lambda: boom
        response = client.post("/agent/chat", json={"question": "Hola"})
        assert response.status_code == 503


class TestAgentChatResume:
    def test_approve_returns_done_reply(self, client):
        app.dependency_overrides[get_agent_resume] = lambda: (
            lambda resume_state, decision, store, calendar, profile, settings, edited_args=None:
                AgentReply(status="done", reply="Listo, agendé tu cita.")
        )
        response = client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": f"{FAKE_USER_ID}:t1"}, "decision": "approve",
        })
        assert response.status_code == 200
        assert response.json() == {"status": "done", "reply": "Listo, agendé tu cita."}

    def test_rejects_unknown_decision(self, client):
        response = client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": "t1"}, "decision": "maybe",
        })
        assert response.status_code == 400

    def test_edit_without_edited_args_is_400(self, client):
        response = client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": "t1"}, "decision": "edit",
        })
        assert response.status_code == 400

    def test_edit_forwards_edited_args(self, client):
        seen = {}

        def fake_resume(resume_state, decision, store, calendar, profile, settings, edited_args=None):
            seen["edited_args"] = edited_args
            return AgentReply(status="done", reply="ok")

        app.dependency_overrides[get_agent_resume] = lambda: fake_resume
        client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": f"{FAKE_USER_ID}:t1"}, "decision": "edit",
            "edited_args": {"scheduled_at": "2026-11-01T09:00:00Z"},
        })
        assert seen["edited_args"] == {"scheduled_at": "2026-11-01T09:00:00Z"}

    def test_corrupt_resume_state_is_400(self, client):
        def boom(*args, **kwargs):
            raise KeyError("thread_id")

        app.dependency_overrides[get_agent_resume] = lambda: boom
        response = client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": f"{FAKE_USER_ID}:t1"}, "decision": "approve",
        })
        assert response.status_code == 400

    def test_resume_state_from_another_user_is_403(self, client):
        app.dependency_overrides[get_agent_resume] = lambda: (
            lambda resume_state, decision, store, calendar, profile, settings, edited_args=None:
                AgentReply(status="done", reply="no debería llegar aquí")
        )
        response = client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": "other-user:t1"}, "decision": "approve",
        })
        assert response.status_code == 403


class TestModelConnectionErrors:
    """El agente llama al modelo con la librería de OpenAI: un cuelgue o una caída debe
    salir como un 503 con mensaje para el paciente, no como un 500 sin explicación."""

    def make_error(self):
        import httpx
        import openai

        return openai.APITimeoutError(request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))

    def test_a_model_timeout_on_chat_is_a_friendly_503(self, client):
        error = self.make_error()

        def boom(*args, **kwargs):
            raise error

        app.dependency_overrides[get_agent_start] = lambda: boom
        response = client.post("/agent/chat", json={"question": "Agenda una cita"})
        assert response.status_code == 503
        assert response.json()["detail"] == "No se pudo completar la solicitud. Intenta de nuevo en unos minutos."

    def test_a_model_timeout_when_resuming_is_a_friendly_503(self, client):
        error = self.make_error()

        def boom(*args, **kwargs):
            raise error

        app.dependency_overrides[get_agent_resume] = lambda: boom
        response = client.post("/agent/chat/resume", json={
            "resume_state": {"thread_id": f"{FAKE_USER_ID}:t1"}, "decision": "approve",
        })
        assert response.status_code == 503


class TestAgentModelSetting:
    def test_the_agent_uses_its_own_model_when_set(self, tmp_path, monkeypatch):
        import uuid

        from app.agent import executor

        captured = {}
        monkeypatch.setattr(executor, "ChatOpenAI", lambda **kw: captured.update(kw) or (_ for _ in ()).throw(RuntimeError("stop")))
        for agent_model, expected in (("google/gemini-2.5-flash-lite", "google/gemini-2.5-flash-lite"), ("", "chat-model")):
            settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None, chat_model="chat-model", agent_model=agent_model)
            with pytest.raises(RuntimeError):
                executor.run_step("hola", f"u:{uuid.uuid4().hex}", DocumentStore(tmp_path), CalendarStore(tmp_path), ProfileStore(tmp_path), settings)
            assert captured["model"] == expected
            assert captured["max_retries"] == 1
