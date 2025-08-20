from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, String
from sqlmodel import Field, SQLModel
from sqlalchemy import UniqueConstraint


class UserRole(str, Enum):
    ADMIN = "admin"
    PARENT = "parent"
    PSYCHOLOGIST = "psychologist"
    CHILD = "child"


class ResponseStatus(str, Enum):
    QUEUED = "QUEUED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    role: UserRole = Field(default=UserRole.PARENT)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Response(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_name: str
    emotion: str = Field(default="Unknown", sa_column=Column(String, index=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    status: ResponseStatus = Field(default=ResponseStatus.QUEUED)
    analysis_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    child_id: Optional[int] = Field(default=None, foreign_key="child.id", index=True)
    task_id: Optional[str] = Field(default=None, index=True)
    # Audio pipeline metadata
    audio_path: Optional[str] = Field(default=None, index=True)
    audio_format: Optional[str] = None
    audio_duration_sec: Optional[float] = None
    transcript: Optional[str] = None


class Child(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    age: Optional[int] = None
    notes: Optional[str] = None
    parent_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_child_parent_name"),)


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id", index=True)
    type: str
    message: str
    severity: str = Field(default="info")  # info | warning | critical
    rule_version: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RevokedToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    jti_hash: str = Field(index=True, unique=True)
    token_type: str = Field(default="refresh")
    revoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(default=None, index=True)


class AppConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
