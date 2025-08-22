rompt mejorado y actualizado: Desarrollo completo — EmoTrack Kids (MVP → producción)
Resumen del proyecto (visión general)
Crea EmoTrack Kids, una plataforma local-first (despliegue local reproducible y empaquetado para un único hosting/VPS sin dependencia obligatoria de nube paga) orientada al bienestar emocional de niños de 6 a 10 años, con posibilidad de escalar a producción (VPS/Kubernetes).
La plataforma combina:

Frontend para web y futuro móvil: Flutter Web (posibilidad de compilar la misma base a Android/iOS). Si la experiencia necesita ser extremadamente interactiva o “tipo juego”, Unity WebGL puede considerarse como alternativa para la capa visual/gamificación pesada.

Backend robusto en Python + FastAPI.

IA: integración con Grok (o proveedor equivalente) a través de un adaptador; fallback a modelos locales (Hugging Face, Whisper para transcripción).

Datos: SQLite para desarrollo local, PostgreSQL para producción; Redis para cache y broker de cola.

Contenerización: Docker + Docker Compose para local; manifiestos/k8s opcionales para producción.

Seguridad, privacidad y cumplimiento: diseño orientado a COPPA/GDPR y buenas prácticas de protección infantil.

Objetivos clave
Análisis emocional multimodal (texto + transcripción de audio + análisis de tono) con Grok y fallback local.

UX infantil accesible, gamificada y reconfortante usando animaciones (Animanate si existe integración para Flutter; si no, Rive / Lottie / Flare).

Panel de padres con insights, alertas y recomendaciones accionables.

Directorio y portal para psicólogos (registro, verificación documental, gestión de citas).

Infraestructura reproducible localmente + camino claro a producción en VPS/Kubernetes.

Privacidad por diseño: consentimiento parental, eliminación/exportación de datos, cifrado.

Elección tecnológica (justificación breve)
Flutter Web: permite compartir código entre web y móvil (iOS/Android), buena performance en UI declarativa y soporte para animaciones (Rive/Lottie). Ideal si quieres una única base para web + app en el futuro.

Unity WebGL (opcional): para experiencias tipo juego con físicas avanzadas/3D — trade-off: mayor tamaño de build, menos SEO, mayor complejidad.

FastAPI (Python): tipado, rendimiento, excelente para integrar modelos ML/IA (Grok, HuggingFace, Whisper) y bien documentado (OpenAPI).

PostgreSQL para producción y SQLite para dev: equilibrio entre robustez y facilidad local.

Redis: cache, sesión opcional y broker para Celery/RQ (procesamiento asíncrono de transcripciones/analítica).

Docker: reproducibilidad local y despliegue simple.

CI: GitHub Actions para tests, builds y generación de artefactos (opcional).

Observabilidad: logs estructurados, Sentry, Prometheus + Grafana (opcional).

Requisitos funcionales (detallado)
Flow niño — interfaz (Flutter Web)
Pantalla bienvenida con selección/creación de perfil (parent-linked) y selección de emoji inicial.

Formulario de 3 preguntas (texto + micrófono):

¿Qué fue lo mejor de tu día?

¿Hubo algo que te hizo sentir mal?

¿Cómo te sientes ahora?

Opciones de entrada: texto libre o grabación de audio (wav/webm/opus, 16 kHz, mono recomendado).

Al enviar: audio → backend (multipart) → transcripción (Whisper local o servicio) → análisis Grok/HF → almacenamiento.

Selección de emoji interactiva (animaciones reactivas).

Gamificación: puntos, logros, mascota virtual que evoluciona.

Animaciones: Rive / Lottie / Animanate (si tiene SDK Flutter) para reacciones del avatar.

Flow padre — dashboard
Gestión de múltiples perfiles infantiles por padre.

Vistas agregadas (por niño): diario/semana/mes con filtros por fecha.

Visualizaciones: gráfico de barras (distribución de emociones), gráfico de líneas (tendencia), tabla de respuestas con análisis detallado.

Alertas automáticas y notificaciones (ej.: 3+ días negativos, intensidad alta, discrepancia emoji-IA).

Recomendaciones generadas por IA (texto breve y acciones sugeridas).

Exportación CSV/PDF de registros.

Contacto/solicitud de cita con psicólogos.

Flow psicólogo — panel profesional
Página “Únete a nosotros” (registro + subida de documentos).

Panel con calendario, gestión de citas (confirmar, reprogramar, cancelar).

Historial de sesiones, resumen y posibilidad de subir adjuntos (PDF).

Sistema de valoración de consultas por padres (empatía, claridad, resultados).

Comunicación segura (mensajería simple o canal de contacto).

API & contratos (JSON examples) — actualizados con tareas asíncronas
POST /api/submit-responses (multipart/form-data)
Request fields: parent_id, child_id, responses[] (cada item: question_id, text_answer optional, selected_emoji, audio_file optional, timestamp)
Response 202 Accepted — processing in background:

json
Copiar
Editar
{
  "status": "accepted",
  "task_id": "uuid-1234",
  "message": "Transcription and emotion analysis queued."
}
Then worker updates DB when ready; clients can poll GET /api/response-status/{task_id}.
Nuevo: /api/response-status/{task_id} devuelve también:
{
  "task_id": "uuid-1234",
  "celery_status": "SUCCESS|PENDING|...",
  "progress": 85,
  "phase": "TRANSCRIPTION_QUEUED",
  "response_id": 42,
  "db_status": "COMPLETED",
  "analysis": { ... } // presente sólo si completed
}

Endpoint listado de tareas recientes:
GET /api/tasks/recent?child_id=123&limit=20
Respuesta:
{
  "items": [
     {"response_id": 42, "task_id": "uuid", "status": "COMPLETED", "progress": 100, "phase": "DONE", "emotion": "Mixto", "created_at": "..."}
  ],
  "limit": 20,
  "offset": 0
}

Eventos WebSocket (canal emotrack:updates):
 - task_queued {task_id, response_id}
 - analysis_started {response_id}
 - transcription_queued {response_id}
 - transcription_ready {response_id}
 - task_completed {response_id, emotion}
 - alert_created {alert: {...}}

Fases y progreso heurístico:
 QUEUED (0)
 ANALYSIS_RUNNING (30)
 FEATURES_EXTRACTED (70)
 TRANSCRIPTION_QUEUED (85)
 DONE (100)

POST /api/analyze-emotion (sync, for testing)
Request:

json
Copiar
Editar
{ "text": "Me siento triste porque perdí a mi amigo", "child_age": 8 }
Response:

json
Copiar
Editar
{ "analysis": { /* EmotionalAnalysis schema below */ } }
GET /api/dashboard/{child_id}?from=YYYY-MM-DD&to=YYYY-MM-DD
Response includes aggregated metrics, time series, alerts.

GET /api/children/{parent_id}, POST /api/children, PUT /api/children/{id}.

GET /api/psychologists, POST /api/psychologists/register (multipart for docs), POST /api/admin/psychologists/verify.

POST /api/psychologists/appointments, GET /api/psychologists/dashboard/{id}.

GET /api/alerts/{child_id}, GET /api/recommendations/{child_id}.

Esquema de análisis emocional (EmotionalAnalysis) — versión ampliada
json
Copiar
Editar
{
  "primary_emotion": "Triste",
  "secondary_emotions": ["Frustrado", "Inseguro"],
  "intensity": 0.83,              // 0.0 - 1.0
  "polarity": "Negativo Moderado",// Positivo Extremo, Positivo Leve, Neutro, Negativo Leve, Negativo Moderado, Negativo Severo
  "keywords": ["perdí", "amigo"],
  "context_tags": ["problemas con amistades"],
  "emoji_concordance": false,
  "hypothesis_trigger": "conflicto con amigo en el recreo",
  "tone_features": {
    "pitch_mean_hz": 220.5,
    "pitch_std_hz": 12.2,
    "speech_rate_wpm": 95,
    "voice_intensity_db": -20.0,
    "voice_emotion_probabilities": {"sad": 0.8, "neutral": 0.2}
  },
  "audio_features": {
    "duration_sec": 3.4,
    "duration_s": 3.4, // alias para compatibilidad
    "sample_rate": 16000,
    "silence_ratio": 0.12,
    "mfcc_mean": [ ... ]
  },
  "transcript": "Me senti mal porque ...",
  "confidence": 0.92,
  "recommended_action": "Proponer técnica simple de respiración y actividad lúdica con un adulto",
  "model_version": "grok-v2.1",
  "analysis_timestamp": "2025-08-01T14:12:00Z"
}
Nota: audio_features y tone_features provienen del pipeline de audio (librosa/pyAudioAnalysis/torch model). voice_emotion_probabilities son un vector de probabilidad de emociones detectadas en voz.

Modelos de datos sugeridos (Pydantic / SQLModel)
python
Copiar
Editar
from pydantic import BaseModel
from typing import List, Optional, Dict

class ToneFeatures(BaseModel):
    pitch_mean_hz: float
    pitch_std_hz: float
    speech_rate_wpm: float
    voice_intensity_db: float
    voice_emotion_probabilities: Dict[str, float]

class EmotionalAnalysis(BaseModel):
    primary_emotion: str
    secondary_emotions: List[str] = []
    intensity: float
    polarity: str
    keywords: List[str] = []
    context_tags: List[str] = []
    emoji_concordance: bool
    hypothesis_trigger: Optional[str]
    tone_features: Optional[ToneFeatures]
    audio_features: Optional[Dict[str, float]]
    transcript: Optional[str]
    confidence: float
    recommended_action: Optional[str]
    model_version: str
    analysis_timestamp: str

class ResponseRecord(BaseModel):
    id: Optional[int]
    child_id: int
    question_id: int
    text_answer: Optional[str]
    audio_path: Optional[str]
    analysis: EmotionalAnalysis
    created_at: str
SQL (ejemplo simplificado)

sql
Copiar
Editar
CREATE TABLE children (...);
CREATE TABLE parents (...);
CREATE TABLE responses (
  id SERIAL PRIMARY KEY,
  child_id INT REFERENCES children(id),
  question_id INT,
  text_answer TEXT,
  audio_path TEXT,
  analysis_json JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
Backend — arquitectura técnica y componentes
Stack: Python 3.12+, FastAPI, Uvicorn (gunicorn + uvicorn workers opcional), SQLModel/SQLAlchemy + Alembic para migraciones, Pydantic.

Background workers: Celery (con Redis broker) o RQ (con Redis). Encolar tareas pesadas: transcripción, extracción audio-features, llamada a Grok/HF.

Transcripción: Whisper (local: tiny/small/medium dependiendo recursos) o servicio externo (configurable).

Audio analysis: librosa, pyAudioAnalysis, pyannote para VAD, o modelos PyTorch.

Grok adapter: grok_client que abstrae provider — implementar retries, rate-limit handling, model versioning and provenance.

Caching & rate-limiting: Redis + fastapi-limiter.

File storage: uploads/ local; para producción soportar montaje de volumen o S3-similar (opcional). En local usar SQLCipher for DB encryption optional.

Auth: OAuth2 / JWT tokens; roles: admin, parent, psychologist, child-lite (niño no inicia sesión completo). 2FA opcional para psicólogos.

Admin endpoints para verificar psicólogos y revisar documentación.

Sanitization and moderation: profanity filter, PII detection and redaction pipeline (muy importante en contenidos infantiles).

API docs: automatic OpenAPI/Swagger (FastAPI).

Frontend — Flutter Web (arquitectura y librerías)
Stack: Flutter (stable), Riverpod (estado), go_router (routing) o flutter_modular, Rive/Lottie (animaciones), charts_flutter o syncfusion_flutter_charts (gráficas), flutter_sound o recorder_wav para grabación, speech_to_text (opcional en cliente), http/dio para requests.

Estructura:

lib/child/ (formulario, avatar, mascota).

lib/parent/ (dashboard, charts, filters).

lib/psychologist/ (registro, calendar).

lib/shared/ (auth, services, widgets).

Grabación: cliente graba audio y lo sube al backend; validaciones (duración máxima, formato).

Animaciones: usar Rive para interacciones reactivas; mapear estados emocionales a animaciones predefinidas. Si prefieres Animanate y existe SDK, integrarlo; si no, Rive/Lottie.

Responsiveness: diseño pensado para tablet y mobile first.

Testing: widget tests y integration tests.

Tareas asíncronas & performance
Pipeline sugerido para una respuesta con audio:

Frontend envía audio + metadatos → /api/submit-responses → backend almacena archivo y encola tarea.

Worker: transcribe (Whisper/local) → extrae audio features (librosa) → envía texto+features a grok_client.analyze() (o a modelo HF local) → guarda analysis_json en DB y notifica resultado por websocket/notifications.

Si alerta crítica → notifica a padre (email/push) y marca para revisión humana.

Mantener petición inicial muy ligera (202 Accepted) para UX; entregar análisis por websocket/polling cuando termine.

Seguridad, privacidad y cumplimiento (detallado)
Consentimiento parental obligatorio: checkbox + registro y timestamp; no permitir usar perfil de niño sin consentimiento explícito.

Roles y permisos (RBAC): diseño cuidadoso de endpoints y datos visibles por rol.

Autenticación: OAuth2 + JWT, refresh tokens, revocación de sesión.

Protección de contraseñas: bcrypt / argon2.

Cifrado en tránsito: HTTPS/TLS (Let's Encrypt para VPS).

Cifrado en reposo: PostgreSQL TDE opcional o cifrado de columnas sensibles (pgcrypto); SQLite con SQLCipher en local-dev.

Estado actual (implementación MVP)
- Rate limiting básico por usuario/IP con Redis (si disponible) o memoria (fallback).
- Redacción de PII (emails y teléfonos) en logs si está activado.
- Consentimiento: endpoint POST /api/consent con (parent_id, child_id). En /api/submit-responses se exige consentimiento cuando se pasan parent_id y child_id; si parent_id no es numérico o no existe consentimiento, responde 403 consent_required.
- Auth: JWT con refresh y revocación persistente (tabla revokedtoken). Logout revoca el refresh.
- Cifrado en reposo (opcional y transparente para el cliente):
  - Cuando ENABLE_ENCRYPTION=1 y ENCRYPTION_KEY (Fernet) está definido, el backend almacena analysis_json y transcript cifrados en columnas binarias (analysis_json_enc, transcript_enc) y devuelve valores descifrados en las APIs.
  - Por compatibilidad, si el cifrado está desactivado, se guarda en texto/JSON como antes.
  - Requiere migración en Postgres (Alembic) para añadir columnas; en SQLite de dev se parchea automáticamente.

Retención y borrado: endpoints para exportar/borrar datos personales (GDPR Right to Erasure).

Moderación: pipeline para detectar contenido preocupante; alertas y flujo de revisión humana.

Seguridad aplicativa: validación input (Pydantic), protección CSRF/XSS en la UI, rate limiting, Content Security Policy.

Secret management: .env para local + Docker secrets, y vault (opcional para producción).

Auditoría y logs: almacenar logs de acceso y de acciones sensibles para auditoría (retención parametrizable).

Legal: incluir texto legal y aviso de privacidad en onboarding y pedir revisión legal antes de producción (COPPA / leyes locales).

Observabilidad y mantenimiento
Logging: estructurado (JSON) con loguru o structlog.

Errors: integrar Sentry para alertas de errores.

Metrics: Prometheus exporter para FastAPI + Grafana dashboards (latencia, tasks en cola, errores).

Tracing: OpenTelemetry opcional.

Backups: script de backup DB + versiónar uploads/ si necesario.

DevOps y despliegue local → producción
Local dev: Docker Compose con servicios:

app (FastAPI), db (Postgres o SQLite en dev), redis (broker/cache), worker (Celery/RQ), frontend (Flutter dev server) — or build run via flutter build web and serve static via FastAPI or nginx.

Packaging único: build Flutter → copiar a backend/static/ → Docker image que sirve la app (uvicorn + static). Entregar docker-compose.yml y script scripts/build_and_package.sh.

Producción: desplegar en VPS; opción usar docker-compose o Kubernetes (manifiestos). TLS con nginx + certbot.

CI/CD: GitHub Actions que: run tests, build backend image, build Flutter web, run linters, produce artifacts. Opcional: push a registry privado.

Rollback: versionado semántico y tags en git.

Variables de entorno clave (añadidos recientes)
- ENABLE_ENCRYPTION=0|1 → activa el cifrado de columnas sensibles (analysis_json, transcript).
- ENCRYPTION_KEY=<clave_fernet> → clave base64 generada con Fernet.generate_key(). Ejemplo (Python):
  - from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())
- PII_REDACTION_ENABLED=0|1 → controla la redacción básica de PII en logs.

Pruebas y QA
Backend: pytest, pruebas unitarias, mocks para grok_client, tests de integración con DB en memoria.

Worker: tests de tasks en Celery using redis test instance.

Frontend: widget tests e2e (integration_test Flutter).

E2E: Playwright / Cypress (para la web) si necesitas validar flujos completo.

Carga: pruebas de stress ligeras (simular X requests concurrentes para transcripción/analisis).

Seed data & demo
Archivo backend/seed_data.py con create_demo_data() que:

Crea varios padres y 5–7 niños con 7 días de respuestas variadas.

Simula respuestas de audio + texto con diversas emociones e intensidades, incluyendo casos que disparen alertas.

Crea 4 psicólogos (2 verificados, 2 pendientes) y citas simuladas.
Script: python backend/seed_data.py --reset.

Reglas de alerta y recomendaciones (configurables)
Alertas:

intensity >= 0.9 y polarity en Negativo → ALERTA CRÍTICA.

3 días consecutivos con primary_emotion en categoría negativa → ALERTA.

emoji_concordance == false y diferencia de intensidad > 0.4 → marcar discrepancia.

Keywords de alto riesgo (ej.: "lastimarse", "no quiero vivir") → ALERTA CRÍTICA y ruta de emergencia con revisión humana.

Recomendaciones: reglas basado en context_tags y primary_emotion → acciones sencillas (respiración, pedir jugar con un adulto, contactar psicólogo). Estas recomendaciones deben ser revisables y anotadas por profesionales.

Gamificación y animaciones (UX)
Mascota con estados (neutral, happy, sad, energetic, tired) y animaciones mapeadas a emociones.

Logros: 5 días seguidos, grabó su sentimiento, mejor frente a X días.

Evitar sobreestimulación: máximo 2 animaciones simultáneas, controles de volumen y tiempo.

Criterios de éxito (MVP → demo)
Obligatorios:

Interfaz niño funcional con 3 preguntas, micrófono (grabación y subida) y animaciones reactivas.

Backend que encola y procesa audios: transcripción + análisis (Grok/fallback) y guarda EmotionalAnalysis.

Dashboard padres con gráficos (distribución y tendencia) y filtros por fecha.

Directorio de psicólogos con registro y subida de documentación.

Panel psicólogos con calendario y gestión de citas.

Seed data cargada y demo reproducible.

Seguridad mínima: consentimiento parental, auth básica, cifrado en tránsito.

Opcionales (si hay tiempo):

Export CSV/PDF completa.

Mensajería simple padre–psicólogo.

Panel admin para ver/validar alertas y psicólogos.

Entregables
Repositorio emotrackkids-mvp/ con frontend/ (Flutter) y backend/ (FastAPI).

README.md con pasos de instalación y operación para dev y producción mínima.

scripts/ para dev, build y packaging.

seed_data.py.

OpenAPI/Swagger autogenerada.

Tests automatizados y guía para ejecutarlos.

Dockerfiles y docker-compose.yml.

Priorización por fases (sugerida)
Fase 1 — MVP (2 semanas): Backend core, DB, endpoints principales, Flutter UI básico para niño (texto + audio upload asíncrono), grok_client mock, seed data.

Fase 2 (2 semanas): Worker + transcripción (Whisper local o servicio), Grok real, Dashboard padres básico con charts, reglas de alerta simples.

Fase 3 (2 semanas): Portal psicólogos, subida docs, verificación manual, notificaciones y export.

Fase 4: Hardening de seguridad, observabilidad, packaging y optimización de UX (gamificación/mascota), tests e2e, CI/CD.

Notas finales para el desarrollador (y para evaluar a un agente IA)
Implementar un grok_adapter que permita cambiar proveedor sin tocar la lógica de negocio.

Separar código síncrono (endpoints) de código asíncrono (workers) para facilitar debugging y pruebas.

Mantener config en config/*.yml o env vars y no hardcodear secretos.

Human-in-the-loop: para alertas críticas la notificación debe pasar por revisión humana (psicólogo/designado) antes de tomar medidas fuera de la app.

Pruebas de seguridad básicas (scans de dependencias, linters, SAST básico).

Documentar claramente las limitaciones del análisis IA y dejar logs/metadata que permiten auditar decisiones del modelo (model_version, confidence, timestamp).

Antes de despliegue a usuarios reales, revisar con asesoría legal las políticas de privacidad y cumplimiento local (COPPA/GDPR).

Anexo — Endpoints implementados (MVP actual)
- Auth: POST /api/auth/register, POST /api/auth/login, POST /api/auth/refresh, POST /api/auth/logout, GET /api/auth/me.
- Respuestas: POST /api/submit-responses (202, async) y GET /api/response-status/{task_id} con {celery_status, status, progress, phase, analysis?}.
- Tareas: GET /api/tasks/recent (listado con progreso) y GET /api/responses, GET /api/responses/{id}.
- Children: POST /api/children, GET /api/children, GET /api/children/{id}, PATCH /api/children/{id}, DELETE /api/children/{id}, POST /api/children/{id}/responses (crea y encola), POST /api/children/{id}/attach-responses.
- Psychologists: POST /api/psychologists (admin), GET /api/psychologists (filtro verified opcional), POST /api/admin/psychologists/{id}/verify.
- Consent: POST /api/consent.
- Alerts: POST /api/alerts, GET /api/alerts?child_id=, DELETE /api/alerts/{id}.
- Recomendaciones: GET /api/recommendations/{child_id}.
- Realtime: WS /ws (Redis Pub/Sub si disponible; fallback eco si no).

Diferencias vs. plan original (para alinear UI y QA)
- Psychologists register: por ahora lo crea un admin vía POST /api/psychologists (JSON). El flujo con subida de documentos multipart queda para la fase de verificación documental.
- Alerts list: en lugar de GET /api/alerts/{child_id} se usa GET /api/alerts?child_id=.
- Children listing: los endpoints no llevan parent_id en la ruta; el parent se infiere del token.
- Cifrado en reposo: implementado a nivel de columnas con Fernet (flag-enable), además de las opciones de TDE/SQLCipher mencionadas para prod/local respectivamente.