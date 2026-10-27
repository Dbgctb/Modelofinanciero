"""
Rentabilidad real por cliente.

Toda la aritmética se hace sobre fact_resultado_analitico, que es la
fuente de verdad contable.  Los recibos sólo se usan para obtener el
tomador (campo no disponible en el analítico) y los metadatos de la
póliza (ramo, compañía, prima, etc.).

P&L por cliente
---------------
  ingreso_bruto   = Σ importe  WHERE tipo_cuenta='ingreso'  y recibo vinculado al tomador
  cesion_directa  = Σ -importe WHERE naturaleza='Cesión auxiliar' y recibo vinculado al tomador
                    con ingreso en el ejercicio (la 623 de recibos de años anteriores no cuenta)
  costes_indirectos = (costes operativos totales excl. cesión) × peso del cliente

  peso = ingreso_bruto_cliente / total_ingresos_analitico

  comision_neta = ingreso_bruto - cesion_directa
  margen_neto   = comision_neta - costes_indirectos
  margen_pct    = margen_neto / ingreso_bruto × 100

Cesión estimada
---------------
  Si un cliente tiene auxiliar(es) pero cesión real = 0 (aún no pagada),
  se calcula una cesión estimada = ingreso_bruto × tasa_cesion_estimada.
  El margen_neto_estimado y margen_pct_estimado se calculan restando esa estimación.

Las filas sin recibo_id (ajustes, cesiones manuales) se distribuyen
proporcionalmente para que la suma total coincida con el EBITDA del
modelo analítico.

NOTA: comision_bruta_total, margen_neto_total y margen_pct_medio del resumen
usan los totales globales de fact_resultado_analitico para garantizar
identidad exacta con el modelo analítico.
"""
from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from ..models.analitico import (
    NATURALEZAS_COSTE_OP, DRIVERS_DEFAULT, NATURALEZA_RESULTADO_FINANCIERO, PESO_POLIZA_INTERMEDIADA,
)
from .tasa_cesion import resolver_tasa, TASA_AUX_CTE, TASA_EXPR

MIN_COMISION_DEFAULT = 0.0
# Tasa de cesión estimada por defecto: la real del ejercicio (ver tasa_cesion.py).

_indexes_ensured = False

def _ensure_indexes(db: Session) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    try:
        db.execute(_text(
            "CREATE INDEX IF NOT EXISTS idx_fra_ejercicio "
            "ON fact_resultado_analitico(ejercicio)"
        ))
        db.execute(_text(
            "CREATE INDEX IF NOT EXISTS idx_fra_ej_rid "
            "ON fact_resultado_analitico(ejercicio, recibo_id) WHERE recibo_id IS NOT NULL"
        ))
        db.execute(_text(
            "CREATE INDEX IF NOT EXISTS idx_rec_tomador "
            "ON recibos(tomador) WHERE tomador IS NOT NULL AND tomador != ''"
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        _indexes_ensured = True


def _clase(pct: float) -> str:
    if pct >= 25: return "A"
    if pct >= 10: return "B"
    if pct >= 0:  return "C"
    return "D"


def _q(db: Session, sql: str, **kw):
    return db.execute(_text(sql), kw).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# SQL reutilizable: filas analíticas vinculadas a un recibo con tomador
# ─────────────────────────────────────────────────────────────────────────────
_SQL_POR_TOMADOR = """
    SELECT
        r.tomador,
        f.tipo_cuenta,
        f.naturaleza,
        f.numero_cuenta,
        r.ente,
        COALESCE(SUM(CAST(f.importe AS FLOAT)), 0) AS total
    FROM fact_resultado_analitico f
    JOIN recibos r ON f.recibo_id = r.id
    WHERE f.ejercicio = :ej
      AND r.tomador IS NOT NULL
      AND r.tomador != ''
    GROUP BY r.tomador, f.tipo_cuenta, f.naturaleza, f.numero_cuenta, r.ente
"""


def calcular_rentabilidad_clientes(
    db: Session,
    ejercicio: int,
    min_comision: float = MIN_COMISION_DEFAULT,
    tasa_cesion_estimada: float | None = None,
) -> dict:

    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    _ensure_indexes(db)

    # ── 1. Totales globales del ejercicio ────────────────────────────────────
    # SQL idéntico al de dashboard_ejecutivo (modelo analítico) para garantizar
    # que comision_bruta_total cuadra exactamente con lo que muestra el modelo.
    # r[0]=tipo_cuenta  r[1]=naturaleza  r[2]=total
    _pl_rows = _q(db, """
        SELECT tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej
        GROUP BY tipo_cuenta, naturaleza
    """, ej=ejercicio)

    if not _pl_rows:
        return {"sin_datos": True}

    total_ing_global = sum(float(r[2]) for r in _pl_rows if r[0] == 'ingreso')

    # Segunda query con numero_cuenta: necesaria para detectar cuentas 623* en costes
    # r[0]=tipo_cuenta  r[1]=naturaleza  r[2]=numero_cuenta  r[3]=total
    global_rows = _q(db, """
        SELECT tipo_cuenta, naturaleza, numero_cuenta, COALESCE(SUM(CAST(importe AS FLOAT)), 0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej
        GROUP BY tipo_cuenta, naturaleza, numero_cuenta
    """, ej=ejercicio)

    # Cesión real = cuenta 623* SOLO de recibos con auxiliar (ente IS NOT NULL)
    # que además tienen ingreso en el ejercicio. Requiere subquery sobre recibos.
    _aux_stat = _q(db, """
        WITH recibos_con_aux AS (
            SELECT r.id
            FROM recibos r
            WHERE r.ente IS NOT NULL
              AND r.id IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
              )
        )
        SELECT
            COALESCE(SUM( CAST(f.importe AS FLOAT)) FILTER (WHERE f.tipo_cuenta = 'ingreso' AND f.recibo_id IN (SELECT id FROM recibos_con_aux)), 0),
            COALESCE(SUM(-CAST(f.importe AS FLOAT)) FILTER (WHERE f.numero_cuenta LIKE '623%'  AND f.recibo_id IN (SELECT id FROM recibos_con_aux)), 0)
        FROM fact_resultado_analitico f
        WHERE f.ejercicio = :ej AND f.recibo_id IS NOT NULL
    """, ej=ejercicio)
    ing_con_auxiliar = round(float(_aux_stat[0][0]), 2) if _aux_stat else 0.0
    total_ces_global  = round(float(_aux_stat[0][1]), 2) if _aux_stat else 0.0
    total_cop_global = sum(-float(r[3]) for r in global_rows
                           if r[0] == 'gasto' and r[1] in NATURALEZAS_COSTE_OP)
    total_mkt_global = sum(-float(r[3]) for r in global_rows if r[1] == 'Marketing')
    total_sin_mapear_global = sum(-float(r[3]) for r in global_rows
                                  if r[0] == 'gasto' and r[1] is None)
    total_ind_global = total_cop_global + total_mkt_global

    ebitda_esperado = round(
        total_ing_global - total_ces_global - total_ind_global - total_sin_mapear_global, 2
    )

    # ── 2. P&L de las filas CON recibo_id agrupadas por tomador ──────────────
    por_tomador_rows = _q(db, _SQL_POR_TOMADOR, ej=ejercicio)

    ing_directo: dict[str, float] = {}
    ces_directo: dict[str, float] = {}

    for r in por_tomador_rows:
        tomador, tipo, total = r[0], r[1], float(r[5])
        if tipo == 'ingreso':
            ing_directo[tomador] = ing_directo.get(tomador, 0.0) + total
        # 623 sin auxiliar (ente IS NULL) y 640/642: ignorados

    # Cesión 623 por tomador: SOLO de recibos con ingreso en el ejercicio, mismo criterio
    # que total_ces_global. La 623 pagada en el año sobre recibos de años anteriores (la
    # cesión se paga con ~1 año de retraso) es de otro ejercicio: contarla aquí y además
    # estimar la de los recibos del año cargaba al cliente dos cesiones en un año
    # (detectado 2026-10-27 con PARTICIPACIONES PROYECTOS INMOBILIARIOS S.L.).
    for r in _q(db, """
        SELECT r.tomador, COALESCE(SUM(-CAST(f.importe AS FLOAT)), 0)
        FROM fact_resultado_analitico f
        JOIN recibos r ON f.recibo_id = r.id
        WHERE f.ejercicio = :ej
          AND f.naturaleza = 'Cesión auxiliar'
          AND f.numero_cuenta LIKE '623%'
          AND r.ente IS NOT NULL
          AND r.tomador IS NOT NULL AND r.tomador != ''
          AND f.recibo_id IN (
              SELECT DISTINCT recibo_id FROM fact_resultado_analitico
              WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
          )
        GROUP BY r.tomador
    """, ej=ejercicio):
        ces_directo[r[0]] = float(r[1])

    if not ing_directo:
        return {"sin_datos": True}

    # ── 3. Fracciones no atribuibles + pools de costes por driver ────────────
    total_ing_directo = sum(ing_directo.values())

    # Clamp cesión directa a >= 0: reversiones que superan la cesión original no
    # tienen sentido de negocio (el auxiliar no puede cobrar negativo al cliente).
    ces_directo_clamped: dict[str, float] = {t: max(0.0, v) for t, v in ces_directo.items()}
    total_ces_directo = sum(ces_directo_clamped.values())

    ing_sin_recibo = max(0.0, total_ing_global - total_ing_directo)

    # ces_ajuste puede ser negativo (reversiones en recibos sin tomador).
    # Permitirlo negativo elimina la diferencia ebitda_esperado vs suma de clientes.
    ces_ajuste = total_ces_global - total_ces_directo

    base_reparto = total_ing_directo if total_ing_directo > 0 else 1.0

    # Pools de costes desglosados por driver (respeta DRIVERS_DEFAULT del analítico):
    #   POLIZAS       → Personal, Servicios profesionales, Comunicaciones
    #   RECIBOS       → Tecnología, Bancos
    #   COMISION_NETA → Alquiler, Financiero, Viajes, Impuestos, Seguros, Suministros
    #   NUEVA_PRODUCCION (Marketing) → sin info NP por tomador, fallback a RECIBOS
    pool_recibos = 0.0   # costes que usan driver RECIBOS o NUEVA_PRODUCCION
    pool_polizas = 0.0   # costes que usan driver POLIZAS
    pool_cn      = 0.0   # costes que usan driver COMISION_NETA
    for r in global_rows:
        tipo, nat, _ncuenta, val = r[0], r[1], r[2], float(r[3])
        # Resultado financiero (intereses 66*) queda debajo del EBITDA: fuera de los pools.
        if tipo == 'gasto' and nat and nat not in ('Cesión auxiliar', NATURALEZA_RESULTADO_FINANCIERO):
            cost = -val
            drv = DRIVERS_DEFAULT.get(nat, 'RECIBOS')
            if drv == 'COMISION_NETA':
                pool_cn += cost
            elif drv == 'POLIZAS':
                pool_polizas += cost
            else:
                pool_recibos += cost

    # ── 4. Metadatos de los recibos (prima, ramos, compañías, auxiliar) ───────
    meta_rows = _q(db, """
        SELECT
            r.tomador,
            COUNT(*)                                                         AS n_recibos,
            COALESCE(SUM(CAST(r.pr_total AS FLOAT)), 0)                      AS prima_total,
            -- Pólizas ponderadas por canal: intermediada = PESO_POLIZA_INTERMEDIADA
            COUNT(DISTINCT COALESCE(r.numero_poliza, r.id::text)) FILTER (WHERE r.ente IS NULL)
              + :peso_int * COUNT(DISTINCT COALESCE(r.numero_poliza, r.id::text)) FILTER (WHERE r.ente IS NOT NULL)
                                                                             AS n_polizas,
            COUNT(DISTINCT r.ramo)     FILTER (WHERE r.ramo     IS NOT NULL) AS n_ramos,
            COUNT(DISTINCT r.compania) FILTER (WHERE r.compania IS NOT NULL) AS n_companias,
            string_agg(DISTINCT r.ramo,     ', ') FILTER (WHERE r.ramo     IS NOT NULL) AS ramos,
            string_agg(DISTINCT r.compania, ', ') FILTER (WHERE r.compania IS NOT NULL) AS companias,
            string_agg(DISTINCT r.ente,     ', ') FILTER (WHERE r.ente     IS NOT NULL) AS auxiliares
        FROM recibos r
        JOIN (
            -- Solo recibos con ingreso en el ejercicio (mismo criterio que _REC_EN_EJ del
            -- analítico): los de años anteriores que solo traen la 623 pagada este año no
            -- son negocio del año y desviaban los pesos RECIBOS/POLIZAS.
            SELECT DISTINCT recibo_id
            FROM fact_resultado_analitico
            WHERE ejercicio = :ej AND recibo_id IS NOT NULL AND tipo_cuenta = 'ingreso'
        ) fids ON r.id = fids.recibo_id
        WHERE r.tomador IS NOT NULL AND r.tomador != ''
        GROUP BY r.tomador
    """, ej=ejercicio, peso_int=PESO_POLIZA_INTERMEDIADA)

    meta: dict[str, dict] = {
        r[0]: {
            "n_recibos":   int(r[1]),
            "prima_total": float(r[2]),
            "n_polizas":   float(r[3]),
            "n_ramos":     int(r[4]),
            "n_companias": int(r[5]),
            "ramos":       r[6] or "",
            "companias":   r[7] or "",
            "auxiliares":  r[8] or "",
        }
        for r in meta_rows
    }

    # ── Bases de reparto para drivers ────────────────────────────────────────
    # RECIBOS: total de recibos con tomador identificado
    total_recibos_con_tomador = sum(m["n_recibos"] for m in meta.values())
    # POLIZAS: total de pólizas con tomador identificado
    total_polizas_con_tomador = sum(m["n_polizas"] for m in meta.values())

    # COMISION_NETA: sum de comisión neta directa por tomador (pre-cesión-ajuste)
    # Usamos ing_dir - ces_directo_clamped como proxy de comisión neta directa;
    # los pesos se normalizan sobre este total para que sumen 1 exacto.
    total_cn_directo = sum(
        max(0.0, ing - ces_directo_clamped.get(t, 0.0))
        for t, ing in ing_directo.items()
    )

    # ── 5a. Cesión estimada — recibos con auxiliar y sin apunte en cuenta 623* ──
    ces_est_tomador: dict[str, float] = {}
    ing_est_tomador: dict[str, float] = {}
    _ces_rows = _q(db, """
        WITH recibos_sin_cesion AS (
            SELECT r.id AS recibo_id
            FROM recibos r
            WHERE r.ente IS NOT NULL
              AND r.id IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
              )
              AND r.id NOT IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej
                    AND numero_cuenta LIKE '623%'
                    AND recibo_id IS NOT NULL
              )
        ),
    """ + TASA_AUX_CTE + f"""
        SELECT
            rec.tomador,
            COALESCE(SUM(CAST(f.importe AS FLOAT) * {TASA_EXPR}), 0) AS cesion_est,
            COALESCE(SUM(CAST(f.importe AS FLOAT)), 0)                AS ing_est
        FROM fact_resultado_analitico f
        JOIN recibos rec ON f.recibo_id = rec.id
        JOIN recibos_sin_cesion rsc ON f.recibo_id = rsc.recibo_id
        LEFT JOIN tasa_aux ta ON ta.ente = rec.ente
        WHERE f.ejercicio = :ej
          AND f.tipo_cuenta = 'ingreso'
          AND rec.tomador IS NOT NULL
        GROUP BY rec.tomador
    """, ej=ejercicio, tasa=tasa_cesion_estimada)
    # Cada recibo con la tasa real de su auxiliar (tasa = respaldo, ver tasa_cesion.py)
    ces_est_tomador = {r[0]: round(float(r[1]), 2) for r in _ces_rows if r[0]}
    ing_est_tomador = {r[0]: float(r[2]) for r in _ces_rows if r[0]}

    # ── 5. Construir resultado por cliente ────────────────────────────────────
    clientes_raw = []
    for tomador, ing_dir in ing_directo.items():
        peso = ing_dir / base_reparto

        ingreso_bruto = round(ing_dir, 2)
        cesion = max(0.0, round(ces_directo_clamped.get(tomador, 0.0), 2))

        # Peso RECIBOS: proporcional a número de recibos del tomador
        n_rec = meta.get(tomador, {}).get("n_recibos", 0)
        peso_rec = n_rec / total_recibos_con_tomador if total_recibos_con_tomador > 0 else peso

        # Peso POLIZAS: proporcional a número de pólizas del tomador
        n_pol = meta.get(tomador, {}).get("n_polizas", 0)
        peso_pol = n_pol / total_polizas_con_tomador if total_polizas_con_tomador > 0 else peso

        # Peso COMISION_NETA: proporcional a comisión neta directa del tomador
        cn_dir = max(0.0, ing_dir - ces_directo_clamped.get(tomador, 0.0))
        peso_cn_local = cn_dir / total_cn_directo if total_cn_directo > 0 else peso

        # Costes distribuidos con el driver correcto por naturaleza
        costes_ind = round(pool_recibos * peso_rec + pool_polizas * peso_pol + pool_cn * peso_cn_local, 2)
        costes_op  = costes_ind  # agrupado (pool_recibos incluye mkt, ya no se separa)
        costes_mkt = 0.0

        comision_neta = round(ingreso_bruto - cesion, 2)
        margen_neto   = round(comision_neta - costes_ind, 2)
        margen_pct    = round(margen_neto / ingreso_bruto * 100, 2) if ingreso_bruto > 0 else 0.0
        clase         = _clase(margen_pct)

        m = meta.get(tomador, {})
        tiene_aux = bool(m.get("auxiliares", ""))

        # Cesión estimada: misma regla que todos los dashboards
        # (recibos del cliente con auxiliar y sin 623* directa)
        cesion_estimada = ces_est_tomador.get(tomador, 0.0)
        tiene_cesion_estimada = cesion_estimada > 0.01

        margen_neto_estimado = round(margen_neto - cesion_estimada, 2)
        margen_pct_estimado  = round(margen_neto_estimado / ingreso_bruto * 100, 2) if ingreso_bruto > 0 else 0.0
        clase_estimada       = _clase(margen_pct_estimado) if tiene_cesion_estimada else clase

        clientes_raw.append({
            "tomador":               tomador,
            "n_recibos":             m.get("n_recibos", 0),
            "n_ramos":               m.get("n_ramos", 0),
            "n_companias":           m.get("n_companias", 0),
            "ramos":                 m.get("ramos", ""),
            "companias":             m.get("companias", ""),
            "auxiliares":            m.get("auxiliares", ""),
            "prima_total":           round(m.get("prima_total", 0.0), 2),
            "ingreso_bruto":         ingreso_bruto,
            "cesion_directa":        cesion,
            "comision_neta":         comision_neta,
            "costes_op":             costes_op,
            "costes_mkt":            costes_mkt,
            "costes_imputados":      costes_ind,
            "margen_neto":           margen_neto,
            "margen_pct":            margen_pct,
            "clase":                 clase,
            # Estimación
            "cesion_estimada":       cesion_estimada,
            "tiene_cesion_estimada": tiene_cesion_estimada,
            "margen_neto_estimado":  margen_neto_estimado,
            "margen_pct_estimado":   margen_pct_estimado,
            "clase_estimada":        clase_estimada,
        })

    clientes = [c for c in clientes_raw if c["ingreso_bruto"] >= min_comision]
    clientes.sort(key=lambda x: -x["margen_neto"])

    # Ingresos sin recibo vinculado: cliente virtual al final de la lista
    if ing_sin_recibo > 0.01:
        sin_cli_ces  = max(0.0, round(ces_ajuste, 2))
        sin_cli_mgn  = round(ing_sin_recibo - sin_cli_ces, 2)
        sin_cli_mpct = round(sin_cli_mgn / ing_sin_recibo * 100, 2) if ing_sin_recibo > 0 else 0.0
        clientes.append({
            "tomador":               "__SIN_CLIENTE__",
            "n_recibos":             0,
            "n_ramos":               0,
            "n_companias":           0,
            "ramos":                 "",
            "companias":             "",
            "auxiliares":            "",
            "prima_total":           0.0,
            "ingreso_bruto":         round(ing_sin_recibo, 2),
            "cesion_directa":        sin_cli_ces,
            "comision_neta":         round(ing_sin_recibo - sin_cli_ces, 2),
            "costes_op":             0.0,
            "costes_mkt":            0.0,
            "costes_imputados":      0.0,
            "margen_neto":           sin_cli_mgn,
            "margen_pct":            sin_cli_mpct,
            "clase":                 "D",
            "cesion_estimada":       0.0,
            "tiene_cesion_estimada": False,
            "margen_neto_estimado":  sin_cli_mgn,
            "margen_pct_estimado":   sin_cli_mpct,
            "clase_estimada":        "D",
        })

    # ── 6. Resumen ────────────────────────────────────────────────────────────
    # Contar por clase EFECTIVA (la estimada si tiene estimación, la real si no),
    # igual que lo que muestra la tabla y aplican los filtros del frontend.
    # El cliente virtual __SIN_CLIENTE__ no cuenta como cliente real.
    por_clase: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for c in clientes:
        if c["tomador"] == "__SIN_CLIENTE__":
            continue
        clase_ef = c["clase_estimada"] if c["tiene_cesion_estimada"] else c["clase"]
        por_clase[clase_ef] += 1

    cobertura_pct = round(sum(c["ingreso_bruto"] for c in clientes) / total_ing_global * 100, 1) \
        if total_ing_global > 0 else 0.0

    # Estimación global
    total_cesion_estimada = round(sum(c["cesion_estimada"] for c in clientes), 2)
    n_con_cesion_estimada = sum(1 for c in clientes if c["tiene_cesion_estimada"])
    # Base de ingresos sobre la que se aplica la estimación. Con tasa por auxiliar ya no
    # es ces_estimada / tasa: se suma el ingreso de los clientes con cesión estimada.
    ing_estimado_base = round(sum(
        ing_est_tomador.get(c["tomador"], 0.0) for c in clientes if c["tiene_cesion_estimada"]
    ), 2)

    # Suma de per-client (para verificación de cuadre, puede diferir en centavos por redondeo)
    ebitda_calculado = round(sum(c["margen_neto"] for c in clientes), 2)

    # cesión normalizada = cesión real contable + estimada devengada
    ces_normalizada_total = round(total_ces_global + total_cesion_estimada, 2)

    # Margen normalizado: igual que ebitda_esperado pero con ces_norm en lugar de ces_real
    # ebitda_normalizado = bruta - ces_norm - cop - mkt - sin_mapear = ebitda_esperado - ces_estimada
    margen_neto_normalizado = round(ebitda_esperado - total_cesion_estimada, 2)
    margen_pct_normalizado  = round(margen_neto_normalizado / total_ing_global * 100, 2) if total_ing_global else 0.0

    return {
        "ejercicio":              ejercicio,
        "min_comision":          min_comision,
        "tasa_cesion_estimada":  tasa_cesion_estimada,
        "resumen": {
            "n_clientes":                  sum(1 for c in clientes if c["tomador"] != "__SIN_CLIENTE__"),
            "por_clase":                   por_clase,
            # Valores globales — idénticos al modelo analítico
            "comision_bruta_total":        round(total_ing_global, 2),
            "cesion_total":                round(total_ces_global, 2),
            "costes_total":                round(total_cop_global, 2),
            "mkt_total":                   round(total_mkt_global, 2),
            "sin_mapear_total":            round(total_sin_mapear_global, 2),
            "margen_neto_total":           ebitda_esperado,
            "margen_pct_medio":            round(
                ebitda_esperado / total_ing_global * 100, 2
            ) if total_ing_global > 0 else 0.0,
            "margen_neto_normalizado":     margen_neto_normalizado,
            "margen_pct_normalizado":      margen_pct_normalizado,
            # Estimación + cuadre con modelo analítico
            "n_con_cesion_estimada":       n_con_cesion_estimada,
            "cesion_estimada_total":       total_cesion_estimada,
            "ces_normalizada_total":       ces_normalizada_total,
            # Desglose para tabla de cesión
            "ing_con_auxiliar":            ing_con_auxiliar,
            "ing_estimado_base":           ing_estimado_base,
            # Verificación de cuadre
            "cobertura_pct":               cobertura_pct,
            "comision_analitico_total":    round(total_ing_global, 2),
            "ebitda_esperado":             ebitda_esperado,
            "ebitda_calculado":            ebitda_calculado,
        },
        "pool_costes": {
            "cesion_analitico": round(total_ces_global, 2),
            "costes_op":        round(total_cop_global, 2),
            "mkt":              round(total_mkt_global, 2),
            "total_indirecto":  round(total_ind_global, 2),
        },
        "clientes": clientes,
        "top20":    clientes[:20],
        "bottom20": clientes[-20:][::-1],
    }


def recibos_sin_tomador(db: Session, ejercicio: int) -> dict:
    """
    Devuelve los recibos que tienen movimiento contable en el ejercicio
    pero no tienen tomador identificado.
    """
    rows = _q(db, """
        SELECT
            r.codigo,
            r.numero_poliza,
            r.compania,
            r.ramo,
            r.desde,
            r.hasta,
            r.ente            AS auxiliar,
            r.producto,
            r.tomador,
            COALESCE(SUM(CAST(f.importe AS FLOAT)), 0) AS ingreso_analitico
        FROM recibos r
        JOIN fact_resultado_analitico f ON f.recibo_id = r.id
        WHERE f.ejercicio = :ej
          AND f.tipo_cuenta = 'ingreso'
          AND (r.tomador IS NULL OR r.tomador = '')
        GROUP BY r.id, r.codigo, r.numero_poliza, r.compania, r.ramo,
                 r.desde, r.hasta, r.ente, r.producto, r.tomador
        ORDER BY ingreso_analitico DESC
    """, ej=ejercicio)

    total_ing = float(_q(db, """
        SELECT COALESCE(SUM(CAST(importe AS FLOAT)), 0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso'
    """, ej=ejercicio)[0][0])

    recibos = [
        {
            "codigo":            r[0],
            "numero_poliza":     r[1],
            "compania":          r[2] or "—",
            "ramo":              r[3] or "—",
            "desde":             r[4].isoformat() if r[4] else None,
            "hasta":             r[5].isoformat() if r[5] else None,
            "auxiliar":          r[6] or "—",
            "producto":          r[7] or "—",
            "tomador_actual":    r[8] or "",
            "ingreso_analitico": round(float(r[9]), 2),
        }
        for r in rows
    ]

    ingreso_sin_tomador = sum(r["ingreso_analitico"] for r in recibos)

    return {
        "ejercicio":           ejercicio,
        "n_recibos":           len(recibos),
        "ingreso_sin_tomador": round(ingreso_sin_tomador, 2),
        "pct_sobre_total":     round(ingreso_sin_tomador / total_ing * 100, 1) if total_ing else 0.0,
        "recibos":             recibos,
    }


def ejercicios_disponibles(db: Session) -> list[int]:
    rows = db.execute(_text(
        "SELECT DISTINCT ejercicio FROM fact_resultado_analitico ORDER BY 1 DESC"
    )).fetchall()
    return [r[0] for r in rows]


def recibos_por_cliente(db: Session, ejercicio: int, tomador: str) -> list:
    """Desglose por recibo: ingreso y cesión real (cuenta 623*) para un tomador.
    Cuando tomador == '__SIN_CLIENTE__' devuelve los apuntes sin recibo vinculado."""
    _ensure_indexes(db)

    if tomador == "__SIN_CLIENTE__":
        rows = _q(db, """
            SELECT numero_cuenta, naturaleza, concepto,
                   CAST(importe AS FLOAT) AS importe
            FROM fact_resultado_analitico
            WHERE ejercicio = :ej
              AND recibo_id IS NULL
              AND tipo_cuenta = 'ingreso'
            ORDER BY ABS(CAST(importe AS FLOAT)) DESC
        """, ej=ejercicio)
        return [
            {
                "_es_apunte":     True,
                "codigo":         r[0] or "—",
                "poliza":         "—",
                "ramo":           r[1] or "—",
                "compania":       "—",
                "tiene_auxiliar": False,
                "ingreso":        round(float(r[3]), 2),
                "cesion_real":    0.0,
                "concepto":       r[2] or "—",
                "numero_cuenta":  r[0] or "—",
                "naturaleza":     r[1] or "—",
            }
            for r in rows
        ]

    rows = _q(db, """
        SELECT
            r.codigo,
            r.numero_poliza,
            r.ramo,
            r.compania,
            r.ente,
            COALESCE(SUM(CAST(f.importe AS FLOAT)) FILTER (WHERE f.tipo_cuenta = 'ingreso'), 0) AS ingreso,
            COALESCE(SUM(-CAST(f.importe AS FLOAT)) FILTER (WHERE f.numero_cuenta LIKE '623%'), 0) AS cesion_real
        FROM fact_resultado_analitico f
        JOIN recibos r ON f.recibo_id = r.id
        WHERE f.ejercicio = :ej
          AND r.tomador   = :tom
        GROUP BY r.id, r.codigo, r.numero_poliza, r.ramo, r.compania, r.ente
        -- Solo recibos con ingreso en el ejercicio: los de años anteriores que solo
        -- traen la 623 pagada este año no cuentan en la rentabilidad del cliente.
        HAVING COUNT(*) FILTER (WHERE f.tipo_cuenta = 'ingreso') > 0
        ORDER BY ingreso DESC
    """, ej=ejercicio, tom=tomador)

    return [
        {
            "codigo":         r[0] or "—",
            "poliza":         r[1] or "—",
            "ramo":           r[2] or "—",
            "compania":       r[3] or "—",
            "tiene_auxiliar": r[4] is not None,
            "ingreso":        round(float(r[5]), 2),
            "cesion_real":    round(float(r[6]), 2),
        }
        for r in rows
    ]
