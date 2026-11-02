from fastapi.testclient import TestClient

from app.calendar_store import CalendarStore
from app.config import Settings
from app.main import app, get_calendar, get_settings, get_store
from app.store import DocumentStore


def make_client(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    store = DocumentStore(tmp_path)
    calendar = CalendarStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_calendar] = lambda: calendar
    return TestClient(app), store, calendar


class TestNotificationsApi:
    def test_returns_empty_list_when_nothing_to_flag(self, tmp_path):
        client, _, _ = make_client(tmp_path)
        response = client.get("/notifications")
        assert response.status_code == 200
        assert response.json() == {"notices": []}
        app.dependency_overrides.clear()

    def test_returns_a_notice_for_a_past_appointment(self, tmp_path):
        client, _, calendar = make_client(tmp_path)
        calendar.create_appointment(title="Control", scheduled_at="2020-01-01T09:00:00Z")
        response = client.get("/notifications")
        assert response.status_code == 200
        notices = response.json()["notices"]
        assert len(notices) == 1
        assert notices[0]["type"] == "appointment"
        app.dependency_overrides.clear()
