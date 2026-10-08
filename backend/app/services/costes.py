"""
Servicio de clasificación e imputación de costes.
RF-COS-01 a RF-COS-05.
"""
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models.costes import (
    LineaCoste, TipoCoste, TratamientoCoste, DriverReparto,
    EstadoCoste, CLASIFICACION_POR_FAMILIA,
)
from ..models.real import DesvIngreso
from ..models.presupuesto import PresupuestoIngreso


def clasificar_automatico(db: Session, presupuesto_id: str, mes: int, ejercicio: int) -> int:
    """Aplica clasificación automática por familia a líneas pendientes. Devuelve n clasificadas."""
    lineas = db.query(LineaCoste).filter(
        LineaCoste.presupuesto_id == presupuesto_id,
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
    db: Session, presupuesto_id: str, meses: List[int]
) -> Dict[str, Dict[str, float]]:
    """Calcula las bases de reparto para cada driver por compañía/auxiliar/ramo."""
    ing_rows = db.query(DesvIngreso).filter(
        DesvIngreso.presupuesto_id == presupuesto_id,
        DesvIngreso.mes.in_(meses),
    ).all()

    bases: Dict[str, Dict[str, float]] = {
        "comision_contable": {},
        "nueva_produccion": {},
        "numero_polizas": {},
    }

    for r in ing_rows:
        dim = r.compania or "Sin compañía"
        bases["comision_contable"][dim] = bases["comision_contable"].get(dim, 0.0) + float(r.real)
        if r.tipo_negocio == "nueva_produccion":
            bases["nueva_produccion"][dim] = bases["nueva_produccion"].get(dim, 0.0) + float(r.real)

    return bases


def _normalizar(d: Dict[str, float]) -> Dict[str, float]:
    total = sum(d.values())
    if not total:
        return {}
    return {k: round(v / total, 6) for k, v in d.items()}


def imputar_costes(db: Session, presupuesto_id: str, meses: List[int]) -> int:
    """Reparte costes indirectos entre dimensiones según driver. Devuelve n líneas imputadas."""
    lineas = db.query(LineaCoste).filter(
        LineaCoste.presupuesto_id == presupuesto_id,
        LineaCoste.mes.in_(meses),
        LineaCoste.tratamiento == TratamientoCoste.INDIRECTO,
        LineaCoste.estado == EstadoCoste.CLASIFICADO,
    ).all()

    if not lineas:
        return 0

    bases = _calcular_bases_driver(db, presupuesto_id, meses)
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
        LineaCoste.presupuesto_id == presupuesto_id,
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
    db: Session, presupuesto_id: str, meses: List[int]
) -> Dict:
    """Resumen de costes reales vs presupuesto por familia y tratamiento."""
    lineas = db.query(LineaCoste).filter(
        LineaCoste.presupuesto_id == presupuesto_id,
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
    db: Session, presupuesto_id: str, meses: List[int], ing_neto: float
) -> List[Dict]:
    """KPIs de costes: ratio coste/ingreso, % directo vs indirecto, coste por familia."""
    r = resumen_costes(db, presupuesto_id, meses)
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
