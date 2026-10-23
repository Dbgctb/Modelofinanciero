"""
Servicio de cálculo de KPIs. RF-KPI-01 a RF-KPI-04.
Los 15 KPIs definidos en los requerimientos funcionales.
"""
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from ..models.presupuesto import Presupuesto, PresupuestoIngreso, PresupuestoGasto, PresupuestoCesionAuxiliar, TipoReglaGasto
from ..models.real import DesvIngreso, DesvGasto, MesReal, EstadoMesReal
from ..models.kpi import UmbralKPI, ResultadoKPI, SemaforoColor

UMBRALES_DEFAULT = {
    "KPI-01": (95.0, 85.0),    # cumplimiento ingresos %
    "KPI-02": (0.0, -5000.0),  # desviación ingresos €
    "KPI-04": (20.0, 12.0),    # peso nueva producción %
    "KPI-05": (60.0, 40.0),    # peso cartera %
    "KPI-06": (0.0, 30.0),     # ratio cesión % (invertido: menor es mejor)
    "KPI-08": (0.0, 5.0),      # cumplimiento gastos % (invertido)
    "KPI-10": (70.0, 85.0),    # gastos operativos propios / ingresos % (invertido)
    "KPI-11": (0.0, -5000.0),  # EBITDA €
    "KPI-12": (15.0, 5.0),     # margen EBITDA %
}

# Clasificación amort / financiero (igual que cuenta_resultados.py)
_PREFIJOS_AMORT = ('68',)
_PREFIJOS_FIN   = ('66', '76')
_FAMILIA_AMORT  = 'Amortizaciones y ajustes'
_FAMILIA_FIN    = 'Gastos financieros'


def _es_amort(cuenta: str, familia: str) -> bool:
    return any(cuenta.startswith(p) for p in _PREFIJOS_AMORT) or familia == _FAMILIA_AMORT


def _es_fin(cuenta: str, familia: str) -> bool:
    return any(cuenta.startswith(p) for p in _PREFIJOS_FIN) or familia == _FAMILIA_FIN


def _semaforo(codigo: str, valor: float, umbrales: Dict) -> SemaforoColor:
    u = umbrales.get(codigo, (None, None))
    if u[0] is None:
        return SemaforoColor.VERDE
    verde, amarillo = u[0], u[1]
    invertidos = {"KPI-06", "KPI-08", "KPI-10"}
    if codigo in invertidos:
        if valor <= verde:   return SemaforoColor.VERDE
        if valor <= amarillo: return SemaforoColor.AMARILLO
        return SemaforoColor.ROJO
    else:
        if valor >= verde:   return SemaforoColor.VERDE
        if valor >= amarillo: return SemaforoColor.AMARILLO
        return SemaforoColor.ROJO


def _cargar_umbrales(db: Session) -> Dict:
    umbrales = {u.kpi_codigo: (float(u.umbral_verde), float(u.umbral_amarillo))
                for u in db.query(UmbralKPI).all()}
    return {**UMBRALES_DEFAULT, **umbrales}


def _pseudo_desv_from_presupuesto(
    db: Session, presupuesto: Presupuesto, hasta_mes: int
) -> Tuple[List, List]:
    """Construye filas pseudo-DesvIngreso/DesvGasto desde datos de presupuesto."""
    from types import SimpleNamespace
    idx = list(range(0, hasta_mes))  # índices 0-based

    # ── Ingresos ──────────────────────────────────────────────────────────
    lineas_ing = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id
    ).all()
    desv_ing = []
    for li in lineas_ing:
        imp = li.importes_mensuales or []
        total = sum(float(imp[i] or 0) for i in idx if i < len(imp))
        desv_ing.append(SimpleNamespace(
            real=total, presupuesto=total,
            tipo_negocio=li.tipo_negocio,
            auxiliar=li.auxiliar,
            compania=li.compania,
            ramo=li.ramo,
        ))

    # ── Gastos propios (excluye cesiones de auxiliares) ───────────────────
    lineas_gas = db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto.id,
        PresupuestoGasto.tipo_regla != TipoReglaGasto.EXCLUIR,
    ).all()
    desv_gas = []
    for lg in lineas_gas:
        fam = (lg.familia_gasto or '').strip()
        # Excluir cualquier familia de cesión → viene de PresupuestoCesionAuxiliar
        if 'cesion' in fam.lower() or 'cesión' in fam.lower():
            continue
        cuenta = (lg.numero_cuenta or '').strip()
        man = lg.importes_manuales or []
        imp = man if any(v is not None for v in man) else (lg.importes_mensuales or [])
        total = sum(float(imp[i] or 0) for i in idx if i < len(imp))
        desv_gas.append(SimpleNamespace(
            real=total, presupuesto=total,
            familia_gasto=lg.familia_gasto,
            is_amort=_es_amort(cuenta, fam),
            is_fin=_es_fin(cuenta, fam),
        ))

    # ── Cesiones a auxiliares (con auxiliar para KPI-07) ─────────────────
    lineas_ces = db.query(PresupuestoCesionAuxiliar).filter(
        PresupuestoCesionAuxiliar.presupuesto_id == presupuesto.id
    ).all()
    for lc in lineas_ces:
        imp = lc.importes_mensuales or []
        total = sum(float(imp[i] or 0) for i in idx if i < len(imp))
        desv_gas.append(SimpleNamespace(
            real=total, presupuesto=total,
            familia_gasto='Cesiones a auxiliares',
            auxiliar=lc.auxiliar,   # necesario para KPI-07
            is_amort=False, is_fin=False,
        ))

    return desv_ing, desv_gas


def calcular_kpis(db: Session, presupuesto: Presupuesto, hasta_mes: Optional[int] = None) -> List[Dict]:
    """Calcula los 15 KPIs para el presupuesto dado hasta el mes indicado."""
    meses_cerrados = [
        m.mes for m in db.query(MesReal).filter(
            MesReal.presupuesto_id == presupuesto.id,
            MesReal.estado == EstadoMesReal.CERRADO,
        ).all()
    ]
    if hasta_mes:
        meses_cerrados = [m for m in meses_cerrados if m <= hasta_mes]

    umbrales = _cargar_umbrales(db)

    # ── Datos: reales si hay meses cerrados, presupuesto como fallback ────
    if meses_cerrados:
        ultimo_mes = max(meses_cerrados)
        desv_ing = db.query(DesvIngreso).filter(
            DesvIngreso.presupuesto_id == presupuesto.id,
            DesvIngreso.mes.in_(meses_cerrados),
        ).all()
        desv_gas = db.query(DesvGasto).filter(
            DesvGasto.presupuesto_id == presupuesto.id,
            DesvGasto.mes.in_(meses_cerrados),
        ).all()
    else:
        ultimo_mes = hasta_mes or 12
        desv_ing, desv_gas = _pseudo_desv_from_presupuesto(db, presupuesto, ultimo_mes)

    # ── Agregados base ────────────────────────────────────────────────────
    ing_real_total  = sum(float(r.real) for r in desv_ing)
    ing_presup_total = sum(float(r.presupuesto) for r in desv_ing)
    gas_real_total   = sum(float(r.real) for r in desv_gas)
    gas_presup_total = sum(float(r.presupuesto) for r in desv_gas)

    cesiones_real    = sum(float(r.real) for r in desv_gas if r.familia_gasto == 'Cesiones a auxiliares')
    amort_total      = sum(float(r.real) for r in desv_gas if getattr(r, 'is_amort', False))
    fin_total        = sum(float(r.real) for r in desv_gas if getattr(r, 'is_fin', False))

    ing_nueva        = sum(float(r.real) for r in desv_ing if r.tipo_negocio == 'nueva_produccion')
    ing_cartera      = sum(float(r.real) for r in desv_ing if r.tipo_negocio == 'cartera')
    ing_con_auxiliar = sum(float(r.real) for r in desv_ing if r.auxiliar and r.auxiliar != 'Sin auxiliar')

    ing_neto = ing_real_total - cesiones_real

    # Gastos operativos propios: excluye cesiones, amortizaciones y financieros
    # (misma definición que Cuenta de Resultados para EBITDA)
    gas_op_propio = gas_real_total - cesiones_real - amort_total - fin_total

    # EBITDA = Ing_total − Cesiones − Gas_op_propio  (= Ing_neto − Gas_op_propio)
    # Margen = EBITDA / Ing_total  (igual que Cuenta de Resultados)
    ebitda_real   = ing_neto - gas_op_propio
    ebitda_presup = ing_presup_total - gas_presup_total + amort_total + fin_total

    def safe_pct(a, b): return round((a / b) * 100, 2) if b else 0.0

    modo_presupuesto = not meses_cerrados

    if modo_presupuesto:
        kpis_base = [
            ("KPI-01", "Ingresos presupuestados (€)",              round(ing_presup_total, 2)),
            ("KPI-03", "Ingreso neto presupuestado (€)",            round(ing_neto, 2)),
            ("KPI-04", "Peso de nueva producción (%)",              safe_pct(ing_nueva, ing_real_total)),
            ("KPI-05", "Peso de cartera (%)",                       safe_pct(ing_cartera, ing_real_total)),
            ("KPI-06", "Ratio de cesión (%)",                       safe_pct(cesiones_real, ing_con_auxiliar)),
            ("KPI-08", "Gastos operativos propios (€)",             round(gas_op_propio, 2)),
            ("KPI-10", "Gastos op. propios / Ingresos totales (%)", safe_pct(gas_op_propio, ing_real_total)),
            ("KPI-11", "EBITDA presupuestado (€)",                  round(ebitda_real, 2)),
            ("KPI-12", "Margen EBITDA (%)",                         safe_pct(ebitda_real, ing_real_total)),
        ]
        kpis_informativos = {"KPI-01", "KPI-08"}  # montos absolutos → siempre verde
    else:
        kpis_base = [
            ("KPI-01", "Cumplimiento de ingresos (%)",              safe_pct(ing_real_total, ing_presup_total)),
            ("KPI-02", "Desviación de ingresos (€)",                round(ing_real_total - ing_presup_total, 2)),
            ("KPI-03", "Ingreso neto (€)",                          round(ing_neto, 2)),
            ("KPI-04", "Peso de nueva producción (%)",              safe_pct(ing_nueva, ing_real_total)),
            ("KPI-05", "Peso de cartera (%)",                       safe_pct(ing_cartera, ing_real_total)),
            ("KPI-06", "Ratio de cesión (%)",                       safe_pct(cesiones_real, ing_con_auxiliar)),
            ("KPI-08", "Cumplimiento de gastos (%)",                safe_pct(gas_real_total, gas_presup_total)),
            ("KPI-10", "Peso de gastos sobre ingresos netos (%)",   safe_pct(gas_real_total, ing_neto)),
            ("KPI-11", "EBITDA real vs presupuesto (€)",            round(ebitda_real - ebitda_presup, 2)),
            ("KPI-12", "Margen EBITDA (%)",                         safe_pct(ebitda_real, ing_real_total)),
        ]
        kpis_informativos = set()

    resultado_base = []
    for codigo, nombre, valor in kpis_base:
        es_informativo = codigo in kpis_informativos
        sem = SemaforoColor.VERDE if es_informativo else _semaforo(codigo, valor, umbrales)
        resultado_base.append({
            "codigo": codigo, "nombre": nombre, "valor": valor,
            "semaforo": sem.value, "dimension": None, "mes": ultimo_mes,
            # Explícito para que el frontend no tenga que adivinarlo por el texto del
            # nombre: KPI-08 cambia de "% cumplimiento de gastos" (con umbral real) a
            # "Gastos operativos propios (€)" en modo presupuesto (sin datos reales
            # todavía) -- el umbral de KPI-08 está en puntos porcentuales y no tiene
            # sentido aplicado a un importe en euros.
            "informativo": es_informativo,
        })

    # ── KPI-07: Ingreso neto por auxiliar ─────────────────────────────────
    auxiliares = set(r.auxiliar for r in desv_ing if r.auxiliar and r.auxiliar != 'Sin auxiliar')
    kpi07 = []
    for aux in auxiliares:
        ing_aux = sum(float(r.real) for r in desv_ing if r.auxiliar == aux)
        # Cesión específica de este auxiliar (getattr para compatibilidad con DesvGasto real)
        ces_aux = sum(
            float(r.real) for r in desv_gas
            if r.familia_gasto == 'Cesiones a auxiliares'
            and getattr(r, 'auxiliar', None) == aux
        )
        neto = round(ing_aux - ces_aux, 2)
        sem = SemaforoColor.VERDE if neto > 0 else SemaforoColor.ROJO
        kpi07.append({"codigo": "KPI-07", "nombre": "Ingreso neto por auxiliar (€)",
                      "valor": neto, "semaforo": sem.value, "dimension": aux, "mes": ultimo_mes})
    kpi07.sort(key=lambda x: -x['valor'])

    # ── KPI-09: Gastos por familia ─────────────────────────────────────────
    familias: Dict[str, Tuple[float, float]] = {}
    for r in desv_gas:
        fam = r.familia_gasto or 'Sin familia'
        real, presup = familias.get(fam, (0.0, 0.0))
        familias[fam] = (real + float(r.real), presup + float(r.presupuesto))

    kpi09 = []
    if modo_presupuesto:
        # Sin datos reales: mostrar distribución % por familia sobre total gastos
        total_gas_all = sum(v for v, _ in familias.values())
        for fam, (real_v, _) in sorted(familias.items(), key=lambda x: -x[1][0]):
            pct = safe_pct(real_v, total_gas_all)
            kpi09.append({"codigo": "KPI-09", "nombre": "Distribución gastos por familia (%)",
                          "valor": pct, "semaforo": SemaforoColor.VERDE.value,
                          "dimension": fam, "mes": ultimo_mes})
    else:
        # Con datos reales: desviación real vs presupuesto, ordenado por desviación desc
        for fam, (real_v, presup_v) in sorted(familias.items(), key=lambda x: -(x[1][0] - x[1][1])):
            desv = round(real_v - presup_v, 2)
            sem = (SemaforoColor.VERDE if desv <= 0
                   else SemaforoColor.AMARILLO if desv < presup_v * 0.1
                   else SemaforoColor.ROJO)
            kpi09.append({"codigo": "KPI-09", "nombre": "Desviación gastos por familia (€)",
                          "valor": desv, "semaforo": sem.value, "dimension": fam, "mes": ultimo_mes})

    # ── KPI-13: Dependencia por compañía (todas, ordenadas por %) ─────────
    companias: Dict[str, float] = {}
    for r in desv_ing:
        cia = r.compania or 'Sin compañía'
        companias[cia] = companias.get(cia, 0.0) + float(r.real)
    kpi13 = []
    for cia, ing_cia in sorted(companias.items(), key=lambda x: -x[1]):
        pct_dep = safe_pct(ing_cia, ing_real_total)
        sem = (SemaforoColor.VERDE if pct_dep < 40
               else SemaforoColor.AMARILLO if pct_dep < 60
               else SemaforoColor.ROJO)
        kpi13.append({"codigo": "KPI-13", "nombre": "Dependencia de compañía (%)",
                      "valor": pct_dep, "semaforo": sem.value, "dimension": cia, "mes": ultimo_mes})

    # ── KPI-14: Dependencia por auxiliar (todas, ordenadas por %) ─────────
    aux_dict: Dict[str, float] = {}
    for r in desv_ing:
        aux = r.auxiliar or 'Sin auxiliar'
        aux_dict[aux] = aux_dict.get(aux, 0.0) + float(r.real)
    kpi14 = []
    for aux, ing_aux in sorted(aux_dict.items(), key=lambda x: -x[1]):
        pct = safe_pct(ing_aux, ing_real_total)
        sem = (SemaforoColor.VERDE if pct < 30
               else SemaforoColor.AMARILLO if pct < 50
               else SemaforoColor.ROJO)
        kpi14.append({"codigo": "KPI-14", "nombre": "Dependencia de auxiliar (%)",
                      "valor": pct, "semaforo": sem.value, "dimension": aux, "mes": ultimo_mes})

    # ── KPI-15: Mix de ramos (ordenado por % desc) ────────────────────────
    ramos: Dict[str, float] = {}
    for r in desv_ing:
        ramo = r.ramo or 'Sin ramo'
        ramos[ramo] = ramos.get(ramo, 0.0) + float(r.real)
    kpi15 = [
        {"codigo": "KPI-15", "nombre": "Mix de ramos (%)",
         "valor": safe_pct(v, ing_real_total), "semaforo": SemaforoColor.VERDE.value,
         "dimension": k, "mes": ultimo_mes}
        for k, v in sorted(ramos.items(), key=lambda x: -x[1])
    ]

    todos = resultado_base + kpi07 + kpi09 + kpi13 + kpi14 + kpi15

    # Persistir en BD (borrar y reinsertar)
    db.query(ResultadoKPI).filter(ResultadoKPI.presupuesto_id == presupuesto.id).delete()
    for k in todos:
        db.add(ResultadoKPI(
            presupuesto_id=presupuesto.id,
            mes=k["mes"], kpi_codigo=k["codigo"], kpi_nombre=k["nombre"],
            valor=k["valor"], semaforo=SemaforoColor(k["semaforo"]), dimension=k["dimension"],
            informativo=k.get("informativo", False),
        ))
    db.commit()

    return todos


def alertas_gestion(kpis: List[Dict]) -> List[Dict]:
    """RF-KPI-03: genera alertas de gestión desde los KPIs en rojo o amarillo."""
    MENSAJES = {
        "KPI-01": ("Ingresos por debajo del plan", "Los ingresos reales no alcanzan el presupuesto"),
        "KPI-06": ("Ratio de cesión elevado", "Se está cediendo una proporción alta de ingresos a auxiliares"),
        "KPI-08": ("Gastos por encima del presupuesto", "El gasto real supera el presupuestado"),
        "KPI-11": ("EBITDA inferior al objetivo", "El resultado operativo está por debajo del plan"),
        "KPI-12": ("Margen EBITDA bajo", "La rentabilidad operativa es insuficiente"),
        "KPI-13": ("Alta concentración en compañía", "Dependencia elevada de una sola compañía"),
        "KPI-14": ("Alta dependencia de auxiliar", "Riesgo comercial por concentración en un auxiliar"),
        "KPI-04": ("Nueva producción insuficiente", "El peso de nueva producción está por debajo del objetivo"),
    }
    alertas = []
    vistos = set()
    for k in kpis:
        codigo = k["codigo"]
        if k["semaforo"] in ("rojo", "amarillo") and codigo in MENSAJES and codigo not in vistos:
            titulo, desc = MENSAJES[codigo]
            alertas.append({
                "codigo": codigo,
                "nivel": k["semaforo"],
                "titulo": titulo,
                "descripcion": desc,
                "valor": k["valor"],
            })
            vistos.add(codigo)
    return alertas
