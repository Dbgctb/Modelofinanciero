"""Prueba de paridad del motor de punteo: programa original (SQLite) contra el nuevo (PostgreSQL).

Fase 2 de docs/PLAN_CIERRES_CONTABILIDAD.md. Herramienta de verificación de un solo uso.

Pasos:
1. Copia el SQLite original a un directorio de trabajo (el original NO se toca).
2. En la copia y en cc_apuntes deja sin puntear todo salvo los punteos manuales y del
   banco (MANUAL_*, NIVEL_*), para que los dos motores partan del mismo estado.
   Antes guarda el punteo de cc_apuntes en la tabla cc_paridad_respaldo.
3. Ejecuta el motor ORIGINAL sobre la copia (en otro proceso, con su propio código),
   todos los ejercicios en orden, como la opción "Todos" de la pantalla Conciliar.
4. Ejecuta el motor NUEVO sobre cc_apuntes, igual.
5. Compara apunte a apunte: reconciled, recon_rule y recon_group_id.
6. Restaura cc_apuntes desde el respaldo y comprueba que queda idéntico (salvo --conservar).

Uso (desde backend/):
    venv/Scripts/python.exe scripts/paridad_punteo.py SQLITE_ORIGINAL CARPETA_CODIGO_ORIGINAL DIR_TRABAJO
"""
import argparse
import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.services.cierres.motor import ejecutar_punteo  # noqa: E402
from app.services.cierres.normalizador import extract_recibo, normalize_concepto  # noqa: E402

CONSERVAR = "(recon_rule LIKE 'MANUAL%' OR recon_rule LIKE 'NIVEL%')"

# Script que corre en un proceso aparte con el código ORIGINAL (su paquete `app`
# choca con el del Modelo financiero, por eso no se importa aquí).
MOTOR_ORIGINAL = r'''
import sys, json, time, logging
codigo, db_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, codigo)
logging.basicConfig(level=logging.WARNING)
from app.models.database import Database
from app.services.reconciliation_engine import ReconciliationEngine
db = Database(db_path)
ejs = [r[0] for r in db.get_connection().execute(
    "SELECT DISTINCT ejercicio FROM journal_lines WHERE ejercicio IS NOT NULL ORDER BY ejercicio")]
res = []
for i, ej in enumerate(ejs):
    t0 = time.perf_counter()
    por_regla = {}
    eng = ReconciliationEngine(db)
    eng.execute_reconciliation(ej, lambda r, n: por_regla.__setitem__(r, n),
                               account_filter=["*"], execute_cross_year=(i == len(ejs) - 1))
    res.append({"ejercicio": ej, "por_regla": por_regla, "segundos": round(time.perf_counter() - t0, 1)})
    print(json.dumps(res[-1]), flush=True)
db.close()
'''


def paso(msg):
    print(f"\n== {msg}", flush=True)


def verificar_normalizador(sqlite_path):
    """El normalizador nuevo da el mismo recibo_norm y concepto_norm que el guardado."""
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    n = dif_r = dif_c = 0
    ejemplos = []
    for _id, concepto, rn, cn in src.execute(
            "SELECT id, concepto, recibo_norm, concepto_norm FROM journal_lines"):
        n += 1
        r2, c2 = extract_recibo(concepto), normalize_concepto(concepto)
        if r2 != (rn or ""):
            dif_r += 1
            if len(ejemplos) < 5:
                ejemplos.append(("recibo", _id, concepto, rn, r2))
        if c2 != (cn or ""):
            dif_c += 1
            if len(ejemplos) < 5:
                ejemplos.append(("concepto", _id, concepto, cn, c2))
    src.close()
    print(f"  {n:,} conceptos: recibo_norm distintos={dif_r:,}, concepto_norm distintos={dif_c:,}")
    for e in ejemplos:
        print("   ", e)
    return dif_r + dif_c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite")
    ap.add_argument("codigo_original")
    ap.add_argument("dir_trabajo")
    ap.add_argument("--conservar", action="store_true",
                    help="No restaurar cc_apuntes al terminar (se queda el resultado del motor nuevo)")
    args = ap.parse_args()
    os.makedirs(args.dir_trabajo, exist_ok=True)
    copia = os.path.join(args.dir_trabajo, "cuadre_paridad.db")

    paso("Normalizador")
    verificar_normalizador(os.path.abspath(args.sqlite))

    paso("Copia del SQLite (el original no se modifica)")
    shutil.copy2(args.sqlite, copia)
    c = sqlite3.connect(copia)
    n = c.execute(f"""UPDATE journal_lines SET reconciled = 0, recon_rule = NULL, recon_group_id = NULL,
                      recon_run_id = NULL, recon_timestamp = NULL
                      WHERE recon_rule IS NULL OR NOT {CONSERVAR}""").rowcount
    c.commit()
    c.close()
    print(f"  copia: {n:,} apuntes despunteados")

    paso("Respaldo y despunteo de cc_apuntes")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS cc_paridad_respaldo"))
        conn.execute(text("""CREATE TABLE cc_paridad_respaldo AS
            SELECT id, reconciled, recon_rule, recon_group_id, recon_run_id, recon_timestamp FROM cc_apuntes"""))
        max_run = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM cc_ejecuciones")).scalar()
        n = conn.execute(text(f"""UPDATE cc_apuntes SET reconciled = false, recon_rule = NULL,
            recon_group_id = NULL, recon_run_id = NULL, recon_timestamp = NULL
            WHERE recon_rule IS NULL OR NOT {CONSERVAR}""")).rowcount
    print(f"  PostgreSQL: {n:,} apuntes despunteados (respaldo en cc_paridad_respaldo)")

    paso("Motor ORIGINAL sobre la copia")
    t0 = time.perf_counter()
    script = os.path.join(args.dir_trabajo, "motor_original.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(MOTOR_ORIGINAL)
    proc = subprocess.run([sys.executable, script, os.path.abspath(args.codigo_original), copia],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=args.dir_trabajo, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if proc.returncode != 0:
        print(proc.stderr[-3000:])
        sys.exit("El motor original falló")
    orig_res = [json.loads(l) for l in proc.stdout.splitlines() if l.startswith("{")]
    for r in orig_res:
        print(f"  {r['ejercicio']}: {sum(r['por_regla'].values()):>8,} apuntes  ({r['segundos']} s)")
    print(f"  total {time.perf_counter() - t0:.0f} s")

    paso("Motor NUEVO sobre PostgreSQL")
    t0 = time.perf_counter()
    with engine.connect() as conn:
        ejs = conn.execute(text("SELECT DISTINCT ejercicio FROM cc_apuntes ORDER BY 1")).scalars().all()
    nuevo_res = ejecutar_punteo(ejs, filtro_cuentas=["*"])
    for r in nuevo_res:
        print(f"  {r['ejercicio']}: {sum(r['por_regla'].values()):>8,} apuntes  ({r['segundos']} s)"
              + (f"  ERRORES: {r['errores']}" if r["errores"] else ""))
    print(f"  total {time.perf_counter() - t0:.0f} s")

    paso("Comparación apunte a apunte")
    src = sqlite3.connect(copia)
    viejo = {i: (bool(r), ru, g) for i, r, ru, g in src.execute(
        "SELECT id, reconciled, recon_rule, recon_group_id FROM journal_lines")}
    src.close()
    with engine.connect() as conn:
        nuevo = {i: (r, ru, g) for i, r, ru, g in conn.execute(text(
            "SELECT id, reconciled, recon_rule, recon_group_id FROM cc_apuntes"))}
    dif_estado, dif_regla, dif_grupo = [], [], []
    for i, (r1, ru1, g1) in viejo.items():
        r2, ru2, g2 = nuevo.get(i, (None, None, None))
        if r1 != r2:
            dif_estado.append(i)
        elif ru1 != ru2:
            dif_regla.append(i)
        elif g1 != g2:
            dif_grupo.append(i)
    punteados_v = sum(1 for v in viejo.values() if v[0])
    punteados_n = sum(1 for v in nuevo.values() if v[0])
    print(f"  Punteados: original {punteados_v:,} | nuevo {punteados_n:,}")
    print(f"  Distinto estado (punteado/no): {len(dif_estado):,}")
    print(f"  Mismo estado, distinta regla:   {len(dif_regla):,}")
    print(f"  Misma regla, distinto grupo:    {len(dif_grupo):,}")
    por_regla = Counter()
    for i in dif_estado + dif_regla + dif_grupo:
        por_regla[(viejo[i][1], nuevo[i][1])] += 1
    for (a, b), k in por_regla.most_common(20):
        print(f"    original={a!s:<16} nuevo={b!s:<16} {k:,}")
    salida = os.path.join(args.dir_trabajo, "paridad_diferencias.csv")
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "tipo", "reconciled_orig", "regla_orig", "grupo_orig",
                    "reconciled_nuevo", "regla_nueva", "grupo_nuevo"])
        for tipo, lista in (("estado", dif_estado), ("regla", dif_regla), ("grupo", dif_grupo)):
            for i in lista:
                w.writerow([i, tipo, *viejo[i], *nuevo[i]])
    print(f"  Detalle: {salida}")
    with open(os.path.join(args.dir_trabajo, "paridad_resumen.json"), "w", encoding="utf-8") as f:
        json.dump({"original": orig_res, "nuevo": nuevo_res}, f, indent=1, default=str)

    if args.conservar:
        print("\n--conservar: cc_apuntes se queda con el resultado del motor nuevo.")
        return
    paso("Restauración de cc_apuntes")
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE cc_apuntes a SET reconciled = b.reconciled, recon_rule = b.recon_rule,
                recon_group_id = b.recon_group_id, recon_run_id = b.recon_run_id,
                recon_timestamp = b.recon_timestamp
            FROM cc_paridad_respaldo b WHERE a.id = b.id"""))
        conn.execute(text("DELETE FROM cc_ejecuciones WHERE id > :m"), {"m": max_run})
        dif = conn.execute(text("""
            SELECT COUNT(*) FROM cc_apuntes a JOIN cc_paridad_respaldo b USING (id)
            WHERE a.reconciled IS DISTINCT FROM b.reconciled OR a.recon_rule IS DISTINCT FROM b.recon_rule
               OR a.recon_group_id IS DISTINCT FROM b.recon_group_id
               OR a.recon_run_id IS DISTINCT FROM b.recon_run_id
               OR a.recon_timestamp IS DISTINCT FROM b.recon_timestamp""")).scalar()
        if dif:
            raise RuntimeError(f"La restauración no cuadra: {dif} apuntes distintos (respaldo conservado)")
        conn.execute(text("DROP TABLE cc_paridad_respaldo"))
    print("  cc_apuntes restaurado e idéntico al estado migrado; respaldo eliminado.")


if __name__ == "__main__":
    main()
