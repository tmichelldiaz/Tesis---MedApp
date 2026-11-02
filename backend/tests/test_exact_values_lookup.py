"""La búsqueda de valores exactos del agente con nombres de examen reales de un laboratorio
(en mayúsculas, a veces con tildes, a veces sin ellas) y con las formas en que un paciente
los nombra. Antes solo comparaba el texto tal cual: "linfocitos más reciente" o "HbA1c" no
encontraban nada y el asistente decía que no tenía el dato."""

import pytest

from app.agent.tools import _match_exam_rows, _norm, build_tools
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.store import DocumentStore
from tests.test_chat import add_ready_doc


def value(exam, raw, unit="", ref="s/d"):
    return {
        "exam": exam, "value_raw": raw, "value_numeric": None, "unit": unit, "date": None,
        "reference_low": None, "reference_high": None, "reference_text": ref,
    }


LAB = [
    value("LINFOCITOS", "3.86", "10^3/µL", "0.90 - 5.20"),
    value("LINFOCITOS %", "34.0", "%", "20 - 45"),
    value("BASÓFILOS %", "0.4", "%"),
    value("HEMOGLOBINA", "13.2", "g/dL"),
    value("HEMOGLOBINA GLICOSILADA", "5.8", "%"),
    value("HEMOGLOBINA CORPUSCULAR MEDIA", "26.7", "pg"),
    value("VOLUMEN CORPUSCULAR MEDIO", "79.7", "fL", "80 - 100"),
    value("VOLUMEN MEDIO PLAQUETARIO", "9.1", "fL"),
    value("RECUENTO DE GLOBULOS BLANCOS", "11.34", "10^3/µL"),
    value("COLESTEROL DE BAJA DENSIDAD LDL COLESTEROL DE BAJA DENSIDAD LDL", "131", "mg/dL"),
    value("HORMONA ESTIMULANTE DEL TIROIDES ULTRASENSIBLE", "5.8", "mUI/L"),
    value("PLAQUETAS", "464", "10^3/µL"),
]


@pytest.fixture
def get_values(tmp_path):
    store = DocumentStore(tmp_path)
    add_ready_doc(store, lab_values=LAB)
    add_ready_doc(store, name="repetido.pdf", lab_values=LAB)  # el mismo laboratorio subido dos veces
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    tools = {t.name: t for t in build_tools(store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
    return lambda exam="": tools["get_exact_values"].invoke({"exam": exam})


class TestNormalize:
    def test_ignores_case_accents_and_signs(self):
        assert _norm("  Glóbulos   BLANCOS! ") == "globulos blancos"
        assert _norm("BASÓFILOS %") == "basofilos %"


class TestFinding:
    @pytest.mark.parametrize("asked", [
        "linfocitos", "Linfocitos", "LINFOCITOS", "linfocitos más reciente", "mi resultado de linfocitos",
    ])
    def test_finds_lymphocytes_however_it_is_asked(self, get_values, asked):
        result = get_values(asked)
        assert "LINFOCITOS: 3.86" in result and "LINFOCITOS %: 34.0" in result

    def test_accents_do_not_matter(self, get_values):
        assert "BASÓFILOS %: 0.4" in get_values("basofilos")
        assert "BASÓFILOS %: 0.4" in get_values("basófilos")

    @pytest.mark.parametrize("asked, expected", [
        ("HbA1c", "HEMOGLOBINA GLICOSILADA: 5.8"),
        ("hemoglobina glicosilada", "HEMOGLOBINA GLICOSILADA: 5.8"),
        ("LDL", "LDL"),
        ("tsh", "HORMONA ESTIMULANTE DEL TIROIDES ULTRASENSIBLE: 5.8"),
        ("glóbulos blancos", "RECUENTO DE GLOBULOS BLANCOS: 11.34"),
        ("leucocitos", "RECUENTO DE GLOBULOS BLANCOS: 11.34"),
        ("vcm", "VOLUMEN CORPUSCULAR MEDIO: 79.7"),
    ])
    def test_finds_by_the_abbreviations_patients_use(self, get_values, asked, expected):
        assert expected in get_values(asked)

    def test_a_specific_name_does_not_pull_in_a_similar_one(self, get_values):
        result = get_values("volumen corpuscular medio")
        assert "VOLUMEN CORPUSCULAR MEDIO: 79.7" in result
        assert "PLAQUETARIO" not in result

    def test_hemoglobin_alone_matches_all_hemoglobin_exams(self, get_values):
        result = get_values("hemoglobina")
        assert "HEMOGLOBINA: 13.2" in result and "GLICOSILADA" in result and "CORPUSCULAR" in result

    def test_no_filter_returns_everything(self, get_values):
        assert "PLAQUETAS: 464" in get_values("") and "LINFOCITOS: 3.86" in get_values("")


class TestOutput:
    def test_the_same_lab_uploaded_twice_is_not_repeated(self, get_values):
        assert get_values("plaquetas").count("PLAQUETAS: 464") == 1

    def test_an_unknown_exam_tells_the_model_what_does_exist(self, get_values):
        result = get_values("zinc")
        assert "No se encontraron valores para 'zinc'" in result
        assert "LINFOCITOS" in result and "PLAQUETAS" in result  # para que pueda elegir bien

    def test_without_any_values_it_says_so(self, tmp_path):
        store = DocumentStore(tmp_path)
        settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
        tools = {t.name: t for t in build_tools(store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
        assert "todavía no tiene valores" in tools["get_exact_values"].invoke({"exam": "glucosa"})

    def test_a_very_long_list_is_capped_keeping_the_latest(self, tmp_path):
        store = DocumentStore(tmp_path)
        many = [value("GLUCOSA", str(90 + i), "mg/dL") for i in range(40)]
        for i, row in enumerate(many):
            row["date"] = f"2026-01-{i + 1:02d}"
        add_ready_doc(store, lab_values=many)
        settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
        tools = {t.name: t for t in build_tools(store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
        result = tools["get_exact_values"].invoke({"exam": "glucosa"})
        assert "GLUCOSA: 129" in result and "y 10 valores más antiguos" in result


def test_matcher_returns_nothing_for_a_blank_unmatched_query():
    assert _match_exam_rows([({}, {"exam": "PLAQUETAS"})], "zzz") == []
