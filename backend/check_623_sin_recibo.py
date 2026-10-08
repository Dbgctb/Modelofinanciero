from app.core.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
rows = db.execute(text("""
    SELECT numero_cuenta, descripcion_cuenta, auxiliar, concepto
    FROM diario_apuntes
    WHERE numero_cuenta LIKE '623%' AND ejercicio = 2025
      AND recibo_id IS NULL AND estado::text != 'excluido'
    ORDER BY numero_cuenta
""")).fetchall()
for r in rows:
    concepto_corto = (r[3] or '')[:60]
    print(f"cuenta={r[0]}  desc={r[1]}  aux={r[2]}  concepto={concepto_corto}")
db.close()
