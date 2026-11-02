import httpx
import pymupdf
import pytest

from app.config import Settings
from app.extraction import vision_client
from app.extraction.documents import PageImage, UnsupportedDocument, detect_kind, load_pages
from app.extraction.to_markdown import convert

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def make_settings(**kw) -> Settings:
    base = dict(
        openrouter_api_key="test-key",
        retry_min_wait_s=0.0,
        retry_max_wait_s=0.0,
        _env_file=None,
    )
    base.update(kw)
    return Settings(**base)


def make_pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((50, 50), f"Pagina {i + 1}")
    return doc.tobytes()


def ok_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestDocuments:
    def test_detects_supported_kinds(self):
        assert detect_kind(b"%PDF-1.7 ...") == "pdf"
        assert detect_kind(PNG) == "image/png"
        assert detect_kind(b"\xff\xd8\xff\xe0abc") == "image/jpeg"
        assert detect_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"

    def test_rejects_unknown_format(self):
        with pytest.raises(UnsupportedDocument):
            detect_kind(b"MZ\x90\x00 executable")

    def test_rejects_empty_and_oversize(self):
        s = make_settings(max_file_mb=1)
        with pytest.raises(UnsupportedDocument):
            load_pages(b"", s)
        with pytest.raises(UnsupportedDocument):
            load_pages(PNG + b"0" * (1024 * 1024), s)

    def test_pdf_becomes_one_png_per_page(self):
        pages = load_pages(make_pdf(3), make_settings())
        assert [p.index for p in pages] == [1, 2, 3]
        assert all(p.mime == "image/png" and p.data.startswith(b"\x89PNG") for p in pages)

    def test_pdf_page_limit(self):
        with pytest.raises(UnsupportedDocument, match="máximo"):
            load_pages(make_pdf(3), make_settings(max_pages=2))

    def test_broken_pdf(self):
        with pytest.raises(UnsupportedDocument):
            load_pages(b"%PDF-1.7 garbage", make_settings())

    def test_image_is_single_page(self):
        pages = load_pages(PNG, make_settings())
        assert len(pages) == 1 and pages[0].mime == "image/png"


class TestConvert:
    def test_one_request_per_page_with_markers(self):
        calls = []

        def fake(batch, settings):
            calls.append([p.index for p in batch])
            return f"## Sección {batch[0].index}"

        result = convert(make_pdf(2), make_settings(), "muestra.pdf", transcriber=fake)
        assert calls == [[1], [2]]
        assert result.page_count == 2 and result.requests == 2
        assert "<!-- página 1 -->" in result.markdown
        assert result.markdown.index("Sección 1") < result.markdown.index("Sección 2")
        assert result.source_name == "muestra.pdf"

    def test_batches_pages(self):
        seen = []

        def fake(batch, settings):
            seen.append(len(batch))
            return "texto"

        result = convert(
            make_pdf(5), make_settings(pages_per_request=2), transcriber=fake
        )
        assert seen == [2, 2, 1]
        assert "<!-- páginas 1-2 -->" in result.markdown
        assert "<!-- página 5 -->" in result.markdown

    def test_unsupported_file_raises(self):
        with pytest.raises(UnsupportedDocument):
            convert(b"nope", make_settings(), transcriber=lambda b, s: "x")


class TestVisionClient:
    PAGE = [PageImage(index=1, data=PNG, mime="image/png")]

    def test_success_strips_code_fence_and_sends_image(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.read().decode()
            seen["auth"] = request.headers["authorization"]
            return httpx.Response(200, json=ok_response("```markdown\n# Título\n```"))

        text = vision_client.transcribe(self.PAGE, make_settings(), client_for(handler))
        assert text == "# Título"
        assert seen["auth"] == "Bearer test-key"
        assert "data:image/png;base64," in seen["body"]
        assert "qwen/qwen3.8-27b:free" in seen["body"]

    def test_retries_on_429_then_succeeds(self):
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            if attempts["n"] < 3:
                return httpx.Response(429, json={"error": {"message": "rate limited"}})
            return httpx.Response(200, json=ok_response("# ok"))

        text = vision_client.transcribe(self.PAGE, make_settings(), client_for(handler))
        assert text == "# ok" and attempts["n"] == 3

    def test_gives_up_after_max_retries(self):
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            return httpx.Response(503, text="unavailable")

        with pytest.raises(vision_client.VisionError, match="503"):
            vision_client.transcribe(
                self.PAGE, make_settings(max_retries=3), client_for(handler)
            )
        assert attempts["n"] == 3

    def test_does_not_retry_client_errors(self):
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        with pytest.raises(vision_client.VisionError, match="401"):
            vision_client.transcribe(self.PAGE, make_settings(), client_for(handler))
        assert attempts["n"] == 1

    def test_empty_transcription_is_an_error(self):
        handler = lambda request: httpx.Response(200, json=ok_response("   "))
        with pytest.raises(vision_client.VisionError, match="vacía"):
            vision_client.transcribe(self.PAGE, make_settings(), client_for(handler))

    def test_missing_api_key(self):
        with pytest.raises(vision_client.VisionError, match="OPENROUTER_API_KEY"):
            vision_client.transcribe(self.PAGE, make_settings(openrouter_api_key=""))


class TestFallbackAndMessages:
    PAGE = [PageImage(index=1, data=PNG, mime="image/png")]

    def test_429_message_is_readable_not_raw_json(self):
        handler = lambda request: httpx.Response(
            429, json={"error": {"message": "Provider returned error", "code": 429}}
        )
        with pytest.raises(vision_client.VisionError) as info:
            vision_client.transcribe(self.PAGE, make_settings(max_retries=1), client_for(handler))
        message = str(info.value)
        assert "429" in message and "Reintenta" in message and "{" not in message
        assert info.value.transient

    def test_falls_back_to_second_model_on_rate_limit(self):
        models = []

        def handler(request):
            import json as _json
            model = _json.loads(request.read())["model"]
            models.append(model)
            if model == "primario:free":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok_response("# ok"))

        settings = make_settings(
            vision_model="primario:free", vision_fallback_model="respaldo", max_retries=1
        )
        text = vision_client.transcribe(self.PAGE, settings, client_for(handler))
        assert text == "# ok" and text.model == "respaldo"
        assert models == ["primario:free", "respaldo"]

    def test_no_fallback_on_auth_error(self):
        models = []

        def handler(request):
            import json as _json
            models.append(_json.loads(request.read())["model"])
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        settings = make_settings(vision_fallback_model="respaldo")
        with pytest.raises(vision_client.VisionError, match="401"):
            vision_client.transcribe(self.PAGE, settings, client_for(handler))
        assert len(models) == 1

    def test_falls_back_on_empty_transcription(self):
        models = []

        def handler(request):
            import json as _json
            model = _json.loads(request.read())["model"]
            models.append(model)
            if model == "primario:free":
                return httpx.Response(200, json=ok_response("   "))
            return httpx.Response(200, json=ok_response("# ok"))

        settings = make_settings(
            vision_model="primario:free", vision_fallback_model="respaldo", max_retries=1
        )
        text = vision_client.transcribe(self.PAGE, settings, client_for(handler))
        assert text == "# ok" and text.model == "respaldo"
        assert models == ["primario:free", "respaldo"]

    def test_falls_back_on_a_200_with_an_embedded_provider_error(self):
        models = []

        def handler(request):
            import json as _json
            model = _json.loads(request.read())["model"]
            models.append(model)
            if model == "primario:free":
                return httpx.Response(
                    200,
                    json={"error": {"message": "Upstream error from Nvidia: ResourceExhausted"}},
                )
            return httpx.Response(200, json=ok_response("# ok"))

        settings = make_settings(
            vision_model="primario:free", vision_fallback_model="respaldo", max_retries=1
        )
        text = vision_client.transcribe(self.PAGE, settings, client_for(handler))
        assert text == "# ok" and text.model == "respaldo"
        assert models == ["primario:free", "respaldo"]

    def test_convert_reports_the_model_actually_used(self):
        def fake(batch, settings):
            text = vision_client.Transcription("# t")
            text.model = "respaldo"
            return text

        result = convert(make_pdf(1), make_settings(), transcriber=fake)
        assert result.model == "respaldo"


class TestTextFallback:
    LONG = "Glucosa en ayunas 94 mg/dL referencia 70 - 100. Colesterol total 212 mg/dL."

    def rate_limited_then(self, text_reply):
        seen = []

        def handler(request):
            import json as _json
            body = _json.loads(request.read())
            seen.append((body["model"], body["messages"][1]["content"]))
            if body["model"] == "qwen/qwen3.8-27b:free":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok_response(text_reply))

        return handler, seen

    def test_pdf_page_carries_native_text(self):
        doc = pymupdf.open()
        doc.new_page().insert_text((50, 50), self.LONG)
        pages = load_pages(doc.tobytes(), make_settings())
        assert "Glucosa en ayunas" in pages[0].text

    def test_uses_text_model_directly_when_native_text_is_available(self):
        seen = []

        def handler(request):
            import json as _json
            body = _json.loads(request.read())
            seen.append((body["model"], body["messages"][1]["content"]))
            return httpx.Response(200, json=ok_response("## Analítica\n\n" + self.LONG))  # conserva todo el texto

        pages = [PageImage(index=1, data=PNG, mime="image/png", text=self.LONG)]
        settings = make_settings(max_retries=1)

        text = vision_client.transcribe(pages, settings, client_for(handler))
        assert text.model == "nvidia/nemotron-3-ultra-550b-a55b:free" and text.mode == "text"
        model, content = seen[-1]
        assert isinstance(content, str) and "Glucosa en ayunas" in content
        assert "image_url" not in str(content)
        # el modelo de visión ni siquiera se llama: el texto nativo alcanza
        assert len(seen) == 1

    def test_image_without_text_cannot_use_text_model(self):
        handler, seen = self.rate_limited_then("no debería llamarse")
        pages = [PageImage(index=1, data=PNG, mime="image/png")]

        with pytest.raises(vision_client.VisionError, match="solo texto"):
            vision_client.transcribe(pages, make_settings(max_retries=1), client_for(handler))
        assert [m for m, _ in seen] == ["qwen/qwen3.8-27b:free"]

    def test_text_fallback_can_be_disabled(self):
        handler, seen = self.rate_limited_then("x")
        pages = [PageImage(index=1, data=PNG, mime="image/png", text=self.LONG)]
        settings = make_settings(max_retries=1, text_fallback_model="")
        with pytest.raises(vision_client.VisionError, match="429"):
            vision_client.transcribe(pages, settings, client_for(handler))
        assert len(seen) == 1

    def test_convert_notes_the_text_path_and_log_records_it(self):
        from app.okf.builder import build_bundle

        def fake(batch, settings):
            out = vision_client.Transcription("# Doc\n\n## A\n\nx\n\n## B\n\ny")
            out.model, out.mode = "nvidia/nemotron-3-ultra-550b-a55b:free", "text"
            return out

        result = convert(make_pdf(1), make_settings(), transcriber=fake)
        assert result.notes and "solo texto" in result.notes[0]
        bundle = build_bundle(result.markdown, "a.pdf", result.model, notes=result.notes)
        operations = bundle.files["log.md"].split("## Operaciones")[1].split("## Unidades")[0]
        assert "modelo de solo texto" in operations and "capa de texto" in operations


def test_switches_quickly_to_vision_when_the_text_model_is_rate_limited():
    attempts = []

    def handler(request):
        import json as _json
        model = _json.loads(request.read())["model"]
        attempts.append(model)
        if model == "nvidia/nemotron-3-ultra-550b-a55b:free":
            return httpx.Response(429, json={"error": {"message": "x"}})
        return httpx.Response(200, json=ok_response("## ok"))

    long_text = "Glucosa en ayunas 94 mg/dL referencia 70 - 100. Colesterol 212 mg/dL."
    pages = [PageImage(index=1, data=PNG, mime="image/png", text=long_text)]
    text = vision_client.transcribe(pages, make_settings(max_retries=6), client_for(handler))

    assert attempts.count("nvidia/nemotron-3-ultra-550b-a55b:free") == vision_client.QUICK_RETRIES
    assert text.model == "qwen/qwen3.8-27b:free"


def test_keeps_full_retries_when_there_is_no_alternative():
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(429, json={"error": {"message": "x"}})

    pages = [PageImage(index=1, data=PNG, mime="image/png")]
    with pytest.raises(vision_client.VisionError):
        vision_client.transcribe(pages, make_settings(max_retries=5), client_for(handler))
    assert len(attempts) == 5
