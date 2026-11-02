import logging
import time
from dataclasses import replace
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.config import Settings
from app.extraction.category import DEFAULT_CATEGORY, classify_category
from app.extraction.exam_date import find_exam_date
from app.extraction.exam_names import harmonize_exam_names
from app.extraction.integrity import is_grounded
from app.extraction.documents import UnsupportedDocument
from app.extraction.lab_values import LabValue, extract_values
from app.extraction.to_markdown import Transcriber, convert, convert_images
from app.extraction.vision_client import PATIENT_FACING_ERROR, VisionError, transcribe
from app.okf.builder import build_bundle, write_bundle
from app.okf.validator import INVALID
from app.privacy.masking import MaskingError
from app.rag.embeddings import EmbeddingError
from app.rag.index import index_document
from app.store import DocumentStore

log = logging.getLogger("medapp.service")

ValuesExtractor = Callable[[str, Settings], list[LabValue]]
Indexer = Callable[[DocumentStore, str, Settings], list[dict]]
Classifier = Callable[[str, Settings], str]


def process_document(
    store: DocumentStore,
    doc_id: str,
    settings: Settings,
    transcriber: Transcriber = transcribe,
    values_extractor: ValuesExtractor = extract_values,
    indexer: Indexer = index_document,
    classifier: Classifier = classify_category,
    harmonizer: Callable[..., dict] | None = None,
) -> None:
    meta = store.get(doc_id)
    if meta is None:
        return
    started = time.monotonic()
    try:
        if meta.get("source_pages"):
            extraction = convert_images(
                store.read_source_pages(doc_id), settings,
                source_name=meta["filename"], transcriber=transcriber,
            )
        else:
            extraction = convert(
                store.read_original(doc_id), settings,
                source_name=meta["filename"], transcriber=transcriber,
            )
        store.save_transcription(doc_id, extraction.markdown)
        log.info(
            "doc=%s etapa=transcripcion %.1fs paginas=%s modelo=%s",
            doc_id, time.monotonic() - started, extraction.page_count, extraction.model,
        )

        bundle = build_bundle(
            extraction.markdown,
            source_name=meta["filename"],
            model=extraction.model,
            page_count=extraction.page_count,
            seconds=extraction.seconds,
            document_id=doc_id,
            notes=extraction.notes,
            source_format=meta["kind"],
            created_at=meta["created_at"],
        )
        store.ensure_historia_slug(doc_id)
        write_bundle(bundle, store.bundle_dir(doc_id))

        def extract_values_safely() -> list[LabValue]:
            try:
                return values_extractor(extraction.markdown, settings)
            except VisionError:
                log.warning("No se pudieron extraer valores estructurados de %s", doc_id, exc_info=True)
                return []

        def classify_safely() -> str:
            try:
                return classifier(extraction.markdown, settings)
            except VisionError:
                log.warning("No se pudo clasificar la categoría de %s", doc_id, exc_info=True)
                return DEFAULT_CATEGORY

        # Valores y categoría solo dependen de la transcripción, no entre sí: a la
        # vez, el paciente espera lo que tarde el más lento y no la suma de ambos.
        step = time.monotonic()
        if settings.parallel_workers > 1:
            with ThreadPoolExecutor(max_workers=2) as pool:
                values_future = pool.submit(extract_values_safely)
                category_future = pool.submit(classify_safely)
                lab_values, category = values_future.result(), category_future.result()
        else:
            lab_values, category = extract_values_safely(), classify_safely()
        log.info("doc=%s etapa=valores+categoria %.1fs", doc_id, time.monotonic() - step)

        # Fecha del examen: la del texto original del PDF o, en fotos y escaneos, la que quedó en la
        # transcripción. Se aplica a los valores que no traen la suya, para ordenar por fecha real.
        exam_date = extraction.exam_date or find_exam_date(extraction.markdown)
        lab_values = [v if v.date else replace(v, date=exam_date) for v in lab_values]
        # Un valor cuyos números no están en el PDF es una invención del modelo: no se muestra.
        if extraction.source_text:
            grounded = [v for v in lab_values if is_grounded(v.value_raw, extraction.source_text)]
            if len(grounded) != len(lab_values):
                log.warning(
                    "doc=%s se descartaron %d valores que no aparecen en el PDF: %s",
                    doc_id, len(lab_values) - len(grounded),
                    [v.value_raw for v in lab_values if v not in grounded][:8],
                )
            lab_values = grounded

        check = bundle.validation
        failed = check.state == INVALID
        store.update(
            doc_id,
            status="failed" if failed else "ready",
            error="El bundle no pasó la validación: " + " ".join(check.errors) if failed else None,
            exam_date=exam_date,
            page_count=extraction.page_count,
            model=extraction.model,
            seconds=extraction.seconds,
            notes=extraction.notes,
            category=category,
            validation={"state": check.state, "errors": check.errors, "warnings": check.warnings},
            concepts=[
                {"filename": c.filename, "title": c.title, "description": c.description, "pages": c.pages}
                for c in bundle.concepts
            ],
            lab_values=[v.to_dict() for v in lab_values],
        )

        log.info("doc=%s listo para el paciente en %.1fs", doc_id, time.monotonic() - started)

        if not failed:
            _unify_exam_names(store, settings, harmonizer)
            try:
                indexer(store, doc_id, settings)
            except EmbeddingError:
                log.warning("No se pudo indexar %s para RAG", doc_id, exc_info=True)
            log.info("doc=%s indexado (RAG) a los %.1fs", doc_id, time.monotonic() - started)
    except VisionError as exc:
        log.warning("Fallo del modelo procesando %s: %s", doc_id, exc)
        store.update(doc_id, status="failed", error=PATIENT_FACING_ERROR)
    except MaskingError as exc:
        log.warning("Fallo el enmascaramiento (DLP) de %s: %s", doc_id, exc)
        store.update(doc_id, status="failed", error=PATIENT_FACING_ERROR)
    except (UnsupportedDocument, ValueError) as exc:
        store.update(doc_id, status="failed", error=str(exc))
    except Exception:
        log.exception("Error inesperado procesando %s", doc_id)
        store.update(doc_id, status="failed", error="Error inesperado procesando el documento.")
    finally:
        store.rewrite_library()


# Lo que se conserva del documento si la relectura no sale bien.
_KEEP_ON_FAILURE = (
    "status", "error", "exam_date", "page_count", "model", "seconds", "notes", "category",
    "validation", "concepts", "lab_values",
)


def reprocess_document(
    store: DocumentStore,
    doc_id: str,
    settings: Settings,
    transcriber: Transcriber = transcribe,
    values_extractor: ValuesExtractor = extract_values,
    indexer: Indexer = index_document,
    classifier: Classifier = classify_category,
) -> None:
    """Vuelve a leer un documento ya procesado con los modelos actuales, desde el original guardado.

    Si la relectura falla (caída del modelo, error), el documento queda EXACTAMENTE como estaba: nunca se
    cambia una lectura buena por una vacía. La categoría que ya tenía se respeta (puede haberla elegido
    el paciente). Se guarda cuántos valores había antes para poder compararlo."""
    before = store.get(doc_id)
    if before is None:
        return
    snapshot = {k: before.get(k) for k in _KEEP_ON_FAILURE if k in before}
    previous_count = len(before.get("lab_values") or [])
    snapshot["status"], snapshot["error"] = "ready", None  # el servidor ya lo marcó "procesando"
    process_document(store, doc_id, settings, transcriber, values_extractor, indexer, classifier)
    after = store.get(doc_id)
    if after is None:
        return
    if after.get("status") != "ready":
        log.warning("doc=%s la relectura falló; se conserva la lectura anterior", doc_id)
        store.update(doc_id, **snapshot, values_before=None)
    else:
        keep_category = {"category": snapshot["category"]} if snapshot.get("category") else {}
        store.update(doc_id, values_before=previous_count, **keep_category)
    store.rewrite_library()


def _unify_exam_names(store: DocumentStore, settings: Settings, harmonizer: Callable[..., dict] | None) -> None:
    """Que el mismo examen se llame igual en todas las historias del paciente (si hay más de una con valores)."""
    with_values = [d for d in store.list_all() if d.get("status") == "ready" and d.get("lab_values")]
    if len(with_values) < 2:
        return
    try:
        changed = (harmonizer or harmonize_exam_names)(store, settings)
        if changed:
            log.info("nombres de examen unificados: %d", len(changed))
    except Exception:  # nunca debe tumbar el procesamiento de una historia
        log.warning("No se pudieron unificar los nombres de examen", exc_info=True)


def extract_document_values(
    store: DocumentStore,
    doc_id: str,
    settings: Settings,
    values_extractor: ValuesExtractor = extract_values,
) -> dict:
    meta = store.get(doc_id)
    transcription = store.transcription_path(doc_id)
    if meta is None or not transcription.exists():
        raise FileNotFoundError(doc_id)

    text = transcription.read_text(encoding="utf-8")
    values = values_extractor(text, settings)
    exam_date = meta.get("exam_date") or find_exam_date(text)
    values = [v if v.date else replace(v, date=exam_date) for v in values]
    return store.update(doc_id, lab_values=[v.to_dict() for v in values], exam_date=exam_date)


def classify_document_category(
    store: DocumentStore,
    doc_id: str,
    settings: Settings,
    classifier: Classifier = classify_category,
) -> dict:
    meta = store.get(doc_id)
    transcription = store.transcription_path(doc_id)
    if meta is None or not transcription.exists():
        raise FileNotFoundError(doc_id)

    category = classifier(transcription.read_text(encoding="utf-8"), settings)
    return store.update(doc_id, category=category)


def rebuild_document(store: DocumentStore, doc_id: str) -> None:
    meta = store.get(doc_id)
    transcription = store.transcription_path(doc_id)
    if meta is None or not transcription.exists():
        raise FileNotFoundError(doc_id)

    bundle = build_bundle(
        transcription.read_text(encoding="utf-8"),
        source_name=meta["filename"],
        model=meta.get("model") or "desconocido",
        page_count=meta.get("page_count"),
        seconds=meta.get("seconds"),
        document_id=doc_id,
        source_format=meta["kind"],
        notes=meta.get("notes") or [],
        created_at=meta["created_at"],
    )
    store.ensure_historia_slug(doc_id)
    target = store.bundle_dir(doc_id)
    for old in store.bundle_file_names(doc_id):
        (target / old).unlink()
    write_bundle(bundle, target)

    check = bundle.validation
    failed = check.state == INVALID
    store.update(
        doc_id,
        status="failed" if failed else "ready",
        error="El bundle no pasó la validación: " + " ".join(check.errors) if failed else None,
        validation={"state": check.state, "errors": check.errors, "warnings": check.warnings},
        concepts=[
            {"filename": c.filename, "title": c.title, "description": c.description, "pages": c.pages}
            for c in bundle.concepts
        ],
    )
    store.rewrite_library()
