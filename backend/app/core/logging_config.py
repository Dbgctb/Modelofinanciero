import logging
import sys
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent.parent / "app.log"

# Catálogo de errores conocidos → mensaje de log enriquecido
ERROR_CATALOG = {
    "Ya existe un mapeo para esa cuenta": "ERR_MAPEO_DUPLICADO",
    "Las cuentas de ingreso requieren compañía": "ERR_MAPEO_INGRESO_SIN_COMPANIA",
    "Las cuentas de gasto requieren familia de gasto": "ERR_MAPEO_GASTO_SIN_FAMILIA",
    "Mapeo no encontrado": "ERR_MAPEO_NOT_FOUND",
    "Credenciales incorrectas": "ERR_AUTH_CREDENCIALES",
    "Cuenta bloqueada": "ERR_AUTH_CUENTA_BLOQUEADA",
    "Token inválido o expirado": "ERR_AUTH_TOKEN",
    "El archivo está vacío": "ERR_CARGA_ARCHIVO_VACIO",
    "Error procesando el archivo": "ERR_CARGA_PROCESO",
    "Incidencia no encontrada": "ERR_INCIDENCIA_NOT_FOUND",
    "Carga no encontrada": "ERR_CARGA_NOT_FOUND",
}


def get_error_code(detail: str) -> str:
    for key, code in ERROR_CATALOG.items():
        if key in detail:
            return code
    return "ERR_UNKNOWN"


def setup_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    except OSError:
        pass  # si no se puede escribir el log en disco, solo stdout

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )

    # Silenciar loggers de terceros que son muy verbosos
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "passlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
