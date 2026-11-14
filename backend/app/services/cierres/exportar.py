"""Exportar: Excel de los apuntes sin puntear agrupados por cuenta (con niveles de
esquema para plegar cada cuenta), como el botón "Exportar a Excel" del original.

Además se añade la hoja "Incidencias" con el detalle de los controles de calidad
vigentes (el original tenía el código de esa hoja pero el botón no la generaba).
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import text

MAX_FILAS = 1_048_575


def _cabecera(ws, titulos, anchos):
    ws.append(titulos)
    for c, w in zip(ws[1], anchos):
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1565C0")
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "A2"


def excel_no_conciliados(conn, ruta, ejercicio=None, progreso=lambda *a, **k: None):
    filtro, p = ("AND ejercicio = :ej", {"ej": ejercicio}) if ejercicio else ("", {})
    progreso("Leyendo apuntes sin puntear…")
    filas = conn.execute(text(f"""
        SELECT cuenta, recibo_norm, concepto, ejercicio, fecha, neto::float8 AS neto FROM cc_apuntes
        WHERE NOT reconciled {filtro}
        ORDER BY cuenta, CASE WHEN recibo_norm IS NULL OR recibo_norm = '' THEN 1 ELSE 0 END,
                 recibo_norm, fecha, id"""), p).all()
    por_cuenta = {}
    for f in filas:
        por_cuenta.setdefault(f.cuenta, []).append(f)

    wb = Workbook()
    wb.remove(wb.active)
    ws, n_hoja, usadas, fila = None, 0, 0, 1
    negrita = Font(bold=True)
    progreso(f"Escribiendo {len(filas):,} apuntes en {len(por_cuenta):,} cuentas…".replace(",", "."))
    for cuenta in sorted(por_cuenta):
        det = por_cuenta[cuenta]
        if ws is None or usadas + 1 + len(det) > MAX_FILAS:
            n_hoja += 1
            ws = wb.create_sheet(f"NO_Conciliados_{n_hoja}" if n_hoja > 1 else "NO_Conciliados")
            _cabecera(ws, ["Cuenta", "Recibo", "Concepto", "Ejercicio", "Fecha", "Neto"], [14, 12, 60, 10, 12, 14])
            ws.sheet_properties.outlinePr.summaryBelow = False
            usadas, fila = 0, 1
        # Contador propio de filas: ws.max_row recorre la hoja entera en cada llamada.
        fila += 1
        ws.append([int(cuenta), None, None, None, None, round(sum(d.neto for d in det), 2)])
        ws.cell(fila, 1).font = negrita
        ws.cell(fila, 6).font = negrita
        ws.cell(fila, 6).number_format = "#,##0.00"
        for d in det:
            fila += 1
            ws.append([None, d.recibo_norm or "", (d.concepto or "")[:100], d.ejercicio, d.fecha, d.neto])
            ws.row_dimensions[fila].outlineLevel = 1
            ws.cell(fila, 5).number_format = "DD/MM/YYYY"
            ws.cell(fila, 6).number_format = "#,##0.00"
        usadas += 1 + len(det)

    progreso("Hoja de incidencias…")
    wi = wb.create_sheet("Incidencias")
    _cabecera(wi, ["Ejercicio", "Control", "Gravedad", "Cuenta", "Recibo", "Mes", "Descripción", "Apuntes"],
              [10, 9, 11, 14, 12, 6, 70, 30])
    for r in conn.execute(text(f"""
        SELECT ejercicio, control_type, severity, cuenta, recibo_norm, mes, issue_description, line_ids
        FROM cc_incidencias WHERE TRUE {filtro} ORDER BY ejercicio, control_type, cuenta, mes, id"""), p):
        wi.append([r.ejercicio, r.control_type, r.severity, r.cuenta, r.recibo_norm, r.mes, r.issue_description,
                   ", ".join(map(str, r.line_ids or []))])
    progreso("Guardando el fichero…")
    wb.save(ruta)
    return {"apuntes": len(filas), "cuentas": len(por_cuenta), "hojas": n_hoja}
