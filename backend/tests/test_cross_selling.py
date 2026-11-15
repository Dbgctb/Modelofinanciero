"""Piezas puras del recálculo de cross-selling y alertas de fuga (fase 5: función troceada).

La equivalencia completa con la versión anterior se verificó con un golden master sobre la
base real (11 ejercicios, ~75.000 oportunidades y ~31.000 alertas idénticas, en una
transacción deshecha). Aquí se fijan reglas y límites.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from app.services import cross_selling as cs

PARAMS = SimpleNamespace(umbral_bajada_prima=0.2, dias_vencimiento_urgente=60, dias_inactividad_riesgo=365)
HOY = date(2026, 6, 1)


def _ctx(portfolios_ant=None):
    return SimpleNamespace(params=PARAMS, hoy=HOY, portfolios_ant=portfolios_ant or {})


def _cli(**kw):
    base = dict(tomador="ANA", ramos_vigentes={"AUTO", "HOGAR"}, prima_vigente=1000.0, n_ramos=2,
                dias_vencimiento=None)
    base.update(kw)
    return base


def _port(**kw):
    base = dict(polizas_prima={}, max_desde=HOY)
    base.update(kw)
    return base


@pytest.mark.parametrize("score,accion", [(91.8, "Llamar esta semana"), (70, "Llamar esta semana"),
                                          (69.9, "Incluir en campaña"), (50, "Incluir en campaña"),
                                          (35, "Revisar en renovación"), (34.9, "Monitorizar")])
def test_accion_oportunidad(score, accion):
    assert cs._accion_oportunidad(score) == accion


def test_accion_fuga_prioriza_la_senal_mas_grave():
    assert cs._accion_fuga({"mono_cartera", "ramo_perdido"}).startswith("Analizar causa")
    assert cs._accion_fuga({"mono_cartera", "vencimiento_proximo"}).startswith("Contactar antes")
    assert cs._accion_fuga({"cartera_reducida"}) == "Monitorizar y reforzar relación"


def test_percentiles_con_menos_de_4_clientes_son_cero():
    ports = {t: {"prima_vigente": p} for t, p in [("a", 100.0), ("b", 200.0), ("c", 0.0)]}
    assert cs._percentiles_prima(ports) == (0.0, 0.0, 0.0)


def test_percentiles():
    ports = {str(i): {"prima_vigente": float(p)} for i, p in enumerate([400, 100, 300, 200, 0])}
    # 4 primas > 0 ordenadas [100, 200, 300, 400]; índice int(n·q) − 1 → 0, 1, 2
    assert cs._percentiles_prima(ports) == (100.0, 200.0, 300.0)


def test_cliente_sin_historial_ni_riesgo_no_tiene_senales():
    assert cs._senales_fuga(_ctx(), _cli(), _port()) == ([], 0.0)


def test_senal_ramo_perdido_pesa_por_ramo():
    ctx = _ctx({"ANA": {"ramos": {"AUTO", "HOGAR", "VIDA", "SALUD"}, "prima_total": 0, "polizas_prima": {}}})
    senales, peso = cs._senales_fuga(ctx, _cli(), _port())
    assert senales[0]["desc"] == "Ha perdido ramos: SALUD, VIDA" and peso == 2.0


@pytest.mark.parametrize("dias,hay", [(1, True), (60, True), (61, False), (0, False), (None, False)])
def test_senal_vencimiento_proximo(dias, hay):
    senales, _ = cs._senales_fuga(_ctx(), _cli(dias_vencimiento=dias), _port())
    assert ("vencimiento_proximo" in {s["tipo"] for s in senales}) is hay


def test_senal_prima_bajando_supera_el_umbral():
    ctx = _ctx({"ANA": {"ramos": {"AUTO", "HOGAR"}, "prima_total": 2000.0, "polizas_prima": {}}})
    senales, peso = cs._senales_fuga(ctx, _cli(prima_vigente=1000.0), _port())
    assert [s["tipo"] for s in senales] == ["prima_bajando"] and senales[0]["desc"].startswith("Prima total baja un 50%")


def test_senal_sin_renovacion_y_mono_cartera():
    cli = _cli(ramos_vigentes={"AUTO"}, n_ramos=1)
    senales, peso = cs._senales_fuga(_ctx(), cli, _port(max_desde=date(2025, 1, 1)))
    assert {s["tipo"] for s in senales} == {"sin_renovacion", "mono_cartera"}
    assert peso == pytest.approx(0.6 + 0.45)


def test_matriz_afinidad_con_descripcion_por_defecto():
    params = SimpleNamespace(matriz_afinidad=[{"ramo_base": "AUTO", "ramo_objetivo": "VIDA", "afinidad": 0.5}])
    afinidad, desc, objetivos = cs._matriz_afinidad(params)
    assert afinidad[("AUTO", "VIDA")] == 0.5 and desc[("AUTO", "VIDA")] == "AUTO → VIDA" and objetivos == ["VIDA"]
