import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DYNAMIC_CONFIG_ENABLED", "1")

from backend.app.main import app  # noqa: E402
from backend.app.auth import _revoked_refresh_tokens_memory  # noqa: E402
from backend.app.db import init_db  # noqa: E402

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def _register(email: str, role: str = "parent"):
    r = client.post("/api/auth/register", json={"email": email, "password": "pass123", "role": role})
    if r.status_code not in (200, 201, 400):
        raise AssertionError(r.text)
    login = client.post("/api/auth/login", json={"email": email, "password": "pass123"})
    assert login.status_code == 200
    return login.json()


def test_alert_thresholds_admin_update_and_persist():
    # Crear admin
    admin_tokens = _register("admin@example.com", role="admin")
    access = admin_tokens["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    # GET inicial
    g1 = client.get("/api/config/alert-thresholds", headers=headers)
    assert g1.status_code == 200
    body1 = g1.json()
    # Update
    new_payload = {
        "intensity_high": body1["intensity_high"] + 0.01,
        "emotion_streak_length": body1["emotion_streak_length"] + 1,
        "avg_count": body1["avg_count"] + 1,
        "avg_threshold": body1["avg_threshold"] + 0.01,
    }
    u = client.put("/api/config/alert-thresholds", json=new_payload, headers=headers)
    assert u.status_code == 200, u.text
    # GET again must reflect updated values
    g2 = client.get("/api/config/alert-thresholds", headers=headers)
    assert g2.status_code == 200
    body2 = g2.json()
    assert body2 == new_payload


def test_alert_severities_override_changes_generated_alerts():
    admin_tokens = _register("admin2@example.com", role="admin")
    headers = {"Authorization": f"Bearer {admin_tokens['access_token']}`".replace('`','')}
    # Establecer severidades nuevas
    sev_payload = {"intensity_high": "warning", "emotion_streak": "critical", "avg_intensity_high": "info"}
    u = client.put("/api/config/alert-severities", json=sev_payload, headers=headers)
    assert u.status_code == 200, u.text
    # Crear parent y child y forzar intensidad alta
    parent = _register("parentsev@example.com", role="parent")
    p_headers = {"Authorization": f"Bearer {parent['access_token']}"}
    rc = client.post("/api/children", json={"name": "SChild"}, headers=p_headers)
    assert rc.status_code == 201
    cid = rc.json()["id"]
    # Fuerza intensidad alta
    rr = client.post(f"/api/children/{cid}/responses", json={"text": "alto", "force_intensity": 0.95}, headers=p_headers)
    assert rr.status_code == 202
    # Listar alertas y verificar severity override (warning para intensity_high)
    lst = client.get(f"/api/alerts?child_id={cid}", headers=p_headers)
    assert lst.status_code == 200
    items = lst.json()["items"]
    ih = [a for a in items if a["type"] == "intensity_high"]
    assert ih, f"No se generó intensity_high: {items}"
    assert ih[0]["severity"] == "warning"
    # Cleanup: restaurar severidades por defecto para no afectar otros tests
    reset_payload = {"intensity_high": "critical", "emotion_streak": "warning", "avg_intensity_high": "warning"}
    client.put("/api/config/alert-severities", json=reset_payload, headers=headers)


def test_refresh_revocation_persistent_db_lookup():
    # Crear usuario parent y obtener refresh
    tokens = _register("persist@example.com", role="parent")
    refresh = tokens["refresh_token"]
    # Logout para revocar
    rlog = client.post("/api/auth/logout", params={"refresh_token": refresh})
    assert rlog.status_code == 204
    # Simular reinicio (limpiar cache memoria)
    _revoked_refresh_tokens_memory.clear()
    # Intentar refrescar -> debe seguir revocado (detecta en DB)
    r2 = client.post("/api/auth/refresh", params={"token": refresh})
    assert r2.status_code == 401
    assert r2.json().get("detail") == "refresh_revocado"
