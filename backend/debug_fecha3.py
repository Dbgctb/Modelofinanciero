from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Enfoque híbrido: recibos.desde donde existe, si no diario.fecha
    rows = conn.execute(text("""
        SELECT
            COALESCE(
                EXTRACT(MONTH FROM r.desde)::int,
                EXTRACT(MONTH FROM d.fecha)::int
            ) AS m,
            SUM(d.haber - d.debe) AS total
        FROM diario_apuntes d
        LEFT JOIN recibos r ON d.recibo_id = r.id
        WHERE d.ejercicio=2025
          AND d.tipo_cuenta='INGRESO'
          AND d.estado!='EXCLUIDO'
          AND COALESCE(r.desde, d.fecha) IS NOT NULL
        GROUP BY m ORDER BY m
    """)).fetchall()

    print("=== HÍBRIDO: recibos.desde o diario.fecha ===")
    total_con = 0
    for m, t in rows:
        v = float(t)
        total_con += v
        print(f"  Mes {m:2d}: {v:>12,.2f}")
    print(f"  SUBTOTAL: {total_con:>12,.2f}")

    sin = conn.execute(text("""
        SELECT SUM(d.haber - d.debe)
        FROM diario_apuntes d
        LEFT JOIN recibos r ON d.recibo_id = r.id
        WHERE d.ejercicio=2025
          AND d.tipo_cuenta='INGRESO'
          AND d.estado!='EXCLUIDO'
          AND COALESCE(r.desde, d.fecha) IS NULL
    """)).scalar()
    print(f"  Sin ninguna fecha: {float(sin or 0):>12,.2f}")
    print(f"  TOTAL: {total_con + float(sin or 0):>12,.2f}")

    print("\n=== Comparación con Excel 2025 ===")
    excel = {1:36647,2:34958,3:43544,4:39325,5:38471,6:42889,7:41739,8:32990,9:27388,10:38317,11:38007,12:33721}
    por_mes = {int(m): float(t) for m, t in rows}
    for m in range(1, 13):
        db_v = por_mes.get(m, 0)
        ex_v = excel.get(m, 0)
        print(f"  Mes {m:2d}: DB={db_v:>10,.0f}  Excel={ex_v:>10,.0f}  diff={db_v-ex_v:>+8,.0f}")
