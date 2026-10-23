import logging
import time
import traceback

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .core.limiter import limiter

from .core.config import settings
from .core.database import Base, engine
from .core.logging_config import setup_logging
from .routers import auth, users, carga, parametros, presupuesto, tesoreria, real, kpis, analitico, admin, rentabilidad, cuadre, cross_selling, costes

setup_logging()
log = logging.getLogger(__name__)

# Crear tablas
Base.metadata.create_all(bind=engine)

# Migraciones incrementales (ADD COLUMN IF NOT EXISTS es idempotente)
from sqlalchemy import text as _sql
with engine.connect() as _conn:
    for _stmt in [
        "ALTER TABLE ramo_stats_ejercicio ADD COLUMN IF NOT EXISTS ramo_categoria VARCHAR(100)",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefono_fijo VARCHAR(30)",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefono_movil VARCHAR(30)",
        "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS email VARCHAR(200)",
        "ALTER TABLE cross_selling_oportunidades ADD COLUMN IF NOT EXISTS subramos_vigentes JSONB",
        "ALTER TABLE fuga_alertas ADD COLUMN IF NOT EXISTS tipo_cliente VARCHAR(20)",
        "ALTER TABLE fuga_alertas ADD COLUMN IF NOT EXISTS auxiliar VARCHAR(150)",
        "ALTER TABLE fuga_alertas ADD COLUMN IF NOT EXISTS ramos_actuales JSONB",
        "ALTER TABLE fuga_alertas ADD COLUMN IF NOT EXISTS liqui_vigente FLOAT",
    ]:
        _conn.execute(_sql(_stmt))
    _conn.commit()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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
        content={"detail": "Error interno del servidor. Contacta con el administrador."},
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
app.include_router(costes.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}
