import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_admin
from ..core.security import hash_password, validate_password_strength
from ..models.user import User
from ..models.audit import AuditLog
from ..models.password_reset import PasswordResetToken
from ..schemas.user import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Usuarios"])
log = logging.getLogger(__name__)


class ResetPasswordPayload(BaseModel):
    new_password: str


@router.get("/", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    user = User(
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=hash_password(payload.password),
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="USER_CREATED",
        resource="users",
        resource_id=str(user.id),
        detail=f"Usuario '{user.username}' creado con rol '{user.role.value}'",
    )
    db.add(log)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if str(user_id) == str(current_user.id) and payload.is_active is False:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="USER_UPDATED",
        resource="users",
        resource_id=str(user.id),
    )
    db.add(log)
    db.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if str(user_id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.is_active = False
    db.commit()


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: UUID,
    payload: ResetPasswordPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not validate_password_strength(payload.new_password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe tener al menos 10 caracteres, una mayúscula, una minúscula, un número y un carácter especial",
        )

    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = True
    db.commit()

    log.info("Reset de contraseña | user='%s' by='%s'", user.username, current_user.username)
    db_log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="PASSWORD_RESET",
        resource="users",
        resource_id=str(user.id),
        detail=f"Contraseña reseteada para '{user.username}' por admin '{current_user.username}'",
    )
    db.add(db_log)
    db.commit()


@router.get("/audit-log")
def get_audit_log(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    limit: int = 100,
    offset: int = 0,
):
    total = db.query(AuditLog).count()
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": logs}


@router.get("/reset-requests")
def list_reset_requests(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Solicitudes de recuperación de contraseña pendientes (no usadas,
    sin caducar) -- sin email configurado, el admin ve aquí el enlace de
    un solo uso y lo relaya al usuario a mano."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(PasswordResetToken, User)
        .join(User, User.id == PasswordResetToken.user_id)
        .filter(PasswordResetToken.used == False, PasswordResetToken.expires_at > now)
        .order_by(PasswordResetToken.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(prt.id),
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "token": prt.token,
            "expires_at": prt.expires_at.isoformat(),
            "created_at": prt.created_at.isoformat(),
        }
        for prt, user in rows
    ]


@router.delete("/reset-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reset_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    prt = db.query(PasswordResetToken).filter(PasswordResetToken.id == request_id).first()
    if not prt:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    prt.used = True
    db.commit()
