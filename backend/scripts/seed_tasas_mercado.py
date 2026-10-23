"""
Seed inicial de tasas de mercado ICEA.
Ejecutar una sola vez tras la migración f6a1b5e4d9c3:
    python scripts/seed_tasas_mercado.py

Los datos viven en app/data/tasas_mercado_icea.py (compartidos con el botón
"Poblar desde ICEA" de Administración → Tasas de mercado, que hace lo mismo
pero por año, desde la propia pantalla).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uuid
from app.core.database import SessionLocal
from app.data.tasas_mercado_icea import TASAS_ICEA as TASAS


def run():
    db = SessionLocal()
    try:
        from sqlalchemy import text
        # Comprobar si ya hay datos para evitar duplicados
        count = db.execute(text("SELECT COUNT(*) FROM tasas_mercado_ref")).scalar()
        if count > 0:
            print(f"La tabla ya tiene {count} registros. Saltando seed.")
            return

        for fuente, anyo, tipo, keyword, tasa, es_default, notas in TASAS:
            db.execute(text("""
                INSERT INTO tasas_mercado_ref
                    (id, fuente, anyo, tipo, ramo_keyword, tasa_pct, es_default, notas)
                VALUES
                    (:id, :fuente, :anyo, :tipo, :ramo_keyword, :tasa_pct, :es_default, :notas)
            """), {
                "id": str(uuid.uuid4()),
                "fuente": fuente,
                "anyo": anyo,
                "tipo": tipo,
                "ramo_keyword": keyword,
                "tasa_pct": tasa,
                "es_default": es_default,
                "notas": notas,
            })

        db.commit()
        print(f"Seed completado: {len(TASAS)} tasas insertadas.")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    run()
