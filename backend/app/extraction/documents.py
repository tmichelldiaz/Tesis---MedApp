from dataclasses import dataclass

import pymupdf

from app.config import Settings


class UnsupportedDocument(ValueError):
    pass


@dataclass(frozen=True)
class PageImage:
    index: int
    data: bytes
    mime: str
    text: str = ""


def detect_kind(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise UnsupportedDocument("Formato no soportado: se aceptan PDF, PNG, JPEG y WEBP.")


def load_pages(data: bytes, settings: Settings) -> list[PageImage]:
    if not data:
        raise UnsupportedDocument("El archivo está vacío.")
    if len(data) > settings.max_file_mb * 1024 * 1024:
        raise UnsupportedDocument(f"El archivo supera {settings.max_file_mb} MB.")

    kind = detect_kind(data)
    if kind != "pdf":
        return [PageImage(index=1, data=data, mime=kind)]

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UnsupportedDocument("El PDF está dañado o no se puede abrir.") from exc

    with doc:
        if doc.needs_pass:
            raise UnsupportedDocument("El PDF está protegido con contraseña.")
        if doc.page_count == 0:
            raise UnsupportedDocument("El PDF no tiene páginas.")
        if doc.page_count > settings.max_pages:
            raise UnsupportedDocument(
                f"El PDF tiene {doc.page_count} páginas; el máximo es {settings.max_pages}."
            )
        return [
            PageImage(
                index=i + 1,
                data=page.get_pixmap(dpi=settings.pdf_render_dpi).tobytes("png"),
                mime="image/png",
                text=page.get_text().strip(),
            )
            for i, page in enumerate(doc)
        ]


PREVIEW_DPI = 90
PREVIEW_MAX_SIDE = 900


def render_first_page(data: bytes, settings: Settings) -> tuple[bytes, int]:
    """Imagen PNG (liviana) de la primera página de un PDF y su número de páginas.

    Es solo para que el paciente confirme que eligió el documento correcto antes de
    subirlo: no guarda nada ni toca ningún modelo."""
    if not data:
        raise UnsupportedDocument("El archivo está vacío.")
    if len(data) > settings.max_file_mb * 1024 * 1024:
        raise UnsupportedDocument(f"El archivo supera {settings.max_file_mb} MB.")
    if detect_kind(data) != "pdf":
        raise UnsupportedDocument("La vista previa de esta ruta es solo para PDF.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UnsupportedDocument("El PDF está dañado o no se puede abrir.") from exc
    with doc:
        if doc.needs_pass:
            raise UnsupportedDocument("El PDF está protegido con contraseña.")
        if doc.page_count == 0:
            raise UnsupportedDocument("El PDF no tiene páginas.")
        page = doc[0]
        longest = max(page.rect.width, page.rect.height) or 1
        dpi = min(PREVIEW_DPI, int(72 * PREVIEW_MAX_SIDE / longest) or PREVIEW_DPI)
        return page.get_pixmap(dpi=max(dpi, 36)).tobytes("png"), doc.page_count


def load_pages_from_images(items: list[tuple[bytes, str]], settings: Settings) -> list[PageImage]:
    if not items:
        raise UnsupportedDocument("No se recibió ninguna foto.")
    if len(items) > settings.max_pages:
        raise UnsupportedDocument(f"Se recibieron {len(items)} fotos; el máximo es {settings.max_pages}.")
    if sum(len(data) for data, _ in items) > settings.max_file_mb * 1024 * 1024:
        raise UnsupportedDocument(f"El conjunto de fotos supera {settings.max_file_mb} MB en total.")

    pages = []
    for index, (data, kind) in enumerate(items, start=1):
        if not data:
            raise UnsupportedDocument(f"La foto {index} está vacía.")
        if kind == "pdf":
            raise UnsupportedDocument("No se pueden combinar un PDF con fotos en una misma historia.")
        pages.append(PageImage(index=index, data=data, mime=kind))
    return pages
