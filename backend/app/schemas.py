from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = None  # Validado posteriormente


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str

    # Usar ConfigDict (Pydantic v2) para evitar deprecación
    model_config = ConfigDict(from_attributes=True)


class ChildCreate(BaseModel):
    name: str
    age: Optional[int] = None
    notes: Optional[str] = None


class ChildUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    notes: Optional[str] = None


class ChildOut(BaseModel):
    id: int
    name: str
    age: Optional[int]
    notes: Optional[str]
    parent_id: int

    model_config = ConfigDict(from_attributes=True)

class ChildrenList(BaseModel):
    items: List[ChildOut]


class AlertCreate(BaseModel):
    child_id: int
    type: str
    message: str
    severity: Optional[str] = "info"


class AlertOut(BaseModel):
    id: int
    child_id: int
    type: str
    message: str
    severity: str
    created_at: Optional[str | None | object] = None  # aceptar raw; FastAPI serializa

    model_config = ConfigDict(from_attributes=True)

class AlertsList(BaseModel):
    items: List[AlertOut]
