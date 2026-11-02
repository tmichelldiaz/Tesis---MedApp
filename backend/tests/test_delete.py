import pymupdf
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_settings, get_store
from app.store import DocumentStore


def pdf_bytes() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "hola")
    return doc.tobytes()


def make_client(tmp_path, transcriber=lambda pages, settings: "# T\n\ncuerpo\n"):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    store = DocumentStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    from app.main import get_transcriber, get_values_extractor, get_indexer, get_classifier
    app.dependency_overrides[get_transcriber] = lambda: transcriber
    app.dependency_overrides[get_values_extractor] = lambda: (lambda markdown, settings: [])
    app.dependency_overrides[get_indexer] = lambda: (lambda store, doc_id, settings: [])
    app.dependency_overrides[get_classifier] = lambda: (lambda markdown, settings: "Otro")
    return TestClient(app), store


def upload(client, name="a.pdf"):
    return client.post("/documents", files={"files": (name, pdf_bytes(), "application/pdf")})


def test_delete_removes_document_and_its_place_in_the_library(tmp_path):
    client, _ = make_client(tmp_path)
    doc_id = upload(client).json()["id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["historia_slug"] == "historia-01"

    response = client.delete(f"/documents/{doc_id}")
    assert response.status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404
    assert doc_id not in [d["id"] for d in client.get("/documents").json()]

    root_index = client.get("/bundle.zip")
    assert root_index.status_code == 409  # no quedó ninguna historia
    app.dependency_overrides.clear()


def test_deleting_one_document_renumbers_nothing_for_the_rest(tmp_path):
    client, _ = make_client(tmp_path)
    first = upload(client, "a.pdf").json()["id"]
    second = upload(client, "b.pdf").json()["id"]
    assert client.get(f"/documents/{second}").json()["historia_slug"] == "historia-02"

    client.delete(f"/documents/{first}")

    second_after = client.get(f"/documents/{second}").json()
    assert second_after["historia_slug"] == "historia-02"  # no se renumera
    app.dependency_overrides.clear()


def test_delete_unknown_id_is_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.delete(f"/documents/{'0' * 32}").status_code == 404
    app.dependency_overrides.clear()
