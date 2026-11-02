"""La memoria a largo plazo del agente es información de salud del paciente: tiene
que poder verse, borrarse de a una y desaparecer entera al borrar la cuenta."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

import app.agent.memory as memory
from app.agent import planning
from app.agent.memory import delete_user_memory, forget, list_memories, memory_namespace, recall
from tests.test_extraction import make_settings


def remember(store, user_id, text, key=None):
    store.put(memory_namespace(user_id), key or text[:8], {"recuerdo": text})


class TestListAndForget:
    def test_lists_only_this_patients_memories_with_ids(self):
        store = InMemoryStore()
        remember(store, "7", "alérgico a la penicilina", "a1")
        remember(store, "8", "toma losartán", "b1")
        assert list_memories(store, "7") == [{"id": "a1", "text": "alérgico a la penicilina"}]

    def test_forget_removes_one_memory(self):
        store = InMemoryStore()
        remember(store, "7", "alérgico a la penicilina", "a1")
        remember(store, "7", "toma losartán", "a2")
        assert forget(store, "7", "a1") is True
        assert recall(store, "7") == ["toma losartán"]

    def test_a_patient_cannot_forget_someone_elses_memory(self):
        store = InMemoryStore()
        remember(store, "8", "toma losartán", "b1")
        assert forget(store, "7", "b1") is False
        assert recall(store, "8") == ["toma losartán"]


class TestAccountDeletion:
    def test_erases_memories_and_conversations_of_that_patient_only(self, monkeypatch):
        store, saver = InMemoryStore(), InMemorySaver()
        monkeypatch.setattr(memory, "get_store", lambda url: store)
        monkeypatch.setattr(memory, "get_checkpointer", lambda url: saver)
        for i in range(250):  # más de una página de borrado
            remember(store, "7", f"dato {i}", f"k{i}")
        remember(store, "8", "toma losartán", "b1")
        for thread in ("7:conv-1", "7:conv-2", "8:conv-1"):
            saver.storage[thread]  # el defaultdict crea la entrada del hilo

        delete_user_memory("postgresql://x", "7")

        assert recall(store, "7", limit=1000) == []
        assert recall(store, "8") == ["toma losartán"]
        assert [t for t in saver.storage if str(t).startswith("7:")] == []
        assert "8:conv-1" in saver.storage

    def test_a_failure_is_not_swallowed(self, monkeypatch):
        class Broken(InMemoryStore):
            def search(self, *args, **kwargs):
                raise RuntimeError("base caída")

        monkeypatch.setattr(memory, "get_store", lambda url: Broken())
        monkeypatch.setattr(memory, "get_checkpointer", lambda url: InMemorySaver())
        try:
            delete_user_memory("postgresql://x", "7")
        except RuntimeError:
            return
        raise AssertionError("debió propagar el error para que la cuenta no se borre")


class TestPlannerAndSynthesizerSeeMemories:
    def capture(self, monkeypatch):
        seen = []

        def fake(model, mode, messages, settings, client, response_format=None):
            seen.append(messages[1]["content"])
            return '{"steps": ["Buscar"]}' if response_format else "Respuesta"

        monkeypatch.setattr(planning, "chat_completion", fake)
        return seen

    def test_planner_gets_the_memories(self, monkeypatch):
        seen = self.capture(monkeypatch)
        planning.plan("¿qué puedo tomar para el dolor?", None, make_settings(), memories=["alérgico a la penicilina"])
        assert "alérgico a la penicilina" in seen[0]

    def test_synthesizer_gets_the_memories(self, monkeypatch):
        seen = self.capture(monkeypatch)
        planning.synthesize("pregunta", [("paso", "resultado")], make_settings(), memories=["alérgico a la penicilina"])
        assert "alérgico a la penicilina" in seen[0]

    def test_without_memories_the_prompt_is_unchanged(self, monkeypatch):
        seen = self.capture(monkeypatch)
        planning.plan("hola", None, make_settings())
        assert "recordar" not in seen[0]
