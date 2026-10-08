"""
Motor de scoring de cross-selling y alertas de fuga.

Arquitectura del score de cross-selling:
  SCORE = peso_afinidad  × afinidad_matriz     (¿tiene sentido el producto para su cartera?)
        + peso_propension × propension_interna  (¿se parece a quien ya lo compró?)
        + peso_valor      × segmento_valor      (¿cuánto vale el cliente?)
        + peso_timing     × timing              (¿es el momento adecuado?)

Todo parametrizable desde CrossSellingParametros en DB.
"""
import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.cliente import (
    Cliente, CrossSellingParametros, CrossSellingOportunidad,
    FugaAlerta, TipoCliente,
)
from ..models.recibo import Recibo
from .rentabilidad_cliente import calcular_rentabilidad_clientes

log = logging.getLogger(__name__)

# Ramos permitidos según tipo de cliente
_RAMOS_FISICO   = {'AUTO', 'HOGAR', 'SALUD', 'VIDA', 'DECESOS', 'ACCIDENTES', 'RC', 'CIBER'}
_RAMOS_JURIDICO = {'AUTO', 'MULTIRRIESGO', 'RC', 'CIBER', 'FLOTILLAS', 'BAJAS', 'ACCIDENTES', 'SALUD', 'VIDA'}

# ── Matriz de afinidad (benchmarks mercado español de seguros) ───────────────────
DEFAULT_MATRIZ = [
    # ── AUTO como base ──────────────────────────────────────────────────────────
    {"ramo_base": "AUTO",         "ramo_objetivo": "HOGAR",        "afinidad": 0.72, "desc": "Auto → Hogar: combinación más frecuente en cartera personal"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.61, "desc": "Auto → Accidentes: cobertura personal para el conductor y su familia"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "SALUD",        "afinidad": 0.48, "desc": "Auto → Salud: cliente activo con interés en cobertura médica privada"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "VIDA",         "afinidad": 0.40, "desc": "Auto → Vida: protección familiar del conductor o empleado de empresa"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "DECESOS",      "afinidad": 0.35, "desc": "Auto → Decesos: cobertura de fallecimiento complementaria"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "RC",           "afinidad": 0.42, "desc": "Auto → RC: RC personal, profesional o de actividad empresarial"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "FLOTILLAS",    "afinidad": 0.60, "desc": "Auto empresa → Flotillas: un vehículo de empresa es el inicio de una flota"},
    {"ramo_base": "AUTO",         "ramo_objetivo": "MULTIRRIESGO", "afinidad": 0.50, "desc": "Auto empresa → Multirriesgo: empresa con vehículo debe asegurar también el local"},
    # ── HOGAR como base ─────────────────────────────────────────────────────────
    {"ramo_base": "HOGAR",        "ramo_objetivo": "AUTO",         "afinidad": 0.68, "desc": "Hogar → Auto: propietario con hogar suele tener o necesitar auto"},
    {"ramo_base": "HOGAR",        "ramo_objetivo": "SALUD",        "afinidad": 0.54, "desc": "Hogar → Salud: propietario interesado en protección sanitaria familiar"},
    {"ramo_base": "HOGAR",        "ramo_objetivo": "VIDA",         "afinidad": 0.52, "desc": "Hogar → Vida: propietario con hipoteca o familia a su cargo"},
    {"ramo_base": "HOGAR",        "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.46, "desc": "Hogar → Accidentes: complemento habitual en cartera familiar"},
    {"ramo_base": "HOGAR",        "ramo_objetivo": "DECESOS",      "afinidad": 0.38, "desc": "Hogar → Decesos: cliente con vivienda propia en segmento maduro"},
    # ── SALUD como base ─────────────────────────────────────────────────────────
    {"ramo_base": "SALUD",        "ramo_objetivo": "VIDA",         "afinidad": 0.50, "desc": "Salud → Vida: cliente con salud privada concienciado con protección integral"},
    {"ramo_base": "SALUD",        "ramo_objetivo": "DECESOS",      "afinidad": 0.42, "desc": "Salud → Decesos: cobertura complementaria de fallecimiento"},
    {"ramo_base": "SALUD",        "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.55, "desc": "Salud → Accidentes: complemento natural a la cobertura sanitaria"},
    {"ramo_base": "SALUD",        "ramo_objetivo": "BAJAS",        "afinidad": 0.60, "desc": "Salud colectiva → Bajas: empresa con salud colectiva debe cubrir también IT"},
    # ── VIDA como base ──────────────────────────────────────────────────────────
    {"ramo_base": "VIDA",         "ramo_objetivo": "SALUD",        "afinidad": 0.50, "desc": "Vida → Salud: cliente con vida interesado en protección médica complementaria"},
    {"ramo_base": "VIDA",         "ramo_objetivo": "DECESOS",      "afinidad": 0.45, "desc": "Vida → Decesos: complemento de vida para cobertura de sepelio"},
    {"ramo_base": "VIDA",         "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.40, "desc": "Vida → Accidentes: ampliación cobertura para invalidez permanente"},
    {"ramo_base": "VIDA",         "ramo_objetivo": "HOGAR",        "afinidad": 0.45, "desc": "Vida → Hogar: cliente asegurado financieramente, propietario potencial"},
    {"ramo_base": "VIDA",         "ramo_objetivo": "BAJAS",        "afinidad": 0.48, "desc": "Vida colectivo → Bajas: plan de beneficios empresarial completo"},
    # ── DECESOS como base ───────────────────────────────────────────────────────
    {"ramo_base": "DECESOS",      "ramo_objetivo": "VIDA",         "afinidad": 0.52, "desc": "Decesos → Vida: cliente sensibilizado con fallecimiento amplía cobertura a vida"},
    {"ramo_base": "DECESOS",      "ramo_objetivo": "SALUD",        "afinidad": 0.44, "desc": "Decesos → Salud: cliente mayor sensibilizado con salud privada"},
    {"ramo_base": "DECESOS",      "ramo_objetivo": "HOGAR",        "afinidad": 0.36, "desc": "Decesos → Hogar: cliente de edad con vivienda propia"},
    # ── ACCIDENTES como base ────────────────────────────────────────────────────
    {"ramo_base": "ACCIDENTES",   "ramo_objetivo": "SALUD",        "afinidad": 0.55, "desc": "Accidentes → Salud: complemento médico al seguro de accidentes"},
    {"ramo_base": "ACCIDENTES",   "ramo_objetivo": "VIDA",         "afinidad": 0.40, "desc": "Accidentes → Vida: protección complementaria de invalidez permanente"},
    {"ramo_base": "ACCIDENTES",   "ramo_objetivo": "DECESOS",      "afinidad": 0.35, "desc": "Accidentes → Decesos: cobertura de fallecimiento por accidente"},
    {"ramo_base": "ACCIDENTES",   "ramo_objetivo": "BAJAS",        "afinidad": 0.55, "desc": "Accidentes colectivo → Bajas: cobertura IT complementaria en jornada laboral"},
    {"ramo_base": "ACCIDENTES",   "ramo_objetivo": "MULTIRRIESGO", "afinidad": 0.40, "desc": "Accidentes empresa → Multirriesgo: empresa con plantilla debe asegurar instalaciones"},
    # ── RC como base ────────────────────────────────────────────────────────────
    {"ramo_base": "RC",           "ramo_objetivo": "CIBER",        "afinidad": 0.58, "desc": "RC → Ciberriesgos: empresa/profesional con RC expuesto a brechas de datos"},
    {"ramo_base": "RC",           "ramo_objetivo": "MULTIRRIESGO", "afinidad": 0.55, "desc": "RC → Multirriesgo: empresa con RC debe asegurar también sus instalaciones"},
    {"ramo_base": "RC",           "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.45, "desc": "RC → Accidentes: profesional con RC activo con necesidad de cobertura personal"},
    {"ramo_base": "RC",           "ramo_objetivo": "FLOTILLAS",    "afinidad": 0.42, "desc": "RC empresa → Flotillas: empresa con RC puede tener vehículos de empresa"},
    # ── MULTIRRIESGO como base ──────────────────────────────────────────────────
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "RC",           "afinidad": 0.62, "desc": "Multirriesgo → RC: empresa con instalaciones siempre necesita RC profesional"},
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "CIBER",        "afinidad": 0.55, "desc": "Multirriesgo → Ciber: empresa con instalaciones debe proteger también sus datos"},
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "SALUD",        "afinidad": 0.52, "desc": "Multirriesgo → Salud colectiva: empresa con empleados, salud como beneficio"},
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.50, "desc": "Multirriesgo → Accidentes colectivo: cobertura de empleados en jornada laboral"},
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "FLOTILLAS",    "afinidad": 0.48, "desc": "Multirriesgo → Flotillas: empresa con local suele tener vehículos de empresa"},
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "BAJAS",        "afinidad": 0.45, "desc": "Multirriesgo → Colectivo bajas: cobertura de IT para plantilla"},
    {"ramo_base": "MULTIRRIESGO", "ramo_objetivo": "VIDA",         "afinidad": 0.42, "desc": "Multirriesgo → Vida colectivo: seguro de vida para empleados clave"},
    # ── CIBER como base ─────────────────────────────────────────────────────────
    {"ramo_base": "CIBER",        "ramo_objetivo": "RC",           "afinidad": 0.52, "desc": "Ciber → RC: empresa/profesional digital con exposición a responsabilidad de datos"},
    {"ramo_base": "CIBER",        "ramo_objetivo": "MULTIRRIESGO", "afinidad": 0.45, "desc": "Ciber → Multirriesgo: empresa digital con oficina o instalaciones físicas"},
    # ── FLOTILLAS como base ─────────────────────────────────────────────────────
    {"ramo_base": "FLOTILLAS",    "ramo_objetivo": "MULTIRRIESGO", "afinidad": 0.58, "desc": "Flotillas → Multirriesgo: empresa con flota debe asegurar también sus instalaciones"},
    {"ramo_base": "FLOTILLAS",    "ramo_objetivo": "RC",           "afinidad": 0.55, "desc": "Flotillas → RC: empresa con vehículos necesita RC profesional complementaria"},
    {"ramo_base": "FLOTILLAS",    "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.48, "desc": "Flotillas → Accidentes colectivo: cobertura de conductores en jornada laboral"},
    {"ramo_base": "FLOTILLAS",    "ramo_objetivo": "CIBER",        "afinidad": 0.40, "desc": "Flotillas → Ciber: empresa de transporte/logística con exposición digital"},
    # ── BAJAS como base ─────────────────────────────────────────────────────────
    {"ramo_base": "BAJAS",        "ramo_objetivo": "SALUD",        "afinidad": 0.65, "desc": "Bajas → Salud colectiva: empresa con seguro de bajas ofrece salud como beneficio"},
    {"ramo_base": "BAJAS",        "ramo_objetivo": "ACCIDENTES",   "afinidad": 0.58, "desc": "Bajas → Accidentes colectivo: complemento natural a la cobertura de bajas"},
    {"ramo_base": "BAJAS",        "ramo_objetivo": "VIDA",         "afinidad": 0.45, "desc": "Bajas → Vida colectivo: plan de beneficios completo para empleados"},
    {"ramo_base": "BAJAS",        "ramo_objetivo": "MULTIRRIESGO", "afinidad": 0.40, "desc": "Bajas → Multirriesgo: empresa con gestión de personal debe asegurar instalaciones"},
]


_ESTADO_ANULADO_PREFIJOS = ('ANULA', 'CANCEL', 'DEVUEL')


def _es_anulado(estado: str | None) -> bool:
    if not estado:
        return False
    e = estado.strip().upper()
    return any(e.startswith(p) or p in e for p in _ESTADO_ANULADO_PREFIJOS)


def _norm_nombre(nombre: str) -> str:
    return re.sub(r'\s+', ' ', str(nombre).strip().upper())


def _limpiar_subramo(ramo: str) -> str:
    """Limpia el sub-ramo sin colapsar categorías: strip + upper + espacios múltiples."""
    if not ramo:
        return "OTROS"
    return re.sub(r'\s+', ' ', ramo.strip().upper())


def _normalizar_ramo(ramo: str) -> str:
    if not ramo:
        return "OTROS"
    r = ramo.strip().upper()
    if any(x in r for x in ['AUTO', 'VEHICULO', 'VEHÍCULO', 'COCHE', 'MOTO']):
        return 'AUTO'
    if any(x in r for x in ['HOGAR', 'COMUNIDAD', 'EDIFICIO', 'CONTE', 'INMUEBLE']):
        return 'HOGAR'
    if any(x in r for x in ['SALUD', 'MÉDICO', 'MEDICO', 'SANITARIO']):
        return 'SALUD'
    if any(x in r for x in ['VIDA', 'FALLECIMIENTO', 'AHORRO', 'PENSIÓN', 'PENSION']):
        return 'VIDA'
    if any(x in r for x in ['DECESOS', 'DECESO', 'SEPELIO']):
        return 'DECESOS'
    if any(x in r for x in ['ACCIDENTE', 'ACCIDENTES']):
        return 'ACCIDENTES'
    if 'RC' in r.split() or 'RESPONSABILIDAD' in r:
        return 'RC'
    if any(x in r for x in ['MULTIRRIESGO', 'COMERCIO', 'PYME']):
        return 'MULTIRRIESGO'
    if any(x in r for x in ['CIBER', 'CYBER']):
        return 'CIBER'
    if any(x in r for x in ['FLOTILLA', 'FLOTAS']):
        return 'FLOTILLAS'
    if any(x in r for x in ['BAJA', 'COLECTIVO']):
        return 'BAJAS'
    return r


def _antiguedad_anos(fecha_alta: Optional[date], min_desde: Optional[date]) -> float:
    hoy = date.today()
    fecha = fecha_alta or min_desde
    if not fecha:
        return 0.0
    return max(0.0, (hoy - fecha).days / 365.25)


def _score_segmento_valor(prima_total: float, p25: float, p50: float, p75: float) -> float:
    if prima_total >= p75:
        return 100.0
    if prima_total >= p50:
        return 75.0
    if prima_total >= p25:
        return 50.0
    return 25.0


def _score_timing(
    dias_vencimiento: Optional[int],
    antiguedad: float,
    tiene_reciente: bool,
    params: CrossSellingParametros,
) -> float:
    scores = []
    if dias_vencimiento is not None:
        if 0 < dias_vencimiento <= params.dias_vencimiento_urgente:
            scores.append(100.0)
        elif 0 < dias_vencimiento <= params.dias_vencimiento_medio:
            scores.append(60.0)
    if tiene_reciente:
        scores.append(80.0)
    if antiguedad > 3:
        scores.append(40.0)
    elif antiguedad > 1:
        scores.append(20.0)
    return max(scores) if scores else 20.0


def _score_propension(
    tipo_cliente: TipoCliente,
    antiguedad: float,
    prima_total: float,
    n_ramos: int,
    compradores: list,
) -> float:
    if not compradores:
        return 50.0

    avg_ant = sum(c['antiguedad'] for c in compradores) / len(compradores)
    avg_prima = sum(c['prima'] for c in compradores) / len(compradores)
    avg_ramos = sum(c['n_ramos'] for c in compradores) / len(compradores)
    tipo_counts: dict = {}
    for c in compradores:
        tipo_counts[c['tipo']] = tipo_counts.get(c['tipo'], 0) + 1
    tipo_pred = max(tipo_counts, key=lambda t: tipo_counts[t])

    dists = []
    # Antigüedad normalizada sobre 10 años
    dists.append(min(1.0, abs(antiguedad - avg_ant) / max(avg_ant, 10)))
    # Prima en escala log
    if avg_prima > 0 and prima_total > 0:
        log_d = abs(math.log(prima_total + 1) - math.log(avg_prima + 1)) / max(math.log(avg_prima + 1), 1)
        dists.append(min(1.0, log_d))
    else:
        dists.append(0.5)
    # N_ramos
    dists.append(min(1.0, abs(n_ramos - avg_ramos) / max(avg_ramos, 3)))
    # Tipo
    tipo_bonus = 0.0 if tipo_cliente.value == tipo_pred else 0.5
    dists.append(tipo_bonus)

    similitud = 1.0 - (sum(dists) / len(dists))
    return max(0.0, min(100.0, similitud * 100))


def _construir_motivo(
    ramos_act: set,
    ramo_obj: str,
    antiguedad: float,
    propension: float,
    mejor_desc: str,
    tipo: TipoCliente,
) -> str:
    partes = []
    if ramos_act:
        partes.append(f"Tiene: {', '.join(sorted(ramos_act))}")
    partes.append(f"Sin {ramo_obj} contratado")
    if antiguedad > 2:
        partes.append(f"Cliente desde hace {antiguedad:.0f} años")
    if propension >= 70:
        partes.append("Perfil muy similar a compradores existentes")
    elif propension >= 50:
        partes.append("Perfil similar a compradores existentes")
    if mejor_desc:
        partes.append(mejor_desc)
    if tipo == TipoCliente.JURIDICO:
        partes.append("Cliente empresarial")
    return " · ".join(partes)


def calcular_ramo_stats(db: Session, ejercicio: int) -> list[dict]:
    """
    Calcula prima media y margen medio por ramo para el ejercicio (solo recibos vigentes)
    y los guarda en RamoStatsEjercicio. Devuelve la lista calculada.
    """
    from ..models.cliente import RamoStatsEjercicio

    hoy = date.today()
    fecha_ref = date(ejercicio, 12, 31) if ejercicio < hoy.year else hoy

    recibos = db.query(Recibo).filter(Recibo.ejercicio == ejercicio).all()

    _prima_cli: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    _liqui_cli: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # {sub-ramo: {categoria_normalizada, {tomador: prima}}}
    _cat_subramo: dict[str, str] = {}  # sub-ramo → categoría normalizada

    for r in recibos:
        if not r.ramo or not r.pr_total or float(r.pr_total) <= 0 or not r.tomador:
            continue
        if _es_anulado(r.estado):
            continue
        if not r.hasta or r.hasta < fecha_ref:
            continue
        sub = _limpiar_subramo(r.subramo) if r.subramo else _limpiar_subramo(r.ramo)
        cat = _normalizar_ramo(r.ramo)           # categoría normalizada para lookup
        _cat_subramo[sub] = cat
        t = _norm_nombre(r.tomador)
        _prima_cli[sub][t] += float(r.pr_total)
        if r.liqui is not None:
            _liqui_cli[sub][t] += float(r.liqui)

    resultado = []
    for sub, clientes in _prima_cli.items():
        cat = _cat_subramo.get(sub, sub)
        primas = list(clientes.values())
        prima_media = sum(primas) / len(primas) if primas else 0.0

        margenes = []
        for t, prima in clientes.items():
            if prima > 0:
                liqui = _liqui_cli[sub].get(t, 0.0)
                m = liqui / prima
                if 0.0 < m < 1.0:
                    margenes.append(m)
        margen_medio = sum(margenes) / len(margenes) if margenes else 0.15

        existing = db.query(RamoStatsEjercicio).filter(
            RamoStatsEjercicio.ejercicio == ejercicio,
            RamoStatsEjercicio.ramo == sub,
        ).first()
        if existing:
            existing.ramo_categoria = cat
            existing.prima_media = round(prima_media, 2)
            existing.margen_medio = round(margen_medio, 4)
            existing.n_clientes = len(clientes)
        else:
            db.add(RamoStatsEjercicio(
                ejercicio=ejercicio,
                ramo=sub,
                ramo_categoria=cat,
                prima_media=round(prima_media, 2),
                margen_medio=round(margen_medio, 4),
                n_clientes=len(clientes),
            ))
        resultado.append({
            "ramo": sub,
            "ramo_categoria": cat,
            "prima_media": round(prima_media, 2),
            "margen_medio": round(margen_medio, 4),
            "n_clientes": len(clientes),
        })

    db.flush()
    return sorted(resultado, key=lambda x: x["prima_media"], reverse=True)


def _get_or_create_parametros(db: Session) -> CrossSellingParametros:
    p = db.query(CrossSellingParametros).first()
    if not p:
        p = CrossSellingParametros(id=1, matriz_afinidad=DEFAULT_MATRIZ)
        db.add(p)
        db.flush()
    elif len(p.matriz_afinidad or []) < len(DEFAULT_MATRIZ):
        # Actualiza si la almacenada tiene menos entradas (p.ej. tras ampliar DEFAULT_MATRIZ)
        # No sobreescribe personalizaciones que hayan superado el tamaño por defecto
        p.matriz_afinidad = DEFAULT_MATRIZ
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(p, 'matriz_afinidad')
    return p


def recalcular_cross_selling(db: Session, ejercicio: int) -> dict:
    """
    Recalcula oportunidades de cross-selling y alertas de fuga para el ejercicio.
    Borra y regenera. Llamar dentro de una transacción ya abierta.
    """
    params = _get_or_create_parametros(db)

    # ── Auxiliares excluidos de oportunidades ─────────────────────────────────────
    from ..models.cliente import AuxiliarParticipacion, RamoStatsEjercicio as _RamoStats
    excluidos_aux: set[str] = {
        a.auxiliar for a in db.query(AuxiliarParticipacion).all() if not a.participa
    }

    # ── Stats de ramo: desde BD si están calculados, si no on-the-fly ────────────
    # Los stats están por sub-ramo; los agregamos a categoría normalizada (media ponderada
    # por n_clientes) para usarlos en el lookup por ramo_recomendado (nivel normalizado).
    _stats_bd = db.query(_RamoStats).filter(_RamoStats.ejercicio == ejercicio).all()
    if _stats_bd:
        _grouped: dict[str, list] = defaultdict(list)
        for s in _stats_bd:
            cat = s.ramo_categoria or _normalizar_ramo(s.ramo)
            n = s.n_clientes or 1
            _grouped[cat].append((s.prima_media, s.margen_medio, n))
        prima_media_ramo: dict[str, float] = {}
        margen_medio_ramo: dict[str, float] = {}
        for cat, entries in _grouped.items():
            total_n = sum(e[2] for e in entries)
            prima_media_ramo[cat] = sum(e[0] * e[2] for e in entries) / total_n
            margen_medio_ramo[cat] = sum(e[1] * e[2] for e in entries) / total_n
    else:
        prima_media_ramo = {}
        margen_medio_ramo = {}

    # ── Recibos actuales y anteriores ────────────────────────────────────────────
    recibos_act = db.query(Recibo).filter(Recibo.ejercicio == ejercicio).all()
    if not recibos_act:
        return {"sin_datos": True, "oportunidades": 0, "alertas": 0}

    recibos_ant = db.query(Recibo).filter(Recibo.ejercicio == ejercicio - 1).all()

    # ── Prima/margen por ramo on-the-fly si no hay stats en BD ───────────────────
    if not _stats_bd:
        _ramo_prima_cli: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        _ramo_liqui_cli: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for r in recibos_act:
            if not r.ramo or not r.pr_total or float(r.pr_total) <= 0 or not r.tomador:
                continue
            rn = _normalizar_ramo(r.ramo)
            t = _norm_nombre(r.tomador)
            _ramo_prima_cli[rn][t] += float(r.pr_total)
            if r.liqui is not None:
                _ramo_liqui_cli[rn][t] += float(r.liqui)
        prima_media_ramo = {
            rn: sum(clientes.values()) / len(clientes)
            for rn, clientes in _ramo_prima_cli.items() if clientes
        }
        for rn, clientes_prima in _ramo_prima_cli.items():
            margenes = []
            for t, prima in clientes_prima.items():
                if prima > 0:
                    liqui = _ramo_liqui_cli[rn].get(t, 0.0)
                    m = liqui / prima
                    if 0.0 < m < 1.0:
                        margenes.append(m)
            if margenes:
                margen_medio_ramo[rn] = sum(margenes) / len(margenes)

    # ── Márgenes reales del módulo de rentabilidad ───────────────────────────────
    # {tomador_norm: margen decimal (ej: 0.18 = 18%)}
    margenes_reales: dict[str, float] = {}
    try:
        rent = calcular_rentabilidad_clientes(db, ejercicio)
        if not rent.get('sin_datos'):
            for c in rent.get('clientes', []):
                t_norm = _norm_nombre(c.get('cliente', ''))
                m = c.get('margen_pct_normalizado')
                if m is not None:
                    margenes_reales[t_norm] = float(m) / 100
    except Exception:
        pass  # si el módulo falla, usamos proxy 15%

    # ── Construir portfolios actuales ─────────────────────────────────────────────
    # ramos / prima_total  → todos los recibos del ejercicio (para comparación fuga)
    # ramos_vigentes / prima_vigente → solo recibos con hasta >= hoy (cartera en vigor)
    portfolios: dict[str, dict] = defaultdict(lambda: {
        'ramos': set(), 'prima_total': 0.0,
        'ramos_vigentes': set(), 'prima_vigente': 0.0, 'liqui_vigente': 0.0,
        'subramos_vigentes': defaultdict(set),  # {categoria: set de subramos}
        'polizas_prima': {},  # {poliza: prima} — del ejercicio completo
        'auxiliares': {},     # {ente: prima_acumulada} — para identificar auxiliar principal
        'min_desde': None, 'max_desde': None, 'max_hasta': None,
        'recibos': [],
    })

    hoy = date.today()
    # Para ejercicios pasados, consideramos vigentes los recibos activos a fin de año
    fecha_ref = date(ejercicio, 12, 31) if ejercicio < hoy.year else hoy

    for r in recibos_act:
        if not r.tomador or _es_anulado(r.estado):
            continue
        t = _norm_nombre(r.tomador)
        ramo_n = _normalizar_ramo(r.ramo or '')
        p = portfolios[t]
        p['ramos'].add(ramo_n)
        p['prima_total'] += float(r.pr_total or 0)
        # Solo recibos vigentes en la fecha de referencia del ejercicio
        if r.hasta and r.hasta >= fecha_ref:
            p['ramos_vigentes'].add(ramo_n)
            p['prima_vigente'] += float(r.pr_total or 0)
            p['liqui_vigente'] += float(r.liqui or 0)
            sub_text = r.subramo if r.subramo else r.ramo
            if sub_text:
                p['subramos_vigentes'][ramo_n].add(_limpiar_subramo(sub_text))
        if r.numero_poliza:
            cur = p['polizas_prima'].get(r.numero_poliza, 0.0)
            p['polizas_prima'][r.numero_poliza] = cur + float(r.pr_total or 0)
        if r.ente:
            p['auxiliares'][r.ente] = p['auxiliares'].get(r.ente, 0.0) + float(r.pr_total or 0)
        if r.desde:
            if p['min_desde'] is None or r.desde < p['min_desde']:
                p['min_desde'] = r.desde
            if p['max_desde'] is None or r.desde > p['max_desde']:
                p['max_desde'] = r.desde
        if r.hasta:
            if p['max_hasta'] is None or r.hasta > p['max_hasta']:
                p['max_hasta'] = r.hasta
        p['recibos'].append(r)

    # ── Portfolios anteriores ─────────────────────────────────────────────────────
    portfolios_ant: dict[str, dict] = defaultdict(lambda: {
        'ramos': set(), 'prima_total': 0.0, 'polizas_prima': {},
    })
    for r in recibos_ant:
        if not r.tomador or _es_anulado(r.estado):
            continue
        t = _norm_nombre(r.tomador)
        pa = portfolios_ant[t]
        pa['ramos'].add(_normalizar_ramo(r.ramo or ''))
        pa['prima_total'] += float(r.pr_total or 0)
        if r.numero_poliza:
            cur = pa['polizas_prima'].get(r.numero_poliza, 0.0)
            pa['polizas_prima'][r.numero_poliza] = cur + float(r.pr_total or 0)

    # ── Clientes registrados ──────────────────────────────────────────────────────
    clientes_db: dict[str, Cliente] = {
        c.nombre_normalizado: c for c in db.query(Cliente).all()
    }

    # ── Percentiles de prima vigente ─────────────────────────────────────────────
    primas = sorted(p['prima_vigente'] for p in portfolios.values() if p['prima_vigente'] > 0)
    n = len(primas)
    p25 = primas[max(0, int(n * 0.25) - 1)] if n >= 4 else 0.0
    p50 = primas[max(0, int(n * 0.50) - 1)] if n >= 4 else 0.0
    p75 = primas[max(0, int(n * 0.75) - 1)] if n >= 4 else 0.0

    # ── Perfiles de compradores por ramo (para propensión interna) ────────────────
    # Usa ramos_vigentes y prima_vigente para que los perfiles sean reales
    compradores_por_ramo: dict[str, list] = defaultdict(list)
    for t, port in portfolios.items():
        c_db = clientes_db.get(t)
        tipo = c_db.tipo if c_db else TipoCliente.FISICO
        ant = _antiguedad_anos(c_db.fecha_alta if c_db else None, port['min_desde'])
        for ramo in port['ramos_vigentes']:
            compradores_por_ramo[ramo].append({
                'tipo': tipo.value,
                'antiguedad': ant,
                'prima': port['prima_vigente'],
                'n_ramos': len(port['ramos_vigentes']),
            })

    # ── Matriz de afinidad como dict rápido ──────────────────────────────────────
    matriz = params.matriz_afinidad or DEFAULT_MATRIZ
    afinidad_dict: dict[tuple, float] = {}
    afinidad_desc: dict[tuple, str] = {}
    for entry in matriz:
        key = (entry['ramo_base'], entry['ramo_objetivo'])
        afinidad_dict[key] = float(entry.get('afinidad', 0.3))
        afinidad_desc[key] = entry.get('desc', f"{entry['ramo_base']} → {entry['ramo_objetivo']}")

    ramos_objetivo = list(set(k[1] for k in afinidad_dict))

    # ── Borrar previos del ejercicio ──────────────────────────────────────────────
    db.query(CrossSellingOportunidad).filter(CrossSellingOportunidad.ejercicio == ejercicio).delete()
    db.query(FugaAlerta).filter(FugaAlerta.ejercicio == ejercicio).delete()

    ahora = datetime.now(timezone.utc)
    n_oport = 0
    n_alertas = 0

    for tomador_norm, port in portfolios.items():
        c_db = clientes_db.get(tomador_norm)
        tipo_cli = c_db.tipo if c_db else TipoCliente.FISICO
        fecha_alta_cli = c_db.fecha_alta if c_db else None
        cliente_id = c_db.id if c_db else None

        ant_anos = _antiguedad_anos(fecha_alta_cli, port['min_desde'])
        # ramos_vigentes = cartera en vigor en fecha_ref; ramos = todos del ejercicio (para fuga)
        ramos_vigentes = port['ramos_vigentes']
        ramos_act = port['ramos']
        prima_vigente = port['prima_vigente']
        liqui_vigente = port['liqui_vigente']
        n_ramos = len(ramos_vigentes)

        # Días hasta el vencimiento MÁS PRÓXIMO entre pólizas activas (no el más lejano)
        min_hasta_vigente = min(
            (r.hasta for r in port['recibos'] if r.hasta and r.hasta >= fecha_ref),
            default=None,
        )
        dias_vencimiento: Optional[int] = None
        if min_hasta_vigente:
            dias_vencimiento = (min_hasta_vigente - hoy).days

        # Renovación reciente: algún recibo con desde en últimos 60 días
        tiene_reciente = any(
            r.desde and (hoy - r.desde).days <= 60
            for r in port['recibos']
        )

        s_valor = _score_segmento_valor(prima_vigente, p25, p50, p75)
        s_timing = _score_timing(dias_vencimiento, ant_anos, tiene_reciente, params)

        # Auxiliar principal: el que más prima acumula para este cliente
        auxiliar_principal = max(port['auxiliares'], key=port['auxiliares'].get) if port['auxiliares'] else None

        # ── CROSS-SELLING ─────────────────────────────────────────────────────
        aux_excluido = auxiliar_principal is not None and auxiliar_principal in excluidos_aux
        _ramos_iter = ramos_objetivo if (not aux_excluido and ramos_vigentes) else []
        _permitidos = _RAMOS_FISICO if tipo_cli == TipoCliente.FISICO else _RAMOS_JURIDICO
        for ramo_obj in _ramos_iter:
            if ramo_obj in ramos_vigentes:  # ya lo tiene en vigor
                continue
            if ramo_obj not in _permitidos:  # no es adecuado para este tipo de cliente
                continue

            mejor_afinidad = 0.0
            mejor_desc = ""
            for ramo_base in ramos_vigentes:
                key = (ramo_base, ramo_obj)
                af = afinidad_dict.get(key, 0.0)
                if af > mejor_afinidad:
                    mejor_afinidad = af
                    mejor_desc = afinidad_desc.get(key, "")

            if mejor_afinidad < 0.30:
                continue

            s_prop = _score_propension(
                tipo_cli, ant_anos, prima_vigente, n_ramos,
                compradores_por_ramo.get(ramo_obj, [])
            )

            score_final = (
                params.peso_afinidad * mejor_afinidad * 100
                + params.peso_propension * s_prop
                + params.peso_valor * s_valor
                + params.peso_timing * s_timing
            )

            if score_final < 20:
                continue

            if score_final >= 70:
                accion = "Llamar esta semana"
            elif score_final >= 50:
                accion = "Incluir en campaña"
            elif score_final >= 35:
                accion = "Revisar en renovación"
            else:
                accion = "Monitorizar"

            motivo = _construir_motivo(ramos_vigentes, ramo_obj, ant_anos, s_prop, mejor_desc, tipo_cli)

            # Prima esperada = prima media del ramo recomendado en la cartera real
            p_esp = prima_media_ramo.get(ramo_obj)
            # Margen esperado = prima_esperada × margen medio del ramo recomendado
            m_ramo_val = margen_medio_ramo.get(ramo_obj, 0.15)
            m_esp = round(p_esp * m_ramo_val, 2) if p_esp else None

            db.add(CrossSellingOportunidad(
                ejercicio=ejercicio,
                tomador=tomador_norm,
                cliente_id=cliente_id,
                ramo_recomendado=ramo_obj,
                score=round(score_final, 1),
                score_afinidad=round(mejor_afinidad * 100, 1),
                score_propension=round(s_prop, 1),
                score_valor=round(s_valor, 1),
                score_timing=round(s_timing, 1),
                margen_esperado=m_esp,
                prima_esperada=round(p_esp, 2) if p_esp else None,
                motivo=motivo,
                accion_sugerida=accion,
                ramos_actuales=list(ramos_vigentes),
                subramos_vigentes={
                    cat: sorted(list(subs))
                    for cat, subs in port['subramos_vigentes'].items()
                    if cat in ramos_vigentes
                },
                n_ramos=n_ramos,
                prima_total_activa=round(prima_vigente, 2),
                antiguedad_anos=round(ant_anos, 1),
                tipo_cliente=tipo_cli.value,
                auxiliar=auxiliar_principal,
                recalculado_at=ahora,
            ))
            n_oport += 1

        # ── FUGA ─────────────────────────────────────────────────────────────
        senales = []
        peso_acum = 0.0
        port_ant = portfolios_ant.get(tomador_norm)

        if port_ant:
            # Ramos perdidos: tenía el año pasado y no están vigentes hoy
            ramos_perdidos = port_ant['ramos'] - ramos_vigentes
            if ramos_perdidos:
                senales.append({
                    "tipo": "ramo_perdido",
                    "desc": f"Ha perdido ramos: {', '.join(sorted(ramos_perdidos))}",
                    "peso": 1.0,
                })
                peso_acum += 1.0 * len(ramos_perdidos)

            if port_ant['prima_total'] > 0:
                caida = (port_ant['prima_total'] - prima_vigente) / port_ant['prima_total']
                if caida > params.umbral_bajada_prima:
                    senales.append({
                        "tipo": "prima_bajando",
                        "desc": f"Prima total baja un {caida * 100:.0f}% vs ejercicio anterior",
                        "peso": 0.8,
                    })
                    peso_acum += 0.8

            for poliza, prima_ant_pol in port_ant['polizas_prima'].items():
                prima_act_pol = port['polizas_prima'].get(poliza, 0.0)
                if prima_ant_pol > 0 and prima_act_pol > 0:
                    caida_pol = (prima_ant_pol - prima_act_pol) / prima_ant_pol
                    if caida_pol > params.umbral_bajada_prima:
                        senales.append({
                            "tipo": "prima_poliza_bajando",
                            "desc": f"Póliza {poliza}: prima baja {caida_pol * 100:.0f}%",
                            "peso": 0.6,
                        })
                        peso_acum += 0.6
                        break  # una señal por cliente es suficiente

        if dias_vencimiento is not None and 0 < dias_vencimiento <= params.dias_vencimiento_urgente:
            senales.append({
                "tipo": "vencimiento_proximo",
                "desc": f"Vence en {dias_vencimiento} días",
                "peso": 0.9,
            })
            peso_acum += 0.9

        if port_ant and len(port_ant['ramos']) > 1 and n_ramos == 1:
            senales.append({
                "tipo": "cartera_reducida",
                "desc": "Cartera reducida a 1 ramo",
                "peso": 0.7,
            })
            peso_acum += 0.7

        # Sin nueva póliza desde hace mucho (usa max_desde, no max_hasta)
        max_desde = port.get('max_desde')
        if max_desde:
            dias_sin_nueva = (hoy - max_desde).days
            if dias_sin_nueva > params.dias_inactividad_riesgo:
                senales.append({
                    "tipo": "sin_renovacion",
                    "desc": f"Sin nueva póliza desde hace {dias_sin_nueva // 30} meses — posible desvinculación progresiva",
                    "peso": 0.6,
                })
                peso_acum += 0.6

        # Cartera monomedades: 1 solo ramo → riesgo de pérdida total de la relación
        if n_ramos == 1 and prima_vigente > 0:
            ramo_unico = next(iter(ramos_vigentes), '?')
            senales.append({
                "tipo": "mono_cartera",
                "desc": f"Solo tiene contratado {ramo_unico}. Si no renueva, se pierde la relación completa",
                "peso": 0.45,
            })
            peso_acum += 0.45

        if not senales:
            continue

        risk_score = min(100.0, (peso_acum / 4.0) * 100)
        margen_real_cli = margenes_reales.get(tomador_norm, 0.15)
        # valor_protegido = comisión activa × margen neto del cliente
        # (la comisión = liqui, que es lo que realmente ingresa el bróker)
        base_valor = liqui_vigente if liqui_vigente > 0 else prima_vigente
        valor_protegido = round(base_valor * margen_real_cli, 2)
        prioridad = round(risk_score * valor_protegido / 1000, 4)

        tipos_senal = {s['tipo'] for s in senales}
        if 'ramo_perdido' in tipos_senal:
            accion_r = "Analizar causa de pérdida de ramos y recuperar relación"
        elif 'vencimiento_proximo' in tipos_senal:
            accion_r = "Contactar antes del vencimiento para asegurar la renovación"
        elif 'prima_bajando' in tipos_senal:
            accion_r = "Revisar satisfacción — riesgo de reducción de cobertura"
        elif 'sin_renovacion' in tipos_senal:
            accion_r = "Contactar para revisar necesidades — sin nuevos productos desde hace meses"
        elif 'mono_cartera' in tipos_senal:
            accion_r = "Proponer ampliación de cartera — cliente con un único producto"
        else:
            accion_r = "Monitorizar y reforzar relación"

        db.add(FugaAlerta(
            ejercicio=ejercicio,
            tomador=tomador_norm,
            cliente_id=cliente_id,
            risk_score=round(risk_score, 1),
            valor_protegido=valor_protegido,
            prioridad=prioridad,
            senales=senales,
            accion_recomendada=accion_r,
            dias_hasta_vencimiento=dias_vencimiento,
            prima_total_activa=round(prima_vigente, 2),
            liqui_vigente=round(liqui_vigente, 2),
            n_ramos=n_ramos,
            antiguedad_anos=round(ant_anos, 1),
            tipo_cliente=tipo_cli.value,
            auxiliar=auxiliar_principal,
            ramos_actuales=list(ramos_vigentes),
            recalculado_at=ahora,
        ))
        n_alertas += 1

    db.flush()
    log.info(
        "Cross-selling recalculado | ejercicio=%d oportunidades=%d alertas=%d",
        ejercicio, n_oport, n_alertas,
    )
    return {"oportunidades": n_oport, "alertas": n_alertas}
