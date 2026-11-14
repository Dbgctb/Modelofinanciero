"""Prueba de paridad de la conciliación bancaria: programa original (SQLite) contra el
nuevo (PostgreSQL). Fase 4 de docs/PLAN_CIERRES_CONTABILIDAD.md. Herramienta de un solo uso.

1. Copia el SQLite (el original no se toca).
2. En la copia y en PostgreSQL deshace lo conciliado por niveles (NIVEL_1..9 en el diario y
   niveles 1..9 en los extractos); se conservan las conciliaciones manuales. Antes guarda
   el estado de cc_apuntes y cc_extractos en tablas de respaldo.
3. Motor ORIGINAL sobre la copia y motor NUEVO sobre PostgreSQL, para cada banco y ejercicio
   con extractos, con la configuración guardada (días del nivel 2, tolerancias 8 y 9).
4. Compara movimiento a movimiento (conciliado, nivel, apunte, grupo) y apunte a apunte
   (punteado, regla, grupo).
5. Restaura PostgreSQL y comprueba que queda idéntico.

Uso (desde backend/): venv/Scripts/python.exe scripts/paridad_banco.py SQLITE CODIGO_ORIGINAL DIR_TRABAJO
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.services.cierres.banco.motor import conciliar  # noqa: E402

MOTOR_ORIGINAL = r'''
import sys, json, logging
codigo, db_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, codigo)
logging.basicConfig(level=logging.WARNING)
from app.models.database import Database
from app.services.bank_reconciliation import BankReconciliationEngine
db = Database(db_path)
c = db.get_connection()
pares = c.execute("SELECT DISTINCT e.banco_id, e.ejercicio, b.cuenta_572 FROM bank_statements e "
                  "JOIN bancos b ON b.id = e.banco_id ORDER BY 1, 2").fetchall()
for banco_id, ej, cuenta in pares:
    tol = dict(c.execute("SELECT key, value FROM config").fetchall())
    t8 = float(tol.get(f"nivel8_tolerance_{cuenta}", 0.01)); t9 = float(tol.get(f"nivel9_tolerance_{cuenta}", 0.01))
    BankReconciliationEngine(db).execute_reconciliation(ej, cuenta, banco_id, nivel8_tolerance=t8, nivel9_tolerance=t9)
    print(json.dumps({"banco": banco_id, "ejercicio": ej}), flush=True)
'''

NIVELES_SQL = "('1','2','3','7','8','9')"


def main():
    sqlite_orig, codigo, trabajo = sys.argv[1:4]
    os.makedirs(trabajo, exist_ok=True)
    copia = os.path.join(trabajo, "banco_paridad.db")
    shutil.copy2(sqlite_orig, copia)
    c = sqlite3.connect(copia)
    nb = c.execute(f"""UPDATE bank_statements SET reconciled = 0, recon_level = NULL, recon_group_id = NULL,
        recon_journal_id = NULL, recon_difference = NULL, recon_timestamp = NULL
        WHERE recon_level IN {NIVELES_SQL}""").rowcount
    nj = c.execute("""UPDATE journal_lines SET reconciled = 0, recon_rule = NULL, recon_group_id = NULL,
        recon_run_id = NULL, recon_timestamp = NULL WHERE recon_rule LIKE 'NIVEL%'""").rowcount
    c.commit()
    c.close()
    print(f"Copia SQLite: {nb} movimientos y {nj} apuntes desconciliados")

    with engine.begin() as conn:
        for t in ("cc_paridad_apuntes", "cc_paridad_extractos"):
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        conn.execute(text("""CREATE TABLE cc_paridad_apuntes AS SELECT id, reconciled, recon_rule, recon_group_id,
            recon_run_id, recon_timestamp FROM cc_apuntes WHERE recon_rule LIKE 'NIVEL%'"""))
        conn.execute(text("""CREATE TABLE cc_paridad_extractos AS SELECT id, reconciled, recon_level, recon_group_id,
            recon_journal_id, recon_difference, recon_timestamp FROM cc_extractos"""))
        max_run = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM cc_banco_ejecuciones")).scalar()
        nb = conn.execute(text(f"""UPDATE cc_extractos SET reconciled = false, recon_level = NULL, recon_group_id = NULL,
            recon_journal_id = NULL, recon_difference = NULL, recon_timestamp = NULL
            WHERE recon_level IN {NIVELES_SQL}""")).rowcount
        nj = conn.execute(text("""UPDATE cc_apuntes SET reconciled = false, recon_rule = NULL, recon_group_id = NULL,
            recon_run_id = NULL, recon_timestamp = NULL WHERE recon_rule LIKE 'NIVEL%'""")).rowcount
    print(f"PostgreSQL: {nb} movimientos y {nj} apuntes desconciliados (respaldo guardado)")

    script = os.path.join(trabajo, "motor_banco_original.py")
    open(script, "w", encoding="utf-8").write(MOTOR_ORIGINAL)
    p = subprocess.run([sys.executable, script, os.path.abspath(codigo), copia], capture_output=True, text=True,
                       encoding="utf-8", cwd=trabajo, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if p.returncode != 0:
        print(p.stderr[-3000:])
        sys.exit("El motor original falló")
    pares = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
    print("Motor original:", pares)

    for par in pares:
        r = conciliar(engine, par["ejercicio"], par["banco"])
        print(f"Motor nuevo banco {par['banco']} {par['ejercicio']}: {r['niveles']} "
              f"({r['conciliados_banco']}/{r['total_banco']} movimientos, {r['segundos']} s)")

    src = sqlite3.connect(copia)
    vb = {r[0]: (bool(r[1]), r[2], r[3], r[4]) for r in src.execute(
        "SELECT id, reconciled, recon_level, recon_journal_id, recon_group_id FROM bank_statements")}
    vj = {r[0]: (bool(r[1]), r[2], r[3]) for r in src.execute(
        "SELECT id, reconciled, recon_rule, recon_group_id FROM journal_lines WHERE CAST(cuenta AS TEXT) LIKE '572%'")}
    src.close()
    with engine.connect() as conn:
        nbm = {r[0]: (r[1], r[2], r[3], r[4]) for r in conn.execute(text(
            "SELECT id, reconciled, recon_level, recon_journal_id, recon_group_id FROM cc_extractos"))}
        njm = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(text(
            "SELECT id, reconciled, recon_rule, recon_group_id FROM cc_apuntes WHERE cuenta LIKE '572%'"))}
    db = [i for i in vb if vb[i] != nbm.get(i)]
    dj = [i for i in vj if vj[i] != njm.get(i)]
    print(f"\nMovimientos: {len(vb)} | conciliados original {sum(v[0] for v in vb.values())}, "
          f"nuevo {sum(v[0] for v in nbm.values())} | distintos: {len(db)}")
    print("  por nivel original:", sorted(Counter(v[1] for v in vb.values() if v[0]).items()))
    print("  por nivel nuevo:   ", sorted(Counter(v[1] for v in nbm.values() if v[0]).items()))
    for i in db[:10]:
        print("   ", i, "orig", vb[i], "nuevo", nbm.get(i))
    print(f"Apuntes 572: {len(vj)} | punteados original {sum(v[0] for v in vj.values())}, "
          f"nuevo {sum(v[0] for v in njm.values())} | distintos: {len(dj)}")
    for i in dj[:10]:
        print("   ", i, "orig", vj[i], "nuevo", njm.get(i))

    with engine.begin() as conn:
        conn.execute(text("""UPDATE cc_apuntes a SET reconciled = false, recon_rule = NULL, recon_group_id = NULL,
            recon_run_id = NULL, recon_timestamp = NULL WHERE a.recon_rule LIKE 'NIVEL%'"""))
        conn.execute(text("""UPDATE cc_apuntes a SET reconciled = b.reconciled, recon_rule = b.recon_rule,
            recon_group_id = b.recon_group_id, recon_run_id = b.recon_run_id, recon_timestamp = b.recon_timestamp
            FROM cc_paridad_apuntes b WHERE a.id = b.id"""))
        conn.execute(text("""UPDATE cc_extractos e SET reconciled = b.reconciled, recon_level = b.recon_level,
            recon_group_id = b.recon_group_id, recon_journal_id = b.recon_journal_id,
            recon_difference = b.recon_difference, recon_timestamp = b.recon_timestamp
            FROM cc_paridad_extractos b WHERE e.id = b.id"""))
        conn.execute(text("DELETE FROM cc_banco_ejecuciones WHERE id > :m"), {"m": max_run})
        dif = conn.execute(text("""SELECT
            (SELECT COUNT(*) FROM cc_extractos e JOIN cc_paridad_extractos b USING (id)
              WHERE (e.reconciled, e.recon_level, e.recon_group_id, e.recon_journal_id, e.recon_difference, e.recon_timestamp)
                    IS DISTINCT FROM (b.reconciled, b.recon_level, b.recon_group_id, b.recon_journal_id, b.recon_difference, b.recon_timestamp))
          + (SELECT COUNT(*) FROM cc_apuntes a JOIN cc_paridad_apuntes b USING (id)
              WHERE (a.reconciled, a.recon_rule, a.recon_group_id) IS DISTINCT FROM (b.reconciled, b.recon_rule, b.recon_group_id))
          + (SELECT COUNT(*) FROM cc_apuntes WHERE recon_rule LIKE 'NIVEL%') - (SELECT COUNT(*) FROM cc_paridad_apuntes)
        """)).scalar()
        if dif:
            raise RuntimeError(f"La restauración no cuadra ({dif}); respaldo conservado")
        conn.execute(text("DROP TABLE cc_paridad_apuntes"))
        conn.execute(text("DROP TABLE cc_paridad_extractos"))
    print("\nPostgreSQL restaurado e idéntico al estado migrado; respaldos eliminados.")


if __name__ == "__main__":
    main()
