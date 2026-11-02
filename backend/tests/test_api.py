import io
import zipfile

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extraction.vision_client import VisionError
from app.main import app, get_settings, get_store, get_transcriber, get_values_extractor, get_indexer, get_classifier
from app.store import DocumentStore

SAMPLE_MD = "# Lab\n\nPaciente: X\n\n## Sangre\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## Notas\n\nControl en 3 meses.\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def pdf_bytes() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "hola")
    return doc.tobytes()


@pytest.fixture
def make_client(tmp_path):
    def build(
        transcriber=lambda pages, settings: SAMPLE_MD,
        values_extractor=lambda markdown, settings: [],
        classifier=lambda markdown, settings: "Otro",
        **settings_kw,
    ):
        settings = Settings(
            openrouter_api_key="k", data_dir=tmp_path, _env_file=None, **settings_kw
        )
        store = DocumentStore(tmp_path)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_transcriber] = lambda: transcriber
        app.dependency_overrides[get_values_extractor] = lambda: values_extractor
        app.dependency_overrides[get_indexer] = lambda: (lambda store, doc_id, settings: [])
        app.dependency_overrides[get_classifier] = lambda: classifier
        return TestClient(app)

    yield build
    app.dependency_overrides.clear()


def upload(client, data=None, name="resultado.pdf"):
    return client.post("/documents", files={"files": (name, pdf_bytes() if data is None else data, "application/octet-stream")})


def test_upload_returns_job_id_and_processes_to_a_valid_bundle(make_client):
    client = make_client()
    response = upload(client)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing" and len(body["id"]) == 32
    assert "original" not in body

    detail = client.get(f"/documents/{body['id']}").json()
    assert detail["status"] == "ready"
    assert detail["validation"]["state"] == "valid"
    assert [c["title"] for c in detail["concepts"]] == ["Lab", "Sangre", "Notas"]
    assert detail["page_count"] == 1 and detail["filename"] == "resultado.pdf"


def test_list_is_newest_first(make_client):
    client = make_client()
    first = upload(client, name="a.pdf").json()["id"]
    second = upload(client, name="b.pdf").json()["id"]
    ids = [d["id"] for d in client.get("/documents").json()]
    assert set(ids) == {first, second}


def test_bundle_file_and_zip(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()

    text = client.get(f"/documents/{doc_id}/files/{detail['concepts'][1]['filename']}").text
    assert text.startswith("---\ntype: Clinical Document Section")

    slug = detail["historia_slug"]
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/documents/{doc_id}/bundle.zip").content))
    names = archive.namelist()
    assert f"{slug}/index.md" in names and f"{slug}/log.md" in names and len(names) == 5


def test_documents_are_nested_under_one_shared_library_bundle(make_client):
    client = make_client()
    first = upload(client, name="a.pdf").json()["id"]
    second = upload(client, name="b.pdf").json()["id"]
    first_detail = client.get(f"/documents/{first}").json()
    second_detail = client.get(f"/documents/{second}").json()

    assert first_detail["historia_slug"] == "historia-01"
    assert second_detail["historia_slug"] == "historia-02"

    archive = zipfile.ZipFile(io.BytesIO(client.get("/bundle.zip").content))
    names = set(archive.namelist())
    assert {"bundle/index.md", "bundle/log.md"} <= names
    assert "bundle/historia-01/index.md" in names and "bundle/historia-02/index.md" in names

    root_index = archive.read("bundle/index.md").decode("utf-8")
    assert "1. [a.pdf](historia-01/index.md)" in root_index
    assert "2. [b.pdf](historia-02/index.md)" in root_index

    root_log = archive.read("bundle/log.md").decode("utf-8")
    assert "1. a.pdf -> historia-01" in root_log and "2. b.pdf -> historia-02" in root_log
    assert "Total de historias: 2" in root_log


def test_library_bundle_zip_requires_at_least_one_ready_document(make_client):
    assert make_client().get("/bundle.zip").status_code == 409


def test_failed_document_never_claims_a_historia_number(make_client):
    client = make_client(transcriber=lambda p, s: (_ for _ in ()).throw(VisionError("429")))
    upload(client)
    detail = client.get("/documents").json()[0]
    assert detail["status"] == "failed" and detail["historia_slug"] is None
    assert client.get("/bundle.zip").status_code == 409


def test_file_endpoint_blocks_path_traversal(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    for name in ("..%2Fmeta.json", "meta.json", "..%2F..%2Fsecret"):
        assert client.get(f"/documents/{doc_id}/files/{name}").status_code == 404


def test_unknown_or_malformed_ids_are_404(make_client):
    client = make_client()
    for doc_id in ("0" * 32, "..", "nope"):
        assert client.get(f"/documents/{doc_id}").status_code == 404
    assert client.get(f"/documents/{'0' * 32}/bundle.zip").status_code == 404


def test_rejects_unsupported_format(make_client):
    response = upload(make_client(), data=b"MZ\x90\x00 no soy un documento", name="virus.exe")
    assert response.status_code == 415


def test_rejects_empty_and_oversize(make_client):
    client = make_client(max_file_mb=1)
    assert upload(client, data=b"").status_code in (400, 422)
    assert upload(client, data=PNG + b"0" * (1024 * 1024)).status_code == 413


def test_model_failure_marks_document_failed(make_client):
    def broken(pages, settings):
        raise VisionError("OpenRouter respondió 429: límite")

    client = make_client(transcriber=broken)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    # El error que ve el paciente es genérico a propósito: el mensaje técnico
    # (proveedor, código HTTP) solo debe quedar en los logs del servidor.
    assert detail["status"] == "failed"
    assert "429" not in detail["error"] and "OpenRouter" not in detail["error"]
    assert client.get(f"/documents/{doc_id}/bundle.zip").status_code == 409


def test_masking_failure_marks_document_failed_with_a_generic_message(make_client):
    from app.privacy.masking import MaskingError

    def broken(pages, settings):
        raise MaskingError("Cloud DLP no respondió: 503 proyecto medapp-thesis")

    client = make_client(transcriber=broken)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "failed"
    assert "DLP" not in detail["error"] and "medapp-thesis" not in detail["error"]


def test_unexpected_error_is_not_leaked(make_client):
    def crash(pages, settings):
        raise RuntimeError("secreto interno")

    client = make_client(transcriber=crash)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "failed" and "secreto" not in detail["error"]


def test_health(make_client):
    body = make_client().get("/health").json()
    assert body["ok"] and body["api_key_configured"]


def test_failed_document_can_be_retried(make_client):
    calls = {"n": 0}

    def flaky(pages, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            raise VisionError("OpenRouter respondió 429: límite")
        return SAMPLE_MD

    client = make_client(transcriber=flaky)
    doc_id = upload(client).json()["id"]
    assert client.get(f"/documents/{doc_id}").json()["status"] == "failed"

    assert client.post(f"/documents/{doc_id}/retry").status_code == 202
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "ready" and detail["error"] is None


def test_retry_only_for_failed_documents(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    assert client.post(f"/documents/{doc_id}/retry").status_code == 409
    assert client.post(f"/documents/{'0' * 32}/retry").status_code == 404


def test_rebuild_resegments_from_saved_transcription_without_the_model(make_client):
    calls = {"n": 0}

    def once(pages, settings):
        calls["n"] += 1
        return SAMPLE_MD

    client = make_client(transcriber=once)
    doc_id = upload(client).json()["id"]
    before = client.get(f"/documents/{doc_id}").json()

    response = client.post(f"/documents/{doc_id}/rebuild")
    assert response.status_code == 200
    assert calls["n"] == 1
    assert [c["title"] for c in response.json()["concepts"]] == [c["title"] for c in before["concepts"]]
    assert response.json()["validation"]["state"] == "valid"


def test_rebuild_requires_a_transcription(make_client, tmp_path):
    client = make_client(transcriber=lambda p, s: (_ for _ in ()).throw(VisionError("429")))
    doc_id = upload(client).json()["id"]
    assert client.post(f"/documents/{doc_id}/rebuild").status_code == 409
    assert client.post(f"/documents/{'0' * 32}/rebuild").status_code == 404


FAKE_VALUES = [
    {"exam": "Glucosa en ayunas", "value_raw": "94", "value_numeric": 94.0, "unit": "mg/dL",
     "date": "2026-03-10", "reference_low": 70.0, "reference_high": 100.0, "reference_text": "70 - 100"},
]


def fake_extractor(markdown, settings):
    from app.extraction.lab_values import LabValue
    return [LabValue(**FAKE_VALUES[0])]


def test_upload_stores_structured_lab_values(make_client):
    client = make_client(values_extractor=fake_extractor)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["lab_values"] == FAKE_VALUES


def test_upload_stores_the_ai_suggested_category(make_client):
    client = make_client(classifier=lambda markdown, settings: "Medicamentos")
    doc_id = upload(client).json()["id"]
    assert client.get(f"/documents/{doc_id}").json()["category"] == "Medicamentos"


def test_category_classification_failure_does_not_fail_the_document(make_client):
    def broken(markdown, settings):
        raise VisionError("OpenRouter respondió 429: límite", transient=True)

    client = make_client(classifier=broken)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "ready" and detail["category"] == "Otro"


def test_list_categories_returns_the_fixed_set(make_client):
    client = make_client()
    response = client.get("/categories")
    assert response.status_code == 200
    assert response.json() == [
        "Resultados de laboratorio", "Medicamentos", "Diagnósticos", "Notas de consulta", "Otro",
    ]


def test_classify_category_endpoint_reruns_classification(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    assert client.get(f"/documents/{doc_id}").json()["category"] == "Otro"

    app.dependency_overrides[get_classifier] = lambda: (lambda markdown, settings: "Diagnósticos")
    response = client.post(f"/documents/{doc_id}/classify-category")
    assert response.status_code == 200
    assert response.json()["category"] == "Diagnósticos"


def test_classify_category_endpoint_requires_a_transcription(make_client):
    client = make_client(transcriber=lambda p, s: (_ for _ in ()).throw(VisionError("429")))
    doc_id = upload(client).json()["id"]
    assert client.post(f"/documents/{doc_id}/classify-category").status_code == 409
    assert client.post(f"/documents/{'0' * 32}/classify-category").status_code == 404


def test_set_category_manually_overrides_it(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    response = client.put(f"/documents/{doc_id}/category", json={"category": "Medicamentos"})
    assert response.status_code == 200
    assert response.json()["category"] == "Medicamentos"
    assert client.get(f"/documents/{doc_id}").json()["category"] == "Medicamentos"


def test_set_category_rejects_unknown_values(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    response = client.put(f"/documents/{doc_id}/category", json={"category": "Cardiología"})
    assert response.status_code == 400


def test_set_category_unknown_document_is_404(make_client):
    client = make_client()
    response = client.put(f"/documents/{'0' * 32}/category", json={"category": "Otro"})
    assert response.status_code == 404


def test_lab_value_extraction_failure_does_not_fail_the_document(make_client):
    def broken(markdown, settings):
        raise VisionError("OpenRouter respondió 429: límite", transient=True)

    client = make_client(values_extractor=broken)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "ready" and detail["lab_values"] == []


def test_extract_values_endpoint_reruns_extraction_from_saved_transcription(make_client):
    client = make_client()
    doc_id = upload(client).json()["id"]
    assert client.get(f"/documents/{doc_id}").json()["lab_values"] == []

    app.dependency_overrides[get_values_extractor] = lambda: fake_extractor
    response = client.post(f"/documents/{doc_id}/extract-values")
    assert response.status_code == 200
    assert response.json()["lab_values"] == FAKE_VALUES


def test_extract_values_endpoint_requires_a_transcription(make_client):
    client = make_client(transcriber=lambda p, s: (_ for _ in ()).throw(VisionError("429")))
    doc_id = upload(client).json()["id"]
    assert client.post(f"/documents/{doc_id}/extract-values").status_code == 409
    assert client.post(f"/documents/{'0' * 32}/extract-values").status_code == 404


def test_list_values_aggregates_across_ready_documents_sorted_by_date(make_client):
    from app.extraction.lab_values import LabValue

    def extractor(markdown, settings):
        return [LabValue(exam="Glucosa", value_raw="94", date="2026-03-10"),
                LabValue(exam="Colesterol", value_raw="200", date="2026-01-05")]

    client = make_client(values_extractor=extractor)
    doc_id = upload(client).json()["id"]

    rows = client.get("/values").json()
    assert [r["exam"] for r in rows] == ["Colesterol", "Glucosa"]
    assert rows[0]["document_id"] == doc_id and rows[0]["document_filename"] == "resultado.pdf"


def test_list_values_filters_by_exam_substring(make_client):
    client = make_client(values_extractor=fake_extractor)
    upload(client)
    assert len(client.get("/values", params={"exam": "glucosa"}).json()) == 1
    assert len(client.get("/values", params={"exam": "colesterol"}).json()) == 0


def test_list_values_ignores_documents_still_processing_or_failed(make_client):
    client = make_client(transcriber=lambda p, s: (_ for _ in ()).throw(VisionError("429")))
    upload(client)
    assert client.get("/values").json() == []
