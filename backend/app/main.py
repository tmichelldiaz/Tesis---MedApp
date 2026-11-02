import base64
import io
import json
import logging
import re
import shutil
import time
import uuid
import zipfile
from datetime import datetime
from functools import lru_cache

import openai
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from app import auth as auth_module
from app import chat as chat_module
from app import exam_summary
from app.agent import clock
from app.agent import service as agent_service
from app.agent.proactive import build_user_notices
from app.calendar_store import CalendarStore
from app.db import get_session, make_engine, make_session_factory, run_migrations
from app.profile_store import ProfileStore
from app.config import Settings
from app.extraction.category import CATEGORIES, classify_category
from app.user_store import EmailAlreadyExists, UserStore
from app.extraction.documents import UnsupportedDocument, detect_kind, render_first_page
from app.extraction.lab_values import extract_values
from app.extraction.to_markdown import Transcriber
from app.agent import memory as agent_memory
from app.extraction.vision_client import PATIENT_FACING_ERROR, VisionError, transcribe
from app.rag.embeddings import EmbeddingError
from app.rag.index import index_document, search_documents
from app.service import (
    Classifier,
    Indexer,
    ValuesExtractor,
    classify_document_category,
    extract_document_values,
    process_document,
    reprocess_document,
    rebuild_document,
)
from app.store import DocumentStore
from app.values_history import oldest_first, with_document

log = logging.getLogger("medapp.api")

# Cloud Run (uvicorn) solo muestra WARNING o más de los loggers de la app, y los
# tiempos por etapa del procesamiento de documentos se registran como INFO.
_medapp_logger = logging.getLogger("medapp")
_medapp_logger.setLevel(logging.INFO)
if not _medapp_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    _medapp_logger.addHandler(_handler)

async def apply_timezone(request: Request) -> None:
    """La app manda la zona horaria del celular en cada petición; todo lo que dependa de "hoy" la usa."""
    clock.set_request_timezone(request.headers.get("x-timezone"))


app = FastAPI(title="MedApp API", version="0.1.0", dependencies=[Depends(apply_timezone)])


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def _engine_for(url: str):
    return make_engine(get_settings().model_copy(update={"database_url": url}))


@lru_cache
def _session_factory_for(url: str):
    return make_session_factory(_engine_for(url))


def get_db_session(settings: Settings = Depends(get_settings)):
    yield from get_session(_session_factory_for(settings.database_url))


def get_user_store(session=Depends(get_db_session)) -> UserStore:
    return UserStore(session)


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    users: UserStore = Depends(get_user_store),
) -> dict:
    """Cada request a un endpoint protegido trae 'Authorization: Bearer <jwt>'.
    Mismo contrato que internal/http/auth_middleware.go en plataform-OKF-Cloud
    (github.com/fredyxander/plataform-OKF-Cloud), traducido a una dependencia
    de FastAPI en vez de un middleware."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "No autenticado.")
    try:
        user_id = auth_module.validate_token(token, settings)
    except auth_module.InvalidToken as exc:
        raise HTTPException(401, "Token inválido o expirado.") from exc
    user = users.get_by_id(user_id)
    if user is None:
        raise HTTPException(401, "Usuario no encontrado.")
    return user


# Cada paciente tiene su propio subárbol bajo data_dir, nombrado por su user
# id — así DocumentStore/CalendarStore/ProfileStore (que ya sabían manejar
# "una carpeta = un paciente") quedan aislados por usuario sin reescribirlos:
# solo cambia CUÁL carpeta reciben, y esa carpeta ahora depende de quién hizo
# el request (get_current_user), no es fija por instalación.

@lru_cache
def _store_for(path: str) -> DocumentStore:
    return DocumentStore(path)


def get_store(
    settings: Settings = Depends(get_settings), user: dict = Depends(get_current_user)
) -> DocumentStore:
    return _store_for(str(settings.data_dir / str(user["id"])))


@lru_cache
def _calendar_for(path: str) -> CalendarStore:
    return CalendarStore(path)


def get_calendar(
    settings: Settings = Depends(get_settings), user: dict = Depends(get_current_user)
) -> CalendarStore:
    return _calendar_for(str(settings.data_dir / str(user["id"])))


@lru_cache
def _profile_for(path: str) -> ProfileStore:
    return ProfileStore(path)


def get_profile(
    settings: Settings = Depends(get_settings), user: dict = Depends(get_current_user)
) -> ProfileStore:
    return _profile_for(str(settings.data_dir / str(user["id"])))


@lru_cache
def _summary_cache_for(path: str) -> exam_summary.SummaryCache:
    return exam_summary.SummaryCache(path)


def get_summary_cache(
    settings: Settings = Depends(get_settings), user: dict = Depends(get_current_user)
) -> exam_summary.SummaryCache:
    return _summary_cache_for(str(settings.data_dir / str(user["id"])))


def get_transcriber() -> Transcriber:
    return transcribe


def get_values_extractor() -> ValuesExtractor:
    return extract_values


def get_classifier() -> Classifier:
    return classify_category


def get_indexer() -> Indexer:
    return index_document


def get_search():
    return search_documents


def get_chat():
    return chat_module.answer


def get_agent_start():
    return agent_service.start


def get_agent_resume():
    return agent_service.continue_after_confirmation


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    document_ids: list[str] | None = None
    prior_context: str | None = None


def _configure_cors() -> None:
    origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"]
    )


_configure_cors()


@app.on_event("startup")
def _run_startup_migrations() -> None:
    settings = get_settings()
    if settings.database_url:
        run_migrations(_engine_for(settings.database_url))
    agent_memory.warm_up(settings.database_url)


def _public_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password_hash"}


_PASSWORD_RULES = [
    (re.compile(r".{8,}"), "al menos 8 caracteres"),
    (re.compile(r"[A-ZÁÉÍÓÚÑ]"), "una letra mayúscula"),
    (re.compile(r"[a-záéíóúñ]"), "una letra minúscula"),
    (re.compile(r"\d"), "un número"),
    (re.compile(r"[^\w\s]"), "un símbolo (ej. !@#$%)"),
]


def _validate_password_strength(password: str) -> None:
    missing = [desc for pattern, desc in _PASSWORD_RULES if not pattern.search(password)]
    if missing:
        raise HTTPException(400, f"La contraseña debe tener {', '.join(missing)}.")


class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str = ""
    apellido: str = ""
    accept_policy: bool = False
    # Datos básicos de salud: se piden una sola vez, en el registro, para que
    # el paciente no tenga que volver a escribirlos después en el Dashboard.
    birth_date: str | None = None
    sex: str | None = None
    weight_kg: float | None = None
    blood_type: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/register", status_code=201)
def register(
    body: RegisterRequest,
    settings: Settings = Depends(get_settings),
    users: UserStore = Depends(get_user_store),
):
    email = body.email.strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Correo inválido.")
    _validate_password_strength(body.password)
    if not body.accept_policy:
        raise HTTPException(
            400, "Debes aceptar la política de protección de datos para registrarte."
        )
    full_name = f"{body.nombre.strip()} {body.apellido.strip()}".strip()
    profile_fields = _validate_profile_fields({
        "name": full_name or None,
        "birth_date": body.birth_date, "sex": body.sex,
        "weight_kg": body.weight_kg, "blood_type": body.blood_type,
    })

    password_hash = auth_module.hash_password(body.password)
    try:
        user = users.create(
            email, password_hash, body.nombre.strip(), body.apellido.strip(),
            policy_version=settings.policy_version,
        )
    except EmailAlreadyExists as exc:
        raise HTTPException(409, "Ya existe una cuenta con ese correo.") from exc

    # No se usa get_profile (Depends(get_current_user)) porque todavía no
    # existe un token para este usuario recién creado — se instancia el
    # store directamente, con el mismo id que ya quedó en Postgres.
    if any(v is not None for v in profile_fields.values()):
        _profile_for(str(settings.data_dir / str(user["id"]))).update(**profile_fields)

    token = auth_module.generate_token(str(user["id"]), settings)
    return {"token": token, "user": _public_user(user)}


@app.post("/auth/login")
def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    users: UserStore = Depends(get_user_store),
):
    user = users.get_by_email(body.email)
    if user is None or not auth_module.check_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Correo o contraseña incorrectos.")
    token = auth_module.generate_token(str(user["id"]), settings)
    return {"token": token, "user": _public_user(user)}


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return _public_user(user)


@app.delete("/auth/me", status_code=204)
def delete_account(
    user: dict = Depends(get_current_user),
    users: UserStore = Depends(get_user_store),
    settings: Settings = Depends(get_settings),
):
    # Derecho de supresión (Sección 11 de la política): borra la cuenta y
    # todos sus datos — documentos, calendario, perfil y todo lo que el agente
    # guardó (recuerdos de largo plazo y contenido de sus conversaciones).
    # Es irreversible. La memoria del agente se borra primero: si falla, la
    # cuenta sigue existiendo y el paciente puede reintentar, en vez de quedar
    # datos de salud huérfanos en la base sin nadie que pueda pedir borrarlos.
    try:
        agent_memory.delete_user_memory(settings.database_url, str(user["id"]))
    except Exception as exc:
        log.exception("No se pudo borrar la memoria del agente de %s", user["id"])
        raise HTTPException(500, "No se pudo eliminar la cuenta. Intenta de nuevo en unos minutos.") from exc
    users.delete(user["id"])
    shutil.rmtree(settings.data_dir / str(user["id"]), ignore_errors=True)


@app.get("/memory")
def list_agent_memory(user: dict = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    """Lo que el asistente recuerda del paciente de conversaciones anteriores."""
    store = agent_memory.get_store(settings.database_url)
    return agent_memory.list_memories(store, str(user["id"]))


@app.delete("/memory/{memory_id}", status_code=204)
def forget_agent_memory(
    memory_id: str,
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    store = agent_memory.get_store(settings.database_url)
    if not agent_memory.forget(store, str(user["id"]), memory_id):
        raise HTTPException(404, "Recuerdo no encontrado.")


def _public(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if k not in {"original"}}


def _require(store: DocumentStore, doc_id: str) -> dict:
    meta = store.get(doc_id)
    if meta is None:
        raise HTTPException(404, "Documento no encontrado.")
    return meta


class ClientErrorReport(BaseModel):
    message: str = ""
    stack: str = ""
    context: str = ""
    device: dict = {}


_error_reports: dict[str, list[float]] = {}
MAX_REPORTS_PER_MINUTE = 20


@app.post("/client-errors", status_code=204)
def client_errors(report: ClientErrorReport, request: Request):
    """Errores que ocurren en el celular de alguien. Se dejan en los registros del servidor (con el modelo de celular
    y la versión de Android) para poder ver y arreglar lo que "a mí no me sale". No pide sesión (también sirve para
    fallos al iniciar) y está limitado por IP; solo guarda texto corto, nunca datos médicos."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = (forwarded.split(",")[0].strip() or (request.client.host if request.client else "?"))
    now = time.monotonic()
    recent = [t for t in _error_reports.get(ip, []) if now - t < 60]
    if len(recent) >= MAX_REPORTS_PER_MINUTE:
        return
    _error_reports[ip] = recent + [now]
    device = {str(k)[:30]: str(v)[:80] for k, v in list(report.device.items())[:10]}
    logging.getLogger("medapp.client").warning(
        "ERROR_EN_CELULAR %s", json.dumps({
            "mensaje": report.message[:500], "contexto": report.context[:500], "celular": device,
            "traza": report.stack[:1500],
        }, ensure_ascii=False),
    )


@app.get("/health")
def health(settings: Settings = Depends(get_settings)):
    return {"ok": True, "model": settings.vision_model, "api_key_configured": bool(settings.openrouter_api_key)}


@app.post("/documents/preview")
async def preview_document(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(get_current_user),
):
    """Vista previa (primera página) de un PDF que el paciente apenas eligió, para que
    confirme que es el correcto antes de subirlo. No se guarda nada."""
    limit = settings.max_file_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"El archivo supera {settings.max_file_mb} MB.")
    try:
        png, pages = render_first_page(data, settings)
    except UnsupportedDocument as exc:
        raise HTTPException(415, str(exc)) from exc
    return {"image_base64": base64.b64encode(png).decode("ascii"), "page_count": pages}


@app.post("/documents", status_code=202)
async def upload_document(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    transcriber: Transcriber = Depends(get_transcriber),
    values_extractor: ValuesExtractor = Depends(get_values_extractor),
    indexer: Indexer = Depends(get_indexer),
    classifier: Classifier = Depends(get_classifier),
):
    limit = settings.max_file_mb * 1024 * 1024
    blobs: list[tuple[str, bytes, str]] = []
    for upload in files:
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"{upload.filename}: el archivo supera {settings.max_file_mb} MB.")
        if not data:
            raise HTTPException(400, f"{upload.filename}: el archivo está vacío.")
        try:
            kind = detect_kind(data)
        except UnsupportedDocument as exc:
            raise HTTPException(415, f"{upload.filename}: {exc}") from exc
        blobs.append((upload.filename or "documento", data, kind))

    if len(blobs) == 1:
        filename, data, kind = blobs[0]
        meta = store.create(filename, data, kind)
    else:
        if any(kind == "pdf" for _, _, kind in blobs):
            raise HTTPException(
                400, "Para combinar varias páginas selecciona solo fotos; un PDF ya trae todas sus páginas."
            )
        if len(blobs) > settings.max_pages:
            raise HTTPException(413, f"Máximo {settings.max_pages} fotos por historia.")
        meta = store.create_multi(blobs[0][0], [(data, kind) for _, data, kind in blobs])

    background.add_task(
        process_document, store, meta["id"], settings, transcriber, values_extractor, indexer, classifier
    )
    return _public(meta)


@app.get("/documents")
def list_documents(store: DocumentStore = Depends(get_store)):
    return [_public(m) for m in store.list_all()]


@app.get("/documents/{doc_id}")
def get_document(doc_id: str, store: DocumentStore = Depends(get_store)):
    return _public(_require(store, doc_id))


@app.post("/documents/reprocess-all", status_code=202)
def reprocess_all_documents(
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    transcriber: Transcriber = Depends(get_transcriber),
    values_extractor: ValuesExtractor = Depends(get_values_extractor),
    indexer: Indexer = Depends(get_indexer),
    classifier: Classifier = Depends(get_classifier),
):
    """Vuelve a leer, con los modelos actuales, todas las historias ya listas del paciente (una tras otra).
    Si alguna relectura falla, esa historia queda como estaba."""
    ready = [d for d in store.list_all() if d["status"] == "ready"]
    ids = [d["id"] for d in ready]
    for doc_id in ids:
        store.update(doc_id, status="processing", error=None)

    def run_all() -> None:
        for doc_id in ids:
            reprocess_document(store, doc_id, settings, transcriber, values_extractor, indexer, classifier)

    background.add_task(run_all)
    return {"count": len(ids)}


@app.post("/documents/{doc_id}/reprocess", status_code=202)
def reprocess_one_document(
    doc_id: str,
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    transcriber: Transcriber = Depends(get_transcriber),
    values_extractor: ValuesExtractor = Depends(get_values_extractor),
    indexer: Indexer = Depends(get_indexer),
    classifier: Classifier = Depends(get_classifier),
):
    meta = _require(store, doc_id)
    if meta["status"] != "ready":
        raise HTTPException(409, "Solo se pueden volver a leer historias que ya están listas.")
    meta = store.update(doc_id, status="processing", error=None)
    background.add_task(
        reprocess_document, store, doc_id, settings, transcriber, values_extractor, indexer, classifier
    )
    return _public(meta)


@app.post("/documents/{doc_id}/retry", status_code=202)
def retry_document(
    doc_id: str,
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    transcriber: Transcriber = Depends(get_transcriber),
    values_extractor: ValuesExtractor = Depends(get_values_extractor),
    indexer: Indexer = Depends(get_indexer),
    classifier: Classifier = Depends(get_classifier),
):
    meta = _require(store, doc_id)
    if meta["status"] != "failed":
        raise HTTPException(409, "Solo se pueden reintentar documentos fallidos.")
    meta = store.update(doc_id, status="processing", error=None)
    background.add_task(
        process_document, store, doc_id, settings, transcriber, values_extractor, indexer, classifier
    )
    return _public(meta)


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, store: DocumentStore = Depends(get_store)):
    _require(store, doc_id)
    store.delete(doc_id)
    store.rewrite_library()


@app.post("/documents/{doc_id}/rebuild")
def rebuild(doc_id: str, store: DocumentStore = Depends(get_store)):
    _require(store, doc_id)
    try:
        rebuild_document(store, doc_id)
    except FileNotFoundError as exc:
        raise HTTPException(409, "Este documento aún no tiene transcripción.") from exc
    return _public(store.get(doc_id))


@app.post("/documents/{doc_id}/extract-values")
def extract_values_endpoint(
    doc_id: str,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    values_extractor: ValuesExtractor = Depends(get_values_extractor),
):
    _require(store, doc_id)
    try:
        updated = extract_document_values(store, doc_id, settings, values_extractor)
    except FileNotFoundError as exc:
        raise HTTPException(409, "Este documento aún no tiene transcripción.") from exc
    except VisionError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc
    return _public(updated)


@app.get("/categories")
def list_categories():
    return CATEGORIES


@app.post("/documents/{doc_id}/classify-category")
def classify_category_endpoint(
    doc_id: str,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    classifier: Classifier = Depends(get_classifier),
):
    _require(store, doc_id)
    try:
        updated = classify_document_category(store, doc_id, settings, classifier)
    except FileNotFoundError as exc:
        raise HTTPException(409, "Este documento aún no tiene transcripción.") from exc
    except VisionError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc
    return _public(updated)


class CategoryUpdate(BaseModel):
    category: str


@app.put("/documents/{doc_id}/category")
def set_category(
    doc_id: str, body: CategoryUpdate, store: DocumentStore = Depends(get_store)
):
    _require(store, doc_id)
    if body.category not in CATEGORIES:
        raise HTTPException(400, f"Categoría inválida. Usa una de: {', '.join(CATEGORIES)}.")
    return _public(store.update(doc_id, category=body.category))


@app.post("/documents/{doc_id}/reindex")
def reindex_document(
    doc_id: str,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    indexer: Indexer = Depends(get_indexer),
):
    meta = _require(store, doc_id)
    if meta["status"] != "ready":
        raise HTTPException(409, "El documento aún no está listo.")
    try:
        records = indexer(store, doc_id, settings)
    except EmbeddingError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc
    return {"document_id": doc_id, "chunks_indexed": len(records)}


class SearchRequest(BaseModel):
    query: str
    document_ids: list[str] | None = None
    top_k: int | None = None


@app.post("/search")
def search(
    body: SearchRequest,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    searcher=Depends(get_search),
):
    if not body.query.strip():
        raise HTTPException(400, "La búsqueda no puede estar vacía.")
    try:
        return searcher(body.query, store, settings, body.document_ids, body.top_k)
    except EmbeddingError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc


@app.get("/values")
def list_values(exam: str | None = None, store: DocumentStore = Depends(get_store)):
    rows = []
    for doc in store.list_all():
        if doc["status"] != "ready":
            continue
        for value in doc.get("lab_values") or []:
            if exam and exam.lower() not in value["exam"].lower():
                continue
            rows.append(with_document(doc, value))
    return oldest_first(rows)


def _lab_rows(store: DocumentStore) -> list[dict]:
    rows = []
    for doc in store.list_all():
        if doc["status"] == "ready":
            rows.extend(with_document(doc, v) for v in doc.get("lab_values") or [])
    return rows


@app.get("/values/summary")
def exam_value_summary(
    exam: str,
    store: DocumentStore = Depends(get_store),
    cache: exam_summary.SummaryCache = Depends(get_summary_cache),
    settings: Settings = Depends(get_settings),
):
    """Resumen escrito por un modelo de un examen del paciente. `summary` es null
    si la función está apagada (SUMMARY_MODEL vacío) o el examen no existe; la app
    muestra entonces su explicación general."""
    rows = exam_summary.matching_rows(_lab_rows(store), exam)
    try:
        return exam_summary.summarize(exam, rows, settings, cache)
    except VisionError as exc:
        log.warning("No se pudo generar el resumen de un examen: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc


@app.get("/documents/{doc_id}/files/{name}", response_class=PlainTextResponse)
def get_bundle_file(doc_id: str, name: str, store: DocumentStore = Depends(get_store)):
    _require(store, doc_id)
    if name not in store.bundle_file_names(doc_id):
        raise HTTPException(404, "Archivo no encontrado en el bundle.")
    return (store.bundle_dir(doc_id) / name).read_text(encoding="utf-8")


@app.get("/documents/{doc_id}/bundle.zip")
def download_bundle(doc_id: str, store: DocumentStore = Depends(get_store)):
    meta = _require(store, doc_id)
    if meta["status"] != "ready":
        raise HTTPException(409, "El bundle aún no está disponible.")
    slug = meta["historia_slug"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in store.bundle_file_names(doc_id):
            archive.write(store.bundle_dir(doc_id) / name, arcname=f"{slug}/{name}")
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@app.get("/bundle.zip")
def download_library(store: DocumentStore = Depends(get_store)):
    if not any(store.library_dir.glob("historia-*")):
        raise HTTPException(409, "Todavía no hay historias procesadas.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(store.library_dir.rglob("*")):
            if path.is_file():
                archive.write(
                    path, arcname=f"bundle/{path.relative_to(store.library_dir).as_posix()}"
                )
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="bundle.zip"'},
    )


def _require_appointment(store: CalendarStore, appt_id: str) -> dict:
    appt = store.get_appointment(appt_id)
    if appt is None:
        raise HTTPException(404, "Cita no encontrada.")
    return appt


def _require_question(store: CalendarStore, question_id: str) -> dict:
    question = store.get_question(question_id)
    if question is None:
        raise HTTPException(404, "Pregunta no encontrada.")
    return question


def _with_questions(store: CalendarStore, appt: dict) -> dict:
    return {**appt, "questions": store.list_questions(appointment_id=appt["id"])}


def _parse_iso(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, f"Fecha inválida: {value!r}. Usa formato ISO 8601.") from exc


class AppointmentCreate(BaseModel):
    title: str
    scheduled_at: str
    doctor_name: str | None = None
    location: str | None = None
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    title: str | None = None
    scheduled_at: str | None = None
    doctor_name: str | None = None
    location: str | None = None
    notes: str | None = None


class QuestionCreate(BaseModel):
    text: str
    appointment_id: str | None = None


class QuestionUpdate(BaseModel):
    text: str | None = None
    answered: bool | None = None
    appointment_id: str | None = None


@app.get("/appointments")
def list_appointments(calendar: CalendarStore = Depends(get_calendar)):
    return [_with_questions(calendar, a) for a in calendar.list_appointments()]


@app.post("/appointments", status_code=201)
def create_appointment(body: AppointmentCreate, calendar: CalendarStore = Depends(get_calendar)):
    if not body.title.strip():
        raise HTTPException(400, "El título de la cita no puede estar vacío.")
    _parse_iso(body.scheduled_at)
    appt = calendar.create_appointment(
        title=body.title.strip(),
        scheduled_at=body.scheduled_at,
        doctor_name=body.doctor_name,
        location=body.location,
        notes=body.notes,
    )
    return _with_questions(calendar, appt)


@app.get("/appointments/{appt_id}")
def get_appointment(appt_id: str, calendar: CalendarStore = Depends(get_calendar)):
    return _with_questions(calendar, _require_appointment(calendar, appt_id))


@app.put("/appointments/{appt_id}")
def update_appointment(
    appt_id: str, body: AppointmentUpdate, calendar: CalendarStore = Depends(get_calendar)
):
    _require_appointment(calendar, appt_id)
    fields = body.model_dump(exclude_unset=True)
    if "title" in fields and not fields["title"].strip():
        raise HTTPException(400, "El título de la cita no puede estar vacío.")
    if "scheduled_at" in fields:
        _parse_iso(fields["scheduled_at"])
    return _with_questions(calendar, calendar.update_appointment(appt_id, **fields))


@app.delete("/appointments/{appt_id}", status_code=204)
def delete_appointment(appt_id: str, calendar: CalendarStore = Depends(get_calendar)):
    _require_appointment(calendar, appt_id)
    calendar.delete_appointment(appt_id)


# Las preguntas son su propia colección: pueden existir sin una cita todavía
# (ej. el agente anota algo que preguntar antes de que se agende una cita), y
# asignarse o reasignarse a una cita después.
@app.get("/questions")
def list_questions(
    appointment_id: str | None = None,
    unassigned: bool = False,
    calendar: CalendarStore = Depends(get_calendar),
):
    if unassigned:
        return calendar.list_questions(appointment_id=None)
    if appointment_id is not None:
        return calendar.list_questions(appointment_id=appointment_id)
    return calendar.list_questions()


@app.post("/questions", status_code=201)
def create_question(body: QuestionCreate, calendar: CalendarStore = Depends(get_calendar)):
    if not body.text.strip():
        raise HTTPException(400, "La pregunta no puede estar vacía.")
    try:
        return calendar.create_question(body.text.strip(), appointment_id=body.appointment_id)
    except KeyError as exc:
        raise HTTPException(404, "Cita no encontrada.") from exc


@app.get("/questions/{question_id}")
def get_question(question_id: str, calendar: CalendarStore = Depends(get_calendar)):
    return _require_question(calendar, question_id)


@app.put("/questions/{question_id}")
def update_question(
    question_id: str, body: QuestionUpdate, calendar: CalendarStore = Depends(get_calendar)
):
    _require_question(calendar, question_id)
    fields = body.model_dump(exclude_unset=True)
    if "text" in fields and not fields["text"].strip():
        raise HTTPException(400, "La pregunta no puede estar vacía.")
    try:
        return calendar.update_question(question_id, **fields)
    except KeyError as exc:
        raise HTTPException(404, "Cita no encontrada.") from exc


@app.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: str, calendar: CalendarStore = Depends(get_calendar)):
    _require_question(calendar, question_id)
    calendar.delete_question(question_id)


_BLOOD_TYPES = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
_SEX_OPTIONS = {"Femenino", "Masculino", "Prefiero no decir"}


class ProfileUpdate(BaseModel):
    name: str | None = None
    birth_date: str | None = None
    sex: str | None = None
    weight_kg: float | None = None
    blood_type: str | None = None


def _validate_profile_fields(fields: dict) -> dict:
    """Compartido entre /profile y /auth/register: mismas reglas en ambos
    lugares donde se pueden escribir estos campos."""
    if "name" in fields and fields["name"] is not None and not fields["name"].strip():
        raise HTTPException(400, "El nombre no puede estar vacío.")
    if fields.get("name"):
        fields["name"] = fields["name"].strip()
    if "birth_date" in fields and fields["birth_date"] is not None:
        _parse_iso(fields["birth_date"] + "T00:00:00")
    if "sex" in fields and fields["sex"] is not None:
        if fields["sex"] not in _SEX_OPTIONS:
            raise HTTPException(400, f"Sexo inválido. Usa uno de: {', '.join(sorted(_SEX_OPTIONS))}.")
    if "weight_kg" in fields and fields["weight_kg"] is not None and fields["weight_kg"] <= 0:
        raise HTTPException(400, "El peso debe ser un número positivo.")
    if "blood_type" in fields and fields["blood_type"] is not None:
        fields["blood_type"] = fields["blood_type"].strip().upper()
        if fields["blood_type"] not in _BLOOD_TYPES:
            raise HTTPException(400, f"Tipo de sangre inválido. Usa uno de: {', '.join(sorted(_BLOOD_TYPES))}.")
    return fields


@app.get("/profile")
def get_profile_data(profile: ProfileStore = Depends(get_profile)):
    return profile.get()


@app.put("/profile")
def update_profile(body: ProfileUpdate, profile: ProfileStore = Depends(get_profile)):
    fields = _validate_profile_fields(body.model_dump(exclude_unset=True))
    return profile.update(**fields)


@app.get("/notifications")
def get_notifications(
    store: DocumentStore = Depends(get_store),
    calendar: CalendarStore = Depends(get_calendar),
):
    return {"notices": build_user_notices(store, calendar)}


@app.post("/chat")
def chat(
    body: ChatRequest,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    answer=Depends(get_chat),
):
    try:
        result = answer(
            [m.model_dump() for m in body.messages],
            settings,
            store,
            body.document_ids,
            prior_context=body.prior_context,
        )
    except chat_module.ChatInputError as exc:
        raise HTTPException(400, str(exc)) from exc
    except VisionError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc
    return {
        "reply": result.reply,
        "model": result.model,
        "documents": result.documents,
        "route": result.route,
        "degraded": result.degraded,
    }


def _agent_response(reply: agent_service.AgentReply) -> dict:
    if reply.status == "done":
        return {"status": "done", "reply": reply.reply}
    return {
        "status": "needs_confirmation",
        "action": {
            "tool": reply.pending.tool,
            "args": reply.pending.args,
            "description": reply.pending.description,
        },
        "resume_state": reply.pending.resume_state,
    }


class AgentChatRequest(BaseModel):
    question: str
    is_new_conversation: bool = True
    thread_id: str | None = None


class AgentResumeRequest(BaseModel):
    resume_state: dict
    decision: str
    edited_args: dict | None = None


@app.post("/agent/chat")
def agent_chat(
    body: AgentChatRequest,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    calendar: CalendarStore = Depends(get_calendar),
    profile: ProfileStore = Depends(get_profile),
    start=Depends(get_agent_start),
    user: dict = Depends(get_current_user),
):
    if not body.question.strip():
        raise HTTPException(400, "La pregunta no puede estar vacía.")
    # El checkpointer del agente es compartido entre todos los usuarios (una
    # sola memoria en el proceso), así que el thread_id que llega del cliente
    # se antepone con el id del usuario autenticado: así nunca puede chocar
    # con el de otro usuario, ni un cliente puede intentar retomar la
    # conversación de alguien más adivinando o reutilizando un thread_id.
    thread_id = f"{user['id']}:{body.thread_id or uuid.uuid4().hex}"
    try:
        reply = start(
            body.question.strip(), body.is_new_conversation, store, calendar, profile, settings,
            thread_id=thread_id,
        )
    except VisionError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc
    except openai.OpenAIError as exc:
        # El agente llama al modelo con otra librería: un cuelgue o una caída llega
        # como estos errores y no debe salir como un 500 sin explicación.
        log.warning("Error de conexión con el modelo del agente: %r", exc)
        raise HTTPException(503, PATIENT_FACING_ERROR) from exc
    return _agent_response(reply)


@app.post("/agent/chat/resume")
def agent_chat_resume(
    body: AgentResumeRequest,
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_store),
    calendar: CalendarStore = Depends(get_calendar),
    profile: ProfileStore = Depends(get_profile),
    resume=Depends(get_agent_resume),
    user: dict = Depends(get_current_user),
):
    if body.decision not in {"approve", "edit", "reject"}:
        raise HTTPException(400, "decision debe ser 'approve', 'edit' o 'reject'.")
    if body.decision == "edit" and not body.edited_args:
        raise HTTPException(400, "edited_args es obligatorio cuando decision es 'edit'.")
    if not str(body.resume_state.get("thread_id", "")).startswith(f"{user['id']}:"):
        raise HTTPException(403, "Esta confirmación no pertenece a tu sesión.")
    try:
        reply = resume(
            body.resume_state, body.decision, store, calendar, profile, settings,
            edited_args=body.edited_args,
        )
    except VisionError as exc:
        log.warning("Error de modelo/proveedor: %s", exc)
        raise HTTPException(503 if exc.transient else 502, PATIENT_FACING_ERROR) from exc
    except openai.OpenAIError as exc:
        # El agente llama al modelo con otra librería: un cuelgue o una caída llega
        # como estos errores y no debe salir como un 500 sin explicación.
        log.warning("Error de conexión con el modelo del agente: %r", exc)
        raise HTTPException(503, PATIENT_FACING_ERROR) from exc
    except (KeyError, IndexError) as exc:
        # Sin este registro el error real quedaba oculto detrás del 400.
        log.warning("No se pudo reanudar la acción del agente (decisión=%s): %r", body.decision, exc, exc_info=True)
        raise HTTPException(400, "resume_state inválido o corrupto.") from exc
    return _agent_response(reply)
