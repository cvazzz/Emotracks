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
from typing import Optional, Dict


def normalizar_audio(path: str, target_dir: str = "uploads") -> str:
    """Placeholder de normalización.
    Retorna el mismo path; si en un futuro se convierte a WAV 16k mono, se colocará el archivo resultante.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return path


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


__all__ = ["normalizar_audio", "extraer_features_audio"]
