"""Limpia el valor 'None' (string) en diario_apuntes.auxiliar — ejecutar UNA vez."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

with engine.begin() as conn:
    # Cuántos hay
    n_antes = conn.execute(text(
        "SELECT COUNT(*) FROM diario_apuntes WHERE auxiliar IN ('None','nan','NaN','none')"
    )).scalar()
    print(f"Filas con auxiliar='None'/nan antes: {n_antes}")

    if n_antes > 0:
        r = conn.execute(text(
            "UPDATE diario_apuntes SET auxiliar = NULL "
            "WHERE auxiliar IN ('None','nan','NaN','none')"
        ))
        print(f"Actualizadas: {r.rowcount}")
    else:
        print("Nada que limpiar.")

    n_despues = conn.execute(text(
        "SELECT COUNT(*) FROM diario_apuntes WHERE auxiliar IN ('None','nan','NaN','none')"
    )).scalar()
    print(f"Filas con auxiliar='None'/nan después: {n_despues}")
