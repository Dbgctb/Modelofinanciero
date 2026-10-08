import time
from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from pydantic import BaseModel

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.presupuesto import (
    Presupuesto, PresupuestoIngreso, PresupuestoGasto,
    EstadoPresupuesto, TipoReglaGasto, DistribucionGasto,
    PresupuestoCesionAuxiliar, TipoPersonaAuxiliar,
)
from ..models.diario import DiarioApunte, EstadoApunte
from ..services.presupuesto_ingresos import (
    verificar_ejercicio_base_cerrado, crear_presupuesto,
    generar_lineas_ingresos, recalcular_linea,
    aplicar_coeficiente_masivo, calcular_metodologia,
    importar_lineas_ingresos_excel,
    MERCADO_REFERENCIA_ICEA, LAPSE_REFERENCIA,
)
from ..services.presupuesto_gastos import (
    generar_lineas_gastos, recalcular_linea_gasto, ajuste_manual_mes,
    generar_cesiones_auxiliar, recalcular_cesion, importar_cesiones_excel,
)

router = APIRouter(prefix="/presupuesto", tags=["Presupuestación"])


# ─────────────────────────────────────────────
# Presupuesto (cabecera)
# ─────────────────────────────────────────────

@router.get("/")
def listar_presupuestos(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    presupuestos = db.query(Presupuesto).order_by(Presupuesto.ejercicio.desc()).all()
    return [_serializar_presupuesto(p) for p in presupuestos]


@router.post("/iniciar")
def iniciar_presupuesto(
    ejercicio: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-ING-01/03: crea el presupuesto único si el ejercicio base está cerrado."""
    ejercicio_base = ejercicio - 1
    if not verificar_ejercicio_base_cerrado(db, ejercicio_base):
        raise HTTPException(
            status_code=409,
            detail=f"El ejercicio {ejercicio_base} no está cerrado. Cierra primero la carga base antes de presupuestar.",
        )
    presupuesto = crear_presupuesto(db, ejercicio, str(current_user.id))
    return _serializar_presupuesto(presupuesto)


@router.get("/{presupuesto_id}")
def detalle_presupuesto(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    p = _get_presupuesto(db, presupuesto_id)
    return _serializar_presupuesto(p)


# ─────────────────────────────────────────────
# Ingresos
# ─────────────────────────────────────────────

@router.post("/{presupuesto_id}/ingresos/generar")
def generar_ingresos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-ING-04 a RF-ING-13: genera líneas de ingresos desde el ejercicio base."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)
    t0 = time.monotonic()
    n = generar_lineas_ingresos(db, p)
    tiempo = round(time.monotonic() - t0, 1)
    return {"mensaje": f"{n} líneas generadas en {tiempo}s", "lineas": n, "tiempo_segundos": tiempo}


@router.get("/{presupuesto_id}/ingresos")
def listar_ingresos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lineas = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto_id
    ).order_by(PresupuestoIngreso.compania, PresupuestoIngreso.ramo).all()
    return [_serializar_ingreso(l) for l in lineas]


@router.patch("/{presupuesto_id}/ingresos/{linea_id}")
def actualizar_ingreso(
    presupuesto_id: UUID,
    linea_id: UUID,
    datos: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """RF-ING-17/18: actualiza parámetros de crecimiento de una línea y recalcula."""
    linea = _get_linea_ingreso(db, presupuesto_id, linea_id)
    if linea.bloqueado:
        raise HTTPException(status_code=400, detail="La línea está bloqueada tras aprobación")

    campos_permitidos = {
        'crecimiento_modelo', 'crecimiento_mercado', 'coeficiente_prudencia',
        'crecimiento_manual', 'atipicos_excluidos', 'notas', 'tasa_caida',
        'importes_mensuales',  # RF-ING-23: modificar meses concretos
    }
    for campo, valor in datos.items():
        if campo in campos_permitidos:
            setattr(linea, campo, valor)

    # Si se modifican importes directamente, recalcular total
    if 'importes_mensuales' in datos:
        importes = datos['importes_mensuales']
        if len(importes) == 12:
            linea.importes_mensuales = importes
            linea.total_anual = round(sum(importes), 2)
            db.commit()
            db.refresh(linea)
    else:
        # Recalcular con nuevos parámetros de crecimiento
        recalcular_linea(db, linea)

    return _serializar_ingreso(linea)


@router.post("/{presupuesto_id}/ingresos/aprobar")
def aprobar_ingresos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-ING-24: aprueba y bloquea el presupuesto de ingresos."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)

    lineas = db.query(PresupuestoIngreso).filter(PresupuestoIngreso.presupuesto_id == presupuesto_id).all()
    if not lineas:
        raise HTTPException(status_code=400, detail="No hay líneas de ingresos generadas")

    for l in lineas:
        l.bloqueado = True

    p.estado = EstadoPresupuesto.INGRESOS_APROBADOS
    p.ingresos_aprobados_por_id = current_user.id
    p.ingresos_aprobados_at = datetime.now(timezone.utc)
    db.commit()
    return {"mensaje": "Presupuesto de ingresos aprobado y bloqueado"}


@router.post("/{presupuesto_id}/ingresos/reabrir")
def reabrir_ingresos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Reabre el presupuesto de ingresos: desbloquea líneas y revierte estado a BORRADOR.
    Si los gastos también estaban aprobados, los desbloquea también."""
    p = _get_presupuesto(db, presupuesto_id)
    if p.estado == EstadoPresupuesto.BORRADOR:
        raise HTTPException(status_code=400, detail="El presupuesto de ingresos ya está abierto")

    # Desbloquear ingresos
    db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto_id,
    ).update({"bloqueado": False})

    # Si gastos, tesorería o cerrado, desbloquear todo
    if p.estado in (
        EstadoPresupuesto.GASTOS_APROBADOS,
        EstadoPresupuesto.TESORERIA_APROBADA,
        EstadoPresupuesto.CERRADO,
    ):
        db.query(PresupuestoGasto).filter(
            PresupuestoGasto.presupuesto_id == presupuesto_id,
        ).update({"bloqueado": False})
        db.query(PresupuestoCesionAuxiliar).filter(
            PresupuestoCesionAuxiliar.presupuesto_id == presupuesto_id,
        ).update({"bloqueado": False})
        p.gastos_aprobados_por_id = None
        p.gastos_aprobados_at = None
        p.cerrado_por_id = None
        p.cerrado_at = None

    p.estado = EstadoPresupuesto.BORRADOR
    p.ingresos_aprobados_por_id = None
    p.ingresos_aprobados_at = None
    db.commit()
    return {"mensaje": "Presupuesto de ingresos reabierto"}


@router.get("/{presupuesto_id}/ingresos/resumen")
def resumen_ingresos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lineas = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto_id
    ).all()

    por_compania: dict = {}
    por_ramo: dict = {}
    por_tipo_negocio: dict = {'cartera': 0.0, 'nueva_produccion': 0.0, 'sin_clasificar': 0.0}
    total_anual = 0.0
    mensual = [0.0] * 12

    for l in lineas:
        t = float(l.total_anual or 0)
        total_anual += t
        por_compania[l.compania] = por_compania.get(l.compania, 0.0) + t
        por_ramo[l.ramo] = por_ramo.get(l.ramo, 0.0) + t
        tn = l.tipo_negocio or 'sin_clasificar'
        por_tipo_negocio[tn] = por_tipo_negocio.get(tn, 0.0) + t
        for i, imp in enumerate(l.importes_mensuales or []):
            mensual[i] += imp

    return {
        "total_anual": round(total_anual, 2),
        "mensual": [round(v, 2) for v in mensual],
        "por_compania": {k: round(v, 2) for k, v in sorted(por_compania.items(), key=lambda x: -x[1])},
        "por_ramo": {k: round(v, 2) for k, v in sorted(por_ramo.items(), key=lambda x: -x[1])},
        "por_tipo_negocio": {k: round(v, 2) for k, v in por_tipo_negocio.items()},
    }


class AplicarCoeficienteRequest(BaseModel):
    coeficiente_prudencia: float
    compania: Optional[str] = None
    ramo: Optional[str] = None
    actualizar_mercado: bool = False
    tasa_caida_cartera: Optional[float] = None
    tasa_caida_nueva_produccion: Optional[float] = None


@router.post("/{presupuesto_id}/ingresos/aplicar-coeficiente")
def aplicar_coeficiente(
    presupuesto_id: UUID,
    body: AplicarCoeficienteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """RF-ING-17: aplica coeficiente de prudencia en masa a un conjunto de líneas."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)
    actualizadas = aplicar_coeficiente_masivo(
        db, presupuesto_id,
        body.coeficiente_prudencia,
        body.compania,
        body.ramo,
        body.actualizar_mercado,
        body.tasa_caida_cartera,
        body.tasa_caida_nueva_produccion,
    )
    return {"mensaje": f"{actualizadas} líneas actualizadas", "lineas": actualizadas}


@router.get("/{presupuesto_id}/ingresos/mercado-referencia")
def mercado_referencia(
    presupuesto_id: UUID,
    _: User = Depends(get_current_user),
):
    """RF-ING-16: devuelve las tasas de referencia ICEA utilizadas para el mercado."""
    return MERCADO_REFERENCIA_ICEA


@router.get("/{presupuesto_id}/ingresos/metodologia")
def metodologia_presupuesto(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Devuelve el resumen de premisas y metodología del presupuesto activo."""
    p = _get_presupuesto(db, presupuesto_id)
    lineas = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto_id
    ).all()
    meta = calcular_metodologia(lineas)
    meta["ejercicio"] = p.ejercicio
    meta["ejercicio_base"] = p.ejercicio_base
    meta["estado"] = p.estado.value
    meta["total_lineas"] = len(lineas)
    return meta


@router.get("/{presupuesto_id}/ingresos/diagnostico")
def diagnostico_ingresos(
    presupuesto_id: UUID,
    compania: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Diagnóstico detallado de los parámetros de cada línea de ingresos, filtrando por compañía."""
    q = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto_id,
    )
    if compania:
        q = q.filter(PresupuestoIngreso.compania.ilike(f'%{compania}%'))
    lineas = q.order_by(
        PresupuestoIngreso.compania,
        PresupuestoIngreso.ramo,
        PresupuestoIngreso.tipo_negocio,
    ).all()

    resultado = []
    for l in lineas:
        base   = float(l.ingreso_base_anual or 0)
        atip   = float(l.atipicos_excluidos or 0)
        limpia = float(l.ingreso_base_limpio or 0)
        caida  = float(l.tasa_caida or 0)
        superv = round(limpia * (1 - caida / 100), 2)
        crec   = float(l.crecimiento_final or 0)
        total  = float(l.total_anual or 0)
        resultado.append({
            'id':                     str(l.id),
            'compania':               l.compania,
            'ramo':                   l.ramo,
            'auxiliar':               l.auxiliar,
            'tipo_negocio':           l.tipo_negocio,
            'metodo_modelo':          l.metodo_modelo,
            'ingreso_base_anual':     round(base, 2),
            'tiene_atipicos':         bool(l.tiene_atipicos),
            'atipicos_excluidos':     round(atip, 2),
            'ingreso_base_limpio':    round(limpia, 2),
            'tasa_caida_pct':         round(caida, 4),
            'superviviente':          superv,
            'crecimiento_modelo_pct': round(float(l.crecimiento_modelo or 0), 4),
            'crecimiento_mercado_pct':round(float(l.crecimiento_mercado or 0), 4),
            'coeficiente_prudencia':  round(float(l.coeficiente_prudencia or 0), 4),
            'crecimiento_final_pct':  round(crec, 4),
            'total_anual':            round(total, 2),
            'variacion_vs_base_pct':  round((total / base - 1) * 100, 2) if base > 0 else None,
            'bloqueado':              l.bloqueado,
        })

    total_base  = sum(r['ingreso_base_anual'] for r in resultado)
    total_ppto  = sum(r['total_anual'] for r in resultado)
    return {
        'compania_filtro':    compania,
        'n_lineas':           len(resultado),
        'total_base':         round(total_base, 2),
        'total_presupuesto':  round(total_ppto, 2),
        'variacion_total_pct':round((total_ppto / total_base - 1) * 100, 2) if total_base > 0 else None,
        'lineas':             resultado,
    }


@router.get("/{presupuesto_id}/ingresos/{linea_id}/atipicos")
def detalle_atipicos_linea(
    presupuesto_id: UUID,
    linea_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Recalcula y devuelve el detalle de meses atípicos detectados para una línea de ingresos."""
    from sqlalchemy import func as sqlfunc
    from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
    from ..services.presupuesto_ingresos import detectar_atipicos

    linea = _get_linea_ingreso(db, presupuesto_id, linea_id)
    p     = _get_presupuesto(db, presupuesto_id)

    MESES_NOMBRES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                     'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

    rows = (
        db.query(DiarioApunte.mes, sqlfunc.sum(DiarioApunte.haber - DiarioApunte.debe).label('total'))
        .filter(
            DiarioApunte.ejercicio    == p.ejercicio_base,
            DiarioApunte.compania     == linea.compania,
            DiarioApunte.ramo         == linea.ramo,
            DiarioApunte.tipo_cuenta  == TipoCuenta.INGRESO,
            DiarioApunte.estado       == EstadoApunte.CORRECTO,
        )
        .group_by(DiarioApunte.mes)
        .all()
    )

    por_mes = {str(m): 0.0 for m in range(1, 13)}
    sin_mes = 0.0
    for mes, total in rows:
        val = float(total or 0)
        if mes is not None and 1 <= int(mes) <= 12:
            por_mes[str(int(mes))] += val
        else:
            sin_mes += val

    lineal = sin_mes / 12.0
    por_mes_con_reparto = {k: round(v + lineal, 2) for k, v in por_mes.items()}

    resultado = detectar_atipicos(por_mes_con_reparto)

    meses_atipicos = {a['mes'] for a in resultado['atipicos']}
    detalle_meses = [
        {
            'mes':      m,
            'mes_nombre': MESES_NOMBRES[m - 1],
            'importe':  round(por_mes_con_reparto[str(m)], 2),
            'es_atipico': m in meses_atipicos,
            'zscore':   next((a['zscore'] for a in resultado['atipicos'] if a['mes'] == m), None),
        }
        for m in range(1, 13)
    ]

    return {
        'compania':           linea.compania,
        'ramo':               linea.ramo,
        'tipo_negocio':       linea.tipo_negocio,
        'ingreso_base_anual': float(linea.ingreso_base_anual or 0),
        'ingreso_base_limpio':float(linea.ingreso_base_limpio or 0),
        'importe_excluido':   round(resultado['importe_excluible'], 2),
        'meses':              detalle_meses,
        'n_atipicos':         len(resultado['atipicos']),
    }


@router.post("/{presupuesto_id}/ingresos/importar")
async def importar_ingresos(
    presupuesto_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Importa líneas de ingresos desde Excel. Borra las no bloqueadas y carga las del fichero."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)
    contenido = await file.read()
    try:
        resultado = importar_lineas_ingresos_excel(db, p, contenido)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return resultado


# ─────────────────────────────────────────────
# Gastos
# ─────────────────────────────────────────────

@router.post("/{presupuesto_id}/gastos/generar")
def generar_gastos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """RF-GAS-01/04: genera líneas de gastos desde el ejercicio base."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)
    n = generar_lineas_gastos(db, p)
    return {"mensaje": f"{n} líneas de gastos generadas", "lineas": n}


@router.get("/{presupuesto_id}/gastos")
def listar_gastos(
    presupuesto_id: UUID,
    familia: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto_id,
        # Toda cuenta de auxiliares (cualquier variante: "Cesión Auxiliar", "Cesiones a auxiliares"…)
        # se gestiona en PresupuestoCesionAuxiliar; se excluye aquí para evitar duplicidad.
        ~PresupuestoGasto.familia_gasto.ilike('%auxiliar%'),
    )
    if familia:
        q = q.filter(PresupuestoGasto.familia_gasto == familia)
    lineas = q.order_by(PresupuestoGasto.familia_gasto, PresupuestoGasto.numero_cuenta).all()
    return [_serializar_gasto(l) for l in lineas]


@router.patch("/{presupuesto_id}/gastos/{linea_id}/regla")
def actualizar_regla_gasto(
    presupuesto_id: UUID,
    linea_id: UUID,
    datos: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """RF-GAS-05 a RF-GAS-16: cambia la regla de proyección de una línea."""
    linea = _get_linea_gasto(db, presupuesto_id, linea_id)
    if linea.bloqueado:
        raise HTTPException(status_code=400, detail="Línea bloqueada")

    campos = {'tipo_regla', 'porcentaje_variacion', 'mes_inicio_variacion',
              'importe_anual_manual', 'distribucion', 'motivo_exclusion', 'notas'}
    for campo, valor in datos.items():
        if campo in campos:
            setattr(linea, campo, valor)

    recalcular_linea_gasto(db, linea)
    return _serializar_gasto(linea)


@router.patch("/{presupuesto_id}/gastos/{linea_id}/ajuste-manual")
def ajuste_mes_manual(
    presupuesto_id: UUID,
    linea_id: UUID,
    mes: int = Body(...),
    nuevo_importe: float = Body(...),
    mantener_total: bool = Body(False),
    motivo: str = Body(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-GAS-17/19: ajuste manual de un mes con trazabilidad."""
    linea = _get_linea_gasto(db, presupuesto_id, linea_id)
    if linea.bloqueado:
        raise HTTPException(status_code=400, detail="Línea bloqueada")
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mes debe estar entre 1 y 12")

    ajuste_manual_mes(db, linea, mes, nuevo_importe, mantener_total, current_user.username, motivo)
    return _serializar_gasto(linea)


@router.post("/{presupuesto_id}/gastos/nuevo")
def nuevo_gasto(
    presupuesto_id: UUID,
    datos: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """RF-GAS-15: añade un gasto nuevo que no existía en el ejercicio base."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)

    from ..services.presupuesto_gastos import aplicar_regla
    familia = datos.get('familia_gasto') or 'Otros gastos'
    importe = float(datos.get('importe_anual_manual', 0))
    distribucion = DistribucionGasto(datos.get('distribucion', 'lineal'))
    importes = aplicar_regla(
        gasto_base_anual=0,
        estacionalidad=[1/12]*12,
        por_mes={m: 0 for m in range(1, 13)},
        tipo_regla=TipoReglaGasto.NUEVO,
        porcentaje_variacion=None,
        mes_inicio_variacion=None,
        importe_anual_manual=importe,
        distribucion=distribucion,
    )
    linea = PresupuestoGasto(
        presupuesto_id=presupuesto_id,
        familia_gasto=familia,
        descripcion_cuenta=datos.get('descripcion_cuenta'),
        es_gasto_nuevo=True,
        tipo_regla=TipoReglaGasto.NUEVO,
        importe_anual_manual=importe,
        distribucion=distribucion,
        gasto_base_anual=0,
        estacionalidad=[round(1/12, 6)]*12,
        importes_mensuales=importes,
        importes_manuales=[None]*12,
        total_anual=round(sum(importes), 2),
        notas=datos.get('notas'),
    )
    db.add(linea)
    db.commit()
    db.refresh(linea)
    return _serializar_gasto(linea)


@router.post("/{presupuesto_id}/gastos/aprobar")
def aprobar_gastos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """RF-GAS-21: aprueba y bloquea el presupuesto de gastos."""
    p = _get_presupuesto(db, presupuesto_id)

    # RF-GAS-20: validar que no hay gastos sin familia
    sin_familia = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto_id,
        PresupuestoGasto.familia_gasto == None,
    ).count()
    if sin_familia:
        raise HTTPException(status_code=409, detail=f"Hay {sin_familia} líneas de gasto sin familia asignada")

    lineas = db.query(PresupuestoGasto).filter(PresupuestoGasto.presupuesto_id == presupuesto_id).all()
    for l in lineas:
        l.bloqueado = True

    p.estado = EstadoPresupuesto.GASTOS_APROBADOS
    p.gastos_aprobados_por_id = current_user.id
    p.gastos_aprobados_at = datetime.now(timezone.utc)
    db.commit()
    return {"mensaje": "Presupuesto de gastos aprobado y bloqueado"}


@router.post("/{presupuesto_id}/gastos/reabrir")
def reabrir_gastos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Reabre el presupuesto de gastos: desbloquea líneas de gastos y cesiones,
    revierte estado a INGRESOS_APROBADOS."""
    p = _get_presupuesto(db, presupuesto_id)
    estados_validos = (
        EstadoPresupuesto.GASTOS_APROBADOS,
        EstadoPresupuesto.TESORERIA_APROBADA,
        EstadoPresupuesto.CERRADO,
    )
    if p.estado not in estados_validos:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden reabrir gastos cuando están aprobados, la tesorería aprobada o el presupuesto cerrado",
        )

    db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto_id,
    ).update({"bloqueado": False})
    db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto_id,
    ).update({"bloqueado": False})

    # Si estaba cerrado, volver a gastos_aprobados; si no, a ingresos_aprobados
    if p.estado == EstadoPresupuesto.CERRADO:
        p.estado = EstadoPresupuesto.GASTOS_APROBADOS
        p.cerrado_por_id = None
        p.cerrado_at = None
    else:
        p.estado = EstadoPresupuesto.INGRESOS_APROBADOS
        p.gastos_aprobados_por_id = None
        p.gastos_aprobados_at = None
    db.commit()
    return {"mensaje": "Presupuesto de gastos reabierto"}


@router.get("/{presupuesto_id}/gastos/resumen")
def resumen_gastos(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    p = _get_presupuesto(db, presupuesto_id)

    FAMILIA_CESIONES = 'Cesiones a auxiliares'

    def _es_auxiliar(fam: Optional[str]) -> bool:
        return 'auxiliar' in (fam or '').lower()

    todas_lineas = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto_id,
    ).all()
    lineas = [l for l in todas_lineas if l.tipo_regla != TipoReglaGasto.EXCLUIR]

    por_familia_ppto: dict = {}
    por_familia_base: dict = {}
    total_anual = 0.0
    gasto_base_total = 0.0
    mensual = [0.0] * 12

    # Acumular base y presupuesto excluyendo TODA variante de auxiliar (se calcula aparte)
    for l in todas_lineas:
        if _es_auxiliar(l.familia_gasto):
            continue
        base = float(l.gasto_base_anual or 0)
        gasto_base_total += base
        fam = l.familia_gasto or 'Sin familia'
        por_familia_base[fam] = por_familia_base.get(fam, 0.0) + base

    for l in lineas:
        if _es_auxiliar(l.familia_gasto):
            continue
        importes_efectivos = [
            (l.importes_manuales[i] if l.importes_manuales and l.importes_manuales[i] is not None
             else (l.importes_mensuales[i] if l.importes_mensuales and i < len(l.importes_mensuales) else 0))
            for i in range(12)
        ]
        t = sum(importes_efectivos)
        total_anual += t
        fam = l.familia_gasto or 'Sin familia'
        por_familia_ppto[fam] = por_familia_ppto.get(fam, 0.0) + t
        for i, imp in enumerate(importes_efectivos):
            mensual[i] += imp

    # Gasto base 2025 de cesiones = cuentas 623* del ejercicio base
    apuntes_623 = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == p.ejercicio_base,
        DiarioApunte.numero_cuenta.like('623%'),
        DiarioApunte.estado != EstadoApunte.EXCLUIDO,
    ).all()
    base_cesiones = round(sum(float(a.debe - a.haber) for a in apuntes_623), 2)

    # Presupuesto 2026 de cesiones = sum gasto_comision_total de PresupuestoCesionAuxiliar
    cesiones = db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto_id,
    ).all()
    ppto_cesiones = round(sum(float(c.gasto_comision_total or 0) for c in cesiones), 2)
    mensual_cesiones = [0.0] * 12
    for c in cesiones:
        for i, imp in enumerate(c.importes_mensuales or []):
            if i < 12:
                mensual_cesiones[i] += float(imp or 0)

    # Incorporar cesiones a los totales
    gasto_base_total += base_cesiones
    total_anual += ppto_cesiones
    for i in range(12):
        mensual[i] += mensual_cesiones[i]

    por_familia_base[FAMILIA_CESIONES] = base_cesiones
    por_familia_ppto[FAMILIA_CESIONES] = ppto_cesiones

    pct_desviacion = round(
        (total_anual - gasto_base_total) / gasto_base_total * 100, 2
    ) if gasto_base_total else 0.0

    # Construir tabla resumen por familia
    familias_todas = set(list(por_familia_base.keys()) + list(por_familia_ppto.keys()))
    resumen_familia = []
    for fam in sorted(familias_todas):
        base_f = por_familia_base.get(fam, 0.0)
        ppto_f = por_familia_ppto.get(fam, 0.0)
        desv_f = round((ppto_f - base_f) / base_f * 100, 2) if base_f else 0.0
        resumen_familia.append({
            "familia": fam,
            "gasto_base": round(base_f, 2),
            "presupuesto": round(ppto_f, 2),
            "pct_desviacion": desv_f,
        })

    return {
        "total_anual": round(total_anual, 2),
        "gasto_base_total": round(gasto_base_total, 2),
        "pct_desviacion": pct_desviacion,
        "mensual": [round(v, 2) for v in mensual],
        "por_familia": {k: round(v, 2) for k, v in sorted(por_familia_ppto.items(), key=lambda x: -x[1])},
        "resumen_familia": sorted(resumen_familia, key=lambda x: -x["presupuesto"]),
    }


# ─────────────────────────────────────────────
# Cerrar presupuesto + Cuenta de Resultados
# ─────────────────────────────────────────────

@router.post("/{presupuesto_id}/cerrar")
def cerrar_presupuesto(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    """Cierra definitivamente el presupuesto. Solo desde estado gastos_aprobados o tesoreria_aprobada."""
    p = _get_presupuesto(db, presupuesto_id)
    if p.estado == EstadoPresupuesto.CERRADO:
        raise HTTPException(status_code=400, detail="El presupuesto ya está cerrado")
    if p.estado == EstadoPresupuesto.BORRADOR:
        raise HTTPException(status_code=400, detail="No se puede cerrar un presupuesto en borrador")
    p.estado = EstadoPresupuesto.CERRADO
    p.cerrado_por_id = current_user.id
    p.cerrado_at = datetime.now(timezone.utc)
    db.commit()
    return {"mensaje": "Presupuesto cerrado correctamente"}


@router.get("/{presupuesto_id}/cuenta-resultados")
def cuenta_resultados(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Cuenta de Resultados: presupuesto cerrado vs real del ejercicio base."""
    from ..services.cuenta_resultados import calcular_cuenta_resultados
    p = _get_presupuesto(db, presupuesto_id)
    if p.estado != EstadoPresupuesto.CERRADO:
        raise HTTPException(
            status_code=400,
            detail=f"El presupuesto debe estar cerrado (estado actual: {p.estado.value})",
        )
    return calcular_cuenta_resultados(db, p)


# ─────────────────────────────────────────────
# Cesiones de auxiliares
# ─────────────────────────────────────────────

@router.post("/{presupuesto_id}/gastos/cesiones/generar")
def generar_cesiones(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Genera/actualiza cesiones por auxiliar desde el presupuesto de ingresos."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)
    n = generar_cesiones_auxiliar(db, p)
    return {"mensaje": f"{n} auxiliares procesados", "auxiliares": n}


@router.get("/{presupuesto_id}/gastos/cesiones")
def listar_cesiones(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cesiones = db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto_id,
    ).order_by(PresupuestoCesionAuxiliar.auxiliar).all()
    return [_serializar_cesion(c) for c in cesiones]


@router.patch("/{presupuesto_id}/gastos/cesiones/{cesion_id}")
def actualizar_cesion(
    presupuesto_id: UUID,
    cesion_id: UUID,
    datos: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Actualiza tipo, % comisión, % retención y recalcula el gasto."""
    c = db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.id == cesion_id,
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto_id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cesión no encontrada")
    if c.bloqueado:
        raise HTTPException(status_code=400, detail="Cesión bloqueada")

    campos = {'tipo_persona', 'pct_comision', 'pct_retencion', 'notas'}
    for campo, valor in datos.items():
        if campo in campos:
            setattr(c, campo, valor)

    # Override manual: si se envía pct_comision, elimina el override manual
    if 'gasto_comision_manual' in datos:
        val = datos['gasto_comision_manual']
        c.gasto_comision_manual = float(val) if val is not None else None
        if val is not None:
            # El override manual anula el porcentaje como fuente de cálculo
            pass
    elif 'pct_comision' in datos:
        # Cambio de porcentaje → quitar override manual
        c.gasto_comision_manual = None

    # Auto-retención: físico → 15% si no se envió explícitamente
    if 'pct_retencion' not in datos:
        if c.tipo_persona and c.tipo_persona.value == 'fisico':
            c.pct_retencion = 15.0
        elif c.tipo_persona and c.tipo_persona.value == 'juridico':
            c.pct_retencion = 0.0

    recalcular_cesion(db, c)
    return _serializar_cesion(c)


@router.post("/{presupuesto_id}/gastos/cesiones/importar")
async def importar_cesiones(
    presupuesto_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Importa parámetros de cesiones (% comisión, tipo, retención) desde Excel."""
    p = _get_presupuesto(db, presupuesto_id)
    _validar_no_cerrado(p)
    contenido = await file.read()
    try:
        resultado = importar_cesiones_excel(db, p, contenido)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return resultado


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_presupuesto(db: Session, presupuesto_id: UUID) -> Presupuesto:
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return p


def _get_linea_ingreso(db: Session, presupuesto_id: UUID, linea_id: UUID) -> PresupuestoIngreso:
    l = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.id == linea_id,
        PresupuestoIngreso.presupuesto_id == presupuesto_id,
    ).first()
    if not l:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    return l


def _get_linea_gasto(db: Session, presupuesto_id: UUID, linea_id: UUID) -> PresupuestoGasto:
    l = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.id == linea_id,
        PresupuestoGasto.presupuesto_id == presupuesto_id,
    ).first()
    if not l:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    return l


def _validar_no_cerrado(p: Presupuesto):
    if p.estado == EstadoPresupuesto.CERRADO:
        raise HTTPException(status_code=400, detail="El presupuesto está cerrado")


def _serializar_presupuesto(p: Presupuesto) -> dict:
    return {
        "id": str(p.id),
        "ejercicio": p.ejercicio,
        "ejercicio_base": p.ejercicio_base,
        "estado": p.estado.value,
        "ingresos_aprobados_at": p.ingresos_aprobados_at.isoformat() if p.ingresos_aprobados_at else None,
        "gastos_aprobados_at": p.gastos_aprobados_at.isoformat() if p.gastos_aprobados_at else None,
        "cerrado_at": p.cerrado_at.isoformat() if p.cerrado_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serializar_ingreso(l: PresupuestoIngreso) -> dict:
    base_limpio = float(l.ingreso_base_limpio or 0)
    tasa_caida = float(l.tasa_caida or 0)
    return {
        "id": str(l.id),
        "compania": l.compania,
        "ramo": l.ramo,
        "auxiliar": l.auxiliar,
        "tipo_negocio": l.tipo_negocio,
        "ingreso_base_anual": float(l.ingreso_base_anual or 0),
        "tiene_atipicos": l.tiene_atipicos,
        "atipicos_excluidos": float(l.atipicos_excluidos or 0),
        "ingreso_base_limpio": base_limpio,
        "tasa_caida": tasa_caida,
        "base_superviviente": round(base_limpio * (1 - tasa_caida / 100), 2),
        "crecimiento_modelo": float(l.crecimiento_modelo or 0),
        "crecimiento_mercado": float(l.crecimiento_mercado or 0),
        "coeficiente_prudencia": float(l.coeficiente_prudencia or 1),
        "crecimiento_manual": float(l.crecimiento_manual) if l.crecimiento_manual is not None else None,
        "crecimiento_final": float(l.crecimiento_final or 0),
        "importes_mensuales": l.importes_mensuales or [],
        "total_anual": float(l.total_anual or 0),
        "bloqueado": l.bloqueado,
        "notas": l.notas,
        "metodo_modelo": l.metodo_modelo,
    }


def _serializar_gasto(l: PresupuestoGasto) -> dict:
    importes_efectivos = [
        (l.importes_manuales[i] if l.importes_manuales and l.importes_manuales[i] is not None
         else (l.importes_mensuales[i] if l.importes_mensuales and i < len(l.importes_mensuales) else 0))
        for i in range(12)
    ] if l.importes_mensuales else [0.0] * 12
    return {
        "id": str(l.id),
        "numero_cuenta": l.numero_cuenta,
        "descripcion_cuenta": l.descripcion_cuenta,
        "familia_gasto": l.familia_gasto,
        "es_gasto_nuevo": l.es_gasto_nuevo,
        "gasto_base_anual": float(l.gasto_base_anual or 0),
        "tipo_regla": l.tipo_regla.value if l.tipo_regla else None,
        "porcentaje_variacion": float(l.porcentaje_variacion) if l.porcentaje_variacion else None,
        "mes_inicio_variacion": l.mes_inicio_variacion,
        "importe_anual_manual": float(l.importe_anual_manual) if l.importe_anual_manual else None,
        "distribucion": l.distribucion.value if l.distribucion else None,
        "motivo_exclusion": l.motivo_exclusion,
        "importes_mensuales": l.importes_mensuales or [],
        "importes_manuales": l.importes_manuales or [],
        "importes_efectivos": importes_efectivos,
        "total_anual": float(l.total_anual or 0),
        "tiene_ajustes_manuales": bool(l.ajustes_historial),
        "bloqueado": l.bloqueado,
        "notas": l.notas,
    }


def _serializar_cesion(c: PresupuestoCesionAuxiliar) -> dict:
    return {
        "id": str(c.id),
        "auxiliar": c.auxiliar,
        "tipo_persona": c.tipo_persona.value if c.tipo_persona else None,
        "pct_comision": float(c.pct_comision or 0),
        "pct_retencion": float(c.pct_retencion or 0),
        "total_ingreso_base": float(c.total_ingreso_base or 0),
        "gasto_comision_total": float(c.gasto_comision_total or 0),
        "gasto_comision_manual": float(c.gasto_comision_manual) if c.gasto_comision_manual is not None else None,
        "importes_mensuales": c.importes_mensuales or [0.0] * 12,
        "bloqueado": c.bloqueado,
        "notas": c.notas,
    }
