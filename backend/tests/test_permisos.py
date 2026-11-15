"""Control de acceso de TODOS los endpoints, leído de la propia aplicación FastAPI.

Si alguien añade un endpoint sin sesión, o una acción destructiva sin rol, falla aquí.
"""
from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute
from starlette.routing import Route

from app.main import app
from app.models.user import UserRole

# Únicos endpoints que pueden responder sin sesión.
PUBLICOS = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    ("GET", "/api/parametros/familias-gasto"),
    ("GET", "/api/health"),
}


@dataclass
class Ruta:
    """Ruta efectiva: path completo (con prefijos) y TODAS sus dependencias (las de la
    ruta y las que añada el include_router)."""
    path: str
    methods: set
    llamadas: list


def _dependencias(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependencias(d)


def _rutas_efectivas(rutas, prefijo="", extra=()) -> list[Ruta]:
    """Aplana las rutas de la app. FastAPI >= 0.16x guarda cada router incluido como un
    `_IncludedRouter` (no copia sus rutas a app.routes como antes). Si aparece un tipo de
    ruta desconocido, el test FALLA: nunca se salta rutas en silencio."""
    out = []
    for r in rutas:
        if isinstance(r, APIRoute):
            out.append(Ruta(prefijo + r.path, set(r.methods), [*extra, *_dependencias(r.dependant)]))
        elif hasattr(r, "original_router") and hasattr(r, "include_context"):
            ctx = r.include_context
            deps_include = []
            for d in ctx.dependencies:
                deps_include.append(d.dependency)
            out += _rutas_efectivas(r.original_router.routes, prefijo + ctx.prefix, (*extra, *deps_include))
        elif type(r) is Route:
            out.append(Ruta(prefijo + r.path, set(r.methods or ()), list(extra)))  # docs/openapi de Starlette
        else:
            raise AssertionError(f"Tipo de ruta no reconocido por el test: {type(r).__name__}")
    return out


def _roles(route: Ruta) -> set[str] | None:
    """Roles exigidos por require_role(...) en la ruta, o None si solo pide sesión."""
    for call in route.llamadas:
        for celda in getattr(call, "__closure__", None) or ():
            valor = celda.cell_contents
            if isinstance(valor, tuple) and valor and all(isinstance(r, UserRole) for r in valor):
                return {r.value for r in valor}
    return None


def _pide_sesion(route: Ruta) -> bool:
    return any(getattr(c, "__name__", "") in ("get_current_user", "checker") for c in route.llamadas)


RUTAS = _rutas_efectivas(app.routes)
CASOS = [(m, r) for r in RUTAS for m in sorted(r.methods) if m != "HEAD"]


def test_hay_rutas():
    assert len(RUTAS) > 150, "No se están recogiendo las rutas de los routers incluidos"


def test_openapi_no_es_publico_fuera_de_desarrollo():
    """En tests APP_ENV=test: ni /openapi.json ni /api/docs deben existir."""
    paths = {r.path for r in RUTAS}
    assert not paths & {"/openapi.json", "/api/openapi.json", "/api/docs", "/docs"}


@pytest.mark.parametrize("metodo,ruta", CASOS, ids=[f"{m} {r.path}" for m, r in CASOS])
def test_toda_ruta_no_publica_exige_sesion(metodo, ruta):
    if (metodo, ruta.path) in PUBLICOS:
        assert not _pide_sesion(ruta), "Ruta marcada como pública que pide sesión: actualiza PUBLICOS"
    else:
        assert _pide_sesion(ruta), f"{metodo} {ruta.path} responde sin sesión"


def test_lista_de_publicas_al_dia():
    existentes = {(m, r.path) for m, r in CASOS}
    assert PUBLICOS <= existentes, f"Rutas públicas que ya no existen: {PUBLICOS - existentes}"


@pytest.mark.parametrize("metodo,ruta", [(m, r) for m, r in CASOS if m == "DELETE"],
                         ids=[f"{m} {r.path}" for m, r in CASOS if m == "DELETE"])
def test_borrados_exigen_rol_gestor_o_admin(metodo, ruta):
    roles = _roles(ruta)
    assert roles, f"{metodo} {ruta.path} borra datos solo con sesión (un lector podría hacerlo)"
    assert "lector" not in roles


@pytest.mark.parametrize("prefijo", ["/api/users"])
def test_gestion_de_usuarios_solo_admin(prefijo):
    rutas = [r for r in RUTAS if r.path.startswith(prefijo)]
    assert rutas
    for r in rutas:
        assert _roles(r) == {"admin"}, f"{r.path} debería ser solo admin"


def test_reset_de_datos_y_escrituras_de_admin_solo_admin():
    for m, r in CASOS:
        if r.path.startswith("/api/admin/") and m != "GET":
            assert _roles(r) == {"admin"}, f"{m} {r.path} debería ser solo admin"
