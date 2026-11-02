import math

import httpx

from app.config import Settings
from app.okf import frontmatter
from app.rag.chunking import chunk_concept
from app.rag.embeddings import embed
from app.rag.redact import redact_pii
from app.store import DocumentStore


def load_concept_bodies(
    store: DocumentStore, doc_id: str
) -> list[tuple[str, str, list[int], str]]:
    meta = store.get(doc_id)
    if meta is None:
        raise KeyError(doc_id)
    bundle_dir = store.bundle_dir(doc_id)
    if bundle_dir is None:
        return []
    bodies = []
    for concept in meta["concepts"]:
        path = bundle_dir / concept["filename"]
        if not path.exists():
            continue
        _, body = frontmatter.split(path.read_text(encoding="utf-8"))
        bodies.append((concept["filename"], concept["title"], concept["pages"], body))
    return bodies


def index_document(
    store: DocumentStore,
    doc_id: str,
    settings: Settings,
    client: httpx.Client | None = None,
) -> list[dict]:
    chunks = []
    for filename, title, pages, body in load_concept_bodies(store, doc_id):
        chunks += chunk_concept(filename, title, body, pages, settings.embedding_chunk_chars)

    if not chunks:
        store.save_embeddings(doc_id, [])
        return []

    # Se enmascaran nombre/cédula/teléfono/dirección/correo ANTES de que el
    # texto salga hacia el modelo de embeddings (OpenRouter): lo que queda
    # indexado —y por tanto lo que `search_narrative_history` le pasa después
    # al modelo de chat— ya no trae esos datos de identificación.
    texts = [redact_pii(chunk.text) for chunk in chunks]
    vectors = embed(texts, settings, client)
    records = [
        {
            "document_id": doc_id,
            "concept_filename": chunk.concept_filename,
            "concept_title": chunk.concept_title,
            "chunk_index": chunk.chunk_index,
            "pages": chunk.pages,
            "text": text,
            "vector": vector,
        }
        for chunk, text, vector in zip(chunks, texts, vectors)
    ]
    store.save_embeddings(doc_id, records)
    return records


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_documents(
    query: str,
    store: DocumentStore,
    settings: Settings,
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    client: httpx.Client | None = None,
) -> list[dict]:
    query_vector = embed([query], settings, client)[0]

    records: list[dict] = []
    filenames: dict[str, str] = {}
    for doc in store.list_all():
        if doc["status"] != "ready":
            continue
        if document_ids is not None and doc["id"] not in document_ids:
            continue
        filenames[doc["id"]] = doc["filename"]
        records += store.load_embeddings(doc["id"])

    scored = sorted(
        ((cosine(query_vector, r["vector"]), r) for r in records),
        key=lambda pair: pair[0],
        reverse=True,
    )
    limit = top_k or settings.rag_top_k
    return [
        {
            "score": round(score, 4),
            "document_id": r["document_id"],
            "document_filename": filenames.get(r["document_id"], ""),
            "concept_filename": r["concept_filename"],
            "concept_title": r["concept_title"],
            "pages": r["pages"],
            "text": r["text"],
        }
        for score, r in scored[:limit]
    ]
