from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    concept_filename: str
    concept_title: str
    chunk_index: int
    text: str
    pages: list[int]


def chunk_concept(
    filename: str,
    title: str,
    body: str,
    pages: list[int],
    max_chars: int,
) -> list[Chunk]:
    body = body.strip()
    if not body:
        return []
    if len(body) <= max_chars:
        return [Chunk(filename, title, 0, body, pages)]

    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > max_chars and current:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)

    return [Chunk(filename, title, i, piece, pages) for i, piece in enumerate(pieces)]
