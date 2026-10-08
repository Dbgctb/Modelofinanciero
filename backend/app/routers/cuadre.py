from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.dependencies import get_db, get_current_user
from ..services.cuadre import panel_control

router = APIRouter(prefix="/cuadre", tags=["cuadre"])


@router.get("/panel")
def get_panel(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return panel_control(db, ejercicio)
