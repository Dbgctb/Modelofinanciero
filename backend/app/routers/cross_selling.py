"""
Router de Cross-selling y Alertas de Fuga.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..core.limiter import limiter
from ..models.cliente import (
    AccionComercial, Cliente, CrossSellingOportunidad, CrossSellingParametros,
    EstadoAccion, FugaAlerta, TipoAccion,
)
from ..models.recibo import Recibo
from ..models.user import User
from ..services.carga_clientes import cargar_csv_clientes
from ..services.cross_selling import DEFAULT_MATRIZ, recalcular_cross_selling, calcular_ramo_stats

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cross-selling", tags=["Cross-selling"])

ALLOWED_CLIENT_MIME = {
    "text/csv", "application/csv", "text/plain",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
MAX_CLIENT_FILE = 10 * 1024 * 1024  # 10 MB


# ── Schemas Pydantic ──────────────────────────────────────────────────────────

class ParametrosIn(BaseModel):
    peso_afinidad: float = 0.25
    peso_propension: float = 0.30
    peso_valor: float = 0.25
    peso_timing: float = 0.20
    umbral_bajada_prima: float = 0.10
    umbral_subida_prima_riesgo: float = 0.20
    dias_vencimiento_urgente: int = 90
    dias_vencimiento_medio: int = 180
    dias_inactividad_riesgo: int = 540
    matriz_afinidad: list = []


class AccionIn(BaseModel):
    tipo: TipoAccion
    oportunidad_id: Optional[UUID] = None
    alerta_id: Optional[UUID] = None
    tomador: str
    ramo_objetivo: Optional[str] = None
    estado: EstadoAccion = EstadoAccion.PENDIENTE
    notas: Optional[str] = None
    margen_conseguido: Optional[float] = None


class AccionUpdate(BaseModel):
    estado: Optional[EstadoAccion] = None
    notas: Optional[str] = None
    margen_conseguido: Optional[float] = None


class AuxiliarPartIn(BaseModel):
    auxiliar: str
    participa: bool


# ── Utilidades ────────────────────────────────────────────────────────────────

def _ser_oportunidad(o: CrossSellingOportunidad, tiene_accion: bool) -> dict:
    return {
        "id": str(o.id),
        "tomador": o.tomador,
        "auxiliar": o.auxiliar,
        "ramo_recomendado": o.ramo_recomendado,
        "score": o.score,
        "score_afinidad": o.score_afinidad,
        "score_propension": o.score_propension,
        "score_valor": o.score_valor,
        "score_timing": o.score_timing,
        "margen_esperado": o.margen_esperado,
        "prima_esperada": o.prima_esperada,
        "prima_total_activa": o.prima_total_activa,
        "ramos_actuales": o.ramos_actuales or [],
        "subramos_vigentes": o.subramos_vigentes or {},
        "n_ramos": o.n_ramos,
        "antiguedad_anos": o.antiguedad_anos,
        "tipo_cliente": o.tipo_cliente,
        "motivo": o.motivo,
        "accion_sugerida": o.accion_sugerida,
        "recalculado_at": o.recalculado_at.isoformat() if o.recalculado_at else None,
        "tiene_accion_activa": tiene_accion,
    }


def _ser_alerta(a: FugaAlerta) -> dict:
    return {
        "id": str(a.id),
        "tomador": a.tomador,
        "risk_score": a.risk_score,
        "valor_protegido": a.valor_protegido,
        "prioridad": a.prioridad,
        "senales": a.senales or [],
        "accion_recomendada": a.accion_recomendada,
        "dias_hasta_vencimiento": a.dias_hasta_vencimiento,
        "prima_total_activa": a.prima_total_activa,
        "liqui_vigente": a.liqui_vigente,
        "n_ramos": a.n_ramos,
        "antiguedad_anos": a.antiguedad_anos,
        "tipo_cliente": a.tipo_cliente,
        "auxiliar": a.auxiliar,
        "ramos_actuales": a.ramos_actuales or [],
        "recalculado_at": a.recalculado_at.isoformat() if a.recalculado_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ejercicios")
def get_ejercicios(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.query(Recibo.ejercicio).distinct().order_by(Recibo.ejercicio.desc()).all()
    return [r[0] for r in rows]


@router.get("/parametros")
def get_parametros(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    p = db.query(CrossSellingParametros).first()
    if not p:
        return {
            "peso_afinidad": 0.25, "peso_propension": 0.30,
            "peso_valor": 0.25, "peso_timing": 0.20,
            "umbral_bajada_prima": 0.10, "umbral_subida_prima_riesgo": 0.20,
            "dias_vencimiento_urgente": 90, "dias_vencimiento_medio": 180,
            "dias_inactividad_riesgo": 540,
            "matriz_afinidad": DEFAULT_MATRIZ,
        }
    return {
        "peso_afinidad": p.peso_afinidad,
        "peso_propension": p.peso_propension,
        "peso_valor": p.peso_valor,
        "peso_timing": p.peso_timing,
        "umbral_bajada_prima": p.umbral_bajada_prima,
        "umbral_subida_prima_riesgo": p.umbral_subida_prima_riesgo,
        "dias_vencimiento_urgente": p.dias_vencimiento_urgente,
        "dias_vencimiento_medio": p.dias_vencimiento_medio,
        "dias_inactividad_riesgo": p.dias_inactividad_riesgo,
        "matriz_afinidad": p.matriz_afinidad or DEFAULT_MATRIZ,
    }


@router.put("/parametros")
def update_parametros(
    data: ParametrosIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    p = db.query(CrossSellingParametros).filter(CrossSellingParametros.id == 1).first()
    if not p:
        p = CrossSellingParametros(id=1)
        db.add(p)

    p.peso_afinidad = data.peso_afinidad
    p.peso_propension = data.peso_propension
    p.peso_valor = data.peso_valor
    p.peso_timing = data.peso_timing
    p.umbral_bajada_prima = data.umbral_bajada_prima
    p.umbral_subida_prima_riesgo = data.umbral_subida_prima_riesgo
    p.dias_vencimiento_urgente = data.dias_vencimiento_urgente
    p.dias_vencimiento_medio = data.dias_vencimiento_medio
    p.dias_inactividad_riesgo = data.dias_inactividad_riesgo
    if data.matriz_afinidad:
        p.matriz_afinidad = data.matriz_afinidad
    db.commit()
    return {"mensaje": "Parámetros actualizados"}


@router.post("/recalcular")
@limiter.limit("3/minute")
def recalcular(
    request: Request,
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    try:
        result = recalcular_cross_selling(db, ejercicio)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        log.error("ERR_CS_RECALCULAR | ejercicio=%d error=%s", ejercicio, str(e))
        raise HTTPException(status_code=500, detail="Error al recalcular. Revisa los logs.")


@router.get("/oportunidades")
def get_oportunidades(
    ejercicio: int = Query(...),
    ramo: Optional[str] = Query(None),
    score_min: float = Query(0.0, ge=0.0, le=100.0),
    sin_accionar: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(CrossSellingOportunidad).filter(
        CrossSellingOportunidad.ejercicio == ejercicio,
        CrossSellingOportunidad.score >= score_min,
    )
    if ramo:
        q = q.filter(CrossSellingOportunidad.ramo_recomendado == ramo.upper())

    oportunidades = q.order_by(CrossSellingOportunidad.score.desc()).all()

    # Qué oportunidades tienen acción activa (no terminal)
    estados_activos = {EstadoAccion.PENDIENTE, EstadoAccion.CONTACTADO, EstadoAccion.PROPUESTA}
    ids_con_accion: set = set()
    if oportunidades:
        oport_ids = [o.id for o in oportunidades]
        acciones = db.query(AccionComercial).filter(
            AccionComercial.oportunidad_id.in_(oport_ids),
            AccionComercial.estado.in_(estados_activos),
        ).all()
        ids_con_accion = {a.oportunidad_id for a in acciones}

    # Sub-ramos disponibles por categoría (para enriquecer la columna "Recomendar")
    from ..models.cliente import RamoStatsEjercicio
    from collections import defaultdict as _dd
    cat_subs: dict = _dd(list)
    for s in db.query(RamoStatsEjercicio).filter(RamoStatsEjercicio.ejercicio == ejercicio).all():
        if s.ramo_categoria and s.ramo:
            cat_subs[s.ramo_categoria].append(s.ramo)

    resultado = []
    for o in oportunidades:
        tiene = o.id in ids_con_accion
        if sin_accionar and tiene:
            continue
        row = _ser_oportunidad(o, tiene)
        row['subramos_recomendados'] = cat_subs.get(o.ramo_recomendado, [])
        resultado.append(row)

    return resultado


@router.get("/alertas")
def get_alertas(
    ejercicio: int = Query(...),
    risk_min: float = Query(0.0, ge=0.0, le=100.0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    alertas = (
        db.query(FugaAlerta)
        .filter(
            FugaAlerta.ejercicio == ejercicio,
            FugaAlerta.risk_score >= risk_min,
            FugaAlerta.prima_total_activa > 0,  # solo clientes con pólizas vigentes
        )
        .order_by(FugaAlerta.prioridad.desc())
        .all()
    )
    return [_ser_alerta(a) for a in alertas]


@router.get("/auxiliares")
def get_auxiliares(
    ejercicio: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Lista todos los auxiliares (ente) encontrados en recibos con su estado de participación."""
    from ..models.cliente import AuxiliarParticipacion
    from sqlalchemy import func as sqlfunc

    q = db.query(Recibo.ente, sqlfunc.count(Recibo.id), sqlfunc.sum(Recibo.pr_total))
    if ejercicio:
        q = q.filter(Recibo.ejercicio == ejercicio)
    q = q.filter(Recibo.ente.isnot(None)).group_by(Recibo.ente)
    rows = q.all()

    part_db = {a.auxiliar: a.participa for a in db.query(AuxiliarParticipacion).all()}

    resultado = [
        {
            "auxiliar": ente,
            "participa": part_db.get(ente, True),
            "n_recibos": n,
            "prima_total": round(float(prima or 0), 2),
        }
        for ente, n, prima in rows
    ]
    return sorted(resultado, key=lambda x: x["prima_total"], reverse=True)


@router.patch("/auxiliares/participacion")
def update_auxiliar_participacion(
    data: AuxiliarPartIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    from ..models.cliente import AuxiliarParticipacion
    existing = db.query(AuxiliarParticipacion).filter(
        AuxiliarParticipacion.auxiliar == data.auxiliar
    ).first()
    if existing:
        existing.participa = data.participa
    else:
        db.add(AuxiliarParticipacion(auxiliar=data.auxiliar, participa=data.participa))
    db.commit()
    return {"ok": True}


@router.get("/ramo-stats")
def get_ramo_stats(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from ..models.cliente import RamoStatsEjercicio
    rows = (
        db.query(RamoStatsEjercicio)
        .filter(RamoStatsEjercicio.ejercicio == ejercicio)
        .order_by(RamoStatsEjercicio.prima_media.desc())
        .all()
    )
    return [
        {
            "ramo": r.ramo,
            "ramo_categoria": r.ramo_categoria,
            "prima_media": r.prima_media,
            "margen_medio": r.margen_medio,
            "n_clientes": r.n_clientes,
        }
        for r in rows
    ]


@router.post("/ramo-stats/calcular")
def calcular_stats_ramo(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    try:
        resultado = calcular_ramo_stats(db, ejercicio)
        db.commit()
        return {"ejercicio": ejercicio, "ramos": resultado}
    except Exception as e:
        db.rollback()
        log.error("ERR_RAMO_STATS | ejercicio=%d error=%s", ejercicio, str(e))
        raise HTTPException(status_code=500, detail="Error al calcular estadísticas de ramo.")


@router.get("/ocurrencias")
def get_ocurrencias(
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from collections import defaultdict as _dd
    oportunidades = (
        db.query(CrossSellingOportunidad)
        .filter(CrossSellingOportunidad.ejercicio == ejercicio)
        .all()
    )

    por_ramo: dict = _dd(lambda: {"n_clientes": 0, "prima_potencial": 0.0, "margen_potencial": 0.0})
    por_combinacion: dict = _dd(lambda: {"n_clientes": 0, "prima_potencial": 0.0})

    for o in oportunidades:
        r = o.ramo_recomendado
        por_ramo[r]["n_clientes"] += 1
        por_ramo[r]["prima_potencial"] += o.prima_esperada or 0.0
        por_ramo[r]["margen_potencial"] += o.margen_esperado or 0.0
        for ramo_base in (o.ramos_actuales or []):
            key = f"{ramo_base}→{r}"
            por_combinacion[key]["n_clientes"] += 1
            por_combinacion[key]["prima_potencial"] += o.prima_esperada or 0.0

    return {
        "por_ramo_recomendado": sorted(
            [
                {
                    "ramo": ramo,
                    "n_clientes": d["n_clientes"],
                    "prima_potencial": round(d["prima_potencial"], 2),
                    "margen_potencial": round(d["margen_potencial"], 2),
                }
                for ramo, d in por_ramo.items()
            ],
            key=lambda x: x["n_clientes"],
            reverse=True,
        ),
        "por_combinacion": sorted(
            [
                {
                    "combinacion": k,
                    "ramo_base": k.split("→")[0],
                    "ramo_objetivo": k.split("→")[1],
                    "n_clientes": d["n_clientes"],
                    "prima_potencial": round(d["prima_potencial"], 2),
                }
                for k, d in por_combinacion.items()
            ],
            key=lambda x: x["n_clientes"],
            reverse=True,
        )[:40],
    }


@router.get("/efectividad")
def get_efectividad(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import func as sqlfunc

    acciones = db.query(AccionComercial).all()

    cs = [a for a in acciones if a.tipo == TipoAccion.CROSS_SELLING]
    ret = [a for a in acciones if a.tipo == TipoAccion.RETENCION]

    estados_no_terminal = {EstadoAccion.PENDIENTE, EstadoAccion.CONTACTADO, EstadoAccion.PROPUESTA}

    cs_accionadas = [a for a in cs if a.estado not in estados_no_terminal]
    cs_ganadas = [a for a in cs if a.estado == EstadoAccion.GANADO]
    cs_perdidas = [a for a in cs if a.estado == EstadoAccion.PERDIDO]
    cs_en_curso = [a for a in cs if a.estado in estados_no_terminal]

    tasa_cs = len(cs_ganadas) / len(cs_accionadas) if cs_accionadas else 0.0
    margen_inc = sum(a.margen_conseguido or 0 for a in cs_ganadas)

    ret_accionadas = [a for a in ret if a.estado not in estados_no_terminal]
    ret_retenidas = [a for a in ret if a.estado == EstadoAccion.GANADO]
    valor_recuperado = sum(a.margen_conseguido or 0 for a in ret_retenidas)

    # Por ramo
    ramo_stats: dict = {}
    for a in cs:
        ramo = a.ramo_objetivo or "DESCONOCIDO"
        if ramo not in ramo_stats:
            ramo_stats[ramo] = {"oportunidades": 0, "ganadas": 0}
        ramo_stats[ramo]["oportunidades"] += 1
        if a.estado == EstadoAccion.GANADO:
            ramo_stats[ramo]["ganadas"] += 1

    por_ramo = [
        {
            "ramo": ramo,
            "oportunidades": stats["oportunidades"],
            "ganadas": stats["ganadas"],
            "tasa": round(stats["ganadas"] / stats["oportunidades"] * 100, 1)
            if stats["oportunidades"] > 0 else 0.0,
        }
        for ramo, stats in sorted(ramo_stats.items(), key=lambda x: x[1]["ganadas"], reverse=True)
    ]

    return {
        "cross_selling": {
            "total": len(cs),
            "accionadas": len(cs_accionadas),
            "ganadas": len(cs_ganadas),
            "perdidas": len(cs_perdidas),
            "en_curso": len(cs_en_curso),
            "tasa_conversion": round(tasa_cs * 100, 1),
            "margen_incremental": round(margen_inc, 2),
        },
        "retencion": {
            "total": len(ret),
            "accionadas": len(ret_accionadas),
            "retenidas": len(ret_retenidas),
            "valor_protegido_recuperado": round(valor_recuperado, 2),
        },
        "por_ramo": por_ramo,
    }


@router.get("/clientes")
def get_clientes(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
    return [
        {
            "id": str(c.id),
            "codigo_cliente": c.codigo_cliente,
            "nombre": c.nombre,
            "nombre_normalizado": c.nombre_normalizado,
            "fecha_alta": c.fecha_alta.isoformat() if c.fecha_alta else None,
            "fecha_nacimiento": c.fecha_nacimiento.isoformat() if c.fecha_nacimiento else None,
            "tipo": c.tipo.value,
        }
        for c in clientes
    ]


@router.post("/clientes/carga")
async def upload_clientes(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    contenido = await file.read()
    if len(contenido) == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if file.content_type not in ALLOWED_CLIENT_MIME:
        raise HTTPException(status_code=415, detail="Tipo de archivo no permitido. Se esperaba CSV o Excel.")
    if len(contenido) > MAX_CLIENT_FILE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máximo 10 MB).")

    try:
        insertados, actualizados = cargar_csv_clientes(db, contenido)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        db.rollback()
        log.error("ERR_CARGA_CLIENTES | fichero='%s' error='%s'", file.filename, str(e))
        raise HTTPException(status_code=422, detail="Error procesando el archivo de clientes.")

    return {
        "mensaje": f"Clientes cargados correctamente",
        "insertados": insertados,
        "actualizados": actualizados,
    }


@router.post("/acciones")
def create_accion(
    data: AccionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accion = AccionComercial(
        tipo=data.tipo,
        oportunidad_id=data.oportunidad_id,
        alerta_id=data.alerta_id,
        tomador=data.tomador,
        ramo_objetivo=data.ramo_objetivo,
        estado=data.estado,
        notas=data.notas,
        margen_conseguido=data.margen_conseguido,
        usuario_id=current_user.id,
    )
    db.add(accion)
    db.commit()
    db.refresh(accion)
    return {"id": str(accion.id), "estado": accion.estado.value}


@router.get("/cliente-detalle")
def cliente_detalle(
    tomador: str = Query(...),
    ejercicio: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Desglose completo de recibos, prima y margen de un cliente en un ejercicio."""
    from ..services.cross_selling import _norm_nombre, _normalizar_ramo
    from datetime import date

    hoy = date.today()
    tomador_norm = _norm_nombre(tomador)

    todos_recibos = db.query(Recibo).filter(
        Recibo.ejercicio == ejercicio,
        Recibo.pr_total.isnot(None),
    ).all()

    recibos_cliente = [
        r for r in todos_recibos
        if r.tomador and _norm_nombre(r.tomador) == tomador_norm
    ]

    recibos_vigentes = [r for r in recibos_cliente if r.hasta and r.hasta >= hoy]

    def _fmt(r: Recibo) -> dict:
        return {
            "codigo": r.codigo,
            "numero_poliza": r.numero_poliza,
            "compania": r.compania,
            "ramo": r.ramo,
            "ramo_norm": _normalizar_ramo(r.ramo or ''),
            "auxiliar": r.ente,
            "pr_total": float(r.pr_total or 0),
            "pr_neto": float(r.pr_neto or 0) if r.pr_neto is not None else None,
            "liqui": float(r.liqui or 0) if r.liqui is not None else None,
            "desde": r.desde.isoformat() if r.desde else None,
            "hasta": r.hasta.isoformat() if r.hasta else None,
            "vigente": bool(r.hasta and r.hasta >= hoy),
            "tipo_negocio": r.tipo_negocio,
        }

    prima_vigente = sum(float(r.pr_total or 0) for r in recibos_vigentes)
    prima_total_ej = sum(float(r.pr_total or 0) for r in recibos_cliente)
    liqui_vigente = sum(float(r.liqui or 0) for r in recibos_vigentes if r.liqui is not None)
    margen_pct = round(liqui_vigente / prima_vigente * 100, 1) if prima_vigente > 0 else None

    oportunidades = (
        db.query(CrossSellingOportunidad)
        .filter(
            CrossSellingOportunidad.ejercicio == ejercicio,
            CrossSellingOportunidad.tomador == tomador_norm,
        )
        .order_by(CrossSellingOportunidad.score.desc())
        .all()
    )

    alerta = db.query(FugaAlerta).filter(
        FugaAlerta.ejercicio == ejercicio,
        FugaAlerta.tomador == tomador_norm,
    ).first()

    return {
        "tomador": tomador,
        "ejercicio": ejercicio,
        "resumen": {
            "prima_vigente": round(prima_vigente, 2),
            "prima_total_ejercicio": round(prima_total_ej, 2),
            "liqui_vigente": round(liqui_vigente, 2),
            "margen_pct": margen_pct,
            "n_recibos_vigentes": len(recibos_vigentes),
            "n_recibos_ejercicio": len(recibos_cliente),
            "ramos_vigentes": list(set(_normalizar_ramo(r.ramo or '') for r in recibos_vigentes)),
        },
        "recibos": [
            _fmt(r)
            for r in sorted(recibos_cliente, key=lambda r: r.hasta or date.min, reverse=True)
        ],
        "oportunidades_score": [
            {"ramo": o.ramo_recomendado, "score": o.score, "motivo": o.motivo}
            for o in oportunidades
        ],
        "alerta_fuga": {
            "risk_score": alerta.risk_score,
            "senales": alerta.senales,
            "valor_protegido": alerta.valor_protegido,
        } if alerta else None,
    }


@router.patch("/acciones/{accion_id}")
def update_accion(
    accion_id: UUID,
    data: AccionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from datetime import datetime, timezone
    accion = db.query(AccionComercial).filter(AccionComercial.id == accion_id).first()
    if not accion:
        raise HTTPException(status_code=404, detail="Acción no encontrada")

    if data.estado is not None:
        accion.estado = data.estado
        if data.estado == EstadoAccion.CONTACTADO and not accion.fecha_contacto:
            accion.fecha_contacto = datetime.now(timezone.utc)
        if data.estado in (EstadoAccion.GANADO, EstadoAccion.PERDIDO, EstadoAccion.NO_INTERESADO):
            accion.fecha_cierre = datetime.now(timezone.utc)
    if data.notas is not None:
        accion.notas = data.notas
    if data.margen_conseguido is not None:
        accion.margen_conseguido = data.margen_conseguido

    db.commit()
    return {"id": str(accion.id), "estado": accion.estado.value}
