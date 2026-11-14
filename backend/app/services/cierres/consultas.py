"""Consultas de las pantallas de punteo: apuntes, punteo manual, bloques conciliados.

Todo paginado en el servidor y con SQL parametrizado (el original concatenaba texto
del usuario en algunos filtros).
"""
import re
import threading
import time
from decimal import Decimal

from sqlalchemy import text
from ...core.errores import ErrorApp

COLUMNAS_APUNTE = """id, ejercicio, fecha, cuenta, descripcion_cuenta, concepto, recibo_norm,
                     asiento_key, debe, haber, neto, reconciled, recon_rule, recon_group_id,
                     es_nuevo, es_huerfano"""


def _cuenta_cond(cuenta: str, params: dict, alias: str = "") -> str | None:
    """Filtro de cuenta: con * es prefijo; sin *, exacta si son 10 cifras y prefijo si es
    más corta. (En el original, sin * era siempre exacta y "43" no encontraba nada,
    aunque la pantalla sugería "Ej: 43".)"""
    c = (cuenta or "").strip()
    if not c:
        return None
    base = c.replace("*", "")
    if not base.isdigit():
        raise ErrorApp("CC-MAN-001")
    if "*" in c or len(base) < 10:
        params["cuenta"] = base + "%"
        return f"{alias}cuenta LIKE :cuenta"
    params["cuenta"] = base
    return f"{alias}cuenta = :cuenta"


def _filas(rows):
    out = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = float(v)
        out.append(d)
    return out


# ── Importar diario: tabla de apuntes del ejercicio ──────────────────────────

def listar_apuntes(conn, ejercicio, cuenta=None, conciliado=None, page=1, page_size=1000):
    params = {"ej": ejercicio}
    conds = ["ejercicio = :ej"]
    c = _cuenta_cond(cuenta, params)
    if c:
        conds.append(c)
    if conciliado is not None:
        conds.append("reconciled = :rec")
        params["rec"] = conciliado
    where = " AND ".join(conds)
    total = conn.execute(text(f"SELECT COUNT(*) FROM cc_apuntes WHERE {where}"), params).scalar()
    rows = conn.execute(text(f"""
        SELECT {COLUMNAS_APUNTE} FROM cc_apuntes WHERE {where}
        ORDER BY fecha, id LIMIT :lim OFFSET :off
    """), {**params, "lim": page_size, "off": (page - 1) * page_size}).mappings().all()
    return {"total": total, "page": page, "page_size": page_size, "filas": _filas(rows)}


def diferencias_incremental(conn, ejercicio):
    """Nuevos y huérfanos de la última importación incremental del ejercicio."""
    res = {}
    for marca in ("es_nuevo", "es_huerfano"):
        rows = conn.execute(text(f"""
            SELECT {COLUMNAS_APUNTE} FROM cc_apuntes
            WHERE ejercicio = :ej AND {marca} ORDER BY fecha, cuenta, id
        """), {"ej": ejercicio}).mappings().all()
        res["nuevos" if marca == "es_nuevo" else "huerfanos"] = _filas(rows)
    return res


# ── Punteo manual ────────────────────────────────────────────────────────────

def _where_manual(f: dict):
    params, conds = {}, []
    ejs = [int(e) for e in (f.get("ejercicios") or [])]
    if ejs:
        conds.append("ejercicio = ANY(:ejs)")
        params["ejs"] = ejs
    if f.get("solo_pendientes", True):
        conds.append("NOT reconciled")
    c = _cuenta_cond(f.get("cuenta"), params)
    if c:
        conds.append(c)
    if f.get("recibo"):
        conds.append("recibo_norm = :recibo")
        params["recibo"] = f["recibo"].strip()
    if f.get("asiento"):
        conds.append("asiento_key ILIKE :asiento")
        params["asiento"] = "%" + _escapar_like(f["asiento"].strip()) + "%"
    if f.get("concepto"):
        patron = f["concepto"].strip()
        if "*" in patron:
            patron = "*".join(_escapar_like(p) for p in patron.split("*")).replace("*", "%")
        else:
            patron = "%" + _escapar_like(patron) + "%"
        conds.append("concepto ILIKE :concepto")
        params["concepto"] = patron
    return (" AND ".join(conds) or "TRUE"), params


def _escapar_like(s: str) -> str:
    return re.sub(r"([\\%_])", r"\\\1", s)


def buscar_manual(conn, filtros: dict, page=1, page_size=200):
    where, params = _where_manual(filtros)
    agg = conn.execute(text(f"SELECT COUNT(*) AS n, COALESCE(SUM(neto), 0) AS suma FROM cc_apuntes WHERE {where}"),
                       params).mappings().one()
    rows = conn.execute(text(f"""
        SELECT {COLUMNAS_APUNTE} FROM cc_apuntes WHERE {where}
        ORDER BY cuenta, recibo_norm, fecha, id LIMIT :lim OFFSET :off
    """), {**params, "lim": page_size, "off": (page - 1) * page_size}).mappings().all()
    return {"total": agg["n"], "suma_total": float(agg["suma"]), "page": page,
            "page_size": page_size, "filas": _filas(rows)}


MAX_SELECCION = 50_000


def ids_manual(conn, filtros: dict):
    """Todos los ids que cumplen los filtros (botón "Seleccionar todos")."""
    where, params = _where_manual(filtros)
    n = conn.execute(text(f"SELECT COUNT(*) FROM cc_apuntes WHERE {where}"), params).scalar()
    if n > MAX_SELECCION:
        raise ErrorApp("CC-MAN-002", n=f"{n:,}".replace(",", "."), maximo=f"{MAX_SELECCION:,}".replace(",", "."))
    ids = conn.execute(text(f"SELECT id FROM cc_apuntes WHERE {where} ORDER BY id"), params).scalars().all()
    return {"ids": ids}


def resumen_seleccion(conn, ids: list[int]):
    r = conn.execute(text("""
        SELECT COUNT(*) AS n, COALESCE(SUM(neto), 0) AS suma, array_agg(DISTINCT cuenta) AS cuentas,
               COUNT(*) FILTER (WHERE reconciled) AS punteados
        FROM cc_apuntes WHERE id = ANY(:ids)
    """), {"ids": ids}).mappings().one()
    return {"n": r["n"], "suma": float(r["suma"]), "cuentas": sorted(r["cuentas"] or []),
            "punteados": r["punteados"]}


def puntear_manual(conn, ids: list[int], tolerancia: float):
    """Puntea a mano: misma cuenta, suma dentro de la tolerancia, mínimo 2 apuntes.

    Mismas validaciones que el original. Grupo "MANUAL|<segundos>|<id menor>" (el
    original usaba solo los segundos y dos punteos en el mismo segundo se mezclaban).
    """
    ids = sorted(set(int(i) for i in ids))
    if len(ids) < 2:
        raise ErrorApp("CC-MAN-003")
    s = resumen_seleccion(conn, ids)
    if s["n"] != len(ids):
        raise ErrorApp("CC-MAN-004")
    if s["punteados"]:
        raise ErrorApp("CC-MAN-005", n=s["punteados"])
    if len(s["cuentas"]) > 1:
        raise ErrorApp("CC-MAN-006", cuentas=", ".join(s["cuentas"]))
    suma = Decimal(str(s["suma"]))
    if abs(suma) > Decimal(str(tolerancia)):
        raise ErrorApp("CC-MAN-007", suma=s["suma"], tolerancia=tolerancia)
    gid = f"MANUAL|{int(time.time())}|{ids[0]}"
    n = conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = true, recon_rule = 'MANUAL', recon_group_id = :gid,
               recon_run_id = NULL, recon_timestamp = LOCALTIMESTAMP
        WHERE id = ANY(:ids) AND NOT reconciled
    """), {"gid": gid, "ids": ids}).rowcount
    return {"punteados": n, "ya_punteados": len(ids) - n, "grupo": gid, "suma": s["suma"]}


def cambiar_cuenta_572(conn, apunte_id: int, cuenta: str):
    """Cambia la cuenta de un apunte 572* no punteado a otra 572* (como el original)."""
    cuenta = (cuenta or "").strip()
    if not (cuenta.isdigit() and cuenta.startswith("572")):
        raise ErrorApp("CC-MAN-008")
    actual = conn.execute(text("SELECT cuenta, reconciled FROM cc_apuntes WHERE id = :id"),
                          {"id": apunte_id}).mappings().first()
    if not actual:
        raise ErrorApp("CC-MAN-009")
    if actual["reconciled"] or not actual["cuenta"].startswith("572"):
        raise ErrorApp("CC-MAN-010")
    conn.execute(text("UPDATE cc_apuntes SET cuenta = :c WHERE id = :id AND NOT reconciled"),
                 {"c": cuenta, "id": apunte_id})
    return {"id": apunte_id, "cuenta_anterior": actual["cuenta"], "cuenta": cuenta}


def desconciliar_ejercicio(conn, ejercicio: int):
    """Quita TODO el punteo del ejercicio, manual incluido (como el original)."""
    n = conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = false, recon_rule = NULL, recon_group_id = NULL,
               recon_run_id = NULL, recon_timestamp = NULL
        WHERE ejercicio = :ej AND reconciled
    """), {"ej": ejercicio}).rowcount
    return {"desconciliados": n}


# ── Ver conciliados ──────────────────────────────────────────────────────────
# La lista de bloques agrega ~900.000 apuntes (2-4 s). Como el original (que la
# materializaba en una tabla temporal), se calcula una vez por filtro y se pagina
# sobre la copia en memoria. Se invalida con cualquier escritura del módulo
# (invalidar_cache) o con el botón "Recargar" de la pantalla.


_CACHE = {"clave": None, "bloques": None}
_CACHE_LOCK = threading.Lock()
_VERSION = [0]


def invalidar_cache():
    with _CACHE_LOCK:
        _VERSION[0] += 1
        _CACHE["clave"], _CACHE["bloques"] = None, None


def sql_bloques(ejercicio=None, regla=None):
    """Bloques (grupos punteados) que tienen algún apunte del ejercicio y de la regla.

    Suma TODOS los apuntes punteados del grupo, aunque sean de otros ejercicios
    (igual que el original).
    """
    where, having, params = "", "", {}
    if regla:
        where = "AND recon_rule = :regla"
        params["regla"] = regla
    if ejercicio:
        having = "HAVING bool_or(ejercicio = :ej)"
        params["ej"] = ejercicio
    return f"""
        SELECT recon_group_id, recon_rule, COUNT(*) AS num_lineas, SUM(neto) AS suma_neto,
               SUM(CASE WHEN cuenta LIKE '440%' THEN neto ELSE 0 END) AS suma_neto_440,
               MIN(ejercicio) AS min_ej, MAX(ejercicio) AS max_ej
        FROM cc_apuntes
        WHERE reconciled AND recon_group_id IS NOT NULL {where}
        GROUP BY recon_group_id, recon_rule
        {having}
        ORDER BY recon_group_id COLLATE "C" DESC
    """, params


def _estado_bloque(b):
    """Igual que el original: en RULE_H la alerta mira solo la suma de las 440*."""
    suma = b["suma_neto_440"] if b["recon_rule"] == "RULE_H" else b["suma_neto"]
    if abs(suma) > Decimal("0.05"):
        return suma, "Suma fuera de tolerancia"
    if b["num_lineas"] == 1:
        return suma, "Solo 1 línea"
    return suma, "OK"


def _bloques(conn, ejercicio, regla, refrescar):
    with _CACHE_LOCK:
        clave = (ejercicio, regla, _VERSION[0])
        if not refrescar and _CACHE["clave"] == clave:
            return _CACHE["bloques"]
    sql, params = sql_bloques(ejercicio, regla)
    bloques = []
    for b in conn.execute(text(sql), params).mappings():
        suma, est = _estado_bloque(b)
        bloques.append((b["recon_group_id"], b["recon_rule"], b["num_lineas"], float(suma),
                        b["min_ej"], b["max_ej"], est))
    with _CACHE_LOCK:
        if clave[2] == _VERSION[0]:
            _CACHE["clave"], _CACHE["bloques"] = clave, bloques
    return bloques


def listar_bloques(conn, ejercicio=None, regla=None, page=1, page_size=200, refrescar=False):
    todos = _bloques(conn, ejercicio, regla, refrescar)
    pagina = todos[(page - 1) * page_size: page * page_size]
    campos = ("grupo", "regla", "num_lineas", "suma", "min_ej", "max_ej", "estado")
    return {"total": len(todos), "page": page, "page_size": page_size,
            "bloques": [dict(zip(campos, b)) for b in pagina]}


def detalle_bloque(conn, grupo: str):
    rows = conn.execute(text(f"""
        SELECT {COLUMNAS_APUNTE} FROM cc_apuntes WHERE recon_group_id = :g
        ORDER BY ejercicio, fecha, id
    """), {"g": grupo}).mappings().all()
    filas = _filas(rows)
    return {"grupo": grupo, "filas": filas, "suma": round(sum(f["neto"] for f in filas), 2)}


def reglas_con_punteo(conn):
    return conn.execute(text("""
        SELECT DISTINCT recon_rule FROM cc_apuntes WHERE reconciled AND recon_rule IS NOT NULL
        ORDER BY 1
    """)).scalars().all()
