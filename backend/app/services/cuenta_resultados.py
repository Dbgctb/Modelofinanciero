"""
Servicio de Cuenta de Resultados (P&L).
Compara presupuesto cerrado vs real del ejercicio base.
"""
from sqlalchemy import text as _text
from sqlalchemy.orm import Session
from ..models.presupuesto import (
    Presupuesto, PresupuestoIngreso, PresupuestoGasto,
    PresupuestoCesionAuxiliar, TipoReglaGasto,
)
from ..models.diario import DiarioApunte, EstadoApunte
from ..models.analitico import AnaliticoAjusteCoste
from .tasa_cesion import resolver_tasa, TASA_AUX_CTE, TASA_EXPR

FAMILIA_AMORTIZACIONES = 'Amortizaciones y ajustes'
FAMILIA_FINANCIERO = 'Gastos financieros'
FAMILIA_CESIONES = 'Cesiones a auxiliares'

# Prefijos de cuenta que clasifican automáticamente, independientemente de la familia
_PREFIJOS_AMORT = ('68',)
_PREFIJOS_FINANCIERO = ('66', '76')


def _par(ppto: float, base: float) -> dict:
    dev = round(ppto - base, 2)
    pct = (
        round((ppto - base) / abs(base) * 100, 2)
        if base != 0
        else (100.0 if ppto > 0 else (-100.0 if ppto < 0 else 0.0))
    )
    return {
        'ppto': round(ppto, 2),
        'base': round(base, 2),
        'desviacion': dev,
        'pct_desviacion': pct,
    }


def _margen(numerador_p: float, denom_p: float,
            numerador_b: float, denom_b: float) -> dict:
    """Devuelve margen en % para presupuesto y base, más la variación en puntos porcentuales."""
    ppto_pct = round(numerador_p / denom_p * 100, 2) if denom_p else 0.0
    base_pct = round(numerador_b / denom_b * 100, 2) if denom_b else 0.0
    return {
        'ppto_pct': ppto_pct,
        'base_pct': base_pct,
        'delta_pp': round(ppto_pct - base_pct, 2),
    }


def _es_amort(cuenta: str, familia: str) -> bool:
    return (
        any(cuenta.startswith(p) for p in _PREFIJOS_AMORT)
        or familia == FAMILIA_AMORTIZACIONES
    )


def _es_financiero(cuenta: str, familia: str) -> bool:
    return (
        any(cuenta.startswith(p) for p in _PREFIJOS_FINANCIERO)
        or familia == FAMILIA_FINANCIERO
    )


def _cesion_normalizada_base(db: Session, ejercicio: int, tasa: float = 0.40) -> tuple[float, float]:
    """
    Cesión normalizada del año base — MISMA SQL que rentabilidad_cliente para que
    los valores cuadren exactamente. Devuelve (cesion_normalizada, 0.0).
    No importa de analitico.py para evitar importación circular.
    """
    # Componente directo: WITH + FILTER idéntico a rentabilidad_cliente._aux_stat
    ces_direct = float(db.execute(_text("""
        WITH recibos_con_aux AS (
            SELECT r.id
            FROM recibos r
            WHERE r.ente IS NOT NULL
              AND r.id IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
              )
        )
        SELECT COALESCE(
            SUM(-CAST(f.importe AS FLOAT))
            FILTER (WHERE f.numero_cuenta LIKE '623%' AND f.recibo_id IN (SELECT id FROM recibos_con_aux)),
            0
        )
        FROM fact_resultado_analitico f
        WHERE f.ejercicio = :ej AND f.recibo_id IS NOT NULL
    """), {"ej": ejercicio}).scalar() or 0)

    # Componente estimado: GROUP BY tomador + round por cliente + filtro ing>=0 (misma aritmética que rentabilidad)
    _ces_rows = db.execute(_text("""
        WITH recibos_sin_cesion AS (
            SELECT r.id AS recibo_id
            FROM recibos r
            WHERE r.ente IS NOT NULL
              AND r.id IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
              )
              AND r.id NOT IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej
                    AND numero_cuenta LIKE '623%'
                    AND recibo_id IS NOT NULL
              )
        ),
        tomadores_con_ingreso_positivo AS (
            SELECT r.tomador
            FROM fact_resultado_analitico f
            JOIN recibos r ON f.recibo_id = r.id
            WHERE f.ejercicio = :ej AND f.tipo_cuenta = 'ingreso'
              AND r.tomador IS NOT NULL AND r.tomador != ''
            GROUP BY r.tomador
            HAVING COALESCE(SUM(CAST(f.importe AS FLOAT)), 0) >= 0
        ),
    """ + TASA_AUX_CTE + f"""
        SELECT
            rec.tomador,
            COALESCE(SUM(CAST(f.importe AS FLOAT) * {TASA_EXPR}), 0) AS cesion_est
        FROM fact_resultado_analitico f
        JOIN recibos rec ON f.recibo_id = rec.id
        JOIN recibos_sin_cesion rsc ON f.recibo_id = rsc.recibo_id
        JOIN tomadores_con_ingreso_positivo tip ON rec.tomador = tip.tomador
        LEFT JOIN tasa_aux ta ON ta.ente = rec.ente
        WHERE f.ejercicio = :ej
          AND f.tipo_cuenta = 'ingreso'
          AND rec.tomador IS NOT NULL
        GROUP BY rec.tomador
    """), {"ej": ejercicio, "tasa": tasa}).fetchall()
    ces_est = round(sum(round(float(r[1]), 2) for r in _ces_rows if r[0]), 2)

    ces_norm = round(float(ces_direct) + ces_est, 2)
    return ces_norm, 0.0


def pl_contable_ejercicio(db: Session, ejercicio: int) -> dict:
    """
    P&L contable real de un ejercicio, leído del diario. Única fuente de la columna
    "real/contable": la usan esta Cuenta de Resultados (año base) y el Dashboard
    ejecutivo del Modelo Analítico, para que ambas den exactamente lo mismo.
    """
    # Ingresos por compañía: cuentas 7*
    ing: dict[str, float] = {}
    for a in db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio,
        DiarioApunte.numero_cuenta.like('7%'),
        DiarioApunte.estado != EstadoApunte.EXCLUIDO,
    ).all():
        comp = a.compania or 'Sin compañía'
        ing[comp] = ing.get(comp, 0.0) + float((a.haber or 0) - (a.debe or 0))
    ing = {k: round(v, 2) for k, v in ing.items() if abs(v) > 0.01}

    # Gastos cuentas 6* (clasificación dual: cuenta + familia)
    gto: dict[str, float] = {}
    amort = 0.0
    financiero = 0.0
    for a in db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio,
        DiarioApunte.numero_cuenta.like('6%'),
        DiarioApunte.estado != EstadoApunte.EXCLUIDO,
    ).all():
        cuenta = (a.numero_cuenta or '').strip()
        fam    = (a.familia_gasto or 'Sin clasificar').strip()
        net    = float((a.debe or 0) - (a.haber or 0))

        # Impuesto: solo por cuenta (630), la familia puede ser variable
        if cuenta.startswith('630'):
            continue  # excluido del P&L: se calcula al 25%

        if _es_amort(cuenta, fam):
            amort += net
        elif _es_financiero(cuenta, fam):
            financiero += net
        else:
            if 'auxiliar' in fam.lower():
                fam = FAMILIA_CESIONES
            gto[fam] = gto.get(fam, 0.0) + net
    gto = {k: round(v, 2) for k, v in gto.items() if abs(v) > 0.01}

    # Desglose de cesiones por auxiliar: cuentas 623*, nombre en descripcion_cuenta
    ces_aux: dict[str, float] = {}
    for a in db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio,
        DiarioApunte.numero_cuenta.like('623%'),
        DiarioApunte.estado != EstadoApunte.EXCLUIDO,
    ).all():
        aux = (a.descripcion_cuenta or a.auxiliar or 'Sin auxiliar').strip()
        ces_aux[aux] = ces_aux.get(aux, 0.0) + float((a.debe or 0) - (a.haber or 0))

    total_ing = sum(ing.values())
    total_gto_op = round(sum(gto.values()), 2)
    return {
        'ingresos_por_compania': ing,
        'total_ingresos':        total_ing,
        'gastos_por_familia':    gto,
        'total_gastos_operativos': total_gto_op,
        'total_cesiones':        gto.get(FAMILIA_CESIONES, 0.0),
        'cesiones_por_auxiliar': ces_aux,
        'amortizaciones':        amort,
        'gastos_financieros':    financiero,
        'ebitda':                round(total_ing - total_gto_op, 2),
    }


def ajuste_coste_analitico(db: Session, ejercicio: int) -> tuple[float, dict[str, float]]:
    """
    Ajustes de coste del Modelo Analítico (AnaliticoAjusteCoste): coste de personal
    adscrito a un auxiliar que, en la vista NORMALIZADA, se sustituye por la cesión
    estimada de ese auxiliar (si no se quitara, se contaría dos veces). Devuelve el
    total anual y su reparto por familia de gasto, proporcional al gasto real de las
    cuentas de cada ajuste (igual que el analítico reduce su pool).
    """
    ajustes = db.query(AnaliticoAjusteCoste).filter(
        AnaliticoAjusteCoste.ejercicio == ejercicio,
        AnaliticoAjusteCoste.activo == True,
    ).all()
    total = 0.0
    por_familia: dict[str, float] = {}
    for aj in ajustes:
        importe = float(aj.importe_mensual) * 12
        total += importe
        base_fam: dict[str, float] = {}
        for fam, net in db.query(DiarioApunte.familia_gasto, DiarioApunte.debe - DiarioApunte.haber).filter(
            DiarioApunte.ejercicio == ejercicio,
            DiarioApunte.numero_cuenta.like(f"{aj.numero_cuenta}%"),
            DiarioApunte.estado != EstadoApunte.EXCLUIDO,
        ).all():
            fam = (fam or 'Sin clasificar').strip()
            base_fam[fam] = base_fam.get(fam, 0.0) + float(net or 0)
        pool = sum(v for v in base_fam.values() if v > 0)
        for fam, v in base_fam.items():
            if v > 0 and pool > 0:
                por_familia[fam] = por_familia.get(fam, 0.0) + importe * v / pool
    return round(total, 2), {k: round(v, 2) for k, v in por_familia.items()}


def calcular_cuenta_resultados(db: Session, presupuesto: Presupuesto, tasa_cesion_estimada: float | None = None) -> dict:
    ejercicio_ppto = presupuesto.ejercicio
    ejercicio_base = presupuesto.ejercicio_base
    # Sin informar: tasa real del año base, la misma que usa el Modelo Analítico.
    tasa_cesion_estimada = resolver_tasa(db, ejercicio_base, tasa_cesion_estimada)
    base_pl = pl_contable_ejercicio(db, ejercicio_base)

    # ─── 2026 Ingresos por compañía ──────────────────────────────────────────
    ing_ppto: dict[str, float] = {}
    for l in db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id,
    ).all():
        comp = l.compania or 'Sin compañía'
        ing_ppto[comp] = ing_ppto.get(comp, 0.0) + float(l.total_anual or 0)
    total_ing_ppto = sum(ing_ppto.values())

    # ─── Año base: ingresos por compañía cuentas 7* ──────────────────────────
    ing_base = base_pl['ingresos_por_compania']
    total_ing_base = base_pl['total_ingresos']

    todas_companias = sorted(set(list(ing_ppto.keys()) + list(ing_base.keys())))
    ingresos_por_compania = [
        {
            'concepto': c,
            **_par(ing_ppto.get(c, 0.0), ing_base.get(c, 0.0)),
            'pct_ppto': round(ing_ppto.get(c, 0.0) / total_ing_ppto * 100, 1) if total_ing_ppto else 0.0,
            'pct_base': round(ing_base.get(c, 0.0) / total_ing_base * 100, 1) if total_ing_base else 0.0,
        }
        for c in todas_companias
    ]

    # ─── 2026 Gastos operativos por familia ──────────────────────────────────
    gto_ppto: dict[str, float] = {}
    amort_ppto = 0.0
    financiero_ppto = 0.0

    for l in db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto.id,
        PresupuestoGasto.tipo_regla != TipoReglaGasto.EXCLUIR,
    ).all():
        fam = l.familia_gasto or 'Otros gastos'
        cuenta = (l.numero_cuenta or '').strip()
        importe = float(l.total_anual or 0)
        if 'auxiliar' in fam.lower():
            continue
        if _es_amort(cuenta, fam):
            amort_ppto += importe
        elif _es_financiero(cuenta, fam):
            financiero_ppto += importe
        else:
            gto_ppto[fam] = gto_ppto.get(fam, 0.0) + importe

    cesiones = db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto.id,
    ).all()
    cesiones_aux_ppto: dict[str, float] = {}
    if cesiones:
        gto_ppto[FAMILIA_CESIONES] = round(
            sum(float(c.gasto_comision_total or 0) for c in cesiones), 2
        )
        for c in cesiones:
            aux = c.auxiliar or 'Sin auxiliar'
            cesiones_aux_ppto[aux] = cesiones_aux_ppto.get(aux, 0.0) + float(c.gasto_comision_total or 0)

    amort_ppto = round(amort_ppto, 2)
    financiero_ppto = round(financiero_ppto, 2)
    total_gto_op_ppto = round(sum(gto_ppto.values()), 2)

    # ─── Año base: gastos cuentas 6* (clasificación dual: cuenta + familia) ──
    gto_base = base_pl['gastos_por_familia']
    amort_base = base_pl['amortizaciones']
    financiero_base = base_pl['gastos_financieros']
    total_gto_op_base = base_pl['total_gastos_operativos']
    cesiones_aux_base = base_pl['cesiones_por_auxiliar']

    total_cesiones_ppto = gto_ppto.get(FAMILIA_CESIONES, 0.0)
    total_cesiones_base = gto_base.get(FAMILIA_CESIONES, 0.0)
    todos_auxiliares = sorted(set(list(cesiones_aux_ppto.keys()) + list(cesiones_aux_base.keys())))
    cesiones_por_auxiliar = [
        {
            'auxiliar': aux,
            'ppto': round(cesiones_aux_ppto.get(aux, 0.0), 2),
            'base': round(cesiones_aux_base.get(aux, 0.0), 2),
            'pct_ppto': round(cesiones_aux_ppto.get(aux, 0.0) / total_cesiones_ppto * 100, 1) if total_cesiones_ppto else 0.0,
            'pct_base': round(cesiones_aux_base.get(aux, 0.0) / total_cesiones_base * 100, 1) if total_cesiones_base else 0.0,
        }
        for aux in todos_auxiliares
    ]

    todas_familias = sorted(set(list(gto_ppto.keys()) + list(gto_base.keys())))
    gastos_operativos = [
        {
            'concepto': f,
            **_par(gto_ppto.get(f, 0.0), gto_base.get(f, 0.0)),
            'pct_ppto': round(gto_ppto.get(f, 0.0) / total_gto_op_ppto * 100, 1) if total_gto_op_ppto else 0.0,
            'pct_base': round(gto_base.get(f, 0.0) / total_gto_op_base * 100, 1) if total_gto_op_base else 0.0,
        }
        for f in todas_familias
    ]

    # ─── Cesión normalizada del año base ────────────────────────────────────
    ces_norm_base, ces_ant_base = _cesion_normalizada_base(db, ejercicio_base, tasa_cesion_estimada)
    # Diferencia respecto a la cesión contable del año base
    delta_ces_norm = total_cesiones_base - ces_norm_base   # positivo si contable > normalizada
    # Ajustes de coste del analítico: en la vista normalizada ese coste de personal ya
    # está dentro de la cesión estimada del auxiliar, así que sale de gastos operativos.
    # Misma fórmula que analitico.dashboard_ejecutivo: los dos EBITDA normalizados cuadran.
    aj_total_base, aj_familia_base = ajuste_coste_analitico(db, ejercicio_base)
    ebitda_norm_base = round(total_ing_base - total_gto_op_base + aj_total_base + delta_ces_norm, 2)
    gastos_familia_norm = {
        f: round(v - aj_familia_base.get(f, 0.0), 2) for f, v in gto_base.items()
    }
    gastos_familia_norm[FAMILIA_CESIONES] = round(ces_norm_base, 2)
    total_gto_op_norm = round(total_gto_op_base - aj_total_base - delta_ces_norm, 2)

    # ─── KPIs ────────────────────────────────────────────────────────────────
    ebitda_ppto = total_ing_ppto  - total_gto_op_ppto
    ebitda_base = total_ing_base  - total_gto_op_base

    ebit_ppto = ebitda_ppto - amort_ppto
    ebit_base = ebitda_base - amort_base

    bai_ppto  = ebit_ppto - financiero_ppto
    bai_base  = ebit_base - financiero_base

    # Impuesto: 25% del BAI positivo — igual para presupuesto y año base
    impuesto_ppto = round(max(bai_ppto, 0.0) * 0.25, 2)
    impuesto_base = round(max(bai_base, 0.0) * 0.25, 2)

    resultado_ppto = round(bai_ppto - impuesto_ppto, 2)
    resultado_base = round(bai_base - impuesto_base, 2)

    # Ratio gastos totales (operativos + amort + financieros) sobre ingresos
    gto_total_ppto = total_gto_op_ppto + amort_ppto + financiero_ppto
    gto_total_base = total_gto_op_base + amort_base + financiero_base

    return {
        'ejercicio_ppto': ejercicio_ppto,
        'ejercicio_base': ejercicio_base,

        # Detalle
        'cesiones_por_auxiliar':  cesiones_por_auxiliar,
        'ingresos_por_compania': ingresos_por_compania,
        'total_ingresos':         _par(total_ing_ppto, total_ing_base),
        'gastos_operativos':      gastos_operativos,
        'total_gastos_operativos': _par(total_gto_op_ppto, total_gto_op_base),

        # P&L
        'ebitda':            _par(ebitda_ppto,     ebitda_base),
        'amortizaciones':    _par(amort_ppto,       amort_base),
        'ebit':              _par(ebit_ppto,        ebit_base),
        'gastos_financieros': _par(financiero_ppto, financiero_base),
        'bai':               _par(bai_ppto,         bai_base),
        'impuesto':          _par(impuesto_ppto,    impuesto_base),
        'resultado':         _par(resultado_ppto,   resultado_base),

        # Márgenes (%)
        'margen_ebitda':     _margen(ebitda_ppto,    total_ing_ppto, ebitda_base,    total_ing_base),
        'margen_operativo':  _margen(ebit_ppto,      total_ing_ppto, ebit_base,      total_ing_base),
        'margen_neto':       _margen(resultado_ppto, total_ing_ppto, resultado_base, total_ing_base),
        'ratio_gastos':      _margen(gto_total_ppto, total_ing_ppto, gto_total_base, total_ing_base),

        # Columna normalizada (cesión ajustada por desfase temporal)
        'normalizado_base': {
            'cesion_normalizada':     round(ces_norm_base, 2),
            'cesion_años_anteriores': round(ces_ant_base, 2),
            'cesion_contable_base':   round(total_cesiones_base, 2),
            'ajuste_coste':           aj_total_base,
            'gastos_por_familia':     gastos_familia_norm,
            'total_gastos_operativos': total_gto_op_norm,
            'ebitda_normalizado':     ebitda_norm_base,
            'margen_ebitda_norm_pct': round(ebitda_norm_base / total_ing_base * 100, 2) if total_ing_base else 0.0,
        },
    }
