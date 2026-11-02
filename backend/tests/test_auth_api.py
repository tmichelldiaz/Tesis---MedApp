import uuid

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.config import Settings
from app.main import app, get_current_user, get_settings, get_user_store
from app.user_store import EmailAlreadyExists

STRONG_PASSWORD = "Correcto1234!$"


class FakeUserStore:
    """Sustituto de UserStore en memoria, para probar los endpoints de auth
    sin necesitar Postgres — mismo contrato (create/get_by_email/get_by_id)."""

    def __init__(self):
        self.by_email: dict[str, dict] = {}
        self.by_id: dict[str, dict] = {}

    def create(self, email, password_hash, nombre="", apellido="", policy_version=None):
        email = email.strip().lower()
        if email in self.by_email:
            raise EmailAlreadyExists(email)
        user = {
            "id": str(uuid.uuid4()), "email": email, "password_hash": password_hash,
            "nombre": nombre, "apellido": apellido, "created_at": "2026-01-01T00:00:00Z",
            "policy_accepted_at": "2026-01-01T00:00:00Z" if policy_version else None,
            "policy_version_accepted": policy_version,
        }
        self.by_email[email] = user
        self.by_id[user["id"]] = user
        return {k: v for k, v in user.items() if k != "password_hash"}

    def get_by_email(self, email):
        return self.by_email.get(email.strip().lower())

    def get_by_id(self, user_id):
        return self.by_id.get(user_id)

    def delete(self, user_id):
        user = self.by_id.pop(user_id, None)
        if user:
            self.by_email.pop(user["email"], None)


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        openrouter_api_key="k", jwt_secret="test-secret-at-least-32-bytes-x",
        data_dir=tmp_path, _env_file=None,
    )
    store = FakeUserStore()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_user_store] = lambda: store
    yield TestClient(app), store, settings
    app.dependency_overrides.clear()


def register(client, **overrides):
    body = {
        "email": "jennifer@example.com", "password": STRONG_PASSWORD,
        "nombre": "Jennifer", "apellido": "Suarez", "accept_policy": True,
        **overrides,
    }
    return client.post("/auth/register", json=body)


class TestRegister:
    def test_happy_path_returns_a_token_and_the_user(self, client):
        api, _, _ = client
        response = register(api)
        assert response.status_code == 201
        body = response.json()
        assert body["token"]
        assert body["user"]["email"] == "jennifer@example.com"
        assert body["user"]["nombre"] == "Jennifer"
        assert "password_hash" not in body["user"]

    def test_records_policy_acceptance(self, client):
        api, store, settings = client
        register(api)
        user = store.get_by_email("jennifer@example.com")
        assert user["policy_accepted_at"] is not None
        assert user["policy_version_accepted"] == settings.policy_version

    def test_rejects_registration_without_accepting_the_policy(self, client):
        api, _, _ = client
        response = register(api, accept_policy=False)
        assert response.status_code == 400

    def test_rejects_invalid_email(self, client):
        api, _, _ = client
        response = register(api, email="no-es-un-correo")
        assert response.status_code == 400

    def test_rejects_duplicate_email(self, client):
        api, _, _ = client
        register(api)
        response = register(api)
        assert response.status_code == 409

    def test_email_is_normalized_to_lowercase(self, client):
        api, store, _ = client
        register(api, email="Jennifer@Example.com")
        assert store.get_by_email("jennifer@example.com") is not None

    def test_password_is_hashed_not_stored_plain(self, client):
        api, store, _ = client
        register(api)
        stored = store.get_by_email("jennifer@example.com")
        assert stored["password_hash"] != STRONG_PASSWORD
        assert auth_module.check_password(STRONG_PASSWORD, stored["password_hash"])

    @pytest.mark.parametrize("password,missing", [
        ("short1!A", None),  # 8 chars exactas, válida (caso límite, no debe fallar)
        ("nouppercase1!", "mayúscula"),
        ("NOLOWERCASE1!", "minúscula"),
        ("NoNumbers!!", "número"),
        ("NoSymbols123", "símbolo"),
        ("Ab1!", "8 caracteres"),
    ])
    def test_password_strength_rules(self, client, password, missing):
        api, _, _ = client
        response = register(api, password=password)
        if missing is None:
            assert response.status_code == 201
        else:
            assert response.status_code == 400
            assert missing in response.json()["detail"]

    def test_stores_the_health_profile_fields_given_at_registration(self, client):
        api, _, settings = client
        response = register(api, birth_date="1984-01-07", sex="Femenino", weight_kg=62.5, blood_type="o+")
        assert response.status_code == 201
        user_id = response.json()["user"]["id"]

        from app.profile_store import ProfileStore
        profile = ProfileStore(settings.data_dir / str(user_id)).get()
        assert profile["birth_date"] == "1984-01-07"
        assert profile["sex"] == "Femenino"
        assert profile["weight_kg"] == 62.5
        assert profile["blood_type"] == "O+"

    def test_copies_nombre_and_apellido_into_the_profile_name(self, client):
        # El Dashboard saluda con profile.name, no con el nombre/apellido de
        # la cuenta — sin esto, el usuario tendría que volver a escribir su
        # nombre a mano en "Editar información" justo después de registrarse.
        api, _, settings = client
        response = register(api, nombre="Ana", apellido="Gómez")
        user_id = response.json()["user"]["id"]

        from app.profile_store import ProfileStore
        profile = ProfileStore(settings.data_dir / str(user_id)).get()
        assert profile["name"] == "Ana Gómez"

    def test_registering_without_profile_fields_leaves_health_fields_blank(self, client):
        api, _, settings = client
        response = register(api)
        user_id = response.json()["user"]["id"]

        from app.profile_store import ProfileStore
        profile = ProfileStore(settings.data_dir / str(user_id)).get()
        assert profile["birth_date"] is None and profile["sex"] is None

    def test_rejects_invalid_sex_at_registration(self, client):
        api, _, _ = client
        response = register(api, sex="no-es-una-opcion")
        assert response.status_code == 400

    def test_rejects_invalid_blood_type_at_registration(self, client):
        api, _, _ = client
        response = register(api, blood_type="Z+")
        assert response.status_code == 400


class TestLogin:
    def test_happy_path_returns_a_token(self, client):
        api, _, _ = client
        register(api)
        response = api.post("/auth/login", json={"email": "jennifer@example.com", "password": STRONG_PASSWORD})
        assert response.status_code == 200
        assert response.json()["token"]
        assert response.json()["user"]["email"] == "jennifer@example.com"

    def test_wrong_password_is_401(self, client):
        api, _, _ = client
        register(api)
        response = api.post("/auth/login", json={"email": "jennifer@example.com", "password": "wrong-password"})
        assert response.status_code == 401

    def test_unknown_email_is_401_not_404(self, client):
        # No revelar si el correo existe o no
        api, _, _ = client
        response = api.post("/auth/login", json={"email": "nadie@example.com", "password": "x" * 10})
        assert response.status_code == 401


class TestMe:
    def test_returns_the_authenticated_user(self, client):
        api, _, _ = client
        token = register(api).json()["token"]
        response = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] == "jennifer@example.com"

    def test_missing_header_is_401(self, client):
        api, _, _ = client
        assert api.get("/auth/me").status_code == 401

    def test_malformed_header_is_401(self, client):
        api, _, _ = client
        response = api.get("/auth/me", headers={"Authorization": "not-bearer-format"})
        assert response.status_code == 401

    def test_garbage_token_is_401(self, client):
        api, _, _ = client
        response = api.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
        assert response.status_code == 401

    def test_token_for_a_deleted_user_is_401(self, client):
        api, store, _ = client
        token = register(api).json()["token"]
        store.by_email.clear()
        store.by_id.clear()
        response = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestDeleteAccount:
    def test_deletes_the_account_and_its_data_dir(self, client):
        api, store, settings = client
        token = register(api).json()["token"]
        user_id = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
        (settings.data_dir / user_id).mkdir(parents=True, exist_ok=True)
        (settings.data_dir / user_id / "algo.txt").write_text("dato")

        response = api.delete("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 204
        assert store.get_by_id(user_id) is None
        assert not (settings.data_dir / user_id).exists()

    def test_token_no_longer_works_after_deletion(self, client):
        api, _, _ = client
        token = register(api).json()["token"]
        api.delete("/auth/me", headers={"Authorization": f"Bearer {token}"})
        response = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_requires_auth(self, client):
        api, _, _ = client
        assert api.delete("/auth/me").status_code == 401

    def test_also_erases_what_the_agent_remembered_of_the_patient(self, client):
        from app.agent import memory

        api, _, settings = client
        token = register(api).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = api.get("/auth/me", headers=headers).json()["id"]
        store = memory.get_store(settings.database_url)
        store.put(memory.memory_namespace(user_id), "k1", {"recuerdo": "alérgico a la penicilina"})
        store.put(memory.memory_namespace("otro-paciente"), "k2", {"recuerdo": "toma losartán"})

        assert api.delete("/auth/me", headers=headers).status_code == 204

        assert memory.recall(store, user_id) == []
        assert memory.recall(store, "otro-paciente") == ["toma losartán"]

    def test_if_the_memory_cannot_be_erased_the_account_is_kept(self, client, monkeypatch):
        from app.agent import memory

        api, users, _ = client
        token = register(api).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = api.get("/auth/me", headers=headers).json()["id"]

        def broken(database_url, user_id):
            raise RuntimeError("base caída")

        monkeypatch.setattr(memory, "delete_user_memory", broken)
        response = api.delete("/auth/me", headers=headers)
        assert response.status_code == 500
        assert "base caída" not in response.text
        assert users.get_by_id(user_id) is not None  # el paciente puede reintentar


class TestAgentMemoryEndpoints:
    def seed(self, client, text="alérgico a la penicilina", key="k1"):
        from app.agent import memory

        api, _, settings = client
        token = register(api).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = api.get("/auth/me", headers=headers).json()["id"]
        memory.get_store(settings.database_url).put(memory.memory_namespace(user_id), key, {"recuerdo": text})
        return api, headers, user_id

    def test_lists_what_the_assistant_remembers(self, client):
        api, headers, _ = self.seed(client)
        assert api.get("/memory", headers=headers).json() == [{"id": "k1", "text": "alérgico a la penicilina"}]

    def test_forgets_one_memory(self, client):
        api, headers, _ = self.seed(client)
        assert api.delete("/memory/k1", headers=headers).status_code == 204
        assert api.get("/memory", headers=headers).json() == []

    def test_unknown_memory_is_404(self, client):
        api, headers, _ = self.seed(client)
        assert api.delete("/memory/no-existe", headers=headers).status_code == 404

    def test_one_patient_never_sees_or_deletes_anothers(self, client):
        from app.agent import memory

        api, _, settings = client
        other_token = register(api, email="otra@example.com").json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        other_id = api.get("/auth/me", headers=other_headers).json()["id"]
        memory.get_store(settings.database_url).put(memory.memory_namespace(other_id), "ajeno", {"recuerdo": "dato ajeno"})

        _, headers, _ = self.seed(client)
        assert api.get("/memory", headers=headers).json() == [{"id": "k1", "text": "alérgico a la penicilina"}]
        assert api.delete("/memory/ajeno", headers=headers).status_code == 404

    def test_requires_auth(self, client):
        api, _, _ = client
        assert api.get("/memory").status_code == 401
        assert api.delete("/memory/k1").status_code == 401


class TestProtectedEndpointsRequireAuth:
    def test_listing_documents_without_a_token_is_401(self, client):
        api, _, _ = client
        assert api.get("/documents").status_code == 401

    def test_listing_appointments_without_a_token_is_401(self, client):
        api, _, _ = client
        assert api.get("/appointments").status_code == 401

    def test_getting_the_profile_without_a_token_is_401(self, client):
        api, _, _ = client
        assert api.get("/profile").status_code == 401

    def test_health_and_categories_stay_public(self, client):
        api, _, _ = client
        assert api.get("/health").status_code == 200
        assert api.get("/categories").status_code == 200
