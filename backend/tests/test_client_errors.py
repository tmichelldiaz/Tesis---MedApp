"""El servidor se entera de los errores que ocurren en el celular de cada persona."""

import logging

from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def report(**extra):
    body = {"message": "undefined is not a function", "stack": "at Foo (bar.js:1)", "context": "{}",
            "device": {"model": "samsung SM-A135M", "android": "13 (API 33)", "appVersion": "1.1.0"}, **extra}
    return client.post("/client-errors", json=body)


def test_a_report_is_logged_with_the_phone_model(caplog):
    main._error_reports.clear()
    with caplog.at_level(logging.WARNING, logger="medapp.client"):
        assert report().status_code == 204
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "ERROR_EN_CELULAR" in text and "samsung SM-A135M" in text and "undefined is not a function" in text


def test_it_does_not_need_a_session():
    main._error_reports.clear()
    assert report().status_code == 204


def test_flooding_is_limited(caplog):
    main._error_reports.clear()
    with caplog.at_level(logging.WARNING, logger="medapp.client"):
        for _ in range(main.MAX_REPORTS_PER_MINUTE + 10):
            report()
    assert sum("ERROR_EN_CELULAR" in r.getMessage() for r in caplog.records) == main.MAX_REPORTS_PER_MINUTE


def test_huge_texts_are_cut():
    main._error_reports.clear()
    assert report(message="x" * 100000, stack="y" * 100000).status_code == 204
