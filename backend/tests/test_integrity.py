"""Ningún número del documento se pierde ni se inventa al pasar por un modelo.

Caso real (laboratorio de 3 páginas): Gemini 2.5 Flash Lite conservó solo 16 de los 74 números de la
página 2 y la app dejó de mostrar sodio, potasio, el perfil de colesterol, TSH, T4 libre y más."""

import httpx
import pymupdf
import pytest

from app.config import Settings
from app.extraction import vision_client
from app.extraction.documents import PageImage
from app.extraction.integrity import is_grounded, keeps_the_numbers, lost_numbers
from app.extraction.lab_values import LabValue
from app.service import process_document
from app.store import DocumentStore

SOURCE = "Sodio 135 mmol/L (136 - 145)\nPotasio 4,1 mmol/L (3.5 - 5.1)\nColesterol total 212 mg/dL"


class TestNumbers:
    def test_a_faithful_rewrite_keeps_everything(self):
        out = "| Sodio | 135 | mmol/L |\n| Potasio | 4.1 | mmol/L |\n| Colesterol total | 212 | mg/dL |\n(136 - 145) (3.5 - 5.1)"
        assert lost_numbers(SOURCE, out) == [] and keeps_the_numbers(SOURCE, out)

    def test_decimal_comma_and_point_are_the_same_number(self):
        assert lost_numbers("Glucosa 4,1", "Glucosa 4.1") == []

    def test_dropped_rows_are_detected(self):
        out = "Sodio 135 mmol/L"
        assert sorted(lost_numbers(SOURCE, out)) == ["136", "145", "212", "3.5", "4.1", "5.1"]
        assert not keeps_the_numbers(SOURCE, out)

    def test_a_repeated_number_must_appear_as_many_times(self):
        assert lost_numbers("Hb 13 y Hto 13", "Hb 13") == ["13"]

    def test_a_tiny_loss_is_tolerated_in_a_long_document(self):
        source = " ".join(f"v{i} {i}.5" for i in range(100))
        assert keeps_the_numbers(source, source.replace("v7 7.5", "v7"))
        assert not keeps_the_numbers(source, " ".join(f"v{i} {i}.5" for i in range(80)))


class TestGrounding:
    def test_a_value_present_in_the_document_is_grounded(self):
        assert is_grounded("135", SOURCE) and is_grounded("4,1", SOURCE) and is_grounded("4.1 mmol/L", SOURCE)

    def test_a_value_the_document_does_not_contain_is_not(self):
        assert not is_grounded("0.182", "Densidad de PSA 0.142")

    def test_values_without_numbers_cannot_be_checked_and_are_accepted(self):
        assert is_grounded("Negativa", SOURCE)


def pages(*texts):
    return [PageImage(index=i + 1, data=b"", mime="image/png", text=t) for i, t in enumerate(texts)]


class TestTranscribeEscalates:
    @pytest.fixture
    def settings(self):
        return Settings(
            openrouter_api_key="k", _env_file=None, dlp_enabled=True, retry_min_wait_s=0, retry_max_wait_s=0,
            text_fallback_model="primero", vision_model="segundo", vision_fallback_model="tercero",
        )

    def run(self, settings, monkeypatch, behaviour):
        calls = []
        self.messages = []

        self.options = []

        def fake(model, mode, messages, s, client, response_format=None, reasoning=None):
            attempt = calls.count(model)
            calls.append(model)
            self.messages.append(messages)
            self.options.append({"reasoning": reasoning, "max_tokens": s.max_output_tokens})
            answers = behaviour[model]
            text = answers[min(attempt, len(answers) - 1)] if isinstance(answers, list) else answers
            out = vision_client.Transcription(text)
            out.model, out.mode = model, mode
            return out

        monkeypatch.setattr(vision_client, "chat_completion", fake)
        monkeypatch.setattr(vision_client, "mask_text", lambda text, s, client=None: text)
        result = vision_client.transcribe(pages(SOURCE + "\n" + "texto " * 10), settings)
        return result, calls

    FULL = "## Química\n| Sodio | 135 |\n(136 - 145) Potasio 4.1 (3.5 - 5.1) Colesterol total 212 " + "texto " * 10

    def test_a_model_that_drops_numbers_is_skipped_for_the_next_one(self, settings, monkeypatch):
        result, calls = self.run(settings, monkeypatch, {"primero": "## Química\nSodio 135", "segundo": self.FULL, "tercero": self.FULL})
        assert calls == ["primero", "primero", "segundo"] and result.model == "segundo"  # 2 intentos por modelo

    def test_the_same_model_is_asked_again_telling_it_which_numbers_it_omitted(self, settings, monkeypatch):
        result, calls = self.run(settings, monkeypatch, {"primero": ["## Química\nSodio 135", self.FULL], "segundo": "x", "tercero": "x"})
        assert calls == ["primero", "primero"] and result.model == "primero"   # no hizo falta cambiar de modelo
        retry = self.messages[1]
        assert retry[-1]["role"] == "user" and "omitió" in retry[-1]["content"]
        assert "212" in retry[-1]["content"] and "136" in retry[-1]["content"]  # le dice cuáles faltaron

    def test_transcription_runs_without_reasoning_and_with_a_capped_output(self, settings, monkeypatch):
        # Con el razonamiento activado, Gemini 2.5 Flash a veces repetía basura hasta llenar el límite.
        self.run(settings, monkeypatch, {"primero": self.FULL, "segundo": "x", "tercero": "x"})
        assert self.options[0]["reasoning"] == {"enabled": False}
        assert self.options[0]["max_tokens"] <= settings.transcribe_max_tokens == 6144

    def test_a_faithful_first_model_is_used_without_trying_others(self, settings, monkeypatch):
        result, calls = self.run(settings, monkeypatch, {"primero": self.FULL, "segundo": "x", "tercero": "x"})
        assert calls == ["primero"]

    def test_if_every_model_loses_data_the_original_text_is_used_untouched(self, settings, monkeypatch):
        bad = "## Resumen\nSodio normal"
        result, calls = self.run(settings, monkeypatch, {"primero": bad, "segundo": bad, "tercero": bad})
        assert calls == ["primero", "primero", "segundo", "segundo", "tercero", "tercero"]
        assert "135" in str(result) and "212" in str(result) and "(136 - 145)" in str(result)
        assert result.model == "texto original (sin IA)"


def pdf_with(text):
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=10)
    return doc.tobytes()


class TestValuesMustExistInTheDocument:
    def run(self, tmp_path, text, values):
        settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
        store = DocumentStore(tmp_path)
        meta = store.create("lab.pdf", pdf_with(text), "pdf")
        process_document(
            store, meta["id"], settings,
            transcriber=lambda p, s: "## Hematología\nGlucosa 92\n",
            values_extractor=lambda md, s: values,
            indexer=lambda st, d, s: [], classifier=lambda md, s: "Resultados de laboratorio",
        )
        return store.get(meta["id"])

    TEXT = "LABORATORIO CLINICO\nGlucosa en ayunas 92 mg/dL referencia 70 - 100\n" + "texto " * 12

    def test_an_invented_value_is_dropped_and_a_real_one_is_kept(self, tmp_path):
        values = [LabValue("Glucosa", "92", 92.0, "mg/dL"), LabValue("Creatinina", "0.8", 0.8, "mg/dL")]
        doc = self.run(tmp_path, self.TEXT, values)
        assert [v["exam"] for v in doc["lab_values"]] == ["Glucosa"]

    def test_a_scan_with_almost_no_text_is_not_checked(self, tmp_path):
        # Una foto/escaneo: los valores salen de leer la imagen y no están en la capa de texto.
        doc = self.run(tmp_path, "hola", [LabValue("Glucosa", "92", 92.0, "mg/dL")])
        assert [v["value_raw"] for v in doc["lab_values"]] == ["92"]


class TestLoopsAreCutShort:
    """Gemini 2.5 Flash a veces se quedaba escribiendo guiones sin parar en la fila separadora de una tabla."""

    @pytest.fixture
    def settings(self):
        return Settings(
            openrouter_api_key="k", _env_file=None, dlp_enabled=True, retry_min_wait_s=0, retry_max_wait_s=0,
            text_fallback_model="primero", vision_model="segundo", vision_fallback_model="tercero",
        )

    def run(self, settings, monkeypatch, behaviour):
        calls, caps = [], []

        def fake(model, mode, messages, s, client, response_format=None, reasoning=None):
            calls.append(model)
            caps.append(s.max_output_tokens)
            out = vision_client.Transcription(behaviour[model])
            out.model, out.mode = model, mode
            return out

        monkeypatch.setattr(vision_client, "chat_completion", fake)
        monkeypatch.setattr(vision_client, "mask_text", lambda text, s, client=None: text)
        result = vision_client.transcribe(pages(SOURCE + "\n" + "texto " * 10), settings)
        return result, calls, caps

    GOOD = "## Química\n|---|---|\n| Sodio | 135 |\n(136 - 145) Potasio 4.1 (3.5 - 5.1) Colesterol total 212 " + "texto " * 10
    LOOP = "## Química\n| Examen | Resultado |\n| :" + "-" * 20000

    def test_a_loop_is_not_retried_on_the_same_model(self, settings, monkeypatch):
        result, calls, _ = self.run(settings, monkeypatch, {"primero": self.LOOP, "segundo": self.GOOD, "tercero": self.GOOD})
        assert calls == ["primero", "segundo"] and result.model == "segundo"

    def test_the_output_limit_follows_the_size_of_the_page(self, settings, monkeypatch):
        _, _, caps = self.run(settings, monkeypatch, {"primero": self.GOOD, "segundo": "x", "tercero": "x"})
        assert caps == [1500]  # una página corta no necesita miles de tokens

    def test_the_prompt_asks_for_a_minimal_table_separator(self):
        assert "|---|---|---|" in vision_client.TEXT_SYSTEM_PROMPT
