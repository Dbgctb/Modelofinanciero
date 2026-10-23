"""
Router Costes — RF-COS-01 a RF-COS-05.

Organizado por ejercicio (año), no por presupuesto -- funciona con solo
tener diario real cargado para ese año, sin necesitar ningún presupuesto
creado (ver services/costes.py).
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
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..services.costes import (
    clasificar_automatico, imputar_costes, resumen_costes, kpis_costes, generar_lineas_coste,
)
from pydantic import BaseModel

router = APIRouter(prefix="/costes", tags=["costes"])


class ClasificacionIn(BaseModel):
    tipo_coste: Optional[TipoCoste] = None
    tratamiento: Optional[TratamientoCoste] = None
    driver: Optional[DriverReparto] = None
    motivo_exclusion: Optional[MotivoExclusionCoste] = None
    reparto_manual: Optional[dict] = None
    notas: Optional[str] = None


# ── Clasificación ────────────────────────────────────────────────────────────

@router.post("/{ejercicio}/clasificar")
def clasificar_periodo(
    ejercicio: int,
    mes: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    try:
        generar_lineas_coste(db, ejercicio, mes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    n = clasificar_automatico(db, ejercicio, mes)
    return {"clasificadas": n}


@router.get("/{ejercicio}/lineas")
def listar_lineas(
    ejercicio: int,
    mes: Optional[int] = Query(None, ge=1, le=12),
    familia: Optional[str] = None,
    estado: Optional[EstadoCoste] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(LineaCoste).filter(LineaCoste.ejercicio == ejercicio)
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


@router.patch("/{ejercicio}/lineas/{linea_id}")
def actualizar_clasificacion(
    ejercicio: int,
    linea_id: str,
    body: ClasificacionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    linea = db.query(LineaCoste).filter(
        LineaCoste.id == linea_id,
        LineaCoste.ejercicio == ejercicio,
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

@router.post("/{ejercicio}/imputar")
def imputar(
    ejercicio: int,
    meses: List[int] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    n = imputar_costes(db, ejercicio, meses)
    return {"imputadas": n}


# ── Comparativa real vs presupuesto ─────────────────────────────────────────

@router.get("/{ejercicio}/comparativa")
def comparativa(
    ejercicio: int,
    meses: List[int] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return resumen_costes(db, ejercicio, meses)


# ── KPIs de costes ───────────────────────────────────────────────────────────

@router.get("/{ejercicio}/kpis")
def kpis(
    ejercicio: int,
    meses: List[int] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ingreso neto real, directamente del diario (sin depender de presupuesto)
    apuntes = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio,
        DiarioApunte.mes.in_(meses),
        DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
        DiarioApunte.estado == EstadoApunte.CORRECTO,
    ).all()
    ing_neto = sum(float(ap.haber - ap.debe) for ap in apuntes)
    return kpis_costes(db, ejercicio, meses, ing_neto)


# ── Años disponibles (con diario de gastos cargado) ──────────────────────────

@router.get("/anyos-disponibles")
def anyos_disponibles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import distinct
    anyos = db.query(distinct(DiarioApunte.ejercicio)).filter(
        DiarioApunte.tipo_cuenta == TipoCuenta.GASTO,
        DiarioApunte.estado == EstadoApunte.CORRECTO,
    ).order_by(DiarioApunte.ejercicio.desc()).all()
    return [a[0] for a in anyos]


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
