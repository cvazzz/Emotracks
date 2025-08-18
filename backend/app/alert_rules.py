"""Alert rule evaluation logic (versioned).

Rules (v2):
 - intensity_high: current intensity >= 0.8 (critical)
 - emotion_streak: last 3 emotions identical & non-neutral (warning)
 - avg_intensity_high: average intensity of last 5 >= 0.7 (warning)

Dedup window = 10 minutes per (child_id, type, rule_version).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel import Session

from .models import Alert, Response
from .settings import settings

RULE_VERSION_V2 = "v2"
DEDUP_WINDOW_MINUTES = 10


def _recent_alert_exists(session: Session, child_id: int, alert_type: str, rule_version: str) -> bool:
    """Return True if an alert of same type/version exists inside dedup window.

    Uses select(Alert.id) to satisfy SQLModel typing (scalar select) and avoid Pylance
    complaints about Select[Tuple[Alert]].
    """
    window_start = datetime.now(timezone.utc) - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    # Usamos sqlmodel.select que devuelve SelectOfScalar cuando se pasa una columna declarativa
    stmt = (
        select(Alert.id)  # type: ignore[attr-defined]
        .where(
            Alert.child_id == child_id,
            Alert.type == alert_type,
            Alert.rule_version == rule_version,
            Alert.created_at >= window_start,
        )
        .limit(1)
    )
    existing_id = session.exec(stmt).first()  # type: ignore[arg-type]
    return existing_id is not None


def evaluate_rules_v2(session: Session, child_id: int, new_response: Response, analysis: dict) -> List[Alert]:
    created: List[Alert] = []
    intensity = float(analysis.get("intensity") or 0.0)
    primary = (analysis.get("primary_emotion") or "Unknown").strip() or "Unknown"

    # Rule 1: intensity_high
    if intensity >= settings.alert_intensity_high_threshold and not _recent_alert_exists(
        session, child_id, "intensity_high", RULE_VERSION_V2
    ):
        created.append(
            Alert(
                child_id=child_id,
                type="intensity_high",
                message=f"Intensidad alta detectada ({intensity:.2f})",
                severity="critical",
                rule_version=RULE_VERSION_V2,
            )
        )

    # Obtain last up-to 50 responses then slice last 5
    created_col = getattr(Response, "created_at")
    stmt_recent = select(Response).where(Response.child_id == child_id).order_by(created_col).limit(50)
    recent_rows = list(session.exec(stmt_recent))  # type: ignore[arg-type]
    recent_list = recent_rows[-5:]

    # Rule 2: emotion_streak (3 identical non-neutral)
    streak_len = settings.alert_emotion_streak_length
    tail3 = recent_list[-streak_len:]
    if streak_len > 0 and (
        len(tail3) == streak_len
        and all(r.emotion == primary for r in tail3)
        and primary.lower() not in {"neutral", "none", "unknown"}
        and not _recent_alert_exists(session, child_id, "emotion_streak", RULE_VERSION_V2)
    ):
        created.append(
            Alert(
                child_id=child_id,
                type="emotion_streak",
                message=f"3 respuestas consecutivas con emoción {primary}",
                severity="warning",
                rule_version=RULE_VERSION_V2,
            )
        )

    # Rule 3: avg_intensity_high (average last 5 >= 0.7)
    required_avg_n = settings.alert_avg_intensity_count
    if len(recent_list) >= required_avg_n:
        last_n = recent_list[-required_avg_n:]
        intensities = [(r.analysis_json or {}).get("intensity", 0.0) for r in last_n]
        avg_intensity = sum(intensities) / len(intensities)
        if avg_intensity >= settings.alert_avg_intensity_threshold and not _recent_alert_exists(
            session, child_id, "avg_intensity_high", RULE_VERSION_V2
        ):
            created.append(
                Alert(
                    child_id=child_id,
                    type="avg_intensity_high",
                    message=f"Promedio de intensidad alto en últimas 5 respuestas ({avg_intensity:.2f})",
                    severity="warning",
                    rule_version=RULE_VERSION_V2,
                )
            )

    for a in created:
        session.add(a)
    if created:
        try:
            session.flush()
        except Exception:
            pass
    return created


def evaluate_auto_alerts(session: Session, child_id: int, new_response: Response, analysis: dict) -> List[Alert]:
    return evaluate_rules_v2(session, child_id, new_response, analysis)
