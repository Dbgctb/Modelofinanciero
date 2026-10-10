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
    Preserva: mapeo de cuentas, tasas de mercado, usuarios, meses_reales
    (solo se le desvincula la carga).

    Bug real reportado en vivo (2026-10-10), dos vueltas:
    1) Usaba TRUNCATE sobre las 4 tablas grandes a la vez, incluyendo
       cargas_contables -- Postgres lo rechaza en bloque porque
       meses_reales tiene una FK hacia cargas_contables (da igual que esa
       fila ya se haya puesto a NULL antes: TRUNCATE comprueba la
       restricción, no el valor real fila a fila). Cambiado a DELETE para
       las 4 juntas -- correcto, pero con ~230.000 filas reales (diario +
       recibos) DELETE es muchísimo más lento que TRUNCATE: borra fila a
       fila, con mantenimiento de índice y WAL por cada una.
    2) Arreglo real: solo cargas_contables (8 filas) necesita DELETE --
       es la única con un referenciador "blando" (meses_reales) que hay
       que preservar. Las otras tres (incidencias, fact_resultado_analitico,
       diario_apuntes, recibos) no las referencia nada fuera de este
       mismo grupo, así que se pueden TRUNCATE juntas sin tocar
       cargas_contables -- recupera la velocidad O(1) de TRUNCATE donde
       de verdad importa (las tablas grandes) y dejar el DELETE solo para
       la tabla pequeña, donde el coste es irrelevante.
    """
    # Conteos aproximados desde pg_stat (instantáneo, no hace full scan)
    rows = db.execute(text(
        "SELECT relname, n_live_tup::bigint FROM pg_stat_user_tables "
        "WHERE relname IN ('cargas_contables','recibos','diario_apuntes','incidencias')"
    )).fetchall()
    stats = {r[0]: int(r[1]) for r in rows}

    # meses_reales.carga_id es FK SET NULL → desvincular antes de borrar cargas_contables
    db.execute(text("UPDATE meses_reales SET carga_id = NULL WHERE carga_id IS NOT NULL"))

    # Las tablas grandes no las referencia nada fuera de este grupo -> TRUNCATE (O(1)).
    db.execute(text("TRUNCATE TABLE incidencias, fact_resultado_analitico, diario_apuntes, recibos"))
    # cargas_contables sí la referencia meses_reales (ya desvinculada arriba) -> DELETE, pero solo 8 filas.
    db.execute(text("DELETE FROM cargas_contables"))
    db.commit()

    return {
        "mensaje": "Datos eliminados correctamente",
        "cargas_eliminadas": stats.get("cargas_contables", 0),
        "recibos_eliminados": stats.get("recibos", 0),
        "apuntes_eliminados": stats.get("diario_apuntes", 0),
        "incidencias_eliminadas": stats.get("incidencias", 0),
    }
