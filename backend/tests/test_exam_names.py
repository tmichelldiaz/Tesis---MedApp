"""Un mismo examen se llama igual en todas las historias, sin mezclar medidas distintas.

Caso real: "Puntuación ESUR" en una historia e "Invasión extracapsular (ESUR)" en otra; al preguntar por el examen,
el asistente decía que no tenía valores previos aunque los tenía bajo otro nombre."""

import json
from collections import Counter

import pytest

from app.config import Settings
from app.extraction import exam_names
from app.extraction.exam_names import compatible, harmonize_exam_names, propose_mapping
from app.store import DocumentStore
from tests.test_chat import add_ready_doc


def value(exam, raw="1", unit=None):
    return {"exam": exam, "value_raw": raw, "value_numeric": float(raw), "unit": unit, "date": None,
            "reference_low": None, "reference_high": None, "reference_text": None}


class TestCompatible:
    @pytest.mark.parametrize("a, b", [
        ("Uretra membranosa", "Longitud de uretra membranosa"),
        ("Puntuación ESUR", "Puntuación ESUR (invasión extracapsular)"),
        ("Invasión extracapsular (ESUR)", "Puntuación ESUR invasión extracapsular"),
    ])
    def test_the_same_measure_written_differently(self, a, b):
        assert compatible(a, b)

    @pytest.mark.parametrize("a, b", [
        ("LINFOCITOS", "LINFOCITOS %"),
        ("Lóbulo derecho", "Lóbulo izquierdo"),
        ("Área de lesión (largo)", "Área de lesión (ancho)"),
        ("PIRADS lesión 1", "PIRADS lesión 2"),
        ("BILIRRUBINA DIRECTA", "BILIRRUBINA INDIRECTA"),
        ("CREATININA EN ORINA", "CREATININA EN SUERO"),
    ])
    def test_different_measures_are_never_joined(self, a, b):
        assert not compatible(a, b)


def fake_model(monkeypatch, groups):
    monkeypatch.setattr(exam_names, "chat_completion", lambda *a, **k: json.dumps({"groups": groups}))


@pytest.fixture
def settings(tmp_path):
    return Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)


class TestMapping:
    NAMES = Counter({"Puntuación ESUR": 3, "Invasión extracapsular (ESUR)": 2, "LINFOCITOS": 2, "LINFOCITOS %": 2})

    def test_valid_groups_become_a_mapping(self, monkeypatch, settings):
        fake_model(monkeypatch, [{"canonical": "Puntuación ESUR", "variants": ["Puntuación ESUR", "Invasión extracapsular (ESUR)"]}])
        assert propose_mapping(self.NAMES, {}, settings) == {"Invasión extracapsular (ESUR)": "Puntuación ESUR"}

    def test_a_dangerous_union_proposed_by_the_model_is_dropped(self, monkeypatch, settings):
        fake_model(monkeypatch, [{"canonical": "LINFOCITOS", "variants": ["LINFOCITOS %"]}])
        assert propose_mapping(self.NAMES, {}, settings) == {}

    def test_invented_names_are_ignored(self, monkeypatch, settings):
        fake_model(monkeypatch, [{"canonical": "Nombre inventado", "variants": ["Puntuación ESUR"]},
                                 {"canonical": "Puntuación ESUR", "variants": ["Otro inventado"]}])
        assert propose_mapping(self.NAMES, {}, settings) == {}

    def test_units_copied_into_the_names_are_ignored(self, monkeypatch, settings):
        names = Counter({"Longitud de uretra membranosa": 7, "Uretra membranosa": 3})
        units = {"Longitud de uretra membranosa": "cm", "Uretra membranosa": "cm"}
        fake_model(monkeypatch, [{"canonical": "Longitud de uretra membranosa [cm]",
                                  "variants": ["Longitud de uretra membranosa [cm]", "Uretra membranosa [cm]"]}])
        assert propose_mapping(names, units, settings) == {"Uretra membranosa": "Longitud de uretra membranosa"}

    def test_the_same_name_in_cm_and_in_mm_is_not_joined(self, monkeypatch, settings):
        names = Counter({"Protrusión en suelo vesical": 4, "Protrusión en la vejiga": 2})
        units = {"Protrusión en suelo vesical": "cm", "Protrusión en la vejiga": "mm"}
        fake_model(monkeypatch, [{"canonical": "Protrusión en suelo vesical", "variants": ["Protrusión en la vejiga"]}])
        assert propose_mapping(names, units, settings) == {}

    def test_garbage_from_the_model_changes_nothing(self, monkeypatch, settings):
        monkeypatch.setattr(exam_names, "chat_completion", lambda *a, **k: "no es json")
        assert propose_mapping(self.NAMES, {}, settings) == {}


def test_names_are_unified_across_all_histories(tmp_path, monkeypatch, settings):
    store = DocumentStore(tmp_path)
    first = add_ready_doc(store, name="a.pdf", lab_values=[value("Puntuación ESUR", "1"), value("PSA", "4")])
    second = add_ready_doc(store, name="b.pdf", lab_values=[value("Invasión extracapsular (ESUR)", "2"), value("PSA", "5")])
    fake_model(monkeypatch, [{"canonical": "Puntuación ESUR", "variants": ["Invasión extracapsular (ESUR)"]}])
    changed = harmonize_exam_names(store, settings)
    assert changed == {"Invasión extracapsular (ESUR)": "Puntuación ESUR"}
    names = {d["id"]: [v["exam"] for v in d["lab_values"]] for d in store.list_all()}
    assert names[second["id"]] == ["Puntuación ESUR", "PSA"] and names[first["id"]] == ["Puntuación ESUR", "PSA"]
    # los números no se tocan
    assert [v["value_raw"] for v in store.get(second["id"])["lab_values"]] == ["2", "5"]


def test_a_dry_run_changes_nothing(tmp_path, monkeypatch, settings):
    store = DocumentStore(tmp_path)
    add_ready_doc(store, name="a.pdf", lab_values=[value("Puntuación ESUR")])
    second = add_ready_doc(store, name="b.pdf", lab_values=[value("Invasión extracapsular (ESUR)")])
    fake_model(monkeypatch, [{"canonical": "Puntuación ESUR", "variants": ["Invasión extracapsular (ESUR)"]}])
    assert harmonize_exam_names(store, settings, dry_run=True)
    assert store.get(second["id"])["lab_values"][0]["exam"] == "Invasión extracapsular (ESUR)"
