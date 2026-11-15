"""Semáforo y alertas de KPIs (lógica pura, sin base de datos)."""
import pytest

from app.models.kpi import SemaforoColor
from app.services.kpis import UMBRALES_DEFAULT, _semaforo, alertas_gestion

V, A, R = SemaforoColor.VERDE, SemaforoColor.AMARILLO, SemaforoColor.ROJO


@pytest.mark.parametrize("valor,esperado", [
    (100.0, V), (95.0, V),          # en el umbral verde cuenta como verde
    (94.99, A), (85.0, A),
    (84.99, R), (-10.0, R),
])
def test_kpi_normal_mas_es_mejor(valor, esperado):
    """KPI-01 cumplimiento de ingresos: verde ≥ 95 %, amarillo ≥ 85 %."""
    assert _semaforo("KPI-01", valor, UMBRALES_DEFAULT) == esperado


@pytest.mark.parametrize("valor,esperado", [
    (0.0, V), (-3.0, V),
    (0.01, A), (30.0, A),
    (30.01, R),
])
def test_kpi_invertido_menos_es_mejor(valor, esperado):
    """KPI-06 ratio de cesión: verde ≤ 0, amarillo ≤ 30 %, rojo por encima."""
    assert _semaforo("KPI-06", valor, UMBRALES_DEFAULT) == esperado


@pytest.mark.parametrize("codigo", ["KPI-06", "KPI-08", "KPI-10"])
def test_los_tres_invertidos_premian_valores_bajos(codigo):
    verde, amarillo = UMBRALES_DEFAULT[codigo]
    assert _semaforo(codigo, verde, UMBRALES_DEFAULT) == V
    assert _semaforo(codigo, amarillo + 1, UMBRALES_DEFAULT) == R


def test_kpi_sin_umbral_es_verde():
    assert _semaforo("KPI-99", -1e9, UMBRALES_DEFAULT) == V


def test_umbral_personalizado_prevalece():
    umbrales = {**UMBRALES_DEFAULT, "KPI-01": (50.0, 40.0)}
    assert _semaforo("KPI-01", 60.0, umbrales) == V


def test_alertas_solo_rojo_y_amarillo_con_mensaje_y_sin_duplicados():
    kpis = [
        {"codigo": "KPI-01", "semaforo": "rojo", "valor": 70.0},
        {"codigo": "KPI-01", "semaforo": "rojo", "valor": 70.0},      # duplicado
        {"codigo": "KPI-06", "semaforo": "amarillo", "valor": 12.0},
        {"codigo": "KPI-12", "semaforo": "verde", "valor": 20.0},      # verde: sin alerta
        {"codigo": "KPI-02", "semaforo": "rojo", "valor": -9000.0},    # sin mensaje definido
    ]
    alertas = alertas_gestion(kpis)
    assert [(a["codigo"], a["nivel"]) for a in alertas] == [("KPI-01", "rojo"), ("KPI-06", "amarillo")]
    assert alertas[0]["titulo"] == "Ingresos por debajo del plan"
