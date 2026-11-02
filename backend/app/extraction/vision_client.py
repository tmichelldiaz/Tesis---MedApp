import base64
import json
import logging
import re
from dataclasses import replace

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings
from app.extraction.documents import PageImage
from app.extraction.integrity import keeps_the_numbers, lost_numbers
from app.privacy.masking import mask_text

_RULES = """Reglas:
- Transcribe TODO el contenido, en el idioma original y en el orden de lectura. No resumas, no interpretes, no expliques y no agregues comentarios propios.
- Nunca inventes contenido. Si algo no se lee con certeza escribe [ilegible]; no lo adivines.
- Conserva exactamente fechas, cifras, unidades, rangos de referencia y nombres.
- Refleja la estructura del documento con encabezados Markdown: `#` para el título del documento, `##` para cada sección principal, `###` para subsecciones.
- Los resultados tabulares (laboratorio, mediciones) van como tablas Markdown, una fila por examen, con sus columnas originales (examen, resultado, unidad, valor de referencia, etc.).
- En las tablas Markdown, la fila separadora debe ser exactamente `|---|---|---|` (tres guiones por columna, nada más). Nunca la alargues ni la alinees con más guiones o dos puntos.
- Las listas van como listas Markdown. Marca sellos, firmas o logotipos como [sello], [firma] o [logotipo].
- Responde únicamente con el Markdown, sin bloques de código que lo envuelvan."""

SYSTEM_PROMPT = (
    "Eres un transcriptor de documentos clínicos. Recibes imágenes de páginas de una "
    "historia clínica o de un resultado médico y devuelves su contenido como Markdown fiel.\n\n"
    + _RULES
)

TEXT_SYSTEM_PROMPT = (
    "Eres un transcriptor de documentos clínicos. Recibes el texto extraído automáticamente de "
    "las páginas de un PDF clínico (puede venir sin formato, con columnas de tablas aplanadas en "
    "líneas sueltas) y devuelves su contenido como Markdown fiel.\n\n"
    + _RULES
    + "\n- Si una tabla llegó aplanada, reconstrúyela solo cuando la correspondencia entre "
    "columnas sea inequívoca; si no lo es, deja las líneas tal cual en lugar de adivinar."
)

QUICK_RETRIES = 2
NO_REASONING = {"enabled": False}
MIN_OUTPUT_TOKENS = 1500   # mínimo de salida al transcribir una página, aunque tenga poco texto
LOOP_FACTOR = 4           # una salida más de 4 veces más larga que el texto original es un bucle
LOSSY_ATTEMPTS = 2  # intentos por modelo cuando la transcripción pierde números

_FENCE = re.compile(r"^\s*```(?:markdown|md)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


log = logging.getLogger("medapp.vision")


def _raw_text_transcription(pages: list[PageImage]) -> "Transcription":
    """El texto original de las páginas como Markdown mínimo, sin pasar por ningún modelo."""
    body = "\n\n".join(f"<!-- página {p.index} -->\n\n{p.text.strip()}" for p in pages)
    result = Transcription(body)
    result.model = "texto original (sin IA)"
    result.mode = "text"
    return result


class VisionError(RuntimeError):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


# El mensaje real de VisionError es para los logs (nombra modelos, proveedores,
# códigos HTTP: útil para depurar, pero un paciente no tiene por qué ver eso ni
# entenderlo). Esto es lo único que debe llegar al cliente.
PATIENT_FACING_ERROR = "No se pudo completar la solicitud. Intenta de nuevo en unos minutos."


class Transcription(str):
    model: str = ""
    mode: str = "vision"


def _api_message(body: str) -> str:
    try:
        return str(json.loads(body)["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return body[:200]


def _friendly(status: int, body: str, model: str) -> str:
    if status == 429:
        return (
            f"El modelo {model} está saturado o limitó el uso en este momento (429). "
            "Reintenta en unos minutos."
        )
    if status in (401, 403):
        return f"OpenRouter rechazó la API key ({status}). Revisa OPENROUTER_API_KEY."
    if status == 402:
        return f"Tu cuenta de OpenRouter no tiene saldo para el modelo {model} (402)."
    if status == 404:
        return f"El modelo {model} no existe o no está disponible (404)."
    return f"OpenRouter respondió {status}: {_api_message(body)}"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _data_uri(page: PageImage) -> str:
    return f"data:{page.mime};base64,{base64.b64encode(page.data).decode()}"


def _clean(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _vision_messages(pages: list[PageImage]) -> list[dict]:
    content: list[dict] = [
        {"type": "text", "text": f"Transcribe a Markdown estas {len(pages)} página(s) en orden."}
    ]
    content += [{"type": "image_url", "image_url": {"url": _data_uri(p)}} for p in pages]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _text_messages(pages: list[PageImage]) -> list[dict]:
    body = "\n\n".join(f"[Página {p.index}]\n{p.text}" for p in pages)
    return [
        {"role": "system", "content": TEXT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Convierte a Markdown el texto de estas {len(pages)} página(s):\n\n{body}",
        },
    ]


def has_native_text(pages: list[PageImage], settings: Settings) -> bool:
    return all(len(p.text.strip()) >= settings.min_native_text_chars for p in pages)


def transcribe(
    pages: list[PageImage],
    settings: Settings,
    client: httpx.Client | None = None,
) -> str:
    vision_models = [settings.vision_model]
    if settings.vision_fallback_model:
        vision_models.append(settings.vision_fallback_model)

    text_model = settings.text_fallback_model
    has_text = has_native_text(pages, settings)
    text_usable = bool(text_model and text_model not in vision_models and has_text)

    last_error: VisionError | None = None

    # El texto nativo del PDF (cuando existe) ya lo extrajo PyMuPDF sin costo
    # ni espera; leerlo con un modelo de solo texto es mucho más rápido y
    # barato que renderizar la página como imagen y mandarla a un modelo de
    # visión. Por eso se intenta primero, y la visión queda como respaldo
    # (para fotos, escaneos, o si el modelo de texto falla).
    # Con el DLP activo y un PDF con texto, la página NUNCA sale como imagen: la
    # imagen traería a la vista los datos de identificación que acabamos de
    # enmascarar en el texto. Si el modelo de texto falla, se prueban los modelos
    # multimodales igualmente, pero solo con el texto ya enmascarado; el último
    # usa el presupuesto completo de reintentos y, si tampoco responde, el
    # paciente reintenta.
    keep_private = settings.dlp_enabled and has_text
    if keep_private:
        text_chain = list(dict.fromkeys(m for m in [text_model, *vision_models] if m))
    elif text_usable:
        text_chain = [text_model]
    else:
        text_chain = []

    if text_chain:
        masked_pages = [replace(p, text=mask_text(p.text, settings)) for p in pages]
        quick = settings.model_copy(update={"max_retries": min(settings.max_retries, QUICK_RETRIES)})
        source = "\n".join(p.text for p in masked_pages)
        # Tope de salida proporcional al texto de entrada (el Markdown ocupa poco más que el texto): un
        # bucle de repetición se corta en segundos y no llena el límite general.
        cap = {"max_output_tokens": min(settings.transcribe_max_tokens, max(MIN_OUTPUT_TOKENS, len(source) // 2))}
        lossy = False  # algún modelo respondió, pero perdiendo números
        for position, model in enumerate(text_chain):
            is_last = position == len(text_chain) - 1
            attempt_settings = (settings if (keep_private and is_last) else quick).model_copy(update=cap)
            messages = _text_messages(masked_pages)
            for attempt in range(LOSSY_ATTEMPTS):
                try:
                    result = chat_completion(model, "text", messages, attempt_settings, client, reasoning=NO_REASONING)
                except VisionError as exc:
                    if not exc.transient:
                        raise
                    last_error = exc
                    break
                # Un modelo que omite filas de la tabla deja al paciente con resultados que faltan o, peor,
                # con otro valor. Si pierde números del texto original, se rehace una vez diciéndole cuáles
                # omitió (es lo más rápido); si insiste, se descarta y se prueba el siguiente modelo.
                if keeps_the_numbers(source, str(result)):
                    return result
                lost = lost_numbers(source, str(result))
                lossy = True
                log.warning("La transcripción de %s perdió %d números (%s...) en el intento %d", model, len(lost), lost[:6], attempt + 1)
                last_error = VisionError(f"{model} omitió {len(lost)} números del documento.", transient=True)
                if len(str(result)) > LOOP_FACTOR * len(source) + 500:
                    # Es un bucle de repetición, no una omisión: a temperatura 0 el mismo modelo lo repetiría
                    # idéntico, así que no se le da otra oportunidad.
                    log.warning("%s entró en un bucle de repetición; se pasa al siguiente modelo", model)
                    break
                messages = messages + [
                    {"role": "assistant", "content": str(result)},
                    {"role": "user", "content": (
                        "Tu transcripción omitió datos del texto original (por ejemplo estos números: "
                        + ", ".join(lost[:40])
                        + "). Vuelve a transcribir TODAS las páginas completas, fila por fila, sin omitir ninguna."
                    )},
                ]
        if keep_private:
            if lossy:
                # Los modelos respondieron pero ninguno conservó todos los números: se usa el texto
                # original, sin IA. Es menos ordenado, pero no pierde ni cambia ningún dato.
                log.warning("Ningún modelo conservó los números; se usa el texto original de las páginas")
                return _raw_text_transcription(masked_pages)
            # Si todos fallaron por una caída del proveedor, el paciente reintenta (no se guarda texto crudo).
            assert last_error is not None
            raise last_error

    for position, model in enumerate(vision_models):
        is_last_option = position == len(vision_models) - 1
        attempt_settings = (
            settings
            if is_last_option
            else settings.model_copy(update={"max_retries": min(settings.max_retries, QUICK_RETRIES)})
        )
        try:
            return chat_completion(model, "vision", _vision_messages(pages), attempt_settings, client)
        except VisionError as exc:
            if not exc.transient:
                raise
            last_error = exc

    if text_model and text_model not in vision_models and not has_text:
        last_error = VisionError(
            f"{last_error} El modelo de respaldo {text_model} es de solo texto y este "
            "documento no tiene texto seleccionable (es una foto o un escaneo), "
            "así que no puede leerlo.",
            transient=True,
        )
    assert last_error is not None
    raise last_error


def provider_routing(settings: Settings) -> dict | None:
    """Parámetro `provider` de OpenRouter según la configuración, o None si no hay."""
    only = [p.strip() for p in settings.openrouter_providers.split(",") if p.strip()]
    deny = settings.openrouter_data_collection.strip().lower() == "deny"
    if not only and not deny:
        return None
    routing: dict = {}
    if only:
        routing["only"] = only
        routing["allow_fallbacks"] = False
    if deny:
        routing["data_collection"] = "deny"
    return routing


def chat_completion(
    model: str,
    mode: str,
    messages: list[dict],
    settings: Settings,
    client: httpx.Client | None,
    response_format: dict | None = None,
    reasoning: dict | None = None,
) -> Transcription:
    if not settings.openrouter_api_key:
        raise VisionError("Falta OPENROUTER_API_KEY (configúrala en backend/.env).")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": settings.max_output_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if reasoning is not None:
        # Copiar texto no necesita razonar. En una prueba, con el razonamiento activado Gemini 2.5 Flash
        # entraba en un bucle (2 de 3 veces: 65 s y 16.384 tokens de basura); apagado: 4 s y todo correcto.
        payload["reasoning"] = reasoning
    routing = provider_routing(settings)
    if routing:
        payload["provider"] = routing
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
            f"{settings.openrouter_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    try:
        data = _call()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        # Un 404 es un modelo que OpenRouter ya no ofrece (los gratuitos rotan).
        # No tiene sentido reintentarlo, pero sí pasar al siguiente de la cadena de
        # respaldo, así que se marca igual que una saturación: "prueba otro".
        raise VisionError(
            _friendly(status, exc.response.text, model),
            transient=status in (404, 429) or status >= 500,
        ) from exc
    except httpx.HTTPError as exc:
        raise VisionError(
            f"No se pudo contactar a OpenRouter: {exc}", transient=True
        ) from exc
    finally:
        if owns_client:
            http.close()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        # OpenRouter a veces responde 200 con un cuerpo de error del proveedor
        # (saturación, límite de cuota) en vez de un 429 real — sin esto, el
        # llamador nunca se entera de que puede reintentar con otro modelo.
        err = data.get("error", {}).get("message") if isinstance(data, dict) else None
        raise VisionError(
            f"Respuesta inesperada de OpenRouter: {err or data}", transient=True
        ) from exc

    if not content or not content.strip():
        # Mismo caso: un 200 con contenido vacío suele ser el modelo degradado
        # por demanda, no un error real de la petición — se trata como transitorio
        # para que el llamador pueda intentarlo con el modelo de respaldo.
        raise VisionError("El modelo devolvió una transcripción vacía.", transient=True)
    result = Transcription(_clean(content))
    result.model = model
    result.mode = mode
    return result
