import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.extraction.documents import UnsupportedDocument  # noqa: E402
from app.extraction.to_markdown import convert  # noqa: E402
from app.extraction.vision_client import VisionError  # noqa: E402
from app.okf.builder import build_bundle, write_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF/imagen (o .md) -> bundle OKF v0.2.")
    parser.add_argument("file", type=Path, help="PDF/imagen, o un .md ya transcrito")
    parser.add_argument("-o", "--output", type=Path, help="Carpeta del bundle")
    args = parser.parse_args()

    settings = Settings()
    try:
        if args.file.suffix.lower() == ".md":
            markdown, model, pages, seconds, notes = (
                args.file.read_text(encoding="utf-8"), settings.vision_model, None, None, []
            )
        else:
            result = convert(args.file.read_bytes(), settings, source_name=args.file.name)
            markdown, model, pages, seconds, notes = (
                result.markdown, result.model, result.page_count, result.seconds, result.notes
            )
        suffix = args.file.suffix.lower()
        kinds = {".md": "markdown", ".pdf": "pdf", ".png": "image/png",
                 ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        bundle = build_bundle(
            markdown, source_name=args.file.name, model=model,
            page_count=pages, seconds=seconds, source_format=kinds.get(suffix),
            notes=notes,
        )
    except (UnsupportedDocument, VisionError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    target = args.output or Path("out") / f"bundle-{args.file.stem}"
    write_bundle(bundle, target)

    check = bundle.validation
    print(f"Bundle -> {target}  | conceptos={len(bundle.concepts)} validación={check.state}")
    for message in check.errors + check.warnings:
        print(f"  - {message}")
    return 0 if check.state != "invalid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
