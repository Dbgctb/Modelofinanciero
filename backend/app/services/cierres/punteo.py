"""Punteo automático: motor + controles por ejercicio, y configuración de reglas y
cuentas de control (pantalla "Punteo automático")."""
from decimal import Decimal

from sqlalchemy import text

from .controles import CONTROLES, ejecutar_controles
from .motor import ejecutar_ejercicio
from .reglas import REGLAS


def tarea_punteo(progreso, engine, ejercicios, filtro_cuentas, controles):
    """Como la opción "Todos" del original: cada ejercicio en orden con sus controles;
    las reglas finales (CROSS_YEAR, L, P, Q, R, T) solo tras el último."""
    ejercicios = sorted(set(int(e) for e in ejercicios))
    if not ejercicios:
        raise ValueError("Elige al menos un ejercicio.")
    resultados = []
    for i, ej in enumerate(ejercicios):
        def prog(e, regla, n, _i=i):
            progreso(f"Ejercicio {e}: {regla} ({n:,} apuntes)".replace(",", "."), _i + 1, len(ejercicios))
        progreso(f"Ejercicio {ej}…", i + 1, len(ejercicios))
        r = ejecutar_ejercicio(ej, filtro_cuentas=filtro_cuentas,
                               ejecutar_finales=(i == len(ejercicios) - 1),
                               progreso=prog, engine=engine)
        if controles:
            progreso(f"Ejercicio {ej}: controles de calidad…", i + 1, len(ejercicios))
            r["incidencias"] = ejecutar_controles(engine, ej, r["run_id"], controles)
        with engine.connect() as conn:
            tot, pun = conn.execute(text("""
                SELECT COUNT(*), COUNT(*) FILTER (WHERE reconciled) FROM cc_apuntes WHERE ejercicio = :ej
            """), {"ej": ej}).one()
        r["total"], r["punteados"] = tot, pun
        resultados.append(r)
    return {"ejercicios": resultados,
            "errores": [e | {"ejercicio": r["ejercicio"]} for r in resultados for e in r["errores"]]}


def listar_reglas(conn):
    rows = conn.execute(text("""
        SELECT rule_code, rule_name, description, active, priority, tolerance_amount
        FROM cc_reglas ORDER BY priority, rule_code COLLATE "C"
    """)).mappings().all()
    return [dict(r) | {"tolerance_amount": float(r["tolerance_amount"]),
                       "implementada": r["rule_code"] in REGLAS} for r in rows]


def actualizar_regla(conn, codigo, active=None, tolerance_amount=None, description=None):
    if codigo not in REGLAS:
        raise ValueError(f"Regla desconocida: {codigo}")
    sets, params = [], {"c": codigo}
    if active is not None:
        sets.append("active = :a")
        params["a"] = active
    if tolerance_amount is not None:
        t = Decimal(str(tolerance_amount))
        if t < 0 or t > 10000:
            raise ValueError("La tolerancia debe estar entre 0 y 10.000 €")
        sets.append("tolerance_amount = :t")
        params["t"] = t
    if description is not None:
        sets.append("description = :d")
        params["d"] = description.strip()[:500]
    if sets:
        conn.execute(text(f"UPDATE cc_reglas SET {', '.join(sets)}, updated_at = LOCALTIMESTAMP WHERE rule_code = :c"),
                     params)


# ── Cuentas de control ───────────────────────────────────────────────────────

def listar_cuentas_control(conn):
    return [dict(r) | {"tolerance_pct": float(r["tolerance_pct"]) if r["tolerance_pct"] is not None else None}
            for r in conn.execute(text("""
                SELECT id, tipo, name, cuenta, min_mov, max_mov, tolerance_pct, active
                FROM cc_cuentas_control ORDER BY tipo, cuenta""")).mappings()]


def guardar_cuenta_control(conn, datos: dict, id_: int | None = None):
    tipo = datos.get("tipo")
    if tipo not in CONTROLES:
        raise ValueError("Tipo de control no válido (C, D, K o L)")
    cuenta = str(datos.get("cuenta") or "").strip()
    if not cuenta.isdigit():
        raise ValueError("La cuenta debe ser numérica (se usa como prefijo; en D, exacta)")
    valores = {"tipo": tipo, "name": (datos.get("name") or "").strip()[:150], "cuenta": cuenta,
               "min_mov": datos.get("min_mov"), "max_mov": datos.get("max_mov"),
               "tolerance_pct": datos.get("tolerance_pct"), "active": bool(datos.get("active", True))}
    if tipo == "C" and (valores["min_mov"] is None or valores["max_mov"] is None
                        or valores["min_mov"] > valores["max_mov"]):
        raise ValueError("El control C necesita mínimo y máximo de movimientos (mínimo ≤ máximo)")
    if tipo == "D" and valores["tolerance_pct"] is None:
        raise ValueError("El control D necesita una tolerancia en %")
    if id_ is None:
        return conn.execute(text("""
            INSERT INTO cc_cuentas_control (tipo, name, cuenta, min_mov, max_mov, tolerance_pct, active)
            VALUES (:tipo, :name, :cuenta, :min_mov, :max_mov, :tolerance_pct, :active) RETURNING id
        """), valores).scalar()
    n = conn.execute(text("""
        UPDATE cc_cuentas_control SET tipo = :tipo, name = :name, cuenta = :cuenta, min_mov = :min_mov,
               max_mov = :max_mov, tolerance_pct = :tolerance_pct, active = :active
        WHERE id = :id
    """), valores | {"id": id_}).rowcount
    if not n:
        raise ValueError("La cuenta de control no existe")
    return id_


def borrar_cuenta_control(conn, id_: int):
    conn.execute(text("DELETE FROM cc_cuentas_control WHERE id = :id"), {"id": id_})
