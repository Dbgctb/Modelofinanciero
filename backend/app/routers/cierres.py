"""Endpoints del módulo "Cierres contabilidad".

Fase 0: solo el resumen de estado. El resto de endpoints (importar, punteo,
manual, banco...) se añaden por fases según docs/PLAN_CIERRES_CONTABILIDAD.md.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.dependencies import get_db, get_current_user
from ..models import cierres as _modelos  # noqa: F401 — registra las tablas cc_* en Base
from ..services.cierres.resumen import resumen_por_ejercicio

router = APIRouter(prefix="/cierres", tags=["cierres"])


@router.get("/resumen")
def get_resumen(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return resumen_por_ejercicio(db)
