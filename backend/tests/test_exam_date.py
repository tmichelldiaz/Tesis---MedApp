"""La fecha del examen: se lee del documento, se aplica a los valores y manda sobre el orden de subida."""

from datetime import date

import pymupdf
import pytest

from app.config import Settings
from app.extraction.exam_date import find_exam_date
from app.extraction.lab_values import LabValue
from app.service import extract_document_values, process_document
from app.store import DocumentStore
from app.values_history import latest_per_exam, oldest_first

TODAY = date(2026, 10, 12)


class TestFindExamDate:
    @pytest.mark.parametrize("text, expected", [
        ("Fecha de toma de muestra: 02/09/2026 07:45\nFecha de resultado: 03/09/2026", "2026-09-02"),
        ("FECHA DE RESULTADO: 3 de septiembre de 2026", "2026-09-03"),
        ("Fecha de atención: 2026-08-15", "2026-08-15"),
        ("Fecha: 15-08-2026", "2026-08-15"),
        ("Fecha del examen 10 mar 2026", "2026-03-10"),
        ("Fecha y hora de toma de muestra 5.1.2026 08:10", "2026-01-05"),
        ("fecha de toma de muestra: 09/25/2026", "2026-09-25"),  # mes/día si el primer número no puede ser un día
        ("Fecha de resultado: 14 de octubre del 2025", "2025-10-14"),
    ])
    def test_reads_the_usual_formats_and_labels(self, text, expected):
        assert find_exam_date(text, TODAY) == expected

    def test_the_sample_date_wins_over_the_result_date(self):
        text = "Fecha de resultado: 05/09/2026\nFecha de toma de muestra: 02/09/2026"
        assert find_exam_date(text, TODAY) == "2026-09-02"

    @pytest.mark.parametrize("text", [
        "Fecha de nacimiento: 14/03/1985",
        "Fecha de impresión: 04/09/2026",
        "Fecha de ingreso: 01/09/2026",
        "Fecha de nacimiento: 14/03/1985\nFecha de impresión: 04/09/2026\nFecha de ingreso: 01/09/2026",
    ])
    def test_ignores_personal_and_administrative_dates(self, text):
        assert find_exam_date(text, TODAY) is None

    @pytest.mark.parametrize("text", [
        "Control realizado el 10/03/2026: glucosa 118",   # una fecha suelta, sin etiqueta
        "Fecha de resultado: 31/12/2030",                   # del futuro
        "Fecha de resultado: 01/01/1950",                   # demasiado antigua
        "Fecha de resultado: 31/02/2026",                   # no existe
        "", "   ", "sin fechas aquí",
    ])
    def test_does_not_guess(self, text):
        assert find_exam_date(text, TODAY) is None

    def test_a_birth_date_next_to_the_exam_date_does_not_confuse_it(self):
        text = "Fecha de nacimiento: 14/03/1985 (41 años)\nFecha de toma de muestra: 02/09/2026"
        assert find_exam_date(text, TODAY) == "2026-09-02"


def pdf_with(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=10)
    return doc.tobytes()


def run(store, settings, text, values):
    meta = store.create("laboratorio.pdf", pdf_with(text), "pdf")
    process_document(
        store, meta["id"], settings,
        transcriber=lambda pages, s: "## Hematología\n\n| Examen | Resultado |\n|---|---|\n| Glucosa | 92 |\n",
        values_extractor=lambda md, s: values,
        indexer=lambda st, d, s: [],
        classifier=lambda md, s: "Resultados de laboratorio",
    )
    return store.get(meta["id"])


@pytest.fixture
def settings(tmp_path):
    return Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)


HEADER = "LABORATORIO\nFecha de nacimiento: 14/03/1985\nFecha de toma de muestra: 02/09/2026 07:45\nGlucosa 92 mg/dL\nUrea 30 mg/dL\n" + "texto " * 20


class TestPipeline:
    def test_values_without_a_date_get_the_documents_exam_date(self, tmp_path, settings):
        doc = run(DocumentStore(tmp_path), settings, HEADER, [LabValue("Glucosa", "92", 92.0, "mg/dL")])
        assert doc["exam_date"] == "2026-09-02"
        assert [v["date"] for v in doc["lab_values"]] == ["2026-09-02"]

    def test_a_value_that_already_has_its_own_date_keeps_it(self, tmp_path, settings):
        values = [LabValue("Glucosa", "92", 92.0, "mg/dL", date="2026-08-30"), LabValue("Urea", "30", 30.0, "mg/dL")]
        doc = run(DocumentStore(tmp_path), settings, HEADER, values)
        assert [v["date"] for v in doc["lab_values"]] == ["2026-08-30", "2026-09-02"]

    def test_a_document_without_a_clear_date_leaves_values_undated(self, tmp_path, settings):
        doc = run(DocumentStore(tmp_path), settings, "LABORATORIO\nGlucosa 92 mg/dL\n" + "texto " * 20, [LabValue("Glucosa", "92", 92.0, "mg/dL")])
        assert doc["exam_date"] is None and doc["lab_values"][0]["date"] is None

    def test_the_date_is_read_before_masking_so_spelled_months_survive(self, tmp_path, settings, monkeypatch):
        # El DLP real convierte "10 de marzo de 2026" en "10 [dato oculto] de 2026"; la fecha se lee antes.
        from app.extraction import to_markdown

        monkeypatch.setattr(to_markdown, "mask_text", lambda text, s, client=None: text.replace("marzo", "[dato oculto]"))
        text = "LABORATORIO\nFecha de toma de muestra: 10 de marzo de 2026\n" + "texto " * 20
        doc = run(DocumentStore(tmp_path), settings, text, [LabValue("Glucosa", "92", 92.0, "mg/dL")])
        assert doc["exam_date"] == "2026-03-10"

    def test_re_extracting_values_also_applies_the_date(self, tmp_path, settings):
        store = DocumentStore(tmp_path)
        doc = run(store, settings, HEADER, [])
        out = extract_document_values(store, doc["id"], settings, values_extractor=lambda md, s: [LabValue("Glucosa", "92", 92.0)])
        assert out["lab_values"][0]["date"] == "2026-09-02"


class TestOrderingByExamDate:
    def test_a_newer_exam_uploaded_first_is_still_the_current_one(self):
        # El examen de septiembre se subió DESPUÉS que el de octubre: manda la fecha del examen, no la subida.
        rows = [
            {"exam": "Glucosa", "value_raw": "90", "date": "2026-10-01", "document_created_at": "2026-10-12T10:00:00Z"},
            {"exam": "Glucosa", "value_raw": "100", "date": "2026-09-01", "document_created_at": "2026-10-12T11:00:00Z"},
        ]
        assert [r["value_raw"] for r in oldest_first(rows)] == ["100", "90"]
        assert latest_per_exam(rows)["glucosa"]["value_raw"] == "90"
