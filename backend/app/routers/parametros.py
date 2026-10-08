import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, field_validator

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_admin, require_gestor_or_admin
from ..models.user import User
from ..models.parametros import MapCuentaContable, TipoCuentaParam

router = APIRouter(prefix="/parametros", tags=["Parámetros"])
log = logging.getLogger(__name__)

FAMILIAS_GASTO = [
    "Personal",
    "Cesiones a auxiliares",
    "Alquiler y oficina",
    "Tecnología y software",
    "Servicios profesionales",
    "Marketing y captación",
    "Gastos financieros",
    "Tributos y seguros",
    "Amortizaciones y ajustes",
    "Otros gastos",
]


class MapCuentaCreate(BaseModel):
    numero_cuenta: str
    tipo: TipoCuentaParam
    compania: Optional[str] = None
    familia_gasto: Optional[str] = None
    descripcion: Optional[str] = None
    excluir_tesoreria: bool = False

    @field_validator('tipo', mode='before')
    @classmethod
    def normalizar_tipo(cls, v: object) -> object:
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator('numero_cuenta', mode='before')
    @classmethod
    def normalizar_cuenta(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return str(v).strip() if v is not None else v

    @field_validator('excluir_tesoreria', mode='before')
    @classmethod
    def normalizar_excluir(cls, v: object) -> bool:
        # Excel puede traerlo como "si"/"no"/"true"/"false"/1/0
        if isinstance(v, str):
            return v.strip().lower() in ('si', 'sí', 'true', '1', 'yes', 'x')
        return bool(v)


class MapCuentaUpdate(BaseModel):
    tipo: Optional[TipoCuentaParam] = None
    compania: Optional[str] = None
    familia_gasto: Optional[str] = None
    descripcion: Optional[str] = None
    excluir_tesoreria: Optional[bool] = None
    activo: Optional[bool] = None


class MapCuentaResponse(BaseModel):
    id: UUID
    numero_cuenta: str
    tipo: TipoCuentaParam
    compania: Optional[str]
    familia_gasto: Optional[str]
    descripcion: Optional[str]
    excluir_tesoreria: bool
    activo: bool

    model_config = {"from_attributes": True}


@router.get("/familias-gasto")
def listar_familias():
    return FAMILIAS_GASTO


@router.get("/cuentas", response_model=List[MapCuentaResponse])
def listar_cuentas(
    tipo: Optional[TipoCuentaParam] = None,
    activo: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(MapCuentaContable)
    if tipo:
        q = q.filter(MapCuentaContable.tipo == tipo)
    if activo is not None:
        q = q.filter(MapCuentaContable.activo == activo)
    return q.order_by(MapCuentaContable.numero_cuenta).all()


@router.post("/cuentas", response_model=MapCuentaResponse, status_code=status.HTTP_201_CREATED)
def crear_cuenta(
    payload: MapCuentaCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.query(MapCuentaContable).filter(MapCuentaContable.numero_cuenta == payload.numero_cuenta).first():
        log.warning("ERR_MAPEO_DUPLICADO | cuenta='%s'", payload.numero_cuenta)
        raise HTTPException(status_code=400, detail="Ya existe un mapeo para esa cuenta")

    _validar_campos(payload.tipo, payload.compania, payload.familia_gasto)

    mapa = MapCuentaContable(**payload.model_dump())
    db.add(mapa)
    db.commit()
    db.refresh(mapa)
    log.info("Cuenta creada | cuenta='%s' tipo='%s'", payload.numero_cuenta, payload.tipo)
    return mapa


@router.patch("/cuentas/{cuenta_id}", response_model=MapCuentaResponse)
def actualizar_cuenta(
    cuenta_id: UUID,
    payload: MapCuentaUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    mapa = db.query(MapCuentaContable).filter(MapCuentaContable.id == cuenta_id).first()
    if not mapa:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")

    datos = payload.model_dump(exclude_none=True)
    tipo_final = datos.get("tipo", mapa.tipo)
    compania_final = datos.get("compania", mapa.compania)
    familia_final = datos.get("familia_gasto", mapa.familia_gasto)
    _validar_campos(tipo_final, compania_final, familia_final)

    for k, v in datos.items():
        setattr(mapa, k, v)
    db.commit()
    db.refresh(mapa)
    return mapa


@router.delete("/cuentas/{cuenta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cuenta(
    cuenta_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    mapa = db.query(MapCuentaContable).filter(MapCuentaContable.id == cuenta_id).first()
    if not mapa:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")
    db.delete(mapa)
    db.commit()


@router.post("/cuentas/importar-lote")
def importar_lote(
    cuentas: List[MapCuentaCreate],
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Importa múltiples mapeos de una vez, devolviendo detalle por fila."""
    insertados = 0
    omitidos = 0
    errores: list[dict] = []

    log.info("Inicio importación lote | total_filas=%d", len(cuentas))

    for i, c in enumerate(cuentas):
        fila = i + 1
        if db.query(MapCuentaContable).filter(MapCuentaContable.numero_cuenta == c.numero_cuenta).first():
            omitidos += 1
            motivo = "Ya existe un mapeo para esta cuenta"
            errores.append({"fila": fila, "cuenta": c.numero_cuenta, "motivo": motivo})
            log.info("ERR_MAPEO_DUPLICADO | fila=%d cuenta='%s'", fila, c.numero_cuenta)
            continue
        try:
            _validar_campos(c.tipo, c.compania, c.familia_gasto)
            db.add(MapCuentaContable(**c.model_dump()))
            insertados += 1
            log.info("Fila %d insertada | cuenta='%s' tipo='%s'", fila, c.numero_cuenta, c.tipo)
        except HTTPException as exc:
            omitidos += 1
            errores.append({"fila": fila, "cuenta": c.numero_cuenta, "motivo": exc.detail})
            log.warning(
                "ERR_MAPEO_VALIDACION | fila=%d cuenta='%s' motivo='%s'",
                fila, c.numero_cuenta, exc.detail,
            )
        except Exception as exc:
            omitidos += 1
            motivo = f"Error inesperado: {type(exc).__name__}: {str(exc)}"
            errores.append({"fila": fila, "cuenta": c.numero_cuenta, "motivo": motivo})
            log.error(
                "ERR_MAPEO_INESPERADO | fila=%d cuenta='%s' error='%s'",
                fila, c.numero_cuenta, str(exc),
            )

    db.commit()
    log.info(
        "Importación lote completada | insertados=%d omitidos=%d",
        insertados, omitidos,
    )
    return {"insertados": insertados, "omitidos": omitidos, "errores": errores}


def _validar_campos(tipo: TipoCuentaParam, compania: Optional[str], familia: Optional[str]):
    if tipo == TipoCuentaParam.INGRESO and not compania:
        raise HTTPException(status_code=400, detail="Las cuentas de ingreso requieren compañía")
    if tipo == TipoCuentaParam.GASTO and not familia:
        raise HTTPException(status_code=400, detail="Las cuentas de gasto requieren familia de gasto")
