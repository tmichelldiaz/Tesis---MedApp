"""CRUD de usuarios sobre Postgres. Mismo modelo de datos que la tabla
`users` de plataform-OKF-Cloud (id UUID, email único, password_hash,
nombre, apellido), más policy_accepted_at/policy_version_accepted para
dejar constancia de que el usuario aceptó la política de datos al
registrarse (Sección 15 de la política)."""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


class EmailAlreadyExists(Exception):
    pass


class UserNotFound(Exception):
    pass


class UserStore:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        email: str,
        password_hash: str,
        nombre: str = "",
        apellido: str = "",
        policy_version: str | None = None,
    ) -> dict:
        email = email.strip().lower()
        existing = self.session.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        ).first()
        if existing:
            raise EmailAlreadyExists(email)

        policy_accepted_at = datetime.now(timezone.utc) if policy_version is not None else None
        row = self.session.execute(
            text(
                "INSERT INTO users (email, password_hash, nombre, apellido, "
                "policy_accepted_at, policy_version_accepted) "
                "VALUES (:email, :password_hash, :nombre, :apellido, "
                ":policy_accepted_at, :policy_version) "
                "RETURNING id, email, nombre, apellido, created_at, "
                "policy_accepted_at, policy_version_accepted"
            ),
            {
                "email": email, "password_hash": password_hash,
                "nombre": nombre, "apellido": apellido,
                "policy_accepted_at": policy_accepted_at, "policy_version": policy_version,
            },
        ).mappings().first()
        self.session.commit()
        return dict(row)

    def get_by_email(self, email: str) -> dict | None:
        row = self.session.execute(
            text(
                "SELECT id, email, password_hash, nombre, apellido, created_at "
                "FROM users WHERE email = :email"
            ),
            {"email": email.strip().lower()},
        ).mappings().first()
        return dict(row) if row else None

    def get_by_id(self, user_id: str) -> dict | None:
        row = self.session.execute(
            text(
                "SELECT id, email, nombre, apellido, created_at, "
                "policy_accepted_at, policy_version_accepted "
                "FROM users WHERE id = :id"
            ),
            {"id": user_id},
        ).mappings().first()
        return dict(row) if row else None

    def delete(self, user_id: str) -> None:
        self.session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        self.session.commit()
