import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.carga import CargaContable, TipoCarga, EstadoCarga
from ..models.incidencia import Incidencia, EstadoIncidencia, TipoIncidencia
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..models.recibo import Recibo
from ..services.carga_recibos import cargar_csv_recibos
from ..services.carga_diario import procesar_diario_excel

router = APIRouter(prefix="/carga", tags=["Carga de datos"])
log = logging.getLogger(__name__)


def _calcular_totales_tipo(db: Session, carga_id) -> dict:
    """Calcula neto (Haber-Debe) separado por tipo de cuenta para una carga."""
    from sqlalchemy import func as sqlfunc
    rows = (
        db.query(DiarioApunte.tipo_cuenta, sqlfunc.sum(DiarioApunte.haber - DiarioApunte.debe))
        .filter(DiarioApunte.carga_id == carga_id)
        .group_by(DiarioApunte.tipo_cuenta)
        .all()
    )
    result = {"ingresos": 0.0, "gastos": 0.0}
    for tipo, neto in rows:
        if tipo == TipoCuenta.INGRESO:
            result["ingresos"] = float(neto or 0)
        elif tipo == TipoCuenta.GASTO:
            # Gastos: convención positiva = importe gastado (Debe - Haber)
            result["gastos"] = float(-(neto or 0))
    return result

ALLOWED_EXCEL = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"}
ALLOWED_CSV = {"text/csv", "application/csv", "text/plain"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB -- el CSV de recibos consolidado real pesa ~23 MB (reportado en vivo, 2026-10-10)


@router.post("/recibos")
async def upload_recibos(
    file: UploadFile = File(...),
    ejercicio: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Carga el CSV de recibos para un ejercicio."""
    contenido = await file.read()
    if len(contenido) == 0:
        log.warning("ERR_CARGA_ARCHIVO_VACIO | fichero='%s'", file.filename)
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if file.content_type not in ALLOWED_CSV:
        raise HTTPException(status_code=415, detail="Tipo de archivo no permitido. Se esperaba CSV.")
    if len(contenido) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máximo 20 MB).")

    log.info("Carga recibos iniciada | fichero='%s' ejercicio=%d user='%s'",
             file.filename, ejercicio, current_user.username)

    carga = CargaContable(
        ejercicio=ejercicio,
        tipo_carga=TipoCarga.RECIBOS,
        usuario_id=current_user.id,
        nombre_fichero=file.filename,
    )
    db.add(carga)
    db.flush()
    db.refresh(carga)

    try:
        insertados, actualizados = cargar_csv_recibos(db, contenido, ejercicio, carga)
        db.commit()
    except Exception as e:
        db.rollback()
        log.error("ERR_CARGA_PROCESO | fichero='%s' error='%s'", file.filename, str(e))
        raise HTTPException(status_code=422, detail="Error procesando el archivo. Revisa el formato e inténtalo de nuevo.")

    log.info("Carga recibos OK | carga_id='%s' insertados=%d actualizados=%d ejercicio=%d",
             carga.id, insertados, actualizados, ejercicio)
    return {
        "carga_id": str(carga.id),
        "mensaje": f"Recibos cargados para ejercicio {ejercicio}",
        "insertados": insertados,
        "actualizados": actualizados,
    }


@router.post("/diario")
async def upload_diario(
    file: UploadFile = File(...),
    ejercicio: int = Form(...),
    tipo_carga: TipoCarga = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Carga el Excel del diario contable y genera incidencias automáticamente.
    Si ya existen cargas del mismo ejercicio y tipo, se eliminan antes de procesar.
    """
    contenido = await file.read()
    if len(contenido) == 0:
        log.warning("ERR_CARGA_ARCHIVO_VACIO | fichero='%s'", file.filename)
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    log.info("Carga diario iniciada | fichero='%s' ejercicio=%d tipo='%s' user='%s'",
             file.filename, ejercicio, tipo_carga, current_user.username)

    if file.content_type not in ALLOWED_EXCEL:
        raise HTTPException(status_code=415, detail="Tipo de archivo no permitido. Se esperaba Excel (.xlsx).")
    if len(contenido) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máximo 20 MB).")

    # Eliminar cargas previas del mismo ejercicio+tipo para evitar duplicados.
    # No se hace commit intermedio: todo forma parte de la misma transacción.
    cargas_previas = db.query(CargaContable).filter(
        CargaContable.ejercicio == ejercicio,
        CargaContable.tipo_carga == tipo_carga,
    ).all()
    if cargas_previas:
        for c in cargas_previas:
            db.delete(c)
        log.info("Cargas previas eliminadas | ejercicio=%d tipo='%s' cantidad=%d",
                 ejercicio, tipo_carga, len(cargas_previas))

    carga = CargaContable(
        ejercicio=ejercicio,
        tipo_carga=tipo_carga,
        usuario_id=current_user.id,
        nombre_fichero=file.filename,
    )
    db.add(carga)
    db.flush()
    db.refresh(carga)

    try:
        correctos, con_incidencia = procesar_diario_excel(db, contenido, carga, ejercicio, tipo_carga=tipo_carga)
        db.commit()
    except Exception as e:
        db.rollback()
        log.error("ERR_CARGA_PROCESO | fichero='%s' error='%s'", file.filename, str(e))
        raise HTTPException(status_code=422, detail="Error procesando el archivo. Revisa el formato e inténtalo de nuevo.")

    log.info("Carga diario OK | carga_id='%s' correctos=%d incidencias=%d",
             carga.id, correctos, con_incidencia)
    totales_tipo = _calcular_totales_tipo(db, carga.id)
    return {
        "carga_id": str(carga.id),
        "ejercicio": ejercicio,
        "tipo_carga": tipo_carga.value,
        "estado": carga.estado.value,
        "total_registros": carga.total_registros,
        "registros_correctos": correctos,
        "registros_con_incidencia": con_incidencia,
        "importe_debe_total": float(carga.importe_debe_total or 0),
        "importe_haber_total": float(carga.importe_haber_total or 0),
        "total_ingresos_neto": totales_tipo["ingresos"],
        "total_gastos_neto": totales_tipo["gastos"],
    }


@router.get("/historial")
def historial_cargas(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    limit: int = 20,
):
    cargas = db.query(CargaContable).order_by(CargaContable.created_at.desc()).limit(limit).all()
    return [
        {
            "id": str(c.id),
            "ejercicio": c.ejercicio,
            "mes": c.mes,
            "tipo_carga": c.tipo_carga.value,
            "estado": c.estado.value,
            "nombre_fichero": c.nombre_fichero,
            "total_registros": c.total_registros,
            "registros_correctos": c.registros_correctos,
            "registros_con_incidencia": c.registros_con_incidencia,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cargas
    ]


@router.get("/historico")
def listar_historico_estadistico(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Lista los ejercicios históricos cargados para el modelo estadístico."""
    cargas = (
        db.query(CargaContable)
        .filter(CargaContable.tipo_carga == TipoCarga.HISTORICO_ESTADISTICO)
        .order_by(CargaContable.ejercicio.desc())
        .all()
    )
    return [
        {
            "id": str(c.id),
            "ejercicio": c.ejercicio,
            "estado": c.estado.value,
            "nombre_fichero": c.nombre_fichero,
            "total_registros": c.total_registros,
            "registros_correctos": c.registros_correctos,
            "registros_con_incidencia": c.registros_con_incidencia,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cargas
    ]


@router.delete("/historico/{carga_id}")
def eliminar_historico(
    carga_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Elimina una carga histórica estadística y sus apuntes asociados."""
    carga = db.query(CargaContable).filter(
        CargaContable.id == carga_id,
        CargaContable.tipo_carga == TipoCarga.HISTORICO_ESTADISTICO,
    ).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga histórica no encontrada")

    db.delete(carga)
    db.commit()
    log.info("Carga histórica eliminada | carga_id='%s'", carga_id)
    return {"mensaje": "Carga histórica eliminada"}


@router.delete("/{carga_id}")
def eliminar_carga(
    carga_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Elimina cualquier carga y sus apuntes asociados (en cascada)."""
    carga = db.query(CargaContable).filter(CargaContable.id == carga_id).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga no encontrada")

    db.delete(carga)
    db.commit()
    log.info("Carga eliminada | carga_id='%s' ejercicio=%d tipo='%s'",
             carga_id, carga.ejercicio, carga.tipo_carga)
    return {"mensaje": "Carga eliminada", "carga_id": str(carga_id)}


@router.delete("/ejercicio/{ejercicio}/purgar")
def purgar_ejercicio(
    ejercicio: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Elimina TODAS las cargas de un ejercicio (todos los tipos). Usar para limpiar datos incorrectos."""
    cargas = db.query(CargaContable).filter(CargaContable.ejercicio == ejercicio).all()
    if not cargas:
        raise HTTPException(status_code=404, detail=f"No hay cargas para el ejercicio {ejercicio}")

    cantidad = len(cargas)
    for c in cargas:
        db.delete(c)
    db.commit()
    log.info("Ejercicio purgado | ejercicio=%d cargas_eliminadas=%d", ejercicio, cantidad)
    return {"mensaje": f"Ejercicio {ejercicio} purgado", "cargas_eliminadas": cantidad}


@router.get("/{carga_id}/incidencias")
def listar_incidencias(
    carga_id: UUID,
    tipo: TipoIncidencia | None = None,
    estado: EstadoIncidencia | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Incidencia, DiarioApunte).join(
        DiarioApunte, Incidencia.apunte_id == DiarioApunte.id, isouter=True
    ).filter(Incidencia.carga_id == carga_id)

    if tipo:
        q = q.filter(Incidencia.tipo == tipo)
    if estado:
        q = q.filter(Incidencia.estado == estado)

    resultados = q.order_by(Incidencia.created_at).all()

    return [
        {
            "id": str(inc.id),
            "tipo": inc.tipo.value,
            "es_critica": inc.es_critica,
            "descripcion": inc.descripcion,
            "estado": inc.estado.value,
            "apunte": {
                "numero_cuenta": ap.numero_cuenta if ap else None,
                "concepto": ap.concepto if ap else None,
                "fecha": ap.fecha.isoformat() if ap and ap.fecha else None,
                "debe": float(ap.debe or 0) if ap else 0,
                "haber": float(ap.haber or 0) if ap else 0,
            } if ap else None,
        }
        for inc, ap in resultados
    ]


@router.patch("/{carga_id}/incidencias/{incidencia_id}/resolver")
def resolver_incidencia(
    carga_id: UUID,
    incidencia_id: UUID,
    resolucion: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    from datetime import datetime, timezone
    inc = db.query(Incidencia).filter(
        Incidencia.id == incidencia_id,
        Incidencia.carga_id == carga_id,
    ).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    inc.estado = EstadoIncidencia.RESUELTA
    inc.resolucion = resolucion
    inc.resuelta_por_id = current_user.id
    inc.fecha_resolucion = datetime.now(timezone.utc)
    db.commit()
    return {"mensaje": "Incidencia resuelta"}


@router.patch("/{carga_id}/cerrar")
def cerrar_carga(
    carga_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Cierra definitivamente una carga base presupuestaria para habilitar la presupuestación."""
    carga = db.query(CargaContable).filter(CargaContable.id == carga_id).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga no encontrada")
    if carga.tipo_carga != TipoCarga.BASE_PRESUPUESTARIA:
        raise HTTPException(status_code=400, detail="Solo se pueden cerrar cargas de tipo base presupuestaria")
    if carga.estado == EstadoCarga.CERRADO:
        raise HTTPException(status_code=400, detail="La carga ya está cerrada")

    criticas_pendientes = db.query(Incidencia).filter(
        Incidencia.carga_id == carga_id,
        Incidencia.es_critica == 'si',
        Incidencia.estado == EstadoIncidencia.PENDIENTE,
    ).count()
    if criticas_pendientes > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Hay {criticas_pendientes} incidencias críticas pendientes. Resuélvelas antes de cerrar.",
        )

    carga.estado = EstadoCarga.CERRADO
    db.commit()
    log.info("Carga cerrada | carga_id='%s' user='%s'", carga_id, current_user.username)
    return {"mensaje": "Carga cerrada definitivamente", "carga_id": str(carga_id)}


@router.get("/{carga_id}/recibos")
def detalle_recibos(
    carga_id: UUID,
    tipo_negocio: Optional[str] = Query(None),
    ramo: Optional[str] = Query(None),
    compania: Optional[str] = Query(None),
    ejercicio: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    carga = db.query(CargaContable).filter(
        CargaContable.id == carga_id,
        CargaContable.tipo_carga == TipoCarga.RECIBOS,
    ).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga de recibos no encontrada")

    # Recibo.ejercicio es el año de efecto de cada recibo, no el de la carga (un
    # fichero trae varios años), así que el año es un filtro opcional.
    q = db.query(Recibo)
    if ejercicio is not None:
        q = q.filter(Recibo.ejercicio == ejercicio)
    if tipo_negocio:
        q = q.filter(Recibo.tipo_negocio == tipo_negocio)
    if ramo:
        q = q.filter(Recibo.ramo == ramo)
    if compania:
        q = q.filter(Recibo.compania.ilike(f"%{compania}%"))

    total = q.count()
    recibos = q.order_by(Recibo.codigo).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "carga": {
            "id": str(carga.id),
            "ejercicio": carga.ejercicio,
            "nombre_fichero": carga.nombre_fichero,
            "total_registros": carga.total_registros,
            "created_at": carga.created_at.isoformat() if carga.created_at else None,
        },
        "recibos": [
            {
                "codigo": r.codigo,
                "recibo_cia": r.recibo_cia,
                "compania": r.compania,
                "tomador": r.tomador,
                "producto": r.producto,
                "ramo": r.ramo,
                "tipo_negocio": r.tipo_negocio,
                "pr_total": float(r.pr_total or 0),
                "pr_neto": float(r.pr_neto or 0),
                "desde": r.desde.isoformat() if r.desde else None,
                "hasta": r.hasta.isoformat() if r.hasta else None,
                "cobro": r.cobro,
                "estado": r.estado,
            }
            for r in recibos
        ],
    }


@router.get("/{carga_id}/apuntes")
def detalle_apuntes(
    carga_id: UUID,
    estado: Optional[EstadoApunte] = Query(None),
    tipo_cuenta: Optional[TipoCuenta] = Query(None),
    mes: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    carga = db.query(CargaContable).filter(CargaContable.id == carga_id).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga no encontrada")

    q = db.query(DiarioApunte).filter(DiarioApunte.carga_id == carga_id)
    if estado:
        q = q.filter(DiarioApunte.estado == estado)
    if tipo_cuenta:
        q = q.filter(DiarioApunte.tipo_cuenta == tipo_cuenta)
    if mes:
        q = q.filter(DiarioApunte.mes == mes)

    total = q.count()
    apuntes = q.order_by(DiarioApunte.linea, DiarioApunte.fecha).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "carga": {
            "id": str(carga.id),
            "ejercicio": carga.ejercicio,
            "tipo_carga": carga.tipo_carga.value,
            "nombre_fichero": carga.nombre_fichero,
            "total_registros": carga.total_registros,
            "registros_correctos": carga.registros_correctos,
            "registros_con_incidencia": carga.registros_con_incidencia,
            "importe_debe_total": float(carga.importe_debe_total or 0),
            "importe_haber_total": float(carga.importe_haber_total or 0),
            "created_at": carga.created_at.isoformat() if carga.created_at else None,
        },
        "apuntes": [
            {
                "id": str(a.id),
                "linea": a.linea,
                "fecha": a.fecha.isoformat() if a.fecha else None,
                "mes": a.mes,
                "numero_cuenta": a.numero_cuenta,
                "descripcion_cuenta": a.descripcion_cuenta,
                "concepto": a.concepto,
                "debe": float(a.debe or 0),
                "haber": float(a.haber or 0),
                "tipo_cuenta": a.tipo_cuenta.value if a.tipo_cuenta else None,
                "compania": a.compania,
                "codigo_recibo": a.codigo_recibo,
                "ramo": a.ramo,
                "tipo_negocio": a.tipo_negocio,
                "familia_gasto": a.familia_gasto,
                "estado": a.estado.value if a.estado else None,
            }
            for a in apuntes
        ],
    }


@router.get("/{carga_id}/resumen")
def resumen_carga(
    carga_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    carga = db.query(CargaContable).filter(CargaContable.id == carga_id).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga no encontrada")

    pendientes_criticas = db.query(Incidencia).filter(
        Incidencia.carga_id == carga_id,
        Incidencia.es_critica == 'si',
        Incidencia.estado == EstadoIncidencia.PENDIENTE,
    ).count()

    por_tipo = db.query(Incidencia.tipo, Incidencia.es_critica).filter(
        Incidencia.carga_id == carga_id,
        Incidencia.estado == EstadoIncidencia.PENDIENTE,
    ).all()

    conteo = {}
    for tipo, critica in por_tipo:
        conteo[tipo.value] = conteo.get(tipo.value, 0) + 1

    totales_tipo = _calcular_totales_tipo(db, carga_id)
    return {
        "carga_id": str(carga_id),
        "estado": carga.estado.value,
        "puede_validar": pendientes_criticas == 0,
        "incidencias_criticas_pendientes": pendientes_criticas,
        "incidencias_por_tipo": conteo,
        "totales": {
            "registros": carga.total_registros,
            "correctos": carga.registros_correctos,
            "con_incidencia": carga.registros_con_incidencia,
            "debe": float(carga.importe_debe_total or 0),
            "haber": float(carga.importe_haber_total or 0),
            "total_ingresos_neto": totales_tipo["ingresos"],
            "total_gastos_neto": totales_tipo["gastos"],
        },
    }
