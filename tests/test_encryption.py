from fastapi.testclient import TestClient
import os
import importlib
import pytest


def _get_client(env: dict[str, str] | None = None) -> TestClient:
    if env:
        for k, v in env.items():
            os.environ[k] = v
    # Reload settings and main to pick up env flags
    import backend.app.settings as s
    importlib.reload(s)
    import backend.app.main as m
    importlib.reload(m)
    return TestClient(m.app)


def _register_parent(client: TestClient, email_prefix: str = "enc_parent"):
    email = f"{email_prefix}_{os.urandom(3).hex()}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "pass123", "role": "parent"})
    assert r.status_code in (200, 201)
    login = client.post("/api/auth/login", json={"email": email, "password": "pass123"})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_encryption_disabled_plaintext_storage():
    client = _get_client({"ENABLE_ENCRYPTION": "0"})
    token = _register_parent(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/children", json={"name": "Nene"}, headers=headers)
    assert r.status_code == 201
    child_id = r.json()["id"]

    # Crear response con force_intensity para generar analysis inmediato
    r2 = client.post(f"/api/children/{child_id}/responses", json={"text": "hola", "force_intensity": 0.5}, headers=headers)
    # Endpoint es async canonicalizado → 202
    assert r2.status_code == 202

    # Listar respuestas recientes y tomar el id
    r_list = client.get("/api/responses")
    assert r_list.status_code == 200
    assert len(r_list.json()) >= 1

    # Obtener detalle y verificar analysis_json presente
    rid = r_list.json()[0]["id"]
    r_detail = client.get(f"/api/responses/{rid}")
    assert r_detail.status_code == 200
    data = r_detail.json()
    assert isinstance(data.get("analysis_json"), dict)


def test_encryption_enabled_encrypts_at_rest():
    # Habilitar cifrado y proporcionar una clave
    fernet = pytest.importorskip("cryptography.fernet")
    key = fernet.Fernet.generate_key().decode()
    client = _get_client({"ENABLE_ENCRYPTION": "1", "ENCRYPTION_KEY": key})

    token = _register_parent(client, "enc_on_parent")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/children", json={"name": "Nena"}, headers=headers)
    assert r.status_code == 201
    child_id = r.json()["id"]

    r2 = client.post(f"/api/children/{child_id}/responses", json={"text": "hola", "force_intensity": 0.6}, headers=headers)
    assert r2.status_code == 202

    # Tomar el response creado
    r_list = client.get("/api/responses")
    rid = r_list.json()[0]["id"]

    # Validar que la API devuelve analysis descifrado
    r_detail = client.get(f"/api/responses/{rid}")
    assert r_detail.status_code == 200
    data = r_detail.json()
    analysis = data.get("analysis_json")
    assert isinstance(analysis, dict)
    assert analysis.get("primary_emotion") is not None

    # Chequear directamente que al menos una de las columnas cifradas no sea None en DB
    # Nota: accedemos a la sesión y modelo para inspección
    from backend.app.db import session_scope
    from backend.app.models import Response

    with session_scope() as s:
        row = s.get(Response, rid)
        assert row is not None
        # Con cifrado activo, analysis_json debería ser None y analysis_json_enc no vacío
        assert row.analysis_json is None
        assert row.analysis_json_enc is not None
        # Transcript puede estar vacío o placeholder según flujo, pero la columna enc debe existir (None o bytes)
        assert hasattr(row, "transcript_enc")
