from app.okf.builder import VALIDATION_TEXT, format_label, index_label
from app.okf.validator import VALID


def build_root_index(entries: list[dict]) -> str:
    navigation = "".join(
        f"{position}. [{index_label(e['title'])}]({e['slug']}/index.md) — {e['created_at']}\n"
        for position, e in enumerate(entries, start=1)
    )
    return (
        "# Índice\n\n"
        f"- Historias: {len(entries)}\n\n"
        f"## Historias\n\n{navigation}"
    )


def _operations(entries: list[dict]) -> str:
    return "".join(
        f"- Se agregó `{e['slug']}` el {e['created_at']} a partir de `{index_label(e['title'])}` "
        f"({format_label(e['kind'])}, {e['concept_count']} concepto(s), "
        f"{VALIDATION_TEXT.get(e['validation_state'], e['validation_state'])}).\n"
        for e in entries
    )


def _validation_section(entries: list[dict]) -> str:
    total = len(entries)
    clean = sum(1 for e in entries if e["validation_state"] == VALID)
    lines = [f"- Resultado: {clean} de {total} historias válidas sin advertencias.\n"]
    lines.append(
        "- Comprobaciones superadas: cada historia agregada supera su propia validación de "
        "bundle (index.md, log.md, frontmatter y enlaces resueltos; ver el log.md de cada historia).\n"
    )
    if clean == total:
        lines.append("- Advertencias: ninguna.\n")
    else:
        con_advertencias = ", ".join(f"`{e['slug']}`" for e in entries if e["validation_state"] != VALID)
        lines.append(f"- Advertencias: {total - clean} historia(s) con advertencias: {con_advertencias}.\n")
    return "".join(lines)


def build_root_log(entries: list[dict]) -> str:
    detected = "".join(
        f"{position}. {index_label(e['title'])} -> {e['slug']} ({e['created_at']})\n"
        for position, e in enumerate(entries, start=1)
    )
    return (
        "# Registro de historias\n\n"
        "## Biblioteca\n\n"
        f"- Historias: {len(entries)}\n\n"
        f"## Operaciones\n\n{_operations(entries)}\n"
        f"## Historias detectadas\n\n{detected}\n"
        f"Total de historias: {len(entries)}\n\n"
        f"## Validación\n\n{_validation_section(entries)}"
    )
