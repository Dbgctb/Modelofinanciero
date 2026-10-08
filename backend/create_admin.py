"""
Ejecuta este script una sola vez para crear el primer usuario administrador.
Uso: python create_admin.py
"""
import sys
from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.user import User, UserRole

Base.metadata.create_all(bind=engine)

db = SessionLocal()

email = input("Email del administrador: ").strip()
username = input("Nombre de usuario: ").strip()
full_name = input("Nombre completo: ").strip()
password = input("Contraseña (mín. 10 chars, mayúscula, número, especial): ").strip()

from app.core.security import validate_password_strength
if not validate_password_strength(password):
    print("ERROR: La contraseña no cumple los requisitos de seguridad.")
    sys.exit(1)

if db.query(User).filter(User.email == email).first():
    print("ERROR: Ya existe un usuario con ese email.")
    sys.exit(1)

admin = User(
    email=email,
    username=username.lower(),
    full_name=full_name,
    hashed_password=hash_password(password),
    role=UserRole.ADMIN,
    is_active=True,
    must_change_password=False,
)
db.add(admin)
db.commit()
print(f"\nAdministrador '{username}' creado correctamente.")
db.close()
