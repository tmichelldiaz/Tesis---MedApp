import json

import httpx
import pytest

from app.extraction import to_markdown, vision_client
from app.extraction.documents import PageImage
from app.extraction.to_markdown import convert
from app.privacy import masking
from app.privacy.masking import MaskingError, _chunks, mask_text
from app.rag.redact import redact_pii
from tests.test_extraction import PNG, client_for, make_pdf, make_settings, ok_response


class TestLocalLayer:
    def test_id_number_with_label_but_no_colon(self):
        out = redact_pii("C.C. 1.023.456.789 de Bogotá")
        assert "1.023.456.789" not in out and "de Bogotá" in out

    def test_id_number_written_in_full(self):
        out = redact_pii("Cédula de ciudadanía número 1090456789")
        assert "1090456789" not in out

    def test_bare_dotted_id_number(self):
        assert "1.023.456.789" not in redact_pii("Se identifica con 1.023.456.789 en admisión")

    def test_date_of_birth_is_hidden_but_age_and_exam_date_stay(self):
        out = redact_pii("nacida el 14/03/1985 (41 años). Examen del 02/09/2026.")
        assert "14/03/1985" not in out
        assert "41 años" in out and "02/09/2026" in out

    def test_written_out_date_of_birth(self):
        out = redact_pii("Fecha de nacimiento: 14 de marzo de 1985")
        assert "1985" not in out

    @pytest.mark.parametrize(
        "clinical",
        [
            "Plaquetas 250.000 /mm3",
            "Urocultivo: 1.000.000 UFC/ml",
            "Hemoglobina: 13,2 g/dL (12,0 - 15,5)",
            "Glucosa 92 mg/dL, examen del 02/09/2026",
        ],
    )
    def test_clinical_values_are_not_touched(self, clinical):
        assert redact_pii(clinical) == clinical


class TestDlpLayer:
    @pytest.fixture(autouse=True)
    def fake_credentials(self, monkeypatch):
        monkeypatch.setattr(masking, "_auth", lambda project="": ({"Authorization": "Bearer t"}, "proyecto-x"))

    def test_dlp_is_off_by_default_and_makes_no_request(self):
        def boom(request):
            raise AssertionError("no debería llamar a DLP")

        text = "Paciente: Ana Ruiz\nGlucosa 92 mg/dL"
        assert mask_text(text, make_settings(), client_for(boom)) == redact_pii(text)

    def test_sends_locally_masked_text_with_the_expected_info_types(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.read())
            return httpx.Response(200, json={"item": {"value": "[dato oculto] refiere dolor"}})

        text = "C.C. 1.023.456.789. María Gómez refiere dolor"
        out = mask_text(text, make_settings(dlp_enabled=True), client_for(handler))

        assert out == "[dato oculto] refiere dolor"
        assert "projects/proyecto-x/content:deidentify" in seen["url"]
        sent = seen["body"]["item"]["value"]
        assert "1.023.456.789" not in sent  # la cédula ya iba enmascarada por la capa local
        names = {t["name"] for t in seen["body"]["inspectConfig"]["infoTypes"]}
        assert {"PERSON_NAME", "PHONE_NUMBER", "EMAIL_ADDRESS", "STREET_ADDRESS"} <= names

    def test_explicit_project_wins_over_the_default(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"item": {"value": "x"}})

        mask_text("hola", make_settings(dlp_enabled=True, dlp_project="otro"), client_for(handler))
        assert "projects/otro/" in seen["url"]

    def test_long_text_is_split_and_reassembled_exactly(self):
        calls = []

        def echo(request):
            value = json.loads(request.read())["item"]["value"]
            calls.append(len(value))
            return httpx.Response(200, json={"item": {"value": value}})

        text = "\n\n".join(f"Párrafo {i}: " + "x" * 40 for i in range(10))
        out = mask_text(text, make_settings(dlp_enabled=True, dlp_chunk_chars=120), client_for(echo))
        assert out == text
        assert len(calls) > 1 and max(calls) <= 120

    def test_chunks_cut_a_single_giant_paragraph(self):
        parts = _chunks("a" * 250, 100)
        assert [len(p) for p in parts] == [100, 100, 50] and "".join(parts) == "a" * 250

    @pytest.mark.parametrize(
        "response",
        [httpx.Response(500, json={"error": "x"}), httpx.Response(200, json={"sin": "item"}), httpx.Response(200, text="no json")],
    )
    def test_dlp_failure_fails_closed(self, response):
        with pytest.raises(MaskingError):
            mask_text("Paciente: Ana", make_settings(dlp_enabled=True), client_for(lambda r: response))

    def test_unreachable_dlp_fails_closed(self):
        def down(request):
            raise httpx.ConnectError("sin red")

        with pytest.raises(MaskingError):
            mask_text("Paciente: Ana", make_settings(dlp_enabled=True), client_for(down))


class TestWiring:
    LONG = "Paciente: Juan Pérez\nGlucosa en ayunas 94 mg/dL referencia 70 - 100. Colesterol total 212 mg/dL."

    def test_native_text_is_masked_before_it_reaches_the_text_model(self):
        sent = []

        def handler(request):
            body = json.loads(request.read())
            sent.append(body["messages"][1]["content"])
            return httpx.Response(200, json=ok_response("## Analítica"))

        pages = [PageImage(index=1, data=PNG, mime="image/png", text=self.LONG)]
        vision_client.transcribe(pages, make_settings(max_retries=1), client_for(handler))
        assert "Juan Pérez" not in sent[0] and "[dato oculto]" in sent[0]
        assert "Glucosa en ayunas 94 mg/dL" in sent[0]

    def test_with_dlp_on_the_page_image_never_leaves_even_if_every_model_fails(self, monkeypatch):
        monkeypatch.setattr(vision_client, "mask_text", lambda text, settings, client=None: "[oculto]")
        requests = []

        def handler(request):
            requests.append(json.loads(request.read()))
            return httpx.Response(429, json={"error": {"message": "x"}})

        pages = [PageImage(index=1, data=PNG, mime="image/png", text=self.LONG)]
        settings = make_settings(max_retries=1, dlp_enabled=True, vision_fallback_model="otro/vision:free")
        with pytest.raises(vision_client.VisionError):
            vision_client.transcribe(pages, settings, client_for(handler))
        # se probaron todos los modelos, pero solo con texto: ninguna imagen salió
        assert len({r["model"] for r in requests}) == 3
        assert all(isinstance(r["messages"][1]["content"], str) for r in requests)
        assert "image_url" not in json.dumps(requests)

    def test_with_dlp_on_a_multimodal_model_rescues_the_text_only_failure(self, monkeypatch):
        monkeypatch.setattr(vision_client, "mask_text", lambda text, settings, client=None: "[oculto]")

        def handler(request):
            body = json.loads(request.read())
            if body["model"].startswith("nvidia"):
                return httpx.Response(429, json={"error": {"message": "x"}})
            assert isinstance(body["messages"][1]["content"], str)  # texto, no imagen
            return httpx.Response(200, json=ok_response("# Doc"))

        pages = [PageImage(index=1, data=PNG, mime="image/png", text=self.LONG)]
        out = vision_client.transcribe(pages, make_settings(max_retries=1, dlp_enabled=True), client_for(handler))
        assert out.mode == "text" and out.model == "qwen/qwen3.8-27b:free"

    def test_a_model_that_no_longer_exists_is_skipped_not_fatal(self):
        models = []

        def handler(request):
            model = json.loads(request.read())["model"]
            models.append(model)
            if model.startswith("qwen"):  # el modelo muerto: OpenRouter responde 404
                return httpx.Response(404, json={"error": {"message": "No endpoints found"}})
            return httpx.Response(200, json=ok_response("# Doc"))

        pages = [PageImage(index=1, data=PNG, mime="image/png")]  # una foto: va por visión
        settings = make_settings(max_retries=1, vision_fallback_model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
        out = vision_client.transcribe(pages, settings, client_for(handler))
        assert out.model == "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
        assert models == ["qwen/qwen3.8-27b:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"]

    def test_with_dlp_off_the_vision_fallback_still_works(self):
        models = []

        def handler(request):
            model = json.loads(request.read())["model"]
            models.append(model)
            if model.startswith("nvidia"):
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok_response("# Doc"))

        pages = [PageImage(index=1, data=PNG, mime="image/png", text=self.LONG)]
        out = vision_client.transcribe(pages, make_settings(max_retries=1), client_for(handler))
        assert out.mode == "vision" and models[-1] == "qwen/qwen3.8-27b:free"

    def test_vision_output_is_masked_but_text_output_is_not_masked_twice(self, monkeypatch):
        calls = []
        monkeypatch.setattr(to_markdown, "mask_text", lambda text, settings, client=None: calls.append(text) or text)

        def fake(batch, settings):
            out = vision_client.Transcription("# Doc\n\n## A\n\nx")
            out.model, out.mode = "m", "text" if batch[0].index == 1 else "vision"
            return out

        convert(make_pdf(2), make_settings(), transcriber=fake)
        assert len(calls) == 1  # solo la página que salió del modelo de visión

    def test_transcription_from_vision_has_no_identification_data(self):
        def fake(batch, settings):
            return "# Doc\n\nPaciente: Ana Ruiz\nC.C. 1.023.456.789\n\n## A\n\nGlucosa 92 mg/dL"

        result = convert(make_pdf(1), make_settings(), transcriber=fake)
        assert "Ana Ruiz" not in result.markdown and "1.023.456.789" not in result.markdown
        assert "Glucosa 92 mg/dL" in result.markdown
