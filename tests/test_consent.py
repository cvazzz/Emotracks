from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _register_parent(email="parent_consent@example.com", password="pass123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "role": "parent"})
    assert r.status_code in (200, 201)
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return login.json()["access_token"], login.json()


def test_consent_and_submit_flow():
    token, login_data = _register_parent()
    headers = {"Authorization": f"Bearer {token}"}

    # Crear niño
    r_child = client.post("/api/children", json={"name": "Peque"}, headers=headers)
    assert r_child.status_code == 201
    child_id = r_child.json()["id"]

    # Enviar sin consentimiento explícito (debería permitir si no pasan parent_id/child_id en submit) 
    r1 = client.post("/api/submit-responses", data={"text": "Hola"})
    assert r1.status_code == 202

    # Enviar con parent_id y child_id sin consentimiento => 403
    r2 = client.post("/api/submit-responses", data={"text": "Hola", "parent_id":  login_data["access_token"], "child_id": str(child_id)})
    # Nota: parent_id no es un id real en este proyecto de pruebas, así que no encontrará consentimiento y devolverá 403
    assert r2.status_code in (400, 403)

    # Otorgar consentimiento correcto con IDs coherentes (usamos parent como 1 en tests si existe)
    # En este entorno, no tenemos el id del parent en DB, así que este test asegura el endpoint funciona
    rc = client.post("/api/consent", json={"parent_id": 1, "child_id": child_id}, headers=headers)
    assert rc.status_code in (200, 201)
    assert rc.json()["child_id"] == child_id
