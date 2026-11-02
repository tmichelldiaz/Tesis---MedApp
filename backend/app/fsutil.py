"""Lectura y escritura de archivos JSON que aguantan varias peticiones a la vez.

En producción los datos viven en un bucket montado como carpeta (Cloud Storage FUSE). Si dos peticiones del mismo
paciente llegaban juntas (la app pide citas, avisos y perfil al mismo tiempo cuando se abre), ambas escribían el
mismo archivo temporal: una lo renombraba y a la otra le fallaba con "no existe el archivo" (error 500), y a veces
el archivo definitivo quedaba vacío, con lo que TODAS las peticiones siguientes de ese paciente fallaban."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Callable

log = logging.getLogger("medapp.fs")


def write_text_atomic(path: Path, text: str) -> None:
    """Escribe en un archivo temporal ÚNICO y lo renombra: nadie lee un archivo a medias ni choca con otra petición.
    Si el renombrado falla (el montaje del bucket a veces lo rechaza), se escribe directo como último recurso."""
    path = Path(path)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        log.warning("No se pudo renombrar %s; se escribe directo", path.name, exc_info=True)
        path.write_text(text, encoding="utf-8")
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def write_json_atomic(path: Path, data: object) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json_safe(path: Path, default: Callable[[], object]):
    """El contenido del JSON, o el valor por defecto si no existe, está vacío o está dañado (nunca lanza error:
    un archivo estropeado no debe dejar a una persona sin poder usar la app)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default()
    except OSError:
        log.warning("No se pudo leer %s", path.name, exc_info=True)
        return default()
    if not text.strip():
        log.warning("%s estaba vacío; se usa el valor por defecto", path.name)
        return default()
    try:
        return json.loads(text)
    except ValueError:
        log.warning("%s tenía un JSON dañado; se usa el valor por defecto", path.name)
        return default()
