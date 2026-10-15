"""Pydantic schemas for identity requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.identity.enums import UserRole, UserStatus


class UserRegisterRequest(BaseModel):
    """Payload for public customer registration.

    Note:
        Role is deliberately excluded from this schema to prevent clients
        from requesting administrative or partner roles during registration.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=30)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_non_blank(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Field cannot be blank.")
        return trimmed


class UserLoginRequest(BaseModel):
    """Payload for user authentication."""

    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class TokenResponse(BaseModel):
    """JWT access token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Safe public user representation without sensitive fields (e.g. password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    role: UserRole
    status: UserStatus
    created_at: datetime
