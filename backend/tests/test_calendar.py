import pytest
from fastapi.testclient import TestClient

from app.calendar_store import CalendarStore
from app.config import Settings
from app.main import app, get_calendar, get_settings


# ---------------------------------------------------------------------------
# CalendarStore (unit)
# ---------------------------------------------------------------------------

class TestCalendarStoreAppointments:
    def test_starts_empty(self, tmp_path):
        store = CalendarStore(tmp_path)
        assert store.list_appointments() == []

    def test_create_returns_full_appointment_with_generated_fields(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control anual", scheduled_at="2026-10-01T09:00:00Z")
        assert appt["title"] == "Control anual"
        assert appt["scheduled_at"] == "2026-10-01T09:00:00Z"
        assert appt["doctor_name"] is None
        assert appt["id"]
        assert appt["created_at"] and appt["updated_at"]

    def test_create_persists_optional_fields(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(
            title="Cardiología",
            scheduled_at="2026-10-01T09:00:00Z",
            doctor_name="Dra. Ríos",
            location="Consultorio 4",
            notes="Llevar exámenes previos",
        )
        assert appt["doctor_name"] == "Dra. Ríos"
        assert appt["location"] == "Consultorio 4"
        assert appt["notes"] == "Llevar exámenes previos"

    def test_list_is_sorted_by_scheduled_at(self, tmp_path):
        store = CalendarStore(tmp_path)
        store.create_appointment(title="Tarde", scheduled_at="2026-12-01T09:00:00Z")
        store.create_appointment(title="Temprano", scheduled_at="2026-10-01T09:00:00Z")
        titles = [a["title"] for a in store.list_appointments()]
        assert titles == ["Temprano", "Tarde"]

    def test_survives_reopening_the_same_directory(self, tmp_path):
        CalendarStore(tmp_path).create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        reopened = CalendarStore(tmp_path)
        assert len(reopened.list_appointments()) == 1

    def test_get_returns_none_for_unknown_id(self, tmp_path):
        store = CalendarStore(tmp_path)
        assert store.get_appointment("no-existe") is None

    def test_update_merges_fields_and_touches_updated_at(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        updated = store.update_appointment(appt["id"], title="Control renal", location="Piso 3")
        assert updated["title"] == "Control renal"
        assert updated["location"] == "Piso 3"
        assert updated["scheduled_at"] == "2026-10-01T09:00:00Z"  # no tocado
        assert updated["updated_at"] >= appt["updated_at"]

    def test_update_unknown_id_raises_key_error(self, tmp_path):
        store = CalendarStore(tmp_path)
        with pytest.raises(KeyError):
            store.update_appointment("no-existe", title="x")

    def test_delete_removes_the_appointment(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        store.delete_appointment(appt["id"])
        assert store.list_appointments() == []

    def test_delete_unknown_id_raises_key_error(self, tmp_path):
        store = CalendarStore(tmp_path)
        with pytest.raises(KeyError):
            store.delete_appointment("no-existe")

    def test_deleting_an_appointment_unassigns_its_questions_instead_of_deleting_them(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        question = store.create_question("¿Debo ayunar?", appointment_id=appt["id"])
        store.delete_appointment(appt["id"])
        survivor = store.get_question(question["id"])
        assert survivor is not None and survivor["appointment_id"] is None


class TestCalendarStoreQuestions:
    def test_create_without_an_appointment_is_allowed(self, tmp_path):
        store = CalendarStore(tmp_path)
        question = store.create_question("¿Debo preocuparme por mi colesterol?")
        assert question["appointment_id"] is None
        assert question["answered"] is False
        assert question["id"]

    def test_create_with_an_unknown_appointment_raises_key_error(self, tmp_path):
        store = CalendarStore(tmp_path)
        with pytest.raises(KeyError):
            store.create_question("¿?", appointment_id="no-existe")

    def test_create_with_a_real_appointment_links_it(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        question = store.create_question("¿Debo ayunar?", appointment_id=appt["id"])
        assert question["appointment_id"] == appt["id"]

    def test_list_questions_filters_by_appointment_id(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        store.create_question("Suelta", appointment_id=None)
        store.create_question("De la cita", appointment_id=appt["id"])
        assert [q["text"] for q in store.list_questions(appointment_id=appt["id"])] == ["De la cita"]
        assert [q["text"] for q in store.list_questions(appointment_id=None)] == ["Suelta"]
        assert len(store.list_questions()) == 2

    def test_get_returns_none_for_unknown_id(self, tmp_path):
        store = CalendarStore(tmp_path)
        assert store.get_question("no-existe") is None

    def test_update_merges_fields(self, tmp_path):
        store = CalendarStore(tmp_path)
        question = store.create_question("¿Debo ayunar?")
        updated = store.update_question(question["id"], answered=True)
        assert updated["answered"] is True
        assert updated["text"] == "¿Debo ayunar?"

    def test_update_can_assign_a_standalone_question_to_an_appointment(self, tmp_path):
        store = CalendarStore(tmp_path)
        appt = store.create_appointment(title="Control", scheduled_at="2026-10-01T09:00:00Z")
        question = store.create_question("¿Debo ayunar?")
        updated = store.update_question(question["id"], appointment_id=appt["id"])
        assert updated["appointment_id"] == appt["id"]

    def test_update_assigning_to_an_unknown_appointment_raises_key_error(self, tmp_path):
        store = CalendarStore(tmp_path)
        question = store.create_question("¿Debo ayunar?")
        with pytest.raises(KeyError):
            store.update_question(question["id"], appointment_id="no-existe")

    def test_update_unknown_question_raises_key_error(self, tmp_path):
        store = CalendarStore(tmp_path)
        with pytest.raises(KeyError):
            store.update_question("no-existe", answered=True)

    def test_delete_removes_it(self, tmp_path):
        store = CalendarStore(tmp_path)
        question = store.create_question("¿Debo ayunar?")
        store.delete_question(question["id"])
        assert store.list_questions() == []

    def test_delete_unknown_question_raises_key_error(self, tmp_path):
        store = CalendarStore(tmp_path)
        with pytest.raises(KeyError):
            store.delete_question("no-existe")


# ---------------------------------------------------------------------------
# API (integration, via TestClient)
# ---------------------------------------------------------------------------

def make_client(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    calendar = CalendarStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_calendar] = lambda: calendar
    return TestClient(app), calendar


def create_appt(client, **overrides):
    body = {"title": "Control anual", "scheduled_at": "2026-10-01T09:00:00Z", **overrides}
    return client.post("/appointments", json=body)


class TestAppointmentsApi:
    def test_list_starts_empty(self, tmp_path):
        client, _ = make_client(tmp_path)
        assert client.get("/appointments").json() == []
        app.dependency_overrides.clear()

    def test_create_then_get_includes_empty_questions_list(self, tmp_path):
        client, _ = make_client(tmp_path)
        created = create_appt(client, doctor_name="Dr. Pérez")
        assert created.status_code == 201
        assert created.json()["questions"] == []
        appt_id = created.json()["id"]

        fetched = client.get(f"/appointments/{appt_id}")
        assert fetched.status_code == 200
        assert fetched.json()["doctor_name"] == "Dr. Pérez"
        assert fetched.json()["questions"] == []
        app.dependency_overrides.clear()

    def test_get_includes_its_linked_questions(self, tmp_path):
        client, store = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        store.create_question("¿Debo ayunar?", appointment_id=appt_id)
        fetched = client.get(f"/appointments/{appt_id}")
        assert [q["text"] for q in fetched.json()["questions"]] == ["¿Debo ayunar?"]
        app.dependency_overrides.clear()

    def test_create_rejects_blank_title(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = create_appt(client, title="   ")
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_create_rejects_invalid_date(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = create_appt(client, scheduled_at="no es una fecha")
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_get_unknown_id_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        assert client.get("/appointments/no-existe").status_code == 404
        app.dependency_overrides.clear()

    def test_list_reflects_created_appointments_sorted(self, tmp_path):
        client, _ = make_client(tmp_path)
        create_appt(client, title="Tarde", scheduled_at="2026-12-01T09:00:00Z")
        create_appt(client, title="Temprano", scheduled_at="2026-10-01T09:00:00Z")
        titles = [a["title"] for a in client.get("/appointments").json()]
        assert titles == ["Temprano", "Tarde"]
        app.dependency_overrides.clear()

    def test_update_changes_fields(self, tmp_path):
        client, _ = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        response = client.put(f"/appointments/{appt_id}", json={"location": "Piso 3"})
        assert response.status_code == 200
        assert response.json()["location"] == "Piso 3"
        app.dependency_overrides.clear()

    def test_update_rejects_blank_title(self, tmp_path):
        client, _ = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        response = client.put(f"/appointments/{appt_id}", json={"title": "  "})
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_update_unknown_id_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/appointments/no-existe", json={"title": "x"})
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_delete_removes_it(self, tmp_path):
        client, _ = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        response = client.delete(f"/appointments/{appt_id}")
        assert response.status_code == 204
        assert client.get(f"/appointments/{appt_id}").status_code == 404
        app.dependency_overrides.clear()

    def test_delete_unassigns_its_questions_instead_of_deleting_them(self, tmp_path):
        client, store = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        question = store.create_question("¿Debo ayunar?", appointment_id=appt_id)
        client.delete(f"/appointments/{appt_id}")
        assert client.get(f"/questions/{question['id']}").json()["appointment_id"] is None
        app.dependency_overrides.clear()

    def test_delete_unknown_id_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        assert client.delete("/appointments/no-existe").status_code == 404
        app.dependency_overrides.clear()


class TestQuestionsApi:
    def test_create_without_an_appointment(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.post("/questions", json={"text": "¿Debo preocuparme por mi colesterol?"})
        assert response.status_code == 201
        body = response.json()
        assert body["text"] == "¿Debo preocuparme por mi colesterol?"
        assert body["appointment_id"] is None
        assert body["answered"] is False
        app.dependency_overrides.clear()

    def test_create_linked_to_an_appointment(self, tmp_path):
        client, _ = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        response = client.post("/questions", json={"text": "¿Debo ayunar?", "appointment_id": appt_id})
        assert response.status_code == 201
        assert response.json()["appointment_id"] == appt_id
        app.dependency_overrides.clear()

    def test_create_rejects_blank_text(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.post("/questions", json={"text": "  "})
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_create_with_unknown_appointment_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.post("/questions", json={"text": "¿?", "appointment_id": "no-existe"})
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_list_filters_by_appointment_id(self, tmp_path):
        client, _ = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        client.post("/questions", json={"text": "Suelta"})
        client.post("/questions", json={"text": "De la cita", "appointment_id": appt_id})

        assert [q["text"] for q in client.get(f"/questions?appointment_id={appt_id}").json()] == ["De la cita"]
        assert [q["text"] for q in client.get("/questions?unassigned=true").json()] == ["Suelta"]
        assert len(client.get("/questions").json()) == 2
        app.dependency_overrides.clear()

    def test_get_unknown_question_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        assert client.get("/questions/no-existe").status_code == 404
        app.dependency_overrides.clear()

    def test_update_marks_answered(self, tmp_path):
        client, _ = make_client(tmp_path)
        question_id = client.post("/questions", json={"text": "¿Debo ayunar?"}).json()["id"]
        response = client.put(f"/questions/{question_id}", json={"answered": True})
        assert response.status_code == 200
        assert response.json()["answered"] is True
        assert response.json()["text"] == "¿Debo ayunar?"
        app.dependency_overrides.clear()

    def test_update_can_assign_a_standalone_question_to_an_appointment(self, tmp_path):
        client, _ = make_client(tmp_path)
        appt_id = create_appt(client).json()["id"]
        question_id = client.post("/questions", json={"text": "¿Debo ayunar?"}).json()["id"]
        response = client.put(f"/questions/{question_id}", json={"appointment_id": appt_id})
        assert response.status_code == 200
        assert response.json()["appointment_id"] == appt_id
        app.dependency_overrides.clear()

    def test_update_rejects_blank_text(self, tmp_path):
        client, _ = make_client(tmp_path)
        question_id = client.post("/questions", json={"text": "¿Debo ayunar?"}).json()["id"]
        response = client.put(f"/questions/{question_id}", json={"text": "  "})
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_update_unknown_question_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/questions/no-existe", json={"answered": True})
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_delete_question(self, tmp_path):
        client, _ = make_client(tmp_path)
        question_id = client.post("/questions", json={"text": "¿Debo ayunar?"}).json()["id"]
        response = client.delete(f"/questions/{question_id}")
        assert response.status_code == 204
        assert client.get(f"/questions/{question_id}").status_code == 404
        app.dependency_overrides.clear()

    def test_delete_unknown_question_is_404(self, tmp_path):
        client, _ = make_client(tmp_path)
        assert client.delete("/questions/no-existe").status_code == 404
        app.dependency_overrides.clear()
