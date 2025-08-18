from prometheus_client import Counter, Histogram

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

# Celery task metrics
TASK_COUNTER = Counter(
    "emotrack_tasks_total", "Total de tareas Celery procesadas", ["task_name", "status"]
)

__all__ = [
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "REQUEST_ERRORS",
    "TASK_COUNTER",
    "RATE_LIMIT_HITS",
]
