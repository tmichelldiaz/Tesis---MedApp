"""El asistente puede abrir un documento por su nombre ("cuéntame qué encontraste en Prueba x.pdf").

Antes no tenía ninguna herramienta para eso y respondía "no tengo la capacidad de abrir archivos"."""

import pytest

from app.agent.executor import EXECUTOR_SYSTEM
from app.agent.tools import build_tools
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.store import DocumentStore
from tests.test_chat import add_ready_doc

VALUES = [{
    "exam": "PIRADS", "value_raw": "4", "value_numeric": 4.0, "unit": None, "date": None,
    "reference_low": None, "reference_high": None, "reference_text": None,
}]


@pytest.fixture
def env(tmp_path):
    store = DocumentStore(tmp_path)
    ready = add_ready_doc(store, name="Prueba x.pdf", lab_values=VALUES)
    store.save_transcription(ready["id"], "## Resonancia\n\nLesión en zona periférica, PIRADS 4.")
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    tools = {t.name: t for t in build_tools(store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
    return store, lambda name="": tools["read_document"].invoke({"name": name})


def test_the_agent_has_the_tool_and_is_told_never_to_say_it_cannot_open_files():
    assert "read_document" in EXECUTOR_SYSTEM and "NUNCA digas que no puedes abrir" in EXECUTOR_SYSTEM


@pytest.mark.parametrize("asked", ["Prueba x.pdf", "prueba x", "PRUEBA X.PDF", "mi documento Prueba x"])
def test_finds_the_document_however_the_patient_writes_the_name(env, asked):
    result = env[1](asked)
    assert "Prueba x.pdf" in result and "PIRADS: 4" in result and "Lesión en zona periférica" in result


def test_an_unknown_name_lists_what_there_is(env):
    result = env[1]("otro.pdf")
    assert "No encontré" in result and "Prueba x.pdf" in result


def test_an_empty_name_reads_the_most_recent_document(env):
    store, read = env
    newer = add_ready_doc(store, name="Nueva.pdf", lab_values=[])
    store.update(newer["id"], created_at="2099-01-01T00:00:00+00:00")  # sin empates con el otro documento
    store.save_transcription(newer["id"], "## Nuevo\n\nTexto de la historia más reciente.")
    result = read()
    assert "Nueva.pdf" in result and "historia más reciente" in result and "Otros documentos" in result


def test_a_document_still_being_read_says_so(env):
    store, read = env
    doc = store.list_all()[0]
    store.update(doc["id"], status="processing")
    assert "todavía se está leyendo" in read("Prueba x.pdf")


class TestDocumentIsHandedToTheModel:
    """Aunque el modelo no use la herramienta (o venga de decir "no puedo abrir archivos" en la misma
    conversación), si el paso nombra un documento, su contenido va dentro del propio mensaje."""

    def sent(self, tmp_path, monkeypatch, question):
        from tests.test_agent_edit import ScriptedModel  # modelo simulado que registra lo que recibe
        from app.agent import executor

        seen = []

        class Spy(ScriptedModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                seen.append(str(messages[-1].content))
                return super()._generate(messages, stop, run_manager, **kwargs)

        monkeypatch.setattr(executor, "ChatOpenAI", lambda **kw: Spy(first_date="2099-01-01T10:00:00+00:00"))
        store = DocumentStore(tmp_path)
        ready = add_ready_doc(store, name="Prueba x.pdf", lab_values=VALUES)
        store.save_transcription(ready["id"], "## Resonancia\n\nPIRADS 4 en zona periférica.")
        settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
        executor.run_step(question, "user-1:hilo", store, CalendarStore(tmp_path), ProfileStore(tmp_path), settings)
        return seen[0]

    def test_a_named_document_arrives_with_its_content(self, tmp_path, monkeypatch):
        message = self.sent(tmp_path, monkeypatch, 'Contar qué hay en el documento "Prueba x.pdf"')
        assert "PIRADS 4 en zona periférica" in message and "PIRADS: 4" in message

    def test_the_latest_history_arrives_with_its_content(self, tmp_path, monkeypatch):
        message = self.sent(tmp_path, monkeypatch, "Resumir mi última historia")
        assert "PIRADS 4 en zona periférica" in message

    def test_a_question_about_no_document_is_left_alone(self, tmp_path, monkeypatch):
        message = self.sent(tmp_path, monkeypatch, "Buscar el valor más reciente de glucosa")
        assert "Contenido del documento" not in message


def test_no_documents_at_all(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    tools = {t.name: t for t in build_tools(DocumentStore(tmp_path), CalendarStore(tmp_path), ProfileStore(tmp_path), settings, None)}
    assert "todavía no ha subido" in tools["read_document"].invoke({"name": "x"})
