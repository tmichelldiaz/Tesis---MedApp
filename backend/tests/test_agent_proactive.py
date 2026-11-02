from app.agent.proactive import build_proactive_note, build_user_notices
from app.calendar_store import CalendarStore
from app.okf.builder import build_bundle, write_bundle
from app.store import DocumentStore

GLUCOSA_ALTA = {
    "exam": "Glucosa", "value_raw": "180", "value_numeric": 180.0, "unit": "mg/dL",
    "date": "2026-03-10", "reference_low": 70.0, "reference_high": 100.0, "reference_text": "70 - 100",
}
GLUCOSA_NORMAL = {**GLUCOSA_ALTA, "value_raw": "90", "value_numeric": 90.0}


def add_ready_doc(store, lab_values=None):
    meta = store.create("informe.pdf", b"%PDF-1.4 x", "pdf")
    bundle = build_bundle("# Doc\n\ncuerpo\n", "informe.pdf", "m", page_count=1, document_id=meta["id"], source_format="pdf")
    store.ensure_historia_slug(meta["id"])
    write_bundle(bundle, store.bundle_dir(meta["id"]))
    return store.update(meta["id"], status="ready", concepts=[], lab_values=lab_values or [])


class TestBuildProactiveNote:
    def test_returns_none_when_there_is_nothing_to_flag(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        assert build_proactive_note(store, calendar) is None

    def test_flags_a_past_appointment(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        calendar.create_appointment(title="Control", scheduled_at="2020-01-01T09:00:00Z")
        note = build_proactive_note(store, calendar)
        assert note is not None and "Control" in note and "ya pasó" in note

    def test_does_not_flag_a_future_appointment(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        calendar.create_appointment(title="Control", scheduled_at="2099-01-01T09:00:00Z")
        assert build_proactive_note(store, calendar) is None

    def test_flags_a_standalone_unanswered_question(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        calendar.create_question("¿Debo preocuparme por mi colesterol?")
        note = build_proactive_note(store, calendar)
        assert note is not None and "pregunta suelta" in note

    def test_does_not_flag_an_answered_standalone_question(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        q = calendar.create_question("¿Debo preocuparme por mi colesterol?")
        calendar.update_question(q["id"], answered=True)
        assert build_proactive_note(store, calendar) is None

    def test_flags_an_unanswered_question_tied_to_a_past_appointment(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        appt = calendar.create_appointment(title="Control", scheduled_at="2020-01-01T09:00:00Z")
        calendar.create_question("¿Debo ayunar?", appointment_id=appt["id"])
        note = build_proactive_note(store, calendar)
        assert "¿Debo ayunar?" in note and "tuvo respuesta" in note

    def test_does_not_flag_a_question_tied_to_a_future_appointment(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        appt = calendar.create_appointment(title="Control", scheduled_at="2099-01-01T09:00:00Z")
        calendar.create_question("¿Debo ayunar?", appointment_id=appt["id"])
        assert build_proactive_note(store, calendar) is None

    def test_flags_out_of_range_exam_values(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        add_ready_doc(store, lab_values=[GLUCOSA_ALTA])
        note = build_proactive_note(store, calendar)
        assert note is not None and "Glucosa" in note and "fuera de rango" in note

    def test_does_not_flag_in_range_exam_values(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        add_ready_doc(store, lab_values=[GLUCOSA_NORMAL])
        assert build_proactive_note(store, calendar) is None

    def test_combines_multiple_findings(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        calendar.create_appointment(title="Control", scheduled_at="2020-01-01T09:00:00Z")
        calendar.create_question("¿Suelta?")
        add_ready_doc(store, lab_values=[GLUCOSA_ALTA])
        note = build_proactive_note(store, calendar)
        assert "Control" in note and "suelta" in note and "Glucosa" in note


class TestBuildUserNotices:
    def test_returns_empty_list_when_there_is_nothing_to_flag(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        assert build_user_notices(store, calendar) == []

    def test_flags_a_past_appointment_in_patient_facing_text(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        calendar.create_appointment(title="Control", scheduled_at="2020-01-01T09:00:00Z")
        notices = build_user_notices(store, calendar)
        assert len(notices) == 1
        assert notices[0]["type"] == "appointment"
        assert "Control" in notices[0]["text"]

    def test_flags_out_of_range_exam_values(self, tmp_path):
        store = DocumentStore(tmp_path)
        calendar = CalendarStore(tmp_path)
        add_ready_doc(store, lab_values=[GLUCOSA_ALTA])
        notices = build_user_notices(store, calendar)
        assert any(n["type"] == "lab" and "Glucosa" in n["text"] for n in notices)
