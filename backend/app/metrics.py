from prometheus_client import Counter, Histogram, Gauge

# HTTP metrics
REQUEST_COUNT = Counter(
    "emotrack_requests_total", "Total de requests HTTP", ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "emotrack_request_latency_seconds", "Latencia de requests HTTP", ["method", "endpoint"]
)
REQUEST_ERRORS = Counter(
    "emotrack_request_errors_total", "Errores (exceptions) en requests HTTP", ["method", "endpoint", "exception"]
)

RATE_LIMIT_HITS = Counter(
    "emotrack_rate_limit_hits_total", "Eventos de rate limiting (accepted vs blocked)", ["key", "action"]
)

ALERTS_TOTAL_BY_TYPE = Gauge(
    "emotrack_alerts_total", "Alertas creadas por tipo (acumulativo)", ["type", "severity"]
)

# Celery task metrics
TASK_COUNTER = Counter(
    "emotrack_tasks_total", "Total de tareas Celery procesadas", ["task_name", "status"]
)

# AI provider metrics
GROK_REQUEST_LATENCY = Histogram(
    "emotrack_grok_request_latency_seconds", "Latencia de llamadas a Grok", ["outcome"]
)
GROK_REQUESTS = Counter(
    "emotrack_grok_requests_total", "Llamadas a Grok (resultado)", ["outcome"]
)
GROK_FALLBACKS = Counter(
    "emotrack_grok_fallbacks_total", "Usos de fallback de análisis (mock)", ["reason"]
)

__all__ = [
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "REQUEST_ERRORS",
    "TASK_COUNTER",
    "RATE_LIMIT_HITS",
    "ALERTS_TOTAL_BY_TYPE",
    "GROK_REQUEST_LATENCY",
    "GROK_REQUESTS",
    "GROK_FALLBACKS",
]
