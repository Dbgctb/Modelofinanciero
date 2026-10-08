from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.presupuesto import Presupuesto
from ..models.real import MesReal, DesvIngreso, DesvGasto, EstadoMesReal
from ..models.carga import CargaContable, EstadoCarga
from ..services.seguimiento_real import calcular_desviaciones_mes, resumen_acumulado

router = APIRouter(prefix="/real", tags=["Seguimiento real"])

MESES_LABELS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _get_presupuesto(db: Session, pid: UUID) -> Presupuesto:
    p = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    return p


@router.get("/{presupuesto_id}/meses")
def estado_meses(presupuesto_id: UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """RF-REAL-06: devuelve el estado de los 12 meses del ejercicio."""
    p = _get_presupuesto(db, presupuesto_id)
    meses_db = {
        m.mes: m for m in db.query(MesReal).filter(MesReal.presupuesto_id == presupuesto_id).all()
    }
    resultado = []
    for i in range(1, 13):
        mes_obj = meses_db.get(i)
        resultado.append({
            "mes": i,
            "label": MESES_LABELS[i - 1],
            "estado": mes_obj.estado.value if mes_obj else EstadoMesReal.NO_CARGADO.value,
            "cerrado_at": mes_obj.cerrado_at.isoformat() if mes_obj and mes_obj.cerrado_at else None,
        })
    return resultado


@router.post("/{presupuesto_id}/meses/{mes}/vincular-carga")
def vincular_carga_mes(
    presupuesto_id: UUID,
    mes: int,
    carga_id: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-REAL-01: vincula una carga mensual real al mes del presupuesto."""
    if not (1 <= mes <= 12):
        raise HTTPException(400, "Mes inválido")

    carga = db.query(CargaContable).filter(CargaContable.id == carga_id).first()
    if not carga:
        raise HTTPException(404, "Carga no encontrada")

    mes_real = db.query(MesReal).filter(
        MesReal.presupuesto_id == presupuesto_id, MesReal.mes == mes
    ).first()
    if not mes_real:
        p = _get_presupuesto(db, presupuesto_id)
        mes_real = MesReal(presupuesto_id=presupuesto_id, ejercicio=p.ejercicio, mes=mes)
        db.add(mes_real)

    mes_real.carga_id = carga_id
    mes_real.estado = (
        EstadoMesReal.CON_INCIDENCIAS if carga.registros_con_incidencia > 0
        else EstadoMesReal.CARGADO
    )
    db.commit()
    return {"mensaje": f"Carga vinculada al mes {mes}"}


@router.post("/{presupuesto_id}/meses/{mes}/cerrar")
def cerrar_mes(
    presupuesto_id: UUID,
    mes: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-REAL-05: cierra un mes real y calcula desviaciones."""
    mes_real = db.query(MesReal).filter(
        MesReal.presupuesto_id == presupuesto_id, MesReal.mes == mes
    ).first()
    if not mes_real:
        raise HTTPException(400, "El mes no tiene carga vinculada")
    if mes_real.estado == EstadoMesReal.CON_INCIDENCIAS:
        raise HTTPException(409, "Hay incidencias críticas pendientes en este mes")

    p = _get_presupuesto(db, presupuesto_id)
    calcular_desviaciones_mes(db, p, mes)

    mes_real.estado = EstadoMesReal.CERRADO
    mes_real.cerrado_por_id = current_user.id
    mes_real.cerrado_at = datetime.now(timezone.utc)
    db.commit()
    return {"mensaje": f"Mes {mes} cerrado. Desviaciones calculadas."}


@router.post("/{presupuesto_id}/meses/{mes}/reabrir")
def reabrir_mes(
    presupuesto_id: UUID,
    mes: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    mes_real = db.query(MesReal).filter(
        MesReal.presupuesto_id == presupuesto_id, MesReal.mes == mes
    ).first()
    if not mes_real:
        raise HTTPException(404, "Mes no encontrado")
    mes_real.estado = EstadoMesReal.REABIERTO
    mes_real.cerrado_at = None
    db.commit()
    return {"mensaje": f"Mes {mes} reabierto"}


@router.get("/{presupuesto_id}/comparativa/acumulado")
def comparativa_acumulada(
    presupuesto_id: UUID,
    hasta_mes: int = 12,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """RF-DESV-05: comparativa acumulada hasta el mes indicado."""
    return resumen_acumulado(db, str(presupuesto_id), hasta_mes)


@router.get("/{presupuesto_id}/comparativa/mensual")
def comparativa_mensual(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """RF-DESV-05/06: comparativa mes a mes de ingresos y gastos."""
    resultado = []
    for mes in range(1, 13):
        ing = db.query(DesvIngreso).filter(
            DesvIngreso.presupuesto_id == presupuesto_id, DesvIngreso.mes == mes
        ).all()
        gas = db.query(DesvGasto).filter(
            DesvGasto.presupuesto_id == presupuesto_id, DesvGasto.mes == mes
        ).all()

        ing_real = round(sum(float(r.real) for r in ing), 2)
        ing_presup = round(sum(float(r.presupuesto) for r in ing), 2)
        gas_real = round(sum(float(r.real) for r in gas), 2)
        gas_presup = round(sum(float(r.presupuesto) for r in gas), 2)
        ing_desv = round(ing_real - ing_presup, 2)
        gas_desv = round(gas_real - gas_presup, 2)

        resultado.append({
            "mes": mes,
            "label": MESES_LABELS[mes - 1],
            "tiene_datos": len(ing) > 0 or len(gas) > 0,
            "ingresos": {"real": ing_real, "presupuesto": ing_presup, "desv_abs": ing_desv,
                         "desv_pct": round((ing_desv / ing_presup * 100), 2) if ing_presup else 0,
                         "favorable": ing_desv >= 0},
            "gastos": {"real": gas_real, "presupuesto": gas_presup, "desv_abs": gas_desv,
                       "desv_pct": round((gas_desv / gas_presup * 100), 2) if gas_presup else 0,
                       "favorable": gas_desv <= 0},
            "ebitda_real": round(ing_real - gas_real, 2),
            "ebitda_presup": round(ing_presup - gas_presup, 2),
        })
    return resultado


@router.get("/{presupuesto_id}/comparativa/ingresos-detalle")
def detalle_ingresos(
    presupuesto_id: UUID,
    mes: Optional[int] = None,
    compania: Optional[str] = None,
    ramo: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """RF-DESV-06: desviaciones de ingresos con filtros."""
    q = db.query(DesvIngreso).filter(DesvIngreso.presupuesto_id == presupuesto_id)
    if mes: q = q.filter(DesvIngreso.mes == mes)
    if compania: q = q.filter(DesvIngreso.compania == compania)
    if ramo: q = q.filter(DesvIngreso.ramo == ramo)
    rows = q.order_by(DesvIngreso.mes, DesvIngreso.compania).all()
    return [{"mes": r.mes, "compania": r.compania, "ramo": r.ramo, "auxiliar": r.auxiliar,
             "tipo_negocio": r.tipo_negocio, "real": float(r.real), "presupuesto": float(r.presupuesto),
             "desv_abs": float(r.desviacion_abs), "desv_pct": float(r.desviacion_pct),
             "favorable": r.es_favorable} for r in rows]


@router.get("/{presupuesto_id}/comparativa/gastos-detalle")
def detalle_gastos(
    presupuesto_id: UUID,
    mes: Optional[int] = None,
    familia: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """RF-DESV-06: desviaciones de gastos con filtros."""
    q = db.query(DesvGasto).filter(DesvGasto.presupuesto_id == presupuesto_id)
    if mes: q = q.filter(DesvGasto.mes == mes)
    if familia: q = q.filter(DesvGasto.familia_gasto == familia)
    rows = q.order_by(DesvGasto.mes, DesvGasto.familia_gasto).all()
    return [{"mes": r.mes, "numero_cuenta": r.numero_cuenta, "familia_gasto": r.familia_gasto,
             "real": float(r.real), "presupuesto": float(r.presupuesto),
             "desv_abs": float(r.desviacion_abs), "desv_pct": float(r.desviacion_pct),
             "favorable": r.es_favorable} for r in rows]
