import httpx

from app.agent.tools import WRITE_TOOLS, build_tools
from app.calendar_store import CalendarStore
from app.config import Settings
from app.profile_store import ProfileStore
from app.store import DocumentStore


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None, **kw)


def make_tools(tmp_path, client=None):
    store = DocumentStore(tmp_path)
    calendar = CalendarStore(tmp_path)
    profile = ProfileStore(tmp_path)
    settings = make_settings(tmp_path)
    tools = {t.name: t for t in build_tools(store, calendar, profile, settings, client)}
    return tools, store, calendar, profile


def add_ready_doc(store, lab_values=None):
    from app.okf.builder import build_bundle, write_bundle

    meta = store.create("informe.pdf", b"%PDF-1.4 x", "pdf")
    bundle = build_bundle("# Doc\n\ncuerpo\n", "informe.pdf", "m", page_count=1, document_id=meta["id"], source_format="pdf")
    store.ensure_historia_slug(meta["id"])
    write_bundle(bundle, store.bundle_dir(meta["id"]))
    return store.update(meta["id"], status="ready", concepts=[], lab_values=lab_values or [])


GLUCOSA = {
    "exam": "Glucosa", "value_raw": "94", "value_numeric": 94.0, "unit": "mg/dL",
    "date": "2026-03-10", "reference_low": 70.0, "reference_high": 100.0, "reference_text": "70 - 100",
}


class TestWriteTools:
    def test_write_tools_are_exactly_the_ones_that_change_data(self, tmp_path):
        tools, *_ = make_tools(tmp_path)
        assert WRITE_TOOLS == {"create_appointment", "save_question_for_doctor", "remember_fact"}
        assert WRITE_TOOLS.issubset(tools.keys())


class TestRememberFact:
    def test_saves_a_fact_under_the_patients_namespace(self, tmp_path):
        from langgraph.store.memory import InMemoryStore

        long_term = InMemoryStore()
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        profile = ProfileStore(tmp_path)
        settings = make_settings(tmp_path)
        tools = {
            t.name: t
            for t in build_tools(store, calendar, profile, settings, None, long_term, "paciente-1")
        }

        result = tools["remember_fact"].invoke({"fact": "Es alérgico a la penicilina."})
        assert "Guardado" in result
        saved = long_term.search(("memoria", "paciente-1"))
        assert len(saved) == 1 and saved[0].value["recuerdo"] == "Es alérgico a la penicilina."

    def test_reports_unavailable_without_a_long_term_store(self, tmp_path):
        tools, *_ = make_tools(tmp_path)
        result = tools["remember_fact"].invoke({"fact": "x"})
        assert "no está disponible" in result


class TestGetExactValues:
    def test_returns_a_message_when_the_patient_has_no_values(self, tmp_path):
        tools, *_ = make_tools(tmp_path)
        result = tools["get_exact_values"].invoke({"exam": ""})
        assert "no tiene" in result.lower()

    def test_returns_matching_values(self, tmp_path):
        tools, store, *_ = make_tools(tmp_path)
        add_ready_doc(store, lab_values=[GLUCOSA])
        result = tools["get_exact_values"].invoke({"exam": "glucosa"})
        assert "94" in result and "mg/dL" in result

    def test_filters_out_unrelated_exams(self, tmp_path):
        tools, store, *_ = make_tools(tmp_path)
        colesterol = {**GLUCOSA, "exam": "Colesterol", "value_raw": "200"}
        add_ready_doc(store, lab_values=[GLUCOSA, colesterol])
        result = tools["get_exact_values"].invoke({"exam": "colesterol"})
        assert "Colesterol" in result and "Glucosa" not in result


class TestSearchNarrativeHistory:
    def test_returns_a_message_when_nothing_is_indexed(self, tmp_path):
        # embed() siempre llama al modelo para vectorizar la pregunta, incluso
        # sin nada que comparar, así que hay que simularlo para no pegarle a
        # la red real en un test que debería ser instantáneo.
        handler = lambda request: httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0], "index": 0}]})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        tools, *_ = make_tools(tmp_path, client=client)
        result = tools["search_narrative_history"].invoke({"query": "diagnóstico"})
        assert "no se encontró" in result.lower()


class TestListAppointments:
    def test_returns_a_message_when_there_are_none(self, tmp_path):
        tools, *_ = make_tools(tmp_path)
        assert "no tiene citas" in tools["list_appointments"].invoke({}).lower()

    def test_lists_appointments_with_pending_questions(self, tmp_path):
        tools, _, calendar, _ = make_tools(tmp_path)
        appt = calendar.create_appointment(title="Cardiología", scheduled_at="2099-10-15T09:00:00Z", doctor_name="Dra. Ríos")
        calendar.create_question("¿Debo ayunar?", appointment_id=appt["id"])
        result = tools["list_appointments"].invoke({})
        assert "Cardiología" in result and "Dra. Ríos" in result and "¿Debo ayunar?" in result


class TestCreateAppointment:
    def test_creates_an_appointment_and_it_is_persisted(self, tmp_path):
        tools, _, calendar, _ = make_tools(tmp_path)
        result = tools["create_appointment"].invoke({
            "title": "Cardiología", "scheduled_at": "2099-10-15T09:00:00Z",
        })
        assert "Cita creada" in result
        assert len(calendar.list_appointments()) == 1


class TestSaveQuestionForDoctor:
    def test_saves_a_standalone_question(self, tmp_path):
        tools, _, calendar, _ = make_tools(tmp_path)
        result = tools["save_question_for_doctor"].invoke({"text": "¿Y mi colesterol?", "appointment_id": ""})
        assert "guardada" in result.lower()
        questions = calendar.list_questions()
        assert len(questions) == 1 and questions[0]["appointment_id"] is None

    def test_links_a_question_to_a_real_appointment(self, tmp_path):
        tools, _, calendar, _ = make_tools(tmp_path)
        appt = calendar.create_appointment(title="Control", scheduled_at="2099-10-15T09:00:00Z")
        result = tools["save_question_for_doctor"].invoke({"text": "¿Y mi colesterol?", "appointment_id": appt["id"]})
        assert "guardada" in result.lower()
        assert calendar.list_questions(appointment_id=appt["id"])[0]["text"] == "¿Y mi colesterol?"

    def test_reports_when_the_appointment_does_not_exist(self, tmp_path):
        tools, *_ = make_tools(tmp_path)
        result = tools["save_question_for_doctor"].invoke({"text": "¿?", "appointment_id": "no-existe"})
        assert "no se encontr" in result.lower()


class TestGetProfile:
    def test_returns_a_message_when_the_profile_is_empty(self, tmp_path):
        tools, *_ = make_tools(tmp_path)
        assert "no ha completado" in tools["get_profile"].invoke({}).lower()

    def test_returns_the_filled_fields(self, tmp_path):
        tools, _, _, profile = make_tools(tmp_path)
        profile.update(name="Jennifer", weight_kg=62.5, blood_type="O+")
        result = tools["get_profile"].invoke({})
        assert "Jennifer" in result and "62.5" in result and "O+" in result
