"""Lógica pura de la valoración y de la rentabilidad por cliente (fase 5: funciones troceadas).

La equivalencia completa con la versión anterior se verificó con un golden master contra la
base real (26 casos, salida idéntica); aquí se fijan los límites que esos datos no ejercitan.
"""
import pytest

from app.services import analitico as an
from app.services import rentabilidad_cliente as rc

# ── Valoración: factores de ajuste en sus límites exactos ───────────────────


@pytest.mark.parametrize("pct,ajuste", [(100, 0.25), (80, 0.25), (79.9, 0.15), (70, 0.15), (69.9, 0.0),
                                        (55, 0.0), (54.9, -0.20), (0, -0.20)])
def test_ajuste_cartera_incluye_el_limite(pct, ajuste):
    assert an._ajuste_cartera(pct) == ajuste


@pytest.mark.parametrize("pct,ajuste", [(90, -0.30), (70.1, -0.30), (70, -0.15), (55.1, -0.15), (55, -0.05),
                                        (40.1, -0.05), (40, 0.0), (0, 0.0)])
def test_ajuste_concentracion_excluye_el_limite(pct, ajuste):
    assert an._ajuste_concentracion(pct) == ajuste


@pytest.mark.parametrize("pct,ajuste", [(80, 0.20), (70.1, 0.20), (70, 0.10), (50.1, 0.10), (50, 0.0),
                                        (30.1, 0.0), (30, -0.10), (0, -0.10)])
def test_ajuste_ramos_excluye_el_limite(pct, ajuste):
    assert an._ajuste_ramos(pct) == ajuste


@pytest.mark.parametrize("cagr,ajuste", [(0.20, 0.25), (0.08, 0.25), (0.0799, 0.15), (0.05, 0.15), (0.02, 0.05),
                                         (0.0199, 0.0), (0.0, 0.0), (-0.0001, -0.15)])
def test_ajuste_crecimiento_incluye_el_limite(cagr, ajuste):
    assert an._ajuste_crecimiento(cagr) == ajuste


@pytest.mark.parametrize("inicio,fin,anos,esperado", [
    (100.0, 121.0, 2, 0.1),     # 10 % anual
    (100.0, 100.0, 3, 0.0),
    (0.0, 100.0, 3, None),       # sin base: no hay CAGR
    (100.0, 150.0, 0, None),
])
def test_cagr(inicio, fin, anos, esperado):
    assert an._cagr(inicio, fin, anos) == esperado


def test_valoraciones_por_escenario():
    v = an._valoraciones(comision_bruta=100_000.0, ebitda=20_000.0, adj_total=0.2)
    assert v["comisiones"]["base"] == {"multiplo_base": 1.8, "ajuste_aplicado": 0.2,
                                       "multiplo_final": 2.0, "valor": 200_000.0}
    assert v["comisiones"]["pesimista"]["ajuste_aplicado"] == 0.1    # atenuado ×0,5
    assert v["ebitda"]["optimista"]["ajuste_aplicado"] == 0.6        # ×2 en EBITDA y ×1,5 optimista
    assert v["combinado"] == 150_000.0                               # (2×100k + 5×20k) / 2


def test_valoraciones_con_ebitda_negativo_no_aplican_metodo_ebitda():
    v = an._valoraciones(comision_bruta=100_000.0, ebitda=-5.0, adj_total=0.0)
    assert v["ebitda"] == {"pesimista": None, "base": None, "optimista": None}
    assert v["combinado"] is None


def test_pct_sin_total_es_cero():
    assert an._pct(5, 0) == 0 and an._pct(1, 3) == 33.3


# ── Rentabilidad por cliente ────────────────────────────────────────────────

@pytest.mark.parametrize("pct,clase", [(25, "A"), (24.99, "B"), (10, "B"), (9.99, "C"), (0, "C"), (-0.01, "D")])
def test_clase(pct, clase):
    assert rc._clase(pct) == clase


def test_pools_por_driver():
    filas = [
        ("gasto", "Personal", "640", -1000.0),              # POLIZAS
        ("gasto", "Tecnología", "629", -300.0),             # RECIBOS
        ("gasto", "Alquiler", "621", -200.0),               # COMISION_NETA
        ("gasto", "Cesión auxiliar", "623", -999.0),        # excluido
        ("gasto", rc.NATURALEZA_RESULTADO_FINANCIERO, "662", -50.0),  # bajo el EBITDA: excluido
        ("gasto", None, "699", -77.0),                      # sin mapear: excluido
        ("ingreso", "Comisiones", "705", 5000.0),           # no es coste
        ("gasto", "Naturaleza nueva", "600", -10.0),        # sin driver: RECIBOS por defecto
    ]
    assert rc._pools_por_driver(filas) == (310.0, 1000.0, 200.0)


def _reparto(**kw):
    base = dict(base_reparto=1000.0, ces_directo_clamped={"ANA": 10.0}, pools=(100.0, 200.0, 50.0),
                meta={"ANA": {"n_recibos": 2, "n_polizas": 1.0, "prima_total": 1234.567, "auxiliares": "AUX"}},
                total_recibos=4, total_polizas=2.0, total_cn_directo=990.0, ces_est_tomador={})
    base.update(kw)
    return rc._Reparto(**base)


def test_fila_cliente_reparte_costes_por_driver():
    f = rc._fila_cliente("ANA", 500.0, _reparto())
    # recibos 2/4 × 100 + pólizas 1/2 × 200 + comisión neta 490/990 × 50
    assert f["costes_imputados"] == round(50 + 100 + 50 * 490 / 990, 2)
    assert f["cesion_directa"] == 10.0 and f["comision_neta"] == 490.0
    assert f["margen_neto"] == round(490.0 - f["costes_imputados"], 2)
    assert f["prima_total"] == 1234.57 and f["tiene_cesion_estimada"] is False
    assert f["clase_estimada"] == f["clase"]


def test_fila_cliente_con_cesion_estimada():
    f = rc._fila_cliente("ANA", 500.0, _reparto(ces_est_tomador={"ANA": 40.0}))
    assert f["tiene_cesion_estimada"] is True
    assert f["margen_neto_estimado"] == round(f["margen_neto"] - 40.0, 2)


def test_fila_cliente_sin_metadatos_usa_peso_por_ingreso():
    f = rc._fila_cliente("BEA", 250.0, _reparto(meta={}, total_recibos=0, total_polizas=0.0,
                                                total_cn_directo=0.0, ces_directo_clamped={}))
    assert f["costes_imputados"] == round((100.0 + 200.0 + 50.0) * 0.25, 2)  # peso = 250/1000


def test_fila_sin_cliente():
    f = rc._fila_sin_cliente(ing_sin_recibo=200.0, ces_ajuste=-5.0)  # ajuste negativo: cesión 0
    assert f["tomador"] == "__SIN_CLIENTE__" and f["cesion_directa"] == 0.0
    assert f["margen_neto"] == 200.0 and f["margen_pct"] == 100.0 and f["clase"] == "D"
