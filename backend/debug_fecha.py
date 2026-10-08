from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT EXTRACT(MONTH FROM fecha)::int AS m, SUM(haber - debe) "
        "FROM diario_apuntes "
        "WHERE ejercicio=2025 AND tipo_cuenta=:tc AND estado!=:exc AND fecha IS NOT NULL "
        "GROUP BY m ORDER BY m"
    ), {"tc": "INGRESO", "exc": "EXCLUIDO"}).fetchall()

    print("=== Por FECHA (mes real del apunte) ===")
    total = 0
    for m, t in rows:
        v = float(t)
        total += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")

    sin_f = conn.execute(text(
        "SELECT SUM(haber - debe) FROM diario_apuntes "
        "WHERE ejercicio=2025 AND tipo_cuenta=:tc AND estado!=:exc AND fecha IS NULL"
    ), {"tc": "INGRESO", "exc": "EXCLUIDO"}).scalar()
    print(f"  Sin fecha: {float(sin_f or 0):>12,.2f}")
    print(f"  TOTAL: {total + float(sin_f or 0):>12,.2f}")
