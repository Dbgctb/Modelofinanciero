from app.core.database import SessionLocal
from app.services.analitico import dashboard_auxiliar

db = SessionLocal()
try:
    r = dashboard_auxiliar(db, 2025)
    auxi = r['auxiliares']
    print(f'Total auxiliares: {len(auxi)}')
    for a in sorted(auxi, key=lambda x: -x['comision_bruta'])[:10]:
        name = (a['auxiliar'] or '(sin)') [:35]
        print(f'  {name:35s}  ingresos={a["comision_bruta"]:>10.0f}  cesion={a["comision_auxiliar"]:>10.0f}')
finally:
    db.close()
