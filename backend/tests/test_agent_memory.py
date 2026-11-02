from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.agent import memory


class TestFallbackWithoutPostgres:
    def test_checkpointer_falls_back_to_in_memory_without_a_database_url(self):
        assert isinstance(memory.get_checkpointer(""), InMemorySaver)

    def test_store_falls_back_to_in_memory_without_a_database_url(self):
        assert isinstance(memory.get_store(""), InMemoryStore)

    def test_falls_back_when_the_url_is_not_a_reachable_postgres(self):
        # Cadena con la forma correcta pero un host que no existe: debe caer
        # de vuelta a memoria en vez de tumbar la app.
        bad_url = "postgresql+psycopg://user:pass@host-que-no-existe.invalid:5432/db"
        assert isinstance(memory.get_checkpointer(bad_url), InMemorySaver)
        assert isinstance(memory.get_store(bad_url), InMemoryStore)


class TestRecall:
    def test_recall_returns_saved_facts(self):
        store = InMemoryStore()
        store.put(memory.memory_namespace("paciente-1"), key="a", value={"recuerdo": "Alergia al maní"})
        assert memory.recall(store, "paciente-1") == ["Alergia al maní"]

    def test_recall_is_empty_for_a_patient_with_no_memories(self):
        store = InMemoryStore()
        assert memory.recall(store, "paciente-sin-recuerdos") == []
