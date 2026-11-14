"""Controles de calidad del diario (C, D, K, L). No puntean: detectan incidencias.

Traducción de app/services/controls.py del programa original, con dos cambios
decididos por el usuario (2026-11-14):
- se ejecutan solo los controles marcados en pantalla (el original ignoraba las casillas);
- cada ejecución sustituye las incidencias de ese control y ejercicio (el original las
  acumulaba: 81.094 al migrar).
Y una corrección: el control L comparaba la cuenta configurada (p. ej. "430") con
igualdad exacta contra cuentas de 10 dígitos, así que nunca encontraba nada; aquí la
cuenta configurada se usa como prefijo, igual que en los controles C y K.

Cuentas vigiladas: cc_cuentas_control (tipo C con min/max movimientos, D con
tolerancia %, K y L solo la cuenta).
"""
from sqlalchemy import text

CONTROLES = {
    "C": "Movimientos mensuales",
    "D": "Neto mensual estable",
    "K": "Duplicados de emisión",
    "L": "Anulación sin emisión",
}


def _cuentas(conn, tipo):
    return conn.execute(text("""
        SELECT cuenta, min_mov, max_mov, tolerance_pct FROM cc_cuentas_control
        WHERE tipo = :t AND active ORDER BY cuenta
    """), {"t": tipo}).mappings().all()


def _filtro_prefijos(cuentas, alias=""):
    """OR de `cuenta LIKE prefijo%` parametrizado. Sin cuentas → todas (como el original)."""
    if not cuentas:
        return "TRUE", {}
    conds, params = [], {}
    for i, c in enumerate(cuentas):
        conds.append(f"{alias}cuenta LIKE :p{i}")
        params[f"p{i}"] = f"{c['cuenta']}%"
    return "(" + " OR ".join(conds) + ")", params


def control_c(conn, ejercicio, run_id):
    """Meses sin movimientos o fuera del rango [min, max] por cuenta."""
    n = 0
    for cfg in _cuentas(conn, "C"):
        n += conn.execute(text("""
            WITH cuentas AS (
                SELECT DISTINCT cuenta FROM cc_apuntes
                WHERE cuenta LIKE :prefijo AND ejercicio = :ej
            ),
            movs AS (
                SELECT c.cuenta, m.mes, COUNT(a.id) AS n
                FROM cuentas c
                CROSS JOIN generate_series(1, 12) AS m(mes)
                LEFT JOIN cc_apuntes a ON a.cuenta = c.cuenta AND a.ejercicio = :ej
                                       AND EXTRACT(MONTH FROM a.fecha) = m.mes
                GROUP BY c.cuenta, m.mes
            )
            INSERT INTO cc_incidencias (run_id, control_type, ejercicio, cuenta, mes, issue_description, severity)
            SELECT :run, 'C', :ej, cuenta, mes,
                   CASE WHEN n = 0 THEN 'Mes sin movimientos (esperados: ' || :mn || '-' || :mx || ')'
                        WHEN n < :mn THEN 'Movimientos insuficientes: ' || n || ' (mínimo: ' || :mn || ')'
                        ELSE 'Exceso de movimientos: ' || n || ' (máximo: ' || :mx || ')' END,
                   CASE WHEN n = 0 THEN 'WARNING' ELSE 'ERROR' END
            FROM movs
            WHERE n < :mn OR n > :mx OR n = 0
        """), {"prefijo": f"{cfg['cuenta']}%", "ej": ejercicio, "run": run_id,
               "mn": cfg["min_mov"], "mx": cfg["max_mov"]}).rowcount or 0
    return n


def control_d(conn, ejercicio, run_id):
    """Variación del neto mensual respecto al mes anterior por encima de la tolerancia %."""
    return conn.execute(text("""
        WITH cfg AS (
            SELECT cuenta, tolerance_pct FROM cc_cuentas_control WHERE tipo = 'D' AND active
        ),
        saldos AS (
            SELECT a.cuenta, EXTRACT(MONTH FROM a.fecha)::int AS mes, SUM(a.neto) AS saldo
            FROM cc_apuntes a JOIN cfg ON a.cuenta = cfg.cuenta
            WHERE a.ejercicio = :ej
            GROUP BY a.cuenta, mes
        ),
        comp AS (
            SELECT s1.cuenta, s1.mes,
                   ABS(s1.saldo - COALESCE(s2.saldo, 0)) AS dif,
                   CASE WHEN s2.saldo IS NULL OR s2.saldo = 0 THEN NULL
                        ELSE ABS((s1.saldo - s2.saldo) / s2.saldo * 100) END AS pct,
                   cfg.tolerance_pct
            FROM saldos s1
            LEFT JOIN saldos s2 ON s1.cuenta = s2.cuenta AND s1.mes = s2.mes + 1
            JOIN cfg ON s1.cuenta = cfg.cuenta
        )
        INSERT INTO cc_incidencias (run_id, control_type, ejercicio, cuenta, mes, issue_description, severity)
        SELECT :run, 'D', :ej, cuenta, mes,
               'Variación anómala: ' || ROUND(pct, 2) || '% respecto mes anterior (Δ=' ||
               ROUND(dif, 2) || '€, tolerancia=' || tolerance_pct || '%)',
               CASE WHEN pct > 50 THEN 'ERROR' WHEN pct > 20 THEN 'WARNING' ELSE 'INFO' END
        FROM comp
        WHERE pct > tolerance_pct
    """), {"ej": ejercicio, "run": run_id}).rowcount or 0


def control_k(conn, ejercicio, run_id):
    """Recibos con más de una emisión en la misma cuenta."""
    filtro, params = _filtro_prefijos(_cuentas(conn, "K"))
    return conn.execute(text(f"""
        INSERT INTO cc_incidencias (run_id, control_type, ejercicio, cuenta, recibo_norm,
                                    issue_description, severity, line_ids)
        SELECT :run, 'K', ejercicio, cuenta, recibo_norm,
               'Recibo duplicado: ' || COUNT(*) || ' emisiones (fechas: ' ||
                   string_agg(to_char(fecha, 'YYYY-MM-DD'), ',' ORDER BY id) || ')',
               'ERROR', array_agg(id ORDER BY id)
        FROM cc_apuntes
        WHERE concepto_norm ILIKE 'EMISION%' AND recibo_norm <> ''
          AND ejercicio = :ej AND {filtro}
        GROUP BY ejercicio, cuenta, recibo_norm
        HAVING COUNT(*) > 1
    """), {"ej": ejercicio, "run": run_id, **params}).rowcount or 0


def control_l(conn, ejercicio, run_id):
    """Anulaciones sin una emisión previa del mismo recibo en la misma cuenta y ejercicio."""
    filtro, params = _filtro_prefijos(_cuentas(conn, "L"), alias="a.")
    return conn.execute(text(f"""
        INSERT INTO cc_incidencias (run_id, control_type, ejercicio, cuenta, recibo_norm,
                                    issue_description, severity, line_ids)
        SELECT :run, 'L', a.ejercicio, a.cuenta, a.recibo_norm,
               'Anulación sin emisión previa (fecha: ' || to_char(a.fecha, 'YYYY-MM-DD') || ')',
               'ERROR', ARRAY[a.id]
        FROM cc_apuntes a
        WHERE a.concepto_norm ILIKE 'ANULACION%' AND a.recibo_norm <> ''
          AND a.ejercicio = :ej AND {filtro}
          AND NOT EXISTS (
              SELECT 1 FROM cc_apuntes e
              WHERE e.recibo_norm = a.recibo_norm AND e.concepto_norm ILIKE 'EMISION%'
                AND e.fecha <= a.fecha AND e.ejercicio = a.ejercicio AND e.cuenta = a.cuenta)
    """), {"ej": ejercicio, "run": run_id, **params}).rowcount or 0


_FUNCIONES = {"C": control_c, "D": control_d, "K": control_k, "L": control_l}


def ejecutar_controles(engine, ejercicio, run_id, controles):
    """Ejecuta los controles elegidos; cada uno sustituye sus incidencias del ejercicio.

    Devuelve {control: nº incidencias}.
    """
    res = {}
    for codigo in [c for c in ("C", "D", "K", "L") if c in set(controles or [])]:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM cc_incidencias WHERE control_type = :t AND ejercicio = :ej"),
                         {"t": codigo, "ej": ejercicio})
            res[codigo] = _FUNCIONES[codigo](conn, ejercicio, run_id)
    return res


def resumen_incidencias(conn, ejercicio=None):
    """Incidencias vigentes por ejercicio, control y gravedad."""
    filtro = "WHERE ejercicio = :ej" if ejercicio else ""
    return [dict(r) for r in conn.execute(text(f"""
        SELECT ejercicio, control_type, severity, COUNT(*) AS n, MAX(created_at) AS fecha
        FROM cc_incidencias {filtro}
        GROUP BY ejercicio, control_type, severity
        ORDER BY ejercicio DESC, control_type, severity
    """), {"ej": ejercicio}).mappings()]
