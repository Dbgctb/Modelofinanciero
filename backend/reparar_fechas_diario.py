"""
Reparacion rapida de fecha/mes en diario_apuntes 2025.
Usa vectorizacion pandas + executemany en batches.
"""
import pandas as pd
import io
from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.normalizer import norm_col

EJERCICIO = 2025
EXCEL_PATH = "../carga de datos/diario 2025.xlsx"

def _to_int(v):
    try:
        s = str(v).strip()
        return int(float(s)) if s and s != 'nan' else None
    except Exception:
        return None

def main():
    print("Leyendo Excel...")
    with open(EXCEL_PATH, "rb") as f:
        contenido = f.read()

    df = pd.read_excel(io.BytesIO(contenido), dtype=str, keep_default_na=False)
    _RENAMES = {"ejercicio": "ejercicio_col", "numero_de_cuenta": "numero_cuenta"}
    df.columns = [_RENAMES.get(norm_col(c), norm_col(c)) for c in df.columns]
    print(f"Filas totales: {len(df)}")

    # Parsear fechas vectorizado (dayfirst=False - correcto para YYYY-MM-DD)
    print("Parseando fechas...")
    dt = pd.to_datetime(df["fecha"].astype(str), dayfirst=False, errors="coerce")
    # Extraer mes numericamente (NaT -> 0 -> convertir a None despues)
    df["mes_ok"]   = dt.dt.month.where(dt.notna(), other=None)
    df["fecha_ok"] = dt.dt.date.where(dt.notna(), other=None)
    df["linea_ok"] = pd.to_numeric(df["linea"], errors="coerce").astype("Int64")

    # Solo filas con linea valida
    validas = df[df["linea_ok"].notna()].copy()
    print(f"Filas con linea valida: {len(validas)}")
    print(f"Con fecha parseable: {validas['fecha_ok'].notna().sum()}")
    print(f"Sin fecha parseable: {validas['fecha_ok'].isna().sum()}")

    # Construir lista de dicts para executemany (solo campos necesarios)
    records = [
        {
            "linea": int(r["linea_ok"]),
            "mes":   int(r["mes_ok"]) if pd.notna(r["mes_ok"]) else None,
            "fecha": r["fecha_ok"],
        }
        for _, r in validas.iterrows()
    ]
    print(f"Preparados {len(records)} registros para update")

    db = SessionLocal()
    try:
        BATCH = 10000
        actualizadas = 0
        sql = text("UPDATE diario_apuntes SET fecha=:fecha, mes=:mes WHERE ejercicio=2025 AND linea=:linea")
        for i in range(0, len(records), BATCH):
            batch = records[i : i + BATCH]
            result = db.execute(sql, batch)
            actualizadas += result.rowcount
            db.commit()
            print(f"  Batch {i//BATCH + 1}/{(len(records)-1)//BATCH + 1}: {actualizadas} actualizadas")
    finally:
        db.close()

    print(f"\nTotal actualizadas: {actualizadas}")

    # Verificacion
    db2 = SessionLocal()
    try:
        from app.models.diario import DiarioApunte
        sin_mes = db2.query(DiarioApunte).filter(
            DiarioApunte.ejercicio == EJERCICIO,
            DiarioApunte.numero_cuenta.like("6%"),
            DiarioApunte.mes == None
        ).count()
        print(f"Apuntes 6* sin mes tras reparacion: {sin_mes}")

        dist = db2.execute(text(
            "SELECT mes, COUNT(*) as n, ROUND(SUM(debe-haber),2) as total "
            "FROM diario_apuntes "
            "WHERE ejercicio=2025 AND numero_cuenta LIKE '6%' "
            "GROUP BY mes ORDER BY mes"
        )).fetchall()
        print("\nDistribucion mensual 2025 (cuentas 6*):")
        for row in dist:
            print(f"  Mes {str(row[0]).rjust(2)}: {row[1]:5d} apuntes  {float(row[2] or 0):>14,.2f} EUR")
    finally:
        db2.close()

if __name__ == "__main__":
    main()
