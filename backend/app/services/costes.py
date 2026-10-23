"""
Servicio de clasificación e imputación de costes.
RF-COS-01 a RF-COS-05.

Organizado por ejercicio (año natural), no por presupuesto: los costes se
calculan directamente del diario real cargado, para poder analizarlos aunque
no exista ningún presupuesto para ese año todavía. Si existe un Presupuesto
para el mismo ejercicio, se usa automáticamente para rellenar
importe_presupuesto (comparación) y las bases de reparto de comisión; si no
existe, esas partes quedan a 0 y solo se ve el real.
"""
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models.costes import (
    LineaCoste, TipoCoste, TratamientoCoste, DriverReparto,
    EstadoCoste, CLASIFICACION_POR_FAMILIA,
)
from ..models.presupuesto import Presupuesto, PresupuestoGasto
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte


def generar_lineas_coste(db: Session, ejercicio: int, mes: int) -> int:
    """
    Crea/actualiza las líneas de coste de un mes directamente desde el diario
    real cargado (DiarioApunte, cuentas de gasto) -- no depende de ningún
    presupuesto, solo de que haya diario cargado para ese mes/ejercicio.

    Si existe un Presupuesto para este mismo ejercicio, se usa su
    PresupuestoGasto para rellenar importe_presupuesto (solo para poder
    comparar en pantalla); si no existe, importe_presupuesto queda a 0.

    Preserva las líneas que el usuario ya clasificó a mano (clasificacion_automatica
    == False); solo regenera las que siguen en automático, igual que
    presupuesto_gastos.generar_lineas_gastos con sus propias líneas.
    """
    apuntes = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio,
        DiarioApunte.mes == mes,
        DiarioApunte.tipo_cuenta == TipoCuenta.GASTO,
        DiarioApunte.estado == EstadoApunte.CORRECTO,
    ).all()
    if not apuntes:
        raise ValueError(
            f"No hay diario de gastos cargado para el mes {mes} del ejercicio {ejercicio}."
        )

    real_por_cuenta: Dict[str, Dict] = {}
    for ap in apuntes:
        cta = ap.numero_cuenta or 'SIN_CUENTA'
        if cta not in real_por_cuenta:
            real_por_cuenta[cta] = {'familia': ap.familia_gasto or None, 'descripcion': None, 'real': 0.0}
        real_por_cuenta[cta]['real'] += float(ap.debe - ap.haber)
        if not real_por_cuenta[cta]['descripcion'] and ap.descripcion_cuenta:
            real_por_cuenta[cta]['descripcion'] = ap.descripcion_cuenta

    # Presupuesto del mismo ejercicio, si existe -- solo para comparar (opcional)
    presupuesto = db.query(Presupuesto).filter(Presupuesto.ejercicio == ejercicio).first()
    presup_por_cuenta: Dict[str, float] = {}
    if presupuesto:
        for l in db.query(PresupuestoGasto).filter(PresupuestoGasto.presupuesto_id == presupuesto.id).all():
            if not l.numero_cuenta:
                continue
            importes_ef = [
                (l.importes_manuales[i] if l.importes_manuales and l.importes_manuales[i] is not None
                 else (l.importes_mensuales[i] if l.importes_mensuales and i < len(l.importes_mensuales) else 0))
                for i in range(12)
            ]
            presup_por_cuenta[l.numero_cuenta] = importes_ef[mes - 1] if len(importes_ef) >= mes else 0

    db.query(LineaCoste).filter(
        LineaCoste.ejercicio == ejercicio,
        LineaCoste.mes == mes,
        LineaCoste.clasificacion_automatica == True,
    ).delete()
    db.flush()

    ya_manuales = {
        l.numero_cuenta
        for l in db.query(LineaCoste).filter(
            LineaCoste.ejercicio == ejercicio,
            LineaCoste.mes == mes,
        ).all()
    }

    creadas = 0
    for cta, datos in real_por_cuenta.items():
        if cta in ya_manuales:
            continue
        db.add(LineaCoste(
            presupuesto_id=presupuesto.id if presupuesto else None,
            mes=mes,
            ejercicio=ejercicio,
            numero_cuenta=cta,
            descripcion_cuenta=datos['descripcion'],
            familia_gasto=datos['familia'],
            importe_real=round(datos['real'], 2),
            importe_presupuesto=round(presup_por_cuenta.get(cta, 0.0), 2),
            clasificacion_automatica=True,
            estado=EstadoCoste.PENDIENTE,
        ))
        creadas += 1

    db.commit()
    return creadas


def clasificar_automatico(db: Session, ejercicio: int, mes: int) -> int:
    """Aplica clasificación automática por familia a líneas pendientes. Devuelve n clasificadas."""
    lineas = db.query(LineaCoste).filter(
        LineaCoste.ejercicio == ejercicio,
        LineaCoste.mes == mes,
        LineaCoste.estado == EstadoCoste.PENDIENTE,
    ).all()

    clasificadas = 0
    for linea in lineas:
        cfg = CLASIFICACION_POR_FAMILIA.get(linea.familia_gasto)
        if not cfg:
            linea.estado = EstadoCoste.CON_ALERTA
            continue
        if linea.clasificacion_automatica:
            linea.tipo_coste = cfg["tipo"]
            linea.tratamiento = cfg["tratamiento"]
            linea.driver = cfg["driver"]
        if linea.tratamiento == TratamientoCoste.EXCLUIDO:
            linea.estado = EstadoCoste.EXCLUIDO
        else:
            linea.estado = EstadoCoste.CLASIFICADO
        clasificadas += 1

    db.commit()
    return clasificadas


def _calcular_bases_driver(
    db: Session, ejercicio: int, meses: List[int]
) -> Dict[str, Dict[str, float]]:
    """
    Calcula las bases de reparto para cada driver por compañía, directamente
    del diario real de ingresos (mismo cálculo que
    seguimiento_real._calcular_desv_ingresos, sin depender de que exista un
    presupuesto ni de que el mes esté cerrado en Seguimiento Real).
    """
    apuntes = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio,
        DiarioApunte.mes.in_(meses),
        DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
        DiarioApunte.estado == EstadoApunte.CORRECTO,
    ).all()

    bases: Dict[str, Dict[str, float]] = {
        "comision_contable": {},
        "nueva_produccion": {},
    }

    for ap in apuntes:
        dim = ap.compania or "Sin compañía"
        importe = float(ap.haber - ap.debe)
        bases["comision_contable"][dim] = bases["comision_contable"].get(dim, 0.0) + importe
        if ap.tipo_negocio == "nueva_produccion":
            bases["nueva_produccion"][dim] = bases["nueva_produccion"].get(dim, 0.0) + importe

    return bases


def _normalizar(d: Dict[str, float]) -> Dict[str, float]:
    total = sum(d.values())
    if not total:
        return {}
    return {k: round(v / total, 6) for k, v in d.items()}


def imputar_costes(db: Session, ejercicio: int, meses: List[int]) -> int:
    """Reparte costes indirectos entre dimensiones según driver. Devuelve n líneas imputadas."""
    lineas = db.query(LineaCoste).filter(
        LineaCoste.ejercicio == ejercicio,
        LineaCoste.mes.in_(meses),
        LineaCoste.tratamiento == TratamientoCoste.INDIRECTO,
        LineaCoste.estado == EstadoCoste.CLASIFICADO,
    ).all()

    if not lineas:
        return 0

    bases = _calcular_bases_driver(db, ejercicio, meses)
    pct_comision = _normalizar(bases["comision_contable"])
    pct_nueva = _normalizar(bases["nueva_produccion"])

    imputadas = 0
    for linea in lineas:
        importe = float(linea.importe_real)
        if linea.driver == DriverReparto.MANUAL_PORCENTUAL and linea.reparto_manual:
            pcts = linea.reparto_manual
        elif linea.driver == DriverReparto.NUEVA_PRODUCCION:
            pcts = pct_nueva
        else:
            pcts = pct_comision

        linea.imputacion = {dim: round(importe * pct, 2) for dim, pct in pcts.items()}
        linea.estado = EstadoCoste.IMPUTADO
        imputadas += 1

    # Costes directos: se imputan 100% a su propia compañía/familia (sin driver)
    directos = db.query(LineaCoste).filter(
        LineaCoste.ejercicio == ejercicio,
        LineaCoste.mes.in_(meses),
        LineaCoste.tratamiento == TratamientoCoste.DIRECTO,
        LineaCoste.estado == EstadoCoste.CLASIFICADO,
    ).all()
    for linea in directos:
        linea.imputacion = {"directo": float(linea.importe_real)}
        linea.estado = EstadoCoste.IMPUTADO
        imputadas += 1

    db.commit()
    return imputadas


def resumen_costes(
    db: Session, ejercicio: int, meses: List[int]
) -> Dict:
    """Resumen de costes reales vs presupuesto por familia y tratamiento."""
    lineas = db.query(LineaCoste).filter(
        LineaCoste.ejercicio == ejercicio,
        LineaCoste.mes.in_(meses),
    ).all()

    por_familia: Dict[str, Dict] = {}
    totales = {"real": 0.0, "presupuesto": 0.0, "directo": 0.0, "indirecto": 0.0, "excluido": 0.0}

    for linea in lineas:
        fam = linea.familia_gasto or "Sin familia"
        if fam not in por_familia:
            por_familia[fam] = {
                "familia": fam,
                "tipo_coste": linea.tipo_coste.value if linea.tipo_coste else None,
                "tratamiento": linea.tratamiento.value if linea.tratamiento else None,
                "real": 0.0, "presupuesto": 0.0,
            }
        por_familia[fam]["real"] += float(linea.importe_real)
        por_familia[fam]["presupuesto"] += float(linea.importe_presupuesto)
        totales["real"] += float(linea.importe_real)
        totales["presupuesto"] += float(linea.importe_presupuesto)
        if linea.tratamiento == TratamientoCoste.DIRECTO:
            totales["directo"] += float(linea.importe_real)
        elif linea.tratamiento == TratamientoCoste.INDIRECTO:
            totales["indirecto"] += float(linea.importe_real)
        elif linea.tratamiento == TratamientoCoste.EXCLUIDO:
            totales["excluido"] += float(linea.importe_real)

    familias = sorted(por_familia.values(), key=lambda x: -x["real"])
    for f in familias:
        f["desviacion"] = round(f["real"] - f["presupuesto"], 2)
        f["desv_pct"] = round((f["desviacion"] / f["presupuesto"]) * 100, 2) if f["presupuesto"] else 0.0
        f["real"] = round(f["real"], 2)
        f["presupuesto"] = round(f["presupuesto"], 2)

    totales["desviacion"] = round(totales["real"] - totales["presupuesto"], 2)
    return {"familias": familias, "totales": totales}


def kpis_costes(
    db: Session, ejercicio: int, meses: List[int], ing_neto: float
) -> List[Dict]:
    """KPIs de costes: ratio coste/ingreso, % directo vs indirecto, coste por familia."""
    r = resumen_costes(db, ejercicio, meses)
    totales = r["totales"]
    coste_operativo = totales["directo"] + totales["indirecto"]
    ratio = round((coste_operativo / ing_neto) * 100, 2) if ing_neto else 0.0
    pct_directo = round((totales["directo"] / coste_operativo) * 100, 2) if coste_operativo else 0.0
    pct_indirecto = round((totales["indirecto"] / coste_operativo) * 100, 2) if coste_operativo else 0.0

    return [
        {"codigo": "CK-01", "nombre": "Ratio coste operativo / ingreso neto (%)", "valor": ratio},
        {"codigo": "CK-02", "nombre": "Coste directo (€)", "valor": round(totales["directo"], 2)},
        {"codigo": "CK-03", "nombre": "Coste indirecto (€)", "valor": round(totales["indirecto"], 2)},
        {"codigo": "CK-04", "nombre": "Coste excluido (€)", "valor": round(totales["excluido"], 2)},
        {"codigo": "CK-05", "nombre": "% Coste directo sobre operativo", "valor": pct_directo},
        {"codigo": "CK-06", "nombre": "% Coste indirecto sobre operativo", "valor": pct_indirecto},
        *[
            {"codigo": f"CK-F{i+1}", "nombre": f"Coste {f['familia']} (€)", "valor": f["real"]}
            for i, f in enumerate(r["familias"])
        ],
    ]
