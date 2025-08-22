from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _register_parent(email="parent_rec@example.com", password="pass123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "role": "parent"})
    assert r.status_code in (200, 201)
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_recommendations_endpoint():
    token = _register_parent()
    headers = {"Authorization": f"Bearer {token}"}

    # Crear niño y algunas respuestas para tener emoción dominante
    r_child = client.post("/api/children", json={"name": "Recom"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]

    # Crear varias respuestas con force_intensity para completar rápido
    for i in range(3):
        r = client.post(f"/api/children/{cid}/responses", json={"text": "Hola", "force_intensity": 0.9}, headers=headers)
        assert r.status_code == 202

    # Obtener recomendaciones
    rec = client.get(f"/api/recommendations/{cid}", headers=headers)
    assert rec.status_code == 200
    items = rec.json().get("items", [])
    assert isinstance(items, list)
    assert len(items) > 0
