"""
Servicio de tesorería presupuestada. RF-TES-01 a RF-TES-13.
Cobros: 30 días por defecto.
Pagos:  inmediato por defecto; cesiones a auxiliares a 30 días.
Netos:  SS empleado + IRPF deducidos en pagos de personal (640*).
        Retención IRPF deducida en pagos de cesiones.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.presupuesto import (
    Presupuesto, PresupuestoIngreso, PresupuestoGasto,
    TipoReglaGasto, PresupuestoCesionAuxiliar,
)
from ..models.tesoreria import (
    TesoreriaConfig, TesoreriaApunteManual, TesoreriaResultado,
    TesoreriaEmpleado, ReglaCobro, ReglaPago,
)

# ── Sentinel keys para configs globales ──────────────────────────────────────
_KEY_COBROS_GLOBAL   = '__cobros__'   # familia_gasto sentinel → regla_cobro global
_KEY_PAGOS_DEFAULT   = '__pagos__'    # familia_gasto sentinel → regla_pago por defecto
_FAMILIA_CESIONES    = 'Cesiones a auxiliares'
_FAMILIA_AMORT       = 'Amortizaciones y ajustes'


def _get_regla_cobro(configs: List[TesoreriaConfig], compania: Optional[str]) -> ReglaCobro:
    # 1. Regla específica de compañía
    for c in configs:
        if c.compania == compania and c.compania is not None and c.regla_cobro:
            return c.regla_cobro
    # 2. Global de cobros
    for c in configs:
        if c.familia_gasto == _KEY_COBROS_GLOBAL and c.regla_cobro:
            return c.regla_cobro
    return ReglaCobro.DIAS_30          # defecto: 30 días


def _get_regla_pago(configs: List[TesoreriaConfig], familia: Optional[str]) -> ReglaPago:
    # 1. Regla específica de familia
    for c in configs:
        if c.familia_gasto == familia and familia not in (None, _KEY_COBROS_GLOBAL, _KEY_PAGOS_DEFAULT) and c.regla_pago:
            return c.regla_pago
    # 2. Global de pagos
    for c in configs:
        if c.familia_gasto == _KEY_PAGOS_DEFAULT and c.regla_pago:
            return c.regla_pago
    return ReglaPago.MISMO_MES         # defecto: inmediato


def _get_regla_pago_cesiones(configs: List[TesoreriaConfig]) -> ReglaPago:
    for c in configs:
        if c.familia_gasto == _FAMILIA_CESIONES and c.regla_pago:
            return c.regla_pago
    return ReglaPago.DIAS_30           # cesiones: 30 días por defecto


def _aplicar_regla_cobro(importes_12: List[float], regla: ReglaCobro) -> List[float]:
    if regla == ReglaCobro.MISMO_MES:
        return list(importes_12)
    cobros = [0.0] * 12
    if regla == ReglaCobro.MES_SIGUIENTE:
        for i, v in enumerate(importes_12):
            if i + 1 < 12:
                cobros[i + 1] += v
    elif regla == ReglaCobro.DIAS_30:
        for i, v in enumerate(importes_12):
            cobros[i] += v * 0.5
            if i + 1 < 12:
                cobros[i + 1] += v * 0.5
    elif regla == ReglaCobro.DIAS_60:
        for i, v in enumerate(importes_12):
            if i + 2 < 12:
                cobros[i + 2] += v
            elif i + 1 < 12:
                cobros[i + 1] += v * 0.5
    else:
        cobros = list(importes_12)
    return [round(v, 2) for v in cobros]


def _aplicar_regla_pago(importes_12: List[float], regla: ReglaPago) -> List[float]:
    if regla == ReglaPago.MISMO_MES:
        return list(importes_12)
    pagos = [0.0] * 12
    if regla == ReglaPago.MES_SIGUIENTE:
        for i, v in enumerate(importes_12):
            if i + 1 < 12:
                pagos[i + 1] += v
    elif regla == ReglaPago.DIAS_30:
        for i, v in enumerate(importes_12):
            pagos[i] += v * 0.5
            if i + 1 < 12:
                pagos[i + 1] += v * 0.5
    elif regla == ReglaPago.DIAS_60:
        for i, v in enumerate(importes_12):
            if i + 2 < 12:
                pagos[i + 2] += v
            elif i + 1 < 12:
                pagos[i + 1] += v * 0.5
    else:
        pagos = list(importes_12)
    return [round(v, 2) for v in pagos]


def calcular_tesoreria(
    db: Session,
    presupuesto: Presupuesto,
    caja_inicial: float,
    caja_minima: Optional[float],
) -> TesoreriaResultado:
    configs = db.query(TesoreriaConfig).filter(
        TesoreriaConfig.presupuesto_id == presupuesto.id
    ).all()

    # ── Mapa empleados: numero_cuenta → net_factor y pct_irpf ────────────────
    empleados = db.query(TesoreriaEmpleado).filter(
        TesoreriaEmpleado.presupuesto_id == presupuesto.id
    ).all()
    emp_net: dict[str, float] = {}
    emp_irpf_pct: dict[str, float] = {}
    for e in empleados:
        if e.numero_cuenta:
            pct_irpf = float(e.pct_irpf or 0) / 100
            factor = 1.0 - float(e.pct_ss or 0) / 100 - pct_irpf
            emp_net[e.numero_cuenta] = max(0.0, factor)
            emp_irpf_pct[e.numero_cuenta] = pct_irpf

    # ── Cobros desde ingresos presupuestados ──────────────────────────────────
    lineas_ing = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id
    ).all()

    cobros_totales = [0.0] * 12
    for linea in lineas_ing:
        regla = _get_regla_cobro(configs, linea.compania)
        importes = linea.importes_mensuales or [0.0] * 12
        cobros = _aplicar_regla_cobro(importes, regla)
        for i in range(12):
            cobros_totales[i] += cobros[i]

    # ── Pagos desde gastos (excl. amortizaciones y cesiones auxiliares) ───────
    lineas_gas = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto.id,
        PresupuestoGasto.tipo_regla != TipoReglaGasto.EXCLUIR,
    ).all()

    pagos_totales = [0.0] * 12
    irpf_nomina   = [0.0] * 12   # IRPF retenido de nóminas por mes

    for linea in lineas_gas:
        fam = linea.familia_gasto or ''
        if fam == _FAMILIA_AMORT:
            continue          # sin impacto en caja
        if 'auxiliar' in fam.lower():
            continue          # cesiones tratadas por separado abajo

        importes_ef = [
            float(
                linea.importes_manuales[i]
                if linea.importes_manuales and linea.importes_manuales[i] is not None
                else (linea.importes_mensuales[i] if linea.importes_mensuales and i < len(linea.importes_mensuales) else 0)
            )
            for i in range(12)
        ]

        # Personal 640*: acumular IRPF retenido; aplicar factor neto al pago
        cuenta = (linea.numero_cuenta or '').strip()
        if cuenta.startswith('640'):
            irpf_f = emp_irpf_pct.get(cuenta, 0.0)
            for i in range(12):
                irpf_nomina[i] += importes_ef[i] * irpf_f
            factor = emp_net.get(cuenta, 1.0)
            importes_ef = [v * factor for v in importes_ef]

        regla = _get_regla_pago(configs, fam)
        pagos = _aplicar_regla_pago(importes_ef, regla)
        for i in range(12):
            pagos_totales[i] += pagos[i]

    # ── Cesiones a auxiliares: neto de retención, a 30 días ──────────────────
    cesiones = db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto.id
    ).all()
    regla_ces = _get_regla_pago_cesiones(configs)
    irpf_cesiones = [0.0] * 12   # IRPF retenido de cesiones por mes

    for ces in cesiones:
        retencion = float(ces.pct_retencion or 0) / 100
        factor_neto = max(0.0, 1.0 - retencion)
        meses_ces = ces.importes_mensuales or [0.0] * 12
        importes_ces = [float(meses_ces[i]) * factor_neto for i in range(12)]
        for i in range(12):
            irpf_cesiones[i] += float(meses_ces[i]) * retencion
        pagos = _aplicar_regla_pago(importes_ces, regla_ces)
        for i in range(12):
            pagos_totales[i] += pagos[i]

    # ── Mod-111: pagos trimestrales IRPF a Hacienda ───────────────────────────
    # En enero se paga el 4T del año anterior (se estima con el 4T del ejercicio).
    # El 4T del ejercicio (oct-dic) se paga en enero del año siguiente → no se incluye.
    # Resultado: 4 pagos dentro del año, simétrico y sin distorsión neta.
    _TRIMESTRES = [
        (9, 12, 0,  '4T ant. (est.)', True),   # Q4 anterior → enero     (estimado)
        (0,  3, 3,  '1T',             False),   # Q1          → abril
        (3,  6, 6,  '2T',             False),   # Q2          → julio
        (6,  9, 9,  '3T',             False),   # Q3          → octubre
    ]
    irpf_trimestral: list[dict] = []
    for ini, fin, idx_pago, label, es_estimado in _TRIMESTRES:
        nom_q = round(sum(irpf_nomina[ini:fin]), 2)
        ces_q = round(sum(irpf_cesiones[ini:fin]), 2)
        tot_q = round(nom_q + ces_q, 2)
        irpf_trimestral.append({
            'label': label,
            'nomina': nom_q,
            'cesiones': ces_q,
            'total': tot_q,
            'mes_pago': idx_pago + 1,
            'es_estimado': es_estimado,
        })
        if tot_q > 0:
            pagos_totales[idx_pago] += tot_q

    # ── Apuntes manuales ──────────────────────────────────────────────────────
    apuntes = db.query(TesoreriaApunteManual).filter(
        TesoreriaApunteManual.presupuesto_id == presupuesto.id
    ).all()

    entradas = [0.0] * 12
    salidas  = [0.0] * 12
    for ap in apuntes:
        idx = ap.mes - 1
        entradas[idx] += float(ap.importe_haber or 0)
        salidas[idx]  += float(ap.importe_debe  or 0)

    # ── Flujo y caja encadenada ───────────────────────────────────────────────
    flujo = [
        round(cobros_totales[i] - pagos_totales[i] + entradas[i] - salidas[i], 2)
        for i in range(12)
    ]
    caja_final: list[float] = []
    caja_acum = caja_inicial
    for f in flujo:
        caja_acum = round(caja_acum + f, 2)
        caja_final.append(caja_acum)

    # ── Alertas ───────────────────────────────────────────────────────────────
    alertas = []
    if caja_minima is not None:
        for i, cf in enumerate(caja_final):
            if cf < caja_minima:
                alertas.append({'mes': i + 1, 'caja_final': cf, 'caja_minima': caja_minima})

    # ── Guardar resultado ─────────────────────────────────────────────────────
    resultado = db.query(TesoreriaResultado).filter(
        TesoreriaResultado.presupuesto_id == presupuesto.id
    ).first()
    if not resultado:
        resultado = TesoreriaResultado(presupuesto_id=presupuesto.id)
        db.add(resultado)

    resultado.caja_inicial          = caja_inicial
    resultado.caja_minima           = caja_minima
    resultado.cobros_mensuales      = [round(v, 2) for v in cobros_totales]
    resultado.pagos_mensuales       = [round(v, 2) for v in pagos_totales]
    resultado.entradas_manuales     = [round(v, 2) for v in entradas]
    resultado.salidas_manuales      = [round(v, 2) for v in salidas]
    resultado.flujo_mensual         = flujo
    resultado.caja_final_mensual    = caja_final
    resultado.alertas               = alertas
    resultado.irpf_trimestral       = irpf_trimestral

    db.commit()
    db.refresh(resultado)
    return resultado
