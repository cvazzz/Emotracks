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
import hashlib
import json
from typing import Optional, Dict
from .settings import settings


class AudioValidationError(Exception):
    """Error de validación de archivo de audio."""
    pass


def validar_audio(file_path: str, file_size_bytes: int) -> None:
    """Valida formato, tamaño y duración del archivo de audio."""
    if not os.path.isfile(file_path):
        raise AudioValidationError("Archivo no encontrado")
    
    # Validar tamaño
    max_size_bytes = settings.max_audio_file_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        raise AudioValidationError(f"Archivo muy grande: {file_size_bytes/1024/1024:.1f}MB > {settings.max_audio_file_size_mb}MB")
    
    # Validar formato por extensión
    ext = os.path.splitext(file_path)[1][1:].lower()
    if ext not in settings.allowed_audio_formats:
        raise AudioValidationError(f"Formato no permitido: {ext}. Permitidos: {', '.join(settings.allowed_audio_formats)}")
    
    # Validar duración si es WAV
    if ext == 'wav':
        duration = _duracion_wav(file_path)
        if duration and duration > settings.max_audio_duration_sec:
            raise AudioValidationError(f"Audio muy largo: {duration:.1f}s > {settings.max_audio_duration_sec}s")


def _get_transcription_cache_key(file_path: str, model: str, language: str) -> str:
    """Genera clave de caché basada en hash del archivo y parámetros."""
    with open(file_path, 'rb') as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    return f"transcription:{file_hash}:{model}:{language}"


def _get_cache_file_path(cache_key: str) -> str:
    """Retorna path del archivo de caché."""
    cache_dir = os.path.join("uploads", ".transcription_cache")
    os.makedirs(cache_dir, exist_ok=True)
    safe_key = cache_key.replace(":", "_").replace("/", "_")
    return os.path.join(cache_dir, f"{safe_key}.json")


def _load_from_cache(cache_key: str) -> Optional[str]:
    """Carga transcripción desde caché si existe y es válida."""
    if not settings.transcription_cache_enabled:
        return None
    
    cache_file = _get_cache_file_path(cache_key)
    try:
        if os.path.isfile(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('transcript')
    except Exception:
        pass
    return None


def _save_to_cache(cache_key: str, transcript: str) -> None:
    """Guarda transcripción en caché."""
    if not settings.transcription_cache_enabled:
        return
    
    cache_file = _get_cache_file_path(cache_key)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({'transcript': transcript}, f, ensure_ascii=False)
    except Exception:
        pass


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
    Incluye caché y soporte multiidioma.
    Retorna transcript o None si no procede.
    """
    if not settings.enable_transcription:
        return None
    
    # Verificar caché primero
    cache_key = _get_transcription_cache_key(path, settings.transcription_model, settings.transcription_language)
    cached = _load_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        # Import perezoso
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None
    
    try:
        model = WhisperModel(settings.transcription_model, device="cpu")
        
        # Configurar idioma
        language = None if settings.transcription_language == "auto" else settings.transcription_language
        
        segments, info = model.transcribe(path, beam_size=1, language=language)
        text_parts = [s.text.strip() for s in segments if getattr(s, 'text', '').strip()]
        transcript = " ".join(text_parts).strip() or None
        
        # Guardar en caché si se obtuvo resultado
        if transcript:
            _save_to_cache(cache_key, transcript)
        
        return transcript
    except Exception:
        return None


__all__ = ["normalizar_audio", "extraer_features_audio", "transcribir_audio", "validar_audio", "AudioValidationError"]
