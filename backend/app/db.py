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
        if "child_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE response ADD COLUMN child_id INTEGER"))
        if "task_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE response ADD COLUMN task_id TEXT"))
        # Audio pipeline new columns (added via migration 0010 in real DBs). For tests/dev on SQLite we patch in-place.
        audio_columns = [
            ("audio_path", "TEXT"),
            ("audio_format", "TEXT"),
            ("audio_duration_sec", "REAL"),
            ("transcript", "TEXT"),
        ]
        for col_name, col_type in audio_columns:
            if col_name not in cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE response ADD COLUMN {col_name} {col_type}"))
                except Exception:
                    pass
        # Best-effort index for audio_path
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_response_audio_path ON response(audio_path)"))
        except Exception:
            pass
        # Create child table if not exists (simple check)
        if "child" not in insp.get_table_names():
            with engine.begin() as conn:
                conn.execute(text("""
                CREATE TABLE child (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    age INTEGER NULL,
                    notes TEXT NULL,
                    parent_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """))
        # Ensure alert table has rule_version if table exists
        if "alert" in insp.get_table_names():
            alert_cols = {c["name"] for c in insp.get_columns("alert")}
            if "rule_version" not in alert_cols:
                try:
                    with engine.begin() as conn:
                        try:
                            conn.execute(text("ALTER TABLE alert ADD COLUMN rule_version VARCHAR(50) NULL"))
                        except Exception:
                            # Fallback: recreate table (SQLite sin ALTER avanzado)
                            conn.execute(text("""
                                CREATE TABLE IF NOT EXISTS alert__new (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    child_id INTEGER NOT NULL,
                                    type TEXT NOT NULL,
                                    message TEXT NOT NULL,
                                    severity TEXT NOT NULL DEFAULT 'info',
                                    rule_version VARCHAR(50) NULL,
                                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    FOREIGN KEY(child_id) REFERENCES child(id)
                                )
                            """))
                            existing_cols = "id, child_id, type, message, severity, created_at"
                            conn.execute(text(f"INSERT INTO alert__new ({existing_cols}) SELECT {existing_cols} FROM alert"))
                            conn.execute(text("DROP TABLE alert"))
                            conn.execute(text("ALTER TABLE alert__new RENAME TO alert"))
                            # Recreate index
                            try:
                                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alert_child_id ON alert(child_id)"))
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        # Best-effort; ignore if not applicable
        pass
