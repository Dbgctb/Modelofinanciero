import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .core.limiter import limiter

from .core.config import settings
from .core.database import engine
from .core.errores import ErrorApp, texto
from .core.logging_config import setup_logging
from .routers import auth, users, carga, parametros, presupuesto, tesoreria, real, kpis, analitico, admin, rentabilidad, cuadre, cross_selling, cierres, cierres_banco, cierres_herramientas

setup_logging()
log = logging.getLogger(__name__)

def comprobar_revision(actual: str | None, esperada: str) -> None:
    """Lanza CFG-004 si la base no está en la última migración de Alembic."""
    if actual != esperada:
        raise ErrorApp("CFG-004", actual=actual or "ninguna", esperada=esperada)


def verificar_base_de_datos() -> None:
    """Al arrancar: la base debe estar en la última migración (no se crea ni se altera nada).

    El esquema lo gestiona SOLO Alembic (auditoría, fase 3). Antes el arranque ejecutaba
    create_all() y una lista de ALTER TABLE, y el historial de migraciones no podía crear
    la base desde cero. Las migraciones se aplican a mano: `python -m alembic upgrade head`.
    """
    from pathlib import Path
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    esperada = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        actual = MigrationContext.configure(conn).get_current_revision()
    comprobar_revision(actual, esperada)
    log.info("Base de datos en la revisión %s (última)", actual)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    verificar_base_de_datos()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(ErrorApp)
async def error_app_handler(request: Request, exc: ErrorApp):
    """ErrorApp que nadie capturó: responde con el estado y el mensaje del catálogo."""
    log.warning("%s %s → %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=exc.http, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error(
        "Excepción no controlada | %s %s | %s: %s\n%s",
        request.method,
        request.url.path,
        type(exc).__name__,
        str(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": texto("GEN-001")},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info(
        "%s %s → %d (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "   # Vite/React requiere inline scripts
        "style-src 'self' 'unsafe-inline'; "    # Ant Design usa estilos inline
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(carga.router, prefix="/api")
app.include_router(parametros.router, prefix="/api")
app.include_router(presupuesto.router, prefix="/api")
app.include_router(tesoreria.router, prefix="/api")
app.include_router(real.router, prefix="/api")
app.include_router(kpis.router, prefix="/api")
app.include_router(analitico.router, prefix="/api")
app.include_router(rentabilidad.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(cuadre.router, prefix="/api")
app.include_router(cross_selling.router, prefix="/api")
app.include_router(cierres.router, prefix="/api")
app.include_router(cierres_banco.router, prefix="/api")
app.include_router(cierres_herramientas.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}
