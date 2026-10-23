"""
Servicio de presupuestación de ingresos.
RF-ING-01 a RF-ING-24 + importación Excel

Lógica de generación (dos líneas por grupo compañía/ramo/auxiliar):

  Línea 1 — Cartera 2026
    Base = Cartera 2025 + Nueva Producción 2025  (todo lo vigente pasa a cartera)
    Aplica: caída (% anulaciones en renovación) + crecimiento (modelo/mercado)

  Línea 2 — Nueva Producción 2026
    Base = Nueva Producción 2025  (referencia de captación del año anterior)
    Sin caída (es negocio nuevo, no sujeto a renovación)
    Aplica: crecimiento de nueva producción (modelo/mercado)

Todo parametrizado en BD (tasas_mercado_ref). CERO hardcoding de tasas.
"""
import logging
import time
import uuid
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, insert as sa_insert, or_

from ..models.presupuesto import Presupuesto, PresupuestoIngreso
from ..models.recibo import Recibo
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..models.carga import CargaContable, TipoCarga, EstadoCarga
from ..models.mercado import TasaMercadoRef, TipoTasaMercado

log = logging.getLogger(__name__)

MESES = list(range(1, 13))

# Solo para documentación/UI
MERCADO_REFERENCIA_ICEA = {"fuente": "ICEA/UNESPA", "anyo": 2024, "no_vida_pct": 7.78}
LAPSE_REFERENCIA = {"fuente": "ICEA + estándares actuariales correduría española", "default_pct": 9.0}


# ─────────────────────────────────────────────────────────────────────────────
# Acceso BD tasas — todo desde tasas_mercado_ref
# ─────────────────────────────────────────────────────────────────────────────

def _anyo_ref_mas_reciente(db: Session, tipo: TipoTasaMercado, ejercicio_base: int) -> Optional[int]:
    return (
        db.query(func.max(TasaMercadoRef.anyo))
        .filter(TasaMercadoRef.tipo == tipo, TasaMercadoRef.anyo <= ejercicio_base)
        .scalar()
    )


def _preload_tasas_db(
    db: Session, tipo: TipoTasaMercado, ejercicio_base: int
) -> Tuple[List, Optional[float]]:
    """Una sola query por tipo. Devuelve (filas_keyword, default_val)."""
    anyo = _anyo_ref_mas_reciente(db, tipo, ejercicio_base)
    if not anyo:
        return [], None
    filas = db.query(TasaMercadoRef).filter(
        TasaMercadoRef.tipo == tipo, TasaMercadoRef.anyo == anyo
    ).all()
    default = next((f for f in filas if f.es_default), None)
    return [f for f in filas if not f.es_default], (float(default.tasa_pct) if default else None)


def _buscar_tasa_cached(filas: List, default_val: Optional[float], ramo: str) -> float:
    """Lookup en lista pre-cargada. Sin hardcoding."""
    ramo_l = (ramo or '').lower()
    for fila in filas:
        if fila.ramo_keyword and fila.ramo_keyword.lower() in ramo_l:
            return float(fila.tasa_pct)
    return default_val if default_val is not None else 0.0


def get_mercado_referencia(ramo: str, db: Optional[Session] = None, ejercicio_base: Optional[int] = None) -> float:
    if db is None or ejercicio_base is None:
        return 0.0
    filas, default_val = _preload_tasas_db(db, TipoTasaMercado.CRECIMIENTO, ejercicio_base)
    return _buscar_tasa_cached(filas, default_val, ramo)


def get_tasa_caida(ramo: str, tipo_negocio: str, db: Optional[Session] = None, ejercicio_base: Optional[int] = None) -> float:
    if db is None or ejercicio_base is None:
        return 0.0
    filas, default_val = _preload_tasas_db(db, TipoTasaMercado.CAIDA_CARTERA, ejercicio_base)
    return _buscar_tasa_cached(filas, default_val, ramo)


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-03
# ─────────────────────────────────────────────────────────────────────────────

def verificar_ejercicio_base_cerrado(db: Session, ejercicio_base: int) -> bool:
    return db.query(CargaContable).filter(
        CargaContable.ejercicio == ejercicio_base,
        CargaContable.tipo_carga == TipoCarga.BASE_PRESUPUESTARIA,
        CargaContable.estado == EstadoCarga.CERRADO,
    ).first() is not None


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-04-13: base de ingresos agrupada por (compañía, ramo, auxiliar)
# Devuelve breakdown total (cartera + NP) y NP solo — para las dos líneas
# ─────────────────────────────────────────────────────────────────────────────

def calcular_base_ingresos(db: Session, ejercicio_base: int) -> List[Dict]:
    rows = (
        db.query(
            DiarioApunte.compania, DiarioApunte.ramo, DiarioApunte.auxiliar,
            DiarioApunte.tipo_negocio, DiarioApunte.mes,
            func.sum(DiarioApunte.haber - DiarioApunte.debe).label('total'),
        )
        .filter(
            DiarioApunte.ejercicio == ejercicio_base,
            DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
            DiarioApunte.estado == EstadoApunte.CORRECTO,
        )
        .group_by(
            DiarioApunte.compania, DiarioApunte.ramo, DiarioApunte.auxiliar,
            DiarioApunte.tipo_negocio, DiarioApunte.mes,
        )
        .all()
    )

    grupos: Dict[tuple, Dict] = {}
    for comp, ramo, aux, tn, mes, total in rows:
        clave = (comp or 'Sin compañía', ramo or 'Sin ramo', aux or 'Sin auxiliar')
        if clave not in grupos:
            grupos[clave] = {
                'compania': clave[0], 'ramo': clave[1], 'auxiliar': clave[2],
                'por_mes_total':      {m: 0.0 for m in MESES},
                'por_mes_nueva_prod': {m: 0.0 for m in MESES},
                'sin_mes_total':      0.0,
                'sin_mes_nueva_prod': 0.0,
                'total_combinado': 0.0,
                'total_nueva_prod': 0.0,
            }
        val = float(total or 0)
        if mes is not None and 1 <= int(mes) <= 12:
            grupos[clave]['por_mes_total'][int(mes)] += val
            if tn == 'nueva_produccion':
                grupos[clave]['por_mes_nueva_prod'][int(mes)] += val
        else:
            # Sin fecha: acumular separado para distribución lineal posterior
            grupos[clave]['sin_mes_total'] += val
            if tn == 'nueva_produccion':
                grupos[clave]['sin_mes_nueva_prod'] += val
        grupos[clave]['total_combinado'] += val
        if tn == 'nueva_produccion':
            grupos[clave]['total_nueva_prod'] += val

    # Distribuir importes sin fecha linealmente entre los 12 meses
    # (mismo criterio que calcular_base_gastos con sin_mes)
    for g in grupos.values():
        lineal = g['sin_mes_total'] / 12.0
        lineal_np = g['sin_mes_nueva_prod'] / 12.0
        for m in MESES:
            g['por_mes_total'][m] += lineal
            g['por_mes_nueva_prod'][m] += lineal_np

    resultado = []
    for g in grupos.values():
        total = g['total_combinado']
        total_np = g['total_nueva_prod']
        if total <= 0:
            continue
        estac_total = [round(g['por_mes_total'][m] / total if total else 0, 6) for m in MESES]
        estac_np = (
            [round(g['por_mes_nueva_prod'][m] / total_np if total_np else 0, 6) for m in MESES]
            if total_np > 0 else []
        )
        resultado.append({
            'compania': g['compania'], 'ramo': g['ramo'], 'auxiliar': g['auxiliar'],
            'total_combinado':    total,
            'total_nueva_prod':   total_np,
            'por_mes_total':      {str(m): g['por_mes_total'][m] for m in MESES},
            'por_mes_nueva_prod': {str(m): g['por_mes_nueva_prod'][m] for m in MESES},
            'estacionalidad_total': estac_total,
            'estacionalidad_np':    estac_np,
        })

    return sorted(resultado, key=lambda x: (-x['total_combinado']))


# ─────────────────────────────────────────────────────────────────────────────
# Pre-carga histórico — UNA query, devuelve dos índices:
#   hist_total: histórico de ingresos totales (para Línea 1 cartera)
#   hist_nueva: histórico de nueva producción (para Línea 2 nueva prod)
# ─────────────────────────────────────────────────────────────────────────────

def _preload_historico(db: Session, ejercicio_base: int) -> Tuple[Dict, Dict]:
    tipos_validos = [TipoCarga.HISTORICO_ESTADISTICO, TipoCarga.BASE_PRESUPUESTARIA]
    rows = (
        db.query(
            DiarioApunte.compania, DiarioApunte.ramo,
            DiarioApunte.tipo_negocio, DiarioApunte.ejercicio,
            func.sum(DiarioApunte.haber - DiarioApunte.debe),
        )
        .join(CargaContable, DiarioApunte.carga_id == CargaContable.id)
        .filter(
            DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
            DiarioApunte.estado == EstadoApunte.CORRECTO,
            CargaContable.tipo_carga.in_(tipos_validos),
            CargaContable.ejercicio <= ejercicio_base,
        )
        .group_by(
            DiarioApunte.compania, DiarioApunte.ramo,
            DiarioApunte.tipo_negocio, DiarioApunte.ejercicio,
        )
        .all()
    )

    # Acumular por (key, ejercicio) separando total vs nueva_prod
    temp: Dict = {}
    for comp, ramo, tn, ej, total in rows:
        key = (comp or 'Sin compañía', ramo or 'Sin ramo')
        k = (key, int(ej))
        if k not in temp:
            temp[k] = {'total': 0.0, 'nueva': 0.0}
        val = float(total or 0)
        temp[k]['total'] += val
        if tn == 'nueva_produccion':
            temp[k]['nueva'] += val

    hist_total: Dict[tuple, List] = {}
    hist_nueva: Dict[tuple, List] = {}
    for (key, ej), vals in temp.items():
        if vals['total'] > 0:
            hist_total.setdefault(key, []).append((ej, vals['total']))
        if vals['nueva'] > 0:
            hist_nueva.setdefault(key, []).append((ej, vals['nueva']))
    for d in (hist_total, hist_nueva):
        for key in d:
            d[key].sort()

    return hist_total, hist_nueva


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-14: detección de atípicos (z-score)
# ─────────────────────────────────────────────────────────────────────────────

def detectar_atipicos(por_mes: Dict[str, float], umbral_zscore: float = 2.0) -> Dict:
    import statistics
    valores = list(por_mes.values())
    if len(valores) < 3 or all(v == 0 for v in valores):
        return {'atipicos': [], 'importe_excluible': 0}
    positivos = [v for v in valores if v > 0]
    if len(positivos) < 3:
        return {'atipicos': [], 'importe_excluible': 0}
    media = statistics.mean(positivos)
    try:
        stdev = statistics.stdev(positivos)
    except Exception:
        return {'atipicos': [], 'importe_excluible': 0}
    if stdev == 0:
        return {'atipicos': [], 'importe_excluible': 0}
    atipicos = []
    for mes_str, val in por_mes.items():
        if val > 0 and abs(val - media) / stdev > umbral_zscore:
            atipicos.append({'mes': int(mes_str), 'importe': val, 'zscore': round(abs(val - media) / stdev, 2)})
    return {'atipicos': atipicos, 'importe_excluible': sum(a['importe'] for a in atipicos)}


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-15: modelos estadísticos
# ─────────────────────────────────────────────────────────────────────────────

# Tope superior del crecimiento interanual. Nueva producción usa uno más bajo:
# muchas líneas NP son pequeñas y muy volátiles, y con +20% un 31% de la base NP
# 2025 quedaba clavada en el tope, proyectando +9,8% de NP con un histórico
# agregado que bajaba (-7,9% en 2024, -4,5% en 2025). Decisión del usuario 2026-10-23.
CAP_CRECIMIENTO_CARTERA = 20.0
CAP_CRECIMIENTO_NP = 10.0


def _calcular_crec_interanual(totales: List[Tuple[int, float]], cap_max: float = CAP_CRECIMIENTO_CARTERA) -> float:
    """Mediana de tasas YoY. Filtra outliers. Cap [-15%, +cap_max]."""
    if len(totales) < 2:
        return 0.0
    tasas = []
    for i in range(1, len(totales)):
        ej_ant, tot_ant = totales[i - 1]
        ej_act, tot_act = totales[i]
        if tot_ant > 0 and tot_act > 0:
            años_diff = ej_act - ej_ant
            if años_diff > 0:
                tasa = ((tot_act / tot_ant) ** (1.0 / años_diff) - 1) * 100
                if -35.0 < tasa < 60.0:
                    tasas.append(tasa)
    if not tasas:
        return 0.0
    tasas.sort()
    n = len(tasas)
    mediana = tasas[n // 2] if n % 2 else (tasas[n // 2 - 1] + tasas[n // 2]) / 2.0
    return round(max(-15.0, min(cap_max, mediana)), 4)


def calcular_crecimiento_estadistico(por_mes: Dict[str, float]) -> float:
    """Fallback OLS intraanual. Cap ±8%."""
    valores = [float(por_mes.get(str(m), 0)) for m in range(1, 13)]
    meses_con_datos = sum(1 for v in valores if v > 0)
    if meses_con_datos < 4:
        return 0.0
    media = sum(valores) / 12
    if media <= 0:
        return 0.0
    x_mean, ss_xx = 6.5, 143.0
    ss_xy = sum((i + 1 - x_mean) * (v - media) for i, v in enumerate(valores))
    return round(max(-8.0, min(8.0, (ss_xy / ss_xx * 11 / media) * 100)), 4)


def calcular_crecimiento_estadistico_interanual(db: Session, compania: str, ramo: str, ejercicio_base: int) -> float:
    """Versión con query propia — usada desde recalcular_linea."""
    tipos_validos = [TipoCarga.HISTORICO_ESTADISTICO, TipoCarga.BASE_PRESUPUESTARIA]
    rows = (
        db.query(DiarioApunte.ejercicio, func.sum(DiarioApunte.haber - DiarioApunte.debe))
        .join(CargaContable, DiarioApunte.carga_id == CargaContable.id)
        .filter(
            DiarioApunte.compania == compania, DiarioApunte.ramo == ramo,
            DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
            DiarioApunte.estado == EstadoApunte.CORRECTO,
            CargaContable.tipo_carga.in_(tipos_validos),
            CargaContable.ejercicio <= ejercicio_base,
        )
        .group_by(DiarioApunte.ejercicio).order_by(DiarioApunte.ejercicio).all()
    )
    totales = [(int(ej), float(t or 0)) for ej, t in rows if (t or 0) > 0]
    return _calcular_crec_interanual(totales)


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-18: crecimiento final
# ─────────────────────────────────────────────────────────────────────────────

def calcular_crecimiento_final(
    crecimiento_modelo: float, crecimiento_mercado: float,
    coeficiente_prudencia: float, crecimiento_manual: Optional[float],
) -> float:
    if crecimiento_manual is not None:
        return round(float(crecimiento_manual), 4)
    mercado = float(crecimiento_mercado or 0)
    modelo = float(crecimiento_modelo or 0)
    coef = float(coeficiente_prudencia or 1)
    if mercado <= modelo:
        return round(modelo, 4)
    return round(modelo + (mercado - modelo) * coef, 4)


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-22: proyección mensual
# ─────────────────────────────────────────────────────────────────────────────

def proyectar_importes(base_limpia: float, tasa_caida: float, crecimiento_final: float, estacionalidad: List[float]) -> List[float]:
    superviviente = base_limpia * (1 - tasa_caida / 100)
    total = superviviente * (1 + crecimiento_final / 100)
    return [round(total * peso, 2) for peso in estacionalidad]


# ─────────────────────────────────────────────────────────────────────────────
# RF-ING-01
# ─────────────────────────────────────────────────────────────────────────────

def crear_presupuesto(db: Session, ejercicio: int, usuario_id: str) -> Presupuesto:
    existente = db.query(Presupuesto).filter(Presupuesto.ejercicio == ejercicio).first()
    if existente:
        return existente
    presupuesto = Presupuesto(ejercicio=ejercicio, ejercicio_base=ejercicio - 1, creado_por_id=usuario_id)
    db.add(presupuesto)
    db.commit()
    db.refresh(presupuesto)
    return presupuesto


# ─────────────────────────────────────────────────────────────────────────────
# Generación principal — DOS líneas por grupo (compañía/ramo/auxiliar)
# ─────────────────────────────────────────────────────────────────────────────

def _metodo_y_crec(
    totales_hist: List, por_mes: Dict, prefijo: str = '', cap_max: float = CAP_CRECIMIENTO_CARTERA,
) -> Tuple[float, str]:
    """Calcula crecimiento modelo y etiqueta del método."""
    n = len(totales_hist)
    if n >= 2:
        crec = _calcular_crec_interanual(totales_hist, cap_max)
        return crec, f"Interanual{' ' + prefijo if prefijo else ''} ({n} ej.)"
    crec = calcular_crecimiento_estadistico(por_mes)
    if crec != 0.0:
        return crec, f"OLS{' ' + prefijo if prefijo else ''} intraanual"
    return 0.0, "Sin datos (0%)"


def generar_lineas_ingresos(db: Session, presupuesto: Presupuesto, coeficiente_prudencia: float) -> int:
    """
    coeficiente_prudencia: fracción (0-1) del exceso de mercado sobre el modelo que se
    incorpora al crecimiento final (ver calcular_crecimiento_final). Lo decide el usuario
    desde la pantalla al generar -- no hay un valor por defecto hardcodeado aquí: antes
    el cálculo usaba un 0.5 fijo en el código mientras la línea guardaba un 0.75/1.0 que
    nunca se usó para calcular nada, así que el "Coef." que se veía en pantalla no era el
    que realmente se había aplicado (bug real reportado en vivo 2026-10-17).
    """
    t0 = time.monotonic()

    db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id,
        PresupuestoIngreso.bloqueado == False,
    ).delete()
    db.flush()

    base = calcular_base_ingresos(db, presupuesto.ejercicio_base)
    if not base:
        db.commit()
        return 0

    # ── Estacionalidad global: recibos.desde + relleno de meses sin datos ───
    # El 2025 se cargó como una única carga anual, por lo que `mes` y `fecha`
    # en diario_apuntes no reflejan la distribución mensual real del negocio.
    # La mejor aproximación es usar el mes de inicio de cobertura del recibo
    # (recibos.desde), que refleja cuándo se devengó la comisión.
    # Los meses sin recibos emparejados reciben el importe restante a partes iguales.
    rows_rec = (
        db.query(
            func.extract('month', Recibo.desde).label('m'),
            func.sum(DiarioApunte.haber - DiarioApunte.debe),
        )
        .join(Recibo, DiarioApunte.recibo_id == Recibo.id)
        .filter(
            DiarioApunte.ejercicio == presupuesto.ejercicio_base,
            DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
            DiarioApunte.estado != EstadoApunte.EXCLUIDO,
            Recibo.desde.isnot(None),
        )
        .group_by(func.extract('month', Recibo.desde))
        .all()
    )
    sin_desde_glob = float(
        db.query(func.sum(DiarioApunte.haber - DiarioApunte.debe))
        .outerjoin(Recibo, DiarioApunte.recibo_id == Recibo.id)
        .filter(
            DiarioApunte.ejercicio == presupuesto.ejercicio_base,
            DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
            DiarioApunte.estado != EstadoApunte.EXCLUIDO,
            or_(DiarioApunte.recibo_id.is_(None), Recibo.desde.is_(None)),
        )
        .scalar() or 0.0
    )
    por_mes_glob: Dict[int, float] = {
        int(m): float(t or 0) for m, t in rows_rec if m and 1 <= int(m) <= 12
    }
    meses_sin_datos = [m for m in MESES if m not in por_mes_glob]
    if meses_sin_datos:
        per_missing = sin_desde_glob / len(meses_sin_datos)
        for m in meses_sin_datos:
            por_mes_glob[m] = per_missing
    else:
        lineal = sin_desde_glob / 12.0
        for m in MESES:
            por_mes_glob[m] = por_mes_glob.get(m, 0.0) + lineal
    total_glob = sum(por_mes_glob.values())
    estac_global = (
        [round(por_mes_glob.get(m, 0.0) / total_glob, 6) for m in MESES]
        if total_glob > 0
        else [round(1 / 12, 6)] * 12
    )

    # 4 queries para TODAS las líneas
    hist_total, hist_nueva = _preload_historico(db, presupuesto.ejercicio_base)
    caida_filas, caida_default = _preload_tasas_db(db, TipoTasaMercado.CAIDA_CARTERA, presupuesto.ejercicio_base)
    mercado_filas, mercado_default = _preload_tasas_db(db, TipoTasaMercado.CRECIMIENTO, presupuesto.ejercicio_base)

    presupuesto_id = presupuesto.id
    lineas_data: List[dict] = []

    for item in base:
        key = (item['compania'], item['ramo'])
        crec_mercado = _buscar_tasa_cached(mercado_filas, mercado_default, item['ramo'])
        tasa_caida = _buscar_tasa_cached(caida_filas, caida_default, item['ramo'])

        # ── LÍNEA 1: CARTERA 2026 ────────────────────────────────────────────
        # total_combinado ya incluye cartera+NP de 2025 (NP de 2025 pasa a cartera en 2026)
        atip = detectar_atipicos(item['por_mes_total'])
        base_limpia = item['total_combinado'] - atip['importe_excluible']

        crec_modelo, metodo = _metodo_y_crec(hist_total.get(key, []), item['por_mes_total'])
        crec_final = calcular_crecimiento_final(crec_modelo, crec_mercado, coeficiente_prudencia, None)
        if crec_final < 0:
            crec_final = 0.0
            metodo = metodo + ' [suelo 0%]'
        # Los atípicos se excluyen de la base de crecimiento (no hay estadística fiable
        # sobre un importe puntual) pero siguen siendo cartera real: la caída SÍ se les
        # aplica (mismo riesgo de anulación que el resto), el crecimiento NO.
        importes_base = proyectar_importes(base_limpia, tasa_caida, crec_final, estac_global)
        importes_atip = proyectar_importes(atip['importe_excluible'], tasa_caida, 0.0, estac_global)
        importes = [round(a + b, 2) for a, b in zip(importes_base, importes_atip)]

        lineas_data.append({
            'id': uuid.uuid4(),
            'presupuesto_id': presupuesto_id,
            'compania': item['compania'],
            'ramo': item['ramo'],
            'auxiliar': item['auxiliar'],
            'tipo_negocio': 'cartera',
            'ingreso_base_anual': item['total_combinado'],
            'tiene_atipicos': bool(atip['atipicos']),
            'atipicos_excluidos': atip['importe_excluible'],
            'ingreso_base_limpio': base_limpia,
            'estacionalidad': estac_global,
            'tasa_caida': tasa_caida,
            'crecimiento_modelo': crec_modelo,
            'crecimiento_mercado': crec_mercado,
            'coeficiente_prudencia': coeficiente_prudencia,
            'crecimiento_final': crec_final,
            'importes_mensuales': importes,
            'total_anual': round(sum(importes), 2),
            'metodo_modelo': metodo,
            'bloqueado': False,
        })

        # ── LÍNEA 2: NUEVA PRODUCCIÓN 2026 ───────────────────────────────────
        if item['total_nueva_prod'] > 0:
            base_limpia_np = item['total_nueva_prod']
            crec_modelo_np, metodo_np = _metodo_y_crec(
                hist_nueva.get(key, []), item['por_mes_nueva_prod'], 'NP', CAP_CRECIMIENTO_NP,
            )
            crec_final_np = calcular_crecimiento_final(crec_modelo_np, crec_mercado, coeficiente_prudencia, None)
            if crec_modelo_np < 0 and crec_final_np < 0:
                crec_final_np = 0.0
                metodo_np = metodo_np + ' [suelo 0%]'
            importes_np = proyectar_importes(base_limpia_np, 0.0, crec_final_np, estac_global)

            lineas_data.append({
                'id': uuid.uuid4(),
                'presupuesto_id': presupuesto_id,
                'compania': item['compania'],
                'ramo': item['ramo'],
                'auxiliar': item['auxiliar'],
                'tipo_negocio': 'nueva_produccion',
                'ingreso_base_anual': item['total_nueva_prod'],
                'tiene_atipicos': False,
                'atipicos_excluidos': 0.0,
                'ingreso_base_limpio': base_limpia_np,
                'estacionalidad': estac_global,
                'tasa_caida': 0.0,
                'crecimiento_modelo': crec_modelo_np,
                'crecimiento_mercado': crec_mercado,
                'coeficiente_prudencia': coeficiente_prudencia,
                'crecimiento_final': crec_final_np,
                'importes_mensuales': importes_np,
                'total_anual': round(sum(importes_np), 2),
                'metodo_modelo': metodo_np,
                'bloqueado': False,
            })

    if lineas_data:
        db.execute(sa_insert(PresupuestoIngreso), lineas_data)

    db.commit()
    log.info("generar_lineas_ingresos: %d líneas en %.1fs", len(lineas_data), time.monotonic() - t0)
    return len(lineas_data)


# ─────────────────────────────────────────────────────────────────────────────
# Recalcular línea individual
# ─────────────────────────────────────────────────────────────────────────────

def recalcular_linea(db: Session, linea: PresupuestoIngreso) -> PresupuestoIngreso:
    crec_final = calcular_crecimiento_final(
        float(linea.crecimiento_modelo or 0), float(linea.crecimiento_mercado or 0),
        float(linea.coeficiente_prudencia or 1),
        float(linea.crecimiento_manual) if linea.crecimiento_manual is not None else None,
    )
    es_cartera = (linea.tipo_negocio or '') == 'cartera'
    if es_cartera and linea.crecimiento_manual is None and crec_final < 0:
        crec_final = 0.0
    linea.crecimiento_final = crec_final

    # Estacionalidad por recibos.desde (ver generar_lineas_ingresos)
    estac = [round(1 / 12, 6)] * 12
    if presupuesto := db.query(Presupuesto).filter(Presupuesto.id == linea.presupuesto_id).first():
        rows_r = (
            db.query(
                func.extract('month', Recibo.desde).label('m'),
                func.sum(DiarioApunte.haber - DiarioApunte.debe),
            )
            .join(Recibo, DiarioApunte.recibo_id == Recibo.id)
            .filter(
                DiarioApunte.ejercicio == presupuesto.ejercicio_base,
                DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
                DiarioApunte.estado != EstadoApunte.EXCLUIDO,
                Recibo.desde.isnot(None),
            )
            .group_by(func.extract('month', Recibo.desde))
            .all()
        )
        sin_d = float(
            db.query(func.sum(DiarioApunte.haber - DiarioApunte.debe))
            .outerjoin(Recibo, DiarioApunte.recibo_id == Recibo.id)
            .filter(
                DiarioApunte.ejercicio == presupuesto.ejercicio_base,
                DiarioApunte.tipo_cuenta == TipoCuenta.INGRESO,
                DiarioApunte.estado != EstadoApunte.EXCLUIDO,
                or_(DiarioApunte.recibo_id.is_(None), Recibo.desde.is_(None)),
            )
            .scalar() or 0.0
        )
        pm: Dict[int, float] = {int(m): float(t or 0) for m, t in rows_r if m and 1 <= int(m) <= 12}
        sin_mes = [m for m in MESES if m not in pm]
        if sin_mes:
            pp = sin_d / len(sin_mes)
            for m in sin_mes:
                pm[m] = pp
        else:
            for m in MESES:
                pm[m] = pm.get(m, 0.0) + sin_d / 12.0
        tot = sum(pm.values())
        if tot > 0:
            estac = [round(pm.get(m, 0.0) / tot, 6) for m in MESES]
    linea.estacionalidad = estac

    # Misma regla que generar_lineas_ingresos: la caída aplica a toda la base
    # (limpia + atípicos), el crecimiento solo a la parte limpia.
    importes_base = proyectar_importes(
        float(linea.ingreso_base_limpio or 0), float(linea.tasa_caida or 0),
        crec_final, estac,
    )
    importes_atip = proyectar_importes(
        float(linea.atipicos_excluidos or 0), float(linea.tasa_caida or 0), 0.0, estac,
    )
    importes = [round(a + b, 2) for a, b in zip(importes_base, importes_atip)]
    linea.importes_mensuales = importes
    linea.total_anual = round(sum(importes), 2)
    db.commit()
    db.refresh(linea)
    return linea


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros masivos
# ─────────────────────────────────────────────────────────────────────────────

def aplicar_coeficiente_masivo(
    db: Session, presupuesto_id,
    coeficiente_prudencia: float, compania: Optional[str], ramo: Optional[str],
    actualizar_mercado: bool,
    tasa_caida_cartera: Optional[float] = None,
    tasa_caida_nueva_produccion: Optional[float] = None,
) -> int:
    q = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto_id,
        PresupuestoIngreso.bloqueado == False,
    )
    if compania:
        q = q.filter(PresupuestoIngreso.compania == compania)
    if ramo:
        q = q.filter(PresupuestoIngreso.ramo == ramo)

    mercado_filas, mercado_default = [], None
    if actualizar_mercado:
        presupuesto = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
        if presupuesto:
            mercado_filas, mercado_default = _preload_tasas_db(db, TipoTasaMercado.CRECIMIENTO, presupuesto.ejercicio_base)

    lineas = q.all()
    for linea in lineas:
        linea.coeficiente_prudencia = coeficiente_prudencia
        if actualizar_mercado:
            linea.crecimiento_mercado = _buscar_tasa_cached(mercado_filas, mercado_default, linea.ramo or '')
        # Caída: solo aplica a cartera; nueva producción siempre 0
        if linea.tipo_negocio == 'nueva_produccion':
            linea.tasa_caida = 0.0
        elif tasa_caida_cartera is not None:
            linea.tasa_caida = tasa_caida_cartera

        linea.crecimiento_final = calcular_crecimiento_final(
            float(linea.crecimiento_modelo or 0), float(linea.crecimiento_mercado or 0),
            coeficiente_prudencia,
            float(linea.crecimiento_manual) if linea.crecimiento_manual is not None else None,
        )
        importes_base = proyectar_importes(
            float(linea.ingreso_base_limpio or 0), float(linea.tasa_caida or 0),
            float(linea.crecimiento_final), linea.estacionalidad or [],
        )
        importes_atip = proyectar_importes(
            float(linea.atipicos_excluidos or 0), float(linea.tasa_caida or 0), 0.0, linea.estacionalidad or [],
        )
        importes = [round(a + b, 2) for a, b in zip(importes_base, importes_atip)]
        linea.importes_mensuales = importes
        linea.total_anual = round(sum(importes), 2)

    db.commit()
    return len(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# Metodología para Dashboard
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Importación Excel
# ─────────────────────────────────────────────────────────────────────────────

def importar_lineas_ingresos_excel(db: Session, presupuesto: Presupuesto, contenido: bytes) -> dict:
    """Importa líneas desde un Excel con el mismo formato que el export."""
    import io as _io
    import unicodedata
    import pandas as pd

    df = pd.read_excel(_io.BytesIO(contenido), dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]

    _MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

    # Búsqueda tolerante a acentos y mayúsculas
    def _norm(s: str) -> str:
        return ''.join(
            c for c in unicodedata.normalize('NFD', s.lower())
            if unicodedata.category(c) != 'Mn'
        )

    col_norm = {_norm(c): c for c in df.columns}

    def _find(*keywords) -> Optional[str]:
        for nk, real in col_norm.items():
            if all(k in nk for k in keywords):
                return real
        return None

    compania_col  = _find('compa')
    ramo_col      = _find('ramo')
    auxiliar_col  = _find('auxil')
    linea_col     = _find('linea')
    atip_col      = _find('atip')
    limpia_col    = _find('limpi')
    caida_col     = _find('caida')
    crec_mod_col  = _find('crec', 'model')
    crec_ref_col  = _find('ref', 'mercad')
    crec_fin_col  = _find('crec', 'final')

    # Detectar columna Base dinámica (ej. 'Base 2025 (€)')
    base_col = next(
        (c for c in df.columns
         if c.lower().startswith('base') and '€' in c
         and 'limpia' not in c.lower() and 'superv' not in c.lower()),
        None,
    )

    if not compania_col or not ramo_col or not linea_col:
        missing = []
        if not compania_col: missing.append('Compañía')
        if not ramo_col:     missing.append('Ramo')
        if not linea_col:    missing.append('Línea')
        raise ValueError(f"Columnas requeridas no encontradas: {', '.join(missing)}")

    def _f(val) -> float:
        try:
            s = str(val or '').strip().replace(',', '.')
            return float(s) if s and s.lower() != 'nan' else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _r(row, col: Optional[str], default=0):
        if col is None:
            return default
        return row.get(col, default)

    # Borrar líneas no bloqueadas
    db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id,
        PresupuestoIngreso.bloqueado == False,
    ).delete()
    db.flush()

    lineas_data: List[dict] = []
    errores: List[str] = []
    presupuesto_id = presupuesto.id

    for idx, row in df.iterrows():
        try:
            compania  = str(_r(row, compania_col, '') or '').strip() or 'Sin compañía'
            ramo      = str(_r(row, ramo_col, '')     or '').strip() or 'Sin ramo'
            auxiliar  = str(_r(row, auxiliar_col, '') or '').strip() or 'Sin auxiliar'
            linea_raw = str(_r(row, linea_col, '')    or '').strip().lower()

            if 'cart' in linea_raw:
                tipo_negocio = 'cartera'
            elif any(k in linea_raw for k in ('prod', 'n.prod', 'np', 'nva')):
                tipo_negocio = 'nueva_produccion'
            else:
                errores.append(f"Fila {idx + 2}: valor de 'Línea' no reconocido: '{_r(row, linea_col)}'")
                continue

            base_anual   = _f(_r(row, base_col, 0)) if base_col else 0.0
            atipicos     = _f(_r(row, atip_col, 0))
            base_limpia  = _f(_r(row, limpia_col, 0)) or base_anual
            tasa_caida   = _f(_r(row, caida_col, 0))
            crec_modelo  = _f(_r(row, crec_mod_col, 0))
            crec_mercado = _f(_r(row, crec_ref_col, 0))
            crec_final   = _f(_r(row, crec_fin_col, 0))

            importes = [_f(row.get(m, 0)) for m in _MESES]
            if not any(v != 0 for v in importes):
                superviviente = base_limpia * (1 - tasa_caida / 100)
                total_calc = superviviente * (1 + crec_final / 100)
                importes = [round(total_calc / 12, 2)] * 12

            total_anual = round(sum(importes), 2)
            estacionalidad = (
                [round(v / total_anual, 6) for v in importes] if total_anual > 0
                else [round(1 / 12, 6)] * 12
            )

            lineas_data.append({
                'id':                    uuid.uuid4(),
                'presupuesto_id':        presupuesto_id,
                'compania':              compania,
                'ramo':                  ramo,
                'auxiliar':              auxiliar,
                'tipo_negocio':          tipo_negocio,
                'ingreso_base_anual':    base_anual,
                'tiene_atipicos':        atipicos > 0,
                'atipicos_excluidos':    atipicos,
                'ingreso_base_limpio':   base_limpia,
                'estacionalidad':        estacionalidad,
                'tasa_caida':            tasa_caida,
                'crecimiento_modelo':    crec_modelo,
                'crecimiento_mercado':   crec_mercado,
                'coeficiente_prudencia': 1.0,
                'crecimiento_manual':    None,
                'crecimiento_final':     crec_final,
                'importes_mensuales':    importes,
                'total_anual':           total_anual,
                'metodo_modelo':         'Importado Excel',
                'bloqueado':             False,
            })
        except Exception as exc:
            errores.append(f"Fila {idx + 2}: {exc}")

    if lineas_data:
        db.execute(sa_insert(PresupuestoIngreso), lineas_data)
    db.commit()
    log.info("importar_lineas_ingresos_excel [ppto=%s]: %d importadas, %d errores",
             presupuesto.id, len(lineas_data), len(errores))
    return {'importadas': len(lineas_data), 'errores': errores}


def calcular_metodologia(lineas: list) -> dict:
    if not lineas:
        return {}
    base_bruta = sum(float(l.ingreso_base_anual or 0) for l in lineas)
    base_limpia = sum(float(l.ingreso_base_limpio or 0) for l in lineas)
    # La caída aplica a toda la base (limpia + atípicos), ver generar_lineas_ingresos.
    caida_total = sum(float(l.ingreso_base_anual or 0) * float(l.tasa_caida or 0) / 100 for l in lineas)
    total_anual = sum(float(l.total_anual or 0) for l in lineas)

    def media_pond(campo):
        p = base_limpia or 1
        return sum(float(getattr(l, campo) or 0) * float(l.ingreso_base_limpio or 0) for l in lineas) / p

    por_tipo: dict = {}
    for l in lineas:
        tn = l.tipo_negocio or 'sin_clasificar'
        if tn not in por_tipo:
            por_tipo[tn] = {'base_bruta': 0.0, 'base_limpia': 0.0, 'caida': 0.0, 'proyectado': 0.0, 'n': 0}
        bl = float(l.ingreso_base_limpio or 0)
        por_tipo[tn]['base_bruta'] += float(l.ingreso_base_anual or 0)
        por_tipo[tn]['base_limpia'] += bl
        por_tipo[tn]['caida'] += bl * float(l.tasa_caida or 0) / 100
        por_tipo[tn]['proyectado'] += float(l.total_anual or 0)
        por_tipo[tn]['n'] += 1

    for d in por_tipo.values():
        d['superviviente'] = d['base_limpia'] - d['caida']
        d['tasa_caida_media'] = round(d['caida'] / d['base_limpia'] * 100, 2) if d['base_limpia'] else 0

    manual = sum(1 for l in lineas if l.crecimiento_manual is not None)
    mdo = sum(1 for l in lineas if l.crecimiento_manual is None and float(l.crecimiento_mercado or 0) > float(l.crecimiento_modelo or 0))
    metodos: dict = {}
    for l in lineas:
        m = l.metodo_modelo or 'desconocido'
        metodos[m] = metodos.get(m, 0) + 1

    return {
        "base_bruta_total": round(base_bruta, 2),
        "base_limpia_total": round(base_limpia, 2),
        "atipicos_total": round(base_bruta - base_limpia, 2),
        "caida_total": round(caida_total, 2),
        "base_superviviente_total": round(base_limpia - caida_total, 2),
        "total_anual": round(total_anual, 2),
        "coeficiente_prudencia_medio": round(media_pond('coeficiente_prudencia'), 4),
        "tasa_caida_media": round(media_pond('tasa_caida'), 4),
        "crecimiento_final_medio": round(media_pond('crecimiento_final'), 4),
        "origen_resumen": {"manual": manual, "mercado_activo": mdo, "solo_modelo": len(lineas) - manual - mdo},
        "metodos_estadisticos": metodos,
        "por_tipo_negocio": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in por_tipo.items()},
        "mercado_ref": MERCADO_REFERENCIA_ICEA,
        "lapse_ref": LAPSE_REFERENCIA,
    }
