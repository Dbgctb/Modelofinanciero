"""
Router KPIs — RF-KPI-01 a RF-KPI-04.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.presupuesto import Presupuesto
from ..models.kpi import UmbralKPI, ResultadoKPI, SemaforoColor
from ..services.kpis import calcular_kpis, alertas_gestion
from pydantic import BaseModel
from decimal import Decimal

router = APIRouter(prefix="/kpis", tags=["kpis"])


class UmbralIn(BaseModel):
    kpi_codigo: str
    umbral_verde: float
    umbral_amarillo: float


class UmbralOut(BaseModel):
    kpi_codigo: str
    umbral_verde: float
    umbral_amarillo: float

    class Config:
        from_attributes = True


def _get_presupuesto(presupuesto_id: str, db: Session) -> Presupuesto:
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    return p


@router.post("/{presupuesto_id}/calcular")
def calcular(
    presupuesto_id: str,
    hasta_mes: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    presupuesto = _get_presupuesto(presupuesto_id, db)
    resultado = calcular_kpis(db, presupuesto, hasta_mes)
    return {"calculados": len(resultado), "kpis": resultado}


@router.get("/{presupuesto_id}/resultados")
def obtener_resultados(
    presupuesto_id: str,
    codigo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ResultadoKPI).filter(ResultadoKPI.presupuesto_id == presupuesto_id)
    if codigo:
        q = q.filter(ResultadoKPI.kpi_codigo == codigo)
    rows = q.order_by(ResultadoKPI.kpi_codigo, ResultadoKPI.dimension).all()
    return [
        {
            "codigo": r.kpi_codigo,
            "nombre": r.kpi_nombre,
            "valor": float(r.valor) if r.valor is not None else None,
            "semaforo": r.semaforo.value if r.semaforo else None,
            "dimension": r.dimension,
            "mes": r.mes,
            "informativo": r.informativo,
        }
        for r in rows
    ]


@router.get("/{presupuesto_id}/alertas")
def obtener_alertas(
    presupuesto_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(ResultadoKPI).filter(
        ResultadoKPI.presupuesto_id == presupuesto_id,
        ResultadoKPI.semaforo.in_([SemaforoColor.ROJO, SemaforoColor.AMARILLO]),
    ).all()
    kpis_dict = [
        {
            "codigo": r.kpi_codigo,
            "valor": float(r.valor) if r.valor is not None else None,
            "semaforo": r.semaforo.value,
        }
        for r in rows
    ]
    return alertas_gestion(kpis_dict)


# ── Umbrales configurables ──────────────────────────────────────────────────

@router.get("/umbrales", response_model=List[UmbralOut])
def listar_umbrales(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(UmbralKPI).order_by(UmbralKPI.kpi_codigo).all()


@router.put("/umbrales/{kpi_codigo}", response_model=UmbralOut)
def actualizar_umbral(
    kpi_codigo: str,
    body: UmbralIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    u = db.query(UmbralKPI).filter(UmbralKPI.kpi_codigo == kpi_codigo).first()
    if u:
        u.umbral_verde = Decimal(str(body.umbral_verde))
        u.umbral_amarillo = Decimal(str(body.umbral_amarillo))
    else:
        u = UmbralKPI(
            kpi_codigo=kpi_codigo,
            umbral_verde=Decimal(str(body.umbral_verde)),
            umbral_amarillo=Decimal(str(body.umbral_amarillo)),
        )
        db.add(u)
    db.commit()
    db.refresh(u)
    return u
