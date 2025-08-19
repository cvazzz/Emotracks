import json
from datetime import datetime, timezone

import redis
from celery.result import AsyncResult

from .celery_app import celery_app
from .db import session_scope
from .models import Response, ResponseStatus
from .grok_client import analyze_text as grok_analyze
from .alert_rules import evaluate_auto_alerts
from .metrics import TASK_COUNTER
from sqlalchemy import select  # (posible uso futuro, no estricto)
from .settings import settings
from .audio_utils import normalizar_audio, extraer_features_audio
import os
import wave
import contextlib


def _extract_duration_seconds(path: str) -> float | None:
    """Extracción simple de duración para WAV; otros formatos se omiten por ahora.
    Devuelve None si no se puede determinar."""
    if not path or not os.path.isfile(path):
        return None
    # Solo WAV rápido sin dependencias externas
    if not path.lower().endswith(".wav"):
        return None
    try:
        with contextlib.closing(wave.open(path, "rb")) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception:
        return None
    return None


@celery_app.task(name="analyze.text")
def analyze_text_task(payload: dict) -> dict:
    """Tarea simulada de análisis de texto (mock)."""
    text = payload.get("text", "")
    audio_path = payload.get("audio_path")
    audio_duration = _extract_duration_seconds(audio_path) if audio_path else None
    audio_features_extra = {}
    if audio_path and settings.enable_audio_features:
        try:
            norm_path = normalizar_audio(audio_path)
            feats = extraer_features_audio(norm_path)
            audio_features_extra.update(feats)
        except Exception:
            pass
    response_id = payload.get("response_id")
    payload_child_id = payload.get("child_id")
    # Allow forcing intensity (test support) else mock default 0.2 / 0.9 for high text tokens
    forced = payload.get("force_intensity")
    auto_intensity = 0.9 if "ALTO" in text.upper() else 0.2
    intensity_value = forced if isinstance(forced, (int, float)) else auto_intensity
    # Si Grok habilitado delegar (manteniendo compatibilidad con force_intensity para tests)
    if forced is not None:  # forzamos stub para pruebas deterministas
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
    else:
        try:
            result = grok_analyze(text)
        except Exception:
            # Fallback a mock simple (no fuerza intensidades altas salvo palabra ALTO)
            result = {
                "primary_emotion": "Neutral" if not text else "Mixto",
                "intensity": intensity_value,
                "polarity": "Neutro",
                "keywords": [],
                "tone_features": None,
                "audio_features": None,
                "transcript": text,
                "confidence": 0.5,
                "model_version": "mock-worker-fallback-exc",
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            }
    # Placeholder: si audio_path y no transcript, mantener campo para futura transcripción
    if audio_path and not result.get("transcript"):
        result["transcript"] = "<audio_pending_transcription>"
    if audio_duration is not None or audio_features_extra:
        af = result.get("audio_features") or {}
        if audio_duration is not None:
            af["duration_sec"] = audio_duration
        af.update(audio_features_extra)
        result["audio_features"] = af
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
                    # Guardar duración en columna si se obtuvo
                    if audio_duration is not None:
                        try:
                            row.audio_duration_sec = audio_duration
                        except Exception:
                            pass
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
