"""Utilidades de procesamiento de audio (placeholders iniciales).

Objetivos futuros:
 - Normalizar formatos a WAV mono 16 kHz (ffmpeg)
 - Extraer características (librosa / praat) para enriquecer `tone_features`
 - Integrar Whisper (local o API) para transcripción bajo flag ENABLE_TRANSCRIPTION

Implementación actual (MVP):
 - normalizar_audio(): copiar/retornar path original (sin cambio)
 - extraer_features_audio(): retorna dict mínimo con duración si se puede inferir
"""
from __future__ import annotations

import os
import wave
import contextlib
import subprocess
import tempfile
from typing import Optional, Dict
from .settings import settings


def normalizar_audio(path: str, target_dir: str = "uploads") -> str:
    """Normaliza a WAV mono 16k si ENABLE_AUDIO_NORMALIZATION está activo.
    Devuelve path del archivo normalizado (igual al original si ya es WAV válido o si la normalización está desactivada).
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if not settings.enable_audio_normalization:
        return path
    os.makedirs(target_dir, exist_ok=True)
    # Si ya es WAV 16k mono podemos reutilizarlo (heurística mínima)
    if path.lower().endswith('.wav'):
        try:
            with contextlib.closing(wave.open(path, 'rb')) as wf:
                if wf.getnchannels() == 1 and wf.getframerate() == 16000:
                    return path
        except Exception:
            pass
    out_path = os.path.join(target_dir, f"norm_{os.path.basename(path)}.wav")
    cmd = [settings.ffmpeg_path, '-y', '-i', path, '-ac', '1', '-ar', '16000', out_path]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return out_path
    except Exception:
        return path  # fallback silencioso


def _duracion_wav(path: str) -> Optional[float]:
    if not path.lower().endswith('.wav'):
        return None
    try:
        with contextlib.closing(wave.open(path, 'rb')) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception:
        return None
    return None


def extraer_features_audio(path: str) -> Dict:
    """Devuelve un dict con features básicos (duración si WAV)."""
    feats: Dict[str, float] = {}
    dur = _duracion_wav(path)
    if dur is not None:
        feats["duration_sec"] = dur
    return feats


def transcribir_audio(path: str) -> Optional[str]:
    """Transcribe usando faster-whisper si ENABLE_TRANSCRIPTION=1 y lib disponible.
    Retorna transcript o None si no procede.
    """
    if not settings.enable_transcription:
        return None
    try:
        # Import perezoso
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None
    try:
        model = WhisperModel(settings.transcription_model, device="cpu")
        segments, info = model.transcribe(path, beam_size=1)
        text_parts = [s.text.strip() for s in segments if getattr(s, 'text', '').strip()]
        return " ".join(text_parts).strip() or None
    except Exception:
        return None


__all__ = ["normalizar_audio", "extraer_features_audio", "transcribir_audio"]
