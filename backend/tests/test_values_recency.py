"""Cuál es el valor 'actual' de un examen cuando los resultados no traen fecha.

Caso real: cinco archivos con la densidad de PSA 0.054, 0.182, 0.083, 0.152 y 0.142 (en el orden en
que se subieron). El último subido, 0.142, es el actual. Antes, el detalle de la app decía 0.142, el
resumen con IA 0.054 y el chat 0.182, porque cada parte desempataba a su manera."""

import pytest
from fastapi.testclient import TestClient

from app import chat, exam_summary
from app.agent.tools import build_tools
from app.calendar_store import CalendarStore
from app.config import Settings
from app.main import app, get_current_user, get_settings, get_store
from app.profile_store import ProfileStore
from app.store import DocumentStore
from app.values_history import drop_repeats, latest_per_exam, oldest_first
from tests.test_chat import add_ready_doc

DENSITIES = ["0.054", "0.182", "0.083", "0.152", "0.142"]  # del primero al último subido


def value(exam, raw, unit="", date=None, ref=None):
    return {
        "exam": exam, "value_raw": raw, "value_numeric": float(raw) if raw.replace(".", "", 1).isdigit() else None,
        "unit": unit, "date": date, "reference_low": None, "reference_high": None, "reference_text": ref,
    }


def upload_all(store, extra=None):
    """Cinco documentos subidos uno tras otro; ninguno trae fecha de examen."""
    for i, raw in enumerate(DENSITIES):
        doc = add_ready_doc(store, name=f"Prueba {i + 1}.pdf", lab_values=[value("Densidad de PSA", raw)] + (extra or []))
        store.update(doc["id"], created_at=f"2026-10-11T21:4{i}:00Z")


@pytest.fixture
def store(tmp_path):
    s = DocumentStore(tmp_path)
    upload_all(s)
    return s


@pytest.fixture
def settings(tmp_path):
    return Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)


class TestSharedOrdering:
    def test_oldest_first_puts_the_last_upload_at_the_end(self, store):
        rows = [dict(v, document_created_at=d["created_at"]) for d in store.list_all() for v in d["lab_values"]]
        assert [r["value_raw"] for r in oldest_first(rows)] == DENSITIES

    def test_the_exam_date_wins_over_the_upload_date(self):
        rows = [
            {"exam": "X", "value_raw": "1", "date": "2026-01-01", "document_created_at": "2026-10-12T00:00:00Z"},
            {"exam": "X", "value_raw": "2", "date": "2026-06-01", "document_created_at": "2026-10-01T00:00:00Z"},
        ]
        assert latest_per_exam(rows)["x"]["value_raw"] == "2"  # el examen más reciente, aunque se subió antes

    def test_the_same_lab_uploaded_twice_keeps_one_copy_in_the_newest_slot(self):
        rows = [
            {"exam": "Glucosa", "value_raw": "90", "unit": "mg/dL", "document_created_at": "2026-10-01T00:00:00Z"},
            {"exam": "GLUCOSA", "value_raw": "85", "unit": "mg/dL", "document_created_at": "2026-10-02T00:00:00Z"},
            {"exam": "Glucosa", "value_raw": "90", "unit": "mg/dL", "document_created_at": "2026-10-03T00:00:00Z"},
        ]
        assert [r["value_raw"] for r in drop_repeats(rows)] == ["85", "90"]


class TestEveryConsumerAgrees:
    def test_the_values_endpoint_lists_the_newest_last(self, store, settings):
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: {"id": "u", "email": "u@example.com"}
        try:
            rows = TestClient(app).get("/values").json()
        finally:
            app.dependency_overrides.clear()
        assert [r["value_raw"] for r in rows] == DENSITIES
        assert all(r["document_created_at"] for r in rows)

    def test_the_summary_sees_the_last_upload_as_current(self, store, settings):
        rows = [v for d in store.list_all() for v in [dict(x, document_created_at=d["created_at"], document_id=d["id"]) for x in d["lab_values"]]]
        matched = exam_summary.matching_rows(rows, "densidad de psa")
        assert [r["value_raw"] for r in matched] == DENSITIES
        block = exam_summary._data_block("Densidad de PSA", matched)
        current_lines = [line for line in block.splitlines() if "ACTUAL" in line]
        assert len(current_lines) == 1 and "0.142" in current_lines[0]
        assert "el ÚLTIMO es el resultado actual" in block

    def test_the_agent_tool_marks_only_the_last_upload_as_current(self, store, settings, tmp_path):
        tools = {t.name: t for t in build_tools(store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
        result = tools["get_exact_values"].invoke({"exam": "densidad de psa"})
        marked = [line for line in result.splitlines() if line.startswith("- ") and "<- ACTUAL" in line]
        assert len(marked) == 1 and ": 0.142" in marked[0]
        order = [line.split(": ")[1].split(" ")[0] for line in result.splitlines() if line.startswith("- ")]
        assert order == DENSITIES
        assert "ACTUAL" in result.splitlines()[0]  # la explicación va antes de la lista

    def test_the_classic_chat_table_marks_the_same_value(self, store):
        ready = [d for d in store.list_all() if d["status"] == "ready"]
        table, _ = chat.build_values_context(ready)
        current = [line for line in table.splitlines() if line.rstrip().endswith("| ACTUAL |")]
        assert len(current) == 1 and "| 0.142 |" in current[0]
        assert [line.split("|")[2].strip() for line in table.splitlines() if line.startswith("| Densidad")] == DENSITIES

    def test_each_exam_gets_its_own_current_value(self, tmp_path, settings):
        store = DocumentStore(tmp_path)
        upload_all(store, extra=[value("PLAQUETAS", "464", "10^3/µL")])
        tools = {t.name: t for t in build_tools(store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
        result = tools["get_exact_values"].invoke({"exam": ""})
        assert sum(1 for l in result.splitlines() if l.startswith("- ") and "<- ACTUAL" in l) == 2  # uno por examen
        assert result.count("PLAQUETAS: 464") == 1  # la misma plaqueta subida 5 veces sale una vez
