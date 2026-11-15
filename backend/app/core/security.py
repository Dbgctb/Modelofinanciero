"""Contraseñas (bcrypt) y tokens JWT (PyJWT).

Auditoría, fase 4: se sustituyeron `passlib` (sin mantenimiento desde 2020) y `python-jose`
(vulnerabilidad sin arreglo y dependencias pyasn1/ecdsa vulnerables) por `bcrypt` y `PyJWT`.
Compatibilidad: los hashes guardados con passlib ($2b$12$…) y los tokens ya emitidos (HS256)
siguen siendo válidos; lo comprueban los tests.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from .config import settings

BCRYPT_RONDAS = 12
# bcrypt solo usa los primeros 72 bytes de la contraseña. passlib los truncaba en silencio;
# se hace igual para que las contraseñas largas ya guardadas sigan validando.
_BCRYPT_MAX_BYTES = 72

PASSWORD_REGEX = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&._\-])[A-Za-z\d@$!%*?&._\-]{10,}$'
)


def validate_password_strength(password: str) -> bool:
    return bool(PASSWORD_REGEX.match(password))


def _bytes_bcrypt(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bytes_bcrypt(password), bcrypt.gensalt(rounds=BCRYPT_RONDAS)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_bytes_bcrypt(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):  # hash mal formado o vacío: no valida, sin error 500
        return False


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire, "type": "access", "jti": uuid.uuid4().hex})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    # jti aleatorio: sin él, dos tokens del mismo usuario emitidos en el mismo segundo eran
    # idénticos y la renovación inmediata chocaba con la unicidad de token_hash (error 500).
    payload.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Payload si la firma y la caducidad son válidas; None en cualquier otro caso."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
