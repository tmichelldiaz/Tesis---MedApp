import json

import httpx
import pytest

from app.agent.planning import plan, synthesize
from app.config import Settings
from app.extraction.vision_client import VisionError


def make_settings(**kw) -> Settings:
    return Settings(openrouter_api_key="k", retry_min_wait_s=0, retry_max_wait_s=0, _env_file=None, **kw)


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class TestPlan:
    def test_happy_path_returns_the_steps(self):
        handler = lambda request: httpx.Response(200, json=ok(json.dumps({"steps": ["Buscar la glucosa"]})))
        assert plan("¿Cuál fue mi glucosa?", None, make_settings(), client_for(handler)) == ["Buscar la glucosa"]

    def test_includes_the_proactive_note_in_the_prompt(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok(json.dumps({"steps": ["x"]})))

        plan("Hola", "La cita ya pasó.", make_settings(), client_for(handler))
        assert "La cita ya pasó." in seen[0]["messages"][1]["content"]

    def test_requests_json_object_response_format(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok(json.dumps({"steps": ["x"]})))

        plan("Hola", None, make_settings(), client_for(handler))
        assert seen[0]["response_format"] == {"type": "json_object"}

    def test_falls_back_to_a_single_step_plan_on_malformed_output(self):
        handler = lambda request: httpx.Response(200, json=ok("no soy json"))
        assert plan("¿Cuál fue mi glucosa?", None, make_settings(), client_for(handler)) == ["¿Cuál fue mi glucosa?"]

    def test_retries_once_when_the_model_reasons_instead_of_answering_json(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json=ok(
                    "The user wants to know their glucose value, so I need to plan a step "
                    "that searches for it in their lab results..."
                ))
            return httpx.Response(200, json=ok(json.dumps({"steps": ["Buscar la glucosa"]})))

        result = plan("¿Cuál fue mi glucosa?", None, make_settings(), client_for(handler))
        assert calls["n"] == 2 and result == ["Buscar la glucosa"]

    def test_falls_back_to_single_step_on_non_transient_error(self):
        handler = lambda request: httpx.Response(401, json={"error": {"message": "bad key"}})
        assert plan("¿Cuál fue mi glucosa?", None, make_settings(), client_for(handler)) == ["¿Cuál fue mi glucosa?"]

    def test_falls_back_on_rate_limit(self):
        seen = []

        def handler(request):
            model = json.loads(request.read())["model"]
            seen.append(model)
            if model == "primario":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok(json.dumps({"steps": ["Paso"]})))

        settings = make_settings(agent_planner_model="primario", agent_planner_fallback_model="respaldo")
        result = plan("Hola", None, settings, client_for(handler))
        assert result == ["Paso"] and seen[0] == "primario" and seen[-1] == "respaldo"

    def test_drops_empty_steps(self):
        handler = lambda request: httpx.Response(200, json=ok(json.dumps({"steps": ["Paso 1", "  ", ""]})))
        assert plan("Hola", None, make_settings(), client_for(handler)) == ["Paso 1"]


class TestSynthesize:
    def test_happy_path_returns_the_reply(self):
        handler = lambda request: httpx.Response(200, json=ok("Tu glucosa fue 94 mg/dL."))
        result = synthesize(
            "¿Cuál fue mi glucosa?", [("Buscar la glucosa", "Glucosa: 94 mg/dL")],
            make_settings(), client_for(handler),
        )
        assert result == "Tu glucosa fue 94 mg/dL."

    def test_includes_question_and_steps_in_the_prompt(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok("ok"))

        synthesize("¿Cuál fue mi glucosa?", [("Buscar la glucosa", "94 mg/dL")], make_settings(), client_for(handler))
        content = seen[0]["messages"][1]["content"]
        assert "¿Cuál fue mi glucosa?" in content and "94 mg/dL" in content

    def test_falls_back_on_rate_limit(self):
        seen = []

        def handler(request):
            model = json.loads(request.read())["model"]
            seen.append(model)
            if model == "primario":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok("respuesta final"))

        settings = make_settings(chat_model="primario", chat_fallback_model="respaldo")
        result = synthesize("Hola", [("paso", "resultado")], settings, client_for(handler))
        assert result == "respuesta final" and seen[0] == "primario" and seen[-1] == "respaldo"

    def test_raises_on_non_transient_error(self):
        handler = lambda request: httpx.Response(401, json={"error": {"message": "bad key"}})
        with pytest.raises(VisionError, match="401"):
            synthesize("Hola", [("paso", "resultado")], make_settings(), client_for(handler))
