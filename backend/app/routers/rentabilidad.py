from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.dependencies import get_db, get_current_user
from ..services.rentabilidad_cliente import (
    calcular_rentabilidad_clientes,
    recibos_sin_tomador,
    ejercicios_disponibles,
    recibos_por_cliente,
    MIN_COMISION_DEFAULT,
    TASA_CESION_ESTIMADA_DEFAULT,
)

router = APIRouter(prefix="/rentabilidad", tags=["rentabilidad"])


@router.get("/clientes")
def clientes(
    ejercicio: int = Query(...),
    min_comision: float = Query(default=MIN_COMISION_DEFAULT),
    tasa_cesion_estimada: float = Query(default=TASA_CESION_ESTIMADA_DEFAULT),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return calcular_rentabilidad_clientes(db, ejercicio, min_comision, tasa_cesion_estimada)


@router.get("/sin-tomador")
def sin_tomador(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return recibos_sin_tomador(db, ejercicio)


@router.get("/ejercicios")
def ejercicios(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return ejercicios_disponibles(db)


@router.get("/recibos-cliente")
def get_recibos_cliente(
    ejercicio: int = Query(...),
    tomador: str = Query(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return recibos_por_cliente(db, ejercicio, tomador)
