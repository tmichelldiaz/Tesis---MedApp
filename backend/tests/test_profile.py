from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_profile, get_settings
from app.profile_store import ProfileStore


class TestProfileStore:
    def test_starts_with_all_fields_blank(self, tmp_path):
        store = ProfileStore(tmp_path)
        profile = store.get()
        assert profile["name"] is None
        assert profile["birth_date"] is None
        assert profile["weight_kg"] is None
        assert profile["blood_type"] is None
        assert profile["updated_at"] is None

    def test_update_merges_fields_and_stamps_updated_at(self, tmp_path):
        store = ProfileStore(tmp_path)
        updated = store.update(name="Jennifer", weight_kg=62.5)
        assert updated["name"] == "Jennifer"
        assert updated["weight_kg"] == 62.5
        assert updated["blood_type"] is None
        assert updated["updated_at"]

    def test_update_is_partial_and_does_not_clear_other_fields(self, tmp_path):
        store = ProfileStore(tmp_path)
        store.update(name="Jennifer", blood_type="O+")
        updated = store.update(weight_kg=60)
        assert updated["name"] == "Jennifer"
        assert updated["blood_type"] == "O+"
        assert updated["weight_kg"] == 60

    def test_survives_reopening_the_same_directory(self, tmp_path):
        ProfileStore(tmp_path).update(name="Jennifer")
        reopened = ProfileStore(tmp_path)
        assert reopened.get()["name"] == "Jennifer"


def make_client(tmp_path):
    settings = Settings(openrouter_api_key="k", data_dir=tmp_path, _env_file=None)
    profile = ProfileStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_profile] = lambda: profile
    return TestClient(app), profile


class TestProfileApi:
    def test_get_starts_blank(self, tmp_path):
        client, _ = make_client(tmp_path)
        body = client.get("/profile").json()
        assert body["name"] is None
        app.dependency_overrides.clear()

    def test_put_updates_and_get_reflects_it(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/profile", json={
            "name": "Jennifer Suarez", "birth_date": "1984-01-07",
            "weight_kg": 62.5, "blood_type": "o+",
        })
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Jennifer Suarez"
        assert body["blood_type"] == "O+"  # se normaliza a mayúsculas

        fetched = client.get("/profile").json()
        assert fetched["weight_kg"] == 62.5
        app.dependency_overrides.clear()

    def test_put_is_partial(self, tmp_path):
        client, _ = make_client(tmp_path)
        client.put("/profile", json={"name": "Jennifer"})
        response = client.put("/profile", json={"weight_kg": 60})
        assert response.status_code == 200
        assert response.json()["name"] == "Jennifer"
        assert response.json()["weight_kg"] == 60
        app.dependency_overrides.clear()

    def test_rejects_blank_name(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/profile", json={"name": "   "})
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_rejects_invalid_birth_date(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/profile", json={"birth_date": "no es una fecha"})
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_rejects_non_positive_weight(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/profile", json={"weight_kg": 0})
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_rejects_invalid_blood_type(self, tmp_path):
        client, _ = make_client(tmp_path)
        response = client.put("/profile", json={"blood_type": "Z+"})
        assert response.status_code == 400
        app.dependency_overrides.clear()
