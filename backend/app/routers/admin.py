import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..core.database import get_db
from ..core.dependencies import require_admin
from ..models.user import User
from ..models.mercado import TasaMercadoRef, TipoTasaMercado

router = APIRouter(prefix="/admin", tags=["Administración"])


def _serializar(t: TasaMercadoRef) -> dict:
    return {
        "id": str(t.id),
        "fuente": t.fuente,
        "anyo": t.anyo,
        "tipo": t.tipo.value,
        "ramo_keyword": t.ramo_keyword,
        "tasa_pct": float(t.tasa_pct),
        "es_default": t.es_default,
        "notas": t.notas,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class TasaMercadoCreate(BaseModel):
    fuente: str
    anyo: int
    tipo: TipoTasaMercado
    ramo_keyword: Optional[str] = None
    tasa_pct: float
    es_default: bool = False
    notas: Optional[str] = None


class TasaMercadoUpdate(BaseModel):
    fuente: Optional[str] = None
    tasa_pct: Optional[float] = None
    es_default: Optional[bool] = None
    notas: Optional[str] = None


@router.get("/tasas-mercado")
def listar_tasas(
    anyo: Optional[int] = Query(None),
    tipo: Optional[TipoTasaMercado] = Query(None),
    fuente: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(TasaMercadoRef)
    if anyo:
        q = q.filter(TasaMercadoRef.anyo == anyo)
    if tipo:
        q = q.filter(TasaMercadoRef.tipo == tipo)
    if fuente:
        q = q.filter(TasaMercadoRef.fuente == fuente)
    tasas = q.order_by(TasaMercadoRef.anyo.desc(), TasaMercadoRef.tipo, TasaMercadoRef.ramo_keyword).all()
    return [_serializar(t) for t in tasas]


@router.get("/tasas-mercado/anyos")
def listar_anyos(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Devuelve la lista de años disponibles en la tabla de tasas."""
    from sqlalchemy import distinct
    anyos = db.query(distinct(TasaMercadoRef.anyo)).order_by(TasaMercadoRef.anyo.desc()).all()
    return [a[0] for a in anyos]


@router.post("/tasas-mercado", status_code=201)
def crear_tasa(
    body: TasaMercadoCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tasa = TasaMercadoRef(
        id=uuid.uuid4(),
        fuente=body.fuente,
        anyo=body.anyo,
        tipo=body.tipo,
        ramo_keyword=body.ramo_keyword,
        tasa_pct=body.tasa_pct,
        es_default=body.es_default,
        notas=body.notas,
    )
    db.add(tasa)
    db.commit()
    db.refresh(tasa)
    return _serializar(tasa)


@router.patch("/tasas-mercado/{tasa_id}")
def actualizar_tasa(
    tasa_id: str,
    body: TasaMercadoUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tasa = db.query(TasaMercadoRef).filter(TasaMercadoRef.id == tasa_id).first()
    if not tasa:
        raise HTTPException(status_code=404, detail="Tasa no encontrada")
    for campo, valor in body.model_dump(exclude_none=True).items():
        setattr(tasa, campo, valor)
    db.commit()
    db.refresh(tasa)
    return _serializar(tasa)


@router.delete("/tasas-mercado/{tasa_id}", status_code=204)
def eliminar_tasa(
    tasa_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tasa = db.query(TasaMercadoRef).filter(TasaMercadoRef.id == tasa_id).first()
    if not tasa:
        raise HTTPException(status_code=404, detail="Tasa no encontrada")
    db.delete(tasa)
    db.commit()


@router.post("/reset-datos")
def reset_datos(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Elimina todas las cargas (diarios, recibos, apuntes, incidencias).
    Preserva: mapeo de cuentas, tasas de mercado, usuarios.
    Usa TRUNCATE — ~50x más rápido que DELETE para tablas grandes.
    """
    # Conteos aproximados desde pg_stat (instantáneo, no hace full scan)
    rows = db.execute(text(
        "SELECT relname, n_live_tup::bigint FROM pg_stat_user_tables "
        "WHERE relname IN ('cargas_contables','recibos','diario_apuntes','incidencias')"
    )).fetchall()
    stats = {r[0]: int(r[1]) for r in rows}

    # meses_reales.carga_id es FK SET NULL → actualizar antes del TRUNCATE
    db.execute(text("UPDATE meses_reales SET carga_id = NULL WHERE carga_id IS NOT NULL"))

    # TRUNCATE en orden hijo→padre elimina restricciones FK sin CASCADE
    # Es O(1): desaloja páginas de datos sin procesar fila por fila
    db.execute(text("TRUNCATE TABLE incidencias, diario_apuntes, cargas_contables, recibos"))
    db.commit()

    return {
        "mensaje": "Datos eliminados correctamente",
        "cargas_eliminadas": stats.get("cargas_contables", 0),
        "recibos_eliminados": stats.get("recibos", 0),
        "apuntes_eliminados": stats.get("diario_apuntes", 0),
        "incidencias_eliminadas": stats.get("incidencias", 0),
    }
