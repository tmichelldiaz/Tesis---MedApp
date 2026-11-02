"""Las peticiones simultáneas y los archivos dañados ya no dejan a una persona con error 500.

Caso real (16 oct): una tester abría la app y esta pedía citas, avisos y perfil a la vez; dos peticiones escribían el
mismo archivo temporal y una fallaba con "no existe el archivo"; otra dejó appointments.json VACÍO y desde entonces
todas sus peticiones devolvían 500. Además, el asistente fallaba cuando la base había cerrado una conexión inactiva."""

import json
import threading

import psycopg
import pytest

from app.agent import service
from app.calendar_store import CalendarStore
from app.fsutil import read_json_safe, write_json_atomic
from app.profile_store import ProfileStore


class TestDamagedFiles:
    def test_an_empty_calendar_file_is_an_empty_calendar_not_an_error(self, tmp_path):
        (tmp_path / "appointments.json").write_text("", encoding="utf-8")
        calendar = CalendarStore(tmp_path)
        assert calendar.list_appointments() == [] and calendar.list_questions() == []

    def test_a_corrupt_file_does_not_break_the_calendar_and_can_be_written_again(self, tmp_path):
        (tmp_path / "appointments.json").write_text("{no es json", encoding="utf-8")
        calendar = CalendarStore(tmp_path)
        assert calendar.list_appointments() == []
        calendar.create_appointment("Cardiología", "2099-01-01T10:00:00+00:00")
        assert len(calendar.list_appointments()) == 1

    def test_an_empty_profile_file_gives_the_default_profile(self, tmp_path):
        (tmp_path / "profile.json").write_text("   ", encoding="utf-8")
        assert ProfileStore(tmp_path).get().get("name") in (None, "")

    def test_creating_the_store_does_not_write_files_by_itself(self, tmp_path):
        CalendarStore(tmp_path)
        ProfileStore(tmp_path)
        assert list(tmp_path.glob("*.json")) == []


class TestSimultaneousRequests:
    def test_many_requests_at_once_never_fail_nor_leave_empty_files(self, tmp_path):
        errors = []

        def request(i):
            try:
                calendar = CalendarStore(tmp_path)  # lo que hace cada petición al empezar
                calendar.list_appointments()
                if i % 3 == 0:
                    calendar.create_appointment(f"Cita {i}", "2099-01-01T10:00:00+00:00")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=request, args=(i,)) for i in range(40)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert errors == []
        assert json.loads((tmp_path / "appointments.json").read_text(encoding="utf-8"))["appointments"] is not None
        assert list(tmp_path.glob("*.tmp")) == []  # sin archivos temporales sueltos

    def test_each_write_uses_its_own_temp_file(self, tmp_path):
        target = tmp_path / "datos.json"
        write_json_atomic(target, {"a": 1})
        write_json_atomic(target, {"a": 2})
        assert read_json_safe(target, dict) == {"a": 2}


class TestLostDatabaseConnection:
    def test_the_agent_reconnects_and_retries_once(self, monkeypatch):
        resets = []
        monkeypatch.setattr(service.memory, "reset_connections", lambda: resets.append(1))
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise psycopg.OperationalError("the connection is closed")
            return "respuesta"

        assert service._retry_if_connection_lost(flaky) == "respuesta"
        assert len(calls) == 2 and resets == [1]

    def test_a_second_failure_is_not_hidden(self, monkeypatch):
        monkeypatch.setattr(service.memory, "reset_connections", lambda: None)

        def always_down():
            raise psycopg.OperationalError("la base no responde")

        with pytest.raises(psycopg.OperationalError):
            service._retry_if_connection_lost(always_down)
