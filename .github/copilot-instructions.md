# Copilot instructions for EmoTrack Kids

- Source of truth: This repo currently has `intructions.txt` defining the system. Treat it as canonical until code exists; align new files with it.

## Big picture
- Architecture: Flutter Web frontend; Python FastAPI backend; async worker (Celery) via Redis (REDIS_URL=redis://redis:6379/0); DB: PostgreSQL (dev via docker-compose) → PostgreSQL (prod), fallback SQLite; AI: Grok/HF with local fallbacks (Whisper, librosa); Docker Compose for local, optional k8s for prod.
- Principle: Keep HTTP endpoints fast and queue heavy work (transcription, audio features, emotion analysis). Prefer 202 Accepted + `task_id`.
- Security/privacy: COPPA/GDPR-minded. Roles: admin, parent, psychologist, child-lite. Consent required; redact PII; rate-limit; TLS; consider encryption at rest.

## Critical workflows
- Local dev: docker-compose services: app (FastAPI), db (Postgres), redis, worker (Celery), frontend (Flutter dev server) OR build Flutter and serve statics from backend.
- Packaging: `flutter build web` → copy to backend static dir → single image serving API + statics.
- Seed/demo: `python backend/seed_data.py --reset` creates demo data (parents, children, psychologists, responses, alerts).
- Tests: `pytest` for backend/worker; Flutter widget/integration tests; mock `grok_client`.
 - Env/compose quickstart: `.env` keys → `REDIS_URL=redis://redis:6379/0`, `DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/emotrack`; bring up with docker compose and hit `/health`.

## Conventions/patterns
- Layout (planned): `frontend/` (Riverpod, go_router, Rive/Lottie; subfolders: `lib/child`, `lib/parent`, `lib/psychologist`, `lib/shared`), `backend/` (FastAPI, SQLModel/Alembic), `worker/` (async tasks), `uploads/` (audio), `scripts/`, `seed_data.py`.
- API: Per “API & contratos” in `intructions.txt`. Use async submission with polling endpoint.
 - Realtime: Use WebSocket notifications backed by Redis Pub/Sub for task completion/status, with polling as a fallback.
- Adapter: Implement `grok_client` with retries, rate-limit handling, and clear `model_version` provenance; provider-swappable.
- Models: Pydantic/SQLModel matching `EmotionalAnalysis`, `ToneFeatures`, `ResponseRecord`. Store analysis JSON in `responses.analysis_json`.
- Audio: Accept wav/webm/opus (16 kHz mono). Store in `uploads/` with DB metadata.
- Alerts/recs: Implement rules from spec (intensity/polarity thresholds, streaks, keywords, emoji mismatch) in a configurable module.
- Config: `.env` for local, optional `config/*.yml`. Never hardcode secrets. Feature flag provider choice.
- Observability: JSON logs via structlog, optional Sentry, Prometheus exporter for FastAPI.

## Cross-component flow (audio submission)
1) POST `/api/submit-responses` (multipart: text/emoji/audio) → persist file/row, enqueue task → 202 `{ task_id }`.
2) Worker: Whisper transcribe → librosa features → `grok_client.analyze()` → persist `analysis_json`.
3) Client receives WebSocket notification (Redis Pub/Sub) or polls `/api/response-status/{task_id}`; dashboards read aggregates.

## Key endpoints/models (from spec)
- Endpoints: `/api/submit-responses`, `/api/response-status/{task_id}`, `/api/analyze-emotion`, `/api/dashboard/{child_id}`, children/psychologists CRUD, alerts, recommendations.
 - New for MVP scaffold: `/api/responses` returns the latest persisted responses (for UI lists/tests).
- Model example: `EmotionalAnalysis` includes `primary_emotion`, `intensity`, `polarity`, `keywords`, `tone_features`, `audio_features`, `transcript`, `confidence`, `model_version`, `analysis_timestamp`.

## Security notes for agents
- Enforce RBAC, consent checks, input validation, and PII redaction in logs. Prefer async 202 flows for heavy work. Choose stricter defaults when unsure.

## Good first implementation steps
- Minimal FastAPI app + `/health`.
- `POST /api/analyze-emotion` (sync) using mock `grok_client`; define Pydantic models per spec.
- `POST /api/submit-responses` + queue scaffold; persist request, return 202.
- `seed_data.py` to create demo parents/children/responses with mixed emotions.

Note: If the live repo layout diverges, update this document to reflect actual files while staying true to `intructions.txt` intent.
