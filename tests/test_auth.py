import os
import pytest
from fastapi.testclient import TestClient

# Asegurar BD sqlite temporal para tests si no se define otra
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("AUTO_MIGRATE", "0")

from backend.app.main import app  # noqa: E402
from backend.app.db import init_db, session_scope  # noqa: E402
from backend.app.models import User  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    # limpiar usuarios para evitar colisión de email
    from sqlmodel import select
    with session_scope() as s:
        # Eliminar todos los usuarios con API moderna de SQLModel
        users = s.exec(select(User)).all()
        for u in users:
            s.delete(u)
    yield


def test_register_login_me_flow():
    # Registro
    r = client.post("/api/auth/register", json={"email": "user1@example.com", "password": "pass123"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["email"] == "user1@example.com"

    # Login
    r2 = client.post("/api/auth/login", json={"email": "user1@example.com", "password": "pass123"})
    assert r2.status_code == 200, r2.text
    token = r2.json()["access_token"]
    assert token

    # /me
    r3 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200
    me = r3.json()
    assert me["email"] == "user1@example.com"


def test_login_invalid_password():
    r = client.post("/api/auth/register", json={"email": "user2@example.com", "password": "pass123"})
    assert r.status_code == 201

    bad = client.post("/api/auth/login", json={"email": "user2@example.com", "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "credenciales_invalidas"


def test_me_requires_token():
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_register_duplicate_email():
    r1 = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "pass123"})
    assert r1.status_code == 201
    r2 = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "pass123"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "email_ya_existe"


def test_refresh_and_dashboard_role_enforcement():
    # Registrar usuario parent (permitido en dashboard) y child (no permitido)
    r_parent = client.post("/api/auth/register", json={"email": "parent@example.com", "password": "pass123", "role": "parent"})
    assert r_parent.status_code == 201
    r_child = client.post("/api/auth/register", json={"email": "kid@example.com", "password": "pass123", "role": "child"})
    assert r_child.status_code == 201

    # Login parent
    login_parent = client.post("/api/auth/login", json={"email": "parent@example.com", "password": "pass123"})
    assert login_parent.status_code == 200
    parent_tokens = login_parent.json()
    assert "refresh_token" in parent_tokens

    # Refresh access token
    ref = client.post("/api/auth/refresh", params={"token": parent_tokens["refresh_token"]})
    assert ref.status_code == 200
    new_access = ref.json()["access_token"]
    assert new_access

    # Acceder a dashboard con token válido
    dash = client.get("/api/dashboard/child", headers={"Authorization": f"Bearer {new_access}"})
    assert dash.status_code == 200

    # Login child
    login_child = client.post("/api/auth/login", json={"email": "kid@example.com", "password": "pass123"})
    assert login_child.status_code == 200
    child_access = login_child.json()["access_token"]

    # Dashboard con rol prohibido -> 403
    dash_forbidden = client.get("/api/dashboard/child", headers={"Authorization": f"Bearer {child_access}"})
    assert dash_forbidden.status_code == 403
    assert dash_forbidden.json()["detail"] == "forbidden"
