"""
Router Modelo Analítico de Rentabilidad.
Expone MAP_CUENTAS CRUD, MAP_DRIVERS, recálculo y 7 dashboards.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from ..core.limiter import limiter
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.analitico import NATURALEZAS, DRIVERS
from ..services.analitico import (
    recalcular_analitico_async, get_task_status,
    dashboard_ejecutivo, dashboard_compania, dashboard_auxiliar,
    dashboard_ramo, dashboard_subramo, dashboard_nueva_produccion,
    dashboard_operaciones, dashboard_costes,
    listar_map_cuentas, upsert_map_cuenta, delete_map_cuenta,
    listar_map_drivers, upsert_map_driver,
    ejercicios_disponibles, importar_desde_mapeo, conciliacion,
    asignar_auxiliar_cesion,
    listar_ajustes_coste, crear_ajuste_coste,
    actualizar_ajuste_coste, eliminar_ajuste_coste,
    calcular_valoracion,
)
from ..core.errores import error_http

router = APIRouter(prefix="/analitico", tags=["analitico"])


# ── Map Cuentas ───────────────────────────────────────────────────────────────

class MapCuentaIn(BaseModel):
    numero_cuenta: str
    naturaleza: str
    descripcion: Optional[str] = None


@router.get("/map-cuentas")
def get_map_cuentas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = listar_map_cuentas(db)
    return [
        {
            "numero_cuenta": r.numero_cuenta,
            "naturaleza": r.naturaleza,
            "descripcion": r.descripcion,
        }
        for r in rows
    ]


@router.post("/map-cuentas")
def save_map_cuenta(
    body: MapCuentaIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    if body.naturaleza not in NATURALEZAS:
        raise error_http("ANA-001", valores=", ".join(NATURALEZAS))
    upsert_map_cuenta(db, body.numero_cuenta.strip(), body.naturaleza, body.descripcion)
    return {"ok": True}


@router.post("/map-cuentas/importar-desde-mapeo")
def importar_mapeo(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Copia cuentas de gasto de map_cuentas_contables → analitico_map_cuentas."""
    return importar_desde_mapeo(db)


@router.delete("/map-cuentas/{numero_cuenta}")
def remove_map_cuenta(
    numero_cuenta: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    ok = delete_map_cuenta(db, numero_cuenta)
    if not ok:
        raise error_http("ANA-002")
    return {"ok": True}


# ── Map Drivers ───────────────────────────────────────────────────────────────

class MapDriverIn(BaseModel):
    naturaleza: str
    driver: str


@router.get("/map-drivers")
def get_map_drivers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return listar_map_drivers(db)


@router.post("/map-drivers")
def save_map_driver(
    body: MapDriverIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    if body.naturaleza not in NATURALEZAS:
        raise error_http("ANA-001", valores=", ".join(NATURALEZAS))
    if body.driver not in DRIVERS:
        raise error_http("ANA-003", valores=", ".join(DRIVERS))
    return upsert_map_driver(db, body.naturaleza, body.driver)


# ── Listas de referencia ──────────────────────────────────────────────────────

@router.get("/naturalezas")
def get_naturalezas(current_user: User = Depends(get_current_user)):
    return NATURALEZAS


@router.get("/drivers")
def get_drivers(current_user: User = Depends(get_current_user)):
    return DRIVERS


@router.get("/ejercicios")
def get_ejercicios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ejercicios_disponibles(db)


# ── Recálculo ─────────────────────────────────────────────────────────────────

@router.post("/recalcular")
@limiter.limit("5/minute")
def recalcular(
    request: Request,
    ejercicio: int = Query(...),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Lanza el recálculo en segundo plano. Devuelve task_id para polling."""
    task_id = recalcular_analitico_async(ejercicio)
    return {"task_id": task_id}


@router.get("/recalcular/estado")
def recalcular_estado(
    task_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    status = get_task_status(task_id)
    if status is None:
        raise error_http("ANA-004")
    return status


# ── Dashboards ────────────────────────────────────────────────────────────────

@router.get("/tasa-cesion-real")
def get_tasa_cesion_real(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tasa real de cesión del ejercicio: la que se aplica por defecto a la cesión estimada."""
    from ..services.tasa_cesion import detalle_tasa_cesion_real
    return detalle_tasa_cesion_real(db, ejercicio)


@router.get("/conciliacion")
def conciliacion_analitica(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0, description="Tasa de cesión estimada 0–1. Sin informar: tasa real del ejercicio."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Comprobaciones de cuadre entre diario contable, modelo analítico y presupuesto."""
    return conciliacion(db, ejercicio, tasa_cesion_estimada=tasa)


@router.get("/dashboard/ejecutivo")
def dash_ejecutivo(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_ejecutivo(db, ejercicio, tasa_cesion_estimada=tasa)


@router.get("/dashboard/compania")
def dash_compania(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_compania(db, ejercicio, tasa_cesion_estimada=tasa)


@router.get("/dashboard/auxiliar")
def dash_auxiliar(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_auxiliar(db, ejercicio, tasa_cesion_estimada=tasa)


@router.get("/dashboard/ramo")
def dash_ramo(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_ramo(db, ejercicio, tasa_cesion_estimada=tasa)


@router.get("/dashboard/subramo")
def dash_subramo(
    ejercicio: int = Query(...),
    ramo: Optional[str] = Query(None, description="Filtrar por ramo. Sin valor devuelve todos."),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_subramo(db, ejercicio, ramo, tasa_cesion_estimada=tasa)


@router.get("/dashboard/nueva-produccion")
def dash_nueva_produccion(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_nueva_produccion(db, ejercicio, tasa_cesion_estimada=tasa)


@router.get("/dashboard/operaciones")
def dash_operaciones(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_operaciones(db, ejercicio, tasa_cesion_estimada=tasa)


# ── Ajustes de coste por auxiliar ────────────────────────────────────────────

class AjusteCosteIn(BaseModel):
    ejercicio: int
    auxiliar: str
    numero_cuenta: str
    descripcion: str
    importe_mensual: float


class AjusteCosteUpdate(BaseModel):
    auxiliar: Optional[str] = None
    numero_cuenta: Optional[str] = None
    descripcion: Optional[str] = None
    importe_mensual: Optional[float] = None
    activo: Optional[bool] = None


@router.get("/ajustes-coste")
def get_ajustes_coste(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = listar_ajustes_coste(db, ejercicio)
    return [
        {
            "id": str(r.id),
            "ejercicio": r.ejercicio,
            "auxiliar": r.auxiliar,
            "numero_cuenta": r.numero_cuenta,
            "descripcion": r.descripcion,
            "importe_mensual": float(r.importe_mensual),
            "importe_anual": float(r.importe_mensual) * 12,
            "activo": r.activo,
        }
        for r in rows
    ]


@router.post("/ajustes-coste")
def post_ajuste_coste(
    body: AjusteCosteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    aj = crear_ajuste_coste(
        db, body.ejercicio, body.auxiliar, body.numero_cuenta,
        body.descripcion, body.importe_mensual,
    )
    return {"ok": True, "id": str(aj.id)}


@router.patch("/ajustes-coste/{ajuste_id}")
def patch_ajuste_coste(
    ajuste_id: str,
    body: AjusteCosteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    kwargs = {k: v for k, v in body.dict().items() if v is not None}
    aj = actualizar_ajuste_coste(db, ajuste_id, **kwargs)
    if not aj:
        raise error_http("ANA-005")
    return {"ok": True}


@router.delete("/ajustes-coste/{ajuste_id}")
def delete_ajuste_coste_endpoint(
    ajuste_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    ok = eliminar_ajuste_coste(db, ajuste_id)
    if not ok:
        raise error_http("ANA-005")
    return {"ok": True}


@router.post("/cesion-sin-auxiliar/asignar")
def asignar_auxiliar(
    ejercicio: int = Query(...),
    numero_cuenta: str = Query(...),
    auxiliar: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Asigna auxiliar a todos los apuntes 623 sin auxiliar de una cuenta del ejercicio."""
    n = asignar_auxiliar_cesion(db, ejercicio, numero_cuenta, auxiliar)
    return {"ok": True, "actualizados": n}


# ── Valoración ────────────────────────────────────────────────────────────────

@router.get("/valoracion")
def get_valoracion(
    ejercicio: int = Query(...),
    crecimiento: Optional[float] = Query(None, ge=0.0, le=1.0, description="CAGR manual 0-1 (ej: 0.05 = 5%). Si omite, se calcula automáticamente."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calcular_valoracion(db, ejercicio, crecimiento)


@router.get("/dashboard/costes")
def dash_costes(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_costes(db, ejercicio, tasa_cesion_estimada=tasa)
