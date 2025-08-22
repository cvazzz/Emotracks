import json
from datetime import datetime, timezone

import redis
from celery.result import AsyncResult

from .celery_app import celery_app
from .db import session_scope
from .models import Response, ResponseStatus
from .grok_client import analyze_text as grok_analyze, _ensure_contract
from .alert_rules import evaluate_auto_alerts
from .metrics import TASK_COUNTER
from sqlalchemy import select  # (posible uso futuro, no estricto)
from .settings import settings
from .audio_utils import normalizar_audio, extraer_features_audio, transcribir_audio, comprimir_audio
from .events import publish_event
from .metrics import TRANSCRIPTION_REQUESTS, TRANSCRIPTION_LATENCY
import os
import wave
import contextlib
from .crypto_utils import encrypt_text


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


@celery_app.task(name="transcribe.audio")
def transcribe_audio_task(payload: dict) -> dict:
    """Tarea dedicada para transcripción de audio."""
    audio_path = payload.get("audio_path")
    response_id = payload.get("response_id")
    
    if not audio_path or not os.path.isfile(audio_path):
        return {"error": "audio_file_not_found"}
    
    start_time = datetime.now().timestamp()
    
    try:
        TRANSCRIPTION_REQUESTS.labels("attempt").inc()
        transcript = transcribir_audio(audio_path)
        
        if transcript:
            # Actualizar response con transcript
            if response_id:
                try:
                    with session_scope() as s:
                        row = s.get(Response, response_id)
                        if row and row.analysis_json:
                            analysis = row.analysis_json.copy()
                            analysis["transcript"] = transcript
                            # Optional encryption path
                            if settings.enable_encryption:
                                row.analysis_json = None
                                row.analysis_json_enc = encrypt_text(json.dumps(analysis))
                                if not row.transcript or row.transcript == "<audio_pending_transcription>":
                                    row.transcript = None
                                    row.transcript_enc = encrypt_text(transcript)
                            else:
                                row.analysis_json = analysis
                                if not row.transcript or row.transcript == "<audio_pending_transcription>":
                                    row.transcript = transcript
                            s.add(row)
                except Exception:
                    pass
            # Emitir evento websocket (Redis pub/sub) de transcripción lista
            publish_event("transcription_ready", response_id=response_id, status="COMPLETED")
            
            try:
                TRANSCRIPTION_REQUESTS.labels("success").inc()
                TRANSCRIPTION_LATENCY.labels("success").observe(datetime.now().timestamp() - start_time)
            except Exception:
                pass
            
            return {"transcript": transcript, "status": "success"}
        else:
            try:
                TRANSCRIPTION_REQUESTS.labels("failed").inc()
                TRANSCRIPTION_LATENCY.labels("failed").observe(datetime.now().timestamp() - start_time)
            except Exception:
                pass
            return {"error": "transcription_failed"}
            
    except Exception as e:
        try:
            TRANSCRIPTION_REQUESTS.labels("error").inc()
            TRANSCRIPTION_LATENCY.labels("error").observe(datetime.now().timestamp() - start_time)
        except Exception:
            pass
        return {"error": str(e)}


@celery_app.task(name="analyze.text")
def analyze_text_task(payload: dict) -> dict:
    """Tarea simulada de análisis de texto (mock)."""
    text = payload.get("text", "")
    audio_path = payload.get("audio_path")
    audio_duration = _extract_duration_seconds(audio_path) if audio_path else None
    audio_features_extra = {}
    normalized_path = audio_path
    # Emitir evento de inicio de análisis
    publish_event("analysis_started", response_id=payload.get("response_id"))
    if audio_path and settings.enable_audio_features:
        try:
            normalized_path = normalizar_audio(audio_path)
            # Comprimir si está habilitado
            if settings.enable_audio_compression:
                normalized_path = comprimir_audio(normalized_path)
            feats = extraer_features_audio(normalized_path)
            audio_features_extra.update(feats)
        except Exception:
            pass
    transcript_added = False
    if normalized_path and settings.enable_transcription:
        # Enviar a cola separada de transcripción (no bloquear análisis principal)
        try:
            transcribe_audio_task.delay({
                "audio_path": normalized_path,
                "response_id": payload.get("response_id")
            })
        except Exception:
            pass
        # Publicar evento de progreso
    publish_event("transcription_queued", response_id=payload.get("response_id"))
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
            result = grok_analyze(text, audio_features_extra)
        except Exception:
            # Fallback a mock simple (no fuerza intensidades altas salvo palabra ALTO)
            result = {
                "primary_emotion": "Neutral" if not text else "Mixto",
                "intensity": intensity_value,
                "polarity": "Neutro",
                "keywords": [],
                "tone_features": None,
                "audio_features": audio_features_extra if audio_features_extra else None,
                "transcript": text,
                "confidence": 0.5,
                "model_version": "mock-worker-fallback-exc",
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            }
    # Normalizar contrato (rellenar campos faltantes)
    result = _ensure_contract(result)
    # Mantener placeholder si no hay transcript inmediato
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
                    # Optional encryption for analysis_json and transcript
                    try:
                        if settings.enable_encryption:
                            row.analysis_json = None
                            row.analysis_json_enc = encrypt_text(json.dumps(result))
                            if result.get("transcript"):
                                row.transcript = None
                                row.transcript_enc = encrypt_text(result.get("transcript"))
                        else:
                            row.analysis_json = result
                            if result.get("transcript"):
                                row.transcript = result.get("transcript")
                    except Exception:
                        # Fallback to plaintext if encryption fails
                        row.analysis_json = result
                        if result.get("transcript"):
                            row.transcript = result.get("transcript")
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
                                for a in new_alerts:
                                    publish_event(
                                        "alert_created",
                                        alert={
                                            "id": a.id,
                                            "child_id": a.child_id,
                                            "alert_type": a.type,
                                            "severity": a.severity,
                                            "rule_version": a.rule_version,
                                            "message": a.message,
                                        },
                                    )
                            except Exception:
                                pass
        except Exception:
            status_label = "error"
            pass
    publish_event(
        "task_completed",
        response_id=response_id,
        status="COMPLETED",
        emotion=result["primary_emotion"],
    )
    try:
        TASK_COUNTER.labels(task_name, status_label).inc()
    except Exception:
        pass
    return result


@celery_app.task(name="cleanup.audio")
def cleanup_old_audio_task() -> dict:
    """Tarea de limpieza periódica de archivos de audio antiguos."""
    try:
        from .audio_utils import limpiar_archivos_antiguos
        cleaned_count = limpiar_archivos_antiguos()
        return {"status": "success", "cleaned_files": cleaned_count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def enqueue_analysis_task(payload: dict) -> str:
    res = analyze_text_task.delay(payload)
    return res.id


def get_task_status(task_id: str) -> str:
    res = AsyncResult(task_id, app=celery_app)
    return res.status
