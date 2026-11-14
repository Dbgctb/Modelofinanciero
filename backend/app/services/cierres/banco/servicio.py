"""Operaciones de la pantalla Conciliación bancaria: bancos, configuración, importar
extractos, pendientes, punteo manual (1:1 y N:N), conciliados y desconciliar.

Diferencias con el original (programa Cuadre Contable):
- Reimportar un Norma 43 ya no borra los movimientos conciliados (el original los
  borraba y dejaba los apuntes del diario punteados contra movimientos que ya no
  existían): se conservan, se sustituyen solo los pendientes y no se vuelven a
  insertar los del fichero que coinciden con uno conciliado.
- Desconciliar libera el grupo completo (en un N:N el original liberaba los
  apuntes pero dejaba conciliados los demás movimientos del grupo).
- "Auto-crear asiento" del original no creaba nada (solo mostraba la propuesta);
  aquí se presenta como lo que es: una propuesta de asientos.
"""
import io
import time
from collections import Counter
from decimal import Decimal

import pandas as pd
from sqlalchemy import text

from .norma43 import leer_norma43


def _f(v):
    return float(v) if isinstance(v, Decimal) else v


def _dicts(rows):
    return [{k: _f(v) for k, v in dict(r).items()} for r in rows]


# ── Bancos y configuración ───────────────────────────────────────────────────

def listar_bancos(conn, solo_activos=False):
    filtro = "WHERE activo" if solo_activos else ""
    return _dicts(conn.execute(text(f"""
        SELECT b.id, b.nombre, b.codigo, b.cuenta_572, b.iban, b.entidad, b.activo,
               (SELECT COUNT(*) FROM cc_extractos e WHERE e.banco_id = b.id) AS movimientos
        FROM cc_bancos b {filtro} ORDER BY b.nombre""")).mappings())


def guardar_banco(conn, datos: dict, id_=None):
    cuenta = str(datos.get("cuenta_572") or "").strip()
    if not (cuenta.isdigit() and cuenta.startswith("572")):
        raise ValueError("La cuenta contable debe ser numérica y empezar por 572")
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El banco necesita un nombre")
    v = {"nombre": nombre[:150], "cuenta_572": cuenta, "iban": (datos.get("iban") or "").replace(" ", "")[:34],
         "entidad": (datos.get("entidad") or "").strip()[:150], "activo": bool(datos.get("activo", True))}
    existe = conn.execute(text("SELECT id FROM cc_bancos WHERE lower(nombre) = lower(:n) AND id IS DISTINCT FROM :id"),
                          {"n": nombre, "id": id_}).first()
    if existe:
        raise ValueError("Ya existe un banco con ese nombre")
    if id_ is None:
        return conn.execute(text("""
            INSERT INTO cc_bancos (nombre, cuenta_572, iban, entidad, activo)
            VALUES (:nombre, :cuenta_572, :iban, :entidad, :activo) RETURNING id"""), v).scalar()
    if not conn.execute(text("""
        UPDATE cc_bancos SET nombre = :nombre, cuenta_572 = :cuenta_572, iban = :iban, entidad = :entidad,
               activo = :activo WHERE id = :id"""), v | {"id": id_}).rowcount:
        raise ValueError("El banco no existe")
    return id_


def borrar_banco(conn, id_):
    n = conn.execute(text("SELECT COUNT(*) FROM cc_extractos WHERE banco_id = :b"), {"b": id_}).scalar()
    if n:
        raise ValueError(f"El banco tiene {n} movimientos de extracto; desactívalo en lugar de borrarlo")
    conn.execute(text("DELETE FROM cc_bancos WHERE id = :b"), {"b": id_})


def _banco(conn, banco_id):
    b = conn.execute(text("SELECT * FROM cc_bancos WHERE id = :b"), {"b": banco_id}).mappings().first()
    if not b:
        raise ValueError("Banco no encontrado")
    return b


def leer_config(conn, banco_id):
    from .motor import configuracion
    return configuracion(conn, _banco(conn, banco_id)["cuenta_572"])


def guardar_config(conn, banco_id, dias_nivel2: int, tol_nivel8: float, tol_nivel9: float):
    if not (0 <= dias_nivel2 <= 30):
        raise ValueError("Los días del nivel 2 deben estar entre 0 y 30")
    for t in (tol_nivel8, tol_nivel9):
        if not (0 <= t <= 1000):
            raise ValueError("Las tolerancias deben estar entre 0 y 1.000 €")
    cuenta = _banco(conn, banco_id)["cuenta_572"]
    conn.execute(text("""
        INSERT INTO cc_banco_config (cuenta_572, level_2_days) VALUES (:c, :d)
        ON CONFLICT (cuenta_572) DO UPDATE SET level_2_days = EXCLUDED.level_2_days, updated_at = LOCALTIMESTAMP
    """), {"c": cuenta, "d": dias_nivel2})
    for nivel, tol in ((8, tol_nivel8), (9, tol_nivel9)):
        conn.execute(text("""
            INSERT INTO cc_config (key, value) VALUES (:k, :v)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = LOCALTIMESTAMP
        """), {"k": f"nivel{nivel}_tolerance_{cuenta}", "v": str(tol)})


# ── Importar extractos ───────────────────────────────────────────────────────

def _clave(fop, fval, importe, concepto):
    return (fop, fval, Decimal(str(importe)).quantize(Decimal("0.01")), (concepto or "")[:500])


def importar_norma43(conn, contenido: bytes, banco_id: int, ejercicio: int, indice_cuenta=None):
    banco = _banco(conn, banco_id)
    cuentas = leer_norma43(contenido)
    if len(cuentas) == 1:
        datos = cuentas[0]
    else:
        datos = None
        if indice_cuenta is not None:
            if not 0 <= indice_cuenta < len(cuentas):
                raise ValueError("Cuenta del fichero no válida")
            datos = cuentas[indice_cuenta]
        else:
            for c in cuentas:  # criterio del original
                if c["iban"] == banco["iban"] or c["cuenta"] in (banco["cuenta_572"] or ""):
                    datos = c
                    break
        if datos is None:
            return {"elegir_cuenta": [{"indice": i, "cuenta": c["cuenta"], "iban": c["iban"],
                                       "movimientos": len(c["movimientos"])} for i, c in enumerate(cuentas)]}
    if not datos["movimientos"]:
        raise ValueError("El fichero no tiene movimientos")

    conservados = Counter(_clave(r.fecha_operacion, r.fecha_valor, r.importe, r.concepto)
                          for r in conn.execute(text("""
        SELECT fecha_operacion, fecha_valor, importe, concepto FROM cc_extractos
        WHERE banco_id = :b AND ejercicio = :ej AND reconciled"""), {"b": banco_id, "ej": ejercicio}))
    borrados = conn.execute(text("DELETE FROM cc_extractos WHERE banco_id = :b AND ejercicio = :ej AND NOT reconciled"),
                            {"b": banco_id, "ej": ejercicio}).rowcount
    filas, omitidos = [], 0
    for m in datos["movimientos"]:
        k = _clave(m["fecha_operacion"], m["fecha_valor"], m["importe"], m["concepto"])
        if conservados[k] > 0:
            conservados[k] -= 1
            omitidos += 1
            continue
        filas.append({"ej": ejercicio, "cb": datos.get("iban") or banco["iban"], "cc": banco["cuenta_572"],
                      "fop": m["fecha_operacion"], "fval": m["fecha_valor"], "con": (m["concepto"] or "")[:500],
                      "ref": (m.get("referencia") or "")[:100], "imp": m["importe"], "saldo": m.get("saldo") or 0,
                      "b": banco_id})
    if filas:
        conn.execute(text("""
            INSERT INTO cc_extractos (ejercicio, cuenta_banco, cuenta_contable, fecha_operacion, fecha_valor,
                                      concepto, referencia, importe, saldo, reconciled, banco_id)
            VALUES (:ej, :cb, :cc, :fop, :fval, :con, :ref, :imp, :saldo, false, :b)"""), filas)
    return {"formato": "norma43", "cuenta": datos["cuenta"], "movimientos_fichero": len(datos["movimientos"]),
            "insertados": len(filas), "ya_conciliados": omitidos, "pendientes_sustituidos": borrados,
            "saldo_inicial": _f(datos["saldo_inicial"]), "saldo_final": _f(datos["saldo_final"])}


def _leer_tabla(nombre: str, contenido: bytes) -> pd.DataFrame:
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if ext in ("xlsx", "xls"):
        return pd.read_excel(io.BytesIO(contenido))
    for cod in ("utf-8", "latin-1"):  # mismo orden que el original
        for sep in (";", ",", "\t", "|"):
            try:
                df = pd.read_csv(io.BytesIO(contenido), sep=sep, encoding=cod)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue
    raise ValueError("No se pudo leer el fichero (separador o codificación no reconocidos)")


def columnas_tabla(nombre: str, contenido: bytes):
    df = _leer_tabla(nombre, contenido)
    return {"columnas": [str(c) for c in df.columns],
            "muestra": df.head(5).astype(str).to_dict("records")}


def importar_tabla(conn, nombre: str, contenido: bytes, banco_id: int, ejercicio: int, mapeo: dict):
    """Excel/CSV con mapeo de columnas. Como el original, AÑADE los movimientos."""
    banco = _banco(conn, banco_id)
    df = _leer_tabla(nombre, contenido)
    for req in ("fecha", "concepto", "importe"):
        if not mapeo.get(req) or mapeo[req] not in df.columns:
            raise ValueError(f"Falta la columna de {req} en el mapeo")
    out = pd.DataFrame()
    out["fop"] = pd.to_datetime(df[mapeo["fecha"]], dayfirst=True, errors="coerce")
    out["con"] = df[mapeo["concepto"]].astype(str)
    out["imp"] = pd.to_numeric(df[mapeo["importe"]], errors="coerce")
    out["saldo"] = pd.to_numeric(df[mapeo["saldo"]], errors="coerce") if mapeo.get("saldo") in df.columns else None
    out["ref"] = df[mapeo["referencia"]].astype(str) if mapeo.get("referencia") in df.columns else ""
    out["fval"] = (pd.to_datetime(df[mapeo["fecha_valor"]], dayfirst=True, errors="coerce")
                   if mapeo.get("fecha_valor") in df.columns else out["fop"])
    descartadas = int(out[["fop", "imp"]].isna().any(axis=1).sum())
    out = out.dropna(subset=["fop", "imp"])
    filas = [{"ej": ejercicio, "cb": banco["iban"], "cc": banco["cuenta_572"], "fop": r.fop.date(),
              "fval": r.fval.date() if pd.notna(r.fval) else None, "con": str(r.con)[:500],
              "ref": "" if pd.isna(r.ref) else str(r.ref)[:100], "imp": round(float(r.imp), 2),
              "saldo": None if r.saldo is None or pd.isna(r.saldo) else round(float(r.saldo), 2), "b": banco_id}
             for r in out.itertuples(index=False)]
    if filas:
        conn.execute(text("""
            INSERT INTO cc_extractos (ejercicio, cuenta_banco, cuenta_contable, fecha_operacion, fecha_valor,
                                      concepto, referencia, importe, saldo, reconciled, banco_id)
            VALUES (:ej, :cb, :cc, :fop, :fval, :con, :ref, :imp, :saldo, false, :b)"""), filas)
    return {"formato": "tabla", "insertados": len(filas), "filas_descartadas": descartadas}


def listar_extractos(conn, banco_id, ejercicio, page=1, page_size=200):
    total = conn.execute(text("SELECT COUNT(*) FROM cc_extractos WHERE banco_id = :b AND ejercicio = :ej"),
                         {"b": banco_id, "ej": ejercicio}).scalar()
    rows = conn.execute(text("""
        SELECT id, fecha_operacion, fecha_valor, concepto, referencia, importe, saldo, reconciled, recon_level
        FROM cc_extractos WHERE banco_id = :b AND ejercicio = :ej
        ORDER BY fecha_operacion DESC, id DESC LIMIT :lim OFFSET :off
    """), {"b": banco_id, "ej": ejercicio, "lim": page_size, "off": (page - 1) * page_size}).mappings()
    return {"total": total, "filas": _dicts(rows)}


# ── Pendientes y punteo manual ───────────────────────────────────────────────

def pendientes(conn, banco_id, ejercicio, limite=2000):
    cuenta = _banco(conn, banco_id)["cuenta_572"]
    p = {"b": banco_id, "ej": ejercicio, "c": cuenta, "lim": limite}
    banco = _dicts(conn.execute(text("""
        SELECT id, fecha_operacion, fecha_valor, concepto, referencia, importe FROM cc_extractos
        WHERE banco_id = :b AND ejercicio = :ej AND NOT reconciled
        ORDER BY fecha_operacion DESC, id DESC LIMIT :lim"""), p).mappings())
    diario = _dicts(conn.execute(text("""
        SELECT id, fecha, cuenta, asiento_key, concepto, neto FROM cc_apuntes
        WHERE ejercicio = :ej AND cuenta = :c AND NOT reconciled
        ORDER BY fecha DESC, id DESC LIMIT :lim"""), p).mappings())
    tb, td = conn.execute(text("""
        SELECT (SELECT COUNT(*) FROM cc_extractos WHERE banco_id = :b AND ejercicio = :ej AND NOT reconciled),
               (SELECT COUNT(*) FROM cc_apuntes WHERE ejercicio = :ej AND cuenta = :c AND NOT reconciled)
    """), p).one()
    return {"cuenta_572": cuenta, "banco": banco, "diario": diario, "total_banco": tb, "total_diario": td}


def _cargar_seleccion(conn, banco_id, ejercicio, ids_banco, ids_diario):
    cuenta = _banco(conn, banco_id)["cuenta_572"]
    b = conn.execute(text("""
        SELECT id, importe, fecha_operacion FROM cc_extractos
        WHERE id = ANY(:ids) AND banco_id = :b AND ejercicio = :ej AND NOT reconciled"""),
        {"ids": ids_banco, "b": banco_id, "ej": ejercicio}).mappings().all()
    d = conn.execute(text("""
        SELECT id, neto, fecha FROM cc_apuntes
        WHERE id = ANY(:ids) AND cuenta = :c AND ejercicio = :ej AND NOT reconciled"""),
        {"ids": ids_diario, "c": cuenta, "ej": ejercicio}).mappings().all()
    if len(b) != len(set(ids_banco)) or len(d) != len(set(ids_diario)):
        raise ValueError("Algún movimiento ya no está pendiente (o no es de este banco y ejercicio); actualiza la lista")
    return b, d


def conciliar_1a1(conn, banco_id, ejercicio, id_banco: int, id_diario: int):
    """1 movimiento contra 1 apunte (la pantalla avisa si importes o fechas difieren)."""
    b, d = _cargar_seleccion(conn, banco_id, ejercicio, [id_banco], [id_diario])
    dif = abs(b[0]["importe"] - d[0]["neto"])
    conn.execute(text("""
        UPDATE cc_extractos SET reconciled = true, recon_journal_id = :jid, recon_level = 'MANUAL',
               recon_difference = :dif, recon_timestamp = LOCALTIMESTAMP WHERE id = :bid"""),
                 {"jid": id_diario, "dif": dif if dif > Decimal("0.01") else None, "bid": id_banco})
    conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = true, recon_rule = 'MANUAL', recon_timestamp = LOCALTIMESTAMP
        WHERE id = :jid"""), {"jid": id_diario})
    return {"diferencia": float(dif)}


def conciliar_nn(conn, banco_id, ejercicio, ids_banco: list[int], ids_diario: list[int]):
    """N movimientos contra N apuntes (suma banco = suma diario; la pantalla avisa si no)."""
    if not ids_banco or not ids_diario:
        raise ValueError("Marca al menos un movimiento del banco y un apunte del diario")
    b, d = _cargar_seleccion(conn, banco_id, ejercicio, ids_banco, ids_diario)
    dif = abs(sum(x["importe"] for x in b) - sum(x["neto"] for x in d))
    gid = f"MANUAL_NN_{int(time.time())}_{min(ids_banco)}"
    conn.execute(text("""
        UPDATE cc_extractos SET reconciled = true, recon_level = 'MANUAL_NN', recon_group_id = :g,
               recon_difference = :dif, recon_timestamp = LOCALTIMESTAMP WHERE id = ANY(:ids)"""),
                 {"g": gid, "dif": dif, "ids": ids_banco})
    conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = true, recon_rule = 'MANUAL_NN', recon_group_id = :g,
               recon_timestamp = LOCALTIMESTAMP WHERE id = ANY(:ids)"""), {"g": gid, "ids": ids_diario})
    return {"grupo": gid, "diferencia": float(dif), "banco": len(b), "diario": len(d)}


def propuesta_asientos(conn, banco_id, ids_banco: list[int]):
    """Asiento propuesto para comisiones, intereses y otros gastos (no crea nada)."""
    cuenta = _banco(conn, banco_id)["cuenta_572"]
    res = []
    for m in conn.execute(text("""
        SELECT id, fecha_operacion, concepto, importe FROM cc_extractos
        WHERE id = ANY(:ids) AND banco_id = :b ORDER BY fecha_operacion, id"""),
            {"ids": ids_banco, "b": banco_id}).mappings():
        c, imp = (m["concepto"] or "").lower(), float(m["importe"])
        a = abs(imp)
        if "comision" in c or "comisión" in c:
            tipo, lineas = "Comisión", [("626", "Servicios bancarios", a, 0), (cuenta, "Bancos", 0, a)]
        elif "interes" in c or "interés" in c:
            tipo = "Interés"
            lineas = ([(cuenta, "Bancos", a, 0), ("769", "Otros ingresos financieros", 0, a)] if imp > 0
                      else [("662", "Intereses de deudas", a, 0), (cuenta, "Bancos", 0, a)])
        elif "mantenimiento" in c:
            tipo, lineas = "Mantenimiento", [("626", "Servicios bancarios", a, 0), (cuenta, "Bancos", 0, a)]
        else:
            tipo, lineas = "Otro gasto", [("627", "Gastos bancarios", a, 0), (cuenta, "Bancos", 0, a)]
        res.append({"id": m["id"], "fecha": m["fecha_operacion"], "concepto": m["concepto"], "importe": imp,
                    "tipo": tipo, "lineas": [{"cuenta": l[0], "nombre": l[1], "debe": l[2], "haber": l[3]}
                                             for l in lineas]})
    return res


# ── Conciliados y desconciliar ───────────────────────────────────────────────

def conciliados(conn, banco_id, ejercicio, nivel=None, page=1, page_size=200):
    p = {"b": banco_id, "ej": ejercicio, "lim": page_size, "off": (page - 1) * page_size}
    filtro = ""
    if nivel:
        filtro = "AND e.recon_level = :nivel"
        p["nivel"] = nivel
    total = conn.execute(text(f"""SELECT COUNT(*) FROM cc_extractos e
        WHERE e.banco_id = :b AND e.ejercicio = :ej AND e.reconciled {filtro}"""), p).scalar()
    por_nivel = {r.recon_level: r.n for r in conn.execute(text("""
        SELECT recon_level, COUNT(*) AS n FROM cc_extractos
        WHERE banco_id = :b AND ejercicio = :ej AND reconciled GROUP BY 1 ORDER BY 1"""), p)}
    rows = conn.execute(text(f"""
        SELECT e.id, e.fecha_operacion, e.concepto, e.importe, e.recon_level, e.recon_difference,
               e.recon_timestamp, e.recon_group_id, e.recon_journal_id,
               j.asiento_key, j.concepto AS concepto_diario, j.neto,
               (SELECT COUNT(*) FROM cc_apuntes g WHERE e.recon_group_id IS NOT NULL
                  AND g.recon_group_id = e.recon_group_id) AS apuntes_grupo
        FROM cc_extractos e LEFT JOIN cc_apuntes j ON j.id = e.recon_journal_id
        WHERE e.banco_id = :b AND e.ejercicio = :ej AND e.reconciled {filtro}
        ORDER BY e.fecha_operacion DESC, e.id DESC LIMIT :lim OFFSET :off"""), p).mappings()
    return {"total": total, "por_nivel": por_nivel, "filas": _dicts(rows)}


def desconciliar(conn, banco_id, ids_banco: list[int]):
    """Libera los movimientos, todos los de sus grupos y sus apuntes del diario."""
    grupos = conn.execute(text("""
        SELECT DISTINCT recon_group_id FROM cc_extractos
        WHERE id = ANY(:ids) AND banco_id = :b AND recon_group_id IS NOT NULL"""),
        {"ids": ids_banco, "b": banco_id}).scalars().all()
    ids = conn.execute(text("""
        SELECT id FROM cc_extractos WHERE banco_id = :b AND reconciled
          AND (id = ANY(:ids) OR recon_group_id = ANY(:g))"""),
        {"ids": ids_banco, "b": banco_id, "g": grupos}).scalars().all()
    jids = conn.execute(text("SELECT recon_journal_id FROM cc_extractos WHERE id = ANY(:ids) AND recon_journal_id IS NOT NULL"),
                        {"ids": ids}).scalars().all()
    n_diario = conn.execute(text("""
        UPDATE cc_apuntes SET reconciled = false, recon_rule = NULL, recon_group_id = NULL,
               recon_run_id = NULL, recon_timestamp = NULL
        WHERE reconciled AND (id = ANY(:jids) OR recon_group_id = ANY(:g))"""),
        {"jids": jids, "g": grupos}).rowcount
    n_banco = conn.execute(text("""
        UPDATE cc_extractos SET reconciled = false, recon_journal_id = NULL, recon_level = NULL,
               recon_group_id = NULL, recon_difference = NULL, recon_timestamp = NULL
        WHERE id = ANY(:ids)"""), {"ids": ids}).rowcount
    return {"movimientos": n_banco, "apuntes": n_diario}


def excel_conciliados(conn, banco_id, ejercicio, ruta):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Conciliados"
    cab = ["Fecha", "Concepto Banco", "Importe", "Asiento", "Concepto Diario", "Neto", "Nivel",
           "Diferencia", "Grupo", "Fecha conciliación"]
    ws.append(cab)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1565C0")
    for r in conn.execute(text("""
        SELECT e.fecha_operacion, e.concepto, e.importe, j.asiento_key, j.concepto AS cd, j.neto,
               e.recon_level, e.recon_difference, e.recon_group_id, e.recon_timestamp
        FROM cc_extractos e LEFT JOIN cc_apuntes j ON j.id = e.recon_journal_id
        WHERE e.banco_id = :b AND e.ejercicio = :ej AND e.reconciled
        ORDER BY e.fecha_operacion DESC, e.id DESC"""), {"b": banco_id, "ej": ejercicio}):
        ws.append([r.fecha_operacion, r.concepto, _f(r.importe), r.asiento_key, r.cd, _f(r.neto),
                   r.recon_level, _f(r.recon_difference), r.recon_group_id, r.recon_timestamp])
    for col, ancho in zip("ABCDEFGHIJ", (12, 50, 13, 16, 50, 13, 10, 11, 30, 19)):
        ws.column_dimensions[col].width = ancho
    ws.freeze_panes = "A2"
    wb.save(ruta)
