"""Conexión a Postgres y aplicación de migraciones al arrancar.

Mismo espíritu que migrations/*.sql en plataform-OKF-Cloud
(github.com/fredyxander/plataform-OKF-Cloud): archivos SQL simples,
numerados, aplicados en orden — sin un framework de migraciones aparte."""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def make_engine(settings: Settings):
    return create_engine(settings.database_url, pool_pre_ping=True)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def run_migrations(engine) -> list[str]:
    """Aplica los archivos migrations/*.sql que aún no se hayan corrido,
    en orden alfabético (por eso el prefijo numérico: 001_, 002_...).
    Devuelve los nombres de los archivos que se acaban de aplicar."""
    applied_now = []
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  filename TEXT PRIMARY KEY,"
            "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            ")"
        )
        already = {
            row[0] for row in conn.exec_driver_sql("SELECT filename FROM schema_migrations")
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already:
                continue
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))
            conn.exec_driver_sql(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
            )
            applied_now.append(path.name)
    return applied_now


def get_session(session_factory: sessionmaker):
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.close()
