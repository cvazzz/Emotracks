from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

# Intentamos importar dependencias externas. Si no están instaladas, lanzamos un error claro.
try:  # PyJWT
    import jwt  # type: ignore
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "PyJWT no está instalado. Ejecuta: pip install PyJWT (o añade a requirements.txt y reinstala)."
    ) from e

try:  # passlib
    from passlib.context import CryptContext  # type: ignore
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "passlib[bcrypt] no está instalado. Ejecuta: pip install 'passlib[bcrypt]'"
    ) from e

from .settings import settings
from .db import session_scope
from sqlalchemy.orm import Session
from .models import User, UserRole
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def create_access_token(sub: str, role: str, expires_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(sub: str, role: str, expires_days: int = 7) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expires_days)).timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except Exception:
        return None


# --- Acceso a datos de usuario ---
def get_user_by_email(email: str):
    with session_scope() as s:
        assert isinstance(s, Session)
        stmt = select(User).where(User.email == email)  # type: ignore[arg-type]
        u = s.execute(stmt).scalars().first()
        if not u:
            return None
        return {"id": u.id, "email": u.email, "role": u.role, "hashed_password": u.hashed_password}


def create_user(email: str, password: str, role: UserRole = UserRole.PARENT):
    with session_scope() as s:
        assert isinstance(s, Session)
        user = User(email=email, hashed_password=hash_password(password), role=role)
        s.add(user)
        try:
            s.flush()
        except IntegrityError:
            raise ValueError("email_ya_existe")
        return {"id": user.id, "email": user.email, "role": user.role}
