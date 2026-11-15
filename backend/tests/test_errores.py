"""Catálogo de errores: integridad, formato de todos los mensajes y comportamiento."""
import importlib.util
import string

import pytest

from app.core.errores import CATALOGO, ErrorApp, detalle_usuario, error_http, texto
from app.core.config import settings  # noqa: F401  (asegura que la configuración carga)

_spec = importlib.util.spec_from_file_location("catalogo_errores", "scripts/catalogo_errores.py")
catalogo_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalogo_script)


def test_comprobador_del_catalogo_pasa():
    """Códigos válidos, parámetros de cada uso, sin textos literales y documento al día."""
    assert catalogo_script.main() == 0


@pytest.mark.parametrize("codigo", sorted(CATALOGO))
def test_todos_los_mensajes_se_pueden_formatear(codigo):
    campos = {f for _, f, _, _ in string.Formatter().parse(CATALOGO[codigo].mensaje) if f}
    params = {c: 1.5 for c in campos}  # numérico: vale para {x} y para {x:.2f}
    assert texto(codigo, **params).startswith(f"[{codigo}] ")


def test_parametro_llamado_codigo_no_choca():
    """Regresión: CC-PUN-002 tiene {codigo} y daba TypeError (500) en vez del error."""
    assert str(ErrorApp("CC-PUN-002", codigo="ZZZ")) == "[CC-PUN-002] Regla desconocida: ZZZ"
    assert error_http("CC-PUN-002", codigo="ZZZ").detail.endswith("ZZZ")


def test_error_app_es_value_error_con_estado_http():
    e = ErrorApp("USR-003")
    assert isinstance(e, ValueError) and e.http == 404 and e.codigo == "USR-003"


def test_detalle_usuario_oculta_errores_sin_codigo():
    assert detalle_usuario(ErrorApp("USR-003")).startswith("[USR-003]")
    oculto = detalle_usuario(ValueError("invalid literal for int() with base 10: 'secreto'"))
    assert oculto.startswith("[GEN-004]") and "secreto" not in oculto
