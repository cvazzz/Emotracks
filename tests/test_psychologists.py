from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def _register_admin(email="admin_psy@example.com", password="pass123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "role": "admin"})
    assert r.status_code in (200, 201)
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_psychologists_crud_and_verify():
    token = _register_admin()
    headers = {"Authorization": f"Bearer {token}"}

    # Crear psicólogo
    r = client.post("/api/psychologists", json={"name": "Dra. Ana", "email": "ana@psy.com"}, headers=headers)
    assert r.status_code == 201
    psy = r.json()
    assert psy["verified"] is False

    # Verificar
    rv = client.post(f"/api/admin/psychologists/{psy['id']}/verify", headers=headers)
    assert rv.status_code == 200
    assert rv.json()["verified"] is True

    # Listar solo verificados
    lst = client.get("/api/psychologists", params={"verified": True}, headers=headers)
    assert lst.status_code == 200
    items = lst.json().get("items", [])
    assert any(p["id"] == psy["id"] for p in items)
