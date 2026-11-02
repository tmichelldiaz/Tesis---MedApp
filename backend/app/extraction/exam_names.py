"""Un mismo examen, un solo nombre.

Cada informe escribe el mismo resultado a su manera ("Puntuación ESUR", "Invasión extracapsular (ESUR)",
"Puntuación ESUR (invasión extracapsular)"). Como el historial, las gráficas y el asistente agrupan por nombre, el
paciente veía "no hay valores previos" para un examen que sí tenía en otras historias. Aquí se unifican los nombres
de TODOS los exámenes del paciente: un modelo propone qué nombres son la misma medida y una revisión
determinista descarta las uniones peligrosas (derecho con izquierdo, largo con ancho, porcentaje con valor
absoluto, lesión 1 con lesión 2...)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter

import httpx

from app.config import Settings
from app.extraction.vision_client import NO_REASONING, VisionError, chat_completion
from app.store import DocumentStore
from app.values_history import exam_key

log = logging.getLogger("medapp.exam_names")

SYSTEM_PROMPT = """Unificas los nombres de los exámenes de UN mismo paciente. Recibes una lista de nombres \
(con su unidad y cuántas veces aparece cada uno). Informes distintos escriben la MISMA medida con nombres \
diferentes; agrupa los nombres que son exactamente la misma medida o resultado.

Reglas:
- Agrupa solo si es la misma medida de la misma estructura. Ejemplos que SÍ van juntos: "Uretra membranosa" y \
"Longitud de uretra membranosa"; "Puntuación ESUR" e "Invasión extracapsular (ESUR)".
- NO agrupes medidas distintas aunque se parezcan: PSA y densidad de PSA; lóbulo derecho e izquierdo; largo, \
ancho y profundidad; lesión 1 y lesión 2; un porcentaje (%) y su valor absoluto; total, directa e indirecta; \
exámenes de sangre y de orina.
- Solo agrupa nombres con la MISMA unidad (cm con cm, mm con mm): una medida en cm y otra en mm no se unen.
- Escribe los nombres tal cual los recibes, SIN la unidad entre corchetes.
- Si dudas, no los agrupes.
- "canonical" debe ser EXACTAMENTE uno de los nombres del grupo: el más claro y completo.
- Un nombre aparece en un solo grupo. Los nombres que no se repiten con otro no van en ningún grupo.

Responde ÚNICAMENTE con JSON de esta forma: {"groups": [{"canonical": "<nombre>", "variants": ["<nombre>", "<nombre>"]}]}
Si no hay nada que unir: {"groups": []}"""

# Palabras que distinguen una medida de otra: dos nombres solo se unen si las tienen iguales.
_DISTINCTIVE = {
    "derecho", "derecha", "izquierdo", "izquierda", "largo", "ancho", "profundidad", "total", "directa",
    "indirecta", "libre", "anterior", "posterior", "superior", "inferior", "basal", "postprandial",
    "orina", "suero", "sangre",
}


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _signature(name: str) -> tuple:
    plain = _plain(name)
    words = set(re.findall(r"[a-z]+", plain))
    return (
        frozenset(words & _DISTINCTIVE),
        frozenset(re.findall(r"\d+", plain)),
        "%" in plain,
    )


def compatible(a: str, b: str) -> bool:
    """¿Se pueden unir estos dos nombres sin mezclar medidas distintas?"""
    return _signature(a) == _signature(b)


def _listing(counts: Counter, units: dict[str, str]) -> str:
    lines = []
    for name, n in counts.most_common():
        unit = units.get(name)
        lines.append(f"- {name}" + (f" [{unit}]" if unit else "") + f" (x{n})")
    return "\n".join(lines)


def propose_mapping(
    names: Counter, units: dict[str, str], settings: Settings, client: httpx.Client | None = None,
) -> dict[str, str]:
    """{nombre_variante: nombre_canónico} para los nombres que son la misma medida. Vacío si no hay nada que unir."""
    if len(names) < 2:
        return {}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _listing(names, units)},
    ]
    call_settings = settings.model_copy(update={"max_output_tokens": settings.values_max_tokens})
    raw = str(chat_completion(
        settings.values_model, "text", messages, call_settings, client,
        response_format={"type": "json_object"}, reasoning=NO_REASONING,
    ))
    try:
        data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()))
    except ValueError:
        return {}
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return {}

    known = set(names)

    def known_name(text: object) -> str | None:
        # El modelo a veces copia la unidad entre corchetes que va en la lista: se la quitamos.
        if not isinstance(text, str):
            return None
        clean = re.sub(r"\s*\[[^\]]*\]\s*$", "", text).strip()
        return clean if clean in known else None

    mapping: dict[str, str] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        canonical, variants = known_name(group.get("canonical")), group.get("variants")
        if canonical is None or not isinstance(variants, list):
            continue
        for raw_variant in variants:
            variant = known_name(raw_variant)
            if variant is None or variant == canonical or variant in mapping or variant in mapping.values():
                continue
            if canonical in mapping:
                continue
            if units.get(variant) and units.get(canonical) and units[variant] != units[canonical]:
                log.info("unión rechazada por unidades distintas: %r -> %r", variant, canonical)
                continue
            if compatible(variant, canonical):
                mapping[variant] = canonical
            else:
                log.info("unión rechazada por distinguir medidas: %r -> %r", variant, canonical)
    return mapping


def harmonize_exam_names(
    store: DocumentStore, settings: Settings, client: httpx.Client | None = None, dry_run: bool = False,
) -> dict[str, str]:
    """Unifica los nombres de examen en todas las historias listas del paciente. Devuelve lo que se cambió."""
    docs = [d for d in store.list_all() if d.get("status") == "ready"]
    counts: Counter = Counter()
    units: dict[str, str] = {}
    for doc in docs:
        for v in doc.get("lab_values") or []:
            counts[v["exam"]] += 1
            if v.get("unit"):
                units.setdefault(v["exam"], v["unit"])
    try:
        mapping = propose_mapping(counts, units, settings, client)
    except VisionError:
        log.warning("No se pudieron unificar los nombres de examen", exc_info=True)
        return {}
    if not mapping or dry_run:
        return mapping

    by_key = {exam_key(variant): canonical for variant, canonical in mapping.items()}
    for doc in docs:
        values = doc.get("lab_values") or []
        renamed = [
            {**v, "exam": by_key[exam_key(v["exam"])]} if exam_key(v["exam"]) in by_key else v for v in values
        ]
        if renamed != values:
            store.update(doc["id"], lab_values=renamed)
    return mapping
