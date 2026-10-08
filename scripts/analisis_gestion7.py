"""
Análisis exhaustivo de GESTION 7 ASESORES en el diario 2025.
Compara los números del Excel con lo que el modelo debería calcular.
"""
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('diario 2025 david.xlsx', read_only=True, data_only=True)
ws = wb['Hoja completada']

# Recoge TODAS las líneas que mencionan GESTION 7 en cualquier campo
lineas_g7 = []
lineas_g7_cia = []   # donde compania = GESTION 7
lineas_g7_aux = []   # donde auxiliar = GESTION 7

for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0:
        continue
    if row[0] is None:
        break
    cia = str(row[13]).strip() if row[13] else ''
    aux = str(row[14]).strip() if row[14] else ''
    agrup = str(row[9]) if row[9] else ''
    recibo = row[12]
    debe = float(row[5]) if row[5] else 0.0
    haber = float(row[6]) if row[6] else 0.0
    tiene_rec = bool(recibo and str(recibo).strip() not in ('', 'None', '0'))

    es_g7_cia = 'GESTION 7' in cia.upper()
    es_g7_aux = 'GESTION 7' in aux.upper()

    if es_g7_cia or es_g7_aux:
        lineas_g7.append({
            'linea': row[0], 'fecha': str(row[4])[:10],
            'agrup': agrup, 'desc': str(row[10])[:30],
            'concepto': str(row[11])[:40],
            'debe': debe, 'haber': haber,
            'recibo': str(recibo).strip() if recibo else '',
            'cia': cia, 'aux': aux,
            'tiene_rec': tiene_rec,
            'campo': 'AUX' if es_g7_aux else 'CIA',
        })
        if es_g7_cia:
            lineas_g7_cia.append(agrup)
        if es_g7_aux:
            lineas_g7_aux.append(agrup)

print('=== RESUMEN GESTION 7 ===')
print('Total lineas donde aparece:', len(lineas_g7))
print('  En campo Auxiliar (col aux):', sum(1 for l in lineas_g7 if l['campo'] == 'AUX'))
print('  En campo Compania (col cia):', sum(1 for l in lineas_g7 if l['campo'] == 'CIA'))
print()

# Agrupar por cuenta y campo
from collections import Counter
print('Cuentas donde aparece:')
cta_campo = Counter((l['agrup'], l['campo'], l['tiene_rec']) for l in lineas_g7)
for (agrup, campo, tiene_rec), n in sorted(cta_campo.items()):
    print(f'  cta={agrup}  campo={campo}  con_recibo={tiene_rec}  n={n}')

print()
print('=== INGRESOS 705 DE GESTION 7 ===')
ing_con_rec = 0.0
ing_sin_rec = 0.0
n_ing_con = 0
n_ing_sin = 0
for l in lineas_g7:
    if l['agrup'].startswith('705'):
        ingreso = l['haber'] - l['debe']
        if l['tiene_rec']:
            ing_con_rec += ingreso
            n_ing_con += 1
        else:
            ing_sin_rec += ingreso
            n_ing_sin += 1
            print(f"  SIN RECIBO: {l['fecha']} {l['concepto'][:50]} H={l['haber']} D={l['debe']} campo={l['campo']}")

print(f'  Con recibo: {n_ing_con} lineas = {round(ing_con_rec,2)} €')
print(f'  Sin recibo: {n_ing_sin} lineas = {round(ing_sin_rec,2)} €')
print(f'  TOTAL 705:  {round(ing_con_rec + ing_sin_rec, 2)} €')

print()
print('=== CESION 623 DE GESTION 7 ===')
ces_con_rec_aux = 0.0
ces_con_rec_cia = 0.0
ces_sin_rec_aux = 0.0
ces_sin_rec_cia = 0.0
n_ces = 0
for l in lineas_g7:
    if l['agrup'].startswith('623'):
        ces = l['debe'] - l['haber']
        n_ces += 1
        if l['campo'] == 'AUX':
            if l['tiene_rec']:
                ces_con_rec_aux += ces
            else:
                ces_sin_rec_aux += ces
                print(f"  SIN RECIBO (aux): {l['fecha']} {l['concepto'][:50]} D={l['debe']} H={l['haber']}")
        else:  # campo CIA
            if l['tiene_rec']:
                ces_con_rec_cia += ces
            else:
                ces_sin_rec_cia += ces
                print(f"  SIN RECIBO (cia): {l['fecha']} {l['concepto'][:50]} D={l['debe']} H={l['haber']}")

print(f'  Con recibo, campo aux: {round(ces_con_rec_aux,2)} €')
print(f'  Con recibo, campo cia: {round(ces_con_rec_cia,2)} €')
print(f'  Sin recibo, campo aux: {round(ces_sin_rec_aux,2)} €')
print(f'  Sin recibo, campo cia: {round(ces_sin_rec_cia,2)} €')
print(f'  TOTAL 623:  {round(ces_con_rec_aux + ces_con_rec_cia + ces_sin_rec_aux + ces_sin_rec_cia, 2)} €')

print()
print('=== LO QUE VE EL MODELO vs LO QUE VE EL EXCEL ===')
total_ing = ing_con_rec + ing_sin_rec
total_ces = ces_con_rec_aux + ces_con_rec_cia + ces_sin_rec_aux + ces_sin_rec_cia

print('EXCEL (tu control):')
print(f'  Ingresos: 125.647,65 €')
print(f'  Cesion:    63.019,71 €')
print()
print('DIARIO (lo que hay en la hoja completada):')
print(f'  Ingresos 705: {round(total_ing,2)} €')
print(f'  Cesion 623:   {round(total_ces,2)} €')
print()

# Hipotesis: el Excel solo cuenta campo AUX, el modelo tambien suma campo CIA
print('Hipotesis: Excel solo cuenta donde auxiliar=GESTION7, no donde compania=GESTION7')
print(f'  Ingresos solo campo AUX: {round(sum(l["haber"]-l["debe"] for l in lineas_g7 if l["agrup"].startswith("705") and l["campo"]=="AUX"),2)}')
print(f'  Cesion solo campo AUX:   {round(sum(l["debe"]-l["haber"] for l in lineas_g7 if l["agrup"].startswith("623") and l["campo"]=="AUX"),2)}')
print()
print(f'  Ingresos solo campo CIA: {round(sum(l["haber"]-l["debe"] for l in lineas_g7 if l["agrup"].startswith("705") and l["campo"]=="CIA"),2)}')
print(f'  Cesion solo campo CIA:   {round(sum(l["debe"]-l["haber"] for l in lineas_g7 if l["agrup"].startswith("623") and l["campo"]=="CIA"),2)}')
