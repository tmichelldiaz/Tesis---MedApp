"""El valor se guarda solo ("2"), sin el nombre del examen pegado ("PIRADS 2")."""

import pytest

from app.extraction.lab_values import _entry, strip_exam_prefix


@pytest.mark.parametrize("raw, exam, expected", [
    ("PIRADS 2", "PIRADS", "2"),
    ("PIRADS: 4", "Pirads", "4"),
    ("PI-RADS 3", "PIRADS", "3"),
    ("Pirads 1 y 2", "PIRADS", "1 y 2"),
    ("Glucosa 94", "Glucosa en ayunas", "Glucosa 94"),  # no es el nombre completo: se deja
    ("94", "Glucosa", "94"),
    ("PIRADS", "PIRADS", "PIRADS"),  # el valor es el nombre: no queda nada, se deja
    ("Negativo", "VIH", "Negativo"),
])
def test_strip_exam_prefix(raw, exam, expected):
    assert strip_exam_prefix(raw, exam) == expected


def test_entry_applies_it():
    value = _entry({"exam": "PIRADS", "value_raw": "PIRADS 2", "value_numeric": 2, "unit": None})
    assert value.value_raw == "2"
