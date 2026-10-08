from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Distribución por campo 'mes'
    rows_mes = conn.execute(text("""
        SELECT mes, SUM(debe - haber) AS total
        FROM diario_apuntes
        WHERE ejercicio=2025
          AND numero_cuenta LIKE '6%'
          AND estado!='EXCLUIDO'
          AND mes IS NOT NULL
        GROUP BY mes ORDER BY mes
    """)).fetchall()

    sin_mes = conn.execute(text("""
        SELECT SUM(debe - haber)
        FROM diario_apuntes
        WHERE ejercicio=2025
          AND numero_cuenta LIKE '6%'
          AND estado!='EXCLUIDO'
          AND mes IS NULL
    """)).scalar()

    total_gas = conn.execute(text("""
        SELECT SUM(debe - haber)
        FROM diario_apuntes
        WHERE ejercicio=2025
          AND numero_cuenta LIKE '6%'
          AND estado!='EXCLUIDO'
    """)).scalar()

    print("=== GASTOS 2025 por campo 'mes' ===")
    for m, t in rows_mes:
        print(f"  Mes {m:2d}: {float(t):>12,.2f}")
    print(f"  Sin mes: {float(sin_mes or 0):>12,.2f}")
    print(f"  TOTAL:   {float(total_gas or 0):>12,.2f}")

    # Distribución por campo 'fecha'
    rows_fecha = conn.execute(text("""
        SELECT EXTRACT(MONTH FROM fecha)::int AS m, SUM(debe - haber) AS total
        FROM diario_apuntes
        WHERE ejercicio=2025
          AND numero_cuenta LIKE '6%'
          AND estado!='EXCLUIDO'
          AND fecha IS NOT NULL
        GROUP BY m ORDER BY m
    """)).fetchall()

    sin_fecha = conn.execute(text("""
        SELECT SUM(debe - haber)
        FROM diario_apuntes
        WHERE ejercicio=2025
          AND numero_cuenta LIKE '6%'
          AND estado!='EXCLUIDO'
          AND fecha IS NULL
    """)).scalar()

    print("\n=== GASTOS 2025 por campo 'fecha' ===")
    total_f = 0
    for m, t in rows_fecha:
        v = float(t or 0)
        total_f += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  Sin fecha: {float(sin_fecha or 0):>12,.2f}")
    print(f"  TOTAL con fecha: {total_f:>12,.2f}")

    # Por cuentas principales para ver si hay uniformidad
    print("\n=== Top cuentas de gastos y su distribución ===")
    cuentas = conn.execute(text("""
        SELECT numero_cuenta, SUM(debe-haber) AS total,
               COUNT(CASE WHEN mes IS NOT NULL THEN 1 END) AS con_mes,
               COUNT(*) AS total_registros
        FROM diario_apuntes
        WHERE ejercicio=2025 AND numero_cuenta LIKE '6%' AND estado!='EXCLUIDO'
        GROUP BY numero_cuenta
        ORDER BY total DESC LIMIT 10
    """)).fetchall()
    for nc, tot, con_m, tot_r in cuentas:
        print(f"  {nc:<10} total={float(tot or 0):>10,.0f}  con_mes={con_m:>4}/{tot_r}")
