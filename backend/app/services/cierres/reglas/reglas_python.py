"""Reglas de punteo que son un algoritmo en Python: C, E, H, K, K2, RETRO, RETROCESO (por
ejercicio), Q (todos los ejercicios) y V (cierre de 440*, la última).

Traducción fiel de app/rules/rule_*.py del programa original:
- `neto` se lee como float8 para que el algoritmo (sumas, redondeos, bisect) dé el
  mismo resultado que con REAL en SQLite;
- los órdenes que deciden qué apunte se consume primero son explícitos
  (COLLATE "C" y desempate por id);
- los group_id tienen el mismo formato, `hash()` de tuplas de enteros incluido.
Cada función: ejecutar(conn, ejercicio, run_id, tol, **kw) -> apuntes marcados.
"""
import bisect
from collections import defaultdict
from itertools import combinations

from sqlalchemy import text

from ._comun import SET_PUNTEO, filtro_cuentas_sql, marcar


def _filas(conn, sql, **params):
    return conn.execute(text(sql), params).mappings().all()


# ── RULE_C — Liquidaciones 410000* + recibos de la misma cuenta y fecha ───────
# Suma en NUMERIC exacto (no float): con tolerancia 0,00 el ruido de coma flotante
# rechazaba grupos que cuadran al céntimo (prueba de paridad, 2026-11-14).

def regla_c(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    grupos = _filas(conn, """
        SELECT cuenta, fecha, array_agg(id) AS ids, SUM(neto) AS neto_liquida
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled
          AND cuenta LIKE '410000%'
          AND concepto_norm ILIKE 'LIQUIDA%'
          AND (recibo_norm = '' OR recibo_norm IS NULL)
        GROUP BY cuenta, fecha
    """, ej=ejercicio)
    if not grupos:
        return 0
    cuentas = list({g["cuenta"] for g in grupos})
    fechas = list({g["fecha"] for g in grupos})
    recibos = _filas(conn, """
        SELECT id, cuenta, fecha, neto
        FROM cc_apuntes
        WHERE ejercicio = :ej AND cuenta = ANY(:cuentas) AND fecha = ANY(:fechas)
          AND recibo_norm <> '' AND recibo_norm IS NOT NULL AND NOT reconciled
        ORDER BY id
    """, ej=ejercicio, cuentas=cuentas, fechas=fechas)
    idx = defaultdict(list)
    for r in recibos:
        idx[(r["cuenta"], r["fecha"])].append(r)

    pares = []
    for g in grupos:
        lineas = idx.get((g["cuenta"], g["fecha"]), [])
        if not lineas:
            continue
        suma = g["neto_liquida"] + sum(r["neto"] for r in lineas)
        if abs(suma) > tol:
            continue
        gid = f"C|{g['cuenta']}|{g['fecha'].isoformat()}"
        for lid in list(g["ids"]) + [r["id"] for r in lineas]:
            pares.append((gid, lid))
    return marcar(conn, "RULE_C", pares, run_id, filtro_cuentas=filtro_cuentas)


# ── RULE_E — pares de la misma cuenta+recibo con fechas a 1 día ───────────────

def regla_e(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    candidatos = _filas(conn, """
        SELECT cuenta, recibo_norm,
               array_agg(id ORDER BY id) AS ids,
               array_agg(fecha ORDER BY id) AS fechas,
               array_agg(neto::float8 ORDER BY id) AS netos
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND recibo_norm <> ''
          AND cuenta NOT LIKE '440%'
        GROUP BY cuenta, recibo_norm
        HAVING COUNT(*) = 2
    """, ej=ejercicio)
    ids = []
    for c in candidatos:
        f1, f2 = c["fechas"]
        n1, n2 = c["netos"]
        if abs((f2 - f1).days) == 1 and abs(n1 + n2) <= tol:
            ids.extend(c["ids"])
    if not ids:
        return 0
    fc, fc_params = filtro_cuentas_sql(filtro_cuentas)
    res = conn.execute(text(f"""
        UPDATE cc_apuntes
        SET {SET_PUNTEO}, recon_group_id = 'E|' || cuenta || '|' || recibo_norm
        WHERE id = ANY(:ids) AND NOT reconciled {fc}
    """), {"regla": "RULE_E", "run_id": run_id, "ids": ids, **fc_params})
    return res.rowcount or 0


# ── RULE_H — Recobro de comisiones 440* contra cobros de los recibos 4152* ────

def _buscar_combinacion(candidatos, objetivo, tolerancia=1e-5):
    """Subconjunto (hasta 5 elementos) cuyo neto sume `objetivo`. Igual que el original."""
    for r in range(1, min(len(candidatos) + 1, 6)):
        for combo in combinations(candidatos, r):
            if abs(sum(c["neto"] for c in combo) - objetivo) <= tolerancia:
                return list(combo)
    return None


def regla_h(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    recobros = _filas(conn, """
        SELECT id, cuenta, neto::float8 AS neto, asiento_key, concepto_norm
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled
          AND cuenta LIKE '440%'
          AND (recibo_norm = '' OR recibo_norm IS NULL)
          AND concepto_norm ILIKE 'RECOBRO%'
        ORDER BY id
    """, ej=ejercicio)
    if not recobros:
        return 0

    grupos = {}
    for rec in recobros:
        key = (rec["asiento_key"], rec["concepto_norm"], rec["cuenta"])
        g = grupos.setdefault(key, {"ids": [], "neto": 0.0, "cuenta": None})
        g["ids"].append(rec["id"])
        g["neto"] += rec["neto"]
        g["cuenta"] = rec["cuenta"]

    asientos = list({ak for (ak, _, _) in grupos})
    filas_4152 = _filas(conn, """
        SELECT asiento_key, recibo_norm, neto::float8 AS neto
        FROM cc_apuntes
        WHERE asiento_key = ANY(:asientos)
          AND (cuenta LIKE '4152%' OR cuenta = '4300002988')
          AND recibo_norm <> '' AND recibo_norm IS NOT NULL
        ORDER BY id
    """, asientos=asientos)
    if not filas_4152:
        return 0
    asiento_4152 = defaultdict(list)
    for f in filas_4152:
        asiento_4152[f["asiento_key"]].append({"recibo_norm": f["recibo_norm"], "neto": f["neto"]})

    cuentas, recibos = set(), set()
    for (ak, _, _), g in grupos.items():
        pares_4152 = asiento_4152.get(ak, [])
        if pares_4152:
            cuentas.add(str(g["cuenta"]))
            recibos.update(p["recibo_norm"] for p in pares_4152)
    if not recibos:
        return 0

    lineas = _filas(conn, """
        SELECT id, cuenta, recibo_norm, neto::float8 AS neto, concepto_norm
        FROM cc_apuntes
        WHERE cuenta = ANY(:cuentas) AND recibo_norm = ANY(:recibos)
          AND (UPPER(concepto_norm) LIKE 'COBRO%'
               OR UPPER(concepto_norm) LIKE 'MODIFICACION%'
               OR UPPER(concepto_norm) LIKE 'DESCOBRO%'
               OR UPPER(concepto_norm) LIKE 'RETRO%')
          AND NOT reconciled
        ORDER BY fecha ASC, id ASC
    """, cuentas=list(cuentas), recibos=list(recibos))
    cobros_idx, modif_idx, descobro_idx, retro_idx = (defaultdict(list) for _ in range(4))
    for l in lineas:
        key = (l["cuenta"], l["recibo_norm"])
        cn = l["concepto_norm"].upper()
        item = {"id": l["id"], "neto": l["neto"]}
        if cn.startswith("COBRO"):
            cobros_idx[key].append(item)
        elif cn.startswith("MODIFICACION"):
            modif_idx[key].append(item)
        elif cn.startswith("DESCOBRO"):
            descobro_idx[key].append(item)
        elif cn.startswith("RETRO"):
            retro_idx[key].append(item)

    pares = []
    usados_global = set()
    usados_por_asiento = defaultdict(set)
    for (ak, _cn, _ct), g in grupos.items():
        cuenta = str(g["cuenta"])
        ids_recobros = set(g["ids"])
        pares_4152 = asiento_4152.get(ak)
        if not pares_4152:
            continue
        usados = usados_global | usados_por_asiento[ak]
        seleccion = []
        completo = True
        for par in pares_4152:
            recibo, neto_4152 = par["recibo_norm"], par["neto"]
            clave = (cuenta, recibo)
            libre = lambda lst: [x for x in lst if x["id"] not in usados and x["id"] not in ids_recobros]  # noqa: E731
            cobros_d, modifs_d = libre(cobros_idx.get(clave, [])), libre(modif_idx.get(clave, []))
            descobros_d, retros_d = libre(descobro_idx.get(clave, [])), libre(retro_idx.get(clave, []))

            combo = None
            for c in cobros_d:                                    # 1. cobro solo
                if abs(c["neto"] - neto_4152) <= 1e-5:
                    combo = [c]
                    break
            if combo is None:                                     # 2. cobro + modificaciones
                for c in cobros_d:
                    r = _buscar_combinacion(list(modifs_d), neto_4152 - c["neto"], 1e-5)
                    if r is not None:
                        combo = [c] + r
                        break
            if combo is None and modifs_d:                        # 3. modificaciones solas
                combo = _buscar_combinacion(modifs_d, neto_4152, 1e-5)
            if combo is None:                                     # 4. descobro solo
                for d in descobros_d:
                    if abs(d["neto"] - neto_4152) <= 1e-5:
                        combo = [d]
                        break
            if combo is None:                                     # 5. retro solo
                for r in retros_d:
                    if abs(r["neto"] - neto_4152) <= 1e-5:
                        combo = [r]
                        break
            if combo is None:
                completo = False
                break
            seleccion.extend(combo)

        if not completo or not seleccion:
            continue
        all_ids = list(ids_recobros) + [c["id"] for c in seleccion]
        if len(all_ids) < 2:
            continue
        if abs(g["neto"] + sum(c["neto"] for c in seleccion)) > tol:
            continue
        for c in seleccion:
            usados_global.add(c["id"])
            usados_por_asiento[ak].add(c["id"])
        gid = f"H|{ak}|{cuenta}|{abs(hash(tuple(sorted(all_ids)))) % 100000}"
        pares.extend((gid, lid) for lid in all_ids)
    return marcar(conn, "RULE_H", pares, run_id, filtro_cuentas=filtro_cuentas)


# ── RULE_K / RULE_K2 — emparejamiento 1:1 por cuenta+recibo ──────────────────

_CONCEPTOS_K = """(concepto_norm ILIKE 'COBRO%' OR concepto_norm ILIKE 'DESCOBRO%'
     OR concepto_norm ILIKE 'RETRO%' OR concepto_norm ILIKE 'RECOBRO%'
     OR concepto_norm ILIKE 'A EFECTIVO%' OR concepto_norm ILIKE 'DE EFECTIVO%'
     OR concepto_norm ILIKE 'A PAPEL%' OR concepto_norm ILIKE 'DE PAPEL%'
     OR concepto_norm ILIKE 'ANULACION%' OR concepto_norm ILIKE 'MODIFICACION%')"""


def _emparejar(origen, destino, tol, usados_dest):
    """Para cada elemento de `origen`, el de `destino` libre con menor |suma| <= tol.

    Devuelve [(i_origen, j_destino)]. Mismo recorrido y desempate que el original.
    """
    res = []
    for i, a in enumerate(origen):
        mejor_j, mejor = None, float("inf")
        for j, b in enumerate(destino):
            if j in usados_dest:
                continue
            diff = abs(a["neto"] + b["neto"])
            if diff <= tol and diff < mejor:
                mejor_j, mejor = j, diff
        if mejor_j is not None:
            usados_dest.add(mejor_j)
            res.append((i, mejor_j))
    return res


def _clasificar_k(regs):
    tipos = {k: [] for k in ("cobro", "descobro", "a_ef", "de_ef", "a_pa", "de_pa")}
    for r in regs:
        c = r["concepto_norm"].upper()
        if c.startswith("COBRO"):
            tipos["cobro"].append(r)
        elif c.startswith(("DESCOBRO", "RETRO", "RECOBRO")):
            tipos["descobro"].append(r)
        elif c.startswith("A EFECTIVO"):
            tipos["a_ef"].append(r)
        elif c.startswith("DE EFECTIVO"):
            tipos["de_ef"].append(r)
        elif c.startswith("A PAPEL"):
            tipos["a_pa"].append(r)
        elif c.startswith("DE PAPEL"):
            tipos["de_pa"].append(r)
    return tipos


def _regla_k_comun(conn, ejercicio, run_id, tol, regla, filtro_cuenta, gid_fn, gid2_fn, filtro_cuentas=None):
    registros = _filas(conn, f"""
        SELECT id, cuenta, recibo_norm, concepto_norm, neto::float8 AS neto, fecha
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND recibo_norm <> ''
          AND {filtro_cuenta} AND {_CONCEPTOS_K}
        ORDER BY cuenta COLLATE "C", recibo_norm COLLATE "C", fecha, id
    """, ej=ejercicio)
    grupos = defaultdict(list)
    for r in registros:
        grupos[(r["cuenta"], r["recibo_norm"])].append(r)

    pares = []
    for (cuenta, recibo), regs in grupos.items():
        if len(regs) < 2:
            continue
        t = _clasificar_k(regs)
        cobros_usados = set()
        for orig, dest in (("cobro", "descobro"), ("a_ef", "de_ef"), ("a_pa", "de_pa")):
            if not (t[orig] and t[dest]):
                continue
            for i, j in _emparejar(t[orig], t[dest], tol, set()):
                a, b = t[orig][i]["id"], t[dest][j]["id"]
                gid = gid_fn(cuenta, recibo, a, b)
                pares += [(gid, a), (gid, b)]
                if orig == "cobro":
                    cobros_usados.add(i)
        # Fase 2: cobros sobrantes positivos contra negativos
        restantes = [c for i, c in enumerate(t["cobro"]) if i not in cobros_usados]
        if len(restantes) >= 2:
            pos = [r for r in restantes if r["neto"] > 0]
            neg = [r for r in restantes if r["neto"] < 0]
            for i, j in _emparejar(pos, neg, tol, set()):
                a, b = pos[i]["id"], neg[j]["id"]
                gid = gid2_fn(cuenta, recibo, a, b)
                pares += [(gid, a), (gid, b)]
    return marcar(conn, regla, pares, run_id, filtro_cuentas=filtro_cuentas)


def regla_k(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    """430*/415*: COBRO↔DESCOBRO/RETRO/RECOBRO, A↔DE EFECTIVO, A↔DE PAPEL, cobros +/−."""
    return _regla_k_comun(
        conn, ejercicio, run_id, tol, "RULE_K",
        "(cuenta LIKE '430%' OR cuenta LIKE '415%')",
        lambda c, r, a, b: f"K|{c}|{r}",
        lambda c, r, a, b: f"K2|{c}|{r}",
        filtro_cuentas=filtro_cuentas,
    )


def regla_k2(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    """Igual que K, solo cuentas 440*, con un grupo por pareja."""
    return _regla_k_comun(
        conn, ejercicio, run_id, tol, "RULE_K2",
        "cuenta LIKE '440%'",
        lambda c, r, a, b: f"K2|{c}|{r}|{abs(hash((a, b))) % 100000}",
        lambda c, r, a, b: f"K2B|{c}|{r}|{abs(hash((a, b))) % 100000}",
        filtro_cuentas=filtro_cuentas,
    )


# ── RULE_RETRO — Retroceso% contra Retro.Reco% de la misma cuenta y fecha (440*) ─

def regla_retro(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    retrocesos = _filas(conn, """
        SELECT id, cuenta, fecha, neto::float8 AS neto
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND cuenta LIKE '440%'
          AND UPPER(concepto_norm) LIKE 'RETROCESO%'
        ORDER BY cuenta COLLATE "C", fecha, id
    """, ej=ejercicio)
    if not retrocesos:
        return 0
    recos = _filas(conn, """
        SELECT id, cuenta, fecha, neto::float8 AS neto
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND cuenta LIKE '440%'
          AND UPPER(concepto_norm) LIKE 'RETRO.RECO%'
        ORDER BY cuenta COLLATE "C", fecha, id
    """, ej=ejercicio)
    idx = defaultdict(list)
    for r in recos:
        idx[(r["cuenta"], r["fecha"])].append(r)

    pares, usados = [], set()
    for ret in retrocesos:
        cand = [c for c in idx.get((ret["cuenta"], ret["fecha"]), []) if c["id"] not in usados]
        if not cand:
            continue
        match = None
        for c in cand:
            if abs(ret["neto"] + c["neto"]) <= tol:
                match = [c["id"]]
                break
        if match is None and abs(ret["neto"] + sum(c["neto"] for c in cand)) <= tol:
            match = [c["id"] for c in cand]
        if match is None:
            continue
        gid = (f"RETRO|{ret['cuenta']}|{ret['fecha'].isoformat()}|"
               f"{abs(hash((ret['id'], tuple(sorted(match))))) % 100000}")
        pares.append((gid, ret["id"]))
        for m in match:
            pares.append((gid, m))
            usados.add(m)
    return marcar(conn, "RULE_RETRO", pares, run_id, filtro_cuentas=filtro_cuentas)


# ── RULE_RETROCESO — Retroceso 440* contra los cobros de los recibos 4152* del asiento ─

def regla_retroceso(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    """Igual que el original: se procesa retroceso a retroceso y cada grupo se puntea en
    el momento, de modo que los cobros ya usados no se ofrecen a los siguientes.
    El filtro de cuentas se aplica al retroceso: sus cobros son siempre de la misma cuenta."""
    fc, fc_params = filtro_cuentas_sql(filtro_cuentas)
    retrocesos = _filas(conn, """
        SELECT id, cuenta, neto::float8 AS neto, asiento_key
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND cuenta LIKE '440%'
          AND UPPER(concepto_norm) LIKE 'RETROCESO%' {fc}
        ORDER BY asiento_key COLLATE "C", id
    """.replace("{fc}", fc), ej=ejercicio, **fc_params)
    grupos = 0
    for ret in retrocesos:
        lineas_4152 = _filas(conn, """
            SELECT recibo_norm, neto::float8 AS neto
            FROM cc_apuntes
            WHERE asiento_key = :ak AND cuenta LIKE '4152%'
              AND recibo_norm <> '' AND recibo_norm IS NOT NULL
            ORDER BY id
        """, ak=ret["asiento_key"])
        if not lineas_4152:
            continue
        cobros, completo = [], True
        for l in lineas_4152:
            cobro = conn.execute(text("""
                SELECT id, neto::float8 AS neto
                FROM cc_apuntes
                WHERE cuenta = :cuenta AND recibo_norm = :recibo
                  AND (UPPER(concepto_norm) LIKE 'COBRO%'
                       OR UPPER(concepto_norm) LIKE 'MODIFICACION%'
                       OR UPPER(concepto_norm) LIKE 'DESCOBRO%'
                       OR UPPER(concepto_norm) LIKE 'RETRO.RECO%')
                  AND NOT reconciled
                  AND ABS(neto::float8 - :neto) <= :tol
                ORDER BY fecha ASC, id ASC
                LIMIT 1
            """), {"cuenta": ret["cuenta"], "recibo": l["recibo_norm"],
                   "neto": l["neto"], "tol": tol}).mappings().first()
            if not cobro:
                completo = False
                break
            cobros.append((cobro["id"], cobro["neto"]))
        if not completo or not cobros:
            continue
        if abs(ret["neto"] + sum(n for _, n in cobros)) > tol:
            continue
        all_ids = [ret["id"]] + [cid for cid, _ in cobros]
        gid = f"RETROCESO|{ret['asiento_key']}|{abs(hash(tuple(sorted(all_ids)))) % 100000}"
        conn.execute(text(f"""
            UPDATE cc_apuntes SET {SET_PUNTEO}, recon_group_id = :gid
            WHERE id = ANY(:ids)
        """), {"regla": "RULE_RETROCESO", "run_id": run_id, "gid": gid, "ids": all_ids})
        grupos += 1
    return grupos


# ── RULE_Q — Emisión + A real/De real, Emisión + Cobro, A real Recibo (todos los ejercicios) ─

def regla_q(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    pares = []

    # Pasada 1: A real + De real (emparejados 1:1 de menor a mayor importe)
    filas = _filas(conn, """
        SELECT id, cuenta, recibo_norm, neto::float8 AS neto, concepto_norm, concepto
        FROM cc_apuntes
        WHERE NOT reconciled AND recibo_norm <> '' AND recibo_norm IS NOT NULL
          AND cuenta NOT LIKE '440%'
          AND (concepto_norm ILIKE '%EMISION%' OR concepto_norm ILIKE '%A%REAL%'
               OR concepto_norm ILIKE '%DE%REAL%')
        ORDER BY cuenta COLLATE "C", recibo_norm COLLATE "C", id
    """)
    g1 = defaultdict(lambda: {"emision": [], "a_real": [], "de_real": []})
    for r in filas:
        cn = (r["concepto_norm"] or "").upper()
        c = (r["concepto"] or "").upper()
        cn_norm = cn.replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
        item = {"id": r["id"], "neto": r["neto"]}
        key = (r["cuenta"], r["recibo_norm"])
        if "EMISION" in cn_norm or "EMISION" in c:
            g1[key]["emision"].append(item)
        elif "A REAL" in c:
            g1[key]["a_real"].append(item)
        elif "DE REAL" in c:
            g1[key]["de_real"].append(item)
    for (cuenta, recibo), g in g1.items():
        a_real = sorted(g["a_real"], key=lambda x: abs(x["neto"]))
        de_real = sorted(g["de_real"], key=lambda x: abs(x["neto"]))
        if not a_real or not de_real:
            continue
        emparejados, resto = [], list(de_real)
        for cobro in a_real:
            best_i, best = -1, float("inf")
            for i, dev in enumerate(resto):
                diff = abs(cobro["neto"] + dev["neto"])
                if diff <= tol and diff < best:
                    best, best_i = diff, i
            if best_i >= 0:
                emparejados.append((cobro["id"], resto.pop(best_i)["id"]))
        if not emparejados:
            continue
        gid = f"RULE_Q|ALL_YEARS|{cuenta}|{recibo}|{len(emparejados)}pares"
        pares += [(gid, i) for par in emparejados for i in par]

    # Pasada 2: Emisión + Cobro/Modificación/A efectivo/Anulación/A real recibo
    reservados = {lid for _, lid in pares}
    filas = _filas(conn, """
        SELECT id, cuenta, recibo_norm, neto::float8 AS neto, concepto_norm
        FROM cc_apuntes
        WHERE NOT reconciled AND recibo_norm <> '' AND recibo_norm IS NOT NULL
          AND (UPPER(concepto_norm) LIKE 'EMISION%' OR UPPER(concepto_norm) LIKE 'COBRO%'
               OR UPPER(concepto_norm) LIKE 'MODIFICACI%' OR UPPER(concepto_norm) LIKE 'A EFECTIVO%'
               OR UPPER(concepto_norm) LIKE 'ANULACI%' OR UPPER(concepto_norm) LIKE 'A REAL RECIB%')
        ORDER BY cuenta COLLATE "C", recibo_norm COLLATE "C", id
    """)
    g2 = defaultdict(lambda: {"emision": [], "otros": []})
    for r in filas:
        if r["id"] in reservados:
            continue
        cn = (r["concepto_norm"] or "").upper()
        item = {"id": r["id"], "neto": r["neto"]}
        key = (r["cuenta"], r["recibo_norm"])
        if cn.startswith("EMISION"):
            g2[key]["emision"].append(item)
        elif cn.startswith(("COBRO", "MODIFICACI", "A EFECTIVO", "ANULACI", "A REAL RECIB")):
            g2[key]["otros"].append(item)
    for (cuenta, recibo), g in g2.items():
        if not g["emision"] or not g["otros"]:
            continue
        suma = round(sum(x["neto"] for x in g["emision"]) + sum(x["neto"] for x in g["otros"]), 2)
        if abs(suma) > tol:
            continue
        gid = f"RULE_Q2|{cuenta}|{recibo}"
        pares += [(gid, x["id"]) for x in g["emision"] + g["otros"]]

    # Pasada 3: A real Recibo — todo el grupo, o 1:1 positivos contra negativos
    reservados = {lid for _, lid in pares}
    filas = _filas(conn, """
        SELECT id, cuenta, recibo_norm, neto::float8 AS neto
        FROM cc_apuntes
        WHERE NOT reconciled AND recibo_norm <> '' AND recibo_norm IS NOT NULL
          AND UPPER(concepto_norm) LIKE 'A REAL RECIB%'
        ORDER BY cuenta COLLATE "C", recibo_norm COLLATE "C", id
    """)
    g3 = defaultdict(list)
    for r in filas:
        if r["id"] not in reservados:
            g3[(r["cuenta"], r["recibo_norm"])].append({"id": r["id"], "neto": r["neto"]})
    for (cuenta, recibo), items in g3.items():
        if len(items) < 2:
            continue
        if abs(round(sum(x["neto"] for x in items), 2)) <= tol:
            gid = f"RULE_Q3G|{cuenta}|{recibo}"
            pares += [(gid, x["id"]) for x in items]
            continue
        pos = sorted([x for x in items if x["neto"] >= 0], key=lambda x: abs(x["neto"]))
        neg = sorted([x for x in items if x["neto"] < 0], key=lambda x: abs(x["neto"]))
        for p in pos:
            best_i, best = -1, float("inf")
            for i, n in enumerate(neg):
                diff = abs(p["neto"] + n["neto"])
                if diff <= tol and diff < best:
                    best, best_i = diff, i
            if best_i >= 0:
                partner = neg.pop(best_i)
                gid = f"RULE_Q3P|{cuenta}|{recibo}|{p['id']}"
                pares += [(gid, p["id"]), (gid, partner["id"])]
    return marcar(conn, "RULE_Q", pares, run_id, solo_pendientes=True, filtro_cuentas=filtro_cuentas)


# ── RULE_V — cierre de saldo 440* por cuenta y ejercicio (siempre la última) ───

TOP_CANDIDATES = 25
MAX_K_SIGN = 6
MAX_ITER_C = 500


def _buscar_exclusion(items, suma, tolerance):
    """Copia literal del algoritmo del original (fases A, B y C)."""
    n = len(items)
    negs = [x for x in items if x["neto"] < 0]
    poss = [x for x in items if x["neto"] > 0]
    if not negs or not poss:
        return None, None

    def make_result(exc_ids):
        conc = [it["id"] for it in items if it["id"] not in exc_ids]
        return (exc_ids, conc) if len(conc) >= 2 else (None, None)

    # FASE A: top-25 del signo de la suma
    pool = negs if suma < 0 else poss
    pool_top = sorted(pool, key=lambda x: abs(x["neto"]), reverse=True)[:TOP_CANDIDATES]
    st = sorted(pool_top, key=lambda x: x["neto"])
    st_n = [x["neto"] for x in st]
    st_i = [x["id"] for x in st]

    def find_top(target, excl):
        lo = bisect.bisect_left(st_n, target - tolerance)
        hi = bisect.bisect_right(st_n, target + tolerance)
        for k in range(lo, hi):
            if st_i[k] not in excl:
                return {"id": st_i[k], "neto": st_n[k]}
        return None

    nt = len(pool_top)
    for x in pool_top:
        if abs(round(x["neto"] - suma, 2)) <= tolerance:
            e, c = make_result({x["id"]})
            if c:
                return e, c
    for k in range(2, MAX_K_SIGN + 1):
        if nt < k:
            break
        for combo in combinations(range(nt), k - 1):
            acc = round(sum(pool_top[i]["neto"] for i in combo), 6)
            excl = {pool_top[i]["id"] for i in combo}
            c = find_top(suma - acc, excl)
            if c and abs(round(acc + c["neto"] - suma, 2)) <= tolerance:
                excl.add(c["id"])
                e, conc = make_result(excl)
                if conc:
                    return e, conc

    # FASE B: todos los items, k=1..3
    sa = sorted(items, key=lambda x: x["neto"])
    sa_n = [x["neto"] for x in sa]
    sa_i = [x["id"] for x in sa]

    def find_all(target, excl):
        lo = bisect.bisect_left(sa_n, target - tolerance)
        hi = bisect.bisect_right(sa_n, target + tolerance)
        for k in range(lo, hi):
            if sa_i[k] not in excl:
                return sa_i[k], sa_n[k]
        return None, None

    if n - 1 >= 2:
        for x in items:
            if abs(round(suma - x["neto"], 2)) <= tolerance:
                e, c = make_result({x["id"]})
                if c:
                    return e, c
    if n - 2 >= 2:
        for xi in items:
            jid, jn = find_all(suma - xi["neto"], {xi["id"]})
            if jid and abs(round(suma - xi["neto"] - jn, 2)) <= tolerance:
                e, c = make_result({xi["id"], jid})
                if c:
                    return e, c
    if n - 3 >= 2:
        for i in range(n):
            for j in range(i + 1, n):
                t = suma - items[i]["neto"] - items[j]["neto"]
                kid, kn = find_all(t, {items[i]["id"], items[j]["id"]})
                if kid and abs(round(t - kn, 2)) <= tolerance:
                    e, c = make_result({items[i]["id"], items[j]["id"], kid})
                    if c:
                        return e, c

    # FASE C: exclusión iterativa + ajuste fino
    working = list(items)
    exc_ids = set()
    current = suma
    for _ in range(MAX_ITER_C):
        if abs(current) <= tolerance or len(working) < 3:
            break
        best, best_abs = None, abs(current)
        for x in working:
            cand = round(current - x["neto"], 2)
            if abs(cand) < best_abs:
                best_abs, best = abs(cand), x
        if best is None:
            break
        working.remove(best)
        exc_ids.add(best["id"])
        current = round(current - best["neto"], 2)

    if abs(current) > tolerance and len(working) >= 2:
        for x in list(working):
            nc = round(current - x["neto"], 2)
            if abs(nc) <= tolerance:
                exc_ids.add(x["id"])
                current = nc
                break

    if abs(current) > tolerance and len(working) >= 3:
        sw = sorted(working, key=lambda x: x["neto"])
        sw_n = [x["neto"] for x in sw]
        sw_i = [x["id"] for x in sw]
        for xi in working:
            if xi["id"] in exc_ids:
                continue
            lo = bisect.bisect_left(sw_n, current - xi["neto"] - tolerance)
            hi = bisect.bisect_right(sw_n, current - xi["neto"] + tolerance)
            for k in range(lo, hi):
                if sw_i[k] != xi["id"] and sw_i[k] not in exc_ids:
                    nc = round(current - xi["neto"] - sw_n[k], 2)
                    if abs(nc) <= tolerance:
                        exc_ids.add(xi["id"])
                        exc_ids.add(sw_i[k])
                        current = nc
                        break
            if abs(current) <= tolerance:
                break

    if abs(current) <= tolerance:
        e, c = make_result(exc_ids)
        if c:
            return e, c
    return None, None


def regla_v(conn, ejercicio, run_id, tol, filtro_cuentas=None, **_):
    lineas = _filas(conn, """
        SELECT id, cuenta, neto::float8 AS neto
        FROM cc_apuntes
        WHERE ejercicio = :ej AND NOT reconciled AND cuenta LIKE '440%'
        ORDER BY cuenta COLLATE "C", id
    """, ej=ejercicio)
    grupos = defaultdict(list)
    for l in lineas:
        grupos[l["cuenta"]].append({"id": l["id"], "neto": l["neto"]})

    pares = []
    for cuenta, items in grupos.items():
        n = len(items)
        suma = round(sum(x["neto"] for x in items), 2)
        if n < 2:
            continue
        if abs(suma) <= tol:
            gid = f"V|{ejercicio}|{cuenta}|ALL"
            pares += [(gid, x["id"]) for x in items]
            continue
        if not any(x["neto"] < 0 for x in items) or not any(x["neto"] > 0 for x in items):
            continue
        _excl, conciliar = _buscar_exclusion(items, suma, tol)
        if conciliar and len(conciliar) >= 2:
            gid = f"V|{ejercicio}|{cuenta}|PARTIAL"
            pares += [(gid, cid) for cid in conciliar]
    return marcar(conn, "RULE_V", pares, run_id, solo_pendientes=True, filtro_cuentas=filtro_cuentas)
