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


def test_attach_responses_and_dashboard_by_id():
    token = register_parent("parentattach@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child
    r_child = client.post("/api/children", json={"name": "Carlos"}, headers=headers)
    assert r_child.status_code == 201
    child_id = r_child.json()["id"]
    # Crear dos responses sin child_id
    r1 = client.post("/api/submit-responses", data={"child_id": "Carlos", "text": "hola"})
    r2 = client.post("/api/submit-responses", data={"child_id": "Carlos", "text": "hola2"})
    assert r1.status_code == 202 and r2.status_code == 202
    rid1 = r1.json()["response_id"]
    rid2 = r2.json()["response_id"]
    # Attach
    attach = client.post(f"/api/children/{child_id}/attach-responses", json={"response_ids": [rid1, rid2]}, headers=headers)
    assert attach.status_code == 200
    assert attach.json()["attached"] >= 1
    # Dashboard por id
    dash = client.get(f"/api/dashboard/{child_id}", headers=headers)
    assert dash.status_code == 200
    body = dash.json()
    assert body["total"] >= 1
    assert body["child"] is not None


def test_create_response_direct_child_endpoint():
    token = register_parent("parentresp@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    r_child = client.post("/api/children", json={"name": "Lucia"}, headers=headers)
    assert r_child.status_code == 201
    child_id = r_child.json()["id"]
    r_resp = client.post(f"/api/children/{child_id}/responses", json={"text": "Estoy feliz", "emoji": ":)"}, headers=headers)
    assert r_resp.status_code == 202
    data = r_resp.json()
    assert "task_id" in data and "response_id" in data
    dash = client.get(f"/api/dashboard/{child_id}", headers=headers)
    assert dash.status_code == 200


def test_child_unique_constraint():
    token = register_parent("uniqueparent@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    r1 = client.post("/api/children", json={"name": "Duplicado"}, headers=headers)
    assert r1.status_code == 201
    r2 = client.post("/api/children", json={"name": "Duplicado"}, headers=headers)
    assert r2.status_code == 409


def test_response_detail_and_task_status_flow():
    token = register_parent("resptest@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child
    r_child = client.post("/api/children", json={"name": "Detalle"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    # Crear response directo
    r_resp = client.post(f"/api/children/{cid}/responses", json={"text": "Hola mundo"}, headers=headers)
    assert r_resp.status_code == 202
    resp_id = r_resp.json()["response_id"]
    task_id = r_resp.json()["task_id"]
    # Consultar detalle (puede estar aún QUEUED pero analysis_json None)
    detail = client.get(f"/api/responses/{resp_id}")
    assert detail.status_code == 200
    # Estado de tarea
    status = client.get(f"/api/response-status/{task_id}")
    assert status.status_code == 200
    assert "status" in status.json()
