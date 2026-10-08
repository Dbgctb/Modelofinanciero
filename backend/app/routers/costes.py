"""
Router Costes — RF-COS-01 a RF-COS-05.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.costes import (
    LineaCoste, TipoCoste, TratamientoCoste, DriverReparto,
    MotivoExclusionCoste, EstadoCoste, CLASIFICACION_POR_FAMILIA,
)
from ..models.real import DesvIngreso
from ..services.costes import clasificar_automatico, imputar_costes, resumen_costes, kpis_costes
from pydantic import BaseModel
from decimal import Decimal
import uuid

router = APIRouter(prefix="/costes", tags=["costes"])


class ClasificacionIn(BaseModel):
    tipo_coste: Optional[TipoCoste] = None
    tratamiento: Optional[TratamientoCoste] = None
    driver: Optional[DriverReparto] = None
    motivo_exclusion: Optional[MotivoExclusionCoste] = None
    reparto_manual: Optional[dict] = None
    notas: Optional[str] = None


# ── Clasificación ────────────────────────────────────────────────────────────

@router.post("/{presupuesto_id}/clasificar")
def clasificar_periodo(
    presupuesto_id: str,
    mes: int = Query(..., ge=1, le=12),
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    n = clasificar_automatico(db, presupuesto_id, mes, ejercicio)
    return {"clasificadas": n}


@router.get("/{presupuesto_id}/lineas")
def listar_lineas(
    presupuesto_id: str,
    mes: Optional[int] = Query(None, ge=1, le=12),
    familia: Optional[str] = None,
    estado: Optional[EstadoCoste] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(LineaCoste).filter(LineaCoste.presupuesto_id == presupuesto_id)
    if mes is not None:
        q = q.filter(LineaCoste.mes == mes)
    if familia:
        q = q.filter(LineaCoste.familia_gasto == familia)
    if estado:
        q = q.filter(LineaCoste.estado == estado)
    lineas = q.order_by(LineaCoste.familia_gasto, LineaCoste.numero_cuenta).all()
    return [
        {
            "id": str(linea.id),
            "mes": linea.mes,
            "numero_cuenta": linea.numero_cuenta,
            "descripcion_cuenta": linea.descripcion_cuenta,
            "familia_gasto": linea.familia_gasto,
            "importe_real": float(linea.importe_real),
            "importe_presupuesto": float(linea.importe_presupuesto),
            "tipo_coste": linea.tipo_coste.value if linea.tipo_coste else None,
            "tratamiento": linea.tratamiento.value if linea.tratamiento else None,
            "driver": linea.driver.value if linea.driver else None,
            "motivo_exclusion": linea.motivo_exclusion.value if linea.motivo_exclusion else None,
            "clasificacion_automatica": linea.clasificacion_automatica,
            "imputacion": linea.imputacion,
            "estado": linea.estado.value if linea.estado else None,
            "notas": linea.notas,
        }
        for linea in lineas
    ]


@router.patch("/{presupuesto_id}/lineas/{linea_id}")
def actualizar_clasificacion(
    presupuesto_id: str,
    linea_id: str,
    body: ClasificacionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    linea = db.query(LineaCoste).filter(
        LineaCoste.id == linea_id,
        LineaCoste.presupuesto_id == presupuesto_id,
    ).first()
    if not linea:
        raise HTTPException(404, "Línea no encontrada")

    linea.clasificacion_automatica = False
    if body.tipo_coste is not None:
        linea.tipo_coste = body.tipo_coste
    if body.tratamiento is not None:
        linea.tratamiento = body.tratamiento
        if body.tratamiento == TratamientoCoste.EXCLUIDO:
            linea.estado = EstadoCoste.EXCLUIDO
        else:
            linea.estado = EstadoCoste.CLASIFICADO
    if body.driver is not None:
        linea.driver = body.driver
    if body.motivo_exclusion is not None:
        linea.motivo_exclusion = body.motivo_exclusion
    if body.reparto_manual is not None:
        linea.reparto_manual = body.reparto_manual
    if body.notas is not None:
        linea.notas = body.notas

    db.commit()
    db.refresh(linea)
    return {"ok": True, "estado": linea.estado.value}


# ── Imputación ───────────────────────────────────────────────────────────────

@router.post("/{presupuesto_id}/imputar")
def imputar(
    presupuesto_id: str,
    meses: List[int] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    n = imputar_costes(db, presupuesto_id, meses)
    return {"imputadas": n}


# ── Comparativa real vs presupuesto ─────────────────────────────────────────

@router.get("/{presupuesto_id}/comparativa")
def comparativa(
    presupuesto_id: str,
    meses: List[int] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return resumen_costes(db, presupuesto_id, meses)


# ── KPIs de costes ───────────────────────────────────────────────────────────

@router.get("/{presupuesto_id}/kpis")
def kpis(
    presupuesto_id: str,
    meses: List[int] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ingreso neto = ingresos reales - cesiones (desde DesvIngreso)
    ing_rows = db.query(DesvIngreso).filter(
        DesvIngreso.presupuesto_id == presupuesto_id,
        DesvIngreso.mes.in_(meses),
    ).all()
    ing_neto = sum(float(r.real) for r in ing_rows)
    return kpis_costes(db, presupuesto_id, meses, ing_neto)


# ── Familias disponibles ─────────────────────────────────────────────────────

@router.get("/familias-clasificacion")
def familias_clasificacion(current_user: User = Depends(get_current_user)):
    return [
        {
            "familia": fam,
            "tipo_coste": cfg["tipo"].value,
            "tratamiento": cfg["tratamiento"].value,
            "driver": cfg["driver"].value,
        }
        for fam, cfg in CLASIFICACION_POR_FAMILIA.items()
    ]
