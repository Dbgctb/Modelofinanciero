"""
Servicio de seguimiento real y comparativa. RF-REAL-01 a RF-DESV-07.
"""
from decimal import Decimal
from typing import List, Dict
from sqlalchemy.orm import Session
from ..models.presupuesto import Presupuesto, PresupuestoIngreso, PresupuestoGasto
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..models.real import MesReal, DesvIngreso, DesvGasto, EstadoMesReal
from ..models.carga import CargaContable


def calcular_desviaciones_mes(db: Session, presupuesto: Presupuesto, mes: int):
    """
    RF-DESV-01 a RF-DESV-04: calcula desviaciones real vs presupuesto para un mes cerrado.
    Solo compara ingresos y gastos, nunca tesorería.
    """
    # Eliminar desviaciones previas del mes
    db.query(DesvIngreso).filter(
        DesvIngreso.presupuesto_id == presupuesto.id,
        DesvIngreso.mes == mes,
    ).delete()
    db.query(DesvGasto).filter(
        DesvGasto.presupuesto_id == presupuesto.id,
        DesvGasto.mes == mes,
    ).delete()

    _calcular_desv_ingresos(db, presupuesto, mes)
    _calcular_desv_gastos(db, presupuesto, mes)
    db.commit()


def _calcular_desv_ingresos(db: Session, presupuesto: Presupuesto, mes: int):
    """Agrupa real de ingresos y compara con presupuesto por dimensión."""
    apuntes = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == presupuesto.ejercicio,
        DiarioApunte.mes == mes,
        DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
        DiarioApunte.estado == EstadoApunte.CORRECTO,
    ).all()

    real_por_dim: Dict[tuple, float] = {}
    for ap in apuntes:
        clave = (
            ap.compania or 'Sin compañía',
            ap.ramo or 'Sin ramo',
            ap.auxiliar or 'Sin auxiliar',
            ap.tipo_negocio or 'sin_clasificar',
        )
        importe = float(ap.haber - ap.debe)
        real_por_dim[clave] = real_por_dim.get(clave, 0.0) + importe

    # Presupuesto de ingresos para este mes (índice mes-1)
    lineas_presup = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id,
    ).all()
    presup_por_dim: Dict[tuple, float] = {}
    for l in lineas_presup:
        clave = (l.compania or '', l.ramo or '', l.auxiliar or '', l.tipo_negocio or '')
        importe_mes = (l.importes_mensuales or [])[mes - 1] if l.importes_mensuales and len(l.importes_mensuales) >= mes else 0
        presup_por_dim[clave] = presup_por_dim.get(clave, 0.0) + importe_mes

    todas_claves = set(real_por_dim.keys()) | set(presup_por_dim.keys())
    for clave in todas_claves:
        real_v = real_por_dim.get(clave, 0.0)
        presup_v = presup_por_dim.get(clave, 0.0)
        desv_abs = round(real_v - presup_v, 2)
        desv_pct = round((desv_abs / presup_v) * 100, 4) if presup_v else 0.0
        db.add(DesvIngreso(
            presupuesto_id=presupuesto.id,
            mes=mes,
            compania=clave[0], ramo=clave[1], auxiliar=clave[2], tipo_negocio=clave[3],
            real=real_v, presupuesto=presup_v,
            desviacion_abs=desv_abs, desviacion_pct=desv_pct,
            es_favorable=desv_abs >= 0,  # ingresos: real > presup es favorable
        ))


def _calcular_desv_gastos(db: Session, presupuesto: Presupuesto, mes: int):
    """Agrupa real de gastos y compara con presupuesto por cuenta y familia."""
    apuntes = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == presupuesto.ejercicio,
        DiarioApunte.mes == mes,
        DiarioApunte.tipo_cuenta == TipoCuenta.GASTO,
        DiarioApunte.estado == EstadoApunte.CORRECTO,
    ).all()

    real_por_cuenta: Dict[str, Dict] = {}
    for ap in apuntes:
        cta = ap.numero_cuenta or 'SIN_CUENTA'
        if cta not in real_por_cuenta:
            real_por_cuenta[cta] = {'familia': ap.familia_gasto or '', 'real': 0.0}
        real_por_cuenta[cta]['real'] += float(ap.debe - ap.haber)

    lineas_presup = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto.id,
    ).all()
    presup_por_cuenta: Dict[str, Dict] = {}
    for l in lineas_presup:
        if not l.numero_cuenta:
            continue
        importes_ef = [
            (l.importes_manuales[i] if l.importes_manuales and l.importes_manuales[i] is not None
             else (l.importes_mensuales[i] if l.importes_mensuales and i < len(l.importes_mensuales) else 0))
            for i in range(12)
        ]
        importe_mes = importes_ef[mes - 1] if len(importes_ef) >= mes else 0
        presup_por_cuenta[l.numero_cuenta] = {'familia': l.familia_gasto, 'presup': importe_mes}

    todas = set(real_por_cuenta.keys()) | set(presup_por_cuenta.keys())
    for cta in todas:
        real_v = real_por_cuenta.get(cta, {}).get('real', 0.0)
        presup_v = presup_por_cuenta.get(cta, {}).get('presup', 0.0)
        familia = (real_por_cuenta.get(cta) or presup_por_cuenta.get(cta) or {}).get('familia', '')
        desv_abs = round(real_v - presup_v, 2)
        desv_pct = round((desv_abs / presup_v) * 100, 4) if presup_v else 0.0
        db.add(DesvGasto(
            presupuesto_id=presupuesto.id,
            mes=mes, numero_cuenta=cta, familia_gasto=familia,
            real=real_v, presupuesto=presup_v,
            desviacion_abs=desv_abs, desviacion_pct=desv_pct,
            es_favorable=desv_abs <= 0,  # gastos: real < presup es favorable
        ))


def resumen_acumulado(db: Session, presupuesto_id: str, hasta_mes: int) -> Dict:
    """RF-DESV-05: acumulado de real vs presupuesto hasta el mes indicado."""
    meses = list(range(1, hasta_mes + 1))

    ing_real = sum(
        float(r.real) for r in db.query(DesvIngreso)
        .filter(DesvIngreso.presupuesto_id == presupuesto_id, DesvIngreso.mes.in_(meses)).all()
    )
    ing_presup = sum(
        float(r.presupuesto) for r in db.query(DesvIngreso)
        .filter(DesvIngreso.presupuesto_id == presupuesto_id, DesvIngreso.mes.in_(meses)).all()
    )
    gas_real = sum(
        float(r.real) for r in db.query(DesvGasto)
        .filter(DesvGasto.presupuesto_id == presupuesto_id, DesvGasto.mes.in_(meses)).all()
    )
    gas_presup = sum(
        float(r.presupuesto) for r in db.query(DesvGasto)
        .filter(DesvGasto.presupuesto_id == presupuesto_id, DesvGasto.mes.in_(meses)).all()
    )

    def _desv(real, presup):
        abs_v = round(real - presup, 2)
        pct_v = round((abs_v / presup) * 100, 2) if presup else 0.0
        return abs_v, pct_v

    ing_abs, ing_pct = _desv(ing_real, ing_presup)
    gas_abs, gas_pct = _desv(gas_real, gas_presup)
    ebitda_real = ing_real - gas_real
    ebitda_presup = ing_presup - gas_presup
    ebitda_abs, ebitda_pct = _desv(ebitda_real, ebitda_presup)

    return {
        "hasta_mes": hasta_mes,
        "ingresos": {"real": round(ing_real, 2), "presupuesto": round(ing_presup, 2),
                     "desv_abs": ing_abs, "desv_pct": ing_pct, "favorable": ing_abs >= 0},
        "gastos": {"real": round(gas_real, 2), "presupuesto": round(gas_presup, 2),
                   "desv_abs": gas_abs, "desv_pct": gas_pct, "favorable": gas_abs <= 0},
        "ebitda": {"real": round(ebitda_real, 2), "presupuesto": round(ebitda_presup, 2),
                   "desv_abs": ebitda_abs, "desv_pct": ebitda_pct, "favorable": ebitda_abs >= 0},
    }
