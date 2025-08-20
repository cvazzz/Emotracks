# EmoTrack Kids (skeleton)

## Endpoints (MVP actual)
 - GET /health
 - Auth: POST /api/auth/register, /api/auth/login, /api/auth/refresh, POST /api/auth/logout (revocENABLE_TRANSCRIPTION=0
MAX_AUDIO_DURATION_SEC=600
MAX_AUDIO_FILE_SIZE_MB=50
DYNAMIC_CONFIG_ENABLED=1
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=20
ENABLE_AUDIO_NORMALIZATION=0
ENABLE_AUDIO_FEATURES=1
TRANSCRIPTION_MODEL=base
TRANSCRIPTION_LANGUAGE=auto
TRANSCRIPTION_CACHE_ENABLED=1
ALLOWED_AUDIO_FORMATS=wav,mp3,webm,ogg,m4a
FFMPEG_PATH=ffmpeg
ENABLE_PROSODIC_FEATURES=0
AUDIO_CLEANUP_DAYS=7
ENABLE_AUDIO_COMPRESSION=0), GET /api/auth/me
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
4. Frontend (opcional):
## Métricas
 - Counter Prometheus: `emotrack_requests_total{method,endpoint,http_status}`
 - Histogram Prometheus: `emotrack_request_latency_seconds{method,endpoint}` (latencia en segundos)
 - Counter Errores: `emotrack_request_errors_total{method,endpoint,exception}`
 - Counter Tareas: `emotrack_tasks_total{task_name,status}` (status: success|error)
 - Rate limit: `emotrack_rate_limit_hits_total{key,action}` (accepted|blocked)
 - Alertas (Gauge acumulativo): `emotrack_alerts_total{type,severity}`
 - Grok AI:
   - `emotrack_grok_requests_total{outcome}` (outcome: ok|fallback|disabled)
   - `emotrack_grok_request_latency_seconds{outcome}`
   - `emotrack_grok_fallbacks_total{reason}` (reason = causa agregada de fallback)
 - Transcripción:
   - `emotrack_transcription_requests_total{status}` (attempt|success|failed)
   - `emotrack_transcription_latency_seconds{status}`
- Children: POST /api/children, GET /api/children, GET /api/children/{id}, PATCH /api/children/{id}, DELETE /api/children/{id}
### Alertas
 - `rule_version` para versionado (v2)
 - Reglas (thresholds configurables por env y opcionalmente en runtime si `DYNAMIC_CONFIG_ENABLED=1`):
    - `intensity_high`: intensidad >= ALERT_INTENSITY_HIGH_THRESHOLD (default 0.8) → critical
    - `emotion_streak`: ALERT_EMOTION_STREAK_LENGTH consecutivas iguales (default 3) → warning
    - `avg_intensity_high`: promedio últimas ALERT_AVG_INTENSITY_COUNT >= ALERT_AVG_INTENSITY_THRESHOLD (defaults 5 / 0.7) → warning
 - Dedup 10 minutos
 - Publicación `alert_created` via Redis canal `emotrack:updates`
 - Métrica Gauge: `emotrack_alerts_total{type,severity}`

#### Overrides en runtime (thresholds)
Requiere rol `admin` y `DYNAMIC_CONFIG_ENABLED=1`.
Endpoints:
 - GET `/api/config/alert-thresholds` (valores efectivos merge env + overrides)
 - PUT `/api/config/alert-thresholds` body ejemplo:
 ```json
 { "intensity_high": 0.85, "emotion_streak_length": 4, "avg_count": 6, "avg_threshold": 0.72 }
 ```
Se persisten en tabla `appconfig` (`alert_*`).
- GET /api/responses/{id} (detail with analysis_json)
### Tokens / Logout
 - Refresh revocable: POST /api/auth/logout (query param: `refresh_token`)
 - Revocación persistente: tabla `revokedtoken` almacena hash SHA-256 (permanece tras reinicio)
 - Redis (si disponible) para lookup rápido (`revoked:refresh:<hash>`)
 - /api/auth/refresh => 401 `refresh_revocado` si token revocado
- Métricas Prometheus: GET /metrics
## Notes
 - Realtime: WebSocket + Redis Pub/Sub (to be wired in)
 - Config dinámico: `DYNAMIC_CONFIG_ENABLED=1` permite overrides vía API admin
### Realtime / WebSocket
- Sin Redis: mensaje `warning` y modo echo
### Export OpenAPI
Para exportar el JSON del esquema OpenAPI a `openapi.json`:

```bash
```
make test

PowerShell (Windows) con `scripts\tasks.ps1`:
```
pwsh scripts/tasks.ps1 install
pwsh scripts/tasks.ps1 test
pwsh scripts/tasks.ps1 openapi
```

## Audio / Transcripción (completado)
- Endpoint `/api/submit-responses` acepta `audio_file` (multipart) además de texto / emoji.
- **Validación**: tamaño máximo (`MAX_AUDIO_FILE_SIZE_MB`), formatos permitidos (`ALLOWED_AUDIO_FORMATS`), duración máxima para WAV.
- Archivo se persiste en `uploads/` con nombre único tras validación.
- **Normalización** opcional vía ffmpeg (flag `ENABLE_AUDIO_NORMALIZATION=1`) a WAV 16k mono.
- **Compresión** opcional (`ENABLE_AUDIO_COMPRESSION=1`) para reducir almacenamiento.
- **Características prosódicas** avanzadas con librosa (`ENABLE_PROSODIC_FEATURES=1`):
  - Pitch (F0) medio y desviación estándar
  - Energía (RMS) y características espectrales
  - MFCC, centroide espectral, ratio de pausas
  - Integración con análisis emocional Grok
- **Transcripción** opcional vía `faster-whisper` con:
  - Caché de transcripciones (`TRANSCRIPTION_CACHE_ENABLED=1`)
  - Cola separada (`transcription` queue) para no bloquear análisis
  - Soporte multiidioma (`TRANSCRIPTION_LANGUAGE=auto|es|en|...`)
- **Limpieza automática**: tarea `cleanup.audio` elimina archivos antiguos (`AUDIO_CLEANUP_DAYS=7`)
- **Endpoint admin**: `/api/admin/cleanup-audio` para limpieza manual
- Columnas DB: `audio_path`, `audio_format`, `audio_duration_sec`, `transcript`

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

## Métricas (resumen actualizado)
- Counter Prometheus: `emotrack_requests_total{method,endpoint,http_status}`
- Histogram Prometheus: `emotrack_request_latency_seconds{method,endpoint}` (latencia en segundos)
 - Counter Errores: `emotrack_request_errors_total{method,endpoint,exception}`
 - Counter Tareas: `emotrack_tasks_total{task_name,status}` (status: success|error)
- Rate limit: `emotrack_rate_limit_hits_total{key,action}` (accepted|blocked)
- Grok: `emotrack_grok_requests_total`, `emotrack_grok_request_latency_seconds`, `emotrack_grok_fallbacks_total`

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

## Variables de entorno clave (parcial)
```
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/emotrack
GROK_ENABLED=1
GROK_API_KEY=sk_...
GROK_MODEL=emotion-base-1
GROK_TIMEOUT_SECONDS=8
ENABLE_TRANSCRIPTION=0
MAX_AUDIO_DURATION_SEC=600
DYNAMIC_CONFIG_ENABLED=1
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=20
 +ENABLE_AUDIO_NORMALIZATION=0
 +ENABLE_AUDIO_FEATURES=1
 +TRANSCRIPTION_MODEL=base
 +FFMPEG_PATH=ffmpeg
```

## Roadmap completado ✅
- ✅ Implementar transcripción (Whisper local) con caché y tiempo máximo.
- ✅ Normalizar formatos (ffmpeg) a 16k mono WAV antes de análisis.
- ✅ Extraer features de audio (pitch, energy, MFCC) para `tone_features`.
- ✅ Endpoint de polling mejorado que incluya progreso de transcripción.
- ✅ Pruebas unitarias de flujo con audio simulado y duración.
- ✅ Validación completa (tamaño, formato, duración).
- ✅ Cola separada para transcripción asíncrona.
- ✅ Compresión y limpieza automática de archivos.
- ✅ Integración prosódica con análisis emocional.

## Próximas mejoras opcionales
- [ ] Dashboard en tiempo real con WebSocket para transcripciones.
- [ ] Análisis de sentimientos por lotes para performance.
- [ ] API de estadísticas de uso de audio/transcripción.
- [ ] Soporte para video (extracción de audio).
- [ ] Modelos Whisper especializados por edad/contexto.


