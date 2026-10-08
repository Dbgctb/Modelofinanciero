"""
Identifica exactamente qué entra en el modelo para GESTION 7:
- Qué va DIRECTO (con recibo o sin recibo pero auxiliar identificado)
- Qué va INDIRECTO (pool que se reparte por driver) y cuánto se le asigna a G7
"""
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('diario 2025 david.xlsx', read_only=True, data_only=True)
ws  = wb['Hoja completada']
ws_r = wb['Recibos']

# ── 1. Calcular el peso de G7 en el driver (recibos únicos del diario) ────────
rec_g7 = set()
rec_total = set()
rec_g7_liqui = 0.0
rec_total_liqui = 0.0

# Recibos de la hoja Recibos referenciados en el diario: necesitamos cruzar
# Primero: recibos referenciados en el diario (campo 12) con ente G7
recibos_en_diario = set()
rec_diario_g7 = set()
rec_diario_g7_liqui = 0.0

# Índice de recibos: codigo -> (ente, liqui)
rec_index = {}
for i, row in enumerate(ws_r.iter_rows(values_only=True)):
    if i == 0: continue
    if row[0] is None: break
    try:
        cod = str(int(row[0]))
    except:
        cod = str(row[0]).strip()
    ente = str(row[10]).strip() if row[10] else ''
    liqui = float(row[9]) if row[9] else 0.0
    rec_index[cod] = (ente, liqui)

for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0: continue
    if row[0] is None: break
    rec = row[12]
    if not rec or str(rec).strip() in ('','None','0'): continue
    r = str(rec).strip()
    recibos_en_diario.add(r)
    if r in rec_index:
        ente, liqui = rec_index[r]
        if 'GESTION 7' in ente.upper():
            rec_diario_g7.add(r)
            rec_diario_g7_liqui += liqui

rec_total_n = len(recibos_en_diario)
g7_n = len(rec_diario_g7)
rec_total_liqui = sum(v[1] for v in rec_index.values() if v[0] in recibos_en_diario or True)
# Liqui total solo de recibos del diario
rec_total_liqui = sum(rec_index[r][1] for r in recibos_en_diario if r in rec_index)

peso_g7_recibos    = g7_n / rec_total_n if rec_total_n else 0
peso_g7_comision   = rec_diario_g7_liqui / rec_total_liqui if rec_total_liqui else 0

print('=== PESO DE G7 EN DRIVERS (solo recibos del diario 2025) ===')
print(f'  Recibos G7 en diario: {g7_n} de {rec_total_n} → peso RECIBOS = {peso_g7_recibos*100:.1f}%')
print(f'  Liqui G7: {round(rec_diario_g7_liqui,2)} de {round(rec_total_liqui,2)} → peso COMISION_NETA = {peso_g7_comision*100:.1f}%')

# ── 2. Clasificar TODAS las líneas del diario como el modelo lo haría ─────────
# Reglas del modelo:
#   - 705 con recibo        → DIRECTO (ingreso)
#   - 705 sin recibo        → INDIRECTO (ingreso, sin naturaleza, sin driver)
#   - 623 con recibo        → DIRECTO (cesión)
#   - 623 sin recibo + aux  → DIRECTO (cesión, aux identificado)
#   - 623 sin recibo s/aux  → INDIRECTO (cesión)
#   - 6xx otros sin recibo  → INDIRECTO (coste operativo)

print()
print('=== CLASIFICACION DE LINEAS DEL DIARIO ===')

indirect_705 = []   # (importe, aux_excel)
indirect_623 = []   # (importe, aux_excel, cia_excel)
indirect_6xx = defaultdict(float)  # agrup -> importe total

direct_g7_705 = 0.0
direct_g7_623 = 0.0

for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0: continue
    if row[0] is None: break
    agrup = str(row[9]) if row[9] else ''
    rec   = row[12]
    debe  = float(row[5]) if row[5] else 0.0
    haber = float(row[6]) if row[6] else 0.0
    aux   = str(row[14]).strip() if row[14] else ''
    cia   = str(row[13]).strip() if row[13] else ''
    tiene_rec = bool(rec and str(rec).strip() not in ('','None','0'))
    importe = haber - debe  # positivo=ingreso, negativo=coste

    if agrup.startswith('705'):
        if tiene_rec:
            if 'GESTION 7' in aux.upper():
                direct_g7_705 += importe
        else:
            # INDIRECTO: va al pool de reparto
            indirect_705.append((importe, aux, cia))

    elif agrup.startswith('623'):
        if tiene_rec:
            if 'GESTION 7' in aux.upper():
                direct_g7_623 += importe
        else:
            # Sin recibo: ¿tiene auxiliar identificado?
            aux_id = aux or cia
            if aux_id:
                # DIRECTO al auxiliar identificado (si es G7, va a G7)
                if 'GESTION 7' in aux_id.upper():
                    direct_g7_623 += importe
                    # No va al pool
                else:
                    pass  # va directo a otro auxiliar, no afecta G7
            else:
                # INDIRECTO: va al pool
                indirect_623.append((importe, aux, cia))
    else:
        if not tiene_rec:
            indirect_6xx[agrup] += importe  # todos los 6xx sin recibo son indirectos

# ── 3. Cuantificar qué le llega a G7 desde los pools indirectos ───────────────
total_indirect_705 = sum(v[0] for v in indirect_705)
total_indirect_623 = sum(v[0] for v in indirect_623)
total_indirect_6xx = sum(indirect_6xx.values())

# G7 recibe peso_g7_comision (COMISION_NETA) de cada pool indirecto
# (para 705 ingresos no hay driver definido en el modelo actual → usa RECIBOS)
g7_from_indirect_705 = total_indirect_705 * peso_g7_recibos
g7_from_indirect_623 = total_indirect_623 * peso_g7_comision
g7_from_indirect_6xx = total_indirect_6xx * peso_g7_comision  # Personal, Alquiler, etc.

print(f'  Pool 705 indirecto: {round(total_indirect_705,2)} €  → G7 recibe ({peso_g7_recibos*100:.1f}%): {round(g7_from_indirect_705,2)} €')
print(f'  Pool 623 indirecto: {round(total_indirect_623,2)} €  → G7 recibe ({peso_g7_comision*100:.1f}%): {round(g7_from_indirect_623,2)} €')
print(f'  Pool 6xx indirecto: {round(total_indirect_6xx,2)} €  → G7 recibe ({peso_g7_comision*100:.1f}%): {round(g7_from_indirect_6xx,2)} €')

print()
print('=== DESGLOSE 705 INDIRECTO (líneas sin recibo) ===')
for imp, aux, cia in indirect_705:
    print(f'  imp={round(imp,2)}  aux={aux[:30]}  cia={cia[:30]}')
print(f'  TOTAL: {round(total_indirect_705,2)}')

print()
print('=== DESGLOSE 623 INDIRECTO (sin recibo Y sin auxiliar identificado) ===')
if indirect_623:
    for imp, aux, cia in indirect_623:
        print(f'  imp={round(imp,2)}  aux={aux[:30]}  cia={cia[:30]}')
else:
    print('  (ninguno: todos los 623 sin recibo tienen auxiliar identificado en el Excel)')

print()
print('=== COMPARACION FINAL GESTION 7 ===')
print('                      EXCEL        MODELO(directo)   MODELO(+indirecto)')
print(f'  Ingresos 705:   {125647.65:>10.2f}  {round(direct_g7_705,2):>16.2f}  {round(direct_g7_705+g7_from_indirect_705,2):>18.2f}')
print(f'  Cesion 623:     {63019.71:>10.2f}  {round(-direct_g7_623,2):>16.2f}  {round(-direct_g7_623-g7_from_indirect_623,2):>18.2f}')
print()
print('CAUSA DEL DESCUADRE:')
print(f'  Extra ingresos por pool 705 indirecto:   +{round(g7_from_indirect_705,2)} €')
print(f'  Extra cesion por pool 623 indirecto:     +{round(-g7_from_indirect_623,2)} €')
print()
print('DIAGNOSTICO 705 indirecto:')
print('  Son ajustes de liquidacion y comisiones SANITAS sin recibo vinculado.')
print('  En el Excel tienen auxiliar="Directo" → no pertenecen a ningun auxiliar.')
print('  SOLUCION: tratarlos como ingresos de la correduria (no repartir).')
