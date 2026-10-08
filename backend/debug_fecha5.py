from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Por mes de la carga mensual real
    rows = conn.execute(text("""
        SELECT c.mes, SUM(d.haber - d.debe) AS total
        FROM diario_apuntes d
        JOIN cargas_contables c ON d.carga_id = c.id
        WHERE d.ejercicio=2025
          AND d.tipo_cuenta='INGRESO'
          AND d.estado!='EXCLUIDO'
          AND c.tipo_carga='MENSUAL_REAL'
          AND c.mes IS NOT NULL
        GROUP BY c.mes ORDER BY c.mes
    """)).fetchall()

    print("=== Por mes de CARGA MENSUAL REAL ===")
    total = 0
    for m, t in rows:
        v = float(t or 0)
        total += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  SUBTOTAL: {total:>12,.2f}")

    # Ver cuántos tipos de carga hay
    tipos = conn.execute(text("""
        SELECT c.tipo_carga, c.mes, COUNT(d.id), SUM(d.haber-d.debe)
        FROM diario_apuntes d
        JOIN cargas_contables c ON d.carga_id = c.id
        WHERE d.ejercicio=2025 AND d.tipo_cuenta='INGRESO' AND d.estado!='EXCLUIDO'
        GROUP BY c.tipo_carga, c.mes
        ORDER BY c.tipo_carga, c.mes
    """)).fetchall()

    print("\n=== Desglose por tipo_carga y mes ===")
    for tc, m, cnt, tot in tipos:
        print(f"  {str(tc):<25} mes={str(m):<4} count={cnt:>5}  total={float(tot or 0):>12,.2f}")
