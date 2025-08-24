from __future__ import annotations

"""
Seed/demo de datos para EmoTrack Kids.

Uso:
  python backend/seed_data.py --reset --yes

Variables recomendadas (dev):
  DATABASE_URL=sqlite:///./dev.db

Este script crea:
 - 1 admin, 1 parent
 - 1 niño asociado al parent
 - 6 respuestas de ejemplo (mezcla de emociones)
 - 2 alertas

Respeta el modo de cifrado en reposo si ENABLE_ENCRYPTION=1.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select
from sqlalchemy import delete
import os
import sys

# Ensure project root is on sys.path when running as a script
_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.app.db import init_db, engine
from backend.app.models import UserRole, User, Child, Response, ResponseStatus, Alert
from backend.app.settings import settings
from backend.app.crypto_utils import encrypt_text
from passlib.hash import pbkdf2_sha256


def _get_session() -> Session:
    init_db()
    return Session(engine, expire_on_commit=False)


def _create_user(s: Session, email: str, password: str, role: UserRole) -> User:
    # Si ya existe, devolverlo
    existing = s.exec(select(User).where(User.email == email)).first()
    if existing:
        return existing
    # Crear directo para seed, evitando dependencias de bcrypt
    hashed = pbkdf2_sha256.hash(password)
    u = User(email=email, hashed_password=hashed, role=role)
    s.add(u)
    s.flush()
    return u


def _make_analysis(emotion: str, text: str, intensity: float, transcript: str | None = None) -> dict:
    return {
        "primary_emotion": emotion,
        "intensity": intensity,
        "polarity": 1 if emotion in {"Feliz", "Alegre", "Contento"} else (-1 if emotion in {"Triste", "Enojado", "Ansioso"} else 0),
        "keywords": [emotion.lower()],
        "tone_features": {"pitch_mean_hz": None, "pitch_std_hz": None, "speaking_rate_wps": None},
        "audio_features": {},
        "transcript": transcript or text,
        "confidence": 0.9,
        "model_version": "seed-demo",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _store_analysis(response: Response, analysis: dict) -> None:
    if settings.enable_encryption:
        response.analysis_json = None
        response.analysis_json_enc = encrypt_text(json.dumps(analysis))
        if analysis.get("transcript"):
            response.transcript = None
            response.transcript_enc = encrypt_text(analysis["transcript"])
    else:
        response.analysis_json = analysis
        if analysis.get("transcript"):
            response.transcript = analysis["transcript"]


def run(reset: bool = False) -> None:
    with _get_session() as s:
        if reset:
            # Borrar con ORM para respetar nombres reales de tablas y FKs
            s.exec(delete(Alert))
            s.exec(delete(Response))
            s.exec(delete(Child))
            s.exec(delete(User))
            s.commit()

        # Usuarios
        _ = _create_user(s, "admin@example.com", "admin123", UserRole.ADMIN)
        parent = _create_user(s, "parent@example.com", "parent123", UserRole.PARENT)

        # Niño (get-or-create por (parent_id, name))
        child = s.exec(
            select(Child).where(Child.parent_id == parent.id, Child.name == "Alex")  # type: ignore[arg-type]
        ).first()
        if not child:
            child = Child(name="Alex", age=8, parent_id=parent.id)  # type: ignore[arg-type]
            s.add(child)
            s.flush()

        # Respuestas demo
        examples = [
            ("Feliz", "Jugué con mis amigos", 0.8),
            ("Triste", "Perdí mi juguete", 0.7),
            ("Enojado", "Mi tarea fue difícil", 0.6),
            ("Ansioso", "Mañana tengo examen", 0.65),
            ("Neutral", "Comí pasta", 0.2),
            ("Feliz", "Gané en el juego", 0.9),
        ]
        now = datetime.now(timezone.utc)
        for i, (emo, text, inten) in enumerate(examples):
            r = Response(
                child_name=child.name,
                child_id=child.id,  # type: ignore[arg-type]
                emotion=emo,
                status=ResponseStatus.COMPLETED,
                created_at=now - timedelta(days=len(examples) - i),
            )
            _store_analysis(r, _make_analysis(emo, text, inten))
            s.add(r)

        s.flush()

        # Alertas demo
        a1 = Alert(child_id=child.id, type="high_intensity", message="Alta intensidad reciente", severity="warning")  # type: ignore[arg-type]
        a2 = Alert(child_id=child.id, type="streak_negative", message="Racha negativa detectada", severity="critical")  # type: ignore[arg-type]
        s.add(a1)
        s.add(a2)

        s.commit()

        # Info y conteo
        total_responses = s.exec(select(Response)).all()
        print("Seed completado. Usuario admin: admin@example.com/admin123 — parent: parent@example.com/parent123")
        print(f"Respuestas en DB: {len(total_responses)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed de datos demo")
    parser.add_argument("--reset", action="store_true", help="Limpia tablas principales antes de sembrar")
    parser.add_argument("--yes", action="store_true", help="No solicitar confirmación al hacer reset")
    args = parser.parse_args()

    if args.reset and not args.yes:
        resp = input("Esto borrará datos existentes (tablas principales). ¿Continuar? [y/N]: ")
        if resp.strip().lower() not in {"y", "yes", "s", "si"}:
            print("Cancelado.")
            raise SystemExit(1)

    run(reset=args.reset)
