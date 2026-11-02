import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_indexer, get_search, get_settings, get_store
from app.okf.builder import build_bundle, write_bundle
from app.rag.chunking import chunk_concept
from app.rag.embeddings import EmbeddingError, embed
from app.rag.index import cosine, index_document, load_concept_bodies, search_documents
from app.store import DocumentStore

MD = (
    "<!-- página 1 -->\n\n# Laboratorio\n\nPaciente: X\n\n"
    "## Sangre\n\n| Examen | Resultado |\n|---|---|\n| Glucosa | 94 |\n\n"
    "## Notas\n\nControl en 3 meses.\n"
)


def make_settings(**kw) -> Settings:
    kw.setdefault("openrouter_api_key", "k")
    return Settings(retry_min_wait_s=0, retry_max_wait_s=0, _env_file=None, **kw)


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def embeddings_response(vectors: list[list[float]]) -> dict:
    return {"data": [{"embedding": v, "index": i} for i, v in enumerate(vectors)]}


def add_ready_doc(store: DocumentStore, name="informe.pdf", markdown=MD) -> dict:
    meta = store.create(name, b"%PDF-1.4 x", "pdf")
    bundle = build_bundle(markdown, name, "m", page_count=1, document_id=meta["id"], source_format="pdf")
    store.ensure_historia_slug(meta["id"])
    write_bundle(bundle, store.bundle_dir(meta["id"]))
    return store.update(
        meta["id"],
        status="ready",
        concepts=[
            {"filename": c.filename, "title": c.title, "description": c.description, "pages": c.pages}
            for c in bundle.concepts
        ],
    )


class TestChunking:
    def test_short_body_is_one_chunk(self):
        chunks = chunk_concept("concept-01.md", "Título", "cuerpo corto", [1], max_chars=2000)
        assert len(chunks) == 1 and chunks[0].text == "cuerpo corto"

    def test_empty_body_yields_no_chunks(self):
        assert chunk_concept("concept-01.md", "Título", "   ", [1], max_chars=2000) == []

    def test_long_body_splits_by_paragraph_within_budget(self):
        paragraphs = [f"Párrafo {i} " + "x" * 40 for i in range(10)]
        body = "\n\n".join(paragraphs)
        chunks = chunk_concept("concept-01.md", "Título", body, [1, 2], max_chars=120)
        assert len(chunks) > 1
        assert all(len(c.text) <= 200 for c in chunks)  # margen por el último párrafo agregado
        assert all(c.pages == [1, 2] and c.concept_filename == "concept-01.md" for c in chunks)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_a_single_paragraph_longer_than_the_budget_is_kept_whole(self):
        body = "x" * 5000
        chunks = chunk_concept("concept-01.md", "T", body, [], max_chars=100)
        assert len(chunks) == 1 and chunks[0].text == body


class TestEmbeddingsClient:
    VEC = [0.1, 0.2, 0.3]

    def test_happy_path_sends_batch_and_reorders_by_index(self):
        seen = []

        def handler(request):
            body = json.loads(request.read())
            seen.append(body)
            return httpx.Response(200, json=embeddings_response([[9, 9], [1, 1]]))

        vectors = embed(["a", "b"], make_settings(), client_for(handler))
        assert vectors == [[9, 9], [1, 1]]
        assert seen[0]["model"] == "nvidia/nemotron-3-embed-1b:free"
        assert seen[0]["input"] == ["a", "b"]

    def test_empty_input_short_circuits(self):
        assert embed([], make_settings()) == []

    def test_missing_api_key_raises(self):
        with pytest.raises(EmbeddingError, match="OPENROUTER_API_KEY"):
            embed(["x"], make_settings(openrouter_api_key=""))

    def test_falls_back_on_rate_limit(self):
        seen = []

        def handler(request):
            model = json.loads(request.read())["model"]
            seen.append(model)
            if model == "primario":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=embeddings_response([self.VEC]))

        settings = make_settings(embeddings_model="primario", embeddings_fallback_model="respaldo")
        vectors = embed(["x"], settings, client_for(handler))
        assert vectors == [self.VEC]
        assert seen[0] == "primario" and seen[-1] == "respaldo"

    def test_raises_on_non_transient_error(self):
        handler = lambda request: httpx.Response(401, json={"error": {"message": "bad key"}})
        with pytest.raises(EmbeddingError, match="401"):
            embed(["x"], make_settings(), client_for(handler))

    def test_mismatched_vector_count_raises(self):
        handler = lambda request: httpx.Response(200, json=embeddings_response([self.VEC]))
        with pytest.raises(EmbeddingError, match="2 texto"):
            embed(["a", "b"], make_settings(), client_for(handler))


class TestCosine:
    def test_identical_vectors_are_maximally_similar(self):
        assert cosine([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)

    def test_orthogonal_vectors_are_zero(self):
        assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_zero_vector_does_not_divide_by_zero(self):
        assert cosine([0, 0], [1, 1]) == 0.0


class TestIndexDocument:
    def test_load_concept_bodies_reads_the_written_bundle_files(self, tmp_path):
        store = DocumentStore(tmp_path)
        doc = add_ready_doc(store)
        bodies = load_concept_bodies(store, doc["id"])
        assert [title for _, title, _, _ in bodies] == ["Laboratorio", "Sangre", "Notas"]
        assert "Glucosa" in bodies[1][3]

    def test_index_document_embeds_one_chunk_per_concept_and_saves_them(self, tmp_path):
        store = DocumentStore(tmp_path)
        doc = add_ready_doc(store)
        calls = []

        def handler(request):
            body = json.loads(request.read())
            calls.append(len(body["input"]))
            return httpx.Response(200, json=embeddings_response([[float(i)] * 3 for i in range(len(body["input"]))]))

        records = index_document(store, doc["id"], make_settings(), client_for(handler))
        assert calls == [3]
        assert len(records) == 3
        assert store.load_embeddings(doc["id"]) == records
        assert {r["concept_title"] for r in records} == {"Laboratorio", "Sangre", "Notas"}

    def test_document_with_no_concepts_indexes_to_an_empty_list(self, tmp_path):
        store = DocumentStore(tmp_path)
        meta = store.create("a.pdf", b"%PDF-1.4 x", "pdf")
        assert index_document(store, meta["id"], make_settings()) == []
        assert store.load_embeddings(meta["id"]) == []


class TestSearchDocuments:
    def index_with_vector(self, store, doc_id, vector, handler_calls=None):
        def handler(request):
            body = json.loads(request.read())
            if handler_calls is not None:
                handler_calls.append(body)
            return httpx.Response(200, json=embeddings_response([vector] * len(body["input"])))

        index_document(store, doc_id, make_settings(), client_for(handler))

    def test_ranks_by_similarity_across_documents(self, tmp_path):
        store = DocumentStore(tmp_path)
        close = add_ready_doc(store, "a.pdf")
        far = add_ready_doc(store, "b.pdf")
        self.index_with_vector(store, close["id"], [1.0, 0.0])
        self.index_with_vector(store, far["id"], [0.0, 1.0])

        def query_handler(request):
            return httpx.Response(200, json=embeddings_response([[1.0, 0.0]]))

        results = search_documents("glucosa", store, make_settings(), client=client_for(query_handler))
        assert results[0]["document_id"] == close["id"]
        assert results[0]["score"] > results[-1]["score"]
        assert results[0]["document_filename"] == "a.pdf"

    def test_filters_by_document_ids(self, tmp_path):
        store = DocumentStore(tmp_path)
        keep = add_ready_doc(store, "a.pdf")
        other = add_ready_doc(store, "b.pdf")
        self.index_with_vector(store, keep["id"], [1.0, 0.0])
        self.index_with_vector(store, other["id"], [1.0, 0.0])

        handler = lambda request: httpx.Response(200, json=embeddings_response([[1.0, 0.0]]))
        results = search_documents(
            "x", store, make_settings(), document_ids=[keep["id"]], client=client_for(handler)
        )
        assert {r["document_id"] for r in results} == {keep["id"]}

    def test_respects_top_k(self, tmp_path):
        store = DocumentStore(tmp_path)
        doc = add_ready_doc(store)
        self.index_with_vector(store, doc["id"], [1.0, 0.0])

        handler = lambda request: httpx.Response(200, json=embeddings_response([[1.0, 0.0]]))
        results = search_documents("x", store, make_settings(), top_k=1, client=client_for(handler))
        assert len(results) == 1

    def test_no_ready_documents_returns_empty(self, tmp_path):
        store = DocumentStore(tmp_path)
        handler = lambda request: httpx.Response(200, json=embeddings_response([[1.0, 0.0]]))
        assert search_documents("x", store, make_settings(), client=client_for(handler)) == []


@pytest.fixture
def api_client(tmp_path):
    store = DocumentStore(tmp_path)
    settings = make_settings(data_dir=tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()


class TestReindexEndpoint:
    def test_reindexes_a_ready_document(self, api_client):
        client, store = api_client
        doc = add_ready_doc(store)

        app.dependency_overrides[get_indexer] = lambda: (lambda st, doc_id, settings: [{"fake": True}])
        response = client.post(f"/documents/{doc['id']}/reindex")
        assert response.status_code == 200
        assert response.json() == {"document_id": doc["id"], "chunks_indexed": 1}

    def test_requires_the_document_to_be_ready(self, api_client):
        client, store = api_client
        meta = store.create("a.pdf", b"%PDF-1.4 x", "pdf")
        assert client.post(f"/documents/{meta['id']}/reindex").status_code == 409
        assert client.post(f"/documents/{'0' * 32}/reindex").status_code == 404

    def test_embedding_failure_is_reported_not_swallowed(self, api_client):
        client, store = api_client
        doc = add_ready_doc(store)

        def broken(st, doc_id, settings):
            raise EmbeddingError("El servicio de embeddings está saturado (429).", transient=True)

        app.dependency_overrides[get_indexer] = lambda: broken
        response = client.post(f"/documents/{doc['id']}/reindex")
        detail = response.json()["detail"]
        # Genérico a propósito: el paciente no debe ver detalles del proveedor.
        assert response.status_code == 503
        assert "saturado" not in detail and "429" not in detail


class TestSearchEndpoint:
    def test_returns_ranked_results(self, api_client):
        client, store = api_client
        doc = add_ready_doc(store)

        def handler(request):
            body = json.loads(request.read())
            return httpx.Response(200, json=embeddings_response([[1.0, 0.0]] * len(body["input"])))

        index_document(store, doc["id"], make_settings(), client_for(handler))

        app.dependency_overrides[get_search] = lambda: (
            lambda query, st, settings, document_ids, top_k: search_documents(
                query, st, settings, document_ids, top_k, client=client_for(handler)
            )
        )
        response = client.post("/search", json={"query": "glucosa"})
        assert response.status_code == 200
        assert response.json()[0]["document_id"] == doc["id"]

    def test_rejects_empty_query(self, api_client):
        client, _ = api_client
        assert client.post("/search", json={"query": "   "}).status_code == 400
