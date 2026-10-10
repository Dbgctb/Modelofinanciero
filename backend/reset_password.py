"""
Resetea la contraseña de cualquier usuario (incluido el admin) directamente
en la base de datos, sin pasar por el login web -- para cuando nadie puede
entrar a la aplicación para verla desde "Solicitudes de reset" (p. ej. el
único admin se olvidó de su propia contraseña).

Uso: python reset_password.py
"""
import sys
from app.core.database import SessionLocal
from app.core.security import hash_password, validate_password_strength
from app.models.user import User
from app.models.refresh_token import RefreshToken

db = SessionLocal()

identificador = input("Usuario o email de la cuenta a resetear: ").strip().lower()
user = db.query(User).filter(
    (User.username == identificador) | (User.email == identificador)
).first()

if not user:
    print(f"ERROR: No existe ningún usuario con usuario/email '{identificador}'.")
    sys.exit(1)

print(f"Encontrado: {user.full_name} (@{user.username}, {user.role.value}, {'activo' if user.is_active else 'INACTIVO'})")

password = input("Nueva contraseña (mín. 10 chars, mayúscula, minúscula, número, especial): ").strip()

if not validate_password_strength(password):
    print("ERROR: La contraseña no cumple los requisitos de seguridad.")
    sys.exit(1)

user.hashed_password = hash_password(password)
user.must_change_password = False
user.failed_login_attempts = 0
user.locked_until = None
db.commit()

# Mismo criterio que el reset por token/admin: invalidar sesiones activas.
db.query(RefreshToken).filter(
    RefreshToken.user_id == user.id, RefreshToken.revoked == False,
).update({"revoked": True})
db.commit()

print(f"\nContraseña actualizada para '@{user.username}'. Ya puede iniciar sesión.")
db.close()
