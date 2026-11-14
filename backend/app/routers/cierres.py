"""Endpoints del módulo "Cierres contabilidad" (punteo del diario completo).

Lectura: cualquier usuario autenticado. Escritura: admin y gestor.
Las operaciones largas (importar, puntear, exportar el Excel de conciliados) van en
segundo plano: devuelven task_id y se consulta /cierres/tareas/{task_id}.
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import engine, get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models import cierres as _modelos  # noqa: F401 — registra las tablas cc_* en Base
from ..models.user import User
from ..services.cierres import consultas, excel, importador, punteo, tareas
from ..services.cierres.controles import CONTROLES, resumen_incidencias
from ..services.cierres.resumen import resumen_por_ejercicio

router = APIRouter(prefix="/cierres", tags=["cierres"])
log = logging.getLogger(__name__)

TIPOS_EXCEL = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"}
TIPOS_TXT = {"text/csv", "application/csv", "text/plain", "application/octet-stream"}
MAX_FICHERO = 80 * 1024 * 1024  # el diario de un ejercicio (~140.000 líneas) cabe holgado


def _400(e: ValueError):
    raise HTTPException(status_code=400, detail=str(e))


def _ocupado(e: tareas.TareaOcupada):
    raise HTTPException(status_code=409, detail=str(e))


# ── Resumen y tareas ─────────────────────────────────────────────────────────

@router.get("/resumen")
def get_resumen(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return resumen_por_ejercicio(db)


@router.get("/tareas/{task_id}")
def get_tarea(task_id: str, _=Depends(get_current_user)):
    t = tareas.estado(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada (¿se reinició el servidor?)")
    res = t.get("resultado")
    if isinstance(res, dict) and "archivo" in res:  # no se expone la ruta del servidor
        t["resultado"] = {k: v for k, v in res.items() if k != "archivo"} | {"descargable": True}
    return t


@router.get("/tareas/{task_id}/descarga")
def descargar(task_id: str, _=Depends(get_current_user)):
    t = tareas.estado(task_id)
    res = (t or {}).get("resultado") or {}
    ruta = res.get("archivo")
    if not ruta or not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="El fichero ya no está disponible; vuelve a generarlo.")
    return FileResponse(ruta, filename=res.get("nombre", "export.xlsx"),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── Importar diario ──────────────────────────────────────────────────────────

@router.post("/importar")
async def post_importar(
    file: UploadFile = File(...),
    ejercicio: int = Form(..., ge=2000, le=2100),
    modo: str = Form(..., pattern="^(completo|incremental)$"),
    limpiar: bool = Form(True),
    user: User = Depends(require_gestor_or_admin),
):
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > MAX_FICHERO:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máximo 80 MB)")
    nombre = file.filename or ""
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    permitidos = TIPOS_EXCEL if ext in ("xlsx", "xls") else TIPOS_TXT if ext in ("txt", "csv") else set()
    if file.content_type not in permitidos:
        raise HTTPException(status_code=415, detail="Tipo de archivo no permitido (Excel o TXT/CSV del diario)")
    log.info("Cierres importar | fichero='%s' ejercicio=%d modo=%s limpiar=%s user='%s'",
             nombre, ejercicio, modo, limpiar, user.username)
    try:
        if modo == "completo":
            tid = tareas.lanzar("importar", lambda p: importador.importar_completo(
                engine, nombre, contenido, ejercicio, limpiar, p), escribe=True, usuario=user.username)
        else:
            tid = tareas.lanzar("importar", lambda p: importador.importar_incremental(
                engine, nombre, contenido, ejercicio, p), escribe=True, usuario=user.username)
    except tareas.TareaOcupada as e:
        _ocupado(e)
    return {"task_id": tid}


@router.get("/apuntes")
def get_apuntes(
    ejercicio: int,
    cuenta: Optional[str] = None,
    conciliado: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(1000, ge=10, le=2000),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return consultas.listar_apuntes(db, ejercicio, cuenta, conciliado, page, page_size)
    except ValueError as e:
        _400(e)


@router.get("/importar/diferencias")
def get_diferencias(ejercicio: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return consultas.diferencias_incremental(db, ejercicio)


class EliminarHuerfanos(BaseModel):
    ejercicio: int
    ids: list[int] = Field(..., min_length=1, max_length=50_000)


@router.post("/importar/eliminar-huerfanos")
def post_eliminar_huerfanos(body: EliminarHuerfanos, db: Session = Depends(get_db),
                            user: User = Depends(require_gestor_or_admin)):
    res = importador.eliminar_huerfanos(db, body.ejercicio, body.ids)
    db.commit()
    consultas.invalidar_cache()
    log.info("Cierres eliminar huérfanos | ejercicio=%d borrados=%d user='%s'",
             body.ejercicio, res["borrados"], user.username)
    return res


class Ejercicio(BaseModel):
    ejercicio: int


@router.post("/desconciliar-ejercicio")
def post_desconciliar(body: Ejercicio, db: Session = Depends(get_db),
                      user: User = Depends(require_gestor_or_admin)):
    res = consultas.desconciliar_ejercicio(db, body.ejercicio)
    db.commit()
    consultas.invalidar_cache()
    log.warning("Cierres desconciliar ejercicio | ejercicio=%d apuntes=%d user='%s'",
                body.ejercicio, res["desconciliados"], user.username)
    return res


# ── Punteo automático ────────────────────────────────────────────────────────

@router.get("/reglas")
def get_reglas(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return punteo.listar_reglas(db)


class ReglaCambio(BaseModel):
    active: Optional[bool] = None
    tolerance_amount: Optional[float] = None
    description: Optional[str] = None


@router.put("/reglas/{codigo}")
def put_regla(codigo: str, body: ReglaCambio, db: Session = Depends(get_db),
              user: User = Depends(require_gestor_or_admin)):
    try:
        punteo.actualizar_regla(db, codigo, body.active, body.tolerance_amount, body.description)
    except ValueError as e:
        _400(e)
    db.commit()
    log.info("Cierres regla | %s %s user='%s'", codigo, body.model_dump(exclude_none=True), user.username)
    return {"ok": True}


class PunteoPeticion(BaseModel):
    ejercicios: list[int] = Field(..., min_length=1)
    filtro_cuentas: list[str] = Field(default_factory=lambda: ["*"])
    controles: list[str] = Field(default_factory=lambda: ["C", "D", "K", "L"])


@router.post("/punteo")
def post_punteo(body: PunteoPeticion, user: User = Depends(require_gestor_or_admin)):
    from ..services.cierres.reglas._comun import filtro_cuentas_sql
    try:
        filtro_cuentas_sql(body.filtro_cuentas)  # valida antes de lanzar
        if any(c not in CONTROLES for c in body.controles):
            raise ValueError("Control desconocido")
    except ValueError as e:
        _400(e)
    log.info("Cierres punteo | ejercicios=%s filtro=%s controles=%s user='%s'",
             body.ejercicios, body.filtro_cuentas, body.controles, user.username)
    try:
        tid = tareas.lanzar("punteo", punteo.tarea_punteo, engine, body.ejercicios,
                            body.filtro_cuentas, body.controles, escribe=True, usuario=user.username)
    except tareas.TareaOcupada as e:
        _ocupado(e)
    return {"task_id": tid}


@router.get("/incidencias/resumen")
def get_incidencias(ejercicio: Optional[int] = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return resumen_incidencias(db, ejercicio)


@router.get("/cuentas-control")
def get_cuentas_control(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return punteo.listar_cuentas_control(db)


class CuentaControl(BaseModel):
    tipo: str
    cuenta: str
    name: Optional[str] = ""
    min_mov: Optional[int] = None
    max_mov: Optional[int] = None
    tolerance_pct: Optional[float] = None
    active: bool = True


@router.post("/cuentas-control")
def post_cuenta_control(body: CuentaControl, db: Session = Depends(get_db),
                        _=Depends(require_gestor_or_admin)):
    try:
        id_ = punteo.guardar_cuenta_control(db, body.model_dump())
    except ValueError as e:
        _400(e)
    db.commit()
    return {"id": id_}


@router.put("/cuentas-control/{id_}")
def put_cuenta_control(id_: int, body: CuentaControl, db: Session = Depends(get_db),
                       _=Depends(require_gestor_or_admin)):
    try:
        punteo.guardar_cuenta_control(db, body.model_dump(), id_)
    except ValueError as e:
        _400(e)
    db.commit()
    return {"id": id_}


@router.delete("/cuentas-control/{id_}")
def delete_cuenta_control(id_: int, db: Session = Depends(get_db), _=Depends(require_gestor_or_admin)):
    punteo.borrar_cuenta_control(db, id_)
    db.commit()
    return {"ok": True}


# ── Punteo manual ────────────────────────────────────────────────────────────

class FiltroManual(BaseModel):
    ejercicios: list[int] = Field(default_factory=list)
    cuenta: Optional[str] = None
    recibo: Optional[str] = None
    asiento: Optional[str] = None
    concepto: Optional[str] = None
    solo_pendientes: bool = True


class BusquedaManual(FiltroManual):
    page: int = Field(1, ge=1)
    page_size: int = Field(200, ge=10, le=1000)


@router.post("/manual/buscar")
def post_manual_buscar(body: BusquedaManual, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return consultas.buscar_manual(db, body.model_dump(), body.page, body.page_size)
    except ValueError as e:
        _400(e)


@router.post("/manual/ids")
def post_manual_ids(body: FiltroManual, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return consultas.ids_manual(db, body.model_dump())
    except ValueError as e:
        _400(e)


class Seleccion(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=consultas.MAX_SELECCION)


@router.post("/manual/resumen")
def post_manual_resumen(body: Seleccion, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return consultas.resumen_seleccion(db, body.ids)


class PunteoManual(Seleccion):
    tolerancia: float = Field(0.20, ge=0, le=10000)


@router.post("/manual/puntear")
def post_manual_puntear(body: PunteoManual, db: Session = Depends(get_db),
                        user: User = Depends(require_gestor_or_admin)):
    try:
        res = consultas.puntear_manual(db, body.ids, body.tolerancia)
    except ValueError as e:
        _400(e)
    db.commit()
    consultas.invalidar_cache()
    log.info("Cierres punteo manual | grupo=%s apuntes=%d user='%s'", res["grupo"], res["punteados"], user.username)
    return res


class CambioCuenta(BaseModel):
    cuenta: str


@router.put("/apuntes/{apunte_id}/cuenta")
def put_cuenta_apunte(apunte_id: int, body: CambioCuenta, db: Session = Depends(get_db),
                      user: User = Depends(require_gestor_or_admin)):
    try:
        res = consultas.cambiar_cuenta_572(db, apunte_id, body.cuenta)
    except ValueError as e:
        _400(e)
    db.commit()
    consultas.invalidar_cache()
    log.info("Cierres cambio cuenta | %s user='%s'", res, user.username)
    return res


@router.post("/manual/excel")
def post_manual_excel(body: Seleccion, db: Session = Depends(get_db), _=Depends(get_current_user)):
    ruta = tareas.ruta_descarga("seleccion_manual.xlsx")
    excel.excel_seleccion_manual(db, body.ids, ruta)
    return FileResponse(ruta, filename="Seleccion_Manual.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── Ver conciliados ──────────────────────────────────────────────────────────

@router.get("/conciliados/reglas")
def get_reglas_punteo(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return consultas.reglas_con_punteo(db)


@router.get("/conciliados/bloques")
def get_bloques(
    ejercicio: Optional[int] = None,
    regla: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=10, le=1000),
    refrescar: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return consultas.listar_bloques(db, ejercicio, regla, page, page_size, refrescar)


@router.get("/conciliados/bloque")
def get_bloque(grupo: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return consultas.detalle_bloque(db, grupo)


@router.post("/conciliados/excel")
def post_conciliados_excel(ejercicio: Optional[int] = None, regla: Optional[str] = None,
                           user: User = Depends(get_current_user)):
    nombre = f"conciliados_{ejercicio or 'todos'}_{regla or 'todas_reglas'}.xlsx"

    def generar(progreso):
        ruta = tareas.ruta_descarga(nombre)
        with engine.connect() as conn:
            res = excel.excel_conciliados(conn, ejercicio, regla, ruta, progreso)
        return res | {"archivo": ruta, "nombre": nombre}

    return {"task_id": tareas.lanzar("excel", generar, usuario=user.username)}
