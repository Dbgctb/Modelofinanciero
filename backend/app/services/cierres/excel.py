"""Exportaciones a Excel de las pantallas de punteo (openpyxl, ya instalado; el original
usaba xlsxwriter).

- Selección del punteo manual: mismas columnas y fila de TOTAL que el original.
- Conciliados: hojas "Resumen por Regla", "Bloques" y "Detalle", como el original.
  El detalle puede tener cientos de miles de filas: se escribe en modo write_only.
"""
from collections import defaultdict
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import text

from .consultas import _estado_bloque, sql_bloques

_CAB = Font(bold=True, color="FFFFFF")
_CAB_FONDO = PatternFill("solid", fgColor="1565C0")
_EUR = "#,##0.00"


def _cabecera(ws, titulos, anchos):
    for i, (t, w) in enumerate(zip(titulos, anchos), 1):
        c = ws.cell(row=1, column=i, value=t)
        c.font, c.fill = _CAB, _CAB_FONDO
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "A2"


def excel_seleccion_manual(conn, ids: list[int], ruta: str):
    rows = conn.execute(text("""
        SELECT ejercicio, asiento_key, fecha, cuenta, recibo_norm, concepto,
               debe, haber, neto, reconciled, recon_rule
        FROM cc_apuntes WHERE id = ANY(:ids) ORDER BY cuenta, recibo_norm, fecha, id
    """), {"ids": ids}).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Selección"
    _cabecera(ws, ["Ejercicio", "ID Asiento", "Fecha", "Cuenta", "Recibo", "Concepto",
                   "Debe", "Haber", "Neto", "Conciliada", "Regla"],
              [10, 16, 12, 14, 12, 50, 13, 13, 13, 11, 14])
    for r in rows:
        ws.append([r.ejercicio, r.asiento_key or "", r.fecha, r.cuenta, r.recibo_norm or "",
                   r.concepto or "", float(r.debe), float(r.haber), float(r.neto),
                   "Sí" if r.reconciled else "No", r.recon_rule or ""])
    ultima = ws.max_row
    ws.append([])
    ws.append(["TOTAL", None, None, None, None, None,
               f"=SUM(G2:G{ultima})", f"=SUM(H2:H{ultima})", f"=SUM(I2:I{ultima})"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    for fila in ws.iter_rows(min_row=2, min_col=7, max_col=9):
        for c in fila:
            c.number_format = _EUR
    for fila in ws.iter_rows(min_row=2, min_col=3, max_col=3):
        for c in fila:
            c.number_format = "DD/MM/YYYY"
    wb.save(ruta)
    return {"filas": len(rows)}


def excel_conciliados(conn, ejercicio, regla, ruta: str, progreso=lambda *a, **k: None):
    sql, params = sql_bloques(ejercicio, regla)
    progreso("Calculando bloques…")
    bloques = conn.execute(text(sql), params).mappings().all()

    resumen = defaultdict(lambda: {"bloques": 0, "lineas": 0, "neto": Decimal(0), "a1": 0, "as": 0})
    for b in bloques:
        suma, est = _estado_bloque(b)
        d = resumen[b["recon_rule"]]
        d["bloques"] += 1
        d["lineas"] += b["num_lineas"]
        d["neto"] += b["suma_neto"]
        d["a1"] += b["num_lineas"] == 1
        d["as"] += est == "Suma fuera de tolerancia"

    wb = Workbook(write_only=True)
    ws1 = wb.create_sheet("Resumen por Regla")
    ws1.append(["Regla", "Bloques", "Nº Líneas", "Suma Neto", "⚠ 1 línea", "⚠ Suma"])
    for reg, d in sorted(resumen.items()):
        ws1.append([reg, d["bloques"], d["lineas"], float(d["neto"]), d["a1"], d["as"]])
    ws1.append(["TOTAL", sum(d["bloques"] for d in resumen.values()),
                sum(d["lineas"] for d in resumen.values()),
                float(sum((d["neto"] for d in resumen.values()), Decimal(0)))])

    progreso(f"Escribiendo {len(bloques):,} bloques…".replace(",", "."))
    ws2 = wb.create_sheet("Bloques")
    ws2.append(["Grupo", "Regla", "Nº Líneas", "Suma Neto", "Ej. Mín", "Ej. Máx", "Estado"])
    for b in bloques:
        suma, est = _estado_bloque(b)
        cross = " [X]" if b["min_ej"] != b["max_ej"] else ""
        ws2.append([b["recon_group_id"], b["recon_rule"], b["num_lineas"], float(suma),
                    b["min_ej"], f"{b['max_ej']}{cross}", est])

    progreso("Escribiendo el detalle…")
    ws3 = wb.create_sheet("Detalle")
    ws3.append(["Grupo", "Regla", "Ejercicio", "Fecha", "Cuenta", "Debe", "Haber", "Neto"])
    n = 0
    det = conn.execution_options(stream_results=True, yield_per=20_000).execute(text(f"""
        SELECT j.recon_group_id, j.recon_rule, j.ejercicio, j.fecha, j.cuenta, j.debe, j.haber, j.neto
        FROM cc_apuntes j
        JOIN unnest(CAST(:grupos AS text[])) AS g(id) ON g.id = j.recon_group_id
        WHERE j.reconciled
        ORDER BY j.recon_group_id COLLATE "C" DESC, j.ejercicio, j.id
    """), {"grupos": [b["recon_group_id"] for b in bloques]})
    for r in det:
        ws3.append([r.recon_group_id, r.recon_rule, r.ejercicio, r.fecha, r.cuenta,
                    float(r.debe), float(r.haber), float(r.neto)])
        n += 1
        if n % 100_000 == 0:
            progreso(f"Detalle: {n:,} filas…".replace(",", "."))
    progreso("Guardando el fichero…")
    wb.save(ruta)
    return {"bloques": len(bloques), "lineas_detalle": n}
