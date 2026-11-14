"""Recobros (Diagnóstico H): recobros de comisiones 440* sin conciliar, con el cobro que
les corresponde por cada recibo 4152* del asiento, y herramientas para cerrarlos.

Traducción de la pestaña "Diagnóstico H" del programa original (gui_main.py):
- diagnóstico: grupos (asiento, concepto, cuenta) de recobros pendientes; por cada recibo
  4152* del asiento (sumado por recibo), busca cobro / cobro+modificaciones /
  modificaciones / descobro / retro con el mismo importe. Estados: OK…, FALTANTE, o
  "Sin recibos en 4152*";
- los emparejamientos guardados (cc_emparejamientos_h) se aplican solos a las filas
  FALTANTE, como hacía el original al buscar;
- asignar cobro (recibo vacío) o cobro extra (mismo recibo) a una fila FALTANTE: se
  guarda al momento como emparejamiento;
- conciliar grupo completo o solo filas (regla MANUAL_H) y "Conciliar grupos" (variante
  de la regla H con los emparejamientos manuales; regla RULE_H).

Corrección: al conciliar "filas", el original solo tomaba el primer apunte de cada fila
aunque la fila juntara varios (cobro + modificación, o varios asignados); aquí se
toman todos los de la fila.
"""
import time
from collections import defaultdict
from itertools import combinations

from sqlalchemy import text
from ...core.errores import ErrorApp

SEP = "§"  # separador de la clave de grupo que viaja a la pantalla


def _clave(ak, cn, cuenta):
    return f"{ak}{SEP}{cn}{SEP}{cuenta}"


def _combo(cands, objetivo, tol=1e-5):
    for r in range(1, min(len(cands) + 1, 6)):
        for c in combinations(cands, r):
            if abs(sum(x["neto"] for x in c) - objetivo) <= tol:
                return list(c)
    return None


def diagnostico(conn, ejercicio: int, concepto: str, cuenta: str | None = None) -> dict:
    concepto = (concepto or "").strip()
    if not concepto:
        raise ErrorApp("CC-REC-001")
    p = {"ej": ejercicio, "con": f"%{concepto}%"}
    filtro_cuenta = ""
    if cuenta:
        filtro_cuenta = "AND cuenta = :cuenta"
        p["cuenta"] = cuenta.strip()
    recobros = conn.execute(text(f"""
        SELECT id, cuenta, neto::float8 AS neto, asiento_key, concepto_norm FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND cuenta LIKE '440%'
          AND concepto_norm ILIKE 'RECOBRO%' AND concepto_norm ILIKE :con
          AND (recibo_norm = '' OR recibo_norm IS NULL) {filtro_cuenta}
        ORDER BY id"""), p).mappings().all()
    grupos = {}
    for r in recobros:
        k = (r["asiento_key"], r["concepto_norm"], r["cuenta"])
        g = grupos.setdefault(k, {"ids": [], "neto": 0.0})
        g["ids"].append(r["id"])
        g["neto"] += r["neto"]
    if not grupos:
        return {"filas": [], "grupos": {}, "resumen": {"grupos": 0, "filas": 0, "faltantes": 0, "sin_recibos": 0}}

    asiento_4152 = defaultdict(list)
    for r in conn.execute(text("""
        SELECT asiento_key, recibo_norm, SUM(neto)::float8 AS neto FROM cc_apuntes
        WHERE asiento_key = ANY(:ak) AND (cuenta LIKE '4152%' OR cuenta = '4300002988')
          AND recibo_norm <> '' AND recibo_norm IS NOT NULL
        GROUP BY asiento_key, recibo_norm"""), {"ak": list({k[0] for k in grupos})}).mappings():
        asiento_4152[r["asiento_key"]].append({"recibo": r["recibo_norm"], "neto": r["neto"]})

    idx = {t: defaultdict(list) for t in ("COBRO", "MODIFICACION", "DESCOBRO", "RETRO")}
    recibos = {x["recibo"] for v in asiento_4152.values() for x in v}
    if recibos:
        for l in conn.execute(text("""
            SELECT id, cuenta, recibo_norm, neto::float8 AS neto, concepto_norm FROM cc_apuntes
            WHERE cuenta = ANY(:c) AND recibo_norm = ANY(:r)
              AND (UPPER(concepto_norm) LIKE 'COBRO%' OR UPPER(concepto_norm) LIKE 'MODIFICACION%'
                   OR UPPER(concepto_norm) LIKE 'DESCOBRO%' OR UPPER(concepto_norm) LIKE 'RETRO%')
              AND NOT reconciled
            ORDER BY fecha, id"""), {"c": list({k[2] for k in grupos}), "r": list(recibos)}).mappings():
            cn = l["concepto_norm"].upper()
            tipo = next(t for t in ("COBRO", "MODIFICACION", "DESCOBRO", "RETRO") if cn.startswith(t))
            idx[tipo][(l["cuenta"], l["recibo_norm"])].append({"id": l["id"], "neto": l["neto"]})

    filas, datos = [], {}
    usados = defaultdict(set)
    for (ak, cn, cuenta), g in grupos.items():
        clave = _clave(ak, cn, cuenta)
        ids_rec = set(g["ids"])
        datos[clave] = {"ids_recobros": g["ids"], "ids_cobros_ok": [], "neto_recobros": g["neto"],
                        "neto_cobros_ok": 0.0}
        base = {"grupo": clave, "asiento_key": ak, "concepto": cn, "cuenta": cuenta, "neto_recobros": g["neto"]}
        pares = asiento_4152.get(ak, [])
        if not pares:
            filas.append(base | {"recibo": None, "neto_4152": None, "cobros": [], "neto_cobro": None,
                                 "estado": "Sin recibos en 4152*"})
            continue
        for par in sorted(pares, key=lambda x: x["recibo"]):
            libre = lambda t: [x for x in idx[t].get((cuenta, par["recibo"]), [])  # noqa: E731
                               if x["id"] not in usados[ak] and x["id"] not in ids_rec]
            cob, mod, des, ret = libre("COBRO"), libre("MODIFICACION"), libre("DESCOBRO"), libre("RETRO")
            objetivo, sel, estado = par["neto"], None, None
            for c in cob:
                if abs(c["neto"] - objetivo) <= 1e-5:
                    sel, estado = [c], "OK"
                    break
            if sel is None:
                for c in cob:
                    r = _combo(mod, objetivo - c["neto"])
                    if r is not None:
                        sel, estado = [c] + r, "OK (Cobro + Modificación)"
                        break
            if sel is None and mod:
                r = _combo(mod, objetivo)
                if r is not None:
                    sel, estado = r, "OK (Modificaciones)"
            for lista, etiqueta in ((des, "OK (Descobro)"), (ret, "OK (Retro)")):
                if sel is None:
                    for x in lista:
                        if abs(x["neto"] - objetivo) <= 1e-5:
                            sel, estado = [x], etiqueta
                            break
            if sel:
                for x in sel:
                    usados[ak].add(x["id"])
                    datos[clave]["ids_cobros_ok"].append(x["id"])
                    datos[clave]["neto_cobros_ok"] += x["neto"]
                filas.append(base | {"recibo": par["recibo"], "neto_4152": objetivo, "cobros": [x["id"] for x in sel],
                                     "neto_cobro": sum(x["neto"] for x in sel), "estado": estado})
            else:
                filas.append(base | {"recibo": par["recibo"], "neto_4152": objetivo, "cobros": [], "neto_cobro": None,
                                     "estado": "FALTANTE — sin cobro 440*"})

    _aplicar_emparejamientos(conn, filas, datos)
    return {"filas": filas, "grupos": datos, "resumen": {
        "grupos": len(grupos), "filas": len(filas),
        "faltantes": sum(1 for f in filas if f["estado"].startswith("FALTANTE")),
        "sin_recibos": sum(1 for f in filas if f["estado"] == "Sin recibos en 4152*")}}


def _aplicar_emparejamientos(conn, filas, datos):
    """Como _reaplicar_matches_guardados del original: por (asiento, cuenta, recibo), a la
    primera fila FALTANTE, con los cobros guardados que sigan sin conciliar."""
    guardados = conn.execute(text("""
        SELECT m.asiento_key, m.cuenta_440, m.recibo, m.cobro_id, a.neto::float8 AS neto
        FROM cc_emparejamientos_h m JOIN cc_apuntes a ON a.id = m.cobro_id AND NOT a.reconciled
        ORDER BY m.created_at, m.id""")).mappings().all()
    por_clave = defaultdict(list)
    for m in guardados:
        por_clave[(m["asiento_key"], m["cuenta_440"], m["recibo"])].append(m)
    faltantes = defaultdict(list)
    for f in filas:
        if f["estado"].startswith("FALTANTE"):
            faltantes[(f["asiento_key"], f["cuenta"], f["recibo"])].append(f)
    for k, ms in por_clave.items():
        if not faltantes.get(k):
            continue
        f = faltantes[k].pop(0)
        f["cobros"] = [m["cobro_id"] for m in ms]
        f["neto_cobro"] = sum(m["neto"] for m in ms)
        f["estado"] = "OK (Manual)" if len(ms) == 1 else f"OK (Manual x{len(ms)})"
        d = datos[f["grupo"]]
        for m in ms:
            if m["cobro_id"] not in d["ids_cobros_ok"]:
                d["ids_cobros_ok"].append(m["cobro_id"])
                d["neto_cobros_ok"] += m["neto"]


def _marcar_manual_h(conn, ids, ak):
    gid = f"MANUAL_H|{int(time.time())}|{ak}"
    return conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = true, recon_rule = 'MANUAL_H', recon_group_id = :g,
               recon_run_id = NULL, recon_timestamp = LOCALTIMESTAMP
        WHERE id = ANY(:ids) AND NOT reconciled"""), {"g": gid, "ids": ids}).rowcount or 0


def conciliar(conn, ejercicio, concepto, cuenta, seleccion: list[dict], modo: str, tolerancia: float):
    """seleccion: [{grupo, recibo}] de las filas marcadas.
    modo "grupo": recobros + todos los cobros OK del grupo. "filas": recobros + cobros de esas filas."""
    diag = diagnostico(conn, ejercicio, concepto, cuenta)
    filas = {(f["grupo"], f["recibo"]): f for f in diag["filas"]}
    por_grupo = defaultdict(list)
    for s in seleccion:
        f = filas.get((s.get("grupo"), s.get("recibo")))
        if f:
            por_grupo[f["grupo"]].append(f)
    ok, err, total = [], [], 0
    for clave, fs in por_grupo.items():
        d = diag["grupos"][clave]
        ak = clave.split(SEP)[0]
        if modo == "grupo":
            cobros, neto = d["ids_cobros_ok"], d["neto_cobros_ok"]
        else:
            fs_ok = [f for f in fs if f["estado"].startswith("OK")]
            cobros = [i for f in fs_ok for i in f["cobros"]]
            neto = sum(f["neto_cobro"] for f in fs_ok)
        if not cobros:
            err.append(f"{ak}: sin cobros OK")
            continue
        ids = d["ids_recobros"] + cobros
        suma = d["neto_recobros"] + neto
        if abs(suma) > tolerancia + 1e-9:
            err.append(f"{ak}: suma {suma:.2f} € supera la tolerancia ±{tolerancia:.2f} €")
            continue
        n = _marcar_manual_h(conn, ids, ak)
        total += n
        ok.append(f"{ak}: {n} apuntes (suma {suma:.2f} €)")
    return {"conciliados": total, "grupos_ok": ok, "grupos_error": err}


def candidatos(conn, cuenta: str, recibo: str | None):
    """Asignar cobro (recibo None: cobros con recibo vacío) o cobro extra (mismo recibo)."""
    if recibo:
        cond, p = "recibo_norm = :r", {"r": recibo}
    else:
        cond, p = "(recibo_norm = '' OR recibo_norm IS NULL)", {}
    return [dict(r) | {"neto": float(r["neto"])} for r in conn.execute(text(f"""
        SELECT id, neto, concepto_norm, recibo_norm, fecha, ejercicio FROM cc_apuntes
        WHERE cuenta = :c AND {cond} AND NOT reconciled ORDER BY fecha, id LIMIT 300"""),
        {"c": cuenta, **p}).mappings()]


def guardar_emparejamientos(conn, grupo: str, recibo: str, neto_recobros: float, cobro_ids: list[int]):
    ak, cn, cuenta = grupo.split(SEP)
    validos = conn.execute(text("""
        SELECT id FROM cc_apuntes WHERE id = ANY(:ids) AND cuenta = :c AND NOT reconciled"""),
        {"ids": cobro_ids, "c": cuenta}).scalars().all()
    if len(validos) != len(set(cobro_ids)):
        raise ErrorApp("CC-REC-002")
    nuevos = 0
    for cid in validos:
        nuevos += conn.execute(text("""
            INSERT INTO cc_emparejamientos_h (asiento_key, concepto_norm, cuenta_440, neto_recobros, recibo, cobro_id)
            VALUES (:ak, :cn, :c, :n, :r, :id)
            ON CONFLICT ON CONSTRAINT uq_cc_emparejamientos_h DO NOTHING"""),
            {"ak": ak, "cn": cn, "c": cuenta, "n": round(neto_recobros, 2), "r": recibo or "", "id": cid}).rowcount
    return {"guardados": nuevos, "ya_existian": len(validos) - nuevos}


def listar_emparejamientos(conn):
    return [dict(r) | {"neto_recobros": float(r["neto_recobros"]),
                       "neto_cobro": float(r["neto_cobro"]) if r["neto_cobro"] is not None else None}
            for r in conn.execute(text("""
        SELECT m.id, m.asiento_key, m.concepto_norm, m.cuenta_440, m.neto_recobros, m.recibo, m.cobro_id,
               m.created_at, a.neto AS neto_cobro, a.reconciled AS cobro_conciliado, (a.id IS NULL) AS cobro_inexistente
        FROM cc_emparejamientos_h m LEFT JOIN cc_apuntes a ON a.id = m.cobro_id
        ORDER BY m.created_at DESC, m.id DESC""")).mappings()]


def borrar_emparejamientos(conn, ids: list[int]):
    return {"borrados": conn.execute(text("DELETE FROM cc_emparejamientos_h WHERE id = ANY(:ids)"),
                                     {"ids": ids}).rowcount}


def conciliar_grupos_h(engine, ejercicios: list[int], tolerancia: float, progreso=lambda *a, **k: None):
    """Botón "Conciliar grupos" del original (h_diag_run_rule_h): recobros "RECOBRO COMISIONES"
    con los cobros automáticos por recibo 4152* y los emparejamientos manuales guardados."""
    with engine.begin() as conn:
        manual = defaultdict(list)
        for m in conn.execute(text("SELECT asiento_key, cuenta_440, cobro_id FROM cc_emparejamientos_h ORDER BY id")):
            manual[(m.asiento_key, m.cuenta_440)].append(m.cobro_id)
        run_id = conn.execute(text("""INSERT INTO cc_ejecuciones (ejercicio, total_lines, status)
            VALUES (:ej, 0, 'running') RETURNING id"""), {"ej": ejercicios[0]}).scalar()
    total, ok, err = 0, 0, []
    for n_ej, ej in enumerate(ejercicios, 1):
        progreso(f"Ejercicio {ej}…", n_ej, len(ejercicios))
        with engine.begin() as conn:
            grupos = {}
            for r in conn.execute(text("""
                SELECT id, cuenta, neto::float8 AS neto, asiento_key, concepto_norm FROM cc_apuntes
                WHERE ejercicio = :ej AND NOT reconciled AND cuenta LIKE '440%'
                  AND (recibo_norm = '' OR recibo_norm IS NULL)
                  AND UPPER(concepto_norm) LIKE 'RECOBRO COMISIONES%'
                ORDER BY id"""), {"ej": ej}).mappings():
                g = grupos.setdefault((r["asiento_key"], r["concepto_norm"], r["cuenta"]), {"ids": [], "neto": 0.0})
                g["ids"].append(r["id"])
                g["neto"] += r["neto"]
            if not grupos:
                continue
            a4152 = defaultdict(list)
            for r in conn.execute(text("""
                SELECT asiento_key, recibo_norm, neto::float8 AS neto FROM cc_apuntes
                WHERE asiento_key = ANY(:ak) AND (cuenta LIKE '4152%' OR cuenta = '4300002988')
                  AND recibo_norm <> '' AND recibo_norm IS NOT NULL ORDER BY id"""),
                    {"ak": list({k[0] for k in grupos})}).mappings():
                a4152[r["asiento_key"]].append(r)
            idx = {t: defaultdict(list) for t in ("COBRO", "MODIFICACION", "DESCOBRO", "RETRO")}
            recibos = {x["recibo_norm"] for v in a4152.values() for x in v}
            if recibos:
                for l in conn.execute(text("""
                    SELECT id, cuenta, recibo_norm, neto::float8 AS neto, concepto_norm FROM cc_apuntes
                    WHERE cuenta = ANY(:c) AND recibo_norm = ANY(:r)
                      AND (UPPER(concepto_norm) LIKE 'COBRO%' OR UPPER(concepto_norm) LIKE 'MODIFICACION%'
                           OR UPPER(concepto_norm) LIKE 'DESCOBRO%' OR UPPER(concepto_norm) LIKE 'RETRO%')
                      AND NOT reconciled ORDER BY fecha, id"""),
                        {"c": list({k[2] for k in grupos}), "r": list(recibos)}).mappings():
                    cn = l["concepto_norm"].upper()
                    t = next(t for t in ("COBRO", "MODIFICACION", "DESCOBRO", "RETRO") if cn.startswith(t))
                    idx[t][(l["cuenta"], l["recibo_norm"])].append(l)
            usados = {t: set() for t in idx}
            pares = []
            for (ak, cn, cuenta), g in grupos.items():
                ids_rec = set(g["ids"])
                sel = []
                for par in a4152.get(ak, []):
                    clave, objetivo, hecho = (cuenta, par["recibo_norm"]), par["neto"], False
                    for c in idx["COBRO"].get(clave, []):
                        if c["id"] in usados["COBRO"] or c["id"] in ids_rec:
                            continue
                        mod = next((m for m in idx["MODIFICACION"].get(clave, [])
                                    if m["id"] not in usados["MODIFICACION"] and m["id"] not in ids_rec), None)
                        if abs(round(c["neto"] + (mod["neto"] if mod else 0.0) - objetivo, 6)) <= 1e-5:
                            usados["COBRO"].add(c["id"])
                            sel.append((c["id"], c["neto"]))
                            if mod:
                                usados["MODIFICACION"].add(mod["id"])
                                sel.append((mod["id"], mod["neto"]))
                            hecho = True
                            break
                    for t in ("DESCOBRO", "RETRO"):
                        if hecho:
                            break
                        for x in idx[t].get(clave, []):
                            if x["id"] in usados[t] or x["id"] in ids_rec:
                                continue
                            if abs(round(x["neto"] - objetivo, 6)) <= 1e-5:
                                usados[t].add(x["id"])
                                sel.append((x["id"], x["neto"]))
                                hecho = True
                                break
                for cid in manual.get((ak, cuenta), []):
                    if cid in usados["COBRO"] or cid in ids_rec:
                        continue
                    r = conn.execute(text("SELECT id, neto::float8 AS neto FROM cc_apuntes WHERE id = :i AND NOT reconciled"),
                                     {"i": cid}).mappings().first()
                    if r:
                        sel.append((r["id"], r["neto"]))
                        usados["COBRO"].add(r["id"])
                if not sel:
                    err.append(f"{ak}: sin cobros")
                    continue
                todos = list(ids_rec) + [i for i, _ in sel]
                suma = g["neto"] + sum(n for _, n in sel)
                if abs(suma) > tolerancia:
                    err.append(f"{ak}: suma {suma:.2f} € supera la tolerancia ±{tolerancia:.2f} €")
                    continue
                gid = f"H|{ak}|{cn[:30]}"
                pares += [(gid, i) for i in todos]
                ok += 1
            if pares:
                conn.execute(text("""
                    UPDATE cc_apuntes a SET reconciled = true, recon_rule = 'RULE_H', recon_group_id = v.g,
                           recon_run_id = :run, recon_timestamp = LOCALTIMESTAMP
                    FROM unnest(CAST(:ids AS integer[]), CAST(:gs AS text[])) AS v(id, g) WHERE a.id = v.id"""),
                             {"run": run_id, "ids": [i for _, i in pares], "gs": [g for g, _ in pares]})
                total += len(pares)
    with engine.begin() as conn:
        conn.execute(text("""UPDATE cc_ejecuciones SET status = 'completed', total_lines_reconciled = :n,
            rules_executed = '["RECOBROS_H"]'::jsonb, end_time = LOCALTIMESTAMP WHERE id = :id"""),
                     {"n": total, "id": run_id})
    return {"ejercicios": ejercicios, "apuntes": total, "grupos_ok": ok, "grupos_error": len(err),
            "errores": err[:50]}


def excel_diagnostico(diag: dict, ejercicio, concepto, ruta):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = f"Diag H {ejercicio}"
    ws.append([f"Diagnóstico Regla H — Recobros no conciliados | Ejercicio: {ejercicio} | Concepto: {concepto}"])
    ws["A1"].font = Font(bold=True, size=12, color="1565C0")
    ws.append(["Asiento", "Concepto recobro", "Cuenta 440", "Neto recobros (€)", "Recibo",
               "Apuntes cobro", "Neto cobro (€)", "Neto 4152* (€)", "Estado"])
    for c in ws[2]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1565C0")
    colores = {"OK": "D4EDDA", "FALTANTE": "F8D7DA"}
    fila = 2
    for f in diag["filas"]:
        fila += 1
        ws.append([f["asiento_key"], f["concepto"], f["cuenta"], round(f["neto_recobros"], 2), f["recibo"] or "—",
                   ", ".join(map(str, f["cobros"])), None if f["neto_cobro"] is None else round(f["neto_cobro"], 2),
                   None if f["neto_4152"] is None else round(f["neto_4152"], 2), f["estado"]])
        color = next((v for k, v in colores.items() if f["estado"].startswith(k)), "FFF3CD")
        relleno = PatternFill("solid", fgColor=color)
        for col in range(1, 10):
            ws.cell(fila, col).fill = relleno
    r = diag["resumen"]
    ws.append([])
    ws.append([f"Filas: {r['filas']} | Faltantes: {r['faltantes']} | Sin recibos en 4152*: {r['sin_recibos']}"])
    for col, w in zip("ABCDEFGHI", (18, 40, 13, 15, 12, 18, 14, 14, 28)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A3"
    wb.save(ruta)
