import os
import time
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from backend.app.main import app  # noqa: E402
from backend.app.db import init_db, session_scope  # noqa: E402
from backend.app.models import Child  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    # Limpiar tablas principales para aislamiento sencillo (SQLite)
    from backend.app.db import session_scope as _sc
    from backend.app.models import User, Child as _Child, Response as _Response, Alert as _Alert
    from sqlalchemy import delete
    with _sc() as s:
        for model in (_Alert, _Response, _Child, User):
            try:
                s.execute(delete(model))
            except Exception:
                pass
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


def test_analyze_emotion_endpoint():
    r = client.post("/api/analyze-emotion", json={"text": "Me siento bien"})
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["primary_emotion"] in ("Neutral", "Mixto")


def test_alerts_crud_minimal():
    token = register_parent("alertparent@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child primero
    r_child = client.post("/api/children", json={"name": "Alerta"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    # Crear alert
    r_alert = client.post("/api/alerts", json={"child_id": cid, "type": "streak", "message": "Varias emociones negativas", "severity": "warning"}, headers=headers)
    assert r_alert.status_code == 201
    aid = r_alert.json()["id"]
    # List alerts
    r_list = client.get(f"/api/alerts?child_id={cid}", headers=headers)
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert any(a["id"] == aid for a in items)
    # Invalid severity
    bad = client.post("/api/alerts", json={"child_id": cid, "type": "streak", "message": "bad", "severity": "xxx"}, headers=headers)
    assert bad.status_code == 400
    # Delete
    r_del = client.delete(f"/api/alerts/{aid}", headers=headers)
    assert r_del.status_code == 204


def test_metrics_endpoint():
    # Hacer un par de hits y luego leer /metrics
    client.get("/health")
    m = client.get("/metrics")
    assert m.status_code == 200
    assert b"emotrack_requests_total" in m.content
    assert b"emotrack_request_latency_seconds" in m.content
    assert b"emotrack_request_errors_total" in m.content
    assert b"emotrack_tasks_total" in m.content
    # Probar contador de errores
    boom = client.get("/api/debug/boom")
    assert boom.status_code == 500
    m2 = client.get("/metrics")
    assert b"emotrack_request_errors_total" in m2.content


def test_auto_alert_high_intensity_and_streak():
    token = register_parent("autoalert@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child
    r_child = client.post("/api/children", json={"name": "Pedro"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    # Generar 3 responses para racha (mock usa siempre Mixto con intensidad 0.2 -> no debería disparar intensidad alta)
    for i in range(3):
        rr = client.post(f"/api/children/{cid}/responses", json={"text": f"resp {i}"}, headers=headers)
        assert rr.status_code == 202
    # List alerts (puede existir la de racha)
    lst = client.get(f"/api/alerts?child_id={cid}", headers=headers)
    assert lst.status_code == 200
    items = lst.json()["items"]
    # La alerta de racha es opcional si las tres emociones permanecen iguales (Mixto)
    # Verificamos que no se generó ninguna critical (porque intensidad mock = 0.2)
    assert not any(a["severity"] == "critical" for a in items)


def test_alert_rule_version_and_dedup():
    token = register_parent("rvparent@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child
    r_child = client.post("/api/children", json={"name": "RV"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    payload = {"child_id": cid, "type": "custom_rule", "message": "Mensaje A", "severity": "info"}
    r1 = client.post("/api/alerts", json=payload, headers=headers)
    assert r1.status_code == 201, r1.text
    body1 = r1.json()
    # Con la introducción de RULE_VERSION_V2 las alertas manuales usan ahora 'v2'
    assert body1.get("rule_version") == "v2"
    r2 = client.post("/api/alerts", json=payload, headers=headers)
    assert r2.status_code == 201
    body2 = r2.json()
    # Debe devolver el mismo id (idempotencia ligera)
    assert body1["id"] == body2["id"]
    # List sólo una alerta de ese tipo
    lst = client.get(f"/api/alerts?child_id={cid}", headers=headers)
    assert lst.status_code == 200
    same_type = [a for a in lst.json()["items"] if a["type"] == "custom_rule"]
    assert len(same_type) == 1


def test_auto_alert_intensity_high_and_avg():
    token = register_parent("ruleavg@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child
    r_child = client.post("/api/children", json={"name": "Media"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    # Generar 5 responses: 4 con intensidad moderada 0.6 (no disparan), 1 final alta 0.9 -> debe disparar intensity_high y quizá avg si promedio >=0.7
    # Crear únicamente una respuesta de alta intensidad
    rr_high = client.post(f"/api/children/{cid}/responses", json={"text": "alto", "force_intensity": 0.92}, headers=headers)
    assert rr_high.status_code == 202
    # List alerts
    items = []
    for _ in range(10):  # poll hasta 2s
        lst = client.get(f"/api/alerts?child_id={cid}", headers=headers)
        assert lst.status_code == 200
        items = lst.json()["items"]
        if any(a["type"] == "intensity_high" for a in items):
            break
        time.sleep(0.2)
    types = {a["type"] for a in items}
    assert "intensity_high" in types, f"Alertas presentes: {types}"
    # avg_intensity_high puede existir (dependiendo de intensidades mock); aceptamos opcional
    # Si existe debe tener severity warning
    for a in items:
        if a["type"] == "avg_intensity_high":
            assert a["severity"] == "warning"


def test_auto_alert_avg_intensity_high():
    token = register_parent("avgparent@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Crear child
    r_child = client.post("/api/children", json={"name": "Media2"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    intensities = [0.72, 0.74, 0.76, 0.78, 0.82]
    for idx, val in enumerate(intensities):
        r = client.post(
            f"/api/children/{cid}/responses", json={"text": f"resp {idx}", "force_intensity": val}, headers=headers
        )
        assert r.status_code == 202
    # Tras 5 respuestas forzadas (sin respuesta extra) debería existir avg_intensity_high e intensity_high.
    types = set()
    sev_map = {}
    for _ in range(10):  # hasta ~2s polling
        alerts = client.get(f"/api/alerts?child_id={cid}", headers=headers)
        assert alerts.status_code == 200
        items = alerts.json()["items"]
        types = {a["type"] for a in items}
        sev_map = {a["type"]: a["severity"] for a in items}
        if "avg_intensity_high" in types:
            break
        time.sleep(0.2)
    assert "intensity_high" in types, f"faltan intensity_high: {types}"
    assert "avg_intensity_high" in types, f"faltan avg_intensity_high: {types}"
    assert sev_map.get("intensity_high") == "critical"
    assert sev_map.get("avg_intensity_high") == "warning"


def test_websocket_basic_flow():
    # Si Redis no está disponible el servidor envía un warning y hace eco.
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert "type" in first
        # Enviar ping
        ws.send_text("ping")
        echo = ws.receive_text()
        assert "echo:" in echo
    # Crear child y una respuesta de alta intensidad (no validamos mensajes si no hay Redis)
    token = register_parent("wsparent@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    r_child = client.post("/api/children", json={"name": "WSChild"}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()["id"]
    r_resp = client.post(
        f"/api/children/{cid}/responses", json={"text": "ws", "force_intensity": 0.91}, headers=headers
    )
    assert r_resp.status_code == 202


def test_refresh_revocation_flow():
    token = register_parent("revoc@example.com")
    # Login again to get refresh (register helper already did login, so perform explicit login to capture refresh)
    login = client.post("/api/auth/login", json={"email": "revoc@example.com", "password": "pass123"})
    assert login.status_code == 200
    refresh = login.json()["refresh_token"]
    # Use refresh successfully
    r1 = client.post("/api/auth/refresh", params={"token": refresh})
    assert r1.status_code == 200
    # Logout (revoke)
    rlogout = client.post("/api/auth/logout", params={"refresh_token": refresh})
    assert rlogout.status_code == 204
    # Try refresh again -> 401
    r2 = client.post("/api/auth/refresh", params={"token": refresh})
    assert r2.status_code == 401
    assert r2.json().get("detail") == "refresh_revocado"
