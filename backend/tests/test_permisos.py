"""Control de acceso de TODOS los endpoints, leído de la propia aplicación FastAPI.

Si alguien añade un endpoint sin sesión, o una acción destructiva sin rol, falla aquí.
"""
import pytest
from fastapi.routing import APIRoute

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


def _dependencias(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependencias(d)


def _roles(route: APIRoute) -> set[str] | None:
    """Roles exigidos por require_role(...) en la ruta, o None si solo pide sesión."""
    for call in _dependencias(route.dependant):
        for celda in getattr(call, "__closure__", None) or ():
            valor = celda.cell_contents
            if isinstance(valor, tuple) and valor and all(isinstance(r, UserRole) for r in valor):
                return {r.value for r in valor}
    return None


def _pide_sesion(route: APIRoute) -> bool:
    return any(getattr(c, "__name__", "") in ("get_current_user", "checker") for c in _dependencias(route.dependant))


RUTAS = [r for r in app.routes if isinstance(r, APIRoute)]
CASOS = [(m, r) for r in RUTAS for m in sorted(r.methods)]


def test_hay_rutas():
    assert len(RUTAS) > 150


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
