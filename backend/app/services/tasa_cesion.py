"""
Tasa real de cesión a auxiliares de un ejercicio.

La cesión "estimada" (recibos con auxiliar pero sin cesión 623 contabilizada) se
calculaba con un 40% fijo. Desde 2026-10-26 (decisión del usuario) el valor por
defecto es la tasa REAL del propio ejercicio: cesión 623 / comisión de los recibos
con auxiliar que sí tienen cesión contabilizada. En 2025 es un 57,92%.

Desde la misma fecha, cada auxiliar se estima con SU tasa real (TASA_AUX_CTE) o, si
no tiene cesión contabilizada, con su % del catálogo de Auxiliares; esta tasa global
queda como último respaldo.

Todos los cálculos que estiman cesión (Modelo Analítico, Cuenta de Resultados,
Rentabilidad por cliente y, a través de ellos, el Panel de control) resuelven la
tasa de respaldo con resolver_tasa() y usan TASA_AUX_CTE, así que siguen cuadrando
entre sí. Quien pase una tasa explícita (el selector de la pantalla) cambia solo
la de respaldo.
"""
from typing import Optional

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

# Solo si el ejercicio no tiene ningún recibo con auxiliar y cesión contabilizada.
TASA_CESION_FALLBACK = 0.40

_SQL = """
    WITH ing AS (
        SELECT recibo_id, SUM(CAST(importe AS FLOAT)) AS ing
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
        GROUP BY recibo_id
    ),
    ces AS (
        SELECT recibo_id, SUM(-CAST(importe AS FLOAT)) AS ces
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND numero_cuenta LIKE '623%' AND recibo_id IS NOT NULL
        GROUP BY recibo_id
    )
    SELECT COUNT(*), COALESCE(SUM(i.ing), 0), COALESCE(SUM(c.ces), 0)
    FROM ing i
    JOIN ces c ON c.recibo_id = i.recibo_id
    JOIN recibos r ON r.id = i.recibo_id
    WHERE r.ente IS NOT NULL
"""


def detalle_tasa_cesion_real(db: Session, ejercicio: int) -> dict:
    """Tasa real del ejercicio y los importes de los que sale."""
    n, ingreso, cesion = db.execute(_text(_SQL), {"ej": ejercicio}).one()
    ingreso, cesion = float(ingreso or 0), float(cesion or 0)
    es_real = int(n or 0) > 0 and ingreso > 0
    tasa = round(cesion / ingreso, 4) if es_real else TASA_CESION_FALLBACK
    return {
        "ejercicio": ejercicio,
        "tasa": tasa,
        "tasa_pct": round(tasa * 100, 2),
        "es_real": es_real,
        "n_recibos": int(n or 0),
        "ingreso_recibos": round(ingreso, 2),
        "cesion_recibos": round(cesion, 2),
    }


# ── Tasa POR AUXILIAR (decisiones del usuario 2026-10-26) ────────────────────
# Prioridad para la tasa de cada auxiliar:
#   1. Su tasa REAL del ejercicio: cesión 623 / comisión de sus recibos que sí tienen
#      cesión. Limitada a [0, 1]: reversiones o cesiones mayores que la comisión no
#      dan una tasa con sentido.
#   2. Si no tiene cesión contabilizada: su % pactado en el catálogo de Administración
#      → Auxiliares (auxiliares_comision_ref), del mismo año o, si no lo hay, del más
#      reciente. Se cruza por nombre (mayúsculas y sin espacios en los extremos).
#   3. Si tampoco está en el catálogo: la tasa de respaldo :tasa (resolver_tasa, por
#      defecto la real global del ejercicio).
#
# Uso en SQL: añadir TASA_AUX_CTE a la lista WITH, hacer
#   LEFT JOIN tasa_aux ta ON ta.ente = <recibos>.ente
# y multiplicar cada importe por TASA_EXPR (parámetro :tasa = tasa de respaldo).
TASA_AUX_CTE = """
    tasa_aux_real AS (
        SELECT r.ente,
               GREATEST(0.0, LEAST(1.0, SUM(c.ces) / NULLIF(SUM(i.ing), 0))) AS tasa
        FROM (
            SELECT recibo_id, SUM(CAST(importe AS FLOAT)) AS ing
            FROM fact_resultado_analitico
            WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
            GROUP BY recibo_id
        ) i
        JOIN (
            SELECT recibo_id, SUM(-CAST(importe AS FLOAT)) AS ces
            FROM fact_resultado_analitico
            WHERE ejercicio = :ej AND numero_cuenta LIKE '623%' AND recibo_id IS NOT NULL
            GROUP BY recibo_id
        ) c ON c.recibo_id = i.recibo_id
        JOIN recibos r ON r.id = i.recibo_id
        WHERE r.ente IS NOT NULL
        GROUP BY r.ente
        HAVING SUM(i.ing) > 0
    ),
    tasa_aux_catalogo AS (
        SELECT DISTINCT ON (UPPER(TRIM(auxiliar)))
               UPPER(TRIM(auxiliar)) AS aux_key,
               GREATEST(0.0, LEAST(1.0, CAST(comision_colaborador AS FLOAT) / 100.0)) AS tasa
        FROM auxiliares_comision_ref
        ORDER BY UPPER(TRIM(auxiliar)), (anyo = :ej) DESC, anyo DESC
    ),
    tasa_aux AS (
        SELECT e.ente,
               COALESCE(tr.tasa, tc.tasa) AS tasa,
               CASE WHEN tr.tasa IS NOT NULL THEN 'real'
                    WHEN tc.tasa IS NOT NULL THEN 'catalogo' END AS origen
        FROM (SELECT DISTINCT ente FROM recibos WHERE ente IS NOT NULL) e
        LEFT JOIN tasa_aux_real tr     ON tr.ente = e.ente
        LEFT JOIN tasa_aux_catalogo tc ON tc.aux_key = UPPER(TRIM(e.ente))
    )
"""
TASA_EXPR = "COALESCE(ta.tasa, :tasa)"


def tasas_por_auxiliar(db: Session, ejercicio: int) -> dict[str, tuple[float, str]]:
    """Tasa de cada auxiliar que tiene una propia (0–1) y su origen: 'real' o 'catalogo'.
    Los que no aparecen usan la tasa de respaldo."""
    rows = db.execute(
        _text("WITH " + TASA_AUX_CTE + " SELECT ente, tasa, origen FROM tasa_aux WHERE tasa IS NOT NULL"),
        {"ej": ejercicio},
    ).fetchall()
    return {r[0]: (round(float(r[1]), 4), r[2]) for r in rows}


def tasa_cesion_real(db: Session, ejercicio: int) -> float:
    return detalle_tasa_cesion_real(db, ejercicio)["tasa"]


def resolver_tasa(db: Session, ejercicio: int, tasa: Optional[float]) -> float:
    """La tasa pedida si viene informada; si no, la real del ejercicio."""
    return float(tasa) if tasa is not None else tasa_cesion_real(db, ejercicio)
