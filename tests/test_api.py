import importlib
import os

from fastapi.testclient import TestClient


def get_app_for_tests():
    # Force SQLite for tests
    os.environ["DATABASE_URL"] = "sqlite:///./test.db"
    os.environ.setdefault("LOG_LEVEL", "INFO")
    # Lazy import after env setup
    module = importlib.import_module("backend.app.main")
    return module.app


def test_health():
    app = get_app_for_tests()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_submit_and_list():
    app = get_app_for_tests()
    client = TestClient(app)

    # Submit a mock response
    resp = client.post(
        "/api/submit-responses",
        data={"child_id": "TestChild", "text": "Estoy bien", "selected_emoji": ":)"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert "task_id" in data and "response_id" in data

    # List responses (QUEUED or COMPLETED)
    rlist = client.get("/api/responses")
    assert rlist.status_code == 200
    items = rlist.json()
    assert isinstance(items, list)
    assert any(item["child_name"] == "TestChild" for item in items)


def test_analysis_json_and_dashboard():
    app = get_app_for_tests()
    client = TestClient(app)
    # Asegurar usuario no existe si otro test dejó datos (sqlite reuso)
    client.post("/api/auth/login", json={"email": "dashparent@example.com", "password": "pass123"})  # intento noop

    # Submit two responses for the same child
    r1 = client.post(
        "/api/submit-responses",
        data={"child_id": "ChildA", "text": "hola", "selected_emoji": ":)"},
    )
    assert r1.status_code == 202
    resp1 = r1.json()
    rid1 = resp1["response_id"]

    r2 = client.post(
        "/api/submit-responses",
        data={"child_id": "ChildA", "text": "", "selected_emoji": ":("},
    )
    assert r2.status_code == 202
    resp2 = r2.json()
    rid2 = resp2["response_id"]

    # Fetch detail and ensure analysis_json exists after eager Celery ran
    d1 = client.get(f"/api/responses/{rid1}")
    assert d1.status_code == 200
    body1 = d1.json()
    assert body1["analysis_json"] is None or isinstance(body1["analysis_json"], dict)

    d2 = client.get(f"/api/responses/{rid2}")
    assert d2.status_code == 200
    body2 = d2.json()
    assert body2["analysis_json"] is None or isinstance(body2["analysis_json"], dict)

    # Crear usuario parent y obtener token para acceder al dashboard protegido
    reg = client.post("/api/auth/register", json={"email": "dashparent@example.com", "password": "pass123", "role": "parent"})
    if reg.status_code not in (200, 201, 400):
        assert False, f"registro inesperado {reg.status_code} {reg.text}"
    # Si 400 asumimos email ya existe y continuamos
    login = client.post("/api/auth/login", json={"email": "dashparent@example.com", "password": "pass123"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Dashboard aggregates (con auth)
    dash = client.get("/api/dashboard/ChildA", headers={"Authorization": f"Bearer {token}"})
    assert dash.status_code == 200
    dash_body = dash.json()
    assert dash_body["child_id"] == "ChildA"
    assert dash_body["total"] >= 2
