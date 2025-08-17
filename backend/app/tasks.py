import json
from datetime import datetime, timezone

import redis
from celery.result import AsyncResult

from .celery_app import celery_app
from .db import session_scope
from .models import Response, ResponseStatus
from .settings import settings


@celery_app.task(name="analyze.text")
def analyze_text_task(payload: dict) -> dict:
    """Tarea simulada de análisis de texto (mock)."""
    text = payload.get("text", "")
    response_id = payload.get("response_id")
    result = {
        "primary_emotion": "Neutral" if not text else "Mixto",
        "intensity": 0.2,
        "polarity": "Neutro",
        "keywords": [],
        "tone_features": None,
        "audio_features": None,
        "transcript": text,
        "confidence": 0.5,
        "model_version": "mock-worker-0.1",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if response_id:
        try:
            with session_scope() as s:
                row = s.get(Response, response_id)
                if row is not None:
                    row.emotion = result["primary_emotion"]
                    row.status = ResponseStatus.COMPLETED
                    row.analysis_json = result
        except Exception:
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
        pass
    return result


def enqueue_analysis_task(payload: dict) -> str:
    res = analyze_text_task.delay(payload)
    return res.id


def get_task_status(task_id: str) -> str:
    res = AsyncResult(task_id, app=celery_app)
    return res.status
