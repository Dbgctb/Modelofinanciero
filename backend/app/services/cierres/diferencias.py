"""Asientos de diferencias: cargar un asiento del diario, duplicarlo (igual o invertido)
con otro ejercicio y número, y exportar los duplicados al Excel de importación del ERP.

Traducción de la pestaña "Contab. Diferencias" del original. Como allí, no se guarda
nada en la base: la lista de duplicados vive en la pantalla y solo sale en el Excel.
"""
from sqlalchemy import text
from ...core.errores import ErrorApp

# Cabeceras exactas de la plantilla de importación de asientos del ERP (43 columnas).
CABECERAS = [
    "serie", "numero", "ejercicio", "linea", "cuenta", "debe", "haber",
    "concepto", "concepmanu", "descconcep", "contrapartida", "fecha",
    "automatico", "diario", "confidencial", "impdivisa", "analitica",
    "documento", "numvto", "tipovto", "ejervto", "divdebe", "divhaber",
    "visado", "usuario", "concepto_c", "descconcep_c", "linea_c",
    "fecha_valor", "cod_asiento", "punteado", "version_bean", "factura_cia",
    "su_cobradora", "su_gestora", "su_productora", "recibo_ord",
    "fecha_expor", "fecha_modif", "fecha_ult_expor", "fecha_ult_modif",
    "clave_cia", "desc_movim_conta",
]


def cargar_asiento(conn, ejercicio: int, numero: int):
    filas = conn.execute(text("""
        SELECT linea, serie, cuenta, debe::float8 AS debe, haber::float8 AS haber, concepto, fecha,
               descripcion_cuenta
        FROM cc_apuntes WHERE ejercicio = :ej AND numero = :n ORDER BY linea, id
    """), {"ej": ejercicio, "n": numero}).mappings().all()
    if not filas:
        raise ErrorApp("CC-DIF-001", numero=numero, ejercicio=ejercicio)
    return [dict(f) for f in filas]


def lineas_duplicadas(conn, d: dict):
    """d: {origen_ejercicio, origen_numero, ejercicio, numero, invertido}."""
    lineas = []
    for i, r in enumerate(cargar_asiento(conn, d["origen_ejercicio"], d["origen_numero"]), 1):
        debe, haber = r["debe"] or 0.0, r["haber"] or 0.0
        if d.get("invertido"):
            debe, haber = (-debe if debe else 0.0), (-haber if haber else 0.0)
        lineas.append({"linea": i, "cuenta": r["cuenta"], "debe": debe, "haber": haber,
                       "concepto": r["concepto"] or "", "descripcion_cuenta": r["descripcion_cuenta"] or ""})
    return lineas


def excel_asientos(conn, duplicados: list[dict], ruta: str):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Asientos"
    ws.append(CABECERAS)
    n = 0
    for d in duplicados:
        ej, num = int(d["ejercicio"]), int(d["numero"])
        for l in lineas_duplicadas(conn, d):
            ws.append(["A", num, ej, l["linea"], int(l["cuenta"]), l["debe"] or None, l["haber"] or None,
                       l["concepto"], None, l["descripcion_cuenta"], None, f"01/01/{ej} 0:00",
                       "N", None, "N", 0, "N", None, None, "C", None, None, None, "N", None, None, None, None,
                       None, f"A1{ej}", None, 1, "N", None, None, None, None, None, None, None, None, None, None])
            n += 1
    wb.save(ruta)
    return {"asientos": len(duplicados), "lineas": n}
