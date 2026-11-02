import json

import httpx

from app.config import Settings
from app.extraction.vision_client import chat_completion, provider_routing


def make_settings(**kw) -> Settings:
    return Settings(openrouter_api_key="k", _env_file=None, retry_min_wait_s=0, retry_max_wait_s=0, **kw)


def capture_client(sent):
    def handler(request):
        sent.append(json.loads(request.read()))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestProviderRouting:
    def test_off_by_default_so_openrouter_chooses(self):
        assert provider_routing(make_settings()) is None
        sent = []
        chat_completion("m", "text", [{"role": "user", "content": "hola"}], make_settings(), capture_client(sent))
        assert "provider" not in sent[0]

    def test_restricts_to_the_listed_providers_without_falling_back(self):
        routing = provider_routing(make_settings(openrouter_providers="google-vertex, deepinfra"))
        assert routing == {"only": ["google-vertex", "deepinfra"], "allow_fallbacks": False}

    def test_data_collection_deny_alone_does_not_pin_a_provider(self):
        assert provider_routing(make_settings(openrouter_data_collection="deny")) == {"data_collection": "deny"}

    def test_both_settings_are_sent_in_every_request(self):
        sent = []
        settings = make_settings(openrouter_providers="google-vertex", openrouter_data_collection="DENY")
        chat_completion("google/gemma-4-26b-a4b-it", "text", [{"role": "user", "content": "hola"}], settings, capture_client(sent))
        assert sent[0]["provider"] == {"only": ["google-vertex"], "allow_fallbacks": False, "data_collection": "deny"}
