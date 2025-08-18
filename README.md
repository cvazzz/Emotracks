# EmoTrack Kids (skeleton)

![CI](../../actions/workflows/ci.yml/badge.svg) ![Coverage](https://codecov.io/gh/your-org/emotrack/branch/main/graph/badge.svg)

Local-first scaffold for FastAPI + Celery + Redis + Postgres, with placeholders for a Flutter Web frontend.

## Quick start (Docker Compose)

1. Copy env file
   - Windows PowerShell:
     - Copy-Item .env.example .env
2. Start services
   - docker compose up --build
3. Visit API docs
   - http://localhost:8000/docs
4. Frontend (opcional):
   - Construye Flutter Web y sirve estáticos desde FastAPI (ver sección Frontend Web)

## Endpoints (MVP actual)
- GET /health
- Auth: POST /api/auth/register, /api/auth/login, /api/auth/refresh, GET /api/auth/me
- Children: POST /api/children, GET /api/children, GET /api/children/{id}, PATCH /api/children/{id}, DELETE /api/children/{id}
- Attach responses existentes: POST /api/children/{id}/attach-responses { response_ids: [] }
- Crear response directo para child: POST /api/children/{id}/responses
- POST /api/analyze-emotion (sync mock)
- POST /api/submit-responses → 202 { task_id }
- GET /api/response-status/{task_id}
- WS /ws (stub; future Redis Pub/Sub bridge)
- GET /api/responses (latest)
- GET /api/responses/{id} (detail with analysis_json)
- GET /api/dashboard/{child_ref} (child_ref = id numérico o nombre legacy; incluye objeto child si existe)
- Alerts: POST /api/alerts, GET /api/alerts?child_id=, DELETE /api/alerts/{id} (migración 0006; severities: info|warning|critical)
- Métricas Prometheus: GET /metrics

### Realtime / WebSocket
- Conexión: `GET ws://localhost:8000/ws`
- Mensajes del servidor (JSON):
   - `{"type": "welcome"}` al conectar.
   - `{"type": "task_queued", "task_id": ..., "response_id": ..., "status": "QUEUED"}` cuando se encola una tarea.
   - `{"type": "task_completed", "response_id": ..., "status": "COMPLETED", "emotion": "..."}` cuando finaliza el análisis (mock actual).
- Si Redis no está disponible se envía `warning` y el socket funciona en modo eco.

### Export OpenAPI
Para exportar el JSON del esquema OpenAPI a `openapi.json`:

```bash
python - <<'PY'
from backend.app.main import app
import json
import pathlib
pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2))
print('openapi.json generado')
PY
```

### Tareas rápidas (Makefile / PowerShell)

Makefile (Linux/Mac):
```
make install
make test
make openapi
make coverage
```

PowerShell (Windows) con `scripts\tasks.ps1`:
```
pwsh scripts/tasks.ps1 install
pwsh scripts/tasks.ps1 test
pwsh scripts/tasks.ps1 openapi
```

## Structure
- backend/app: FastAPI app, Celery app, tasks, settings
- worker: (uses same image; tasks live under backend/app)
- frontend: placeholder for Flutter (Riverpod, go_router)
- backend/static: salida de Flutter Web si decides empaquetar UI junto al backend
- uploads: audio uploads (future)
- scripts: helper scripts

## Notes
- Queue: Celery; Broker: Redis (REDIS_URL)
- DB dev: Postgres (docker-compose), fallback SQLite later if needed
- Logging: structlog JSON renderer
- Realtime: WebSocket + Redis Pub/Sub (to be wired in)

## Migrations (Alembic)
- Generate DB (already initialized by app on first run) or run migrations:
   - docker compose exec api alembic upgrade head
   - To create a new migration: docker compose exec api alembic revision -m "msg" --autogenerate
 - Optional: set AUTO_MIGRATE=1 in env to auto-run `alembic upgrade head` on startup (dev/tests only).

## Tests
- Backend unit tests con pytest. Celery corre en modo eager (sin broker externo) y se fuerza SQLite (`tests/conftest.py`).
- Aislamiento por test: fixture que limpia tablas principales (`user`, `child`, `response`).
- Ejecutar: `pytest -q`.
- `celery_app` en tests habilita `task_store_eager_result` para poder consultar estado sin warnings.
- CI genera reporte de cobertura (coverage.xml) como artifact y lo sube a Codecov (añade `CODECOV_TOKEN` en secrets para habilitar el badge).
- Migraciones recientes: `0007_response_indexes_and_tz` añade índices (`emotion`, `created_at`, `(child_id, created_at)`) y asegura TZ en Postgres.

## Métricas
- Counter Prometheus: `emotrack_requests_total{method,endpoint,http_status}`
- Histogram Prometheus: `emotrack_request_latency_seconds{method,endpoint}` (latencia en segundos)
 - Counter Errores: `emotrack_request_errors_total{method,endpoint,exception}`
 - Counter Tareas: `emotrack_tasks_total{task_name,status}` (status: success|error)
Visibles en `/metrics`.

### Alertas
- Campos: `rule_version` añadido (migración 0008) para versionar reglas automáticas / deduplicación.
- Motor de reglas v2 implementado (archivo `alert_rules.py`):
   - `intensity_high`: intensidad >= 0.8 (critical)
   - `emotion_streak`: 3 emociones consecutivas iguales no neutrales (warning)
   - `avg_intensity_high`: promedio de intensidad últimas 5 >= 0.7 (warning)
   - Ventana de deduplicación: 10 minutos por (child_id, type, rule_version).
   - Publicación de nuevas alertas por Redis Pub/Sub en canal `emotrack:updates` como evento `alert_created`.

   ### Rate limiting & PII
   - Middleware de rate limiting in-memory (configurable por env: RATE_LIMIT_REQUESTS_PER_MINUTE / RATE_LIMIT_BURST via settings).
   - Redacción de PII básica (emails y teléfonos) en logs si `pii_redaction_enabled`.
   - Para producción se recomienda sustituir por Redis token bucket y regex más robustos.

## Pre-commit
Instalar hooks (ruff, black, prettier):
```
pip install pre-commit
pre-commit install
```
Ejecutar manualmente sobre todo el repo:
```
pre-commit run --all-files
```

## Frontend Web (Flutter) y servicio desde el backend

Opción A: Servir con el backend (recomendado para demo)

1) Construir Flutter Web

   Windows PowerShell:
   - scripts\build_frontend.ps1

   Esto ejecuta `flutter build web --release` y copia la salida a `backend/static/`.

2) Levantar servicios

   - docker compose up --build

3) Acceder

   - Navega a http://localhost:8000/ para la web (sirve index.html) y http://localhost:8000/docs para la API.

Notas:
- El backend monta estáticos automáticamente si existe `backend/static` (o si apuntas STATIC_DIR a otra ruta). Busca también `frontend/build/web` como fallback en modo desarrollo.
- Variable opcional: STATIC_DIR para indicar una carpeta específica.

Opción B: Servir Flutter por separado (desarrollo)

1) Ejecuta el dev server de Flutter Web en el folder `frontend/`:
   - flutter run -d chrome

2) Apunta la app a la API en http://localhost:8000 (API_BASE si compilas con define)


