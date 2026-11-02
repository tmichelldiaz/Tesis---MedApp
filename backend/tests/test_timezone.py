"""Cada paciente ve y agenda según SU zona horaria, no la de Colombia.

Una amiga en España iba a probar la app: "mañana" y las horas de las citas salían con la hora de Colombia."""

import asyncio
from datetime import datetime, timezone

import pytest

from app.agent.clock import is_past, local_now, set_request_timezone, today_note, user_timezone
from app.config import Settings
from app.main import apply_timezone

SETTINGS = Settings(openrouter_api_key="k", _env_file=None)
# 2026-10-15 23:30 en Bogotá (UTC-5) = 2026-10-16 04:30 UTC = 2026-10-16 06:30 en Madrid (UTC+2, horario de verano)
INSTANT = datetime(2026, 10, 16, 4, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_zone():
    set_request_timezone(None)
    yield
    set_request_timezone(None)


def test_without_a_zone_it_is_colombia():
    assert local_now(SETTINGS, INSTANT).day == 15 and "Colombia" in today_note(SETTINGS, INSTANT)


def test_the_patients_own_zone_is_used_with_its_summer_time():
    assert set_request_timezone("Europe/Madrid")
    moment = local_now(SETTINGS, INSTANT)
    assert (moment.day, moment.hour) == (16, 6)  # ya es el día siguiente allá
    note = today_note(SETTINGS, INSTANT)
    assert "Europe/Madrid" in note and "UTC+02:00" in note and "viernes 16 de octubre" in note
    assert "mañana = 2026-10-17" in note


def test_winter_time_in_spain_is_one_hour():
    set_request_timezone("Europe/Madrid")
    assert "UTC+01:00" in today_note(SETTINGS, datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc))


def test_an_unknown_zone_is_ignored():
    assert not set_request_timezone("Marte/Olimpo")
    assert "Colombia" in today_note(SETTINGS, INSTANT)


def test_an_appointment_time_without_offset_means_the_patients_local_time():
    set_request_timezone("Europe/Madrid")
    assert user_timezone(SETTINGS).utcoffset(INSTANT).total_seconds() == 2 * 3600
    assert is_past("2020-01-01T10:00:00", SETTINGS) is True
    assert is_past("2099-01-01T10:00:00", SETTINGS) is False


def test_the_request_header_sets_the_zone():
    class Fake:
        headers = {"x-timezone": "Asia/Tokyo"}

    async def go():
        await apply_timezone(Fake())
        return user_timezone(SETTINGS).utcoffset(INSTANT).total_seconds()

    assert asyncio.run(go()) == 9 * 3600


def test_a_naive_appointment_is_stored_with_the_patients_zone(tmp_path):
    from app.agent.tools import build_tools
    from app.calendar_store import CalendarStore
    from app.profile_store import ProfileStore
    from app.store import DocumentStore

    set_request_timezone("Europe/Madrid")
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    calendar = CalendarStore(tmp_path)
    tools = {t.name: t for t in build_tools(DocumentStore(tmp_path), calendar, ProfileStore(tmp_path), settings, None)}
    tools["create_appointment"].invoke({"title": "Cardiología", "scheduled_at": "2099-10-16T15:00:00"})
    assert calendar.list_appointments()[0]["scheduled_at"] == "2099-10-16T15:00:00+02:00"
