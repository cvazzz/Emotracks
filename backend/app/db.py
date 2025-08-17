import time
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .settings import settings
import os
import subprocess
from sqlalchemy import inspect, text

engine = create_engine(settings.database_url, echo=False)

_init_lock = Lock()
_initialized = False


def init_db() -> None:
    last_err = None
    for _ in range(10):
        try:
            SQLModel.metadata.create_all(engine)
            # Ensure SQLite has new columns (lightweight shim for tests/dev)
            if engine.dialect.name == "sqlite":
                _ensure_sqlite_columns()
            # Optional: Auto-run Alembic migrations in dev/tests
            if os.getenv("AUTO_MIGRATE") == "1":
                try:
                    subprocess.run([
                        "alembic", "upgrade", "head"
                    ], check=True, cwd=os.getcwd())
                except Exception:
                    pass
            return
        except Exception as e:
            last_err = e
            time.sleep(2)
    if last_err:
        raise last_err


def ensure_db_initialized() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        init_db()
        _initialized = True


@contextmanager
def session_scope() -> Iterator[Session]:
    # Ensure schema exists even if startup hook didn't run (e.g., tests)
    ensure_db_initialized()
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as s:
        yield s



def _ensure_sqlite_columns() -> None:
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("response")}
        if "analysis_json" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE response ADD COLUMN analysis_json TEXT"))
    except Exception:
        # Best-effort; ignore if not applicable
        pass
