import json

import httpx
import pytest

from app.config import Settings
from app.extraction.category import CATEGORIES, DEFAULT_CATEGORY, classify_category
from app.extraction.vision_client import VisionError


def make_settings(**kw) -> Settings:
    return Settings(openrouter_api_key="k", retry_min_wait_s=0, retry_max_wait_s=0, _env_file=None, **kw)


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class TestClassifyCategory:
    def test_empty_markdown_short_circuits_without_a_call(self):
        assert classify_category("   ", make_settings()) == DEFAULT_CATEGORY

    def test_happy_path_returns_a_valid_category(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok('{"category": "Resultados de laboratorio"}'))

        result = classify_category("# Hemograma\n\n| Glucosa | 94 |", make_settings(), client_for(handler))
        assert result == "Resultados de laboratorio"
        assert seen[0]["response_format"] == {"type": "json_object"}

    def test_truncates_input_to_the_configured_limit(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok('{"category": "Otro"}'))

        classify_category("x" * 500, make_settings(category_input_chars=50), client_for(handler))
        assert len(seen[0]["messages"][1]["content"]) == 50

    def test_unknown_category_falls_back_to_default(self):
        handler = lambda request: httpx.Response(200, json=ok('{"category": "Cardiología"}'))
        assert classify_category("# Doc", make_settings(), client_for(handler)) == DEFAULT_CATEGORY

    def test_malformed_output_falls_back_to_default_instead_of_erroring(self):
        handler = lambda request: httpx.Response(200, json=ok("no soy json"))
        assert classify_category("# Doc", make_settings(), client_for(handler)) == DEFAULT_CATEGORY

    def test_falls_back_on_rate_limit(self):
        seen = []

        def handler(request):
            model = json.loads(request.read())["model"]
            seen.append(model)
            if model == "primario":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok('{"category": "Medicamentos"}'))

        settings = make_settings(category_model="primario", category_fallback_model="respaldo")
        result = classify_category("# Doc", settings, client_for(handler))
        assert result == "Medicamentos" and seen[0] == "primario" and seen[-1] == "respaldo"

    def test_raises_on_non_transient_error(self):
        handler = lambda request: httpx.Response(401, json={"error": {"message": "bad key"}})
        with pytest.raises(VisionError, match="401"):
            classify_category("# Doc", make_settings(), client_for(handler))

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_accepts_every_known_category(self, category):
        handler = lambda request: httpx.Response(200, json=ok(json.dumps({"category": category})))
        assert classify_category("# Doc", make_settings(), client_for(handler)) == category

    def test_retries_once_when_the_model_reasons_instead_of_answering_json(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json=ok(
                    "The user wants me to classify this clinical document based on the "
                    "provided markdown. The document appears to be a laboratory report..."
                ))
            return httpx.Response(200, json=ok('{"category": "Resultados de laboratorio"}'))

        result = classify_category("# Hemograma\n\n| Glucosa | 94 |", make_settings(), client_for(handler))
        assert calls["n"] == 2
        assert result == "Resultados de laboratorio"

    def test_a_short_malformed_result_is_accepted_immediately_without_retrying(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=ok("no soy json"))

        assert classify_category("# Doc", make_settings(), client_for(handler)) == DEFAULT_CATEGORY
        assert calls["n"] == 1  # no vale la pena reintentar algo tan corto

    def test_gives_up_to_default_after_exhausting_retries_on_reasoning_prose(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=ok(
                "The user wants me to classify this clinical document based on the "
                "provided markdown, but I keep thinking instead of answering..."
            ))

        result = classify_category("# Doc", make_settings(), client_for(handler))
        assert result == DEFAULT_CATEGORY
        assert calls["n"] == 2  # agotó los reintentos del único modelo configurado
