"""Motor de punteo del diario completo (cc_apuntes).

Reproduce el orden del programa original (ReconciliationEngine + pantalla Conciliar):

1. Por cada ejercicio, en orden ascendente:
   a. las reglas activas por prioridad (desempate por código), salvo las finales y V;
   b. solo tras el ÚLTIMO ejercicio: CROSS_YEAR, L, P, Q, R y T, sobre todos los ejercicios;
   c. V (cierre de saldo 440*), la última de cada ejercicio.
2. Cada regla va en su propia transacción. Si una regla falla, se deshace solo esa
   regla y el motor sigue con las demás (como el original), pero el error queda
   registrado en el resultado y la ejecución acaba con estado "con_errores".
"""
import json
import logging
import time

from sqlalchemy import text

from ...core.database import engine as db_engine
from .reglas import REGLA_ULTIMA, REGLAS, REGLAS_FINALES

log = logging.getLogger(__name__)


def _reglas_activas(conn):
    filas = conn.execute(text("""
        SELECT rule_code, tolerance_amount FROM cc_reglas
        WHERE active ORDER BY priority, rule_code COLLATE "C"
    """)).all()
    return [(r.rule_code, float(r.tolerance_amount)) for r in filas]


def _tolerancia(conn, regla):
    """Se relee en cada regla, como el original (puede cambiarse entre ejecuciones)."""
    t = conn.execute(text("SELECT tolerance_amount FROM cc_reglas WHERE rule_code = :r"),
                     {"r": regla}).scalar()
    return float(t) if t is not None else 0.01


def ejecutar_ejercicio(ejercicio, filtro_cuentas=None, ejecutar_finales=True, progreso=None, engine=None):
    """Puntea un ejercicio. Devuelve dict con run_id, apuntes por regla y errores."""
    engine = engine or db_engine
    t0 = time.perf_counter()
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM cc_apuntes WHERE ejercicio = :ej"),
                             {"ej": ejercicio}).scalar()
        run_id = conn.execute(text("""
            INSERT INTO cc_ejecuciones (ejercicio, total_lines, status)
            VALUES (:ej, :n, 'running') RETURNING id
        """), {"ej": ejercicio, "n": total}).scalar()
        activas = [codigo for codigo, _ in _reglas_activas(conn)]

    normales = [r for r in activas if r not in REGLAS_FINALES and r != REGLA_ULTIMA]
    orden = list(normales)
    if ejecutar_finales:
        orden += [r for r in REGLAS_FINALES if r in activas]
    if REGLA_ULTIMA in activas:
        orden.append(REGLA_ULTIMA)

    por_regla, errores, ejecutadas = {}, [], []
    for regla in orden:
        fn = REGLAS.get(regla)
        if fn is None:
            errores.append({"regla": regla, "error": "Regla sin implementación"})
            continue
        tr = time.perf_counter()
        try:
            with engine.begin() as conn:
                tol = _tolerancia(conn, regla)
                n = fn(conn, ejercicio, run_id, tol, filtro_cuentas=filtro_cuentas)
        except Exception as e:  # se registra y se sigue, como el original
            log.exception("Punteo ejercicio %s: error en %s", ejercicio, regla)
            errores.append({"regla": regla, "error": f"{type(e).__name__}: {e}"})
            continue
        por_regla[regla] = n
        ejecutadas.append(regla)
        log.info("Punteo %s %s: %s apuntes (%.1f s)", ejercicio, regla, n, time.perf_counter() - tr)
        if progreso:
            progreso(ejercicio, regla, n)

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE cc_ejecuciones
            SET total_lines_reconciled = :n, rules_executed = CAST(:reglas AS jsonb),
                status = :estado, end_time = LOCALTIMESTAMP
            WHERE id = :id
        """), {"n": sum(por_regla.values()), "reglas": json.dumps(ejecutadas),
               "estado": "con_errores" if errores else "completed", "id": run_id})
    return {"ejercicio": ejercicio, "run_id": run_id, "por_regla": por_regla,
            "errores": errores, "segundos": round(time.perf_counter() - t0, 1)}


def ejecutar_punteo(ejercicios, filtro_cuentas=None, progreso=None, engine=None):
    """Puntea varios ejercicios como la opción "Todos" del original: las reglas finales
    (CROSS_YEAR, L, P, Q, R, T) solo tras el último."""
    ejercicios = sorted(set(ejercicios))
    resultados = []
    for i, ej in enumerate(ejercicios):
        resultados.append(ejecutar_ejercicio(
            ej, filtro_cuentas=filtro_cuentas,
            ejecutar_finales=(i == len(ejercicios) - 1),
            progreso=progreso, engine=engine))
    return resultados
