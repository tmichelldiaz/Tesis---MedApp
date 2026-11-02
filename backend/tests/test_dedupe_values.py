"""El mismo dato no se repite en la lista de valores de una historia."""

from app.extraction.lab_values import LabValue, dedupe_values


def value(exam, raw, unit=None, date=None, ref=None):
    return LabValue(exam=exam, value_raw=raw, value_numeric=None, unit=unit, date=date,
                    reference_low=None, reference_high=None, reference_text=ref)


def test_identical_values_appear_once_and_keep_their_order():
    out = dedupe_values([value("Densidad de PSA", "0.083"), value("PSA", "4"), value("Densidad de PSA", "0.083")])
    assert [(v.exam, v.value_raw) for v in out] == [("Densidad de PSA", "0.083"), ("PSA", "4")]


def test_spelling_differences_in_case_and_accents_still_count_as_the_same():
    assert len(dedupe_values([value("Puntuación ESUR", "5/5"), value("PUNTUACION ESUR", "5/5")])) == 1


def test_different_values_or_dates_are_kept():
    out = dedupe_values([
        value("PSA", "4", date="2026-01-01"), value("PSA", "4", date="2026-06-01"), value("PSA", "5", date="2026-01-01"),
    ])
    assert len(out) == 3
