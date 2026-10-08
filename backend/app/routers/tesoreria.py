from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

from sqlalchemy import func
from ..core.database import get_db
from ..core.dependencies import get_current_user, require_gestor_or_admin
from ..models.user import User
from ..models.presupuesto import Presupuesto, EstadoPresupuesto, PresupuestoGasto
from ..models.tesoreria import (
    TesoreriaConfig, TesoreriaApunteManual, TesoreriaResultado,
    TesoreriaEmpleado, ReglaCobro, ReglaPago, TipoApunteManual,
)
from ..models.diario import DiarioApunte, EstadoApunte
from ..models.presupuesto import Presupuesto
from ..services.tesoreria import (
    calcular_tesoreria, _KEY_COBROS_GLOBAL, _KEY_PAGOS_DEFAULT, _FAMILIA_CESIONES,
)

router = APIRouter(prefix="/tesoreria", tags=["Tesorería"])


class ConfigInput(BaseModel):
    compania: Optional[str] = None
    regla_cobro: Optional[ReglaCobro] = None
    familia_gasto: Optional[str] = None
    regla_pago: Optional[ReglaPago] = None


class ApunteInput(BaseModel):
    tipo: TipoApunteManual
    concepto: str
    mes: int
    importe_debe: float = 0
    importe_haber: float = 0
    notas: Optional[str] = None


class EmpleadoUpdate(BaseModel):
    pct_ss: Optional[float] = None
    pct_irpf: Optional[float] = None
    es_autonomo: Optional[bool] = None
    salario_bruto_anual: Optional[float] = None
    num_pagas: Optional[int] = None


@router.get("/{presupuesto_id}/config")
def get_config(presupuesto_id: UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    configs = db.query(TesoreriaConfig).filter(TesoreriaConfig.presupuesto_id == presupuesto_id).all()
    return [{"id": str(c.id), "compania": c.compania, "regla_cobro": c.regla_cobro,
             "familia_gasto": c.familia_gasto, "regla_pago": c.regla_pago} for c in configs]


@router.post("/{presupuesto_id}/config")
def upsert_config(
    presupuesto_id: UUID,
    payload: ConfigInput,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """Crea o actualiza la regla de cobro/pago para una compañía o familia."""
    # Buscar existente
    q = db.query(TesoreriaConfig).filter(TesoreriaConfig.presupuesto_id == presupuesto_id)
    if payload.compania:
        cfg = q.filter(TesoreriaConfig.compania == payload.compania).first()
    else:
        cfg = q.filter(TesoreriaConfig.familia_gasto == payload.familia_gasto).first()

    if cfg:
        if payload.regla_cobro: cfg.regla_cobro = payload.regla_cobro
        if payload.regla_pago: cfg.regla_pago = payload.regla_pago
    else:
        cfg = TesoreriaConfig(presupuesto_id=presupuesto_id, **payload.model_dump(exclude_none=True))
        db.add(cfg)
    db.commit()
    return {"mensaje": "Configuración guardada"}


@router.get("/{presupuesto_id}/apuntes")
def listar_apuntes(presupuesto_id: UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    apuntes = db.query(TesoreriaApunteManual).filter(
        TesoreriaApunteManual.presupuesto_id == presupuesto_id
    ).order_by(TesoreriaApunteManual.mes).all()
    return [{"id": str(a.id), "tipo": a.tipo, "concepto": a.concepto, "mes": a.mes,
             "importe_debe": float(a.importe_debe or 0), "importe_haber": float(a.importe_haber or 0),
             "notas": a.notas} for a in apuntes]


@router.post("/{presupuesto_id}/apuntes")
def crear_apunte(
    presupuesto_id: UUID,
    payload: ApunteInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_gestor_or_admin),
):
    if not (1 <= payload.mes <= 12):
        raise HTTPException(400, "Mes debe estar entre 1 y 12")
    ap = TesoreriaApunteManual(
        presupuesto_id=presupuesto_id,
        created_by_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(ap)
    db.commit()
    db.refresh(ap)
    return {"id": str(ap.id), "mensaje": "Apunte añadido"}


@router.delete("/{presupuesto_id}/apuntes/{apunte_id}")
def eliminar_apunte(
    presupuesto_id: UUID,
    apunte_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    ap = db.query(TesoreriaApunteManual).filter(
        TesoreriaApunteManual.id == apunte_id,
        TesoreriaApunteManual.presupuesto_id == presupuesto_id,
    ).first()
    if not ap:
        raise HTTPException(404, "Apunte no encontrado")
    db.delete(ap)
    db.commit()


@router.post("/{presupuesto_id}/calcular")
def calcular(
    presupuesto_id: UUID,
    caja_inicial: float = Body(...),
    caja_minima: Optional[float] = Body(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    """RF-TES-01/13: calcula el flujo de caja presupuestado completo."""
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    _seed_default_configs(db, presupuesto_id)
    resultado = calcular_tesoreria(db, p, caja_inicial, caja_minima)
    return _serializar_resultado(resultado)


def _seed_default_configs(db: Session, presupuesto_id: UUID):
    """Crea configs de timing por defecto si aún no existen."""
    existing_keys = {c.familia_gasto for c in db.query(TesoreriaConfig).filter(
        TesoreriaConfig.presupuesto_id == presupuesto_id).all()}
    defaults = [
        {'familia_gasto': _KEY_COBROS_GLOBAL,  'regla_cobro': ReglaCobro.DIAS_30},
        {'familia_gasto': _KEY_PAGOS_DEFAULT,  'regla_pago':  ReglaPago.MISMO_MES},
        {'familia_gasto': _FAMILIA_CESIONES,   'regla_pago':  ReglaPago.DIAS_30},
    ]
    for d in defaults:
        if d['familia_gasto'] not in existing_keys:
            db.add(TesoreriaConfig(presupuesto_id=presupuesto_id, **d))
    db.commit()


# ── Empleados ─────────────────────────────────────────────────────────────────

@router.get("/{presupuesto_id}/empleados")
def listar_empleados(presupuesto_id: UUID, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    emps = db.query(TesoreriaEmpleado).filter(
        TesoreriaEmpleado.presupuesto_id == presupuesto_id
    ).order_by(TesoreriaEmpleado.nombre).all()
    return [_ser_emp(e) for e in emps]


@router.post("/{presupuesto_id}/empleados/generar")
def generar_empleados(presupuesto_id: UUID, db: Session = Depends(get_db),
                      _: User = Depends(require_gestor_or_admin)):
    """Auto-genera empleados desde cuentas 640* del ejercicio base."""
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    ejercicio_base = p.ejercicio_base or (p.ejercicio - 1)

    # ── Nombres desde contabilidad base (descripcion_cuenta de 640*) ──────────
    nombre_por_cuenta: dict[str, str] = {}
    for a in (
        db.query(DiarioApunte.numero_cuenta, DiarioApunte.descripcion_cuenta)
        .filter(
            DiarioApunte.ejercicio == ejercicio_base,
            DiarioApunte.numero_cuenta.like('640%'),
            DiarioApunte.estado != EstadoApunte.EXCLUIDO,
            DiarioApunte.descripcion_cuenta.isnot(None),
        )
        .distinct()
        .all()
    ):
        if a.numero_cuenta not in nombre_por_cuenta:
            raw = (a.descripcion_cuenta or a.numero_cuenta).strip()
            nombre_por_cuenta[a.numero_cuenta] = raw.replace('Sueldos y Salarios ', '').strip()

    # ── Importes desde PresupuestoGasto 2026 (640*) ───────────────────────────
    data: dict = {}
    for g in (
        db.query(PresupuestoGasto)
        .filter(
            PresupuestoGasto.presupuesto_id == presupuesto_id,
            PresupuestoGasto.numero_cuenta.like('640%'),
        )
        .all()
    ):
        cuenta = g.numero_cuenta
        nombre = nombre_por_cuenta.get(cuenta, cuenta)
        importes = [float(v) for v in (g.importes_mensuales or [0.0] * 12)]
        if len(importes) < 12:
            importes += [0.0] * (12 - len(importes))
        data[cuenta] = {'nombre': nombre, 'importes': importes[:12]}

    # Borrar anteriores y recrear
    db.query(TesoreriaEmpleado).filter(
        TesoreriaEmpleado.presupuesto_id == presupuesto_id
    ).delete()

    AUTONOMAS = ['cristina', 'marta']
    SS_EMPLEADO = 6.47   # contingencias 4,70 + desempleo 1,55 + FP 0,10 + MEI 0,12

    for cuenta, d in data.items():
        nombre_lower = d['nombre'].lower()
        es_autonomo = any(a in nombre_lower for a in AUTONOMAS)
        db.add(TesoreriaEmpleado(
            presupuesto_id=presupuesto_id,
            nombre=d['nombre'],
            numero_cuenta=cuenta,
            es_autonomo=es_autonomo,
            pct_ss=0.0 if es_autonomo else SS_EMPLEADO,
            pct_irpf=0.0,
            num_pagas=14,
            salario_bruto_anual=round(sum(d['importes']), 2),
            importes_brutos_mensuales=[round(v, 2) for v in d['importes']],
        ))

    db.commit()
    return {"mensaje": "Empleados generados", "count": len(data)}


@router.patch("/{presupuesto_id}/empleados/{emp_id}")
def actualizar_empleado(
    presupuesto_id: UUID, emp_id: UUID, payload: EmpleadoUpdate,
    db: Session = Depends(get_db), _: User = Depends(require_gestor_or_admin),
):
    emp = db.query(TesoreriaEmpleado).filter(
        TesoreriaEmpleado.id == emp_id,
        TesoreriaEmpleado.presupuesto_id == presupuesto_id,
    ).first()
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    # Si se marca autónomo, forzar SS a 0
    if payload.es_autonomo is True:
        emp.pct_ss = 0.0
    db.commit()
    db.refresh(emp)
    return _ser_emp(emp)


def _ser_emp(e: TesoreriaEmpleado) -> dict:
    return {
        'id': str(e.id),
        'nombre': e.nombre,
        'numero_cuenta': e.numero_cuenta,
        'es_autonomo': e.es_autonomo,
        'pct_ss': float(e.pct_ss or 0),
        'pct_irpf': float(e.pct_irpf or 0),
        'num_pagas': int(e.num_pagas or 14),
        'salario_bruto_anual': float(e.salario_bruto_anual or 0),
        'importes_brutos_mensuales': e.importes_brutos_mensuales or [],
    }


@router.get("/{presupuesto_id}/resultado")
def get_resultado(presupuesto_id: UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    r = db.query(TesoreriaResultado).filter(TesoreriaResultado.presupuesto_id == presupuesto_id).first()
    if not r:
        raise HTTPException(404, "Aún no se ha calculado la tesorería")
    return _serializar_resultado(r)


@router.post("/{presupuesto_id}/aprobar")
def aprobar_tesoreria(
    presupuesto_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_gestor_or_admin),
):
    r = db.query(TesoreriaResultado).filter(TesoreriaResultado.presupuesto_id == presupuesto_id).first()
    if not r:
        raise HTTPException(400, "Calcula la tesorería antes de aprobarla")
    r.aprobado = True
    p = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
    if p:
        p.estado = EstadoPresupuesto.TESORERIA_APROBADA
    db.commit()
    return {"mensaje": "Tesorería presupuestada aprobada"}


def _serializar_resultado(r: TesoreriaResultado) -> dict:
    MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_data = []
    for i in range(12):
        meses_data.append({
            "mes": i + 1,
            "label": MESES[i],
            "cobros": (r.cobros_mensuales or [0]*12)[i],
            "pagos": (r.pagos_mensuales or [0]*12)[i],
            "entradas_manuales": (r.entradas_manuales or [0]*12)[i],
            "salidas_manuales": (r.salidas_manuales or [0]*12)[i],
            "flujo": (r.flujo_mensual or [0]*12)[i],
            "caja_final": (r.caja_final_mensual or [0]*12)[i],
            "alerta": any(a["mes"] == i + 1 for a in (r.alertas or [])),
        })
    return {
        "presupuesto_id": str(r.presupuesto_id),
        "caja_inicial": float(r.caja_inicial or 0),
        "caja_minima": float(r.caja_minima) if r.caja_minima is not None else None,
        "aprobado": r.aprobado,
        "meses": meses_data,
        "alertas": r.alertas or [],
        "totales": {
            "cobros": round(sum(r.cobros_mensuales or []), 2),
            "pagos": round(sum(r.pagos_mensuales or []), 2),
            "flujo_neto": round(sum(r.flujo_mensual or []), 2),
            "caja_final_diciembre": (r.caja_final_mensual or [0]*12)[11],
        },
        "irpf_trimestral": r.irpf_trimestral or [],
    }
