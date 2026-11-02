import json
import os
import re
import shutil
import threading
import uuid
from urllib.parse import unquote
from datetime import datetime, timezone
from pathlib import Path

from app.fsutil import read_json_safe, write_json_atomic
from app.okf.library import build_root_index, build_root_log

_ID = re.compile(r"^[0-9a-f]{32}$")
_HISTORIA = re.compile(r"^historia-(\d+)$")
_EXT = {"pdf": "pdf", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def clean_filename(name: str | None) -> str:
    """El nombre del archivo tal como lo tiene el paciente.

    El celular manda los espacios y otros caracteres codificados ("Prueba%208.pdf" en vez de
    "Prueba 8.pdf"); aquí se deshace esa codificación. Un "%" que no forma un código (como en
    "Reporte 50%.pdf") se deja intacto."""
    decoded = unquote(name or "")
    return Path(decoded).name.strip() or "documento"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DocumentStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.library_dir = self.root / "bundle"
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _dir(self, doc_id: str) -> Path | None:
        return self.root / doc_id if _ID.match(doc_id) else None

    def bundle_dir(self, doc_id: str) -> Path | None:
        meta = self.get(doc_id)
        slug = meta.get("historia_slug") if meta else None
        return self.library_dir / slug if slug else None

    def create(self, filename: str, data: bytes, kind: str) -> dict:
        doc_id = uuid.uuid4().hex
        folder = self.root / doc_id
        folder.mkdir(parents=True)
        original = f"original.{_EXT[kind]}"
        (folder / original).write_bytes(data)
        meta = {
            "id": doc_id,
            "filename": clean_filename(filename),
            "kind": kind,
            "size": len(data),
            "original": original,
            "source_pages": None,
            "status": "processing",
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
            "page_count": None,
            "model": None,
            "seconds": None,
            "validation": None,
            "concepts": [],
            "notes": [],
            "lab_values": [],
            "historia_slug": None,
            "category": None,
        }
        self._write(folder, meta)
        return meta

    def create_multi(self, filename: str, pages: list[tuple[bytes, str]]) -> dict:
        doc_id = uuid.uuid4().hex
        folder = self.root / doc_id
        folder.mkdir(parents=True)
        source_pages = []
        for i, (data, kind) in enumerate(pages, start=1):
            name = f"page-{i:02d}.{_EXT[kind]}"
            (folder / name).write_bytes(data)
            source_pages.append({"file": name, "kind": kind})
        meta = {
            "id": doc_id,
            "filename": clean_filename(filename),
            "kind": "multi-image",
            "size": sum(len(data) for data, _ in pages),
            "original": None,
            "source_pages": source_pages,
            "status": "processing",
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
            "page_count": None,
            "model": None,
            "seconds": None,
            "validation": None,
            "concepts": [],
            "notes": [],
            "lab_values": [],
            "historia_slug": None,
            "category": None,
        }
        self._write(folder, meta)
        return meta

    def ensure_historia_slug(self, doc_id: str) -> str:
        with self._lock:
            meta = self.get(doc_id)
            if meta is None:
                raise KeyError(doc_id)
            if meta.get("historia_slug"):
                return meta["historia_slug"]

            used = {
                int(m.group(1))
                for other in self.list_all()
                if (m := _HISTORIA.match(other.get("historia_slug") or ""))
            }
            n = 1
            while n in used:
                n += 1
            slug = f"historia-{n:02d}"

            meta["historia_slug"] = slug
            meta["updated_at"] = _now()
            self._write(self.root / doc_id, meta)
            return slug

    def rewrite_library(self) -> None:
        entries = []
        for meta in self.list_all():
            slug = meta.get("historia_slug")
            if not slug or meta["status"] != "ready":
                continue
            entries.append(
                {
                    "slug": slug,
                    "title": meta["filename"],
                    "concept_count": len(meta["concepts"]),
                    "kind": meta["kind"],
                    "validation_state": (meta.get("validation") or {}).get("state", "valid"),
                    "created_at": meta["created_at"],
                }
            )
        entries.sort(key=lambda e: int(_HISTORIA.match(e["slug"]).group(1)))

        self.library_dir.mkdir(parents=True, exist_ok=True)
        (self.library_dir / "index.md").write_text(
            build_root_index(entries), encoding="utf-8", newline="\n"
        )
        (self.library_dir / "log.md").write_text(
            build_root_log(entries), encoding="utf-8", newline="\n"
        )

    def _write(self, folder: Path, meta: dict) -> None:
        write_json_atomic(folder / "meta.json", meta)

    def get(self, doc_id: str) -> dict | None:
        folder = self._dir(doc_id)
        if not folder or not (folder / "meta.json").exists():
            return None
        meta = read_json_safe(folder / "meta.json", lambda: None)
        if not isinstance(meta, dict):
            return None  # registro dañado: ese documento se ignora, no se cae toda la lista
        # Los archivos subidos antes de este arreglo guardaron el nombre codificado ("Prueba%208.pdf").
        if meta.get("filename"):
            meta["filename"] = clean_filename(meta["filename"])
        return meta

    def update(self, doc_id: str, **fields) -> dict:
        with self._lock:
            meta = self.get(doc_id)
            if meta is None:
                raise KeyError(doc_id)
            meta.update(fields, updated_at=_now())
            self._write(self.root / doc_id, meta)
            return meta

    def list_all(self) -> list[dict]:
        items = [m for m in (self.get(p.name) for p in self.root.iterdir() if p.is_dir()) if m]
        return sorted(items, key=lambda m: m["created_at"], reverse=True)

    def read_original(self, doc_id: str) -> bytes:
        meta = self.get(doc_id)
        if meta is None:
            raise KeyError(doc_id)
        return (self.root / doc_id / meta["original"]).read_bytes()

    def read_source_pages(self, doc_id: str) -> list[tuple[bytes, str]]:
        meta = self.get(doc_id)
        if meta is None:
            raise KeyError(doc_id)
        folder = self.root / doc_id
        return [
            ((folder / p["file"]).read_bytes(), p["kind"]) for p in meta["source_pages"]
        ]

    def transcription_path(self, doc_id: str) -> Path:
        return self.root / doc_id / "transcripcion.md"

    def save_transcription(self, doc_id: str, markdown: str) -> None:
        self.transcription_path(doc_id).write_text(markdown, encoding="utf-8")

    def embeddings_path(self, doc_id: str) -> Path:
        return self.root / doc_id / "embeddings.json"

    def save_embeddings(self, doc_id: str, records: list[dict]) -> None:
        self.embeddings_path(doc_id).write_text(
            json.dumps(records, ensure_ascii=False), encoding="utf-8"
        )

    def load_embeddings(self, doc_id: str) -> list[dict]:
        path = self.embeddings_path(doc_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, doc_id: str) -> None:
        folder = self._dir(doc_id)
        if not folder or not folder.is_dir():
            raise KeyError(doc_id)
        meta = self.get(doc_id) or {}
        slug = meta.get("historia_slug")
        shutil.rmtree(folder)
        if slug:
            historia = self.library_dir / slug
            if historia.is_dir():
                shutil.rmtree(historia)

    def bundle_file_names(self, doc_id: str) -> list[str]:
        folder = self.bundle_dir(doc_id)
        if not folder or not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file())
