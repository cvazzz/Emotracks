import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from backend.app.main import app  # noqa: E402
from backend.app.db import init_db, session_scope  # noqa: E402
from backend.app.models import Child  # noqa: E402

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def register_parent(email="parent1@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "pass123", "role": "parent"})
    if r.status_code not in (200,201,400):
        raise AssertionError(r.text)
    login = client.post("/api/auth/login", json={"email": email, "password": "pass123"})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_child_crud_flow():
    token = register_parent()
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    r_create = client.post("/api/children", json={"name": "Juan", "age": 8}, headers=headers)
    assert r_create.status_code == 201, r_create.text
    child = r_create.json()
    cid = child["id"]

    # List
    r_list = client.get("/api/children", headers=headers)
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert any(c["id"] == cid for c in items)

    # Get
    r_get = client.get(f"/api/children/{cid}", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["name"] == "Juan"

    # Update
    r_upd = client.patch(f"/api/children/{cid}", json={"age": 9, "notes": "Alergia a maní"}, headers=headers)
    assert r_upd.status_code == 200
    assert r_upd.json()["age"] == 9
    assert r_upd.json()["notes"] == "Alergia a maní"

    # Delete
    r_del = client.delete(f"/api/children/{cid}", headers=headers)
    assert r_del.status_code == 204

    # Get again 404
    r_get2 = client.get(f"/api/children/{cid}", headers=headers)
    assert r_get2.status_code == 404


def test_child_access_is_scoped_to_parent():
    token1 = register_parent("p1@example.com")
    token2 = register_parent("p2@example.com")

    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    r_create = client.post("/api/children", json={"name": "Ana"}, headers=headers1)
    assert r_create.status_code == 201
    cid = r_create.json()["id"]

    # Parent2 cannot access
    r_forbidden = client.get(f"/api/children/{cid}", headers=headers2)
    assert r_forbidden.status_code == 404

    # Parent2 list should not contain child
    r_list2 = client.get("/api/children", headers=headers2)
    assert r_list2.status_code == 200
    ids2 = {c["id"] for c in r_list2.json()["items"]}
    assert cid not in ids2
