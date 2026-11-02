"""El procesamiento de un documento debe correr sus llamadas independientes a la
vez (páginas, secciones de valores, valores + categoría) sin cambiar el
resultado ni el orden. La prueba usa una barrera: solo se abre si las llamadas
están realmente en vuelo al mismo tiempo, así que en serie falla."""
import json
import threading

import httpx

from app.extraction import vision_client
from app.extraction.lab_values import extract_values
from app.extraction.to_markdown import convert
from tests.test_extraction import make_pdf, make_settings
from tests.test_lab_values import client_for, ok


def test_pages_are_transcribed_at_the_same_time_and_keep_their_order():
    barrier = threading.Barrier(3, timeout=5)

    def fake(batch, settings):
        barrier.wait()  # las 3 páginas tienen que estar dentro a la vez
        out = vision_client.Transcription(f"texto de la página {batch[0].index}")
        out.model, out.mode = "m", "text"
        return out

    result = convert(make_pdf(3), make_settings(parallel_workers=3), transcriber=fake)
    positions = [result.markdown.index(f"texto de la página {i}") for i in (1, 2, 3)]
    assert positions == sorted(positions)
    assert result.page_count == 3


def test_a_failing_page_still_fails_the_document():
    def fake(batch, settings):
        if batch[0].index == 2:
            raise vision_client.VisionError("falló la página 2")
        return vision_client.Transcription("ok")

    import pytest

    with pytest.raises(vision_client.VisionError, match="página 2"):
        convert(make_pdf(3), make_settings(parallel_workers=3), transcriber=fake)


def test_sections_are_extracted_at_the_same_time_and_merged_in_order():
    md = (
        "# Informe\n\n## Hematología\n\n| Hemoglobina | 15 |\n\n"
        "## Química\n\n| Glucosa | 94 |\n\n## Lípidos\n\n| Colesterol | 190 |\n"
    )
    barrier = threading.Barrier(3, timeout=5)

    def handler(request):
        content = json.loads(request.read())["messages"][1]["content"]
        barrier.wait()
        exam = next(e for e in ("Hemoglobina", "Glucosa", "Colesterol") if e in content)
        return httpx.Response(200, json=ok(json.dumps({"values": [{"exam": exam, "value_raw": "1"}]})))

    values = extract_values(md, make_settings(parallel_workers=3), client_for(handler))
    assert [v.exam for v in values] == ["Hemoglobina", "Glucosa", "Colesterol"]


def test_serial_is_still_the_default():
    assert make_settings().parallel_workers == 1
