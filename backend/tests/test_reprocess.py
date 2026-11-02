"""Volver a leer una historia ya procesada con los modelos actuales, sin perder lo que ya estaba bien."""

import pymupdf
import pytest

from app.config import Settings
from app.extraction.lab_values import LabValue
from app.extraction.vision_client import VisionError
from app.service import process_document, reprocess_document
from app.store import DocumentStore


def pdf_with(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=10)
    return doc.tobytes()


def values(*pairs):
    return [LabValue(exam=e, value_raw=v, value_numeric=float(v), unit=None, date="2026-10-01",
                     reference_low=None, reference_high=None, reference_text=None) for e, v in pairs]


OLD = values(("Glucosa", "92"))
NEW = values(("Glucosa", "92"), ("Sodio", "138"))
SOURCE = "Glucosa 92\nSodio 138"


@pytest.fixture
def setup(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    store = DocumentStore(tmp_path)
    meta = store.create("lab.pdf", pdf_with(SOURCE), "pdf")
    process_document(
        store, meta["id"], settings,
        transcriber=lambda pages, s: "## Lab\n\n| Examen | Resultado |\n|---|---|\n| Glucosa | 92 |\n",
        values_extractor=lambda md, s: OLD,
        indexer=lambda st, d, s: [],
        classifier=lambda md, s: "Resultados de laboratorio",
    )
    return store, settings, meta["id"]


def reprocess(store, settings, doc_id, extractor=lambda md, s: NEW, transcriber=None):
    # El servidor marca el documento "procesando" antes de lanzar la relectura.
    store.update(doc_id, status="processing")
    reprocess_document(
        store, doc_id, settings,
        transcriber=transcriber or (lambda pages, s: "## Lab\n\n| Examen | Resultado |\n|---|---|\n| Glucosa | 92 |\n| Sodio | 138 |\n"),
        values_extractor=extractor,
        indexer=lambda st, d, s: [],
        classifier=lambda md, s: "Otra categoría",
    )
    return store.get(doc_id)


def test_the_new_reading_replaces_the_old_one_and_remembers_how_many_there_were(setup):
    store, settings, doc_id = setup
    assert len(store.get(doc_id)["lab_values"]) == 1
    meta = reprocess(store, settings, doc_id)
    assert meta["status"] == "ready"
    assert [v["exam"] for v in meta["lab_values"]] == ["Glucosa", "Sodio"]
    assert meta["values_before"] == 1


def test_the_category_the_patient_already_had_is_kept(setup):
    store, settings, doc_id = setup
    before = store.get(doc_id)["category"]
    assert reprocess(store, settings, doc_id)["category"] == before


def test_a_failed_reading_leaves_the_document_exactly_as_it_was(setup):
    store, settings, doc_id = setup
    original = store.get(doc_id)

    def broken(pages, s):
        raise VisionError("el modelo no respondió")

    meta = reprocess(store, settings, doc_id, transcriber=broken)
    assert meta["status"] == "ready" and meta["error"] is None
    assert meta["lab_values"] == original["lab_values"]
    assert meta["category"] == original["category"]
    assert meta["values_before"] is None
