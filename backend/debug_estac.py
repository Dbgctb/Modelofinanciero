from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    r1 = conn.execute(text(
        "SELECT mes, SUM(haber - debe) FROM diario_apuntes "
        "WHERE ejercicio=2025 AND tipo_cuenta=:tc AND estado=:est AND mes IS NOT NULL "
        "GROUP BY mes ORDER BY mes"
    ), {"tc": "INGRESO", "est": "CORRECTO"}).fetchall()
    print("=== tipo_cuenta=INGRESO, estado=CORRECTO ===")
    total1 = 0
    for m, t in r1:
        v = float(t)
        total1 += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  TOTAL con mes: {total1:>12,.2f}")

    r2 = conn.execute(text(
        "SELECT mes, SUM(haber - debe) FROM diario_apuntes "
        "WHERE ejercicio=2025 AND numero_cuenta LIKE :pat AND estado!=:exc AND mes IS NOT NULL "
        "GROUP BY mes ORDER BY mes"
    ), {"pat": "7%", "exc": "EXCLUIDO"}).fetchall()
    print("\n=== numero_cuenta 7%, estado!=EXCLUIDO ===")
    total2 = 0
    for m, t in r2:
        v = float(t)
        total2 += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  TOTAL con mes: {total2:>12,.2f}")

    s1 = conn.execute(text(
        "SELECT SUM(haber-debe) FROM diario_apuntes "
        "WHERE ejercicio=2025 AND tipo_cuenta=:tc AND estado=:est AND mes IS NULL"
    ), {"tc": "INGRESO", "est": "CORRECTO"}).scalar()
    s2 = conn.execute(text(
        "SELECT SUM(haber-debe) FROM diario_apuntes "
        "WHERE ejercicio=2025 AND numero_cuenta LIKE :pat AND estado!=:exc AND mes IS NULL"
    ), {"pat": "7%", "exc": "EXCLUIDO"}).scalar()
    print(f"\nSin mes (INGRESO/CORRECTO): {float(s1 or 0):>12,.2f}")
    print(f"Sin mes (7%/no-excluido):   {float(s2 or 0):>12,.2f}")

    # Distribuciones de estados para cuentas 7*
    rest = conn.execute(text(
        "SELECT estado, COUNT(*), SUM(haber-debe) FROM diario_apuntes "
        "WHERE ejercicio=2025 AND numero_cuenta LIKE :pat "
        "GROUP BY estado ORDER BY estado"
    ), {"pat": "7%"}).fetchall()
    print("\n=== Estados de cuentas 7* en 2025 ===")
    for est, cnt, tot in rest:
        print(f"  {str(est):<20} count={cnt:>5}  total={float(tot or 0):>12,.2f}")
