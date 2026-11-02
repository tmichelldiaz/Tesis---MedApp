import json
import re

import yaml

_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PLAIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./ -]*$")
_AMBIGUOUS = {"true", "false", "null", "yes", "no", "on", "off", "~"}


def scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _ISO_DT.match(text):
        return text
    if (
        _PLAIN.match(text)
        and text.lower() not in _AMBIGUOUS
        and not re.fullmatch(r"[\d.\-+eE]+", text)
        and not text.endswith(" ")
    ):
        return text
    return json.dumps(text, ensure_ascii=False)


def _render(value, indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    for key, val in value.items():
        if isinstance(val, dict):
            lines.append(f"{pad}{key}:")
            lines.extend(_render(val, indent + 1))
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            lines.append(f"{pad}{key}:")
            for item in val:
                first, *rest = _render(item, indent + 2)
                lines.append(f"{pad}  - {first.strip()}")
                lines.extend(rest)
        elif isinstance(val, list):
            lines.append(f"{pad}{key}: [{', '.join(scalar(v) for v in val)}]")
        else:
            lines.append(f"{pad}{key}: {scalar(val)}")
    return lines


def dump(meta: dict) -> str:
    return "---\n" + "\n".join(_render(meta, 0)) + "\n---\n"


class FrontmatterError(ValueError):
    pass


def split(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise FrontmatterError("no empieza con un bloque de frontmatter '---'")
    end = text.find("\n---", 4)
    if end == -1:
        raise FrontmatterError("el bloque de frontmatter no está cerrado con '---'")
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"YAML inválido: {exc}") from exc
    if not isinstance(meta, dict):
        raise FrontmatterError("el frontmatter no es un mapa clave/valor")
    body = text[end + 4 :].lstrip("\n")
    return meta, body
