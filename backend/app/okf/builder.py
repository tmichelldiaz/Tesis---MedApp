import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from app.okf import frontmatter
from app.okf.models import Bundle, Concept, Unit, ValidationResult
from app.okf.segmenter import segment
from app.okf.validator import INVALID, VALID, VALID_WITH_WARNINGS, validate

CONCEPT_TYPE = "Clinical Document Section"
PRODUCER = "medapp-extractor"

_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_MD_NOISE = re.compile(r"[*_`>#]+")
_LINK_IN_TITLE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LABEL_NOISE = str.maketrans("", "", "[]()")

_FORMATS = {
    "pdf": "pdf", "image/png": "png", "image/jpeg": "jpeg", "image/webp": "webp",
    "multi-image": "fotos",
}
VALIDATION_TEXT = {
    VALID: "válido",
    VALID_WITH_WARNINGS: "válido con advertencias",
    INVALID: "inválido",
}


def format_label(kind: str | None) -> str:
    return _FORMATS.get(kind or "", kind or "desconocido")


def concept_filename(position: int) -> str:
    return f"concept-{position:02d}.md"


def index_label(title: str) -> str:
    label = _LINK_IN_TITLE.sub(r"\1", title).translate(_LABEL_NOISE)
    label = " ".join(label.split())
    return label or "Unidad sin título"


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _describe(unit: Unit, title: str) -> str:
    rows = 0
    for line in unit.text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _TABLE_ROW.match(line):
            if not _TABLE_SEP.match(line):
                rows += 1
            continue
        clean = _MD_NOISE.sub("", stripped).strip()
        if clean:
            return clean if len(clean) <= 160 else clean[:157].rstrip() + "..."
    if rows:
        return f"Tabla con {max(rows - 1, 1)} fila(s) de datos."
    return title


def _actor(model: str) -> str:
    return f"{PRODUCER}/{model}"


def _concept_files(
    units: list[Unit],
    source_name: str,
    document_id: str,
    model: str,
    stamp: str,
) -> list[Concept]:
    concepts: list[Concept] = []
    for position, unit in enumerate(units, start=1):
        title = unit.title or Path(source_name).stem or f"Sección {position}"
        description = _describe(unit, title)
        filename = concept_filename(position)
        meta = {
            "type": CONCEPT_TYPE,
            "title": title,
            "description": description,
            "status": "draft",
            "generated": {"by": _actor(model), "at": stamp},
            "sources": [
                {
                    "id": "original",
                    "resource": f"medapp://documents/{document_id}",
                    "title": source_name,
                }
            ],
        }
        if unit.pages:
            meta["pages"] = unit.pages
        concepts.append(
            Concept(
                filename=filename,
                title=title,
                description=description,
                pages=unit.pages,
                content=frontmatter.dump(meta) + "\n" + unit.text.strip() + "\n",
            )
        )
    return concepts


def _index(concepts: list[Concept], source_name: str, source_format: str, created_at: str) -> str:
    navigation = "".join(
        f"{position}. [{index_label(c.title)}]({c.filename})\n"
        for position, c in enumerate(concepts, start=1)
    )
    return (
        "# Índice\n\n"
        f"- Documento de origen: {source_name}\n"
        f"- Formato: {source_format}\n"
        f"- Conceptos: {len(concepts)}\n"
        f"- Creado: {created_at}\n\n"
        f"## Conceptos\n\n{navigation}"
    )


def _operations(
    *,
    source_format: str,
    page_count: int | None,
    model: str,
    seconds: float | None,
    level: int | None,
    dropped_headers: list[str],
    merged_blocks: int,
    notes: list[str],
) -> list[str]:
    pages = f" ({page_count} página(s))" if page_count is not None else ""
    took = f" en {seconds}s" if seconds is not None else ""
    if source_format == "pdf":
        read = f"Se leyó el documento como PDF{pages}."
    elif source_format == "markdown":
        read = "Se leyó el documento como Markdown UTF-8 ya transcrito."
    elif source_format == "fotos":
        count = f"{page_count} foto(s)" if page_count is not None else "varias fotos"
        read = f"Se combinaron {count} como páginas de una misma historia, en el orden en que se subieron."
    else:
        read = f"Se leyó el documento como imagen {source_format}{pages}."

    operations = [read]
    if source_format != "markdown":
        operations.append(f"Se transcribió el contenido a Markdown con `{model}`{took}.")
    operations += notes
    operations.append("Se ignoraron los encabezados dentro de bloques de código delimitados.")

    if dropped_headers:
        names = ", ".join(f"`{h}`" for h in dropped_headers)
        operations.append(
            f"Se omitieron los encabezados de página repetidos (aparecen en varias páginas): {names}."
        )
    if merged_blocks:
        operations.append(
            f"Se fusionaron {merged_blocks} bloque(s) que solo contenían encabezados con la unidad siguiente."
        )

    if level is None:
        operations.append(
            "Ningún nivel de encabezado dividía el documento: se mantuvo como una única unidad lógica."
        )
    else:
        operations += [
            f"Se segmentó el documento por el nivel de encabezado Markdown H{level}, "
            "el nivel más alto que realmente lo divide.",
            "Se preservó el orden original de las unidades detectadas.",
            "Se mantuvo el encabezado de cada unidad dentro de su documento de concepto.",
        ]
    operations.append(
        "Cada unidad se guardó como documento de concepto con metadatos OKF v0.2 "
        "(`status: draft`, sin verificación humana)."
    )
    return operations


def _log(
    source_name: str, source_format: str, operations: list[str], concepts: list[Concept]
) -> str:
    operation_list = "".join(f"- {op}\n" for op in operations)
    units = "".join(
        f"{position}. {index_label(c.title)} -> {c.filename}\n"
        for position, c in enumerate(concepts, start=1)
    )
    return (
        "# Registro de conversión\n\n"
        "## Documento de origen\n\n"
        f"- Archivo: {source_name}\n"
        f"- Formato: {source_format}\n\n"
        f"## Operaciones\n\n{operation_list}\n"
        f"## Unidades detectadas\n\n{units}\n"
        f"Total de unidades detectadas: {len(concepts)}\n"
    )


def _validation_section(result: ValidationResult) -> str:
    label = VALIDATION_TEXT.get(result.state, result.state)
    section = ["\n## Validación\n\n", f"- Resultado: {label} ({result.state})\n"]
    section.append(
        "- Comprobaciones superadas: estructura mínima (index.md, log.md y al menos un "
        "concepto), frontmatter YAML con `type` en cada concepto y resolución de todos los "
        "enlaces del índice.\n"
        if result.state != INVALID
        else "- Comprobaciones superadas: " + "; ".join(result.passed or ["ninguna"]) + ".\n"
    )
    if result.errors:
        section.append("- Errores:\n" + "".join(f"  - {e}\n" for e in result.errors))
    if result.warnings:
        section.append("- Advertencias:\n" + "".join(f"  - {w}\n" for w in result.warnings))
    else:
        section.append("- Advertencias: ninguna.\n")
    return "".join(section)


def build_bundle(
    markdown: str,
    source_name: str,
    model: str,
    page_count: int | None = None,
    seconds: float | None = None,
    document_id: str | None = None,
    now: datetime | None = None,
    notes: list[str] | None = None,
    source_format: str | None = None,
    created_at: str | None = None,
) -> Bundle:
    stamp = _iso(now or datetime.now(timezone.utc))
    document_id = document_id or hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:16]
    fmt = format_label(source_format)

    segmentation = segment(markdown)
    if not segmentation.units:
        raise ValueError("El Markdown no tiene contenido para generar un bundle.")

    concepts = _concept_files(segmentation.units, source_name, document_id, model, stamp)
    operations = _operations(
        source_format=fmt,
        page_count=page_count,
        model=model,
        seconds=seconds,
        level=segmentation.level,
        dropped_headers=segmentation.dropped_headers,
        merged_blocks=segmentation.merged_heading_blocks,
        notes=notes or [],
    )

    files = {c.filename: c.content for c in concepts}
    files["index.md"] = _index(concepts, source_name, fmt, created_at or stamp)
    files["log.md"] = _log(source_name, fmt, operations, concepts)

    files["log.md"] += _validation_section(validate(files))

    return Bundle(
        files=files,
        concepts=concepts,
        segmentation_level=segmentation.level,
        validation=validate(files),
    )


def write_bundle(bundle: Bundle, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, text in bundle.files.items():
        (target / name).write_text(text, encoding="utf-8", newline="\n")
