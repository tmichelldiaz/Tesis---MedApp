import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extraction.documents import UnsupportedDocument, load_pages_from_images
from app.extraction.to_markdown import convert_images
from app.extraction.vision_client import Transcription
from app.main import app, get_settings, get_store, get_transcriber, get_values_extractor, get_indexer, get_classifier
from app.store import DocumentStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def make_settings(**kw) -> Settings:
    return Settings(openrouter_api_key="k", _env_file=None, **kw)


def pdf_bytes() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "hola")
    return doc.tobytes()


class TestLoadPagesFromImages:
    def test_builds_one_page_per_image_in_order(self):
        pages = load_pages_from_images([(PNG, "image/png"), (JPEG, "image/jpeg")], make_settings())
        assert [p.index for p in pages] == [1, 2]
        assert [p.mime for p in pages] == ["image/png", "image/jpeg"]

    def test_rejects_empty_list(self):
        with pytest.raises(UnsupportedDocument, match="ninguna foto"):
            load_pages_from_images([], make_settings())

    def test_rejects_a_pdf_mixed_in(self):
        with pytest.raises(UnsupportedDocument, match="combinar"):
            load_pages_from_images([(PNG, "image/png"), (pdf_bytes(), "pdf")], make_settings())

    def test_enforces_page_count_limit(self):
        items = [(PNG, "image/png")] * 3
        with pytest.raises(UnsupportedDocument, match="máximo"):
            load_pages_from_images(items, make_settings(max_pages=2))

    def test_enforces_total_size_limit(self):
        items = [(PNG + b"0" * 2_000_000, "image/png")] * 2
        with pytest.raises(UnsupportedDocument, match="MB"):
            load_pages_from_images(items, make_settings(max_file_mb=1))

    def test_rejects_empty_image(self):
        with pytest.raises(UnsupportedDocument, match="vacía"):
            load_pages_from_images([(PNG, "image/png"), (b"", "image/png")], make_settings())


class TestConvertImages:
    def test_one_request_per_photo_in_order(self):
        calls = []

        def fake(batch, settings):
            calls.append(batch[0].index)
            return f"## Foto {batch[0].index}"

        result = convert_images(
            [(PNG, "image/png"), (JPEG, "image/jpeg")], make_settings(),
            source_name="fotos", transcriber=fake,
        )
        assert calls == [1, 2]
        assert result.page_count == 2
        assert result.markdown.index("Foto 1") < result.markdown.index("Foto 2")


@pytest.fixture
def client(tmp_path):
    settings = make_settings(data_dir=tmp_path)
    store = DocumentStore(tmp_path)

    def fake_transcriber(pages, settings):
        text = Transcription(f"## Página {pages[0].index}\n\ncontenido {pages[0].index}")
        text.model = "m"
        return text

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_transcriber] = lambda: fake_transcriber
    app.dependency_overrides[get_values_extractor] = lambda: (lambda markdown, settings: [])
    app.dependency_overrides[get_indexer] = lambda: (lambda store, doc_id, settings: [])
    app.dependency_overrides[get_classifier] = lambda: (lambda markdown, settings: "Otro")
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestUploadEndpoint:
    def test_multiple_photos_become_one_document_with_several_pages(self, client):
        response = client.post(
            "/documents",
            files=[
                ("files", ("p1.jpg", JPEG, "image/jpeg")),
                ("files", ("p2.png", PNG, "image/png")),
                ("files", ("p3.jpg", JPEG, "image/jpeg")),
            ],
        )
        assert response.status_code == 202
        body = response.json()
        assert body["kind"] == "multi-image" and body["filename"] == "p1.jpg"

        detail = client.get(f"/documents/{body['id']}").json()
        assert detail["status"] == "ready"
        assert detail["page_count"] == 3
        assert [c["title"] for c in detail["concepts"]] == ["Página 1", "Página 2", "Página 3"]

    def test_single_file_upload_still_works_with_the_files_field(self, client):
        response = client.post("/documents", files=[("files", ("a.pdf", pdf_bytes(), "application/pdf"))])
        assert response.status_code == 202
        assert response.json()["kind"] == "pdf"

    def test_mixing_a_pdf_with_photos_is_rejected(self, client):
        response = client.post(
            "/documents",
            files=[
                ("files", ("p1.jpg", JPEG, "image/jpeg")),
                ("files", ("a.pdf", pdf_bytes(), "application/pdf")),
            ],
        )
        assert response.status_code == 400
        assert "solo fotos" in response.json()["detail"]

    def test_too_many_photos_at_once_is_rejected(self, client):
        app.dependency_overrides[get_settings] = lambda: make_settings(max_pages=2)
        files = [("files", (f"p{i}.jpg", JPEG, "image/jpeg")) for i in range(3)]
        response = client.post("/documents", files=files)
        assert response.status_code == 413

    def test_one_bad_photo_rejects_the_whole_batch(self, client):
        response = client.post(
            "/documents",
            files=[
                ("files", ("p1.jpg", JPEG, "image/jpeg")),
                ("files", ("bad.jpg", b"no es una imagen", "image/jpeg")),
            ],
        )
        assert response.status_code == 415
        assert client.get("/documents").json() == []
