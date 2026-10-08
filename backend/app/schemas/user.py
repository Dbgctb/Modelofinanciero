from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID
from ..models.user import UserRole
from ..core.security import validate_password_strength


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    role: UserRole = UserRole.LECTOR
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not validate_password_strength(v):
            raise ValueError(
                "La contraseña debe tener al menos 10 caracteres, "
                "una mayúscula, una minúscula, un número y un carácter especial"
            )
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("El usuario debe tener al menos 3 caracteres")
        if not v.replace("_", "").replace(".", "").isalnum():
            raise ValueError("El usuario solo puede contener letras, números, _ y .")
        return v.lower()


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
