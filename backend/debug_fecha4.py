from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Tabla recibos directa, mes por 'desde'
    rows = conn.execute(text("""
        SELECT EXTRACT(MONTH FROM desde)::int AS m, SUM(liqui) AS total
        FROM recibos
        WHERE ejercicio=2025 AND desde IS NOT NULL
        GROUP BY m ORDER BY m
    """)).fetchall()

    print("=== recibos.liqui por mes de 'desde' ===")
    total = 0
    for m, t in rows:
        v = float(t or 0)
        total += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")

    sin = conn.execute(text(
        "SELECT SUM(liqui) FROM recibos WHERE ejercicio=2025 AND desde IS NULL"
    )).scalar()
    print(f"  Sin fecha: {float(sin or 0):>12,.2f}")
    print(f"  TOTAL: {total + float(sin or 0):>12,.2f}")

    # Mismo por 'hasta'
    rows2 = conn.execute(text("""
        SELECT EXTRACT(MONTH FROM hasta)::int AS m, SUM(liqui) AS total
        FROM recibos
        WHERE ejercicio=2025 AND hasta IS NOT NULL
        GROUP BY m ORDER BY m
    """)).fetchall()

    print("\n=== recibos.liqui por mes de 'hasta' ===")
    total2 = 0
    for m, t in rows2:
        v = float(t or 0)
        total2 += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  TOTAL: {total2:>12,.2f}")
