"""El nombre del archivo debe verse exactamente como lo tiene el paciente.

Android manda los espacios codificados ("Prueba 8.pdf" llega como "Prueba%208.pdf")."""

import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_current_user, get_settings, get_store
from app.store import DocumentStore, clean_filename


@pytest.mark.parametrize("sent, shown", [
    ("Prueba%208.pdf", "Prueba 8.pdf"),
    ("Prueba%202%20(1).pdf", "Prueba 2 (1).pdf"),
    ("Informe%20m%C3%A9dico%20Mar%C3%ADa.pdf", "Informe médico María.pdf"),
    ("examen 20.pdf", "examen 20.pdf"),
    ("Reporte 50%.pdf", "Reporte 50%.pdf"),          # un % que no es un código se respeta
    ("Resultado_100%25.pdf", "Resultado_100%.pdf"),
    ("../../etc/passwd", "passwd"),                    # nunca una ruta
    ("%2E%2E%2Fsecreto.pdf", "secreto.pdf"),           # ni una ruta escondida en la codificación
    ("", "documento"), (None, "documento"), ("   ", "documento"),
])
def test_clean_filename(sent, shown):
    assert clean_filename(sent) == shown


def make_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Resultados " * 10, fontsize=12)
    return doc.tobytes()


@pytest.fixture
def client(tmp_path):
    cfg = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    store = DocumentStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: {"id": "u", "email": "u@example.com"}
    yield TestClient(app), store
    app.dependency_overrides.clear()


def test_an_uploaded_file_keeps_the_exact_name(client, monkeypatch):
    http, store = client
    from app import main

    monkeypatch.setattr(main, "process_document", lambda *a, **k: None)  # solo importa el nombre
    response = http.post("/documents", files={"files": ("Prueba%208.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 202
    assert response.json()["filename"] == "Prueba 8.pdf"
    assert store.list_all()[0]["filename"] == "Prueba 8.pdf"


def test_files_uploaded_before_the_fix_are_shown_decoded(client):
    http, store = client
    meta = store.create("Prueba 8.pdf", make_pdf(), "pdf")
    path = store.root / meta["id"] / "meta.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["filename"] = "Prueba%202%20(1).pdf"           # así quedó guardado antes
    path.write_text(json.dumps(stored), encoding="utf-8")
    assert [d["filename"] for d in http.get("/documents").json()] == ["Prueba 2 (1).pdf"]
