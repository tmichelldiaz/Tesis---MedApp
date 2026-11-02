import re

from app.okf import frontmatter
from app.okf.models import ValidationResult

RESERVED = {"index.md", "log.md"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

VALID = "valid"
VALID_WITH_WARNINGS = "valid_with_warnings"
INVALID = "invalid"


def _index_targets(index_text: str) -> list[str]:
    _, body = _safe_split_index(index_text)
    targets = []
    for target in LINK.findall(body):
        if re.match(r"^[a-z]+://", target):
            continue
        targets.append(target.lstrip("./").lstrip("/"))
    return targets


def _safe_split_index(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        try:
            return frontmatter.split(text)
        except frontmatter.FrontmatterError:
            pass
    return {}, text


def validate(files: dict[str, str]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []

    index = files.get("index.md")
    if index is None or not index.strip():
        errors.append("Falta index.md o está vacío.")
    else:
        passed.append("index.md presente y no vacío")

    log = files.get("log.md")
    if log is None:
        errors.append("Falta log.md.")
    elif not log.strip():
        warnings.append("log.md está vacío.")
    else:
        passed.append("log.md presente y no vacío")

    concepts = {name: text for name, text in files.items() if name.endswith(".md") and name not in RESERVED}
    if not concepts:
        errors.append("El bundle no tiene ningún documento de concepto.")
    else:
        passed.append(f"{len(concepts)} documento(s) de concepto")

    frontmatter_ok = True
    for name, text in concepts.items():
        try:
            meta, body = frontmatter.split(text)
        except frontmatter.FrontmatterError as exc:
            errors.append(f"{name}: {exc}.")
            frontmatter_ok = False
            continue
        if not str(meta.get("type") or "").strip():
            errors.append(f"{name}: el frontmatter no tiene el campo 'type'.")
            frontmatter_ok = False
        if not body.strip():
            warnings.append(f"{name}: el concepto no tiene contenido.")
        if not str(meta.get("description") or "").strip():
            warnings.append(f"{name}: el concepto no tiene 'description'.")
    if concepts and frontmatter_ok:
        passed.append("frontmatter YAML válido con 'type' en todos los conceptos (OKF v0.2 §11)")

    if index and index.strip():
        targets = _index_targets(index)
        missing = [t for t in targets if t not in files]
        for target in missing:
            errors.append(f"index.md enlaza a '{target}', que no existe en el bundle.")
        unlinked = [n for n in concepts if n not in targets]
        for name in unlinked:
            errors.append(f"El concepto '{name}' no está enlazado desde index.md.")
        if not missing:
            passed.append("todos los enlaces de index.md se resuelven")
        if not unlinked and concepts:
            passed.append("todos los conceptos están enlazados desde index.md")

    if index and index.startswith("---\n"):
        meta, _ = _safe_split_index(index)
        if set(meta) - {"okf_version"}:
            warnings.append("index.md solo puede llevar 'okf_version' en su frontmatter.")

    state = INVALID if errors else (VALID_WITH_WARNINGS if warnings else VALID)
    return ValidationResult(state=state, errors=errors, warnings=warnings, passed=passed)
