"""Motor de conciliación bancaria: movimientos del extracto (cc_extractos) contra los
apuntes de la cuenta 572 del banco (cc_apuntes).

Traducción fiel de app/services/bank_reconciliation.py del programa original. Niveles,
en este orden (cada nivel solo ve lo que dejan libre los anteriores):

1. Misma fecha e importe exacto (1:1).
2. Importe exacto con ±N días (N configurable por cuenta; 15 si no hay configuración).
3. Misma fecha con diferencia de hasta 5,00 € (fija en el original: no usa la
   tolerancia configurada), el de menor diferencia.
7. Liquidaciones: apuntes "Liquidac…" con el mismo "Nº XXXX" en el mismo mes, cuya
   suma cuadra (±0,01) con un movimiento del mismo mes o del siguiente (N:1).
8. Movimientos "Ingreso…" contra apuntes "Cobro…"/"Extorno…" del mismo mes: primero
   los del mismo día, luego todo el mes y, si no, una selección voraz (N:1).
9. Igual que el 8 con "Devoluc…" contra "Devolu…".

Como en el original: los niveles 1 a 3 no ponen grupo; 7, 8 y 9 ponen
LIQ|, LIQ8| y DEV9| y el movimiento guarda el primer apunte del grupo.
Importes en coma flotante (como REAL) para que las comparaciones den lo mismo, y
los órdenes que deciden qué se consume primero son explícitos (por fecha e id).
"""
import logging
import re
import time
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text
from ....core.errores import ErrorApp

log = logging.getLogger(__name__)

_FECHA_BANCO = "COALESCE(fecha_operacion, fecha_valor, fecha_contable, fecha)"
_RE_LIQ = re.compile(r"N[\xba\xb0o]\.?\s*(\d{4})")


def _filas(conn, sql, **p):
    return conn.execute(text(sql), p).mappings().all()


def configuracion(conn, cuenta_572: str) -> dict:
    """Días del nivel 2 y tolerancias de los niveles 8 y 9 guardados para la cuenta."""
    cfg = conn.execute(text("SELECT level_2_days FROM cc_banco_config WHERE cuenta_572 = :c"),
                       {"c": cuenta_572}).first()
    tol = {r.key: r.value for r in conn.execute(text(
        "SELECT key, value FROM cc_config WHERE key IN (:k8, :k9)"),
        {"k8": f"nivel8_tolerance_{cuenta_572}", "k9": f"nivel9_tolerance_{cuenta_572}"})}
    return {
        "dias_nivel2": int(cfg.level_2_days) if cfg and cfg.level_2_days else 15,
        "tol_nivel8": float(tol.get(f"nivel8_tolerance_{cuenta_572}", 0.01)),
        "tol_nivel9": float(tol.get(f"nivel9_tolerance_{cuenta_572}", 0.01)),
    }


def _marcar_1a1(conn, nivel, pares):
    """pares: [(id_extracto, id_apunte)] de los niveles 1 a 3."""
    if not pares:
        return
    conn.execute(text("""
        UPDATE cc_extractos e SET reconciled = true, recon_level = :nivel, recon_journal_id = v.jid,
               recon_timestamp = LOCALTIMESTAMP
        FROM unnest(CAST(:bids AS integer[]), CAST(:jids AS integer[])) AS v(bid, jid)
        WHERE e.id = v.bid
    """), {"nivel": nivel, "bids": [b for b, _ in pares], "jids": [j for _, j in pares]})
    conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = true, recon_rule = :regla, recon_timestamp = LOCALTIMESTAMP
        WHERE id = ANY(:jids)
    """), {"regla": f"NIVEL_{nivel}", "jids": [j for _, j in pares]})


def _marcar_grupo(conn, nivel, gid, id_extracto, ids_apuntes):
    """Niveles 7, 8 y 9: N apuntes contra 1 movimiento."""
    conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = true, recon_rule = :regla, recon_group_id = :gid,
               recon_timestamp = LOCALTIMESTAMP
        WHERE id = ANY(:ids)
    """), {"regla": f"NIVEL_{nivel}", "gid": gid, "ids": ids_apuntes})
    conn.execute(text("""
        UPDATE cc_extractos SET reconciled = true, recon_level = :nivel, recon_group_id = :gid,
               recon_journal_id = :jid, recon_timestamp = LOCALTIMESTAMP
        WHERE id = :bid
    """), {"nivel": str(nivel), "gid": gid, "jid": ids_apuntes[0], "bid": id_extracto})


def _voraz(candidatos, objetivo, tolerancia, usados):
    """Acumula de mayor a menor |neto| mientras no aleje del objetivo (igual que el original)."""
    acum, sel = 0.0, []
    for r in candidatos:
        if r["id"] in usados:
            continue
        prueba = round(acum + r["neto"], 2)
        if abs(prueba - objetivo) <= abs(acum - objetivo) or abs(prueba - objetivo) <= tolerancia:
            acum = prueba
            sel.append(r)
            if abs(acum - objetivo) <= tolerancia:
                return sel
    return None


def _nivel_agrupado(conn, nivel, prefijo_gid, cuenta_572, banco_id, ejercicio, patron_banco,
                    condicion_diario, tolerancia, banco_libre, diario_libre):
    """Niveles 8 y 9: un movimiento contra la suma de apuntes del mismo mes."""
    movs = [r for r in _filas(conn, f"""
        SELECT id, importe::float8 AS importe, {_FECHA_BANCO} AS fecha
        FROM cc_extractos
        WHERE banco_id = :b AND ejercicio = :ej AND NOT reconciled
          AND upper(concepto) LIKE :patron AND {_FECHA_BANCO} IS NOT NULL
        ORDER BY {_FECHA_BANCO}, id
    """, b=banco_id, ej=ejercicio, patron=patron_banco)]
    apuntes = _filas(conn, f"""
        SELECT id, neto::float8 AS neto, fecha FROM cc_apuntes
        WHERE ejercicio = :ej AND cuenta = :c AND NOT reconciled AND fecha IS NOT NULL
          AND ({condicion_diario})
        ORDER BY fecha, id
    """, ej=ejercicio, c=cuenta_572)
    por_mes = defaultdict(list)
    for r in apuntes:
        por_mes[r["fecha"].month].append(r)
    for m in por_mes:
        por_mes[m].sort(key=lambda x: abs(x["neto"]), reverse=True)

    usados, n = set(), 0
    for b in movs:
        if b["id"] not in banco_libre:
            continue
        objetivo = round(b["importe"], 2)
        cands = [r for r in por_mes.get(b["fecha"].month, []) if r["id"] not in usados and r["id"] in diario_libre]
        if not cands:
            continue
        sel = None
        del_dia = [r for r in cands if r["fecha"] == b["fecha"]]
        if del_dia and abs(round(sum(r["neto"] for r in del_dia), 2) - objetivo) <= tolerancia:
            sel = del_dia
        if sel is None and abs(round(sum(r["neto"] for r in cands), 2) - objetivo) <= tolerancia:
            sel = cands
        if sel is None:
            sel = _voraz(cands, objetivo, tolerancia, usados)
        if not sel:
            continue
        gid = f"{prefijo_gid}|{cuenta_572}|{b['fecha'].month:02d}|{b['id']}"
        _marcar_grupo(conn, nivel, gid, b["id"], [r["id"] for r in sel])
        for r in sel:
            usados.add(r["id"])
            diario_libre.pop(r["id"], None)
        banco_libre.pop(b["id"], None)
        n += len(sel) + 1
    return n


def conciliar(engine, ejercicio: int, banco_id: int, progreso=lambda *a, **k: None) -> dict:
    """Ejecuta los niveles automáticos para un banco y ejercicio. Una sola transacción:
    si algo falla, no queda nada a medias."""
    t0 = time.perf_counter()
    with engine.begin() as conn:
        banco = conn.execute(text("SELECT id, nombre, cuenta_572 FROM cc_bancos WHERE id = :b"),
                             {"b": banco_id}).mappings().first()
        if not banco or not banco["cuenta_572"]:
            raise ErrorApp("CC-BAN-001")
        cuenta = banco["cuenta_572"]
        cfg = configuracion(conn, cuenta)
        run_id = conn.execute(text("""
            INSERT INTO cc_banco_ejecuciones (ejercicio, banco_id, cuenta_contable, cuenta_banco,
                                              fecha_conciliacion, status)
            VALUES (:ej, :b, :c, '', LOCALTIMESTAMP, 'RUNNING') RETURNING id
        """), {"ej": ejercicio, "b": banco_id, "c": cuenta}).scalar()

    stats = {}
    with engine.begin() as conn:
        banco_libre = {r["id"]: r for r in _filas(conn, f"""
            SELECT id, importe::float8 AS importe, {_FECHA_BANCO} AS fecha FROM cc_extractos
            WHERE banco_id = :b AND ejercicio = :ej AND NOT reconciled ORDER BY id
        """, b=banco_id, ej=ejercicio)}
        diario_libre = {r["id"]: r for r in _filas(conn, """
            SELECT id, fecha, neto::float8 AS neto FROM cc_apuntes
            WHERE cuenta = :c AND ejercicio = :ej AND NOT reconciled ORDER BY id
        """, c=cuenta, ej=ejercicio)}

        # Nivel 1: fecha + importe exactos
        idx = defaultdict(list)
        for x in diario_libre.values():
            idx[(x["fecha"], round(x["neto"], 2))].append(x["id"])
        pares = []
        for bid in list(banco_libre):
            b = banco_libre[bid]
            jid = next((j for j in idx.get((b["fecha"], round(b["importe"], 2)), []) if j in diario_libre), None)
            if jid is not None:
                pares.append((bid, jid))
                del banco_libre[bid], diario_libre[jid]
        _marcar_1a1(conn, "1", pares)
        stats["nivel_1"] = len(pares)
        progreso(f"Nivel 1: {len(pares)}", 1, 6)

        # Nivel 2: importe exacto, ±N días (más cercano primero; a igual distancia, el posterior)
        idx = defaultdict(list)
        for x in diario_libre.values():
            idx[(x["fecha"], round(x["neto"], 2))].append(x["id"])
        pares = []
        for bid in list(banco_libre):
            b = banco_libre[bid]
            if b["fecha"] is None:
                continue
            imp, jid = round(b["importe"], 2), None
            for delta in range(1, cfg["dias_nivel2"] + 1):
                for signo in (1, -1):
                    d = b["fecha"] + timedelta(days=delta * signo)
                    jid = next((j for j in idx.get((d, imp), []) if j in diario_libre), None)
                    if jid is not None:
                        break
                if jid is not None:
                    break
            if jid is not None:
                pares.append((bid, jid))
                del banco_libre[bid], diario_libre[jid]
        _marcar_1a1(conn, "2", pares)
        stats["nivel_2"] = len(pares)
        progreso(f"Nivel 2: {len(pares)}", 2, 6)

        # Nivel 3: misma fecha, diferencia <= 5,00 €
        por_fecha = defaultdict(list)
        for x in diario_libre.values():
            por_fecha[x["fecha"]].append(x["id"])
        pares = []
        for bid in list(banco_libre):
            b = banco_libre[bid]
            mejor, mejor_dif = None, float("inf")
            for jid in por_fecha.get(b["fecha"], []):
                if jid not in diario_libre:
                    continue
                dif = abs(diario_libre[jid]["neto"] - b["importe"])
                if dif <= 5.00 and dif < mejor_dif:
                    mejor, mejor_dif = jid, dif
            if mejor is not None:
                pares.append((bid, mejor))
                del banco_libre[bid], diario_libre[mejor]
        _marcar_1a1(conn, "3", pares)
        stats["nivel_3"] = len(pares)
        progreso(f"Nivel 3: {len(pares)}", 3, 6)

        # Nivel 7: liquidaciones agrupadas por "Nº XXXX" y mes
        grupos = defaultdict(list)
        for r in _filas(conn, """
            SELECT id, concepto, neto::float8 AS neto, fecha FROM cc_apuntes
            WHERE ejercicio = :ej AND cuenta = :c AND NOT reconciled AND upper(concepto) LIKE 'LIQUIDAC%'
            ORDER BY id
        """, ej=ejercicio, c=cuenta):
            m = _RE_LIQ.search(r["concepto"] or "")
            if m:
                grupos[(r["fecha"].month, r["fecha"].year, m.group(1))].append(r)
        n7 = 0
        for (mes, _anyo, clave), regs in grupos.items():
            suma = round(sum(r["neto"] for r in regs), 2)
            meses = {mes, (mes % 12) + 1}
            mejor, mejor_dif = None, float("inf")
            for bid, b in banco_libre.items():
                if not b["fecha"] or b["fecha"].month not in meses:
                    continue
                dif = abs(round(b["importe"], 2) - suma)
                if dif <= 0.01 and dif < mejor_dif:
                    mejor, mejor_dif = bid, dif
            if mejor is None:
                continue
            _marcar_grupo(conn, 7, f"LIQ|{cuenta}|{mes:02d}|{clave}", mejor, [r["id"] for r in regs])
            for r in regs:
                diario_libre.pop(r["id"], None)
            del banco_libre[mejor]
            n7 += len(regs) + 1
        stats["nivel_7"] = n7
        progreso(f"Nivel 7: {n7}", 4, 6)

        # Niveles 8 y 9
        stats["nivel_8"] = _nivel_agrupado(
            conn, 8, "LIQ8", cuenta, banco_id, ejercicio, "INGRESO%",
            "upper(concepto) LIKE 'COBRO%' OR upper(concepto) LIKE 'EXTORNO%'",
            cfg["tol_nivel8"], banco_libre, diario_libre)
        progreso(f"Nivel 8: {stats['nivel_8']}", 5, 6)
        stats["nivel_9"] = _nivel_agrupado(
            conn, 9, "DEV9", cuenta, banco_id, ejercicio, "DEVOLUC%",
            "upper(concepto) LIKE 'DEVOLU%'", cfg["tol_nivel9"], banco_libre, diario_libre)
        progreso(f"Nivel 9: {stats['nivel_9']}", 6, 6)

        tot, pend = conn.execute(text("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE NOT reconciled) FROM cc_extractos
            WHERE banco_id = :b AND ejercicio = :ej
        """), {"b": banco_id, "ej": ejercicio}).one()
        pend_diario = conn.execute(text("""
            SELECT COUNT(*) FROM cc_apuntes WHERE cuenta = :c AND ejercicio = :ej AND NOT reconciled
        """), {"c": cuenta, "ej": ejercicio}).scalar()
        conn.execute(text("""
            UPDATE cc_banco_ejecuciones SET status = 'COMPLETED', pct = :pct WHERE id = :id
        """), {"pct": round((tot - pend) / tot * 100, 2) if tot else None, "id": run_id})

    return {"run_id": run_id, "banco": banco["nombre"], "cuenta_572": cuenta, "ejercicio": ejercicio,
            "niveles": stats, "total_banco": tot, "conciliados_banco": tot - pend,
            "pendientes_banco": pend, "pendientes_diario": pend_diario,
            "segundos": round(time.perf_counter() - t0, 1), "configuracion": cfg}
