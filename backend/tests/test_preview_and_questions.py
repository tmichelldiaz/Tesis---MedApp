"""Vista previa de un PDF antes de subirlo, y texto de las preguntas para el médico."""

import base64

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.agent.text import tidy_question
from app.agent.tools import build_tools
from app.calendar_store import CalendarStore
from app.config import Settings
from app.main import app, get_current_user, get_settings
from app.profile_store import ProfileStore
from app.store import DocumentStore


def make_pdf(pages=3) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 100), f"Página {i + 1} de prueba", fontsize=20)
    return doc.tobytes()


@pytest.fixture
def client(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None, max_file_mb=1)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "email": "a@b.co"}
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestPdfPreview:
    def test_returns_the_first_page_as_a_png_and_the_page_count(self, client):
        response = client.post("/documents/preview", files={"file": ("historia.pdf", make_pdf(3), "application/pdf")})
        assert response.status_code == 200
        body = response.json()
        assert body["page_count"] == 3
        png = base64.b64decode(body["image_base64"])
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png) < 400_000  # liviana: se manda por una red móvil

    def test_the_preview_is_not_stored_anywhere(self, client, tmp_path):
        client.post("/documents/preview", files={"file": ("historia.pdf", make_pdf(1), "application/pdf")})
        assert not any(p.is_file() for p in tmp_path.rglob("*") if "original" in p.name or p.suffix == ".pdf")

    def test_rejects_something_that_is_not_a_pdf(self, client):
        response = client.post("/documents/preview", files={"file": ("nota.txt", b"hola", "text/plain")})
        assert response.status_code == 415

    def test_rejects_a_corrupt_pdf(self, client):
        response = client.post("/documents/preview", files={"file": ("roto.pdf", b"%PDF-1.4 roto", "application/pdf")})
        assert response.status_code == 415

    def test_rejects_a_file_over_the_size_limit(self, client):
        big = make_pdf(1) + b"0" * (1024 * 1024 + 10)
        response = client.post("/documents/preview", files={"file": ("grande.pdf", big, "application/pdf")})
        assert response.status_code == 413

    def test_a_password_protected_pdf_gets_a_clear_message(self, client):
        doc = pymupdf.open()
        doc.new_page()
        protected = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="clave", owner_pw="clave")
        response = client.post("/documents/preview", files={"file": ("secreto.pdf", protected, "application/pdf")})
        assert response.status_code == 415 and "contraseña" in response.json()["detail"]


class TestTidyQuestion:
    def test_lowercases_all_caps_exam_names_and_restores_accents(self):
        text = "Revisar los resultados de RECUENTO DE GLOBULOS BLANCOS, VOLUMEN CORPUSCULAR MEDIO y PLAQUETAS"
        assert tidy_question(text) == (
            "Revisar los resultados de recuento de glóbulos blancos, volumen corpuscular medio y plaquetas"
        )

    def test_keeps_acronyms_and_already_well_written_text(self):
        assert tidy_question("¿Mi COLESTEROL LDL está bien?") == "¿Mi colesterol LDL está bien?"
        assert tidy_question("¿Puedo hacer ejercicio con mi prediabetes?") == "¿Puedo hacer ejercicio con mi prediabetes?"

    def test_always_starts_with_a_capital_letter_and_collapses_spaces(self):
        assert tidy_question("  preguntar  por la TSH ") == "Preguntar por la TSH"

    def test_empty_text_stays_empty(self):
        assert tidy_question("   ") == ""

    def test_the_tool_saves_the_tidy_version(self, tmp_path):
        calendar = CalendarStore(tmp_path)
        settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
        tools = {t.name: t for t in build_tools(DocumentStore(tmp_path), calendar, ProfileStore(tmp_path), settings, None)}
        tools["save_question_for_doctor"].invoke({"text": "Revisar GLOBULOS BLANCOS Y PLAQUETAS", "appointment_id": ""})
        assert calendar.list_questions()[0]["text"] == "Revisar glóbulos blancos y plaquetas"
