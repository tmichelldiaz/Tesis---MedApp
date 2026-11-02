from datetime import datetime, timezone

import yaml

from app.okf import frontmatter
from app.okf.builder import build_bundle, concept_filename, index_label
from app.okf.segmenter import segment
from app.okf.validator import INVALID, VALID, VALID_WITH_WARNINGS, validate

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)

SAMPLE = """<!-- página 1 -->

# Laboratorio Ejemplo

Paciente: Prueba

## Analítica de sangre

| Examen | Resultado |
|---|---|
| Glucosa | 94 |

<!-- página 2 -->

## Observaciones

Control en 3 meses.
"""


class TestSegmenter:
    def test_splits_by_h2_when_single_h1(self):
        seg = segment(SAMPLE)
        assert seg.level == 2
        assert [u.title for u in seg.units] == [
            "Laboratorio Ejemplo", "Analítica de sangre", "Observaciones",
        ]

    def test_prefers_h1_when_it_divides(self):
        seg = segment("# A\n\ntexto\n\n# B\n\ntexto\n\n## sub\n\nx")
        assert seg.level == 1
        assert [u.title for u in seg.units] == ["A", "B"]
        assert "## sub" in seg.units[1].text

    def test_falls_back_to_h3(self):
        seg = segment("### uno\n\na\n\n### dos\n\nb")
        assert seg.level == 3 and len(seg.units) == 2

    def test_no_headings_gives_single_unit(self):
        seg = segment("solo texto\nsin encabezados")
        assert seg.level is None and len(seg.units) == 1

    def test_ignores_headings_inside_code_fences(self):
        md = "# T\n\n```\n# no soy encabezado\n## ni yo\n```\n\n## Real\n\nx"
        seg = segment(md)
        assert [u.title for u in seg.units] == ["T", "Real"]
        assert "# no soy encabezado" in seg.units[0].text

    def test_text_before_first_heading_is_its_own_unit(self):
        seg = segment("intro suelta\n\n## A\n\na\n\n## B\n\nb")
        assert seg.level == 2
        assert seg.units[0].title is None and "intro suelta" in seg.units[0].text
        assert [u.title for u in seg.units[1:]] == ["A", "B"]

    def test_tracks_pages_and_strips_markers(self):
        seg = segment(SAMPLE)
        assert [u.pages for u in seg.units] == [[1], [1], [2]]
        assert all("<!--" not in u.text for u in seg.units)

    def test_empty_markdown_has_no_units(self):
        assert segment("  \n\n").units == []


class TestFrontmatter:
    def test_roundtrip_with_tricky_values(self):
        meta = {
            "type": "Clinical Document Section",
            "title": 'Glucosa: "en ayunas" #1',
            "description": "yes",
            "status": "draft",
            "generated": {"by": "medapp-extractor/qwen/qwen3.8-27b:free", "at": "2026-09-21T12:00:00Z"},
            "sources": [{"id": "original", "resource": "medapp://documents/abc", "title": "a b.pdf"}],
            "pages": [1, 2],
        }
        parsed, body = frontmatter.split(frontmatter.dump(meta) + "\ncuerpo\n")
        assert body == "cuerpo\n"
        assert parsed["title"] == meta["title"]
        assert parsed["description"] == "yes"
        assert parsed["generated"]["by"] == meta["generated"]["by"]
        assert parsed["sources"] == meta["sources"]
        assert parsed["pages"] == [1, 2]

    def test_timestamp_is_emitted_unquoted(self):
        assert "at: 2026-09-21T12:00:00Z" in frontmatter.dump({"generated": {"at": "2026-09-21T12:00:00Z"}})

    def test_split_errors(self):
        for bad in ("sin frontmatter", "---\ntype: x\nsin cierre", "---\n[a, b\n---\n"):
            try:
                frontmatter.split(bad)
            except frontmatter.FrontmatterError:
                continue
            raise AssertionError(f"debió fallar: {bad!r}")


class TestBuilder:
    def build(self, md=SAMPLE):
        return build_bundle(
            md, "muestra.pdf", "qwen/qwen3.8-27b:free",
            page_count=2, seconds=3.5, document_id="doc123", now=NOW,
        )

    def test_produces_valid_okf_bundle(self):
        bundle = self.build()
        assert bundle.validation.state == VALID
        assert sorted(bundle.files) == [
            "concept-01.md", "concept-02.md",
            "concept-03.md", "index.md", "log.md",
        ]

    def test_every_concept_has_required_okf_frontmatter(self):
        for concept in self.build().concepts:
            meta, body = frontmatter.split(concept.content)
            assert meta["type"] and meta["title"] and meta["description"]
            assert meta["status"] == "draft"
            assert meta["generated"]["by"].startswith("medapp-extractor/")
            assert meta["sources"][0]["resource"] == "medapp://documents/doc123"
            assert body.strip().startswith("#")

    def test_index_matches_workshop_layout_exactly(self):
        assert self.build().files["index.md"] == (
            "# Índice\n\n"
            "- Documento de origen: muestra.pdf\n"
            "- Formato: desconocido\n"
            "- Conceptos: 3\n"
            "- Creado: 2026-09-21T12:00:00Z\n\n"
            "## Conceptos\n\n"
            "1. [Laboratorio Ejemplo](concept-01.md)\n"
            "2. [Analítica de sangre](concept-02.md)\n"
            "3. [Observaciones](concept-03.md)\n"
        )

    def test_log_matches_workshop_layout(self):
        log = build_bundle(
            SAMPLE, "muestra.pdf", "qwen/qwen3.8-27b:free",
            page_count=2, seconds=3.5, document_id="doc123", now=NOW, source_format="pdf",
        ).files["log.md"]
        assert log.startswith(
            "# Registro de conversión\n\n"
            "## Documento de origen\n\n"
            "- Archivo: muestra.pdf\n"
            "- Formato: pdf\n\n"
            "## Operaciones\n\n"
            "- Se leyó el documento como PDF (2 página(s))"
        )
        assert "- Se transcribió el contenido a Markdown con `qwen/qwen3.8-27b:free` en 3.5s.\n" in log
        assert (
            "Se segmentó el documento por el nivel de encabezado Markdown H2, "
            "el nivel más alto que realmente lo divide."
        ) in log
        assert (
            "\n\n## Unidades detectadas\n\n"
            "1. Laboratorio Ejemplo -> concept-01.md\n"
            "2. Analítica de sangre -> concept-02.md\n"
            "3. Observaciones -> concept-03.md\n\n"
            "Total de unidades detectadas: 3\n"
        ) in log

    def test_log_ends_with_validation_section(self):
        log = self.build().files["log.md"]
        assert log.endswith(
            "\n## Validación\n\n"
            "- Resultado: válido (valid)\n"
            "- Comprobaciones superadas: estructura mínima (index.md, log.md y al menos un concepto), "
            "frontmatter YAML con `type` en cada concepto y resolución de todos los enlaces del índice.\n"
            "- Advertencias: ninguna.\n"
        )

    def test_index_labels_are_sanitized_like_the_workshop(self):
        assert index_label("Ver [la fuente](https://x.org) (2026)") == "Ver la fuente 2026"
        assert index_label("  [] ()  ") == "Unidad sin título"

    def test_single_unit_log_says_no_heading_divided_the_document(self):
        log = self.build("Texto breve sin secciones.").files["log.md"]
        assert "Ningún nivel de encabezado dividía el documento" in log
        assert "Total de unidades detectadas: 1\n" in log

    def test_table_section_description_and_pages(self):
        concept = self.build().concepts[1]
        assert concept.description == "Tabla con 1 fila(s) de datos."
        assert concept.pages == [1]

    def test_short_document_yields_single_concept_without_warnings(self):
        bundle = self.build("Texto breve sin secciones.")
        assert len(bundle.concepts) == 1
        assert bundle.validation.state == VALID and not bundle.validation.warnings

    def test_empty_markdown_is_rejected(self):
        try:
            self.build("   ")
        except ValueError:
            return
        raise AssertionError("debió fallar")

    def test_concept_filenames_follow_the_workshop_convention(self):
        assert concept_filename(1) == "concept-01.md"
        assert concept_filename(12) == "concept-12.md"
        assert concept_filename(100) == "concept-100.md"


class TestValidator:
    def good(self):
        return dict(self_files())

    def test_valid(self):
        assert validate(self.good()).state == VALID

    def test_missing_index_or_log_is_invalid(self):
        for name in ("index.md", "log.md"):
            files = self.good()
            del files[name]
            result = validate(files)
            assert result.state == INVALID and result.errors

    def test_broken_index_link_is_invalid(self):
        files = self.good()
        files["index.md"] += "* [Fantasma](no-existe.md) - x\n"
        assert validate(files).state == INVALID

    def test_unlinked_concept_is_invalid(self):
        files = self.good()
        files["02-otro.md"] = concept("Otro")
        assert validate(files).state == INVALID

    def test_concept_without_type_is_invalid(self):
        files = self.good()
        files["01-a.md"] = "---\ntitle: A\n---\n\ncuerpo\n"
        assert validate(files).state == INVALID

    def test_concept_without_frontmatter_is_invalid(self):
        files = self.good()
        files["01-a.md"] = "# solo markdown\n"
        assert validate(files).state == INVALID

    def test_no_concepts_is_invalid(self):
        assert validate({"index.md": "# x\n", "log.md": "# Directory Update Log\n"}).state == INVALID

    def test_warnings_do_not_invalidate(self):
        files = self.good()
        files["01-a.md"] = "---\ntype: X\n---\n\ncuerpo\n"
        result = validate(files)
        assert result.state == VALID_WITH_WARNINGS and not result.errors

    def test_index_frontmatter_only_allows_okf_version(self):
        files = self.good()
        files["index.md"] = '---\nokf_version: "0.2"\nextra: 1\n---\n\n* [A](01-a.md) - x\n'
        assert validate(files).state == VALID_WITH_WARNINGS


def concept(title: str) -> str:
    return f"---\ntype: X\ndescription: d\n---\n\n# {title}\n\ncuerpo\n"


def self_files() -> dict[str, str]:
    return {
        "index.md": '---\nokf_version: "0.2"\n---\n\n# Doc\n\n* [A](01-a.md) - d\n',
        "log.md": "# Directory Update Log\n\n## 2026-09-21\n* **Creation**: x\n",
        "01-a.md": concept("A"),
    }


def test_yaml_is_loadable_for_generated_concepts():
    for concept_ in build_bundle(SAMPLE, "m.pdf", "m", now=NOW).concepts:
        assert isinstance(yaml.safe_load(concept_.content.split("---")[1]), dict)


class TestRunningHeadersAndMerging:
    PAGED = (
        "<!-- página 1 -->\n\n# INSTITUCIÓN\n## LABORATORIO\n\nPaciente: X\n\n## HEMATOLOGÍA\n\ntabla 1\n\n"
        "<!-- página 2 -->\n\n# INSTITUCIÓN\n## LABORATORIO\n\n## QUÍMICA\n\ntabla 2\n"
    )

    def test_repeated_page_headers_are_dropped_after_first_page(self):
        seg = segment(self.PAGED)
        assert seg.dropped_headers == ["INSTITUCIÓN", "LABORATORIO"]
        assert [u.title for u in seg.units] == ["LABORATORIO", "HEMATOLOGÍA", "QUÍMICA"]
        assert sum(u.text.count("INSTITUCIÓN") for u in seg.units) == 1

    def test_single_page_documents_are_untouched(self):
        seg = segment("<!-- página 1 -->\n\n# T\n\n## A\n\nx\n\n## B\n\ny")
        assert seg.dropped_headers == []

    def test_headings_that_only_look_alike_across_pages_are_kept(self):
        md = "<!-- página 1 -->\n\n## Resumen\n\na\n\n<!-- página 2 -->\n\n## Detalle\n\nb\n"
        assert segment(md).dropped_headers == []

    def test_heading_only_units_merge_into_the_next_one(self):
        seg = segment("# Título\n## Sub\n\ncontenido real\n\n## Otra\n\nmás")
        assert [u.title for u in seg.units] == ["Sub", "Otra"]
        assert "# Título" in seg.units[0].text

    def test_log_records_dropped_headers_in_operations(self):
        bundle = build_bundle(TestRunningHeadersAndMerging.PAGED, "r.pdf", "m", now=NOW)
        operations = bundle.files["log.md"].split("## Operaciones")[1].split("## Unidades")[0]
        assert "encabezados de página repetidos" in operations and "`INSTITUCIÓN`" in operations
        assert bundle.validation.state == VALID

    def test_log_records_merged_heading_blocks(self):
        md = "# Título" + chr(10) + "## Sub" + chr(10) * 2 + "contenido" + chr(10) * 2 + "## Otra" + chr(10) * 2 + "más"
        bundle = build_bundle(md, "r.md", "m", now=NOW)
        assert "Se fusionaron 1 bloque(s)" in bundle.files["log.md"]
