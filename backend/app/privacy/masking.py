"""Enmascaramiento de datos de identificación antes de que un texto salga hacia
un modelo de terceros (OpenRouter).

Son dos capas, aplicadas en este orden:

1. Local (`redact_pii`): reglas por etiqueta, cédula y fecha de nacimiento. Es
   determinista, gratis, y cubre lo que Cloud DLP no detecta bien (la cédula de
   ciudadanía colombiana no tiene un infoType propio; `COLOMBIA_CDC_NUMBER` es
   el carné de identidad). También es la red de seguridad si el DLP está apagado.
2. Cloud DLP (Sensitive Data Protection), solo si `dlp_enabled`: detecta
   nombres de persona, teléfonos, correos y direcciones aunque aparezcan sueltos
   dentro de una nota narrativa, sin etiqueta.

No se tocan valores de laboratorio, fechas de examen ni la edad: el modelo los
necesita para interpretar rangos de referencia y armar la línea de tiempo.

Si el DLP está activado y falla, se lanza `MaskingError` en vez de dejar pasar el
texto sin enmascarar ("fail closed"): es preferible que el paciente reintente a
que un dato de identificación llegue a un tercero.
"""

import logging
import re
import threading

import google.auth
import httpx
from google.auth.credentials import CredentialsWithQuotaProject
from google.auth.transport.requests import Request as GoogleRequest

from app.config import Settings
from app.rag.redact import redact_pii

log = logging.getLogger("medapp.privacy")

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
_DLP_URL = "https://dlp.googleapis.com/v2/projects/{project}/content:deidentify"
INFO_TYPES = ("PERSON_NAME", "PHONE_NUMBER", "EMAIL_ADDRESS", "STREET_ADDRESS", "DATE_OF_BIRTH")
REPLACEMENT = "[dato oculto]"

_lock = threading.Lock()
_credentials = None
_default_project: str | None = None
_by_quota_project: dict[str, object] = {}


class MaskingError(RuntimeError):
    """El enmascaramiento con DLP no se pudo completar."""


def _auth(project: str = "") -> tuple[dict[str, str], str | None]:
    """Cabeceras de autenticación y proyecto por defecto, vía Application Default
    Credentials (en Cloud Run, la cuenta de servicio del servicio).

    La cuota se asigna siempre al proyecto donde corre el DLP. Sin esto, unas
    credenciales de usuario con otro "proyecto de cuota" (p. ej. de un
    `gcloud auth application-default login` antiguo) harían que Google rechace
    la llamada por tener el DLP desactivado en ese otro proyecto."""
    global _credentials, _default_project
    with _lock:
        if _credentials is None:
            _credentials, _default_project = google.auth.default(scopes=_SCOPES)
        target = project or _default_project
        credentials = _credentials
        if target and isinstance(credentials, CredentialsWithQuotaProject):
            if target not in _by_quota_project:
                _by_quota_project[target] = credentials.with_quota_project(target)
            credentials = _by_quota_project[target]
        if not credentials.valid:
            credentials.refresh(GoogleRequest())
        headers: dict[str, str] = {}
        credentials.apply(headers)
        return headers, _default_project


def _chunks(text: str, limit: int) -> list[str]:
    """Parte el texto en trozos de a lo sumo `limit` caracteres, preferentemente
    entre párrafos. Unidos de nuevo reproducen el texto exacto."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for token in re.split(r"(\n\n)", text):
        while len(token) > limit:  # párrafo gigante: se corta por la fuerza
            if current:
                parts.append(current)
                current = ""
            parts.append(token[:limit])
            token = token[limit:]
        if current and len(current) + len(token) > limit:
            parts.append(current)
            current = ""
        current += token
    if current:
        parts.append(current)
    return parts


def _deidentify(text: str, settings: Settings, client: httpx.Client | None) -> str:
    headers, default_project = _auth(settings.dlp_project)
    project = settings.dlp_project or default_project
    if not project:
        raise MaskingError("No hay proyecto de Google Cloud configurado para DLP.")

    body = {
        "item": {"value": text},
        "inspectConfig": {
            "infoTypes": [{"name": name} for name in INFO_TYPES],
            "minLikelihood": "POSSIBLE",
        },
        "deidentifyConfig": {
            "infoTypeTransformations": {
                "transformations": [
                    {"primitiveTransformation": {"replaceConfig": {"newValue": {"stringValue": REPLACEMENT}}}}
                ]
            }
        },
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=settings.dlp_timeout_s)
    try:
        response = http.post(_DLP_URL.format(project=project), json=body, headers=headers)
        response.raise_for_status()
        return response.json()["item"]["value"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise MaskingError(f"Cloud DLP no respondió como se esperaba: {exc}") from exc
    finally:
        if owns_client:
            http.close()


def mask_text(text: str, settings: Settings, client: httpx.Client | None = None) -> str:
    """Devuelve `text` sin datos de identificación del paciente."""
    if not text or not text.strip():
        return text
    masked = redact_pii(text)
    if not settings.dlp_enabled:
        return masked
    return "".join(_deidentify(chunk, settings, client) for chunk in _chunks(masked, settings.dlp_chunk_chars))
