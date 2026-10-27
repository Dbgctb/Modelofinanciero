"""
Router Modelo Analítico de Rentabilidad.
Expone MAP_CUENTAS CRUD, MAP_DRIVERS, recálculo y 7 dashboards.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..core.limiter import limiter
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin, require_admin
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
        raise HTTPException(400, f"Naturaleza inválida. Valores posibles: {NATURALEZAS}")
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
        raise HTTPException(404, "Cuenta no encontrada")
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
        raise HTTPException(400, f"Naturaleza inválida")
    if body.driver not in DRIVERS:
        raise HTTPException(400, f"Driver inválido. Valores posibles: {DRIVERS}")
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
        raise HTTPException(404, "Tarea no encontrada o expirada")
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
        raise HTTPException(404, "Ajuste no encontrado")
    return {"ok": True}


@router.delete("/ajustes-coste/{ajuste_id}")
def delete_ajuste_coste_endpoint(
    ajuste_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    ok = eliminar_ajuste_coste(db, ajuste_id)
    if not ok:
        raise HTTPException(404, "Ajuste no encontrado")
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


@router.get("/debug/cesion")
def debug_cesion(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Diagnóstico: estado de las cuentas 623 en diario, modelo y mapeo."""
    from sqlalchemy import text as _t

    def q(sql, **kw):
        return db.execute(_t(sql), kw).fetchall()

    # 1. Diario: resumen de 623 entries
    diario = q("""
        SELECT
            COUNT(*)                                                               AS total,
            SUM(CASE WHEN auxiliar IS NOT NULL AND auxiliar != '' THEN 1 ELSE 0 END) AS con_aux,
            SUM(CASE WHEN auxiliar IS NULL OR auxiliar = ''       THEN 1 ELSE 0 END) AS sin_aux,
            SUM(CASE WHEN tipo_cuenta::text = 'gasto'             THEN 1 ELSE 0 END) AS tipo_gasto,
            SUM(CASE WHEN tipo_cuenta::text = 'ingreso'           THEN 1 ELSE 0 END) AS tipo_ingreso,
            SUM(CASE WHEN tipo_cuenta IS NULL                     THEN 1 ELSE 0 END) AS tipo_null,
            COALESCE(SUM(CAST(debe AS FLOAT) - CAST(haber AS FLOAT)), 0)           AS importe_total
        FROM diario_apuntes
        WHERE ejercicio = :ej AND numero_cuenta LIKE '623%' AND estado::text != 'excluido'
    """, ej=ejercicio)

    # 2. Fact: resumen de cesión en el modelo
    fact = q("""
        SELECT
            COUNT(*)                                                              AS total_cesion_rows,
            COUNT(DISTINCT auxiliar)                                             AS aux_distintos,
            COALESCE(SUM(CAST(importe AS FLOAT)), 0)                            AS importe_total
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND naturaleza = 'Cesión auxiliar'
    """, ej=ejercicio)

    # 3. Muestra de cesión en el modelo (top 5 por importe)
    fact_sample = q("""
        SELECT auxiliar, tipo_cuenta, naturaleza,
               COALESCE(SUM(CAST(importe AS FLOAT)), 0) AS imp
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND naturaleza = 'Cesión auxiliar'
        GROUP BY auxiliar, tipo_cuenta, naturaleza ORDER BY 4 LIMIT 5
    """, ej=ejercicio)

    # 4. Muestra de 623 en el diario (5 primeras)
    diario_sample = q("""
        SELECT numero_cuenta, auxiliar, tipo_cuenta::text,
               CAST(debe AS FLOAT) - CAST(haber AS FLOAT) AS importe
        FROM diario_apuntes
        WHERE ejercicio = :ej AND numero_cuenta LIKE '623%' AND estado::text != 'excluido'
        LIMIT 5
    """, ej=ejercicio)

    # 5. Map analítico: cuántos 623* tienen nombre de auxiliar en descripcion
    map_stat = q("""
        SELECT
            COUNT(*) AS total_623_en_map,
            COUNT(CASE WHEN descripcion NOT IN ('Auxiliares','Cesión auxiliar','Cesion auxiliar')
                            AND descripcion IS NOT NULL AND descripcion != ''
                       THEN 1 END) AS con_nombre_auxiliar
        FROM analitico_map_cuentas
        WHERE numero_cuenta LIKE '623%' AND LENGTH(numero_cuenta) > 3
    """)

    d = diario[0] if diario else [0]*7
    f = fact[0] if fact else [0]*3

    return {
        "diario_apuntes_623": {
            "total": int(d[0]), "con_auxiliar": int(d[1]), "sin_auxiliar": int(d[2]),
            "tipo_gasto": int(d[3]), "tipo_ingreso": int(d[4]), "tipo_null": int(d[5]),
            "importe_total": round(float(d[6]), 2),
        },
        "fact_resultado_cesion": {
            "total_rows": int(f[0]), "aux_distintos": int(f[1]),
            "importe_total": round(float(f[2]), 2),
        },
        "fact_cesion_sample": [
            {"auxiliar": r[0], "tipo_cuenta": r[1], "naturaleza": r[2], "importe": round(float(r[3]), 2)}
            for r in fact_sample
        ],
        "diario_623_sample": [
            {"numero_cuenta": r[0], "auxiliar": r[1], "tipo_cuenta": r[2], "importe": round(float(r[3]), 2)}
            for r in diario_sample
        ],
        "map_analitico_623": {
            "total_en_map": int(map_stat[0][0]) if map_stat else 0,
            "con_nombre_auxiliar": int(map_stat[0][1]) if map_stat else 0,
        },
    }


@router.get("/dashboard/costes")
def dash_costes(
    ejercicio: int = Query(...),
    tasa: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_costes(db, ejercicio, tasa_cesion_estimada=tasa)
