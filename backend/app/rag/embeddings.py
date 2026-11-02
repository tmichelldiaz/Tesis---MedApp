import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings


class EmbeddingError(RuntimeError):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _friendly(status: int, model: str) -> str:
    if status == 429:
        return (
            f"El modelo de embeddings {model} está saturado o limitó el uso (429). "
            "Reintenta en unos minutos."
        )
    if status in (401, 403):
        return f"OpenRouter rechazó la API key ({status}). Revisa OPENROUTER_API_KEY."
    if status == 402:
        return f"Tu cuenta de OpenRouter no tiene saldo para el modelo {model} (402)."
    if status == 404:
        return f"El modelo de embeddings {model} no existe o no está disponible (404)."
    return f"OpenRouter respondió {status} generando embeddings con {model}."


def _embed_with(
    model: str,
    texts: list[str],
    settings: Settings,
    client: httpx.Client | None,
) -> list[list[float]]:
    payload = {"model": model, "input": texts}
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "X-Title": "MedApp",
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=settings.request_timeout_s)

    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(
            multiplier=settings.retry_min_wait_s, max=settings.retry_max_wait_s
        ),
        reraise=True,
    )
    def _call() -> dict:
        response = http.post(
            f"{settings.openrouter_base_url}/embeddings", json=payload, headers=headers
        )
        response.raise_for_status()
        return response.json()

    try:
        data = _call()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise EmbeddingError(
            _friendly(status, model), transient=status == 429 or status >= 500
        ) from exc
    except httpx.HTTPError as exc:
        raise EmbeddingError(
            f"No se pudo contactar a OpenRouter: {exc}", transient=True
        ) from exc
    finally:
        if owns_client:
            http.close()

    try:
        ordered = sorted(data["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in ordered]
    except (KeyError, TypeError, IndexError) as exc:
        err = data.get("error", {}).get("message") if isinstance(data, dict) else None
        raise EmbeddingError(f"Respuesta inesperada de OpenRouter: {err or data}") from exc

    if len(vectors) != len(texts):
        raise EmbeddingError(
            f"OpenRouter devolvió {len(vectors)} vector(es) para {len(texts)} texto(s)."
        )
    return vectors


def embed(
    texts: list[str],
    settings: Settings,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    if not settings.openrouter_api_key:
        raise EmbeddingError("Falta OPENROUTER_API_KEY (configúrala en backend/.env).")

    models = [settings.embeddings_model]
    if settings.embeddings_fallback_model and settings.embeddings_fallback_model not in models:
        models.append(settings.embeddings_fallback_model)

    last_error: EmbeddingError | None = None
    for position, model in enumerate(models):
        is_last = position == len(models) - 1
        attempt = settings if is_last else settings.model_copy(update={"max_retries": 2})
        try:
            return _embed_with(model, texts, attempt, client)
        except EmbeddingError as exc:
            if not exc.transient or is_last:
                raise
            last_error = exc
    assert last_error is not None
    raise last_error
