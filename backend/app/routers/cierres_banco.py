"""Endpoints de la conciliación bancaria del módulo Cierres.

Lectura: cualquier usuario autenticado. Escritura: admin y gestor.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import engine, get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..services.cierres import consultas, tareas
from ..services.cierres.banco import motor, servicio
from ..core.errores import detalle_usuario, error_http

router = APIRouter(prefix="/cierres/banco", tags=["cierres-banco"])
log = logging.getLogger(__name__)

MAX_EXTRACTO = 20 * 1024 * 1024
TIPOS = {"text/plain", "application/octet-stream", "text/csv", "application/csv",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"}


def _400(e: ValueError):
    raise HTTPException(status_code=400, detail=detalle_usuario(e))


async def _leer(file: UploadFile) -> bytes:
    contenido = await file.read()
    if not contenido:
        raise error_http("ARC-001")
    if len(contenido) > MAX_EXTRACTO:
        raise error_http("ARC-003", max_mb=20)
    if file.content_type not in TIPOS:
        raise error_http("ARC-002", esperado="Norma 43, Excel o CSV")
    return contenido


# ── Bancos y configuración ───────────────────────────────────────────────────

class Banco(BaseModel):
    nombre: str
    cuenta_572: str
    iban: Optional[str] = ""
    entidad: Optional[str] = ""
    activo: bool = True


@router.get("/bancos")
def get_bancos(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return servicio.listar_bancos(db)


@router.post("/bancos")
def post_banco(body: Banco, db: Session = Depends(get_db), _=Depends(require_gestor_or_admin)):
    try:
        id_ = servicio.guardar_banco(db, body.model_dump())
    except ValueError as e:
        _400(e)
    db.commit()
    return {"id": id_}


@router.put("/bancos/{banco_id}")
def put_banco(banco_id: int, body: Banco, db: Session = Depends(get_db), _=Depends(require_gestor_or_admin)):
    try:
        servicio.guardar_banco(db, body.model_dump(), banco_id)
    except ValueError as e:
        _400(e)
    db.commit()
    return {"id": banco_id}


@router.delete("/bancos/{banco_id}")
def delete_banco(banco_id: int, db: Session = Depends(get_db), _=Depends(require_gestor_or_admin)):
    try:
        servicio.borrar_banco(db, banco_id)
    except ValueError as e:
        _400(e)
    db.commit()
    return {"ok": True}


class Config(BaseModel):
    dias_nivel2: int = Field(..., ge=0, le=30)
    tol_nivel8: float = Field(..., ge=0, le=1000)
    tol_nivel9: float = Field(..., ge=0, le=1000)


@router.get("/{banco_id}/config")
def get_config(banco_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return servicio.leer_config(db, banco_id)
    except ValueError as e:
        _400(e)


@router.put("/{banco_id}/config")
def put_config(banco_id: int, body: Config, db: Session = Depends(get_db), _=Depends(require_gestor_or_admin)):
    try:
        servicio.guardar_config(db, banco_id, body.dias_nivel2, body.tol_nivel8, body.tol_nivel9)
    except ValueError as e:
        _400(e)
    db.commit()
    return {"ok": True}


# ── Extractos ────────────────────────────────────────────────────────────────

@router.post("/columnas")
async def post_columnas(file: UploadFile = File(...), _=Depends(get_current_user)):
    try:
        return servicio.columnas_tabla(file.filename or "", await _leer(file))
    except ValueError as e:
        _400(e)


@router.post("/{banco_id}/importar")
async def post_importar(
    banco_id: int,
    file: UploadFile = File(...),
    ejercicio: int = Form(..., ge=2000, le=2100),
    formato: str = Form(..., pattern="^(norma43|tabla)$"),
    mapeo: str = Form("{}"),
    indice_cuenta: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_gestor_or_admin),
):
    contenido = await _leer(file)
    try:
        if formato == "norma43":
            res = servicio.importar_norma43(db, contenido, banco_id, ejercicio, indice_cuenta)
        else:
            res = servicio.importar_tabla(db, file.filename or "", contenido, banco_id, ejercicio, json.loads(mapeo))
    except (ValueError, json.JSONDecodeError) as e:
        db.rollback()
        _400(ValueError(str(e)))
    db.commit()
    log.info("Cierres banco importar | banco=%d ejercicio=%d formato=%s res=%s user='%s'",
             banco_id, ejercicio, formato, {k: v for k, v in res.items() if k != "elegir_cuenta"}, user.username)
    return res


@router.get("/{banco_id}/extractos")
def get_extractos(banco_id: int, ejercicio: int, page: int = 1, page_size: int = 200,
                  db: Session = Depends(get_db), _=Depends(get_current_user)):
    return servicio.listar_extractos(db, banco_id, ejercicio, max(page, 1), min(max(page_size, 10), 1000))


# ── Conciliación automática ──────────────────────────────────────────────────

class Ejecutar(BaseModel):
    ejercicio: int


@router.post("/{banco_id}/conciliar")
def post_conciliar(banco_id: int, body: Ejecutar, user: User = Depends(require_gestor_or_admin)):
    log.info("Cierres banco conciliar | banco=%d ejercicio=%d user='%s'", banco_id, body.ejercicio, user.username)
    try:
        tid = tareas.lanzar("banco", lambda p: motor.conciliar(engine, body.ejercicio, banco_id, p),
                            escribe=True, usuario=user.username)
    except tareas.TareaOcupada as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"task_id": tid}


# ── Pendientes y punteo manual ───────────────────────────────────────────────

@router.get("/{banco_id}/pendientes")
def get_pendientes(banco_id: int, ejercicio: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return servicio.pendientes(db, banco_id, ejercicio)
    except ValueError as e:
        _400(e)


class Manual1a1(BaseModel):
    ejercicio: int
    id_banco: int
    id_diario: int


class ManualNN(BaseModel):
    ejercicio: int
    ids_banco: list[int] = Field(..., min_length=1, max_length=5000)
    ids_diario: list[int] = Field(..., min_length=1, max_length=5000)


class IdsBanco(BaseModel):
    ids_banco: list[int] = Field(..., min_length=1, max_length=5000)


def _escribir(db, fn, user, que):
    try:
        res = fn()
    except ValueError as e:
        db.rollback()
        _400(e)
    db.commit()
    consultas.invalidar_cache()
    log.info("Cierres banco %s | %s user='%s'", que, res, user.username)
    return res


@router.post("/{banco_id}/manual-1a1")
def post_1a1(banco_id: int, body: Manual1a1, db: Session = Depends(get_db),
             user: User = Depends(require_gestor_or_admin)):
    return _escribir(db, lambda: servicio.conciliar_1a1(db, banco_id, body.ejercicio, body.id_banco, body.id_diario),
                     user, "1:1")


@router.post("/{banco_id}/manual-nn")
def post_nn(banco_id: int, body: ManualNN, db: Session = Depends(get_db),
            user: User = Depends(require_gestor_or_admin)):
    return _escribir(db, lambda: servicio.conciliar_nn(db, banco_id, body.ejercicio, body.ids_banco, body.ids_diario),
                     user, "N:N")


@router.post("/{banco_id}/propuesta-asientos")
def post_propuesta(banco_id: int, body: IdsBanco, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return servicio.propuesta_asientos(db, banco_id, body.ids_banco)
    except ValueError as e:
        _400(e)


# ── Conciliados ──────────────────────────────────────────────────────────────

@router.get("/{banco_id}/conciliados")
def get_conciliados(banco_id: int, ejercicio: int, nivel: Optional[str] = None, page: int = 1,
                    page_size: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return servicio.conciliados(db, banco_id, ejercicio, nivel, max(page, 1), min(max(page_size, 10), 1000))


@router.post("/{banco_id}/desconciliar")
def post_desconciliar(banco_id: int, body: IdsBanco, db: Session = Depends(get_db),
                      user: User = Depends(require_gestor_or_admin)):
    return _escribir(db, lambda: servicio.desconciliar(db, banco_id, body.ids_banco), user, "desconciliar")


@router.get("/{banco_id}/conciliados/excel")
def get_excel(banco_id: int, ejercicio: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    ruta = tareas.ruta_descarga("conciliados_banco.xlsx")
    servicio.excel_conciliados(db, banco_id, ejercicio, ruta)
    return FileResponse(ruta, filename=f"conciliados_banco_{ejercicio}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
