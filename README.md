# Gestor Financiero — Correduría de Seguros

## Requisitos previos
- Python 3.11+
- Node.js 20+
- PostgreSQL 15+

---

## Backend (FastAPI)

```bash
cd backend

# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env
# Editar .env con tu DATABASE_URL y SECRET_KEY

# 4. Crear el primer administrador
python create_admin.py

# 5. Arrancar servidor
uvicorn app.main:app --reload
# API disponible en http://localhost:8000
# Docs en http://localhost:8000/api/docs
```

---

## Frontend (React + Vite)

```bash
cd frontend

# 1. Instalar dependencias
npm install

# 2. Arrancar
npm run dev
# Disponible en http://localhost:5173
```

---

## Estructura del proyecto

```
backend/
├── app/
│   ├── core/          → config, seguridad, BD, dependencias
│   ├── models/        → tablas de BD (SQLAlchemy)
│   ├── schemas/       → validación de datos (Pydantic)
│   ├── routers/       → endpoints de la API
│   └── services/      → lógica de negocio
└── create_admin.py    → script inicial de admin

frontend/
├── src/
│   ├── api/           → cliente HTTP y funciones de API
│   ├── components/    → componentes reutilizables
│   ├── pages/         → páginas por módulo
│   ├── store/         → estado global (Zustand)
│   └── types/         → tipos TypeScript
```

---

## Seguridad implementada

- JWT (access 15 min + refresh 7 días con rotación)
- bcrypt con factor 12
- Bloqueo tras 5 intentos fallidos (15 min)
- RBAC: admin / gestor / lector
- Auditoría completa de acciones
- Headers de seguridad HTTP
- CORS restringido
- Revocación de sesiones al cambiar contraseña
