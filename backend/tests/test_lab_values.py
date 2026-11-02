import json

import httpx
import pytest

from app.config import Settings
from app.extraction.lab_values import LabValue, extract_values, parse_values
from app.extraction.vision_client import VisionError

GOOD_JSON = json.dumps([
    {
        "exam": "Glucosa en ayunas", "value_raw": "94", "value_numeric": 94,
        "unit": "mg/dL", "date": "2026-03-10",
        "reference_low": 70, "reference_high": 100, "reference_text": "70 - 100",
    },
    {
        "exam": "Alergias", "value_raw": "Penicilina", "value_numeric": None,
        "unit": None, "date": None, "reference_low": None, "reference_high": None,
        "reference_text": None,
    },
])


def make_settings(**kw) -> Settings:
    return Settings(openrouter_api_key="k", retry_min_wait_s=0, retry_max_wait_s=0, _env_file=None, **kw)


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class TestParseValues:
    def test_parses_a_well_formed_array(self):
        values = parse_values(GOOD_JSON)
        assert len(values) == 2
        assert values[0] == LabValue(
            exam="Glucosa en ayunas", value_raw="94", value_numeric=94.0, unit="mg/dL",
            date="2026-03-10", reference_low=70.0, reference_high=100.0, reference_text="70 - 100",
        )
        assert values[1].value_numeric is None and values[1].unit is None

    def test_strips_code_fence(self):
        assert len(parse_values(f"```json\n{GOOD_JSON}\n```")) == 2

    def test_empty_array_is_fine(self):
        assert parse_values("[]") == []

    def test_garbage_becomes_empty_list_not_an_error(self):
        assert parse_values("no soy json") == []
        assert parse_values('{"exam": "no es un array"}') == []

    def test_drops_entries_missing_required_fields(self):
        bad = json.dumps([{"exam": "Glucosa"}, {"value_raw": "94"}, {}])
        assert parse_values(bad) == []

    def test_ignores_invalid_date_instead_of_crashing(self):
        raw = json.dumps([{"exam": "Glucosa", "value_raw": "94", "date": "10 de marzo"}])
        assert parse_values(raw)[0].date is None

    def test_numeric_fields_accept_comma_decimal(self):
        raw = json.dumps([{"exam": "Creatinina", "value_raw": "0,9", "value_numeric": "0,9"}])
        assert parse_values(raw)[0].value_numeric == 0.9

    def test_truncates_overlong_text_fields(self):
        raw = json.dumps([{"exam": "x" * 500, "value_raw": "y" * 200}])
        entry = parse_values(raw)[0]
        assert len(entry.exam) == 120 and len(entry.value_raw) == 80

    def test_to_dict_roundtrips(self):
        value = parse_values(GOOD_JSON)[0]
        assert value.to_dict()["exam"] == "Glucosa en ayunas"

    @pytest.mark.parametrize("exam", [
        "Paciente", "Nombre", "Orden No", "Historia", "Fecha de Nacimiento",
        "Tipo Identificación", "Edad", "Fecha y Hora de Ingreso", "Fuerza",
        "Fecha de Impresión", "Sede", "Médico", "Servicio", "Procedencia",
        "EPS", "PACIENTE",  # insensible a mayúsculas y a tildes
    ])
    def test_drops_patient_identification_and_administrative_noise(self, exam):
        raw = json.dumps([{"exam": exam, "value_raw": "algo"}])
        assert parse_values(raw) == []

    def test_keeps_real_clinical_values_alongside_dropped_noise(self):
        raw = json.dumps([
            {"exam": "Paciente", "value_raw": "Jennifer Suarez"},
            {"exam": "Glucosa en ayunas", "value_raw": "94"},
            {"exam": "Fecha de Impresión", "value_raw": "31/8/2026"},
        ])
        assert [v.exam for v in parse_values(raw)] == ["Glucosa en ayunas"]


class TestExtractValues:
    def test_empty_markdown_short_circuits_without_a_call(self):
        assert extract_values("   ", make_settings()) == []

    def test_happy_path(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok(GOOD_JSON))

        values = extract_values("# Doc\n\n| Glucosa | 94 |", make_settings(), client_for(handler))
        assert len(values) == 2
        assert seen[0]["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert seen[0]["messages"][1]["content"] == "# Doc\n\n| Glucosa | 94 |"

    def test_falls_back_on_rate_limit(self):
        seen = []

        def handler(request):
            model = json.loads(request.read())["model"]
            seen.append(model)
            if model == "primario":
                return httpx.Response(429, json={"error": {"message": "x"}})
            return httpx.Response(200, json=ok("[]"))

        settings = make_settings(values_model="primario", values_fallback_model="respaldo")
        extract_values("# Doc", settings, client_for(handler))
        assert seen[0] == "primario" and seen[-1] == "respaldo"

    def test_raises_on_non_transient_error(self):
        handler = lambda request: httpx.Response(401, json={"error": {"message": "bad key"}})
        with pytest.raises(VisionError, match="401"):
            extract_values("# Doc", make_settings(), client_for(handler))

    def test_malformed_model_output_yields_empty_list_not_an_error(self):
        handler = lambda request: httpx.Response(200, json=ok("claro, aquí están tus datos: ..."))
        assert extract_values("# Doc", make_settings(), client_for(handler)) == []

    def test_requests_json_object_response_format(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.read()))
            return httpx.Response(200, json=ok('{"values": []}'))

        extract_values("# Doc", make_settings(), client_for(handler))
        assert seen[0]["response_format"] == {"type": "json_object"}

    def test_multi_section_document_makes_one_call_per_section_and_merges(self):
        md = (
            "# Informe\n\n## Hematología\n\n| Hemoglobina | 15 |\n\n"
            "## Química\n\n| Glucosa | 94 |\n"
        )
        calls = []

        def handler(request):
            body = json.loads(request.read())
            content = body["messages"][1]["content"]
            calls.append(content)
            if "Hemoglobina" in content:
                return httpx.Response(200, json=ok(
                    '{"values": [{"exam": "Hemoglobina", "value_raw": "15"}]}'
                ))
            return httpx.Response(200, json=ok(
                '{"values": [{"exam": "Glucosa", "value_raw": "94"}]}'
            ))

        values = extract_values(md, make_settings(), client_for(handler))
        assert len(calls) == 2  # una llamada por sección, no una gigante
        assert [v.exam for v in values] == ["Hemoglobina", "Glucosa"]

    def test_a_single_section_with_no_valid_values_does_not_block_the_rest(self):
        md = "# Informe\n\n## Vacía\n\nsin datos aquí\n\n## Química\n\n| Glucosa | 94 |\n"

        def handler(request):
            body = json.loads(request.read())
            content = body["messages"][1]["content"]
            if "Glucosa" in content:
                return httpx.Response(200, json=ok('{"values": [{"exam": "Glucosa", "value_raw": "94"}]}'))
            return httpx.Response(200, json=ok('{"values": []}'))

        values = extract_values(md, make_settings(), client_for(handler))
        assert [v.exam for v in values] == ["Glucosa"]

    def test_model_returning_a_bare_object_instead_of_a_list_is_still_accepted(self):
        raw = '{"values": {"exam": "Glucosa", "value_raw": "94"}}'
        assert [v.exam for v in parse_values(raw)] == ["Glucosa"]

    def test_retries_once_when_the_model_replies_with_non_empty_prose_instead_of_json(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json=ok(
                    "Claro, aquí tienes los valores que encontré en el documento: Glucosa 94 mg/dL..."
                ))
            return httpx.Response(200, json=ok('{"values": [{"exam": "Glucosa", "value_raw": "94"}]}'))

        values = extract_values("# Doc\n\n| Glucosa | 94 |", make_settings(), client_for(handler))
        assert calls["n"] == 2
        assert [v.exam for v in values] == ["Glucosa"]

    def test_a_short_empty_result_is_accepted_immediately_without_retrying(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=ok('{"values": []}'))

        assert extract_values("# Doc sin datos", make_settings(), client_for(handler)) == []
        assert calls["n"] == 1  # no vale la pena reintentar algo que ya es válido y vacío
