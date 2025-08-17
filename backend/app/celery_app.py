import os
import sys
from celery import Celery

"""Configuración Celery central.
 - En tests / modo eager: usa memoria para broker y backend.
 - En ejecución normal: Redis (REDIS_URL).
"""

_under_pytest = ("PYTEST_CURRENT_TEST" in os.environ) or ("pytest" in " ".join(sys.argv).lower())
_force_eager = os.getenv("CELERY_EAGER") == "1"

if _under_pytest or _force_eager:
    BROKER_URL = "memory://"
    RESULT_BACKEND = "cache+memory://"
else:
    BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    RESULT_BACKEND = BROKER_URL

celery_app = Celery("emotrack", broker=BROKER_URL, backend=RESULT_BACKEND)

if _under_pytest or _force_eager:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=60,
    worker_max_tasks_per_child=100,
)

try:  # Registrar tareas
    import backend.app.tasks  # noqa: F401
except Exception:
    pass
