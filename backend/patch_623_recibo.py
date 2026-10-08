"""
Vincula recibo_id, ramo y tipo_negocio a los apuntes 623* existentes
que tienen el código de recibo en el concepto pero recibo_id = NULL.
Ejecutar UNA vez tras el fix de carga_diario.py.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

with engine.begin() as conn:
    n_antes = conn.execute(text(
        "SELECT COUNT(*) FROM diario_apuntes WHERE numero_cuenta LIKE '623%' AND recibo_id IS NULL"
    )).scalar()
    print(f"Apuntes 623* sin recibo_id antes: {n_antes}")

    r = conn.execute(text("""
        UPDATE diario_apuntes d
        SET
            recibo_id    = r.id,
            codigo_recibo = r.codigo,
            ramo         = r.ramo,
            tipo_negocio = r.tipo_negocio
        FROM recibos r
        WHERE d.numero_cuenta LIKE '623%'
          AND d.recibo_id IS NULL
          AND r.codigo = substring(d.concepto FROM '([0-9]{6})[^0-9]*$')
          AND r.ejercicio = d.ejercicio
    """))
    print(f"Actualizados: {r.rowcount}")

    n_despues = conn.execute(text(
        "SELECT COUNT(*) FROM diario_apuntes WHERE numero_cuenta LIKE '623%' AND recibo_id IS NULL"
    )).scalar()
    print(f"Apuntes 623* sin recibo_id después: {n_despues}")
