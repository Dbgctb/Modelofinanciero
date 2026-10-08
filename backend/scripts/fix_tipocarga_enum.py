import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TYPE tipocarga ADD VALUE IF NOT EXISTS 'HISTORICO_ESTADISTICO'"))
    conn.commit()

    result = conn.execute(text("SELECT unnest(enum_range(NULL::tipocarga))::text"))
    values = [r[0] for r in result]
    print("tipocarga enum values:", values)
    print("Fix applied successfully.")
