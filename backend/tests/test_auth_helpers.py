import time

import jwt
import pytest

from app.auth import InvalidToken, check_password, generate_token, hash_password, validate_token
from app.config import Settings


def make_settings(**kw) -> Settings:
    kw.setdefault("jwt_secret", "test-secret-at-least-32-bytes-long")
    return Settings(openrouter_api_key="k", _env_file=None, **kw)


class TestPasswordHashing:
    def test_a_correct_password_checks_out(self):
        hashed = hash_password("correcthorsebattery")
        assert check_password("correcthorsebattery", hashed) is True

    def test_a_wrong_password_does_not(self):
        hashed = hash_password("correcthorsebattery")
        assert check_password("wrong-password", hashed) is False

    def test_the_hash_is_never_the_plaintext(self):
        assert hash_password("hunter2") != "hunter2"

    def test_two_hashes_of_the_same_password_differ(self):
        # bcrypt genera una sal distinta cada vez
        assert hash_password("hunter2") != hash_password("hunter2")

    def test_a_malformed_hash_is_rejected_not_an_error(self):
        assert check_password("hunter2", "no-es-un-hash-bcrypt") is False


class TestTokens:
    def test_a_generated_token_validates_back_to_the_same_user_id(self):
        settings = make_settings()
        token = generate_token("user-123", settings)
        assert validate_token(token, settings) == "user-123"

    def test_a_token_signed_with_a_different_secret_is_rejected(self):
        token = generate_token("user-123", make_settings(jwt_secret="a" * 32))
        with pytest.raises(InvalidToken):
            validate_token(token, make_settings(jwt_secret="b" * 32))

    def test_an_expired_token_is_rejected(self):
        settings = make_settings(jwt_ttl_hours=0)
        token = generate_token("user-123", settings)
        time.sleep(1.1)
        with pytest.raises(InvalidToken):
            validate_token(token, settings)

    def test_garbage_is_rejected_not_an_error(self):
        with pytest.raises(InvalidToken):
            validate_token("no-soy-un-jwt", make_settings())

    def test_a_token_without_user_id_is_rejected(self):
        settings = make_settings()
        bogus = jwt.encode({"sub": "x"}, settings.jwt_secret, algorithm="HS256")
        with pytest.raises(InvalidToken):
            validate_token(bogus, settings)
