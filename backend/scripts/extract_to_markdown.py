import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.extraction.documents import UnsupportedDocument  # noqa: E402
from app.extraction.to_markdown import convert  # noqa: E402
from app.extraction.vision_client import VisionError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF/imagen -> Markdown con visión.")
    parser.add_argument("file", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Ruta del .md de salida")
    args = parser.parse_args()

    settings = Settings()
    try:
        result = convert(args.file.read_bytes(), settings, source_name=args.file.name)
    except (UnsupportedDocument, VisionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output = args.output or Path("out") / f"{args.file.stem}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.markdown, encoding="utf-8")

    print(
        f"OK -> {output}  | modelo={result.model} páginas={result.page_count} "
        f"llamadas={result.requests} tiempo={result.seconds}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
