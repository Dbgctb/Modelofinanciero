"""Reglas de punteo que son SQL puro: A, B, I, O, S (por ejercicio) y CROSS_YEAR, L, P, R, T
(todos los ejercicios, al final).

Traducción fiel de app/rules/rule_*.py del programa original. Sumas en NUMERIC exacto.
Cada función: ejecutar(conn, ejercicio, run_id, tol, **kw) -> apuntes marcados.
"""
from sqlalchemy import text

from ._comun import SET_PUNTEO, filtro_cuentas_sql


def regla_a(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    """Mismo recibo y concepto en la cuenta (no 440*), suma <= tolerancia.

    Única regla a la que el original aplica el filtro de cuentas de la pantalla.
    """
    filtro, params = filtro_cuentas_sql(filtro_cuentas)
    res = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'A|' || cuenta || '|' || recibo_norm
        WHERE ejercicio = :ej AND NOT reconciled AND recibo_norm <> ''
          AND cuenta NOT LIKE '440%' {filtro}
          AND (cuenta, recibo_norm, concepto_norm) IN (
              SELECT cuenta, recibo_norm, concepto_norm FROM cc_apuntes
              WHERE ejercicio = :ej AND NOT reconciled AND recibo_norm <> ''
                AND cuenta NOT LIKE '440%' {filtro}
              GROUP BY cuenta, recibo_norm, concepto_norm
              HAVING COUNT(*) > 1 AND ABS(SUM(neto)) <= :tol)
    """), {"regla": "RULE_A", "run_id": run_id, "ej": ejercicio, "tol": tol, **params})
    return res.rowcount or 0


def regla_b(conn, ejercicio, run_id, tol, **_):
    """Mismo recibo en la cuenta (no 440*), suma <= tolerancia."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'B|' || cuenta || '|' || recibo_norm
        WHERE ejercicio = :ej AND NOT reconciled AND recibo_norm <> ''
          AND cuenta NOT LIKE '440%'
          AND (cuenta, recibo_norm) IN (
              SELECT cuenta, recibo_norm FROM cc_apuntes
              WHERE ejercicio = :ej AND NOT reconciled AND recibo_norm <> ''
                AND cuenta NOT LIKE '440%'
              GROUP BY cuenta, recibo_norm
              HAVING COUNT(*) > 1 AND ABS(SUM(neto)) <= :tol)
    """), {"regla": "RULE_B", "run_id": run_id, "ej": ejercicio, "tol": tol})
    return res.rowcount or 0


def regla_i(conn, ejercicio, run_id, tol, **_):
    """Cuentas 411* agrupadas por número de asiento, suma <= tolerancia."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'I|' || cuenta || '|' || numero::text
        WHERE ejercicio = :ej AND NOT reconciled AND numero IS NOT NULL
          AND cuenta LIKE '411%'
          AND (cuenta, numero) IN (
              SELECT cuenta, numero FROM cc_apuntes
              WHERE ejercicio = :ej AND NOT reconciled AND numero IS NOT NULL
                AND cuenta LIKE '411%'
              GROUP BY cuenta, numero
              HAVING COUNT(*) > 1 AND ABS(SUM(neto)) <= :tol)
    """), {"regla": "RULE_I", "run_id": run_id, "ej": ejercicio, "tol": tol})
    return res.rowcount or 0


def regla_o(conn, ejercicio, run_id, tol, **_):
    """Cuentas 4751* agrupadas por mes, suma <= tolerancia."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'O|' || cuenta || '|' || to_char(fecha, 'YYYY-MM')
        WHERE ejercicio = :ej AND NOT reconciled
          AND cuenta LIKE '4751%'
          AND (cuenta, to_char(fecha, 'YYYY-MM')) IN (
              SELECT cuenta, to_char(fecha, 'YYYY-MM') FROM cc_apuntes
              WHERE ejercicio = :ej AND NOT reconciled
                AND cuenta LIKE '4751%'
              GROUP BY cuenta, to_char(fecha, 'YYYY-MM')
              HAVING COUNT(*) > 1 AND ABS(SUM(neto)) <= :tol)
    """), {"regla": "RULE_O", "run_id": run_id, "ej": ejercicio, "tol": tol})
    return res.rowcount or 0


def regla_s(conn, ejercicio, run_id, tol, **_):
    """Mismo concepto con "RECIBO" en la cuenta (no 440*), suma <= tolerancia."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'S|' || cuenta || '|' || concepto_norm
        WHERE ejercicio = :ej AND NOT reconciled
          AND cuenta NOT LIKE '440%'
          AND concepto_norm ILIKE '%RECIBO%'
          AND (cuenta, concepto_norm) IN (
              SELECT cuenta, concepto_norm FROM cc_apuntes
              WHERE ejercicio = :ej AND NOT reconciled
                AND cuenta NOT LIKE '440%'
                AND concepto_norm ILIKE '%RECIBO%'
              GROUP BY cuenta, concepto_norm
              HAVING COUNT(*) > 1 AND ABS(SUM(neto)) <= :tol)
    """), {"regla": "RULE_S", "run_id": run_id, "ej": ejercicio, "tol": tol})
    return res.rowcount or 0


# ── Reglas que se ejecutan al final, sobre TODOS los ejercicios ──────────────

def regla_cross_year(conn, ejercicio, run_id, tol, **_):
    """Mismo recibo en la cuenta (no 440*) repartido en 2+ ejercicios, suma <= tolerancia.

    Nota: el original buscaba su tolerancia como 'RULE_CROSS_YEAR' (no existe) y usaba
    siempre 0,01. Aquí se usa la configurada en 'CROSS_YEAR', que hoy también es 0,01.
    """
    n_ej = conn.execute(text("SELECT COUNT(DISTINCT ejercicio) FROM cc_apuntes")).scalar()
    if n_ej < 2:
        return 0
    res = conn.execute(text(f"""
        UPDATE cc_apuntes a
        SET {SET_PUNTEO}, recon_group_id = 'CROSS_YEAR|' || a.cuenta || '|' || a.recibo_norm
        FROM (
            SELECT cuenta, recibo_norm FROM cc_apuntes
            WHERE NOT reconciled AND cuenta NOT LIKE '440%'
              AND recibo_norm <> '' AND recibo_norm IS NOT NULL
            GROUP BY cuenta, recibo_norm
            HAVING COUNT(DISTINCT ejercicio) >= 2 AND COUNT(*) >= 2
               AND ABS(SUM(neto)) <= :tol
        ) g
        WHERE a.cuenta = g.cuenta AND a.recibo_norm = g.recibo_norm
          AND NOT a.reconciled AND a.cuenta NOT LIKE '440%'
    """), {"regla": "CROSS_YEAR", "run_id": run_id, "tol": tol})
    return res.rowcount or 0


def regla_l(conn, ejercicio, run_id, tol, **_):
    """Cuentas 410*/411* cuyo saldo pendiente (todos los ejercicios) es <= tolerancia."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes a
        SET {SET_PUNTEO}, recon_group_id = 'RULE_L|ALL_YEARS|' || a.cuenta
        FROM (
            SELECT cuenta FROM cc_apuntes
            WHERE (cuenta LIKE '410%' OR cuenta LIKE '411%') AND NOT reconciled
            GROUP BY cuenta
            HAVING ABS(SUM(neto)) <= :tol AND COUNT(*) >= 2
        ) g
        WHERE a.cuenta = g.cuenta AND NOT a.reconciled
    """), {"regla": "RULE_L", "run_id": run_id, "tol": tol})
    return res.rowcount or 0


_CONCEPTOS_P = """({c} ILIKE '%ASIENTO%APERTURA%'
                OR {c} ILIKE '%ERROR%'
                OR {c} ILIKE '%LIQUIDACION%RECIBO%NULL%')"""


def regla_p(conn, ejercicio, run_id, tol, **_):
    """415* con conceptos especiales (apertura, error, liquidación recibo null), todos los ejercicios."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes a
        SET {SET_PUNTEO}, recon_group_id = 'RULE_P|ALL_YEARS|' || a.cuenta
        FROM (
            SELECT cuenta FROM cc_apuntes
            WHERE cuenta LIKE '415%' AND NOT reconciled
              AND {_CONCEPTOS_P.format(c='concepto_norm')}
            GROUP BY cuenta
            HAVING ABS(SUM(neto)) <= :tol AND COUNT(*) >= 2
        ) g
        WHERE a.cuenta = g.cuenta AND NOT a.reconciled
          AND {_CONCEPTOS_P.format(c='a.concepto_norm')}
    """), {"regla": "RULE_P", "run_id": run_id, "tol": tol})
    return res.rowcount or 0


def regla_r(conn, ejercicio, run_id, tol, **_):
    """Saldo cero, todos los ejercicios. No usa tolerancia (igual que el original).

    Pasada 1: apuntes sueltos con neto 0. Pasada 2: cuentas cuyo pendiente suma 0.
    """
    p = {"regla": "RULE_R", "run_id": run_id}
    r1 = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'R|NETO0|' || cuenta
        WHERE NOT reconciled AND ROUND(neto, 2) = 0
    """), p).rowcount or 0
    r2 = conn.execute(text(f"""
        UPDATE cc_apuntes a
        SET {SET_PUNTEO}, recon_group_id = 'RULE_R|' || g.ejercicios || '|' || a.cuenta
        FROM (
            SELECT cuenta,
                   CASE WHEN COUNT(DISTINCT ejercicio) > 1 THEN 'ALL_YEARS'
                        ELSE MIN(ejercicio)::text END AS ejercicios
            FROM cc_apuntes
            WHERE NOT reconciled
            GROUP BY cuenta
            HAVING ROUND(SUM(neto), 2) = 0
        ) g
        WHERE a.cuenta = g.cuenta AND NOT a.reconciled
    """), p).rowcount or 0
    return r1 + r2


_FILTRO_T = """NOT {a}reconciled AND {a}cuenta NOT LIKE '440%'
               AND ({a}recibo_norm = '' OR {a}recibo_norm IS NULL)
               AND {a}concepto_norm ILIKE 'RETROCESO LIQUIDACION%'"""


def regla_t(conn, ejercicio, run_id, tol, **_):
    """"Retroceso Liquidación" sin recibo (no 440*), por cuenta, todos los ejercicios."""
    res = conn.execute(text(f"""
        UPDATE cc_apuntes a
        SET {SET_PUNTEO}, recon_group_id = 'T|' || a.cuenta || '|' || g.etiqueta
        FROM (
            SELECT cuenta,
                   CASE WHEN COUNT(DISTINCT ejercicio) > 1
                        THEN 'MULTI_' || string_agg(DISTINCT ejercicio::text, '-' ORDER BY ejercicio::text)
                        ELSE MIN(ejercicio)::text END AS etiqueta
            FROM cc_apuntes
            WHERE {_FILTRO_T.format(a='')}
            GROUP BY cuenta
            HAVING COUNT(*) >= 2 AND ABS(SUM(neto)) <= :tol
        ) g
        WHERE a.cuenta = g.cuenta AND {_FILTRO_T.format(a='a.')}
    """), {"regla": "RULE_T", "run_id": run_id, "tol": tol})
    return res.rowcount or 0
