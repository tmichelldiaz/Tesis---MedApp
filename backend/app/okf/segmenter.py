import re

from app.okf.models import Segmentation, Unit

HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
PAGE_MARKER = re.compile(
    r"^\s*<!--\s*p[áa]ginas?\s+(\d+)(?:\s*-\s*(\d+))?\s*-->\s*$", re.IGNORECASE
)
SPLIT_LEVELS = (1, 2, 3)


def _scan(lines: list[str]) -> list[tuple[int, int, str] | None]:
    marks: list[tuple[int, int, str] | None] = []
    fence: str | None = None
    for line in lines:
        fence_match = FENCE.match(line)
        if fence_match:
            token = fence_match.group(1)
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            marks.append(None)
            continue
        heading = None if fence else HEADING.match(line)
        marks.append((len(heading.group(1)), 0, heading.group(2).strip()) if heading else None)
    return marks


def _build_units(lines: list[str], marks, level: int) -> tuple[list[Unit], int]:
    starts = [i for i, m in enumerate(marks) if m and m[0] == level]
    bounds = ([0] if not starts or starts[0] != 0 else []) + starts + [len(lines)]
    units: list[Unit] = []
    current_pages: list[int] = []

    page_at: list[list[int]] = []
    for line in lines:
        marker = PAGE_MARKER.match(line)
        if marker:
            first = int(marker.group(1))
            last = int(marker.group(2) or first)
            current_pages = list(range(first, last + 1))
        page_at.append(current_pages)

    for begin, end in zip(bounds, bounds[1:]):
        chunk = lines[begin:end]
        kept = [ln for ln in chunk if not PAGE_MARKER.match(ln)]
        text = "\n".join(kept).strip()
        if not text:
            continue
        pages: set[int] = set()
        for offset, line in enumerate(chunk):
            if line.strip() and not PAGE_MARKER.match(line):
                pages.update(page_at[begin + offset])
        first_heading = next(
            (marks[begin + o] for o in range(len(chunk)) if marks[begin + o]), None
        )
        head = marks[begin] if marks[begin] and marks[begin][0] == level else None
        title = (head or first_heading or (None, 0, None))[2]
        units.append(
            Unit(
                title=title,
                level=level if head else None,
                text=text,
                pages=sorted(pages),
            )
        )
    return _merge_heading_only(units)


def _has_body(text: str) -> bool:
    return any(line.strip() and not HEADING.match(line) for line in text.split("\n"))


def _merge_heading_only(units: list[Unit]) -> tuple[list[Unit], int]:
    merged: list[Unit] = []
    carry: Unit | None = None
    folded = 0
    for index, unit in enumerate(units):
        if carry is not None:
            folded += 1
            unit = Unit(
                title=unit.title or carry.title,
                level=unit.level,
                text=f"{carry.text}\n\n{unit.text}",
                pages=sorted(set(carry.pages) | set(unit.pages)),
            )
            carry = None
        if not _has_body(unit.text) and index < len(units) - 1:
            carry = unit
            continue
        merged.append(unit)
    return merged, folded


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _drop_running_headers(lines: list[str]) -> tuple[list[str], list[str]]:
    starts = [i for i, line in enumerate(lines) if PAGE_MARKER.match(line)]
    if len(starts) < 2:
        return lines, []
    marks = _scan(lines)
    bounds = starts + [len(lines)]

    def leading(begin: int, end: int) -> list[int]:
        found: list[int] = []
        for i in range(begin + 1, end):
            if not lines[i].strip():
                continue
            if not marks[i]:
                break
            found.append(i)
        return found

    per_page = [leading(bounds[k], bounds[k + 1]) for k in range(len(starts))]
    pages_with: dict[str, int] = {}
    for indexes in per_page:
        for text in {_normalize(marks[i][2]) for i in indexes}:
            pages_with[text] = pages_with.get(text, 0) + 1

    repeated = {text for text, count in pages_with.items() if count >= 2}
    seen: set[str] = set()
    drop: set[int] = set()
    names: list[str] = []
    for indexes in per_page:
        for i in indexes:
            text = _normalize(marks[i][2])
            if text not in repeated:
                continue
            if text in seen:
                drop.add(i)
                if marks[i][2] not in names:
                    names.append(marks[i][2])
            else:
                seen.add(text)
    kept = [line for i, line in enumerate(lines) if i not in drop]
    return kept, names


def segment(markdown: str) -> Segmentation:
    lines = markdown.replace("\r\n", "\n").split("\n")
    lines, dropped = _drop_running_headers(lines)
    marks = _scan(lines)

    for level in SPLIT_LEVELS:
        units, folded = _build_units(lines, marks, level)
        if len(units) >= 2:
            return Segmentation(
                level=level, units=units, dropped_headers=dropped, merged_heading_blocks=folded
            )

    whole, _ = _build_units(lines, [None] * len(lines), 1)
    if whole:
        first_heading = next((m for m in marks if m), None)
        whole[0].title = first_heading[2] if first_heading else None
    return Segmentation(level=None, units=whole, dropped_headers=dropped)
