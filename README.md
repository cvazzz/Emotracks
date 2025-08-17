# EmoTrack Kids (skeleton)

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

## Endpoints
- GET /health
- POST /api/analyze-emotion (sync mock)
- POST /api/submit-responses → 202 { task_id }
- GET /api/response-status/{task_id}
- WS /ws (stub; future Redis Pub/Sub bridge)
- GET /api/responses (latest)
- GET /api/responses/{id} (detail with analysis_json)
- GET /api/dashboard/{child_id}

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
- Backend unit tests with pytest. In CI, Celery runs in eager mode and SQLite is used with a lightweight schema shim for evolving columns like analysis_json.

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


