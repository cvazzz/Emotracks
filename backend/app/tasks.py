import json
from datetime import datetime, timezone

import redis
from celery.result import AsyncResult

from .celery_app import celery_app
from .db import session_scope
from .models import Response, ResponseStatus
from .alert_rules import evaluate_auto_alerts
from .metrics import TASK_COUNTER
from sqlalchemy import select  # (posible uso futuro, no estricto)
from .settings import settings


@celery_app.task(name="analyze.text")
def analyze_text_task(payload: dict) -> dict:
    """Tarea simulada de análisis de texto (mock)."""
    text = payload.get("text", "")
    response_id = payload.get("response_id")
    payload_child_id = payload.get("child_id")
    # Allow forcing intensity (test support) else mock default 0.2 / 0.9 for high text tokens
    forced = payload.get("force_intensity")
    auto_intensity = 0.9 if "ALTO" in text.upper() else 0.2
    intensity_value = forced if isinstance(forced, (int, float)) else auto_intensity
    result = {
        "primary_emotion": "Neutral" if not text else "Mixto",
        "intensity": intensity_value,
        "polarity": "Neutro",
        "keywords": [],
        "tone_features": None,
        "audio_features": None,
        "transcript": text,
        "confidence": 0.5,
        "model_version": "mock-worker-0.1",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    task_name = "analyze.text"
    status_label = "success"
    if response_id:
        try:
            with session_scope() as s:
                row = s.get(Response, response_id)
                if row is not None:
                    row.emotion = result["primary_emotion"]
                    row.status = ResponseStatus.COMPLETED
                    row.analysis_json = result
                    s.flush()
                    # Fallback: si la transacción original no ha committeado aún child_id (otro session), usar el del payload
                    if row.child_id is None and payload_child_id is not None:
                        try:
                            row.child_id = int(payload_child_id)
                        except Exception:
                            pass
                    child_id = row.child_id
                    # Evaluate alert rules (intensity_high, streak, avg) centrally
                    if child_id:
                        try:
                            new_alerts = evaluate_auto_alerts(s, child_id, row, result)
                        except Exception:
                            new_alerts = []
                        # Publish alerts via Redis channel
                        if new_alerts:
                            try:
                                r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                                for a in new_alerts:
                                    r.publish(
                                        "emotrack:updates",
                                        json.dumps(
                                            {
                                                "type": "alert_created",
                                                "alert": {
                                                    "id": a.id,
                                                    "child_id": a.child_id,
                                                    "alert_type": a.type,
                                                    "severity": a.severity,
                                                    "rule_version": a.rule_version,
                                                    "message": a.message,
                                                },
                                            }
                                        ),
                                    )
                            except Exception:
                                pass
        except Exception:
            status_label = "error"
            pass
    try:
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        r.publish(
            "emotrack:updates",
            json.dumps(
                {
                    "type": "task_completed",
                    "response_id": response_id,
                    "status": "COMPLETED",
                    "emotion": result["primary_emotion"],
                }
            ),
        )
    except Exception:
        status_label = "error"
        pass
    try:
        TASK_COUNTER.labels(task_name, status_label).inc()
    except Exception:
        pass
    return result


def enqueue_analysis_task(payload: dict) -> str:
    res = analyze_text_task.delay(payload)
    return res.id


def get_task_status(task_id: str) -> str:
    res = AsyncResult(task_id, app=celery_app)
    return res.status
