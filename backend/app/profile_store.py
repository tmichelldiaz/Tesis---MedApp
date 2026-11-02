import json
import os
from pathlib import Path

from app.fsutil import read_json_safe, write_json_atomic
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_DEFAULT = {
    "name": None,
    "birth_date": None,
    "sex": None,
    "weight_kg": None,
    "blood_type": None,
    "updated_at": None,
}


class ProfileStore:
    """Un único registro de datos básicos del paciente (nombre, fecha de nacimiento,
    peso, tipo de sangre). Es de un solo paciente por instalación de la app, así que
    no hay lista ni id: solo un archivo con un objeto."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "profile.json"

    def _write(self, data: dict) -> None:
        write_json_atomic(self.path, data)

    def get(self) -> dict:
        stored = read_json_safe(self.path, lambda: {})
        return {**_DEFAULT, **(stored if isinstance(stored, dict) else {})}

    def update(self, **fields) -> dict:
        data = self.get()
        data.update(fields)
        data["updated_at"] = _now()
        self._write(data)
        return data
