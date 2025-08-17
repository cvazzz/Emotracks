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
