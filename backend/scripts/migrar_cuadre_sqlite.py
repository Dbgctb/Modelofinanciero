"""Migración de un solo uso: Cuadre Contable (SQLite) → tablas cc_* (PostgreSQL).

Fase 1 de docs/PLAN_CIERRES_CONTABILIDAD.md. Copia los datos TAL COMO ESTÁN,
con el estado de punteo y los punteos manuales, conservando los ids
originales de apuntes, extractos, incidencias y ejecuciones.

Seguridad:
- El SQLite se abre en modo solo lectura (URI mode=ro): no puede modificarse.
- Toda la carga va en una sola transacción: si algo falla no queda nada a medias.
- Si las tablas cc_* ya tienen datos, se niega a seguir salvo con --reemplazar
  (que las vacía dentro de la misma transacción).

Uso (desde backend/):
    venv/Scripts/python.exe scripts/migrar_cuadre_sqlite.py RUTA_SQLITE            # migra y verifica
    venv/Scripts/python.exe scripts/migrar_cuadre_sqlite.py RUTA_SQLITE --reemplazar
    venv/Scripts/python.exe scripts/migrar_cuadre_sqlite.py RUTA_SQLITE --solo-verificar

La verificación compara TODAS las filas de cada tabla, campo a campo, además de
recuentos y sumas por ejercicio, cuenta (3 dígitos) y regla.
"""
import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine  # noqa: E402

NULL = r"\N"

# Textos de reglas guardados con caracteres perdidos (codificación) en el original.
CORRECCIONES_TEXTO = [
    ("Fecha �1 d�a", "Fecha ±1 día"),
    ("n�mero", "número"),
    ("Emisi�n", "Emisión"),
    ("M�nimo", "Mínimo"),
    ("l�neas", "líneas"),
    ("Liquidaci�n", "Liquidación"),
]

TABLAS_CC = [
    "cc_apuntes", "cc_reglas", "cc_ejecuciones", "cc_incidencias", "cc_cuentas_control",
    "cc_config", "cc_emparejamientos_h", "cc_bancos", "cc_extractos",
    "cc_banco_ejecuciones", "cc_banco_config",
]


# ---------------------------------------------------------------------------
# Conversión de valores
# ---------------------------------------------------------------------------

def _texto(v):
    return None if v is None else str(v)


def _importe(v):
    """REAL de SQLite → texto con 2 decimales (verificado: ningún importe tiene más)."""
    if v is None:
        return None
    d = Decimal(repr(float(v))).quantize(Decimal("0.01"))
    if abs(Decimal(repr(float(v))) - d) > Decimal("0.000001"):
        raise ValueError(f"Importe con más de 2 decimales: {v!r}")
    return str(d)


def _bool(v):
    if v is None:
        return None
    if v not in (0, 1):
        raise ValueError(f"Booleano inesperado: {v!r}")
    return "t" if v == 1 else "f"


def _corregir(texto):
    if texto is None:
        return None
    for malo, bueno in CORRECCIONES_TEXTO:
        texto = texto.replace(malo, bueno)
    if "�" in texto:
        raise ValueError(f"Texto con caracteres perdidos sin corrección definida: {texto!r}")
    return texto


def _line_ids(v):
    if v is None:
        return None
    return "{" + ",".join(str(int(x)) for x in v.split(",")) + "}"


def _json(v):
    if v is None:
        return None
    json.loads(v)  # valida
    return v


# ---------------------------------------------------------------------------
# Definición de cada tabla: consulta origen, tabla destino, columnas y conversiones
# ---------------------------------------------------------------------------

I = lambda v: v  # noqa: E731  (enteros y fechas ISO pasan tal cual)

TABLAS = [
    {
        "destino": "cc_apuntes",
        "origen": """SELECT id, linea, serie, numero, ejercicio, fecha, debe, haber, cuenta,
                            descripcion_cuenta, concepto, neto, recibo_norm, concepto_norm,
                            asiento_key, reconciled, recon_rule, recon_group_id, recon_run_id,
                            recon_timestamp, es_nuevo, es_huerfano, created_at
                     FROM journal_lines ORDER BY id""",
        "columnas": [
            ("id", I), ("linea", I), ("serie", _texto), ("numero", I), ("ejercicio", I),
            ("fecha", I), ("debe", _importe), ("haber", _importe), ("cuenta", _texto),
            ("descripcion_cuenta", _texto), ("concepto", _texto), ("neto", _importe),
            ("recibo_norm", _texto), ("concepto_norm", _texto), ("asiento_key", _texto),
            ("reconciled", _bool), ("recon_rule", _texto), ("recon_group_id", _texto),
            ("recon_run_id", I), ("recon_timestamp", I), ("es_nuevo", _bool),
            ("es_huerfano", _bool), ("created_at", I),
        ],
    },
    {
        "destino": "cc_reglas",
        "origen": """SELECT rule_code, rule_name, description, enabled, active, priority,
                            tolerance_amount, tolerance_days, created_at, updated_at
                     FROM reconciliation_rules ORDER BY rule_code""",
        "columnas": [
            ("rule_code", _texto), ("rule_name", _corregir), ("description", _corregir),
            ("enabled", _bool), ("active", _bool), ("priority", I),
            ("tolerance_amount", _importe), ("tolerance_days", I),
            ("created_at", I), ("updated_at", I),
        ],
        "clave": ("rule_code",),
    },
    {
        "destino": "cc_ejecuciones",
        "origen": """SELECT id, ejercicio, start_time, end_time, total_lines,
                            total_lines_reconciled, rules_executed, status, created_at
                     FROM reconciliation_runs ORDER BY id""",
        "columnas": [
            ("id", I), ("ejercicio", I), ("start_time", I), ("end_time", I),
            ("total_lines", I), ("total_lines_reconciled", I), ("rules_executed", _json),
            ("status", _texto), ("created_at", I),
        ],
    },
    {
        "destino": "cc_incidencias",
        "origen": """SELECT id, control_type, ejercicio, cuenta, recibo_norm, mes, severity,
                            issue_description, run_id, line_ids, created_at
                     FROM control_issues ORDER BY id""",
        "columnas": [
            ("id", I), ("control_type", _texto), ("ejercicio", I), ("cuenta", _texto),
            ("recibo_norm", _texto), ("mes", I), ("severity", _texto),
            ("issue_description", _texto), ("run_id", I), ("line_ids", _line_ids),
            ("created_at", I),
        ],
    },
    {
        # Las 4 tablas control_accounts* → una sola con `tipo`. Ids nuevos: nada los referencia.
        "destino": "cc_cuentas_control",
        "origen": """SELECT 'C', name, cuenta, min_mov, max_mov, NULL, active, created_at FROM control_accounts
                     UNION ALL
                     SELECT 'D', name, cuenta, NULL, NULL, tolerance_pct, active, created_at FROM control_accounts_d
                     UNION ALL
                     SELECT 'K', name, cuenta, NULL, NULL, NULL, active, created_at FROM control_accounts_k
                     UNION ALL
                     SELECT 'L', name, cuenta, NULL, NULL, NULL, active, created_at FROM control_accounts_l
                     ORDER BY 1, 3""",
        "columnas": [
            ("tipo", _texto), ("name", _texto), ("cuenta", _texto), ("min_mov", I),
            ("max_mov", I), ("tolerance_pct", _importe), ("active", _bool), ("created_at", I),
        ],
        "clave": ("tipo", "cuenta"),
    },
    {
        "destino": "cc_config",
        "origen": "SELECT key, value, updated_at FROM config ORDER BY key",
        "columnas": [("key", _texto), ("value", _texto), ("updated_at", I)],
        "clave": ("key",),
    },
    {
        "destino": "cc_emparejamientos_h",
        "origen": """SELECT id, asiento_key, concepto_norm, cuenta_440, neto_recobros, recibo,
                            cobro_id, created_at
                     FROM h_manual_matches ORDER BY id""",
        "columnas": [
            ("id", I), ("asiento_key", _texto), ("concepto_norm", _texto),
            ("cuenta_440", _texto), ("neto_recobros", _importe), ("recibo", _texto),
            ("cobro_id", I), ("created_at", I),
        ],
    },
    {
        "destino": "cc_bancos",
        "origen": """SELECT id, nombre, codigo, cuenta_572, iban, entidad, activo, created_at
                     FROM bancos ORDER BY id""",
        "columnas": [
            ("id", I), ("nombre", _texto), ("codigo", _texto), ("cuenta_572", _texto),
            ("iban", _texto), ("entidad", _texto), ("activo", _bool), ("created_at", I),
        ],
    },
    {
        "destino": "cc_extractos",
        "origen": """SELECT id, banco_id, ejercicio, fecha, fecha_operacion, fecha_valor,
                            fecha_contable, concepto, concepto_banco, concepto_contable,
                            referencia, cuenta_banco, cuenta_contable, importe, cargo, abono,
                            neto, saldo, reconciled, recon_level, recon_group_id,
                            recon_journal_id, recon_difference, recon_timestamp, asiento_key,
                            created_at
                     FROM bank_statements ORDER BY id""",
        "columnas": [
            ("id", I), ("banco_id", I), ("ejercicio", I), ("fecha", I),
            ("fecha_operacion", I), ("fecha_valor", I), ("fecha_contable", I),
            ("concepto", _texto), ("concepto_banco", _texto), ("concepto_contable", _texto),
            ("referencia", _texto), ("cuenta_banco", _texto), ("cuenta_contable", _texto),
            ("importe", _importe), ("cargo", _importe), ("abono", _importe), ("neto", _importe),
            ("saldo", _importe), ("reconciled", _bool), ("recon_level", _texto),
            ("recon_group_id", _texto), ("recon_journal_id", I),
            ("recon_difference", _importe), ("recon_timestamp", I), ("asiento_key", _texto),
            ("created_at", I),
        ],
    },
    {
        "destino": "cc_banco_ejecuciones",
        "origen": """SELECT id, ejercicio, banco_id, cuenta_contable, cuenta_banco,
                            fecha_conciliacion, mes, status, pct, created_at
                     FROM bank_reconciliation_runs ORDER BY id""",
        "columnas": [
            ("id", I), ("ejercicio", I), ("banco_id", I), ("cuenta_contable", _texto),
            ("cuenta_banco", _texto), ("fecha_conciliacion", I), ("mes", I),
            ("status", _texto), ("pct", _importe), ("created_at", I),
        ],
    },
    {
        # Solo las filas por cuenta 572 (las columnas key/value/description no se usan).
        "destino": "cc_banco_config",
        "origen": """SELECT cuenta_572, level_2_days, level_2_amount, level_3_amount, updated_at
                     FROM reconciliation_config WHERE cuenta_572 IS NOT NULL ORDER BY cuenta_572""",
        "columnas": [
            ("cuenta_572", _texto), ("level_2_days", I), ("level_2_amount", _importe),
            ("level_3_amount", _importe), ("updated_at", I),
        ],
        "clave": ("cuenta_572",),
    },
]


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def _abrir_sqlite(ruta):
    if not os.path.isfile(ruta):
        sys.exit(f"No existe el SQLite: {ruta}")
    uri = "file:" + os.path.abspath(ruta).replace("\\", "/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _copiar_tabla(src, cur, t, lote=50_000):
    nombres = [c for c, _ in t["columnas"]]
    convs = [f for _, f in t["columnas"]]
    sql_copy = (f"COPY {t['destino']} ({', '.join(nombres)}) FROM STDIN "
                f"WITH (FORMAT csv, NULL '{NULL}')")
    filas = src.execute(t["origen"])
    total = 0
    while True:
        bloque = filas.fetchmany(lote)
        if not bloque:
            break
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for fila in bloque:
            w.writerow([NULL if (v := f(x)) is None else v for f, x in zip(convs, fila)])
        buf.seek(0)
        cur.copy_expert(sql_copy, buf)
        total += len(bloque)
    return total


def migrar(src, reemplazar):
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        con_datos = []
        for tabla in TABLAS_CC:
            cur.execute(f"SELECT EXISTS (SELECT 1 FROM {tabla})")
            if cur.fetchone()[0]:
                con_datos.append(tabla)
        if con_datos and not reemplazar:
            sys.exit("Las tablas cc_* ya tienen datos (" + ", ".join(con_datos) + "). "
                     "Usa --reemplazar para vaciarlas y volver a migrar.")
        if con_datos:
            cur.execute("TRUNCATE " + ", ".join(TABLAS_CC) + " RESTART IDENTITY")
            print("Tablas cc_* vaciadas (dentro de la transacción).")

        for t in TABLAS:
            t0 = time.perf_counter()
            n = _copiar_tabla(src, cur, t)
            print(f"  {t['destino']:<22} {n:>10,} filas  ({time.perf_counter() - t0:.1f} s)")

        # Las secuencias deben continuar tras el id máximo migrado.
        for tabla in TABLAS_CC:
            cur.execute("SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = %s AND column_name = 'id'", (tabla,))
            if not cur.fetchone():
                continue  # cc_reglas, cc_config y cc_banco_config tienen clave de texto
            cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (tabla,))
            seq = cur.fetchone()[0]
            if seq:
                cur.execute(f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {tabla}), 0) + 1, false)",
                            (seq,))
        raw.commit()
        print("Transacción confirmada.")
    except BaseException:
        raw.rollback()
        print("ERROR: transacción deshecha, las tablas cc_* quedan como estaban.")
        raise
    finally:
        raw.close()

    raw = engine.raw_connection()
    try:
        raw.set_isolation_level(0)  # ANALYZE fuera de transacción
        cur = raw.cursor()
        for tabla in TABLAS_CC:
            cur.execute(f"ANALYZE {tabla}")
        raw.set_isolation_level(1)  # devuelve la conexión al pool en modo transaccional
    finally:
        raw.close()


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------

def _norm(v):
    """Lleva un valor de cualquiera de las dos bases a una forma comparable."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (Decimal, float)):
        return Decimal(repr(float(v))).quantize(Decimal("0.01"))
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    if isinstance(v, (dict,)):
        return json.dumps(v, sort_keys=True)
    return v


def _norm_origen(nombre, conv, v):
    """Aplica la misma conversión que la carga y la deja comparable con PostgreSQL."""
    if v is None:
        return None
    if conv is _bool:
        return v == 1
    if conv is _importe:
        return Decimal(_importe(v))
    if conv is _line_ids:
        return v
    if conv is _json:
        return json.dumps(json.loads(v), sort_keys=True)
    if conv in (_texto, _corregir):
        return conv(v)
    return v


def verificar(src):
    raw = engine.raw_connection()
    raw.autocommit = False  # los cursores de servidor necesitan transacción
    errores = 0
    try:
        for t in TABLAS:
            nombres = [c for c, _ in t["columnas"]]
            convs = [f for _, f in t["columnas"]]
            clave = t.get("clave", ("id",))
            cur = raw.cursor(name=f"v_{t['destino']}")  # cursor de servidor: no carga 1M filas en memoria
            cur.itersize = 50_000
            cur.execute(f"SELECT {', '.join(nombres)} FROM {t['destino']} ORDER BY {', '.join(clave)}")
            origen = src.execute(t["origen"])
            n = dif = 0
            for fo, fd in zip_longest_strict(origen, cur):
                n += 1
                if fo is None or fd is None:
                    dif += 1
                    if dif <= 5:
                        print(f"    falta fila en {'origen' if fo is None else 'destino'}: {fd or fo}")
                    continue
                a = tuple(_norm_origen(c, f, x) for c, f, x in zip(nombres, convs, fo))
                b = tuple(json.dumps(x, sort_keys=True) if (f is _json and x is not None) else _norm(x)
                          for f, x in zip(convs, fd))
                if a != b:
                    dif += 1
                    if dif <= 5:
                        campos = [c for c, x, y in zip(nombres, a, b) if x != y]
                        print(f"    distinta {t['destino']} {dict(zip(nombres, b)).get(clave[0])}: {campos} "
                              f"origen={[x for c, x, y in zip(nombres, a, b) if x != y]} "
                              f"destino={[y for c, x, y in zip(nombres, a, b) if x != y]}")
            cur.close()
            estado = "OK" if dif == 0 else f"{dif:,} DIFERENCIAS"
            print(f"  {t['destino']:<22} {n:>10,} filas comparadas campo a campo: {estado}")
            errores += dif
    finally:
        raw.close()
    return errores


def zip_longest_strict(a, b):
    """Como zip_longest, pero sin cargar nada en memoria y marcando la que falte con None."""
    ia, ib = iter(a), iter(b)
    while True:
        x = next(ia, None)
        y = next(ib, None)
        if x is None and y is None:
            return
        yield x, y


def resumen(src):
    """Recuentos y sumas por ejercicio, cuenta (3 dígitos) y regla en las dos bases."""
    q_src = """SELECT ejercicio, substr(CAST(cuenta AS TEXT), 1, 3), COALESCE(recon_rule, '-'),
                      COUNT(*), SUM(reconciled), ROUND(SUM(debe), 2), ROUND(SUM(haber), 2), ROUND(SUM(neto), 2)
               FROM journal_lines GROUP BY 1, 2, 3"""
    q_pg = """SELECT ejercicio, substr(cuenta, 1, 3), COALESCE(recon_rule, '-'),
                     COUNT(*), COUNT(*) FILTER (WHERE reconciled), SUM(debe), SUM(haber), SUM(neto)
              FROM cc_apuntes GROUP BY 1, 2, 3"""
    a = {r[:3]: (r[3], r[4], *(Decimal(repr(float(x))).quantize(Decimal("0.01")) for x in r[5:]))
         for r in src.execute(q_src)}
    with engine.connect() as c:
        b = {tuple(r[:3]): (r[3], r[4], *r[5:]) for r in c.exec_driver_sql(q_pg)}
    distintos = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
    print(f"  Grupos ejercicio × cuenta(3) × regla: {len(a):,} en SQLite, {len(b):,} en PostgreSQL, "
          f"{len(distintos)} distintos")
    for k in sorted(distintos)[:10]:
        print(f"    {k}: SQLite={a.get(k)} PG={b.get(k)}")

    por_ej = defaultdict(lambda: [0, 0, Decimal(0), Decimal(0)])
    for (ej, _, _), (n, rec, debe, haber, _neto) in b.items():
        x = por_ej[ej]
        x[0] += n; x[1] += rec; x[2] += debe; x[3] += haber
    print(f"  {'Ejercicio':>9} {'Apuntes':>10} {'Punteados':>10} {'%':>6} {'Debe':>18} {'Haber':>18}")
    for ej in sorted(por_ej):
        n, rec, debe, haber = por_ej[ej]
        print(f"  {ej:>9} {n:>10,} {rec:>10,} {rec / n * 100:>5.1f}% {debe:>18,.2f} {haber:>18,.2f}")
    tot = [sum(x[i] for x in por_ej.values()) for i in range(4)]
    print(f"  {'Total':>9} {tot[0]:>10,} {tot[1]:>10,} {tot[1] / tot[0] * 100:>5.1f}% "
          f"{tot[2]:>18,.2f} {tot[3]:>18,.2f}")

    with engine.connect() as c:
        manuales = c.exec_driver_sql(
            "SELECT recon_rule, COUNT(*) FROM cc_apuntes "
            "WHERE recon_rule LIKE 'MANUAL%%' OR recon_rule LIKE 'NIVEL%%' GROUP BY 1 ORDER BY 1").all()
    print("  Punteos manuales y del banco: " + ", ".join(f"{r}={n:,}" for r, n in manuales))
    return len(distintos)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sqlite", help="Ruta a cuadre_contable.db (se abre en solo lectura)")
    ap.add_argument("--reemplazar", action="store_true", help="Vacía las tablas cc_* antes de migrar")
    ap.add_argument("--solo-verificar", action="store_true", help="No migra; solo compara")
    args = ap.parse_args()

    src = _abrir_sqlite(args.sqlite)
    t0 = time.perf_counter()
    if not args.solo_verificar:
        print("Migrando…")
        migrar(src, args.reemplazar)
    print("Verificando fila a fila…")
    errores = verificar(src)
    print("Recuentos y sumas…")
    errores += resumen(src)
    print(f"Tiempo total: {time.perf_counter() - t0:.0f} s")
    if errores:
        print(f"RESULTADO: {errores:,} DIFERENCIAS")
        sys.exit(1)
    print("RESULTADO: migración idéntica al origen")


if __name__ == "__main__":
    main()
