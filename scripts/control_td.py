"""
Compara los controles de la hoja Td con lo que realmente hay
en la hoja completada. Cuenta de lineas con recibo por compania,
por auxiliar, e importes por cuenta.
"""
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('diario 2025 david.xlsx', read_only=True, data_only=True)

# ── 1. Leer controles Td ───────────────────────────────────────────────────
ws_td = wb['Td']
td_cia_recibos = {}    # compania -> n lineas con recibo (todas las cuentas)
td_gastos_cta = {}     # cuenta -> importe
td_total_recibos_cta = {}  # cuenta -> n recibos

fila_actual = 'gastos'
for i, row in enumerate(ws_td.iter_rows(values_only=True)):
    r = row
    # Seccion izquierda: gastos por cuenta (col A=cuenta, B=importe)
    if r[0] not in (None, 'Etiquetas de fila', 'Total general') and r[1] is not None:
        td_gastos_cta[str(r[0])] = r[1]
    # Seccion media: recibos por cuenta (col D=cuenta, E=n)
    if r[3] not in (None, 'Total Recibos', 'Cuenta de Recibo', 'Total general') and r[4] is not None:
        td_total_recibos_cta[str(r[3])] = int(r[4])
    # Seccion derecha: recibos por compania (col G=cia, H=n) desde fila 33
    if i >= 30 and r[6] not in (None, 'Suma de Campo1', 'Total Recibos', 'Total general',
                                 'Etiquetas de columna', 'Agrupacion Cuenta', 'Etiquetas de fila'):
        if r[7] is not None:
            td_cia_recibos[str(r[6]).strip()] = int(r[7])

print('=== CONTROLES Td: gastos por cuenta ===')
for k, v in sorted(td_gastos_cta.items()):
    print(f'  {k}: {round(v,2)}')

print()
print('=== CONTROLES Td: lineas con recibo por cuenta ===')
for k, v in sorted(td_total_recibos_cta.items()):
    print(f'  {k}: {v}')

print()
print('=== CONTROLES Td: lineas con recibo por compania ===')
for k, v in sorted(td_cia_recibos.items()):
    print(f'  {k}: {v}')
print('  TOTAL Td:', sum(td_cia_recibos.values()))

# ── 2. Calcular desde hoja completada ─────────────────────────────────────
ws_d = wb['Hoja completada']

calc_cia_recibos = defaultdict(int)   # compania -> n lineas con recibo (todas cuentas 6+7)
calc_gastos_cta = defaultdict(float)  # cuenta -> importe (debe-haber)
calc_recibos_cta = defaultdict(int)   # cuenta -> n lineas con recibo

for i, row in enumerate(ws_d.iter_rows(values_only=True)):
    if i == 0:
        continue
    if row[0] is None:
        break
    agrup = str(row[9]) if row[9] else ''
    recibo = row[12]
    debe = float(row[5]) if row[5] else 0.0
    haber = float(row[6]) if row[6] else 0.0
    cia = str(row[13]).strip() if row[13] else '(sin cia)'

    # Importe por cuenta (6 = gasto, 7 = ingreso)
    calc_gastos_cta[agrup] += debe - haber

    # Lineas con recibo por cuenta y por compania
    tiene_recibo = bool(recibo and str(recibo).strip() not in ('', 'None', '0'))
    if tiene_recibo:
        calc_recibos_cta[agrup] += 1
        if agrup.startswith('6') or agrup.startswith('7'):
            calc_cia_recibos[cia] += 1

# ── 3. Comparar importes por cuenta ───────────────────────────────────────
print()
print('=== COMPARACION IMPORTES POR CUENTA (Td vs diario) ===')
print('Cuenta     Td-importe     Diario-importe  Diferencia')
todas_ctas = sorted(set(list(td_gastos_cta.keys()) + list(calc_gastos_cta.keys())))
for cta in todas_ctas:
    td_v = td_gastos_cta.get(cta, 0)
    calc_v = calc_gastos_cta.get(cta, 0)
    diff = round(td_v - calc_v, 2)
    flag = ' <-- DIFIERE' if abs(diff) > 0.05 else ''
    print(f'  {cta:<8} {round(td_v,2):>14} {round(calc_v,2):>15} {diff:>12}{flag}')

# ── 4. Comparar lineas con recibo por cuenta ──────────────────────────────
print()
print('=== COMPARACION LINEAS CON RECIBO POR CUENTA (Td vs diario) ===')
print('Cuenta    Td-n    Diario-n   Diferencia')
for cta in sorted(set(list(td_total_recibos_cta.keys()) + list(calc_recibos_cta.keys()))):
    td_n = td_total_recibos_cta.get(cta, 0)
    calc_n = calc_recibos_cta.get(cta, 0)
    diff = td_n - calc_n
    flag = ' <-- DIFIERE' if diff != 0 else ''
    print(f'  {cta:<8} {td_n:>7} {calc_n:>10} {diff:>12}{flag}')

# ── 5. Comparar recibos por compania ──────────────────────────────────────
print()
print('=== COMPARACION LINEAS CON RECIBO POR COMPANIA (Td vs diario) ===')
print('Compania                               Td-n  Diario-n   Dif')
todas_cias = sorted(set(list(td_cia_recibos.keys()) + list(calc_cia_recibos.keys())))
dif_total = 0
for cia in todas_cias:
    td_n = td_cia_recibos.get(cia, 0)
    calc_n = calc_cia_recibos.get(cia, 0)
    diff = td_n - calc_n
    dif_total += abs(diff)
    flag = ' <-- DIFIERE' if diff != 0 else ''
    print(f'  {cia[:36]:<37} {td_n:>5} {calc_n:>8} {diff:>6}{flag}')
print(f'  {"TOTAL":<37} {sum(td_cia_recibos.values()):>5} {sum(calc_cia_recibos.values()):>8}')
print(f'  Suma diferencias absolutas: {dif_total}')
