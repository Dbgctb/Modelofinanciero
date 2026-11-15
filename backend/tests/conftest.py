"""Configuración común de los tests.

Los tests NO usan la base de datos real. DATABASE_URL apunta a un puerto donde no hay
nada: si algún test intentara conectarse por error, fallaría en vez de leer o modificar
datos. (Las variables de entorno tienen prioridad sobre backend/.env en pydantic-settings.)
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

os.environ["DATABASE_URL"] = "postgresql://tests:tests@127.0.0.1:1/sin_base_de_datos"
os.environ["SECRET_KEY"] = "clave-solo-para-tests-" + "x" * 40
os.environ["APP_ENV"] = "test"

os.chdir(BACKEND)  # config.py busca .env en el directorio actual
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
