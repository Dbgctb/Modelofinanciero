from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import hashlib

from ..core.database import get_db
from ..core.security import verify_password, create_access_token, create_refresh_token, decode_token, hash_password
from ..core.config import settings
from ..core.dependencies import get_current_user
from ..models.user import User
from ..models.refresh_token import RefreshToken
from ..models.audit import AuditLog
from ..schemas.auth import LoginRequest, TokenResponse, RefreshRequest, ChangePasswordRequest

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _log(db: Session, action: str, user: User = None, request: Request = None, detail: str = None):
    log = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        action=action,
        detail=detail,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(log)
    db.commit()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == payload.username.lower()) | (User.email == payload.username.lower())
    ).first()

    if not user or not user.is_active:
        _log(db, "LOGIN_FAILED", detail=f"Usuario no encontrado: {payload.username}", request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    # Verificar bloqueo
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada. Inténtalo en {remaining} minutos",
        )

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            db.commit()
            _log(db, "ACCOUNT_LOCKED", user=user, request=request)
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Cuenta bloqueada por {settings.LOCKOUT_MINUTES} minutos tras demasiados intentos fallidos",
            )
        db.commit()
        _log(db, "LOGIN_FAILED", user=user, request=request,
             detail=f"Intento {user.failed_login_attempts}/{settings.MAX_LOGIN_ATTEMPTS}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    # Login exitoso
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)

    token_data = {"sub": str(user.id), "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    rt = RefreshToken(
        token_hash=_hash_token(refresh_token),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=request.client.host,
    )
    db.add(rt)
    db.commit()

    _log(db, "LOGIN_OK", user=user, request=request)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido")

    token_hash = _hash_token(payload.refresh_token)
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
    ).first()

    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revocado o inválido")

    user = db.query(User).filter(User.id == decoded["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")

    # Rotación: revocar el anterior y emitir uno nuevo
    stored.revoked = True

    token_data = {"sub": str(user.id), "role": user.role.value}
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    new_rt = RefreshToken(
        token_hash=_hash_token(new_refresh),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=request.client.host,
    )
    db.add(new_rt)
    db.commit()

    _log(db, "TOKEN_REFRESHED", user=user, request=request)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
def logout(
    payload: RefreshRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_hash = _hash_token(payload.refresh_token)
    db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).update({"revoked": True})
    db.commit()
    _log(db, "LOGOUT", user=current_user, request=request)
    return {"message": "Sesión cerrada correctamente"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.must_change_password = False
    db.commit()

    # Revocar todos los refresh tokens al cambiar contraseña
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked == False,
    ).update({"revoked": True})
    db.commit()

    _log(db, "PASSWORD_CHANGED", user=current_user, request=request)
    return {"message": "Contraseña actualizada correctamente"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "must_change_password": current_user.must_change_password,
    }
