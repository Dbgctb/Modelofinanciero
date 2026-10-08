"""
Ejecuta la migración 001 — índices de rendimiento.
CREATE INDEX CONCURRENTLY no puede correr dentro de una transacción,
por eso se ejecuta sentencia a sentencia con autocommit.
"""
import os
import psycopg2
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ["DATABASE_URL"]

INDICES = [
    ("ix_diario_ejercicio",         "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio ON diario_apuntes (ejercicio)"),
    ("ix_diario_tipo_cuenta",       "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_tipo_cuenta ON diario_apuntes (tipo_cuenta)"),
    ("ix_diario_ejercicio_estado",  "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio_estado ON diario_apuntes (ejercicio, estado)"),
    ("ix_diario_ejercicio_recibo",  "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio_recibo ON diario_apuntes (ejercicio, recibo_id)"),
    ("ix_diario_ejercicio_num_cuenta","CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio_num_cuenta ON diario_apuntes (ejercicio, numero_cuenta)"),
    ("ix_recibos_ejercicio",        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recibos_ejercicio ON recibos (ejercicio)"),
    ("ix_recibos_tomador",          "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recibos_tomador ON recibos (tomador)"),
    ("ix_recibos_ente",             "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recibos_ente ON recibos (ente)"),
    ("ix_fact_tipo_cuenta",         "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_tipo_cuenta ON fact_resultado_analitico (tipo_cuenta)"),
    ("ix_fact_naturaleza",          "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_naturaleza ON fact_resultado_analitico (naturaleza)"),
    ("ix_fact_recibo_id",           "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_recibo_id ON fact_resultado_analitico (recibo_id)"),
    ("ix_fact_ejercicio_tipo_nat",  "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_ejercicio_tipo_nat ON fact_resultado_analitico (ejercicio, tipo_cuenta, naturaleza)"),
    ("ix_fact_ejercicio_recibo",    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_ejercicio_recibo ON fact_resultado_analitico (ejercicio, recibo_id)"),
]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True   # obligatorio para CONCURRENTLY
    cur = conn.cursor()

    ok = 0
    errors = []
    for name, sql in INDICES:
        t0 = time.perf_counter()
        try:
            cur.execute(sql)
            ms = (time.perf_counter() - t0) * 1000
            print(f"  OK  {name:45s}  ({ms:.0f} ms)")
            ok += 1
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            print(f"  ERR {name:45s}  {e}")
            errors.append((name, str(e)))

    cur.close()
    conn.close()

    print(f"\n{'='*60}")
    print(f"Resultado: {ok}/{len(INDICES)} índices creados correctamente")
    if errors:
        print("Errores:")
        for name, msg in errors:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print("Migración completada sin errores.")

if __name__ == "__main__":
    main()
