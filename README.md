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
- Auth: POST /api/auth/register, /api/auth/login, /api/auth/refresh, POST /api/auth/logout (revoca refresh), GET /api/auth/me
- Children: POST /api/children, GET /api/children, GET /api/children/{id}, PATCH /api/children/{id}, DELETE /api/children/{id}
- Attach responses existentes: POST /api/children/{id}/attach-responses { response_ids: [] }
- Crear response directo para child: POST /api/children/{id}/responses
- POST /api/analyze-emotion (sync mock)
- POST /api/submit-responses → 202 { task_id }
- GET /api/response-status/{task_id}
- WS /ws (realtime + fallback eco sin Redis)
- GET /api/responses (latest)
- GET /api/responses/{id} (detail with analysis_json)
- GET /api/dashboard/{child_ref}
- Alerts: POST /api/alerts, GET /api/alerts?child_id=, DELETE /api/alerts/{id}
- Métricas Prometheus: GET /metrics

### Realtime / WebSocket
- Conexión: `GET ws://localhost:8000/ws`
- Mensajes:
  - `{"type": "welcome"}` al conectar
  - `{"type": "task_queued", ...}` al encolar
  - `{"type": "task_completed", ...}` al finalizar (mock)
  - `{"type": "alert_created", "alert": { ... }}` si Redis disponible
- Sin Redis: mensaje `warning` y modo echo

### Export OpenAPI
Para exportar el JSON del esquema OpenAPI a `openapi.json`:

```bash
python - <<'PY'
from backend.app.main import app
import json, pathlib
pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2))
print('openapi.json generado')
PY
```

### Tareas rápidas
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
 - Rate limit: `emotrack_rate_limit_hits_total{key,action}` (accepted|blocked)

### Alertas
- `rule_version` para versionado (v2)
- Reglas (thresholds configurables por env):
  - `intensity_high`: intensidad >= ALERT_INTENSITY_HIGH_THRESHOLD (default 0.8) → critical
  - `emotion_streak`: ALERT_EMOTION_STREAK_LENGTH consecutivas iguales (default 3) → warning
  - `avg_intensity_high`: promedio últimas ALERT_AVG_INTENSITY_COUNT >= ALERT_AVG_INTENSITY_THRESHOLD (defaults 5 / 0.7) → warning
- Dedup 10 minutos
- Publicación `alert_created` via Redis canal `emotrack:updates`

### Rate limiting & PII
- Middleware híbrido (Redis + memoria)
- Env: RATE_LIMIT_REQUESTS_PER_MINUTE, RATE_LIMIT_BURST
- PII redaction (emails, teléfonos) si `PII_REDACTION_ENABLED=1`

### Tokens / Logout
- Refresh revocable: POST /api/auth/logout (body: refresh_token)
- /api/auth/refresh devuelve 401 `refresh_revocado` si token revocado

## Pre-commit
Instalar hooks (ruff, black, prettier):
```
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Frontend Flutter (build & serve)
1. `flutter build web --release`
2. Copiar build a `backend/static/`
3. Levantar backend (sirve index.html)

O usar dev server (flutter run -d chrome) apuntando a API http://localhost:8000


