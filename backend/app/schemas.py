from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional


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
