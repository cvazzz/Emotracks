"""Cliente para la API de Grok (o proveedor similar).

Provee función analyze_text() que retorna dict normalizado listo para persistir
en response.analysis_json. Implementa:
 - Timeout configurable
 - Retries exponenciales con jitter
 - Manejo de 429/5xx
 - Fallback a mock interno si deshabilitado o error definitivo
"""
from __future__ import annotations

import time
import random
import json
from typing import Any, Dict
import http.client
from urllib.parse import urlparse
import ssl

from .settings import settings
from .metrics import GROK_REQUEST_LATENCY, GROK_REQUESTS, GROK_FALLBACKS


class GrokClientError(Exception):
    pass


def _do_http_json(url: str, method: str, headers: dict, body: dict | None, timeout: float) -> tuple[int, dict, str]:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    context = ssl.create_default_context() if parsed.scheme == "https" else None
    conn = conn_cls(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), timeout=timeout, context=context)  # type: ignore[arg-type]
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    data = json.dumps(body).encode() if body is not None else None
    conn.request(method.upper(), path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode(errors="ignore")
    try:
        j = json.loads(raw) if raw else {}
    except Exception:
        j = {}
    return resp.status, j, raw


def _mock_analysis(text: str) -> dict:
    return {
        "primary_emotion": "Mixto" if text.strip() else "Neutral",
        "intensity": 0.2,
        "polarity": "Neutro",
        "keywords": [],
        "tone_features": None,
        "audio_features": None,
        "transcript": text,
        "confidence": 0.5,
        "model_version": "mock-grok-fallback",
        "analysis_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def analyze_text(text: str) -> dict:
    if not settings.grok_enabled or not settings.grok_api_key:
        fb = _mock_analysis(text)
        try:
            GROK_REQUESTS.labels("disabled").inc()
            GROK_FALLBACKS.labels("disabled").inc()
        except Exception:
            pass
        return fb
    url = "https://api.x.ai/v1/analysis"  # Placeholder
    headers = {
        "Authorization": f"Bearer {settings.grok_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": settings.grok_model,
        "input": text,
        "tasks": ["emotion"],
    }
    retries = 3
    backoff = 0.6
    last_error: str | None = None
    start_time = time.time()
    for attempt in range(retries):
        try:
            status, j, raw = _do_http_json(url, "POST", headers, payload, settings.grok_timeout_seconds)
            if status == 200 and j:
                em_data = j.get("emotion", {}) if isinstance(j, dict) else {}
                primary = em_data.get("primary") or em_data.get("label") or "Neutral"
                intensity = float(em_data.get("intensity", 0.2))
                result = {
                    "primary_emotion": primary,
                    "intensity": intensity,
                    "polarity": em_data.get("polarity", "Neutro"),
                    "keywords": em_data.get("keywords", []),
                    "tone_features": None,
                    "audio_features": None,
                    "transcript": text,
                    "confidence": float(em_data.get("confidence", 0.5)),
                    "model_version": f"grok:{settings.grok_model}",
                    "analysis_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                try:
                    GROK_REQUESTS.labels("ok").inc()
                    GROK_REQUEST_LATENCY.labels("ok").observe(time.time() - start_time)
                except Exception:
                    pass
                return result
            if status in (401, 403):
                last_error = f"auth_error_{status}"
                break
            if status == 429:
                last_error = "rate_limited"
            elif status >= 500:
                last_error = f"server_{status}"
            else:
                last_error = f"unexpected_{status}"
        except Exception as e:  # noqa: BLE001
            last_error = f"exception:{e.__class__.__name__}"
        time.sleep(backoff + random.random() * 0.2)
        backoff *= 1.8
    fb = _mock_analysis(text)
    fb["model_version"] += f";fallback_reason={last_error}"
    try:
        GROK_REQUESTS.labels("fallback").inc()
        GROK_FALLBACKS.labels(last_error or "unknown").inc()
        GROK_REQUEST_LATENCY.labels("fallback").observe(time.time() - start_time)
    except Exception:
        pass
    return fb


__all__ = ["analyze_text", "GrokClientError"]
