import asyncio
from datetime import datetime, timezone
import json
import re
from contextlib import asynccontextmanager
from typing import Optional, Dict, Deque
from collections import defaultdict, deque

import redis
import structlog
import os
from fastapi import Depends, FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import desc
from sqlmodel import select

from .db import get_session, init_db
from .logging_setup import configure_logging
from .models import Response, UserRole, ResponseStatus, Child
from sqlalchemy.exc import IntegrityError
from .settings import settings
from .tasks import enqueue_analysis_task, get_task_status
from .auth import (
    create_access_token,
    verify_password,
    decode_token,
    create_user,
    get_user_by_email,
    create_refresh_token,
    revoke_refresh_token,
    is_refresh_token_revoked,
)
from .schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserOut,
    ChildCreate,
    ChildUpdate,
    ChildOut,
    ChildrenList,
    AlertCreate,
    AlertOut,
    AlertsList,
)
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from .metrics import REQUEST_COUNT, REQUEST_LATENCY, REQUEST_ERRORS, RATE_LIMIT_HITS
from fastapi import Response as FastAPIResponse
from .models import Alert
from .alert_rules import RULE_VERSION_V2
from .alert_rules import evaluate_auto_alerts
from .models import AppConfig

logger = structlog.get_logger()

# ------- Simple in-memory rate limiting (best-effort; replace with Redis token bucket in prod) -------
_RATE_WINDOW_SECONDS = 60
_request_log: Dict[str, Deque[float]] = defaultdict(lambda: deque())  # fallback en memoria

def _rate_limit_key(request) -> str:
    # Per-user if auth header present, else per-IP (remote address may be None in test)
    auth = request.headers.get("authorization") or ""
    if auth:
        return f"auth:{auth[:40]}"  # truncate token
    client = request.client.host if request.client else "anon"
    return f"ip:{client}"

PII_EMAIL_RE = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+")
PII_PHONE_RE = re.compile(r"\b\+?\d[\d\s\-]{6,}\b")

def redact_pii(value: str) -> str:
    if not settings.pii_redaction_enabled:
        return value
    redacted = PII_EMAIL_RE.sub("<email_redacted>", value)
    redacted = PII_PHONE_RE.sub("<phone_redacted>", redacted)
    return redacted


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup (startup)
    configure_logging(settings.log_level)
    init_db()
    yield
    # Teardown (shutdown)


app = FastAPI(title="EmoTrack Kids API", version="0.1.0", lifespan=lifespan)

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = asyncio.get_event_loop().time()
    path = request.url.path
    # Rate limiting (simple sliding window count)
    limit = settings.rate_limit_requests_per_minute
    if limit > 0:
        key = _rate_limit_key(request)
        over_limit = False
        # Intentar Redis token (contador por ventana deslizante simple)
        if redis_client is not None:
            try:
                # Usar ventana de 60s basada en timestamp // 60
                window_id = int(start // _RATE_WINDOW_SECONDS)
                rkey = f"rl:{key}:{window_id}"
                current_raw = redis_client.incr(rkey)
                try:
                    current = int(current_raw)  # type: ignore[arg-type]
                except Exception:
                    current = limit + settings.rate_limit_burst + 1
                if current == 1:
                    redis_client.expire(rkey, _RATE_WINDOW_SECONDS)
                if current > (limit + settings.rate_limit_burst):
                    over_limit = True
            except Exception:
                pass
        if not over_limit and redis_client is None:
            bucket = _request_log[key]
            now = start
            while bucket and (now - bucket[0]) > _RATE_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limit + settings.rate_limit_burst:
                over_limit = True
            else:
                bucket.append(now)
        if over_limit:
            try:
                REQUEST_ERRORS.labels(request.method, path, "RateLimitExceeded").inc()
            except Exception:
                pass
            try:
                RATE_LIMIT_HITS.labels(key, "blocked").inc()
            except Exception:
                pass
            return FastAPIResponse(status_code=429, content=json.dumps({"detail": "rate_limited"}), media_type="application/json")
        else:
            try:
                RATE_LIMIT_HITS.labels(key, "accepted").inc()
            except Exception:
                pass
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        # Contabilizar error y re-lanzar
        try:
            REQUEST_ERRORS.labels(request.method, path, exc.__class__.__name__).inc()
        except Exception:
            pass
        raise
    elapsed = asyncio.get_event_loop().time() - start
    try:
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(elapsed)
    except Exception:
        pass
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
try:
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
except Exception:
    redis_client = None  # tests may not have Redis
WS_CHANNEL = "emotrack:updates"


def _safe_publish(channel: str, payload: dict) -> None:
    try:
        if redis_client is not None:
            redis_client.publish(channel, json.dumps(payload))
    except Exception:
        # Evita romper el flujo si Redis no está disponible (tests o dev)
        logger.warning("redis_publish_failed", channel=channel)


# Models (subset aligned with intructions.txt)
class ToneFeatures(BaseModel):
    pitch_mean_hz: Optional[float] = None
    pitch_std_hz: Optional[float] = None
    speech_rate_wpm: Optional[float] = None
    voice_intensity_db: Optional[float] = None


class EmotionalAnalysis(BaseModel):
    primary_emotion: str
    intensity: float
    polarity: str
    keywords: list[str] = []
    tone_features: Optional[ToneFeatures] = None
    audio_features: Optional[dict] = None
    transcript: Optional[str] = None
    confidence: float
    model_version: str
    analysis_timestamp: str


class AnalyzeRequest(BaseModel):
    text: str
    child_age: Optional[int] = None


class AnalyzeResponse(BaseModel):
    analysis: EmotionalAnalysis


class CreateChildResponsePayload(BaseModel):
    # child_id se obtiene de la ruta; no debe ser obligatorio en el body.
    # Se acepta solo texto y emoji opcionales.
    text: Optional[str] = None
    emoji: Optional[str] = None
    force_intensity: Optional[float] = None


class AlertThresholds(BaseModel):
    intensity_high: float
    emotion_streak_length: int
    avg_count: int
    avg_threshold: float


class AlertSeverities(BaseModel):
    intensity_high: str
    emotion_streak: str
    avg_intensity_high: str


def _load_dynamic_thresholds(session) -> dict:
    if not settings.dynamic_config_enabled:
        return {}
    rows = list(session.exec(select(AppConfig).where(AppConfig.key.like("alert_%"))))
    result = {}
    for r in rows:
        result[r.key] = r.value
    return result


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_invalido")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="token_sin_sub")
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="usuario_no_existe")
    return user


def require_roles(*roles: UserRole):
    def wrapper(user=Depends(get_current_user)):
        role = user["role"] if isinstance(user, dict) else getattr(user, "role", None)
        if role not in roles:
            raise HTTPException(status_code=403, detail="forbidden")
        return user
    return wrapper


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config/alert-thresholds", response_model=AlertThresholds)
def get_alert_thresholds(session=Depends(get_session), user=Depends(require_roles(UserRole.ADMIN))):
    overrides = _load_dynamic_thresholds(session)
    return AlertThresholds(
        intensity_high=float(overrides.get("alert_intensity_high_threshold", settings.alert_intensity_high_threshold)),
        emotion_streak_length=int(overrides.get("alert_emotion_streak_length", settings.alert_emotion_streak_length)),
        avg_count=int(overrides.get("alert_avg_intensity_count", settings.alert_avg_intensity_count)),
        avg_threshold=float(overrides.get("alert_avg_intensity_threshold", settings.alert_avg_intensity_threshold)),
    )


@app.put("/api/config/alert-thresholds", response_model=AlertThresholds)
def update_alert_thresholds(payload: AlertThresholds, session=Depends(get_session), user=Depends(require_roles(UserRole.ADMIN))):
    if not settings.dynamic_config_enabled:
        raise HTTPException(status_code=400, detail="dynamic_config_disabled")
    # Upsert keys
    mapping = {
        "alert_intensity_high_threshold": str(payload.intensity_high),
        "alert_emotion_streak_length": str(payload.emotion_streak_length),
        "alert_avg_intensity_count": str(payload.avg_count),
        "alert_avg_intensity_threshold": str(payload.avg_threshold),
    }
    for k, v in mapping.items():
        row = session.exec(select(AppConfig).where(AppConfig.key == k)).first()
        if row:
            row.value = v
        else:
            session.add(AppConfig(key=k, value=v))
    return payload


@app.get("/api/config/alert-severities", response_model=AlertSeverities)
def get_alert_severities(session=Depends(get_session), user=Depends(require_roles(UserRole.ADMIN))):
    overrides = _load_dynamic_thresholds(session) if settings.dynamic_config_enabled else {}
    def _norm(v: str, d: str) -> str:
        vv = (v or d).lower()
        return vv if vv in {"info", "warning", "critical"} else d
    return AlertSeverities(
        intensity_high=_norm(overrides.get("alert_severity_intensity_high", "critical"), "critical"),
        emotion_streak=_norm(overrides.get("alert_severity_emotion_streak", "warning"), "warning"),
        avg_intensity_high=_norm(overrides.get("alert_severity_avg_intensity_high", "warning"), "warning"),
    )


@app.put("/api/config/alert-severities", response_model=AlertSeverities)
def update_alert_severities(payload: AlertSeverities, session=Depends(get_session), user=Depends(require_roles(UserRole.ADMIN))):
    if not settings.dynamic_config_enabled:
        raise HTTPException(status_code=400, detail="dynamic_config_disabled")
    mapping = {
        "alert_severity_intensity_high": payload.intensity_high.lower(),
        "alert_severity_emotion_streak": payload.emotion_streak.lower(),
        "alert_severity_avg_intensity_high": payload.avg_intensity_high.lower(),
    }
    for v in mapping.values():
        if v not in {"info", "warning", "critical"}:
            raise HTTPException(status_code=400, detail="severity_invalid")
    for k, v in mapping.items():
        row = session.exec(select(AppConfig).where(AppConfig.key == k)).first()
        if row:
            row.value = v
        else:
            session.add(AppConfig(key=k, value=v))
    return payload


@app.get("/api/debug/boom")
async def debug_boom():
    # Endpoint intencional para probar métricas de errores
    raise ValueError("boom test")


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return FastAPIResponse(content=data, media_type=CONTENT_TYPE_LATEST)


# ---- Auth Endpoints ----
@app.post("/api/auth/register", response_model=UserOut, status_code=201)
def register(data: RegisterRequest):
    role_value = data.role or UserRole.PARENT.value
    if role_value not in [r.value for r in UserRole]:
        raise HTTPException(status_code=400, detail="rol_invalido")
    try:
        user_dict = create_user(data.email, data.password, UserRole(role_value))
    except ValueError:
        raise HTTPException(status_code=400, detail="email_ya_existe")
    return user_dict


@app.post("/api/auth/login", response_model=TokenResponse)
def login(data: LoginRequest):
    user = get_user_by_email(data.email)
    if not user or not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    access = create_access_token(
        sub=user["email"],
        role=user["role"],
        expires_minutes=settings.access_token_expire_minutes,
    )
    refresh = create_refresh_token(sub=user["email"], role=user["role"], expires_days=settings.refresh_token_expire_days)
    return TokenResponse(access_token=access, expires_in=settings.access_token_expire_minutes * 60, token_type="bearer", refresh_token=refresh)


@app.post("/api/auth/refresh")
def refresh(token: str):
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="refresh_invalido")
    if is_refresh_token_revoked(token):
        raise HTTPException(status_code=401, detail="refresh_revocado")
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="refresh_invalido")
    user = get_user_by_email(sub)
    if not user:
        raise HTTPException(status_code=401, detail="usuario_no_existe")
    access = create_access_token(
        sub=user["email"],
        role=user["role"],
        expires_minutes=settings.access_token_expire_minutes,
    )
    return {"access_token": access, "token_type": "bearer", "expires_in": settings.access_token_expire_minutes * 60}


@app.post("/api/auth/logout", status_code=204)
def logout(refresh_token: str):
    # Cliente envía refresh token para revocar
    if refresh_token:
        try:
            revoke_refresh_token(refresh_token)
        except Exception:
            pass
    return FastAPIResponse(status_code=204, content=None)


@app.get("/api/auth/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    # Normalizar siempre a UserOut dict
    if isinstance(user, dict):
        return {"id": user["id"], "email": user["email"], "role": user["role"]}
    return {"id": getattr(user, "id", None), "email": getattr(user, "email", None), "role": getattr(user, "role", None)}


# Startup handled via lifespan above


@app.post("/api/analyze-emotion", response_model=AnalyzeResponse)
async def analyze_emotion(req: AnalyzeRequest):
    # Mock synchronous analysis to unblock UI; real path goes through Celery
    analysis = EmotionalAnalysis(
        primary_emotion="Neutral",
        intensity=0.1,
        polarity="Neutro",
        keywords=[],
        tone_features=None,
        audio_features=None,
        transcript=req.text,
        confidence=0.5,
        model_version="mock-0.1",
        analysis_timestamp="1970-01-01T00:00:00Z",
    )
    return AnalyzeResponse(analysis=analysis)


@app.post("/api/submit-responses")
async def submit_responses(
    parent_id: Optional[str] = Form(None),
    child_id: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    selected_emoji: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    session=Depends(get_session),
):
    # Minimal: persist file later; for now, enqueue text for analysis
    audio_path = None
    if audio_file is not None:
        try:
            # Validar archivo antes de guardarlo
            content = await audio_file.read()
            from .audio_utils import validar_audio, AudioValidationError
            
            # Guardar temporalmente para validación
            os.makedirs("uploads", exist_ok=True)
            suffix = os.path.splitext(audio_file.filename or "audio.webm")[1] or ".webm"
            fname = f"resp_{int(asyncio.get_event_loop().time()*1000)}_{os.getpid()}{suffix}"
            audio_path = os.path.join("uploads", fname)
            
            with open(audio_path, "wb") as f:
                f.write(content)
            
            # Validar formato, tamaño y duración
            try:
                validar_audio(audio_path, len(content))
            except AudioValidationError as e:
                # Limpiar archivo inválido
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass
                raise HTTPException(status_code=400, detail=f"Audio inválido: {str(e)}")
            
            logger.info("stored_audio", path=audio_path, size=len(content))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("audio_store_failed", error=str(e))
            # Si falla el almacenamiento, continuar sin audio
            audio_path = None
    # Minimal persistence (status QUEUED)
    child_name = (child_id or "child").strip() or "child"
    # child_id numérico opcional si viene convertible
    numeric_child_id = None
    if child_id and child_id.isdigit():
        numeric_child_id = int(child_id)
    row = Response(child_name=child_name, child_id=numeric_child_id, emotion="Unknown", status=ResponseStatus.QUEUED, audio_path=audio_path, audio_format=(os.path.splitext(audio_path)[1][1:] if audio_path else None))
    session.add(row)
    session.flush()  # to get id

    payload = {
        "text": text or "",
        "child_id": child_id,
        "emoji": selected_emoji,
        "response_id": row.id,
        "audio_path": audio_path,
    }
    task_id = enqueue_analysis_task(payload)
    # Notify listeners (WS relay listens on this channel)
    _safe_publish(
        WS_CHANNEL,
        {"type": "task_queued", "task_id": task_id, "response_id": row.id, "status": "QUEUED"},
    )
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "task_id": task_id,
            "response_id": row.id,
            "message": "Queued for analysis",
        },
    )


@app.get("/api/response-status/{task_id}")
async def response_status(task_id: str):
    status = get_task_status(task_id)
    return {"task_id": task_id, "status": status}


@app.get("/api/responses")
async def list_responses(session=Depends(get_session)):
    # Use the SQLAlchemy column to keep type checkers happy
    created_col = getattr(Response, "created_at")  # type: ignore[attr-defined]
    stmt = select(Response).order_by(desc(created_col)).limit(100)
    items = list(session.exec(stmt))
    return [
        {
            "id": r.id,
            "child_name": r.child_name,
            "emotion": r.emotion,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in items
    ]


@app.get("/api/responses/{response_id}")
async def get_response(response_id: int, session=Depends(get_session)):
    r = session.get(Response, response_id)
    if r is None:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return {
        "id": r.id,
        "child_name": r.child_name,
        "emotion": r.emotion,
        "status": r.status,
        "created_at": r.created_at.isoformat(),
        "analysis_json": r.analysis_json,
    }


@app.get("/api/dashboard/{child_ref}")
async def dashboard(child_ref: str, session=Depends(get_session), user=Depends(require_roles(UserRole.ADMIN, UserRole.PARENT, UserRole.PSYCHOLOGIST))):
    # child_ref puede ser id numérico (child_id) o nombre legacy
    if child_ref.isdigit():
        stmt = select(Response).where(Response.child_id == int(child_ref))
    else:
        stmt = select(Response).where(Response.child_name == child_ref)
    rows = list(session.exec(stmt))
    by_emotion: dict[str, int] = {}
    series_by_day: dict[str, int] = {}
    for r in rows:
        by_emotion[r.emotion] = by_emotion.get(r.emotion, 0) + 1
        day = r.created_at.date().isoformat()
        series_by_day[day] = series_by_day.get(day, 0) + 1
    child_meta = None
    if child_ref.isdigit():
        cobj = session.get(Child, int(child_ref))
        if cobj:
            child_meta = {"id": cobj.id, "name": cobj.name, "age": cobj.age}
    else:
        # intento buscar child por nombre para parent/admin/psychologist (no estricto)
        cobj = session.exec(select(Child).where(Child.name == child_ref)).first()
        if cobj:
            child_meta = {"id": cobj.id, "name": cobj.name, "age": cobj.age}
    return {
        "child_ref": child_ref,
        "child": child_meta,
        "total": len(rows),
        "by_emotion": by_emotion,
        "series_by_day": series_by_day,
    }


# ---- Children CRUD ----
@app.post("/api/children", response_model=ChildOut, status_code=201)
def create_child(payload: ChildCreate, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    # Validación manual por compatibilidad SQLite test (puede no recrear constraint al vuelo)
    existing = session.exec(select(Child).where(Child.parent_id == parent_id, Child.name == payload.name)).first()
    if existing:
        raise HTTPException(status_code=409, detail="child_name_exists")
    child = Child(name=payload.name, age=payload.age, notes=payload.notes, parent_id=parent_id)
    session.add(child)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="child_name_exists")
    # child.id no será None tras flush
    assert child.id is not None
    return ChildOut(id=child.id, name=child.name, age=child.age, notes=child.notes, parent_id=child.parent_id)


@app.get("/api/children", response_model=ChildrenList)
def list_children(session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    items = list(session.exec(select(Child).where(Child.parent_id == parent_id)))
    return {"items": [ChildOut.model_validate(c) for c in items]}


@app.get("/api/children/{child_id}", response_model=ChildOut)
def get_child(child_id: int, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    c = session.get(Child, child_id)
    if c is None or c.parent_id != parent_id:
        raise HTTPException(status_code=404, detail="not_found")
    return ChildOut.model_validate(c)


@app.patch("/api/children/{child_id}", response_model=ChildOut)
def update_child(child_id: int, payload: ChildUpdate, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    c = session.get(Child, child_id)
    if c is None or c.parent_id != parent_id:
        raise HTTPException(status_code=404, detail="not_found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    session.add(c)
    session.flush()
    return ChildOut.model_validate(c)


@app.delete("/api/children/{child_id}", status_code=204)
def delete_child(child_id: int, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    c = session.get(Child, child_id)
    if c is None or c.parent_id != parent_id:
        raise HTTPException(status_code=404, detail="not_found")
    session.delete(c)
    return JSONResponse(status_code=204, content=None)


# ---- Alerts (placeholder simple) ----
@app.post("/api/alerts", response_model=AlertOut, status_code=201)
def create_alert(payload: AlertCreate, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN, UserRole.PSYCHOLOGIST))):
    # Podría incluir lógica de reglas; por ahora solo persistencia directa
    severity = (payload.severity or "info").lower()
    if severity not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=400, detail="severity_invalid")
    # Deduplicación básica: misma combinación en últimos 10 minutos con igual rule_version (si aplica)
    rule_version = RULE_VERSION_V2
    existing = session.exec(
        select(Alert).where(
            Alert.child_id == payload.child_id,
            Alert.type == payload.type,
            Alert.message == payload.message,
            Alert.rule_version == rule_version,
        )
    ).first()
    alert = Alert(child_id=payload.child_id, type=payload.type, message=payload.message, severity=severity, rule_version=rule_version)
    if existing:
        return {
            "id": existing.id,
            "child_id": existing.child_id,
            "type": existing.type,
            "message": existing.message,
            "severity": existing.severity,
            "rule_version": existing.rule_version,
            "created_at": existing.created_at.isoformat() if getattr(existing, "created_at", None) else None,
        }
    session.add(alert)
    session.flush()
    assert alert.id is not None
    try:
        from .metrics import ALERTS_TOTAL_BY_TYPE
        ALERTS_TOTAL_BY_TYPE.labels(alert.type, alert.severity).inc()
    except Exception:
        pass
    return {
        "id": alert.id,
        "child_id": alert.child_id,
        "type": alert.type,
        "message": alert.message,
        "severity": alert.severity,
        "rule_version": alert.rule_version,
        "created_at": alert.created_at.isoformat() if getattr(alert, "created_at", None) else None,
    }


@app.get("/api/alerts", response_model=AlertsList)
def list_alerts(child_id: Optional[int] = None, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN, UserRole.PSYCHOLOGIST))):
    stmt = select(Alert)
    if child_id is not None:
        stmt = stmt.where(Alert.child_id == child_id)
    rows = list(session.exec(stmt))
    result = [
        {
            "id": a.id,
            "child_id": a.child_id,
            "type": a.type,
            "message": a.message,
            "severity": a.severity,
            "rule_version": a.rule_version,
            "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) else None,
        }
        for a in rows
    ]
    return {"items": result}


@app.delete("/api/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN, UserRole.PSYCHOLOGIST))):
    a = session.get(Alert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="not_found")
    session.delete(a)
    return JSONResponse(status_code=204, content=None)


class AttachResponsesPayload(BaseModel):
    response_ids: list[int]


@app.post("/api/children/{child_id}/attach-responses", status_code=200)
def attach_responses(child_id: int, payload: AttachResponsesPayload, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    # Verificar child pertenece al parent
    c = session.get(Child, child_id)
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    if c is None or c.parent_id != parent_id:
        raise HTTPException(status_code=404, detail="child_not_found")
    updated = 0
    for rid in payload.response_ids:
        r = session.get(Response, rid)
        if r and (r.child_id is None):
            r.child_id = child_id
            if r.child_name == "child" or r.child_name == "":
                r.child_name = c.name
            updated += 1
    return {"attached": updated}


@app.post("/api/children/{child_id}/responses", status_code=202)
def create_response_for_child(child_id: int, payload: CreateChildResponsePayload | None = None, session=Depends(get_session), user=Depends(require_roles(UserRole.PARENT, UserRole.ADMIN))):
    c = session.get(Child, child_id)
    parent_id = user["id"] if isinstance(user, dict) else getattr(user, "id")
    if c is None or c.parent_id != parent_id:
        raise HTTPException(status_code=404, detail="child_not_found")
    text = payload.text if payload else None
    emoji = payload.emoji if payload else None
    row = Response(child_name=c.name, child_id=child_id, emotion="Unknown", status=ResponseStatus.QUEUED)
    session.add(row)
    session.flush()
    task_payload = {"text": text or "", "child_id": child_id, "emoji": emoji, "response_id": row.id}
    if payload and payload.force_intensity is not None:
        fi = payload.force_intensity
        task_payload["force_intensity"] = fi
        # Pre-popular análisis simulado para permitir reglas (incluye current en media)
        analysis_stub = {
            "primary_emotion": "Mixto",
            "intensity": fi,
            "polarity": "Neutro",
            "keywords": [],
            "tone_features": None,
            "audio_features": None,
            "transcript": text or "",
            "confidence": 0.5,
            "model_version": "mock-sync-0.1",
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Marcar response como completado con stub para que rule engine considere este registro
        row.emotion = analysis_stub["primary_emotion"]
        row.status = ResponseStatus.COMPLETED
        row.analysis_json = analysis_stub
        session.add(row)
        session.flush()
        # Ejecutar reglas v2 (puede crear intensity_high, streak, avg) evitando duplicados temporales
        try:
            evaluate_auto_alerts(session, child_id, row, analysis_stub)
        except Exception:
            pass
    task_id = enqueue_analysis_task(task_payload)
    _safe_publish(WS_CHANNEL, {"type": "task_queued", "task_id": task_id, "response_id": row.id, "status": "QUEUED"})
    return {"status": "accepted", "task_id": task_id, "response_id": row.id}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    if redis_client is None:
        await ws.send_json({"type": "warning", "message": "realtime disabled (no Redis)"})
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                    await ws.send_text(f"echo: {msg}")
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            logger.info("websocket_disconnected")
        return
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe(WS_CHANNEL)
    except Exception:
        await ws.send_json({"type": "warning", "message": "realtime fallback (redis error)"})
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                    await ws.send_text(f"echo: {msg}")
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            logger.info("websocket_disconnected")
        return
    try:
        await ws.send_json({"type": "welcome", "message": "connected"})
        while True:
            # Poll pubsub non-blocking and ping client periodically
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                await ws.send_text(message["data"])  # already JSON string
            # Also accept pings/echo from client without blocking
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
                await ws.send_text(f"echo: {msg}")
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("websocket_disconnected")
    finally:
        try:
            pubsub.close()
        except Exception:
            pass

# Static files (Flutter Web build)
_env_static = os.getenv("STATIC_DIR")
_static_dir_candidates = []
if _env_static:
    _static_dir_candidates.append(_env_static)
_static_dir_candidates.extend([
    "backend/static",
    "frontend/build/web",
])
for _cand in _static_dir_candidates:
    if _cand and os.path.isdir(_cand):
        # Mount as the last route so API paths keep working; html=True serves index.html
        app.mount("/", StaticFiles(directory=_cand, html=True), name="static")
        logger.info("static_mounted", directory=_cand)
        break
