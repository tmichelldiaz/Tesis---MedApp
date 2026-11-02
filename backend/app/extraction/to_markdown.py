import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.config import Settings
from app.extraction.documents import PageImage, load_pages, load_pages_from_images
from app.extraction.exam_date import find_exam_date
from app.extraction.vision_client import transcribe
from app.privacy.masking import mask_text

Transcriber = Callable[[list[PageImage], Settings], str]


@dataclass
class ExtractionResult:
    markdown: str
    model: str
    page_count: int
    requests: int
    seconds: float
    source_name: str | None = None
    notes: list[str] = field(default_factory=list)
    exam_date: str | None = None  # AAAA-MM-DD, leída del texto del PDF antes de enmascararlo
    source_text: str | None = None  # texto original del PDF (para comprobar que los valores existen); no se guarda


def _batches(pages: list[PageImage], size: int) -> list[list[PageImage]]:
    size = max(1, size)
    return [pages[i : i + size] for i in range(0, len(pages), size)]


def _marker(batch: list[PageImage]) -> str:
    first, last = batch[0].index, batch[-1].index
    label = f"página {first}" if first == last else f"páginas {first}-{last}"
    return f"<!-- {label} -->"


def convert(
    data: bytes,
    settings: Settings,
    source_name: str | None = None,
    transcriber: Transcriber = transcribe,
) -> ExtractionResult:
    return _convert_pages(load_pages(data, settings), settings, source_name, transcriber)


def convert_images(
    items: list[tuple[bytes, str]],
    settings: Settings,
    source_name: str | None = None,
    transcriber: Transcriber = transcribe,
) -> ExtractionResult:
    return _convert_pages(
        load_pages_from_images(items, settings), settings, source_name, transcriber
    )


def _convert_pages(
    pages: list[PageImage],
    settings: Settings,
    source_name: str | None,
    transcriber: Transcriber,
) -> ExtractionResult:
    started = time.monotonic()
    # El DLP daña las fechas con el mes en letras ("10 [dato oculto] de 2026"), así que la fecha del
    # examen se lee del texto original del PDF, antes de enmascarar. Una fecha no identifica a nadie.
    exam_date = find_exam_date("\n\n".join(p.text for p in pages if p.text))
    batches = _batches(pages, settings.pages_per_request)

    def transcribe_batch(batch: list[PageImage]) -> tuple[list[PageImage], str, str, str]:
        text = transcriber(batch, settings)
        mode = getattr(text, "mode", "vision")
        if mode == "text":
            # El texto nativo ya se enmascaró antes de salir hacia el modelo.
            body = str(text)
        else:
            # Fotos y escaneos: el modelo de visión ve la imagen original, así que
            # lo único que se puede proteger es lo que sale de él, antes de que
            # lo vean la extracción de valores, la clasificación y los embeddings.
            body = mask_text(str(text), settings)
        used = getattr(text, "model", "") or settings.vision_model
        return batch, used, mode, body

    # Las páginas son independientes entre sí: se transcriben a la vez y el
    # resultado conserva el orden original del documento.
    workers = max(1, min(settings.parallel_workers, len(batches)))
    if workers == 1:
        results = [transcribe_batch(batch) for batch in batches]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(transcribe_batch, batches))

    parts: list[str] = []
    models_used: list[str] = []
    notes: list[str] = []
    text_pages: dict[str, list[int]] = {}
    for batch, used, mode, body in results:
        if used not in models_used:
            models_used.append(used)
        if mode == "text":
            text_pages.setdefault(used, []).extend(p.index for p in batch)
        parts.append(f"{_marker(batch)}\n\n{body}")

    for used, indexes in text_pages.items():
        label = ", ".join(str(i) for i in indexes)
        kind = (
            "modelo de solo texto, respaldo"
            if used == settings.text_fallback_model
            else "modelo multimodal, usado solo con el texto"
        )
        notes.append(
            f"Las páginas {label} se transcribieron con `{used}` ({kind}) "
            "a partir de la capa de texto del PDF, no de la imagen."
        )

    return ExtractionResult(
        markdown="\n\n".join(parts).strip() + "\n",
        model=", ".join(models_used),
        page_count=len(pages),
        requests=len(batches),
        seconds=round(time.monotonic() - started, 2),
        source_name=source_name,
        notes=notes,
        exam_date=exam_date,
        # Solo en documentos con texto de verdad: en un escaneo o una foto los valores salen de leer
        # la imagen y no estarían en la capa de texto, así que no se pueden contrastar.
        source_text=(
            "\n".join(p.text for p in pages)
            if pages and all(len(p.text.strip()) >= settings.min_native_text_chars for p in pages)
            else None
        ),
    )
