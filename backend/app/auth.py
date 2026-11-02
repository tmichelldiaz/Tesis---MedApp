"""Hash de contraseñas y tokens de sesión — mismo patrón que
internal/auth/{password,token}.go en plataform-OKF-Cloud
(github.com/fredyxander/plataform-OKF-Cloud): bcrypt para contraseñas,
JWT firmado HS256 para el token, con user_id como claim principal."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import Settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


class InvalidToken(Exception):
    pass


def validate_token(token: str, settings: Settings) -> str:
    """Devuelve el user_id si el token es válido y no ha expirado.
    Lanza InvalidToken si no (firma inválida, expirado, mal formado)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    user_id = payload.get("user_id")
    if not user_id:
        raise InvalidToken("El token no tiene user_id.")
    return user_id
