"""Endpoints de las herramientas del módulo Cierres: Recobros (Diagnóstico H), Asientos de
diferencias y Exportar. Lectura: cualquier usuario autenticado. Escritura: admin y gestor."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import engine, get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..services.cierres import consultas, diferencias, exportar, recobros, tareas

router = APIRouter(prefix="/cierres", tags=["cierres-herramientas"])
log = logging.getLogger(__name__)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _400(e: ValueError):
    raise HTTPException(status_code=400, detail=str(e))


# ── Recobros (Diagnóstico H) ─────────────────────────────────────────────────

class FiltroRecobros(BaseModel):
    ejercicio: int
    concepto: str = Field(..., min_length=1, max_length=200)
    cuenta: Optional[str] = None


class SeleccionRecobros(FiltroRecobros):
    seleccion: list[dict] = Field(..., min_length=1, max_length=20000)
    modo: str = Field(..., pattern="^(grupo|filas)$")
    tolerancia: float = Field(0.01, ge=0, le=10000)


class Emparejamiento(BaseModel):
    grupo: str
    recibo: Optional[str] = ""
    neto_recobros: float
    cobro_ids: list[int] = Field(..., min_length=1, max_length=300)


class Ids(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=5000)


class GruposH(BaseModel):
    ejercicios: list[int] = Field(..., min_length=1)
    tolerancia: float = Field(0.01, ge=0, le=10000)


@router.post("/recobros/diagnostico")
def post_diagnostico(body: FiltroRecobros, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return recobros.diagnostico(db, body.ejercicio, body.concepto, body.cuenta)
    except ValueError as e:
        _400(e)


@router.post("/recobros/conciliar")
def post_conciliar_recobros(body: SeleccionRecobros, db: Session = Depends(get_db),
                            user: User = Depends(require_gestor_or_admin)):
    try:
        res = recobros.conciliar(db, body.ejercicio, body.concepto, body.cuenta, body.seleccion, body.modo,
                                 body.tolerancia)
    except ValueError as e:
        db.rollback()
        _400(e)
    db.commit()
    consultas.invalidar_cache()
    log.info("Cierres recobros conciliar | modo=%s apuntes=%d user='%s'", body.modo, res["conciliados"], user.username)
    return res


@router.get("/recobros/candidatos")
def get_candidatos(cuenta: str, recibo: Optional[str] = None, db: Session = Depends(get_db),
                   _=Depends(get_current_user)):
    return recobros.candidatos(db, cuenta, recibo)


@router.post("/recobros/emparejamientos")
def post_emparejamiento(body: Emparejamiento, db: Session = Depends(get_db),
                        user: User = Depends(require_gestor_or_admin)):
    try:
        res = recobros.guardar_emparejamientos(db, body.grupo, body.recibo or "", body.neto_recobros, body.cobro_ids)
    except ValueError as e:
        db.rollback()
        _400(e)
    db.commit()
    log.info("Cierres recobros emparejamiento | grupo=%s cobros=%s user='%s'", body.grupo, body.cobro_ids, user.username)
    return res


@router.get("/recobros/emparejamientos")
def get_emparejamientos(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return recobros.listar_emparejamientos(db)


@router.post("/recobros/emparejamientos/borrar")
def post_borrar_emparejamientos(body: Ids, db: Session = Depends(get_db), _=Depends(require_gestor_or_admin)):
    res = recobros.borrar_emparejamientos(db, body.ids)
    db.commit()
    return res


@router.post("/recobros/conciliar-grupos")
def post_conciliar_grupos(body: GruposH, user: User = Depends(require_gestor_or_admin)):
    log.info("Cierres recobros conciliar grupos | ejercicios=%s tol=%s user='%s'",
             body.ejercicios, body.tolerancia, user.username)
    try:
        tid = tareas.lanzar("recobros", lambda p: recobros.conciliar_grupos_h(
            engine, sorted(set(body.ejercicios)), body.tolerancia, p), escribe=True, usuario=user.username)
    except tareas.TareaOcupada as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"task_id": tid}


@router.post("/recobros/excel")
def post_excel_recobros(body: FiltroRecobros, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        diag = recobros.diagnostico(db, body.ejercicio, body.concepto, body.cuenta)
    except ValueError as e:
        _400(e)
    ruta = tareas.ruta_descarga("diagnostico_H.xlsx")
    recobros.excel_diagnostico(diag, body.ejercicio, body.concepto, ruta)
    return FileResponse(ruta, filename=f"diagnostico_H_{body.ejercicio}.xlsx", media_type=XLSX)


# ── Asientos de diferencias ──────────────────────────────────────────────────

class Duplicado(BaseModel):
    origen_ejercicio: int
    origen_numero: int
    ejercicio: int = Field(..., ge=2000, le=2100)
    numero: int = Field(..., ge=1, le=999999)
    invertido: bool = False


class Duplicados(BaseModel):
    duplicados: list[Duplicado] = Field(..., min_length=1, max_length=500)


@router.get("/diferencias/asiento")
def get_asiento(ejercicio: int, numero: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return diferencias.cargar_asiento(db, ejercicio, numero)
    except ValueError as e:
        _400(e)


@router.post("/diferencias/excel")
def post_excel_diferencias(body: Duplicados, db: Session = Depends(get_db), _=Depends(get_current_user)):
    ruta = tareas.ruta_descarga("asientos_diferencias.xlsx")
    try:
        diferencias.excel_asientos(db, [d.model_dump() for d in body.duplicados], ruta)
    except ValueError as e:
        _400(e)
    return FileResponse(ruta, filename=f"Asientos_Diferencias_{body.duplicados[-1].ejercicio}.xlsx", media_type=XLSX)


# ── Exportar ─────────────────────────────────────────────────────────────────

@router.post("/exportar")
def post_exportar(ejercicio: Optional[int] = None, user: User = Depends(get_current_user)):
    nombre = f"Cuadre_Contable_{ejercicio or 'todos'}.xlsx"

    def generar(progreso):
        ruta = tareas.ruta_descarga(nombre)
        with engine.connect() as conn:
            res = exportar.excel_no_conciliados(conn, ruta, ejercicio, progreso)
        return res | {"archivo": ruta, "nombre": nombre}

    return {"task_id": tareas.lanzar("exportar", generar, usuario=user.username)}
