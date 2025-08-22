"""Eventos centralizados (Pub/Sub) para flujo asíncrono.

publish_event(type_, **fields) publica en el canal configurado
usando Redis si está disponible; si falla, hace no-op silencioso.

Esto evita duplicar lógica de conexión y permite ampliar
en el futuro (persistencia de cola, reintentos, métricas).
"""
from __future__ import annotations

import json
from typing import Any, Dict

import redis

from .settings import settings

CHANNEL = "emotrack:updates"

_redis_client = None

def _get_client():  # lazy init
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        _redis_client = None
    return _redis_client


def publish_event(event_type: str, **fields: Any) -> None:
    payload: Dict[str, Any] = {"type": event_type}
    payload.update(fields)
    client = _get_client()
    if client is None:
        return  # graceful noop (fallback: WebSocket enviará warning al conectar)
    try:
        client.publish(CHANNEL, json.dumps(payload))
    except Exception:
        pass

__all__ = ["publish_event", "CHANNEL"]
