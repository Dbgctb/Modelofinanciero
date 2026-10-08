"""
Panel de control — cuadre fino entre módulos para el mismo ejercicio.

Fuentes (4 columnas):
  1. Diario contable     — diario_apuntes RAW (7*, 623*, otros 6*)              → verdad primaria
  2. Presupuesto [año]   — columna «Presupuesto» de Presupuestación > Cta. Resultados
  3. Analítico norm.     — dashboard_ejecutivo (mismos valores que Dashboard Ejecutivo)
  4. Rentabilidad cliente— totales del resumen de calcular_rentabilidad_clientes

Diferencias esperadas:
  Col 1 ↔ Col 2: Desviación real vs plan. No tiene por qué ser 0.
  Col 1 ↔ Col 3: Mínimas (clasificación de cuentas). Ideal = 0.
  Col 3 ↔ Col 4: Solo ces_ajuste sin distribuir. Debe ser ≈ 0.
"""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models.presupuesto import Presupuesto
from .rentabilidad_cliente import calcular_rentabilidad_clientes
from .cuenta_resultados import calcular_cuenta_resultados
from .analitico import dashboard_ejecutivo

_TOL = 1.0  # € — diferencia máxima para "cuadra"


def _pct(n: float | None, d: float | None) -> float | None:
    if n is None or d is None or d == 0:
        return None
    return round(n / d * 100, 2)


def _semaforo(diff: float) -> str:
    ad = abs(diff)
    if ad <= _TOL:   return "ok"
    if ad <= 500:    return "warning"
    return "error"


def _fila(concepto: str, negativo: bool = False, tipo: str = "normal",
          diario=None, presupuesto=None, analitico=None, rentabilidad=None) -> dict:
    return {
        "concepto":     concepto,
        "tipo":         tipo,        # "normal" | "subtotal" | "info"
        "negativo":     negativo,
        "diario":       diario,
        "presupuesto":  presupuesto,
        "analitico":    analitico,
        "rentabilidad": rentabilidad,
    }


def panel_control(db: Session, ejercicio: int) -> dict:

    # ── 1. DIARIO CONTABLE ────────────────────────────────────────────────────
    diario_row = db.execute(text("""
        SELECT
            -- Ingresos: cuentas 7*
            COALESCE(SUM(CASE WHEN numero_cuenta LIKE '7%%'
                THEN CAST(haber AS FLOAT) - CAST(debe AS FLOAT) ELSE 0 END), 0),
            -- Cesión auxiliar: cuentas 623*
            COALESCE(SUM(CASE WHEN numero_cuenta LIKE '623%%'
                THEN CAST(debe AS FLOAT) - CAST(haber AS FLOAT) ELSE 0 END), 0),
            -- Costes operativos: 6* excl. 623, 68*, 66*, 630*
            COALESCE(SUM(CASE
                WHEN numero_cuenta LIKE '6%%'
                 AND numero_cuenta NOT LIKE '623%%'
                 AND numero_cuenta NOT LIKE '68%%'
                 AND numero_cuenta NOT LIKE '66%%'
                 AND numero_cuenta NOT LIKE '630%%'
                THEN CAST(debe AS FLOAT) - CAST(haber AS FLOAT) ELSE 0 END), 0)
        FROM diario_apuntes
        WHERE ejercicio = :ej AND estado::text != 'excluido'
    """), {"ej": ejercicio}).fetchone()

    d_ing    = round(float(diario_row[0]), 2)
    d_ces    = round(float(diario_row[1]), 2)
    d_costes = round(float(diario_row[2]), 2)
    d_cn     = round(d_ing - d_ces, 2)
    d_ebitda = round(d_ing - d_ces - d_costes, 2)
    d_margen = _pct(d_ebitda, d_ing)
    diario_ok = d_ing != 0

    # ── 2. PRESUPUESTO DEL EJERCICIO ─────────────────────────────────────────
    # Prioridad 1: presupuesto PARA el ejercicio (columna ppto = proyección).
    # Prioridad 2: presupuesto que usa el ejercicio como base (columna base = real
    #              clasificado por el módulo presupuesto). Ocurre cuando hay datos
    #              reales para el año pero el presupuesto es para el año siguiente.
    ppto_doc = db.query(Presupuesto).filter(
        Presupuesto.ejercicio == ejercicio
    ).first()
    ppto_es_base = False

    if not ppto_doc:
        ppto_doc = db.query(Presupuesto).filter(
            Presupuesto.ejercicio_base == ejercicio
        ).first()
        ppto_es_base = bool(ppto_doc)

    cr_ok = bool(ppto_doc)
    p_ing = p_ces = p_costes = p_cn = p_ebitda = p_margen = None
    p_ejercicio_base = None
    p_ejercicio_ppto = None

    if ppto_doc:
        p_ejercicio_base = ppto_doc.ejercicio_base
        p_ejercicio_ppto = ppto_doc.ejercicio
        cr = calcular_cuenta_resultados(db, ppto_doc)
        col = "base" if ppto_es_base else "ppto"
        p_ing    = cr["total_ingresos"][col]
        p_ces    = round(sum(item[col] for item in cr.get("cesiones_por_auxiliar", [])), 2)
        p_costes = round(cr["total_gastos_operativos"][col] - p_ces, 2)
        p_cn     = round(p_ing - p_ces, 2)
        p_ebitda = cr["ebitda"][col]
        p_margen = _pct(p_ebitda, p_ing)

    # ── 3. MODELO ANALÍTICO — Dashboard Ejecutivo ────────────────────────────
    # Se llama al mismo servicio que usa el Dashboard Ejecutivo del módulo
    # analítico para garantizar que los valores de la columna 3 cuadren
    # exactamente con la «Cuenta de Resultados Normalizada» del dashboard.
    d1_result = dashboard_ejecutivo(db, ejercicio)
    analitico_ok = not d1_result.get("sin_datos")

    if analitico_ok:
        r1 = d1_result["resumen"]
        a_ing         = round(float(r1["comision_bruta"]), 2)
        a_ces_norm    = round(float(r1["cesion_normalizada"]), 2)
        a_cn_norm     = round(float(r1["comision_neta_norm"]), 2)
        a_ebitda_norm = round(float(r1["ebitda_normalizado"]), 2)
        a_margen_norm = r1.get("margen_pct_norm")
        # Costes operativos = NATURALEZAS_COSTE_OP (igual definición que costes_total
        # de rentabilidad_cliente, para que cols 3 y 4 cuadren).
        # Marketing y sin_mapear están incluidos en ebitda_normalizado pero no se
        # muestran como fila de costes separada (igual que en el Dashboard Ejecutivo).
        a_costes = round(float(r1.get("costes_operativos", 0)), 2)
        # Desglose para el pie de la tabla
        a_cop = round(float(r1.get("costes_operativos", 0)), 2)
        a_mkt = round(float(r1.get("costes_captacion", 0)), 2)
        a_aj  = round(float(r1.get("sin_mapear", 0)), 2)
    else:
        a_ing = a_ces_norm = a_cn_norm = a_ebitda_norm = a_margen_norm = None
        a_costes = a_cop = a_mkt = a_aj = 0.0

    # ── 4. RENTABILIDAD POR CLIENTE ───────────────────────────────────────────
    # Totales tal como aparecen en la fila de resumen de la pestaña
    # Analítico › Rentabilidad por Cliente.
    r_ing = r_ces = r_costes = r_cn = r_ebitda = r_margen = None
    r_n_estimados = None
    rentabilidad_ok = False

    if analitico_ok:
        rent_data = calcular_rentabilidad_clientes(db, ejercicio)
        if not rent_data.get("sin_datos"):
            rentabilidad_ok = True
            rs = rent_data["resumen"]
            r_ing         = rs.get("comision_bruta_total")
            r_ces         = rs.get("ces_normalizada_total")
            r_costes      = rs.get("costes_total")
            r_ebitda      = rs.get("margen_neto_normalizado")
            r_margen      = rs.get("margen_pct_normalizado")
            r_n_estimados = rs.get("n_con_cesion_estimada", 0)
            if r_ing is not None and r_ces is not None:
                r_cn = round(r_ing - r_ces, 2)

    # ── 5. TABLA P&L ──────────────────────────────────────────────────────────
    pl = [
        _fila("Comisión bruta",
              diario      = d_ing if diario_ok else None,
              presupuesto = p_ing,
              analitico   = a_ing if analitico_ok else None,
              rentabilidad= r_ing),

        _fila("Cesión auxiliar", negativo=True,
              diario      = d_ces if diario_ok else None,
              presupuesto = p_ces,
              analitico   = a_ces_norm if analitico_ok else None,
              rentabilidad= r_ces),

        _fila("Comisión neta", tipo="subtotal",
              diario      = d_cn if diario_ok else None,
              presupuesto = p_cn,
              analitico   = a_cn_norm if analitico_ok else None,
              rentabilidad= r_cn),

        _fila("Costes operativos", negativo=True,
              diario      = d_costes if diario_ok else None,
              presupuesto = p_costes,
              analitico   = a_costes if analitico_ok else None,
              rentabilidad= r_costes),

        _fila("EBITDA", tipo="subtotal",
              diario      = d_ebitda if diario_ok else None,
              presupuesto = p_ebitda,
              analitico   = a_ebitda_norm if analitico_ok else None,
              rentabilidad= r_ebitda),

        _fila("Margen %",
              diario      = d_margen if diario_ok else None,
              presupuesto = p_margen,
              analitico   = a_margen_norm if analitico_ok else None,
              rentabilidad= r_margen),
    ]

    # ── 6. SEMÁFOROS ──────────────────────────────────────────────────────────
    def _check(label, a, b, desc_a, desc_b, info=""):
        if a is None or b is None:
            return dict(label=label, desc_a=desc_a, desc_b=desc_b,
                        val_a=None, val_b=None, diff=None, estado="sin_datos", info=info)
        diff = round(b - a, 2)
        return dict(label=label, desc_a=desc_a, desc_b=desc_b,
                    val_a=a, val_b=b, diff=diff, estado=_semaforo(diff), info=info)

    cuadres = [
        _check(
            "Diario ↔ Analítico",
            d_ebitda if diario_ok else None,
            a_ebitda_norm if analitico_ok else None,
            "Diario contable", "Analítico norm.",
            "Ideal = 0. Si difiere: hay cuentas 623 sin auxiliar identificado o "
            "cuentas 6x excluidas. Revisa la Conciliación.",
        ),
        _check(
            "Analítico ↔ Rentabilidad",
            a_ebitda_norm if analitico_ok else None,
            r_ebitda,
            "Analítico normalizado", "Rentabilidad cliente",
            "Ideal = 0. Diferencias pequeñas por ces_ajuste (cesión sin auxiliar) "
            "que no se distribuye a clientes.",
        ),
        {   # Real vs Presupuesto: siempre informativo, no es un cuadre de integridad
            "label":  "Real vs Presupuesto",
            "desc_a": "EBITDA real (diario)",
            "desc_b": f"EBITDA presupuestado {ejercicio}",
            "val_a":  d_ebitda if diario_ok else None,
            "val_b":  p_ebitda,
            "diff":   round((p_ebitda or 0) - (d_ebitda or 0), 2)
                      if (d_ebitda is not None and p_ebitda is not None) else None,
            "estado": "info",
            "info":   "Desviación del EBITDA real frente al plan. No tiene por qué ser 0.",
        },
    ]

    n_ok    = sum(1 for c in cuadres if c["estado"] == "ok")
    n_total = sum(1 for c in cuadres if c["estado"] not in ("sin_datos", "info"))

    return {
        "ejercicio":            ejercicio,
        "presupuesto_base":     p_ejercicio_base,
        "presupuesto_ppto":     p_ejercicio_ppto,
        "presupuesto_es_base":  ppto_es_base,
        "tiene_datos": {
            "diario":       diario_ok,
            "presupuesto":  cr_ok,
            "analitico":    analitico_ok,
            "rentabilidad": rentabilidad_ok,
        },
        "pl":              pl,
        "cuadres":         cuadres,
        "n_cuadres_ok":    n_ok,
        "n_cuadres_total": n_total,
        "rent_n_estimados": r_n_estimados,
        "costes_detalle": {
            "costes_op":     a_cop,
            "costes_mkt":    a_mkt,
            "ajustes_coste": a_aj,
            "total":         round(a_cop + a_mkt + a_aj, 2),
        } if analitico_ok else None,
    }
