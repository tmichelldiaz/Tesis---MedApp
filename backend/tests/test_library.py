from app.okf.library import build_root_index, build_root_log
from app.okf.validator import INVALID, VALID, VALID_WITH_WARNINGS

ENTRIES = [
    {"slug": "historia-01", "title": "informe.pdf", "concept_count": 5, "kind": "pdf",
     "validation_state": VALID, "created_at": "2026-09-21T21:14:58Z"},
    {"slug": "historia-02", "title": "foto.jpg", "concept_count": 2, "kind": "image/jpeg",
     "validation_state": VALID, "created_at": "2026-09-22T00:42:02Z"},
]


class TestRootIndex:
    def test_matches_the_historia_index_style(self):
        assert build_root_index(ENTRIES) == (
            "# Índice\n\n"
            "- Historias: 2\n\n"
            "## Historias\n\n"
            "1. [informe.pdf](historia-01/index.md) — 2026-09-21T21:14:58Z\n"
            "2. [foto.jpg](historia-02/index.md) — 2026-09-22T00:42:02Z\n"
        )

    def test_empty_library(self):
        assert build_root_index([]) == "# Índice\n\n- Historias: 0\n\n## Historias\n\n"

    def test_sanitizes_titles_like_concept_titles(self):
        entry = {**ENTRIES[0], "title": "Ver [esto](https://x.org)"}
        assert "[Ver esto](historia-01/index.md) — 2026-09-21T21:14:58Z" in build_root_index([entry])


class TestRootLog:
    def test_has_the_same_section_shape_as_a_historia_log(self):
        log = build_root_log(ENTRIES)
        assert log.startswith("# Registro de historias\n\n## Biblioteca\n\n- Historias: 2\n\n## Operaciones\n\n")
        for section in ("## Operaciones", "## Historias detectadas", "## Validación"):
            assert section in log

    def test_operations_list_one_line_per_historia_with_its_date(self):
        log = build_root_log(ENTRIES)
        assert "- Se agregó `historia-01` el 2026-09-21T21:14:58Z a partir de `informe.pdf` (pdf, 5 concepto(s), válido).\n" in log
        assert "- Se agregó `historia-02` el 2026-09-22T00:42:02Z a partir de `foto.jpg` (jpeg, 2 concepto(s), válido).\n" in log

    def test_detected_list_includes_dates_and_total(self):
        log = build_root_log(ENTRIES)
        assert "1. informe.pdf -> historia-01 (2026-09-21T21:14:58Z)\n" in log
        assert "2. foto.jpg -> historia-02 (2026-09-22T00:42:02Z)\n" in log
        assert "Total de historias: 2\n" in log

    def test_validation_all_clean(self):
        log = build_root_log(ENTRIES)
        assert "- Resultado: 2 de 2 historias válidas sin advertencias.\n" in log
        assert "- Advertencias: ninguna.\n" in log

    def test_validation_reports_entries_with_warnings(self):
        entries = ENTRIES + [
            {"slug": "historia-03", "title": "c.pdf", "concept_count": 1, "kind": "pdf",
             "validation_state": VALID_WITH_WARNINGS, "created_at": "2026-09-22T02:00:00Z"}
        ]
        log = build_root_log(entries)
        assert "- Resultado: 2 de 3 historias válidas sin advertencias.\n" in log
        assert "- Advertencias: 1 historia(s) con advertencias: `historia-03`.\n" in log

    def test_unknown_validation_state_does_not_crash(self):
        entries = [{**ENTRIES[0], "validation_state": INVALID}]
        log = build_root_log(entries)
        assert "inválido" in log

    def test_empty_library(self):
        log = build_root_log([])
        assert "Total de historias: 0\n" in log
        assert "- Resultado: 0 de 0 historias válidas sin advertencias.\n" in log
