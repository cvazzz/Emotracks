import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional

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
)
from .schemas import RegisterRequest, LoginRequest, TokenResponse, UserOut, ChildCreate, ChildUpdate, ChildOut, ChildrenList

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup (startup)
    configure_logging(settings.log_level)
    init_db()
    yield
    # Teardown (shutdown)


app = FastAPI(title="EmoTrack Kids API", version="0.1.0", lifespan=lifespan)
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
    if audio_file is not None:
        # In future: save to uploads/ and record path
        logger.info("received_audio", filename=audio_file.filename)
    # Minimal persistence (status QUEUED)
    child_name = (child_id or "child").strip() or "child"
    # child_id numérico opcional si viene convertible
    numeric_child_id = None
    if child_id and child_id.isdigit():
        numeric_child_id = int(child_id)
    row = Response(child_name=child_name, child_id=numeric_child_id, emotion="Unknown", status=ResponseStatus.QUEUED)
    session.add(row)
    session.flush()  # to get id

    payload = {
        "text": text or "",
        "child_id": child_id,
        "emoji": selected_emoji,
        "response_id": row.id,
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
    task_id = enqueue_analysis_task({"text": text or "", "child_id": child_id, "emoji": emoji, "response_id": row.id})
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

    pubsub = redis_client.pubsub()
    pubsub.subscribe(WS_CHANNEL)
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
