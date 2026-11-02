"""Cuál es el valor MÁS RECIENTE de un examen: un solo criterio para todo el sistema.

Los exámenes de muchos laboratorios no traen fecha. El servidor entrega los archivos del más
nuevo al más viejo, así que desempatar "por el orden de la lista" hacía que el último de la
lista fuera el archivo más VIEJO. Cada parte (la app, el resumen con IA, el chat) lo
resolvía por su cuenta y llegaban a valores distintos para el mismo examen.

Criterio único: primero la fecha del examen y, si no la tiene o es la misma, la fecha en que
se subió el archivo."""

from __future__ import annotations

import unicodedata


def exam_key(name: str) -> str:
    """Clave para agrupar el mismo examen escrito con distinta mayúscula o tildes."""
    decomposed = unicodedata.normalize("NFD", str(name or "").lower())
    return " ".join("".join(c for c in decomposed if unicodedata.category(c) != "Mn").split())


def with_document(doc: dict, value: dict) -> dict:
    """Un valor del laboratorio con los datos del archivo del que salió."""
    return {
        **value,
        "document_id": doc["id"],
        "document_filename": doc.get("filename"),
        "document_created_at": doc.get("created_at") or "",
    }


def recency(row: dict) -> tuple[str, str]:
    return (row.get("date") or "", row.get("document_created_at") or "")


def oldest_first(rows: list[dict]) -> list[dict]:
    """Del más antiguo al más reciente (estable: lo que empata conserva su orden)."""
    return sorted(rows, key=recency)


def latest_per_exam(rows: list[dict]) -> dict[str, dict]:
    """El valor más reciente de cada examen, por clave de examen."""
    latest: dict[str, dict] = {}
    for row in oldest_first(rows):
        latest[exam_key(row.get("exam"))] = row
    return latest


def drop_repeats(rows: list[dict]) -> list[dict]:
    """Quita lo repetido (el mismo laboratorio subido dos veces) y deja la copia más reciente.

    Devuelve las filas del más antiguo al más reciente."""
    kept: dict[tuple, dict] = {}
    for row in oldest_first(rows):
        key = (
            exam_key(row.get("exam")), str(row.get("value_raw")), row.get("unit") or "",
            row.get("date") or "", row.get("reference_text") or "",
        )
        kept.pop(key, None)  # se reinserta al final: queda la copia más reciente y en su lugar
        kept[key] = row
    return oldest_first(list(kept.values()))


def uploaded_label(row: dict) -> str:
    """Fecha de subida legible para mostrarle a un modelo: '2026-10-11'."""
    return (row.get("document_created_at") or "")[:10] or "s/f"
