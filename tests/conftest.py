import sys, os
from typing import Iterator

# Forzar uso de SQLite para pruebas ANTES de importar settings/engine
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Asegura root en sys.path
root = os.path.abspath(os.path.dirname(__file__) + '/..')
if root not in sys.path:
    sys.path.insert(0, root)

import pytest
from sqlmodel import text

from backend.app.db import init_db, engine


@pytest.fixture(autouse=True, scope="function")
def _isolate_db() -> Iterator[None]:
    """Limpia las tablas principales antes de cada test para aislamiento.

    Estrategia simple: DELETE en orden que respete FK (responses antes de child, child antes de user si FK existiera).
    Evitamos recrear esquemas para acelerar. Esto permite eliminar condicionales 409 en tests.
    """
    init_db()  # asegura esquema
    with engine.begin() as conn:
        # Orden: response -> child -> user
        try:
            conn.execute(text("DELETE FROM response"))
        except Exception:
            pass
        try:
            conn.execute(text("DELETE FROM child"))
        except Exception:
            pass
        try:
            conn.execute(text("DELETE FROM user"))
        except Exception:
            pass
    yield


@pytest.fixture
def parent_token() -> str:
    """Registra y retorna un token de un parent nuevo por test."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    email = f"parent_{os.urandom(4).hex()}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "pass123", "role": "parent"})
    assert r.status_code in (200,201), r.text
    login = client.post("/api/auth/login", json={"email": email, "password": "pass123"})
    assert login.status_code == 200
    return login.json()["access_token"]
