from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT EXTRACT(MONTH FROM r.desde)::int AS m, SUM(d.haber - d.debe)
        FROM diario_apuntes d
        JOIN recibos r ON d.recibo_id = r.id
        WHERE d.ejercicio=2025
          AND d.tipo_cuenta='INGRESO'
          AND d.estado!='EXCLUIDO'
          AND r.desde IS NOT NULL
        GROUP BY m ORDER BY m
    """)).fetchall()

    print("=== Por 'desde' del recibo (con fecha) ===")
    total_con = 0
    for m, t in rows:
        v = float(t)
        total_con += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  SUBTOTAL con fecha: {total_con:>12,.2f}")

    sin = conn.execute(text("""
        SELECT SUM(d.haber - d.debe)
        FROM diario_apuntes d
        LEFT JOIN recibos r ON d.recibo_id = r.id
        WHERE d.ejercicio=2025
          AND d.tipo_cuenta='INGRESO'
          AND d.estado!='EXCLUIDO'
          AND (d.recibo_id IS NULL OR r.desde IS NULL)
    """)).scalar()
    print(f"  Sin fecha desde: {float(sin or 0):>12,.2f}")
    print(f"  TOTAL: {total_con + float(sin or 0):>12,.2f}")
