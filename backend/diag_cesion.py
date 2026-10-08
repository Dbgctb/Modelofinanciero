"""Script de diagnóstico — ejecutar desde el directorio backend."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

EJ = 2025

def q(conn, sql, **kw):
    return conn.execute(text(sql), kw).fetchall()

with engine.connect() as c:
    print("=" * 70)
    print(f"DIAGNÓSTICO CESIÓN — ejercicio {EJ}")
    print("=" * 70)

    # 1. Estado de 623 en diario_apuntes
    rows = q(c, """
        SELECT
            COUNT(*)                                                              AS total,
            SUM(CASE WHEN auxiliar IS NOT NULL AND auxiliar <> ''
                      THEN 1 ELSE 0 END)                                         AS con_aux,
            SUM(CASE WHEN auxiliar IS NULL OR auxiliar = ''
                      THEN 1 ELSE 0 END)                                         AS sin_aux,
            SUM(CASE WHEN tipo_cuenta::text = 'gasto'   THEN 1 ELSE 0 END)      AS tipo_gasto,
            SUM(CASE WHEN tipo_cuenta::text = 'ingreso' THEN 1 ELSE 0 END)      AS tipo_ingreso,
            SUM(CASE WHEN tipo_cuenta IS NULL           THEN 1 ELSE 0 END)      AS tipo_null,
            COALESCE(SUM(CAST(debe AS FLOAT) - CAST(haber AS FLOAT)), 0)        AS importe_total
        FROM diario_apuntes
        WHERE ejercicio = :ej
          AND numero_cuenta LIKE '623%'
          AND estado::text <> 'excluido'
    """, ej=EJ)
    r = rows[0]
    print("\n[1] diario_apuntes — cuentas 623*")
    print(f"    total           : {r[0]}")
    print(f"    con auxiliar    : {r[1]}")
    print(f"    sin auxiliar    : {r[2]}")
    print(f"    tipo_cuenta=gasto  : {r[3]}")
    print(f"    tipo_cuenta=ingreso: {r[4]}")
    print(f"    tipo_cuenta=NULL   : {r[5]}")
    print(f"    importe total (debe-haber): {round(float(r[6]), 2)}")

    # Muestra de 5 filas de 623
    print("\n    Muestra (5 primeras filas):")
    sample = q(c, """
        SELECT numero_cuenta, auxiliar, tipo_cuenta::text,
               CAST(debe AS FLOAT) - CAST(haber AS FLOAT) AS imp
        FROM diario_apuntes
        WHERE ejercicio = :ej AND numero_cuenta LIKE '623%' AND estado::text <> 'excluido'
        LIMIT 5
    """, ej=EJ)
    for s in sample:
        print(f"      cuenta={s[0]}  aux={repr(s[1])}  tipo={s[2]}  imp={round(float(s[3]),2)}")

    # 2. fact_resultado_analitico — cesión
    rows2 = q(c, """
        SELECT
            COUNT(*)                                 AS total_rows,
            COUNT(DISTINCT auxiliar)                 AS aux_distintos,
            COALESCE(SUM(CAST(importe AS FLOAT)), 0) AS importe_total
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND naturaleza = 'Cesión auxiliar'
    """, ej=EJ)
    r2 = rows2[0]
    print("\n[2] fact_resultado_analitico — naturaleza='Cesión auxiliar'")
    print(f"    filas         : {r2[0]}")
    print(f"    aux distintos : {r2[1]}")
    print(f"    importe total : {round(float(r2[2]), 2)}")

    if r2[0] == 0:
        print("    *** CERO FILAS — el recálculo no está creando cesión ***")

    # Muestra de cesión en el modelo
    sample2 = q(c, """
        SELECT auxiliar, tipo_cuenta, naturaleza,
               COALESCE(SUM(CAST(importe AS FLOAT)), 0) AS imp
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND naturaleza = 'Cesión auxiliar'
        GROUP BY auxiliar, tipo_cuenta, naturaleza ORDER BY 4 LIMIT 5
    """, ej=EJ)
    if sample2:
        print("    Muestra (top 5):")
        for s in sample2:
            print(f"      aux={repr(s[0])}  tipo={s[1]}  imp={round(float(s[3]),2)}")

    # 3. analitico_map_cuentas — entradas 623
    rows3 = q(c, """
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN descripcion NOT IN ('Auxiliares','Cesión auxiliar','Cesion auxiliar')
                            AND descripcion IS NOT NULL AND descripcion <> ''
                       THEN 1 END) AS con_nombre_auxiliar
        FROM analitico_map_cuentas
        WHERE numero_cuenta LIKE '623%' AND LENGTH(numero_cuenta) > 3
    """)
    r3 = rows3[0]
    print("\n[3] analitico_map_cuentas — entradas 623* (len>3)")
    print(f"    total en mapa              : {r3[0]}")
    print(f"    con nombre de auxiliar     : {r3[1]}")

    # Muestra de 5 entradas del mapa 623
    sample3 = q(c, """
        SELECT numero_cuenta, naturaleza, descripcion
        FROM analitico_map_cuentas
        WHERE numero_cuenta LIKE '623%' AND LENGTH(numero_cuenta) > 3
        LIMIT 5
    """)
    print("    Muestra (5 primeras):")
    for s in sample3:
        print(f"      cuenta={s[0]}  nat={s[1]}  desc={repr(s[2])}")

    # 4. Todas las naturalezas en fact_resultado_analitico
    print("\n[4] fact_resultado_analitico — distribución por naturaleza")
    rows4 = q(c, """
        SELECT naturaleza, tipo_cuenta,
               COUNT(*) AS n,
               COALESCE(SUM(CAST(importe AS FLOAT)), 0) AS imp
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej
        GROUP BY naturaleza, tipo_cuenta ORDER BY 3 DESC LIMIT 20
    """, ej=EJ)
    for s in rows4:
        print(f"      nat={repr(s[0])}  tipo={s[1]}  n={s[2]}  imp={round(float(s[3]),2)}")

    print("\n" + "=" * 70)
