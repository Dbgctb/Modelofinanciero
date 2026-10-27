"""
Servicio del Modelo Analítico de Rentabilidad.
Implementa enriquecimiento contable, imputación directa/indirecta y P&L analítico.
"""
import logging
import re as _re
import threading
import unicodedata as _ud
import uuid as _uuid_mod
from collections import defaultdict

from sqlalchemy import insert as _sa_insert
from sqlalchemy.orm import Session

from ..models.analitico import (
    AnaliticoMapCuenta, AnaliticoMapDriver, AnaliticoAjusteCoste,
    FactResultadoAnalitico,
    DRIVERS_DEFAULT, NATURALEZAS_COSTE_OP,
    NATURALEZA_RESULTADO_FINANCIERO, PREFIJOS_RESULTADO_FINANCIERO,
    PESO_POLIZA_INTERMEDIADA,
)
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..models.recibo import Recibo
from .normalizer import extraer_codigo_recibo
from .tasa_cesion import resolver_tasa, TASA_AUX_CTE, TASA_EXPR

log = logging.getLogger(__name__)

# ── Gestión de tareas en segundo plano ───────────────────────────────────────
_TASKS: dict[str, dict] = {}
_TASKS_LOCK = threading.Lock()
_BATCH = 2000  # filas por INSERT


def _prog(task_id: str, step: int, total: int, msg: str, done: bool = False, error: str | None = None):
    with _TASKS_LOCK:
        _TASKS[task_id] = {
            "step": step, "total": total,
            "pct": int(step / total * 100) if total else 0,
            "mensaje": msg, "done": done,
            **({"error": error} if error else {}),
        }


def get_task_status(task_id: str) -> dict | None:
    with _TASKS_LOCK:
        return dict(_TASKS.get(task_id, {})) or None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _lookup_naturaleza(numero_cuenta: str | None, map_nat: dict) -> str | None:
    if not numero_cuenta:
        return None
    if numero_cuenta in map_nat:
        return map_nat[numero_cuenta]
    for length in range(min(len(numero_cuenta) - 1, 7), 2, -1):
        prefix = numero_cuenta[:length]
        if prefix in map_nat:
            return map_nat[prefix]
    return None


# ── Normalización canónica de compañías ──────────────────────────────────────
# Las claves del mapa explícito y las palabras de las reglas están en ASCII
# uppercase (sin tildes) para ser inmunes a diferencias NFC/NFD entre la BD
# y el código fuente Python.  La función convierte el input a ASCII-upper
# antes de comparar.

# Mapa explícito: nombres legales completos → nombre canónico
_COMPANIA_EXACT: dict[str, str] = {
    # MAPFRE
    'MAPFRE ESPANA, COMPANIA DE SEGUROS Y REASEGUROS': 'MAPFRE',
    # REALE no-vida
    'REALE SEGUROS GENERALES': 'REALE',
    # REALE vida → nombre corto canónico
    'REALE VIDA Y PENSIONES, SOCIEDAD ANONIMA DE SEGUROS': 'REALE VIDA',
    # OCCIDENT ≡ CATALANA (mismo grupo)
    'CATALANA': 'OCCIDENT',
    # PELAYO forma larga
    'PELAYO, MUTUA DE SEGUROS Y REASEGUROS A PRIMA FIJA': 'PELAYO',
    # PREVENTIVA forma larga
    'PREVENTIVA, CIA. DE SEGUROS Y REASEGUROS': 'PREVENTIVA',
}

# Reglas de contenido: (palabras_requeridas, palabras_excluidas, nombre_canónico)
# Las exclusiones protegen a las ramas de vida de ser absorbidas por la regla del grupo.
_COMPANIA_RULES: list[tuple[list[str], list[str], str]] = [
    (['MAPFRE'],     ['VIDA', 'PENSION'],   'MAPFRE'),
    (['REALE'],      ['VIDA', 'PENSION'],   'REALE'),
    (['PELAYO'],     [],                    'PELAYO'),
    (['PREVENTIVA'], [],                    'PREVENTIVA'),
]


def _ascii_upper(s: str) -> str:
    """Convierte a ASCII uppercase eliminando tildes (NFKD → encode ascii ignore)."""
    return _ud.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()


def _norm_compania(name: str | None) -> str | None:
    """
    Devuelve el nombre canónico de la compañía:
    1. Mapa explícito (insensible a tildes/encoding NFC-NFD).
    2. Reglas de contenido (palabras clave en el nombre).
    3. Limpieza de sufijos legales/geográficos residuales.
    """
    if not name:
        return name
    nfc = _ud.normalize('NFC', name).strip()
    key = _ascii_upper(nfc)

    # 1. Mapa explícito
    if key in _COMPANIA_EXACT:
        return _COMPANIA_EXACT[key]

    # 2. Reglas de contenido
    for required, excluded, canonical in _COMPANIA_RULES:
        if all(w in key for w in required) and not any(w in key for w in excluded):
            return canonical

    # 3. Limpieza regex de sufijos legales/geográficos residuales
    n = nfc
    for pat, repl in [
        (_re.compile(r',\s*S\.?A\.?U?\.?\s*$', _re.IGNORECASE), ''),
        (_re.compile(r',\s*S\.?L\.?U?\.?\s*$', _re.IGNORECASE), ''),
        (_re.compile(r',?\s*Cí?a\.?\s*$',      _re.IGNORECASE), ''),
        (_re.compile(r'\s+de\s+Seguros\s*$',   _re.IGNORECASE), ''),
        (_re.compile(r'\s+Seguros\s*$',        _re.IGNORECASE), ''),
        (_re.compile(r',?\s+España\s*$',       _re.IGNORECASE), ''),
    ]:
        n = pat.sub(repl, n)
    n = n.strip().rstrip(',').strip()
    return n if n else name


def _cap_cesion_rows(direct_rows: list[dict], group_key: str) -> int:
    """
    Recorre direct_rows y escala las filas de cesión de cada grupo para que
    total_cesion ≤ total_ingreso. Si la cesión ya es 0, no toca nada.
    Devuelve el número de grupos ajustados.
    """
    income: dict = defaultdict(float)
    cesion_idxs: dict = defaultdict(list)
    for i, row in enumerate(direct_rows):
        g = row.get(group_key)
        if g is None:
            continue
        if row['tipo_cuenta'] == 'ingreso':
            income[g] += float(row['importe'])
        elif row.get('naturaleza') == 'Cesión auxiliar':
            cesion_idxs[g].append(i)
    ajustados = 0
    for g, idxs in cesion_idxs.items():
        total_cesion = sum(-direct_rows[i]['importe'] for i in idxs)
        if total_cesion == 0:
            continue
        total_income = income.get(g, 0.0)
        if total_cesion > total_income:
            ratio = total_income / total_cesion if total_cesion > 0 else 0.0
            for i in idxs:
                direct_rows[i]['importe'] = round(direct_rows[i]['importe'] * ratio, 4)
            ajustados += 1
    return ajustados


def _compute_weights(recibos_list, driver: str) -> dict:
    """
    Calcula pesos de reparto para cada (compania, ramo, auxiliar, es_np).
    Devuelve dict con pesos normalizados que suman 1.
    """
    totals: dict[tuple, float] = defaultdict(float)
    # POLIZAS: cada póliza suma 1 (PESO_POLIZA_INTERMEDIADA si tiene auxiliar),
    # repartido entre sus recibos del ejercicio (una póliza mensual con 12 recibos
    # pesa lo mismo que una anual con 1). Un recibo sin número de póliza cuenta como
    # una póliza propia.
    recibos_por_poliza: dict[str, int] = defaultdict(int)
    if driver == 'POLIZAS':
        for r in recibos_list:
            recibos_por_poliza[r.numero_poliza or f"_rec_{r.id}"] += 1
    for r in recibos_list:
        es_np = (r.tipo_negocio == 'nueva_produccion')
        key = (_norm_compania(r.compania), r.ramo, r.subramo, r.ente, es_np)
        if driver == 'RECIBOS':
            totals[key] += 1.0
        elif driver == 'POLIZAS':
            peso_canal = PESO_POLIZA_INTERMEDIADA if r.ente else 1.0
            totals[key] += peso_canal / recibos_por_poliza[r.numero_poliza or f"_rec_{r.id}"]
        elif driver == 'COMISION_NETA':
            totals[key] += float(r.liqui or 0)
        elif driver == 'NUEVA_PRODUCCION':
            if es_np:
                totals[key] += float(r.liqui or 0)

    total = sum(v for v in totals.values() if v > 0)
    if total == 0:
        return {}
    return {k: v / total for k, v in totals.items() if v > 0}



# ── Recálculo ─────────────────────────────────────────────────────────────────

def _build_row(base: dict, extra: dict) -> dict:
    r = {**base, **extra, "id": _uuid_mod.uuid4()}
    return r


def _recalcular_worker(db: Session, ejercicio: int, task_id: str):
    """Ejecuta el recálculo en segundo plano. db debe ser una sesión nueva."""
    try:
        _prog(task_id, 1, 6, "Cargando mapas de cuentas y drivers…")
        _mc_all = db.query(AnaliticoMapCuenta).all()
        map_nat = {mc.numero_cuenta: mc.naturaleza for mc in _mc_all}
        # Mapa auxiliar por cuenta 623*: descripcion = nombre del auxiliar.
        # Solo cuentas específicas (len > 3) para no usar el prefijo genérico '623'.
        map_aux_623 = {
            mc.numero_cuenta: mc.descripcion
            for mc in _mc_all
            if mc.numero_cuenta.startswith('623') and len(mc.numero_cuenta) > 3
            and mc.descripcion and mc.descripcion not in ('Auxiliares', 'Cesión auxiliar')
        }
        raw_drv = {md.naturaleza: md.driver for md in db.query(AnaliticoMapDriver).all()}
        map_drv = {**DRIVERS_DEFAULT, **raw_drv}

        _prog(task_id, 2, 6, "Cargando recibos y calculando pesos de reparto…")
        # Solo recibos con apuntes de INGRESO en el ejercicio: base correcta para drivers.
        # Usar todos los apuntes (incluidos 623 de años anteriores) distorsionaría
        # los pesos de reparto incluyendo negocio de ejercicios previos.
        recibo_ids_en_diario = {
            str(r[0])
            for r in db.execute(
                _text(
                    "SELECT DISTINCT recibo_id FROM diario_apuntes "
                    "WHERE ejercicio = :ej AND recibo_id IS NOT NULL "
                    "AND tipo_cuenta = 'INGRESO' AND estado::text != 'excluido'"
                ),
                {"ej": ejercicio},
            )
        }
        recibos_list = (
            db.query(Recibo)
            .filter(Recibo.id.in_(recibo_ids_en_diario))
            .all()
        ) if recibo_ids_en_diario else []
        recibos_by_id   = {str(r.id):    r for r in recibos_list}
        recibos_by_code = {r.codigo:     r for r in recibos_list if r.codigo}

        # RECIBOS y NUEVA_PRODUCCION se calculan desde los recibos del diario.
        # COMISION_NETA se calcula desde los ingresos reales del diario (segunda pasada
        # tras procesar las filas directas), para evitar distorsión por recibos.liqui.
        weights_cache = {
            'RECIBOS':          _compute_weights(recibos_list, 'RECIBOS'),
            'POLIZAS':          _compute_weights(recibos_list, 'POLIZAS'),
            'NUEVA_PRODUCCION': _compute_weights(recibos_list, 'NUEVA_PRODUCCION'),
            'COMISION_NETA':    {},   # se rellena tras procesar ingresos directos
        }

        _prog(task_id, 3, 6, "Leyendo apuntes contables…")
        apuntes = db.query(DiarioApunte).filter(
            DiarioApunte.ejercicio == ejercicio,
            DiarioApunte.estado != EstadoApunte.EXCLUIDO,
        ).all()

        _prog(task_id, 4, 6, f"Procesando {len(apuntes):,} apuntes…")

        direct_rows: list[dict] = []
        indirect_grp: dict[tuple, dict] = {}

        # Contadores diagnóstico
        _cnt_623_total = _cnt_623_nivel1 = _cnt_623_nivel2 = _cnt_623_nivel3 = _cnt_623_nivel4 = _cnt_623_skip = 0

        base_fields = ("ejercicio", "mes", "fecha", "numero_cuenta",
                       "descripcion_cuenta", "tipo_cuenta", "naturaleza", "driver")

        for ap in apuntes:
            importe = float(ap.haber or 0) - float(ap.debe or 0)

            if ap.tipo_cuenta == TipoCuenta.TESORERIA_EXCLUIDA:
                continue

            if ap.tipo_cuenta == TipoCuenta.INGRESO:
                tipo_cuenta, naturaleza, driver = 'ingreso', None, None
            else:
                tipo_cuenta = 'gasto'
                # 623 es Cesión auxiliar SOLO si tiene auxiliar identificado.
                # Prioridad de resolución:
                #   1. ap.auxiliar (campo BD, poblado en reimportaciones)
                #   2. map_aux_623: descripción de AnaliticoMapCuenta para la cuenta exacta
                #   3. concepto → código recibo → recibo.ente
                # Sin auxiliar = directo de correduría, se descarta del modelo.
                if ap.numero_cuenta and ap.numero_cuenta.startswith('623'):
                    _cnt_623_total += 1
                    # Normaliza: el string 'None' / 'nan' / '' se trata como sin auxiliar
                    _raw = (ap.auxiliar or '').strip()
                    auxiliar_623: str | None = _raw if _raw and _raw.lower() not in ('none', 'nan') else None
                    if auxiliar_623:
                        _cnt_623_nivel1 += 1
                    else:
                        # Busca por cuenta exacta, luego prefijos más cortos (min 4 chars)
                        nc = ap.numero_cuenta
                        for length in range(len(nc), 3, -1):
                            desc = map_aux_623.get(nc[:length])
                            if desc:
                                auxiliar_623 = desc
                                _cnt_623_nivel2 += 1
                                break
                    if not auxiliar_623 and ap.concepto:
                        cod = extraer_codigo_recibo(ap.concepto)
                        if cod:
                            r_cod = recibos_by_code.get(cod)
                            if r_cod:
                                auxiliar_623 = r_cod.ente
                                _cnt_623_nivel3 += 1
                    # Nivel 4: descripción de cuenta (asesoramientos, ajustes, rappels sin recibo)
                    if not auxiliar_623 and ap.descripcion_cuenta:
                        desc_cta = (ap.descripcion_cuenta or '').strip()
                        if desc_cta and desc_cta.lower() not in ('none', 'nan'):
                            auxiliar_623 = desc_cta
                            _cnt_623_nivel4 += 1
                    if auxiliar_623:
                        naturaleza = 'Cesión auxiliar'
                        if not ap.auxiliar:
                            ap.auxiliar = auxiliar_623
                    else:
                        _cnt_623_skip += 1
                        # Toda cuenta 623 ES cesión — aunque no se identifique el auxiliar.
                        # Se incluye en fact con auxiliar=None para que el total cuadre
                        # exactamente con el diario. En los dashboards aparece como
                        # "(Sin auxiliar)" en el desglose por auxiliar.
                        naturaleza = 'Cesión auxiliar'
                elif ap.numero_cuenta and ap.numero_cuenta.startswith(PREFIJOS_RESULTADO_FINANCIERO):
                    naturaleza = NATURALEZA_RESULTADO_FINANCIERO
                else:
                    naturaleza = _lookup_naturaleza(ap.numero_cuenta, map_nat)
                driver = map_drv.get(naturaleza, 'RECIBOS') if naturaleza else 'RECIBOS'

            if ap.recibo_id:
                rec = recibos_by_id.get(str(ap.recibo_id))
                direct_rows.append({
                    "id": _uuid_mod.uuid4(),
                    "ejercicio": ejercicio, "mes": ap.mes, "fecha": ap.fecha,
                    "apunte_id": ap.id, "numero_cuenta": ap.numero_cuenta,
                    "descripcion_cuenta": ap.descripcion_cuenta,
                    "tipo_cuenta": tipo_cuenta, "naturaleza": naturaleza,
                    "driver": driver, "tipo_imputacion": 'DIRECTA',
                    "recibo_id": ap.recibo_id,
                    "compania": _norm_compania(rec.compania if rec else ap.compania),
                    "ramo": rec.ramo if rec else ap.ramo,
                    "subramo": rec.subramo if rec else None,
                    "auxiliar": rec.ente if rec else ap.auxiliar,
                    "es_nueva_produccion": (rec.tipo_negocio == 'nueva_produccion') if rec else False,
                    "importe": importe,
                })
            elif tipo_cuenta == 'ingreso' or naturaleza == 'Cesión auxiliar':
                # Ingreso sin recibo (ajuste "Directo") o cesión sin recibo pero con auxiliar:
                # entrada directa atribuida al auxiliar del apunte.
                direct_rows.append({
                    "id": _uuid_mod.uuid4(),
                    "ejercicio": ejercicio, "mes": ap.mes, "fecha": ap.fecha,
                    "apunte_id": ap.id, "numero_cuenta": ap.numero_cuenta,
                    "descripcion_cuenta": ap.descripcion_cuenta,
                    "tipo_cuenta": tipo_cuenta, "naturaleza": naturaleza,
                    "driver": driver, "tipo_imputacion": 'DIRECTA',
                    "recibo_id": None,
                    "compania": _norm_compania(ap.compania), "ramo": ap.ramo,
                    "subramo": None, "auxiliar": ap.auxiliar,
                    "es_nueva_produccion": False,
                    "importe": importe,
                })
            else:
                # Costes operativos (6xx excepto 623) sin recibo → pool indirecto por driver.
                key = (ap.mes, ap.numero_cuenta, naturaleza, driver or 'RECIBOS', tipo_cuenta)
                if key not in indirect_grp:
                    indirect_grp[key] = {
                        "total": 0.0,
                        "mes": ap.mes, "numero_cuenta": ap.numero_cuenta,
                        "descripcion_cuenta": ap.descripcion_cuenta,
                        "naturaleza": naturaleza, "driver": driver or 'RECIBOS',
                        "tipo_cuenta": tipo_cuenta,
                    }
                indirect_grp[key]["total"] += importe

        log.info(
            "Recálculo [ej=%s] — 623: total=%d | nivel1(ap.aux)=%d | nivel2(map)=%d | "
            "nivel3(recibo)=%d | nivel4(desc_cta)=%d | descartados=%d | direct_rows=%d",
            ejercicio, _cnt_623_total, _cnt_623_nivel1, _cnt_623_nivel2,
            _cnt_623_nivel3, _cnt_623_nivel4, _cnt_623_skip, len(direct_rows),
        )
        log.info(
            "Recálculo [ej=%s] — map_aux_623 tiene %d entradas",
            ejercicio, len(map_aux_623),
        )
        # Muestra las primeras 3 entradas de map_aux_623 para verificar contenido
        for k, v in list(map_aux_623.items())[:3]:
            log.info("  map_aux_623 muestra: %r → %r", k, v)
        # Muestra las primeras 3 entradas directas de cesión
        cesion_sample = [r for r in direct_rows if r.get('naturaleza') == 'Cesión auxiliar'][:3]
        for r in cesion_sample:
            log.info("  cesión directa: cuenta=%s aux=%r imp=%s", r['numero_cuenta'], r['auxiliar'], r['importe'])

        # Log de normalizaciones de compañía para diagnóstico
        _norm_changes = {
            r.compania: _norm_compania(r.compania)
            for r in recibos_list
            if r.compania and _norm_compania(r.compania) != r.compania
        }
        if _norm_changes:
            log.info("Recálculo [ej=%s] — normalizaciones compañía (%d): %s",
                     ejercicio, len(_norm_changes),
                     ', '.join(f'{k!r}→{v!r}' for k, v in list(_norm_changes.items())[:15]))
        else:
            log.info("Recálculo [ej=%s] — sin normalizaciones de compañía (nombres ya canónicos)", ejercicio)

        # ── Ajustes de imputación manual ──────────────────────────────────────
        # Extrae importe del pool indirecto (640/642/…) y lo reasigna como coste
        # directo al auxiliar configurado. Caso típico: sueldo de empleado adscrito
        # a un colaborador concreto que se descuenta de su liquidación.
        ajustes = db.query(AnaliticoAjusteCoste).filter(
            AnaliticoAjusteCoste.ejercicio == ejercicio,
            AnaliticoAjusteCoste.activo == True,
        ).all()

        if ajustes:
            for aj in ajustes:
                aj_total = float(aj.importe_mensual) * 12  # importe anual a reclasificar
                prefix   = aj.numero_cuenta              # e.g. '640', '642'

                # 1. Reducir el pool indirecto de la cuenta origen proporcionalmente.
                #    El coste sale de 640/642 (Personal/SS) → el pool queda más pequeño
                #    y el resto de auxiliares absorben menos coste de personal.
                pool_abs = sum(
                    abs(meta["total"])
                    for (_, cta, _, _, _), meta in indirect_grp.items()
                    if cta.startswith(prefix) and meta["total"] < 0
                )
                if pool_abs > 0:
                    for key, meta in indirect_grp.items():
                        _, cta, _, _, _ = key
                        if cta.startswith(prefix) and meta["total"] < 0:
                            frac = abs(meta["total"]) / pool_abs
                            meta["total"] += frac * aj_total  # menos negativo = menos coste indirecto

                log.info(
                    "Ajuste coste [ej=%s]: %r → %.2f €/año extraídos de pool %s (reduce costes analíticos, sin fila de cesión)",
                    ejercicio, aj.descripcion, aj_total, prefix,
                )

        # Cap cesión: ninguna compañía ni auxiliar puede tener cesión > ingreso
        n_cia_ajust = _cap_cesion_rows(direct_rows, 'compania')
        n_aux_ajust = _cap_cesion_rows(direct_rows, 'auxiliar')
        if n_cia_ajust or n_aux_ajust:
            log.info(
                "Recálculo [ej=%s] — cap cesión: %d compañías y %d auxiliares ajustados",
                ejercicio, n_cia_ajust, n_aux_ajust,
            )

        # Calcula COMISION_NETA desde los ingresos reales del diario (no desde recibos.liqui)
        # para evitar distorsión: un auxiliar con historial alto de liquidaciones no absorbe
        # costes de otros si su participación real en 2025 es menor.
        _income_by_key: dict[tuple, float] = defaultdict(float)
        for row in direct_rows:
            if row['tipo_cuenta'] == 'ingreso' and (row.get('compania') or row.get('auxiliar')):
                # Solo ingresos con atribución conocida: los "Directo" (sin compañía ni auxiliar)
                # no participan en el reparto de costes operativos.
                k = (row.get('compania'), row.get('ramo'), row.get('subramo'), row.get('auxiliar'), row.get('es_nueva_produccion', False))
                _income_by_key[k] += float(row['importe'])
        _total_income = sum(v for v in _income_by_key.values() if v > 0)
        if _total_income > 0:
            weights_cache['COMISION_NETA'] = {
                k: v / _total_income for k, v in _income_by_key.items() if v > 0
            }

        # Expande grupos indirectos por driver weights
        indirect_rows: list[dict] = []
        for meta in indirect_grp.values():
            drv = meta["driver"]
            total_imp = meta["total"]
            w_dict = weights_cache.get(drv, {})
            base = {
                "id": None,  # se asigna abajo
                "ejercicio": ejercicio, "mes": meta["mes"], "fecha": None,
                "apunte_id": None, "numero_cuenta": meta["numero_cuenta"],
                "descripcion_cuenta": meta["descripcion_cuenta"],
                "tipo_cuenta": meta["tipo_cuenta"], "naturaleza": meta["naturaleza"],
                "driver": drv, "tipo_imputacion": 'INDIRECTA', "recibo_id": None,
            }
            if not w_dict:
                r = {**base, "id": _uuid_mod.uuid4(),
                     "compania": None, "ramo": None, "subramo": None,
                     "auxiliar": None, "es_nueva_produccion": False, "importe": total_imp}
                indirect_rows.append(r)
            else:
                for (comp, ramo, subramo, aux, es_np), w in w_dict.items():
                    r = {**base, "id": _uuid_mod.uuid4(),
                         "compania": comp, "ramo": ramo, "subramo": subramo,
                         "auxiliar": aux, "es_nueva_produccion": es_np,
                         "importe": round(total_imp * w, 4)}
                    indirect_rows.append(r)

        all_rows = direct_rows + indirect_rows
        total_rows = len(all_rows)

        _prog(task_id, 5, 6, f"Eliminando datos anteriores y guardando {total_rows:,} filas…")
        db.query(FactResultadoAnalitico).filter(
            FactResultadoAnalitico.ejercicio == ejercicio
        ).delete(synchronize_session=False)
        db.commit()

        # INSERT por lotes con Core — mucho más rápido que bulk_save_objects
        for i in range(0, total_rows, _BATCH):
            lote = all_rows[i: i + _BATCH]
            db.execute(_sa_insert(FactResultadoAnalitico), lote)
            # Actualizar mensaje de progreso cada 10 lotes
            if i % (_BATCH * 10) == 0 and total_rows > _BATCH:
                _prog(task_id, 5, 6,
                      f"Guardando… {min(i + _BATCH, total_rows):,}/{total_rows:,} filas")
        db.commit()
        # Estadísticas al día tras reescribir ~200k filas: sin esto el planificador
        # usa las de antes y las consultas de cesión estimada (tasa por auxiliar)
        # pasaban de 0,3 s a más de 25 minutos (visto en vivo 2026-10-27).
        db.execute(_text("ANALYZE fact_resultado_analitico"))
        db.commit()

        _prog(task_id, 6, 6,
              f"Completado: {total_rows:,} filas ({len(apuntes):,} apuntes, "
              f"{len(direct_rows):,} directas, {len(indirect_rows):,} indirectas)",
              done=True)

    except Exception as exc:
        log.error("Error en recálculo analítico ejercicio=%s: %s", ejercicio, exc, exc_info=True)
        _prog(task_id, 0, 6, str(exc), done=True, error=str(exc))
    finally:
        db.close()


def recalcular_analitico_async(ejercicio: int) -> str:
    """Lanza el recálculo en un hilo y devuelve el task_id para polling."""
    from ..core.database import SessionLocal
    task_id = str(_uuid_mod.uuid4())
    _prog(task_id, 0, 6, "Iniciando…")

    def run():
        db = SessionLocal()
        _recalcular_worker(db, ejercicio, task_id)

    threading.Thread(target=run, daemon=True).start()
    return task_id


# ── Dashboards — todo por SQL agregado, cero carga ORM en memoria ─────────────

from sqlalchemy import text as _text

# Subquery: recibos con apunte de INGRESO en el ejercicio.
# Restricción a ingresos: excluye recibos que solo aparecen en 623 de años anteriores,
# garantizando que conteos y drivers reflejan solo el negocio del año.
_REC_EN_EJ = (
    "SELECT DISTINCT recibo_id FROM diario_apuntes "
    "WHERE ejercicio = :ej AND recibo_id IS NOT NULL "
    "AND tipo_cuenta = 'INGRESO' AND estado::text != 'excluido'"
)


def _q(db: Session, sql: str, **kw):
    """Ejecuta SQL parametrizado y devuelve lista de Row."""
    return db.execute(_text(sql), kw).fetchall()


def _calc_pl(rows) -> dict:
    """Calcula P&L a partir de filas (tipo_cuenta, naturaleza, importe).
    EBITDA es el contable real: incluye gastos con naturaleza NULL (sin_mapear)."""
    l1      = sum(float(r[2]) for r in rows if r[0] == 'ingreso')
    l2      = sum(float(r[2]) for r in rows if r[1] == 'Cesión auxiliar')
    cop     = sum(float(r[2]) for r in rows if r[0] == 'gasto' and r[1] in NATURALEZAS_COSTE_OP)
    mkt     = sum(float(r[2]) for r in rows if r[1] == 'Marketing')
    sin_map = sum(float(r[2]) for r in rows if r[0] == 'gasto' and r[1] is None)
    cn  = l1 + l2
    mo  = cn + cop
    eb  = mo + mkt + sin_map   # EBITDA contable: incluye gastos sin naturaleza asignada
    p   = lambda n, d: round(n / d * 100, 2) if d else 0.0
    return {
        "comision_bruta":      round(l1,       2),
        "comision_auxiliar":   round(-l2,      2),
        "comision_neta":       round(cn,        2),
        "costes_operativos":   round(-cop,      2),
        "margen_operativo":    round(mo,        2),
        "costes_captacion":    round(-mkt,      2),
        "sin_mapear":          round(-sin_map,  2),
        "ebitda":              round(eb,        2),
        "margen_pct":          p(eb, l1),
        "ratio_cesion_pct":    p(-l2, l1),
        "ratio_costes_op_pct": p(-cop, l1),
    }


def _add_estimado(m: dict, tasa: float) -> dict:
    """Añade cesion_estimada, ebitda_estimado y margen_pct_estimado a un dict de P&L.
    Solo aplica si la entidad tiene ingresos y cesión real = 0 (válido para auxiliar/NP)."""
    bruta    = m.get("comision_bruta",    0.0)
    ces_real = m.get("comision_auxiliar", 0.0)
    eb       = m.get("ebitda",            0.0)
    ces_est  = round(bruta * tasa, 2) if (bruta > 0 and ces_real == 0.0 and tasa > 0) else 0.0
    m["cesion_estimada"]     = ces_est
    m["tiene_estimada"]      = ces_est > 0
    m["ebitda_estimado"]     = round(eb - ces_est, 2)
    m["margen_pct_estimado"] = round((eb - ces_est) / bruta * 100, 2) if bruta else 0.0
    return m


def _cesion_estimada_por_dim(
    db: Session,
    ejercicio: int,
    dimension: str,
    tasa: float,
    ramo_filtro: str | None = None,
) -> dict:
    """
    Cesión estimada por dimensión (compania | ramo | subramo).

    Identifica recibos con auxiliar asignado (recibos.ente IS NOT NULL) pero sin
    ninguna fila de cesión DIRECTA en fact_resultado_analitico (numero_cuenta 623*),
    y calcula: Σ(ingresos de esos recibos) × tasa para cada valor de la dimensión.

    Es más precisa que _add_estimado para compañía/ramo/subramo porque no requiere
    que el total agregado de cesión sea 0 — detecta recibos individuales sin pagar.
    """
    assert dimension in {'compania', 'ramo', 'subramo', 'auxiliar'}, f"Dimensión no soportada: {dimension}"

    if dimension == 'subramo':
        select_col = "f.ramo, COALESCE(f.subramo, '(Sin subramo)')"
        group_col  = "f.ramo, COALESCE(f.subramo, '(Sin subramo)')"
        dim_filter = "AND f.ramo IS NOT NULL"
        if ramo_filtro:
            dim_filter += " AND f.ramo = :ramo"
    elif dimension == 'auxiliar':
        # Para auxiliar usamos r.ente (la fuente de verdad) agrupado por f.auxiliar
        select_col = "f.auxiliar"
        group_col  = "f.auxiliar"
        dim_filter = "AND f.auxiliar IS NOT NULL"
    else:
        select_col = f"f.{dimension}"
        group_col  = f"f.{dimension}"
        dim_filter = f"AND f.{dimension} IS NOT NULL"

    params: dict = {"ej": ejercicio, "tasa": tasa}
    if ramo_filtro:
        params["ramo"] = ramo_filtro

    # Cada recibo se estima con la tasa real de su auxiliar (tasa = respaldo).
    sql = _CES_EST_CTE + f"""
        SELECT
            {select_col},
            COALESCE(SUM(CAST(f.importe AS FLOAT) * {TASA_EXPR}), 0) AS ces_est
        FROM fact_resultado_analitico f
        JOIN recibos_sin_cesion_directa rsc ON f.recibo_id = rsc.recibo_id
        JOIN recibos rec ON rec.id = f.recibo_id
        LEFT JOIN tasa_aux ta ON ta.ente = rec.ente
        WHERE f.ejercicio = :ej
          AND f.tipo_cuenta = 'ingreso'
          {dim_filter}
        GROUP BY {group_col}
    """

    rows = db.execute(_text(sql), params).fetchall()

    if dimension == 'subramo':
        return {(r[0], r[1]): round(float(r[2]), 2) for r in rows}
    else:
        return {r[0]: round(float(r[1]), 2) for r in rows if r[0] is not None}


# SQL reutilizable: recibos con auxiliar, con ingreso en el ejercicio y sin cuenta 623*.
# Mismo criterio de exclusión que rentabilidad_cliente (numero_cuenta, no naturaleza).
_CES_EST_CTE = """
    WITH recibos_sin_cesion_directa AS (
        SELECT r.id AS recibo_id
        FROM recibos r
        WHERE r.ente IS NOT NULL
          AND r.id IN (
              SELECT DISTINCT recibo_id
              FROM fact_resultado_analitico
              WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
          )
          AND r.id NOT IN (
              SELECT DISTINCT recibo_id
              FROM fact_resultado_analitico
              WHERE ejercicio = :ej AND numero_cuenta LIKE '623%' AND recibo_id IS NOT NULL
          )
    ),
""" + TASA_AUX_CTE


def _cesion_estimada_global(db: Session, ejercicio: int, tasa: float) -> tuple[float, int]:
    """
    Total de cesión estimada — MISMA aritmética que rentabilidad_cliente:
    GROUP BY tomador → round por cliente → suma, filtrando tomadores con ingreso total < 0
    (equivalente al filtro ingreso_bruto >= min_comision=0 de rentabilidad).
    Retorna (cesion_estimada_total, n_tomadores).
    """
    rows = _q(db, """
        WITH recibos_sin_cesion AS (
            SELECT r.id AS recibo_id
            FROM recibos r
            WHERE r.ente IS NOT NULL
              AND r.id IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
              )
              AND r.id NOT IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej
                    AND numero_cuenta LIKE '623%%'
                    AND recibo_id IS NOT NULL
              )
        ),
        tomadores_con_ingreso_positivo AS (
            SELECT r.tomador
            FROM fact_resultado_analitico f
            JOIN recibos r ON f.recibo_id = r.id
            WHERE f.ejercicio = :ej AND f.tipo_cuenta = 'ingreso'
              AND r.tomador IS NOT NULL AND r.tomador != ''
            GROUP BY r.tomador
            HAVING COALESCE(SUM(CAST(f.importe AS FLOAT)), 0) >= 0
        ),
    """ + TASA_AUX_CTE + f"""
        SELECT
            rec.tomador,
            COALESCE(SUM(CAST(f.importe AS FLOAT) * {TASA_EXPR}), 0) AS cesion_est
        FROM fact_resultado_analitico f
        JOIN recibos rec ON f.recibo_id = rec.id
        JOIN recibos_sin_cesion rsc ON f.recibo_id = rsc.recibo_id
        JOIN tomadores_con_ingreso_positivo tip ON rec.tomador = tip.tomador
        LEFT JOIN tasa_aux ta ON ta.ente = rec.ente
        WHERE f.ejercicio = :ej
          AND f.tipo_cuenta = 'ingreso'
          AND rec.tomador IS NOT NULL
        GROUP BY rec.tomador
    """, ej=ejercicio, tasa=tasa)
    if not rows:
        return 0.0, 0
    # Replicar aritmética exacta de rentabilidad: round por tomador, luego suma
    total = round(sum(round(float(r[1]), 2) for r in rows if r[0]), 2)
    return total, len([r for r in rows if r[0]])


def _calc_cesion_normalizada(db: Session, ejercicio: int, tasa: float) -> tuple[float, float, float, float]:
    """
    Cesión analítica normalizada — usa la MISMA SQL que rentabilidad_cliente._aux_stat
    para garantizar que los totales cuadren exactamente.

    Devuelve (cesion_normalizada, 0, 0, cesion_estimada).
    """
    # Estructura WITH + FILTER idéntica a rentabilidad_cliente para el componente 623*
    direct_row = _q(db, """
        WITH recibos_con_aux AS (
            SELECT r.id
            FROM recibos r
            WHERE r.ente IS NOT NULL
              AND r.id IN (
                  SELECT DISTINCT recibo_id FROM fact_resultado_analitico
                  WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
              )
        )
        SELECT COALESCE(
            SUM(-CAST(f.importe AS FLOAT))
            FILTER (WHERE f.numero_cuenta LIKE '623%%' AND f.recibo_id IN (SELECT id FROM recibos_con_aux)),
            0
        )
        FROM fact_resultado_analitico f
        WHERE f.ejercicio = :ej AND f.recibo_id IS NOT NULL
    """, ej=ejercicio)
    ces_direct = round(float((direct_row or [[0.0]])[0][0] or 0.0), 2)

    ces_est, _ = _cesion_estimada_global(db, ejercicio, tasa)

    ces_norm = round(ces_direct + ces_est, 2)
    return ces_norm, 0.0, 0.0, round(ces_est, 2)


def _cesion_directa_por_dim(db: Session, ejercicio: int, dimension: str) -> dict:
    """
    Cesión 623 directa por dimensión: recibos con auxiliar (ente IS NOT NULL)
    e ingreso en el ejercicio. Mismo criterio que rentabilidad_cliente.
    Devuelve dict {valor_dim: importe} (o {(ramo, subramo): importe} para subramo).
    """
    assert dimension in {'compania', 'ramo', 'subramo', 'auxiliar', 'es_nueva_produccion'}
    if dimension == 'subramo':
        sel = "f.ramo, COALESCE(f.subramo, '(Sin subramo)')"
        grp = "f.ramo, COALESCE(f.subramo, '(Sin subramo)')"
    else:
        sel = grp = f"f.{dimension}"
    rows = db.execute(_text(f"""
        SELECT {sel}, COALESCE(SUM(-CAST(f.importe AS FLOAT)), 0)
        FROM fact_resultado_analitico f
        JOIN recibos r ON r.id = f.recibo_id
        WHERE f.ejercicio = :ej
          AND f.numero_cuenta LIKE '623%%'
          AND r.ente IS NOT NULL
          AND f.recibo_id IN (
              SELECT DISTINCT recibo_id FROM fact_resultado_analitico
              WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND recibo_id IS NOT NULL
          )
        GROUP BY {grp}
    """), {"ej": ejercicio}).fetchall()
    if dimension == 'subramo':
        return {(r[0], r[1]): round(float(r[2]), 2) for r in rows}
    return {r[0]: round(float(r[1]), 2) for r in rows if r[0] is not None}


def _norm(m: dict, ces_directa: float, ces_est: float) -> dict:
    """Añade campos normalizados a un dict de P&L ya calculado con _calc_pl.
    ces_normalizada = cesión 623 directa (recibos con ente+ingreso) + cesión estimada."""
    ces_norm = round(ces_directa + ces_est, 2)
    delta    = m["comision_auxiliar"] - ces_norm
    cn_norm  = round(m["comision_neta"]  + delta, 2)
    eb_norm  = round(m["ebitda"]         + delta, 2)
    bruta    = m["comision_bruta"]
    m["cesion_normalizada"]   = ces_norm
    m["cesion_años_ant"]      = 0.0
    m["comision_neta_norm"]   = cn_norm
    m["ebitda_normalizado"]   = eb_norm
    m["margen_pct_norm"]      = round(eb_norm / bruta * 100, 2) if bruta else 0.0
    return m


def _rescale_norm(items: list[dict], ces_norm_global: float) -> None:
    """
    Ajusta proporcionalmente la cesion_normalizada de cada elemento para que su suma
    coincida con la cesión normalizada global (conciliación).
    Necesario porque _cesion_directa_por_dim excluye filas con dimensión NULL que sí se
    cuentan en el global, lo que puede producir un exceso per-dimensión.
    """
    total_local = sum(c.get("cesion_normalizada", 0.0) for c in items)
    if total_local < 0.01 or abs(total_local - ces_norm_global) < 0.02:
        return
    factor = ces_norm_global / total_local
    for c in items:
        ces_n = round(c.get("cesion_normalizada", 0.0) * factor, 2)
        ces_aux = c.get("comision_auxiliar", 0.0)
        delta = ces_aux - ces_n
        c["cesion_normalizada"] = ces_n
        c["comision_neta_norm"] = round(c.get("comision_neta", 0.0) + delta, 2)
        c["ebitda_normalizado"] = round(c.get("ebitda", 0.0) + delta, 2)
        bruta = c.get("comision_bruta", 0.0)
        c["margen_pct_norm"] = round(c["ebitda_normalizado"] / bruta * 100, 2) if bruta else 0.0


def _add_costes_contable(db, ejercicio: int, items: list[dict]) -> None:
    """Añade costes_op_contable, ebitda_contable y margen_pct_contable a cada entidad."""
    aj_total = round(sum(
        float(aj.importe_mensual) * 12
        for aj in db.query(AnaliticoAjusteCoste).filter(
            AnaliticoAjusteCoste.ejercicio == ejercicio,
            AnaliticoAjusteCoste.activo == True,
        ).all()
    ), 2)
    total_anal = sum(m.get("costes_operativos", 0.0) for m in items)
    for m in items:
        cop = m.get("costes_operativos", 0.0)
        aj_entity = round(cop / total_anal * aj_total if total_anal else 0.0, 2)
        m["costes_op_contable"]  = round(cop + aj_entity, 2)
        ebitda_cont              = round(m.get("ebitda", 0.0) - aj_entity, 2)
        m["ebitda_contable"]     = ebitda_cont
        bruta                    = m.get("comision_bruta", 0.0)
        m["margen_pct_contable"] = round(ebitda_cont / bruta * 100, 2) if bruta else 0.0


def _add_por_poliza(db, ejercicio: int, items: list[dict], campo: str, sin_valor: str) -> None:
    """
    Economía por póliza de cada entidad (vista normalizada): pólizas con ingreso en el
    ejercicio, comisión, neta (tras cesión normalizada), coste y resultado por póliza,
    y la comisión mínima por póliza para no perder dinero con su % de cesión:
        comisión mínima = coste por póliza / (1 − % cesión)
    campo: 'compania' | 'auxiliar' | 'ramo' (columna del fact y clave del item).
    """
    assert campo in {'compania', 'auxiliar', 'ramo'}
    rows = db.execute(_text(f"""
        SELECT f.{campo}, COUNT(DISTINCT COALESCE(r.numero_poliza, r.id::text))
        FROM fact_resultado_analitico f
        JOIN recibos r ON r.id = f.recibo_id
        WHERE f.ejercicio = :ej AND f.tipo_cuenta = 'ingreso'
        GROUP BY f.{campo}
    """), {"ej": ejercicio}).fetchall()
    n_por_valor = {(r[0] or sin_valor): int(r[1]) for r in rows}
    for m in items:
        n = n_por_valor.get(m.get(campo), 0)
        bruta = m.get("comision_bruta", 0.0)
        ces = m.get("cesion_normalizada", m.get("comision_auxiliar", 0.0))
        coste = m.get("costes_operativos", 0.0) + m.get("costes_captacion", 0.0) + m.get("sin_mapear", 0.0)
        pct_ces = ces / bruta if bruta > 0 else 0.0
        coste_pol = coste / n if n else None
        m["n_polizas"]              = n
        m["comision_por_poliza"]    = round(bruta / n, 2) if n else None
        m["neta_por_poliza"]        = round((bruta - ces) / n, 2) if n else None
        m["coste_por_poliza"]       = round(coste_pol, 2) if coste_pol is not None else None
        m["resultado_por_poliza"]   = round(m.get("ebitda_normalizado", 0.0) / n, 2) if n else None
        m["comision_minima_poliza"] = (
            round(coste_pol / (1 - pct_ces), 2) if coste_pol is not None and pct_ces < 1 else None
        )


_PL_SQL = """
    SELECT tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
    FROM fact_resultado_analitico
    WHERE ejercicio = :ej {extra}
    GROUP BY tipo_cuenta, naturaleza
"""


def dashboard_ejecutivo(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    pl_rows = _q(db, _PL_SQL.format(extra=""), ej=ejercicio)
    if not pl_rows:
        return {"sin_datos": True}

    resumen = _calc_pl(pl_rows)

    # Columna contable: del diario, con la MISMA función que la Cuenta de Resultados del
    # presupuesto, para que ambas cuadren al céntimo. El fact no sirve para esto: recorta
    # la cesión de auxiliares cuya cesión supera sus ingresos (_cap_cesion_rows) y arrastra
    # céntimos del reparto por recibo.
    from .cuenta_resultados import pl_contable_ejercicio
    pl_cont = pl_contable_ejercicio(db, ejercicio)
    ces_contable = round(pl_cont["total_cesiones"], 2)
    resumen["comision_bruta"]    = round(pl_cont["total_ingresos"], 2)
    resumen["comision_auxiliar"] = ces_contable
    resumen["comision_neta"]     = round(resumen["comision_bruta"] - ces_contable, 2)
    resumen["ratio_cesion_pct"]  = round(ces_contable / resumen["comision_bruta"] * 100, 2) if resumen["comision_bruta"] else 0.0

    # AjusteCoste: solo reduce el pool 640/642 en el modelo analítico (no crea fila de cesión).
    # costes_op_contable = gasto operativo real del diario (sin cesión; captación y sin
    # mapear van aparte, implícitos en el EBITDA). costes_operativos = vista normalizada,
    # sin el AJ (ese coste ya está en la cesión estimada del auxiliar).
    _aj_total = round(sum(
        float(aj.importe_mensual) * 12
        for aj in db.query(AnaliticoAjusteCoste).filter(
            AnaliticoAjusteCoste.ejercicio == ejercicio,
            AnaliticoAjusteCoste.activo == True,
        ).all()
    ), 2)
    resumen["costes_op_contable"]  = round(
        pl_cont["total_gastos_operativos"] - ces_contable
        - resumen["costes_captacion"] - resumen["sin_mapear"], 2
    )
    resumen["costes_operativos"]   = round(resumen["costes_op_contable"] - _aj_total, 2)
    resumen["ebitda_contable"]     = pl_cont["ebitda"]
    resumen["margen_pct_contable"] = round(resumen["ebitda_contable"] / resumen["comision_bruta"] * 100, 2) if resumen["comision_bruta"] else 0.0
    resumen["ratio_costes_op_pct"]      = round(resumen["costes_op_contable"] / resumen["comision_bruta"] * 100, 2) if resumen["comision_bruta"] else 0.0
    resumen["ratio_costes_op_pct_norm"] = round(resumen["costes_operativos"]  / resumen["comision_bruta"] * 100, 2) if resumen["comision_bruta"] else 0.0

    n_recibos = db.execute(
        _text(f"SELECT COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ})"), {"ej": ejercicio}
    ).scalar() or 0
    resumen["n_recibos"] = n_recibos

    mes_rows = _q(db, """
        SELECT mes, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND mes IS NOT NULL
        GROUP BY mes, tipo_cuenta, naturaleza ORDER BY mes
    """, ej=ejercicio)
    by_mes: dict[int, list] = defaultdict(list)
    for r in mes_rows:
        by_mes[r[0]].append((r[1], r[2], r[3]))
    mensual = [{"mes": mes, **_calc_pl(rows)} for mes, rows in sorted(by_mes.items())]

    r = resumen
    waterfall = [
        {"name": "Comisiones brutas",  "value": r["comision_bruta"],          "acum": r["comision_bruta"]},
        {"name": "Cesiones auxiliares","value": -r["comision_auxiliar"],       "acum": r["comision_neta"]},
        {"name": "Costes operativos",  "value": -r["costes_op_contable"],      "acum": round(r["comision_neta"] - r["costes_op_contable"], 2)},
        {"name": "Costes captación",   "value": -r["costes_captacion"],        "acum": r["ebitda_contable"]},
        {"name": "EBITDA",             "value": r["ebitda_contable"],          "acum": r["ebitda_contable"], "total": True},
    ]

    nat_totals: dict[str, float] = defaultdict(float)
    for row in pl_rows:
        if row[0] == 'gasto' and row[1] and row[1] != NATURALEZA_RESULTADO_FINANCIERO:
            nat_totals[row[1]] += float(row[2])
    total_costes = sum(-v for v in nat_totals.values())
    costes_naturaleza = sorted(
        [{"naturaleza": k, "importe": round(-v, 2),
          "pct": round(-v / total_costes * 100, 1) if total_costes else 0}
         for k, v in nat_totals.items()],
        key=lambda x: -x["importe"],
    )

    # Cesión estimada global: misma regla que todos los dashboards
    ces_est_global, n_sin_cesion = _cesion_estimada_global(db, ejercicio, tasa_cesion_estimada)
    resumen["cesion_estimada"]     = ces_est_global
    resumen["n_sin_cesion"]        = n_sin_cesion
    resumen["tiene_estimada"]      = ces_est_global > 0.01
    resumen["ebitda_estimado"]     = round(resumen["ebitda"] - ces_est_global, 2)
    resumen["margen_pct_estimado"] = (
        round((resumen["ebitda"] - ces_est_global) / resumen["comision_bruta"] * 100, 2)
        if resumen["comision_bruta"] else 0.0
    )

    # Cesión normalizada: 623 de recibos con auxiliar e ingreso en el ejercicio + estimada.
    # Criterio coherente con rentabilidad_cliente (la cesión es del ejercicio si el recibo
    # tiene ingreso en ese ejercicio, independientemente del año de inicio de la póliza).
    ces_norm, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    ces_directa = round(ces_norm - ces_est_global, 2)   # componente 623 real (sin estimada)
    delta = resumen["comision_auxiliar"] - ces_norm   # positivo si contable > normalizada
    cn_norm = round(resumen["comision_neta"] + delta, 2)
    # ebitda_norm derivado de ebitda_contable para ser robusto pre/post recálculo.
    # ebitda_contable + AJ (beneficio analítico) + delta (ajuste de cesión) da el valor
    # normalizado correcto: I − (COP−AJ) − ces_norm − captacion − sin_mapear.
    ebitda_norm = round(resumen["ebitda_contable"] + _aj_total + delta, 2)
    resumen["cesion_normalizada"]       = ces_norm
    resumen["cesion_directa"]           = ces_directa
    resumen["cesion_ajuste_analitico"]  = 0.0
    resumen["cesion_años_anteriores"]   = 0.0
    resumen["comision_neta_norm"]       = cn_norm
    resumen["ebitda_normalizado"]       = ebitda_norm
    resumen["margen_pct_norm"]          = (
        round(ebitda_norm / resumen["comision_bruta"] * 100, 2)
        if resumen["comision_bruta"] else 0.0
    )
    # Total gastos normalizado = líneas visibles en el CdR norm: cesión_norm + costes_op analítico
    # (captación y sin_mapear no aparecen como línea en el CdR, van implícitos en el EBITDA)
    total_gastos_norm = round(ces_norm + resumen["costes_operativos"], 2)
    resumen["total_gastos_norm"] = total_gastos_norm
    resumen["coste_por_recibo"]  = round(total_gastos_norm / n_recibos, 2) if n_recibos else 0.0

    # En costes_naturaleza reemplaza el importe contable de "Cesión auxiliar" por
    # la cesión normalizada, para que el gráfico de familias de costes sea coherente.
    for entry in costes_naturaleza:
        if entry["naturaleza"] == "Cesión auxiliar":
            entry["importe"] = ces_norm
            if total_costes > 0:
                entry["pct"] = round(ces_norm / total_costes * 100, 1)

    # Desglose canal directo vs intermediado (con auxiliar)
    # Usa f.auxiliar (campo de fact) para no mezclar con filas sin recibo_id:
    #   - auxiliar IS NOT NULL → ingreso atribuido a un auxiliar (recibo con ente, o ajuste con auxiliar)
    #   - auxiliar IS NULL     → ingreso de negocio directo (sin intermediario)
    # Solo se cuentan recibos con fila de ingreso para el denominador.
    split_rows = _q(db, """
        SELECT
            (auxiliar IS NOT NULL)                          AS tiene_auxiliar,
            COALESCE(SUM(CAST(importe AS FLOAT)), 0)        AS ingresos,
            COUNT(DISTINCT recibo_id) FILTER (WHERE recibo_id IS NOT NULL) AS n_recibos
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso'
        GROUP BY (auxiliar IS NOT NULL)
    """, ej=ejercicio)

    ing_con_aux   = 0.0
    ing_sin_aux   = 0.0
    rec_con_aux   = 0
    rec_sin_aux   = 0
    for sr in split_rows:
        if sr[0]:
            ing_con_aux = float(sr[1]);  rec_con_aux = int(sr[2])
        else:
            ing_sin_aux = float(sr[1]);  rec_sin_aux = int(sr[2])

    total_ing_split  = ing_con_aux + ing_sin_aux
    total_rec_canal  = rec_con_aux + rec_sin_aux
    pct_directo  = round(ing_sin_aux / total_ing_split * 100, 1) if total_ing_split else 0.0
    pct_auxiliar = round(ing_con_aux / total_ing_split * 100, 1) if total_ing_split else 0.0

    resumen["ing_con_auxiliar"]  = round(ing_con_aux, 2)
    resumen["ing_sin_auxiliar"]  = round(ing_sin_aux, 2)
    resumen["rec_con_auxiliar"]  = rec_con_aux
    resumen["rec_sin_auxiliar"]  = rec_sin_aux
    resumen["n_recibos_canal"]   = total_rec_canal   # recibos con ingreso (≠ n_recibos total)
    resumen["pct_con_auxiliar"]  = pct_auxiliar
    resumen["pct_sin_auxiliar"]  = pct_directo

    # Cesión sobre el negocio que paga cesión (intermediado). Separa el "precio" del
    # auxiliar del peso del canal: ratio de cesión = % intermediado × esta tasa.
    from .tasa_cesion import detalle_tasa_cesion_real
    resumen["tasa_cesion_aplicada_pct"]   = round(tasa_cesion_estimada * 100, 2)
    resumen["tasa_cesion_real"]           = detalle_tasa_cesion_real(db, ejercicio)
    resumen["cesion_s_intermediado_pct"]  = (
        round(ces_norm / ing_con_aux * 100, 2) if ing_con_aux else 0.0
    )

    return {"resumen": resumen, "mensual": mensual, "waterfall": waterfall, "costes_naturaleza": costes_naturaleza}


def dashboard_compania(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    comp_rows = _q(db, """
        SELECT compania, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico WHERE ejercicio = :ej
        GROUP BY compania, tipo_cuenta, naturaleza
    """, ej=ejercicio)
    if not comp_rows:
        return {"sin_datos": True}

    rec_rows = _q(db, f"SELECT compania, COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ}) GROUP BY compania", ej=ejercicio)
    # Normaliza el nombre de la compañía para que coincida con los nombres ya normalizados
    # en fact_resultado_analitico — sin esto, "CATALANA" no suma en "OCCIDENT".
    rec_counts: dict[str, int] = defaultdict(int)
    for r in rec_rows:
        key = _norm_compania(r[0]) or "(Sin compañía)"
        rec_counts[key] += int(r[1])

    by_comp: dict[str, list] = defaultdict(list)
    for r in comp_rows:
        by_comp[r[0] or "(Sin compañía)"].append((r[1], r[2], r[3]))

    # Redistribuir todo lo que cae en "(Sin compañía)" — cesiones (+ o −),
    # ingresos y costes — por peso de comisión neta o ingresos brutos.
    # "(Sin compañía)" no debe aparecer en el resultado final.
    sin_cia_all = list(by_comp.pop("(Sin compañía)", []))

    if sin_cia_all and by_comp:
        cn_weights: dict[str, float] = {}
        for comp, rows in by_comp.items():
            pl = _calc_pl(rows)
            if pl['comision_neta'] > 0:
                cn_weights[comp] = pl['comision_neta']
        total_cn = sum(cn_weights.values())

        ing_weights: dict[str, float] = {}
        for comp, rows in by_comp.items():
            pl = _calc_pl(rows)
            if pl['comision_bruta'] > 0:
                ing_weights[comp] = pl['comision_bruta']
        total_ing = sum(ing_weights.values())

        for tipo, nat, val in sin_cia_all:
            if nat == 'Cesión auxiliar' and total_cn > 0:
                for comp, cn in cn_weights.items():
                    by_comp[comp].append((tipo, nat, round(val * cn / total_cn, 4)))
            elif total_ing > 0:
                for comp, ing in ing_weights.items():
                    by_comp[comp].append((tipo, nat, round(val * ing / total_ing, 4)))

    # Cesión estimada por compañía: recibos con auxiliar pero sin pago 623* directo
    ces_est_cia = _cesion_estimada_por_dim(db, ejercicio, 'compania', tasa_cesion_estimada)
    ces_dir_cia = _cesion_directa_por_dim(db, ejercicio, 'compania')

    companias = []
    for comp, rows in by_comp.items():
        m = _calc_pl(rows)
        m["compania"] = comp
        m["n_recibos"] = rec_counts.get(comp, 0)
        ces_est = ces_est_cia.get(comp, 0.0)
        m["cesion_estimada"]     = ces_est
        m["tiene_estimada"]      = ces_est > 0.01
        m["ebitda_estimado"]     = round(m["ebitda"] - ces_est, 2)
        m["margen_pct_estimado"] = (
            round((m["ebitda"] - ces_est) / m["comision_bruta"] * 100, 2)
            if m["comision_bruta"] else 0.0
        )
        _norm(m, ces_dir_cia.get(comp, 0.0), ces_est)
        companias.append(m)
    companias.sort(key=lambda x: -x["ebitda"])

    ces_norm_g, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    _rescale_norm(companias, ces_norm_g)
    _add_costes_contable(db, ejercicio, companias)
    _add_por_poliza(db, ejercicio, companias, "compania", "(Sin compañía)")

    top5 = [c["compania"] for c in sorted(companias, key=lambda x: -x["comision_bruta"])[:5]]

    mes_comp_rows = _q(db, """
        SELECT mes, compania, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND mes IS NOT NULL
        GROUP BY mes, compania ORDER BY mes
    """, ej=ejercicio)
    by_mes_comp: dict[int, dict] = defaultdict(dict)
    meses_set: set[int] = set()
    for r in mes_comp_rows:
        comp = r[1] or "(Sin compañía)"
        if comp in top5:
            by_mes_comp[r[0]][comp] = round(float(r[2]), 2)
        meses_set.add(r[0])

    mensual = [
        {"mes": mes, **{comp: by_mes_comp[mes].get(comp, 0) for comp in top5}}
        for mes in sorted(meses_set)
    ]
    return {"companias": companias, "mensual": mensual, "top5": top5}


def dashboard_auxiliar(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    aux_rows = _q(db, """
        SELECT auxiliar, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico WHERE ejercicio = :ej
        GROUP BY auxiliar, tipo_cuenta, naturaleza
    """, ej=ejercicio)
    if not aux_rows:
        return {"sin_datos": True}

    rec_rows = _q(db, f"SELECT ente, COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ}) GROUP BY ente", ej=ejercicio)
    rec_counts = {(r[0] or "(Sin auxiliar)"): int(r[1]) for r in rec_rows}

    by_aux: dict[str, list] = defaultdict(list)
    for r in aux_rows:
        by_aux[r[0] or "(Sin auxiliar)"].append((r[1], r[2], r[3]))

    ces_est_aux = _cesion_estimada_por_dim(db, ejercicio, 'auxiliar', tasa_cesion_estimada)
    ces_dir_aux = _cesion_directa_por_dim(db, ejercicio, 'auxiliar')
    auxiliares = []
    for aux, rows in by_aux.items():
        m = _calc_pl(rows)
        m["auxiliar"] = aux
        n = rec_counts.get(aux, 0)
        m["n_recibos"] = n
        m["comision_media_recibo"] = round(m["comision_bruta"] / n, 2) if n else 0.0
        ces_est = ces_est_aux.get(aux, 0.0)
        m["cesion_estimada"]     = ces_est
        m["tiene_estimada"]      = ces_est > 0.01
        m["ebitda_estimado"]     = round(m["ebitda"] - ces_est, 2)
        m["margen_pct_estimado"] = (
            round((m["ebitda"] - ces_est) / m["comision_bruta"] * 100, 2)
            if m["comision_bruta"] else 0.0
        )
        _norm(m, ces_dir_aux.get(aux, 0.0), ces_est)
        auxiliares.append(m)
    auxiliares.sort(key=lambda x: -x["ebitda"])

    ces_norm_g, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    _rescale_norm(auxiliares, ces_norm_g)
    _add_costes_contable(db, ejercicio, auxiliares)
    _add_por_poliza(db, ejercicio, auxiliares, "auxiliar", "(Sin auxiliar)")

    top5 = [a["auxiliar"] for a in sorted(auxiliares, key=lambda x: -x["comision_bruta"])[:5]]

    mes_aux_rows = _q(db, """
        SELECT mes, auxiliar, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND mes IS NOT NULL
        GROUP BY mes, auxiliar ORDER BY mes
    """, ej=ejercicio)
    by_mes_aux: dict[int, dict] = defaultdict(dict)
    meses_set: set[int] = set()
    for r in mes_aux_rows:
        aux = r[1] or "(Sin auxiliar)"
        if aux in top5:
            by_mes_aux[r[0]][aux] = round(float(r[2]), 2)
        meses_set.add(r[0])

    mensual = [
        {"mes": mes, **{aux: by_mes_aux[mes].get(aux, 0) for aux in top5}}
        for mes in sorted(meses_set)
    ]
    return {"auxiliares": auxiliares, "mensual": mensual, "top5": top5}


def dashboard_ramo(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    ramo_rows = _q(db, """
        SELECT ramo, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico WHERE ejercicio = :ej
        GROUP BY ramo, tipo_cuenta, naturaleza
    """, ej=ejercicio)
    if not ramo_rows:
        return {"sin_datos": True}

    rec_rows = _q(db, f"SELECT ramo, COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ}) GROUP BY ramo", ej=ejercicio)
    rec_counts = {(r[0] or "(Sin ramo)"): int(r[1]) for r in rec_rows}

    by_ramo: dict[str, list] = defaultdict(list)
    for r in ramo_rows:
        by_ramo[r[0] or "(Sin ramo)"].append((r[1], r[2], r[3]))

    # Eliminar completamente "(Sin ramo)" del desglose:
    # - Cesiones (positivas o negativas): redistribuir por comisión neta de ramos conocidos.
    # - Ingresos y costes indirectos sin ramo: redistribuir por peso de ingresos conocidos.
    # - "(Sin ramo)" no vuelve a aparecer en ningún caso.
    sin_ramo_all = list(by_ramo.pop("(Sin ramo)", []))

    if sin_ramo_all and by_ramo:
        # Peso por comisión neta (para cesiones)
        cn_weights: dict[str, float] = {}
        for ramo_k, rows in by_ramo.items():
            pl = _calc_pl(rows)
            if pl['comision_neta'] > 0:
                cn_weights[ramo_k] = pl['comision_neta']
        total_cn = sum(cn_weights.values())

        # Peso por ingresos brutos (para ingresos y costes indirectos)
        ing_weights: dict[str, float] = {}
        for ramo_k, rows in by_ramo.items():
            pl = _calc_pl(rows)
            if pl['comision_bruta'] > 0:
                ing_weights[ramo_k] = pl['comision_bruta']
        total_ing = sum(ing_weights.values())

        for tipo, nat, val in sin_ramo_all:
            if nat == 'Cesión auxiliar' and total_cn > 0:
                # Cesiones → repartir por comisión neta
                for ramo_k, cn in cn_weights.items():
                    by_ramo[ramo_k].append((tipo, nat, round(val * cn / total_cn, 4)))
            elif total_ing > 0:
                # Ingresos y resto de costes → repartir por ingresos brutos
                for ramo_k, ing in ing_weights.items():
                    by_ramo[ramo_k].append((tipo, nat, round(val * ing / total_ing, 4)))
            # Si no hay pesos disponibles, el apunte se descarta (no vuelve a sin_ramo)

    # Cesión estimada por ramo: recibos con auxiliar pero sin pago 623* directo
    ces_est_ramo = _cesion_estimada_por_dim(db, ejercicio, 'ramo', tasa_cesion_estimada)
    ces_dir_ramo = _cesion_directa_por_dim(db, ejercicio, 'ramo')

    ramos = []
    for ramo, rows in by_ramo.items():
        m = _calc_pl(rows)
        m["ramo"] = ramo
        m["n_recibos"] = rec_counts.get(ramo, 0)
        ces_est = ces_est_ramo.get(ramo, 0.0)
        m["cesion_estimada"]     = ces_est
        m["tiene_estimada"]      = ces_est > 0.01
        m["ebitda_estimado"]     = round(m["ebitda"] - ces_est, 2)
        m["margen_pct_estimado"] = (
            round((m["ebitda"] - ces_est) / m["comision_bruta"] * 100, 2)
            if m["comision_bruta"] else 0.0
        )
        _norm(m, ces_dir_ramo.get(ramo, 0.0), ces_est)
        ramos.append(m)
    ramos.sort(key=lambda x: -x["comision_bruta"])

    ces_norm_g, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    _rescale_norm(ramos, ces_norm_g)
    _add_costes_contable(db, ejercicio, ramos)
    _add_por_poliza(db, ejercicio, ramos, "ramo", "(Sin ramo)")

    heatmap_rows = _q(db, """
        SELECT compania, ramo, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso'
        AND compania IS NOT NULL AND ramo IS NOT NULL
        GROUP BY compania, ramo
    """, ej=ejercicio)
    heatmap = [{"compania": r[0], "ramo": r[1], "importe": round(float(r[2]), 2)} for r in heatmap_rows]

    return {"ramos": ramos, "heatmap": heatmap}


def dashboard_subramo(db: Session, ejercicio: int, ramo: str | None = None, tasa_cesion_estimada: float | None = None) -> dict:
    """
    Desglose por subramo. Si se pasa ramo, filtra solo ese ramo (ej: 'Multirriesgos').
    Sin filtro devuelve todos los subramos con su ramo padre.
    """
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    extra_filter = "AND ramo = :ramo" if ramo else ""
    params = {"ej": ejercicio, **({"ramo": ramo} if ramo else {})}

    rows = db.execute(_text(f"""
        SELECT
            ramo,
            COALESCE(subramo, '(Sin subramo)') AS subramo,
            tipo_cuenta, naturaleza,
            COALESCE(SUM(CAST(importe AS FLOAT)), 0) AS total
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND ramo IS NOT NULL {extra_filter}
        GROUP BY ramo, subramo, tipo_cuenta, naturaleza
        ORDER BY ramo, subramo
    """), params).fetchall()

    if not rows:
        return {"sin_datos": True}

    rec_rows = db.execute(_text(f"""
        SELECT ramo, subramo, COUNT(*) AS n
        FROM recibos
        WHERE id IN ({_REC_EN_EJ}) AND ramo IS NOT NULL
        {('AND ramo = :ramo' if ramo else '')}
        GROUP BY ramo, subramo
    """), params).fetchall()

    rec_counts: dict[tuple, int] = defaultdict(int)
    for r in rec_rows:
        rec_counts[(r[0], r[1] or '(Sin subramo)')] += int(r[2])

    by_subramo: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = (r[0], r[1])  # (ramo, subramo)
        by_subramo[key].append((r[2], r[3], r[4]))

    # Cesión estimada por subramo: recibos con auxiliar pero sin pago 623* directo
    ces_est_sub = _cesion_estimada_por_dim(
        db, ejercicio, 'subramo', tasa_cesion_estimada, ramo_filtro=ramo
    )
    ces_dir_sub = _cesion_directa_por_dim(db, ejercicio, 'subramo')

    result = []
    for (ramo_val, subramo_val), pl_rows in by_subramo.items():
        m = _calc_pl(pl_rows)
        m["ramo"] = ramo_val
        m["subramo"] = subramo_val
        m["n_recibos"] = rec_counts.get((ramo_val, subramo_val), 0)
        m["ingreso_por_recibo"] = round(m["comision_bruta"] / m["n_recibos"], 2) if m["n_recibos"] else 0
        ces_est = ces_est_sub.get((ramo_val, subramo_val), 0.0)
        m["cesion_estimada"]     = ces_est
        m["tiene_estimada"]      = ces_est > 0.01
        m["ebitda_estimado"]     = round(m["ebitda"] - ces_est, 2)
        m["margen_pct_estimado"] = (
            round((m["ebitda"] - ces_est) / m["comision_bruta"] * 100, 2)
            if m["comision_bruta"] else 0.0
        )
        _norm(m, ces_dir_sub.get((ramo_val, subramo_val), 0.0), ces_est)
        result.append(m)
    result.sort(key=lambda x: -x["comision_bruta"])
    _add_costes_contable(db, ejercicio, result)
    if ramo is None:
        # Todos los ramos: reescalar cesión normalizada al global (igual que D2/D3/D4)
        ces_norm_sub_global, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
        _rescale_norm(result, ces_norm_sub_global)

        # Totales D1 para la fila resumen: incluye filas con ramo=NULL que la query
        # anterior excluye (costes indirectos sin driver de reparto asignado).
        _d1_pl_rows = db.execute(_text("""
            SELECT tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
            FROM fact_resultado_analitico WHERE ejercicio = :ej
            GROUP BY tipo_cuenta, naturaleza
        """), {"ej": ejercicio}).fetchall()
        _d1_pl = _calc_pl([(r[0], r[1], r[2]) for r in _d1_pl_rows])

        _ces_cont_row = db.execute(_text("""
            SELECT COALESCE(SUM(-CAST(importe AS FLOAT)) FILTER (WHERE numero_cuenta LIKE '623%%'), 0)
            FROM fact_resultado_analitico WHERE ejercicio = :ej
        """), {"ej": ejercicio}).fetchone()
        _ces_cont_g = round(float(_ces_cont_row[0] or 0.0), 2)

        _aj_g = round(sum(
            float(aj.importe_mensual) * 12
            for aj in db.query(AnaliticoAjusteCoste).filter(
                AnaliticoAjusteCoste.ejercicio == ejercicio,
                AnaliticoAjusteCoste.activo == True,
            ).all()
        ), 2)

        _bruta_g     = _d1_pl["comision_bruta"]
        _cop_cont_g  = round(_d1_pl["costes_operativos"] + _aj_g, 2)
        _ebitda_cont_g = round(
            _bruta_g - _ces_cont_g - _cop_cont_g
            - _d1_pl["costes_captacion"] - _d1_pl["sin_mapear"], 2
        )
        # ebitda_norm = ebitda_cont + AJ + (ces_cont − ces_norm)  [misma fórmula que D1]
        _delta_g     = _ces_cont_g - ces_norm_sub_global
        _ebitda_norm_g = round(_ebitda_cont_g + _aj_g + _delta_g, 2)

        totales = {
            "comision_bruta":      _bruta_g,
            "comision_auxiliar":   _ces_cont_g,
            "costes_op_contable":  _cop_cont_g,
            "ebitda_contable":     _ebitda_cont_g,
            "margen_pct_contable": round(_ebitda_cont_g / _bruta_g * 100, 2) if _bruta_g else 0.0,
            "cesion_normalizada":  ces_norm_sub_global,
            "ebitda_normalizado":  _ebitda_norm_g,
            "margen_pct_norm":     round(_ebitda_norm_g / _bruta_g * 100, 2) if _bruta_g else 0.0,
        }
        return {"subramos": result, "ramo_filtro": ramo, "totales": totales}

    return {"subramos": result, "ramo_filtro": ramo}


def dashboard_nueva_produccion(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    np_rows = _q(db, """
        SELECT es_nueva_produccion, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico WHERE ejercicio = :ej
        GROUP BY es_nueva_produccion, tipo_cuenta, naturaleza
    """, ej=ejercicio)
    if not np_rows:
        return {"sin_datos": True}

    np_pl  = _calc_pl([(r[1], r[2], r[3]) for r in np_rows if r[0]])
    cart_pl = _calc_pl([(r[1], r[2], r[3]) for r in np_rows if not r[0]])
    total_pl = _calc_pl([(r[1], r[2], r[3]) for r in np_rows])

    coste_captacion = total_pl["costes_captacion"]
    payback = None
    if np_pl["ebitda"] > 0 and coste_captacion > 0:
        payback = round(coste_captacion / np_pl["ebitda"], 2)

    mes_rows = _q(db, """
        SELECT mes, es_nueva_produccion, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'ingreso' AND mes IS NOT NULL
        GROUP BY mes, es_nueva_produccion ORDER BY mes
    """, ej=ejercicio)
    by_mes: dict[int, dict] = defaultdict(lambda: {"np": 0.0, "cart": 0.0})
    for r in mes_rows:
        if r[1]:
            by_mes[r[0]]["np"] = round(float(r[2]), 2)
        else:
            by_mes[r[0]]["cart"] = round(float(r[2]), 2)

    mensual = [
        {"mes": mes, "nueva_produccion": v["np"], "cartera": v["cart"]}
        for mes, v in sorted(by_mes.items())
    ]
    # Cesión estimada por segmento: misma regla SQL — recibo con auxiliar sin 623* directo
    np_ces_map: dict[bool, float] = {}
    _np_rows = _q(db, _CES_EST_CTE + f"""
        SELECT f.es_nueva_produccion, COALESCE(SUM(CAST(f.importe AS FLOAT) * {TASA_EXPR}), 0)
        FROM fact_resultado_analitico f
        JOIN recibos_sin_cesion_directa rsc ON f.recibo_id = rsc.recibo_id
        JOIN recibos rec ON rec.id = f.recibo_id
        LEFT JOIN tasa_aux ta ON ta.ente = rec.ente
        WHERE f.ejercicio = :ej AND f.tipo_cuenta = 'ingreso'
        GROUP BY f.es_nueva_produccion
    """, ej=ejercicio, tasa=tasa_cesion_estimada)
    np_ces_map = {bool(r[0]): round(float(r[1]), 2) for r in _np_rows}

    ces_dir_np = _cesion_directa_por_dim(db, ejercicio, 'es_nueva_produccion')

    def _apply_ces(pl: dict, key: bool) -> None:
        ces = np_ces_map.get(key, 0.0)
        pl["cesion_estimada"]     = ces
        pl["tiene_estimada"]      = ces > 0.01
        pl["ebitda_estimado"]     = round(pl["ebitda"] - ces, 2)
        pl["margen_pct_estimado"] = (
            round((pl["ebitda"] - ces) / pl["comision_bruta"] * 100, 2)
            if pl["comision_bruta"] else 0.0
        )
        _norm(pl, ces_dir_np.get(key, 0.0), ces)

    _apply_ces(np_pl,   True)
    _apply_ces(cart_pl, False)
    total_ces = sum(np_ces_map.values())
    total_ces_dir = sum(ces_dir_np.values())
    _apply_ces_total = lambda pl: (pl.update({
        "cesion_estimada":     total_ces,
        "tiene_estimada":      total_ces > 0.01,
        "ebitda_estimado":     round(pl["ebitda"] - total_ces, 2),
        "margen_pct_estimado": round((pl["ebitda"] - total_ces) / pl["comision_bruta"] * 100, 2)
                                if pl["comision_bruta"] else 0.0,
    }) or _norm(pl, total_ces_dir, total_ces))
    _apply_ces_total(total_pl)
    # Normalizado: reescalar NP y Cartera al global para que cuadren con D1
    ces_norm_global_d5, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    _rescale_norm([np_pl, cart_pl], ces_norm_global_d5)
    _bruta_tot = total_pl.get("comision_bruta", 0.0)
    total_pl["cesion_normalizada"] = round(np_pl["cesion_normalizada"] + cart_pl["cesion_normalizada"], 2)
    total_pl["comision_neta_norm"] = round(np_pl["comision_neta_norm"] + cart_pl["comision_neta_norm"], 2)
    total_pl["ebitda_normalizado"] = round(np_pl["ebitda_normalizado"] + cart_pl["ebitda_normalizado"], 2)
    total_pl["margen_pct_norm"]    = round(total_pl["ebitda_normalizado"] / _bruta_tot * 100, 2) if _bruta_tot else 0.0
    # Contable: distribuir AJ solo entre NP y Cartera (no incluir total para no duplicar denominador)
    _add_costes_contable(db, ejercicio, [np_pl, cart_pl])
    total_pl["costes_op_contable"]  = round(np_pl["costes_op_contable"] + cart_pl["costes_op_contable"], 2)
    total_pl["ebitda_contable"]     = round(np_pl["ebitda_contable"]    + cart_pl["ebitda_contable"],    2)
    total_pl["margen_pct_contable"] = round(total_pl["ebitda_contable"] / _bruta_tot * 100, 2) if _bruta_tot else 0.0

    return {
        "nueva_produccion": np_pl, "cartera": cart_pl, "total": total_pl,
        "coste_captacion": coste_captacion, "payback": payback, "mensual": mensual,
    }


def dashboard_operaciones(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    pl_rows = _q(db, _PL_SQL.format(extra=""), ej=ejercicio)
    if not pl_rows:
        return {"sin_datos": True}

    total_pl = _calc_pl(pl_rows)
    n_recibos = db.execute(
        _text(f"SELECT COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ})"), {"ej": ejercicio}
    ).scalar() or 0

    _aj_total_d6 = round(sum(
        float(aj.importe_mensual) * 12
        for aj in db.query(AnaliticoAjusteCoste).filter(
            AnaliticoAjusteCoste.ejercicio == ejercicio,
            AnaliticoAjusteCoste.activo == True,
        ).all()
    ), 2)
    costes_op_contable_d6  = round(total_pl["costes_operativos"] + _aj_total_d6, 2)
    ebitda_contable_d6     = round(total_pl["ebitda"] - _aj_total_d6, 2)
    _bruta_d6              = total_pl["comision_bruta"]
    margen_pct_contable_d6 = round(ebitda_contable_d6 / _bruta_d6 * 100, 2) if _bruta_d6 else 0.0
    total_costes_op        = total_pl["comision_auxiliar"] + costes_op_contable_d6 + total_pl["costes_captacion"] + total_pl.get("sin_mapear", 0.0)
    coste_unitario         = round(total_costes_op / n_recibos, 2) if n_recibos else 0.0
    margen_unitario        = round(ebitda_contable_d6 / n_recibos, 2) if n_recibos else 0.0
    comision_media         = round(_bruta_d6 / n_recibos, 2) if n_recibos else 0.0

    aux_rows = _q(db, """
        SELECT auxiliar, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico WHERE ejercicio = :ej
        GROUP BY auxiliar, tipo_cuenta, naturaleza
    """, ej=ejercicio)
    rec_aux_rows = _q(db, f"SELECT ente, COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ}) GROUP BY ente", ej=ejercicio)
    rec_aux_counts = {(r[0] or "(Sin auxiliar)"): int(r[1]) for r in rec_aux_rows}

    by_aux: dict[str, list] = defaultdict(list)
    for r in aux_rows:
        by_aux[r[0] or "(Sin auxiliar)"].append((r[1], r[2], r[3]))

    ces_est_op  = _cesion_estimada_por_dim(db, ejercicio, 'auxiliar', tasa_cesion_estimada)
    ces_dir_op  = _cesion_directa_por_dim(db, ejercicio, 'auxiliar')
    aux_eficiencia = []
    for aux, rows in by_aux.items():
        m = _calc_pl(rows)
        n = rec_aux_counts.get(aux, 0)
        costes_total = m["comision_auxiliar"] + m["costes_operativos"] + m["costes_captacion"] + m.get("sin_mapear", 0.0)
        ces_est = ces_est_op.get(aux, 0.0)
        ces_dir = ces_dir_op.get(aux, 0.0)
        ces_norm_aux = round(ces_dir + ces_est, 2)
        eb_norm_aux  = round(m["ebitda"] + m["comision_auxiliar"] - ces_norm_aux, 2)
        aux_eficiencia.append({
            "auxiliar":             aux,
            "n_recibos":            n,
            "comision_bruta":       m["comision_bruta"],
            "comision_auxiliar":    m["comision_auxiliar"],
            "comision_neta":        m["comision_neta"],
            "costes_operativos":    m["costes_operativos"],
            "ebitda":               m["ebitda"],
            "margen_pct":           m["margen_pct"],
            "comision_media":       round(m["comision_bruta"] / n, 2) if n else 0,
            "coste_por_recibo":     round(costes_total / n, 2) if n else 0,
            "margen_por_recibo":    round(m["ebitda"] / n, 2) if n else 0,
            "cesion_estimada":      ces_est,
            "tiene_estimada":       ces_est > 0.01,
            "ebitda_estimado":      round(m["ebitda"] - ces_est, 2),
            "margen_pct_estimado":  (
                round((m["ebitda"] - ces_est) / m["comision_bruta"] * 100, 2)
                if m["comision_bruta"] else 0.0
            ),
            "cesion_normalizada":   ces_norm_aux,
            "cesion_años_ant":      0.0,
            "comision_neta_norm":   round(m["comision_neta"] + m["comision_auxiliar"] - ces_norm_aux, 2),
            "ebitda_normalizado":   eb_norm_aux,
            "margen_pct_norm":      round(eb_norm_aux / m["comision_bruta"] * 100, 2) if m["comision_bruta"] else 0.0,
        })
    aux_eficiencia.sort(key=lambda x: -x["margen_pct"])
    _add_costes_contable(db, ejercicio, aux_eficiencia)

    mes_pl_rows = _q(db, """
        SELECT mes, tipo_cuenta, naturaleza, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico WHERE ejercicio = :ej AND mes IS NOT NULL
        GROUP BY mes, tipo_cuenta, naturaleza ORDER BY mes
    """, ej=ejercicio)
    rec_mes_rows = _q(db, f"""
        SELECT EXTRACT(MONTH FROM desde)::int, COUNT(*)
        FROM recibos WHERE id IN ({_REC_EN_EJ}) AND desde IS NOT NULL GROUP BY 1
    """, ej=ejercicio)
    rec_by_mes = {int(r[0]): int(r[1]) for r in rec_mes_rows}

    by_mes_pl: dict[int, list] = defaultdict(list)
    for r in mes_pl_rows:
        by_mes_pl[r[0]].append((r[1], r[2], r[3]))

    mensual_costes = []
    for mes in sorted(by_mes_pl):
        m = _calc_pl(by_mes_pl[mes])
        n_m = rec_by_mes.get(mes, 0) or 1
        mensual_costes.append({
            "mes": mes,
            "coste_por_recibo":  round((m["comision_auxiliar"] + m["costes_operativos"] + m["costes_captacion"] + m.get("sin_mapear", 0.0)) / n_m, 2),
            "margen_por_recibo": round(m["ebitda"] / n_m, 2),
        })

    op_ces_global, _ = _cesion_estimada_global(db, ejercicio, tasa_cesion_estimada)
    op_ebitda_est = round(total_pl["ebitda"] - op_ces_global, 2)
    op_ces_norm, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    op_delta_norm  = total_pl["comision_auxiliar"] - op_ces_norm
    op_ebitda_norm = round(total_pl["ebitda"] + op_delta_norm, 2)
    _rescale_norm(aux_eficiencia, op_ces_norm)
    return {
        "resumen": {
            "n_recibos": n_recibos, "coste_unitario": coste_unitario,
            "margen_unitario": margen_unitario, "comision_media": comision_media,
            "comision_bruta": total_pl["comision_bruta"],
            "total_costes": total_costes_op,
            "costes_op_contable":  costes_op_contable_d6,
            "ebitda": total_pl["ebitda"], "margen_pct": total_pl["margen_pct"],
            "ebitda_contable":     ebitda_contable_d6,
            "margen_pct_contable": margen_pct_contable_d6,
            "cesion_estimada":     op_ces_global,
            "tiene_estimada":      op_ces_global > 0.01,
            "ebitda_estimado":     op_ebitda_est,
            "margen_pct_estimado": (
                round(op_ebitda_est / total_pl["comision_bruta"] * 100, 2)
                if total_pl["comision_bruta"] else 0.0
            ),
            "cesion_normalizada":       op_ces_norm,
            "cesion_ajuste_analitico":  0.0,
            "cesion_años_ant":          0.0,
            "ebitda_normalizado":       op_ebitda_norm,
            "margen_pct_norm":          (
                round(op_ebitda_norm / total_pl["comision_bruta"] * 100, 2)
                if total_pl["comision_bruta"] else 0.0
            ),
        },
        "auxiliares": aux_eficiencia,
        "mensual": mensual_costes,
    }


def dashboard_costes(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    pl_rows = _q(db, _PL_SQL.format(extra=""), ej=ejercicio)
    if not pl_rows:
        return {"sin_datos": True}

    total_pl = _calc_pl(pl_rows)

    nat_imp_rows = _q(db, """
        SELECT naturaleza, tipo_imputacion, COALESCE(SUM(CAST(importe AS FLOAT)),0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej AND tipo_cuenta = 'gasto' AND naturaleza IS NOT NULL
          AND naturaleza <> :nat_fin
        GROUP BY naturaleza, tipo_imputacion
    """, ej=ejercicio, nat_fin=NATURALEZA_RESULTADO_FINANCIERO)

    nat_data: dict[str, dict] = defaultdict(lambda: {"importe": 0.0, "directa": 0.0, "indirecta": 0.0})
    for r in nat_imp_rows:
        nat, tipo_imp, v = r[0], r[1], float(r[2])
        nat_data[nat]["importe"] += v
        if tipo_imp == 'DIRECTA':
            nat_data[nat]["directa"] += v
        else:
            nat_data[nat]["indirecta"] += v

    total_costes = sum(-d["importe"] for d in nat_data.values())
    comision_bruta = total_pl["comision_bruta"]
    costes_detalle = sorted(
        [{
            "naturaleza":  nat,
            "importe":     round(-d["importe"],   2),
            "directa":     round(-d["directa"],   2),
            "indirecta":   round(-d["indirecta"], 2),
            "pct":         round(-d["importe"] / total_costes   * 100, 1) if total_costes   else 0,
            "pct_ingreso": round(-d["importe"] / comision_bruta * 100, 1) if comision_bruta else 0,
        } for nat, d in nat_data.items()],
        key=lambda x: -x["importe"],
    )

    ces_est_costes, n_sin_ces_costes = _cesion_estimada_global(db, ejercicio, tasa_cesion_estimada)
    ebitda_estimado_costes = round(total_pl["ebitda"] - ces_est_costes, 2)
    cos_ces_norm, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
    cos_delta_norm  = total_pl["comision_auxiliar"] - cos_ces_norm
    cos_ebitda_norm = round(total_pl["ebitda"] + cos_delta_norm, 2)

    n_recibos_costes = db.execute(
        _text(f"SELECT COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ})"), {"ej": ejercicio}
    ).scalar() or 0
    _aj_total_d7 = round(sum(
        float(aj.importe_mensual) * 12
        for aj in db.query(AnaliticoAjusteCoste).filter(
            AnaliticoAjusteCoste.ejercicio == ejercicio,
            AnaliticoAjusteCoste.activo == True,
        ).all()
    ), 2)
    sin_mapear = round(total_pl.get("sin_mapear", 0.0), 2)
    costes_op_contable_d7 = round(total_pl["costes_operativos"] + _aj_total_d7, 2)
    total_costes_all  = round(total_pl["comision_auxiliar"] + costes_op_contable_d7 + total_pl["costes_captacion"] + sin_mapear, 2)
    # Normalizado: ces_norm + cop_anal (igual que D1 total_gastos_norm, SIN captación ni sin_mapear)
    total_costes_norm = round(cos_ces_norm + total_pl["costes_operativos"], 2)
    coste_por_recibo      = round(total_costes_all  / n_recibos_costes, 2) if n_recibos_costes else 0.0
    coste_por_recibo_norm = round(total_costes_norm / n_recibos_costes, 2) if n_recibos_costes else 0.0

    # Detectar la naturaleza de cesión (623*) para ajustar el detalle normalizado
    _ces_nat_row = db.execute(_text(
        "SELECT naturaleza FROM analitico_map_cuentas WHERE numero_cuenta LIKE '623%' LIMIT 1"
    )).fetchone()
    _ces_nat = _ces_nat_row[0] if _ces_nat_row else "Cesión auxiliar"
    for item in costes_detalle:
        item["importe_norm"]     = cos_ces_norm if item["naturaleza"] == _ces_nat else item["importe"]
        item["pct_ingreso_norm"] = round(item["importe_norm"] / comision_bruta * 100, 1) if comision_bruta else 0
    _total_det_norm = sum(item["importe_norm"] for item in costes_detalle)
    for item in costes_detalle:
        item["pct_norm"] = round(item["importe_norm"] / _total_det_norm * 100, 1) if _total_det_norm else 0

    return {
        "resumen": {
            "total_costes":           total_costes_all,
            "total_costes_norm":      total_costes_norm,
            "costes_operativos":      total_pl["costes_operativos"],
            "costes_op_contable":     costes_op_contable_d7,
            "costes_captacion":       total_pl["costes_captacion"],
            "sin_mapear":             sin_mapear,
            "comision_bruta":         comision_bruta,
            "ratio_costes_pct":       total_pl["ratio_costes_op_pct"],
            "ratio_costes_pct_norm":  round(total_pl["costes_operativos"] / comision_bruta * 100, 2) if comision_bruta else 0.0,
            "ratio_captacion_pct":    round(total_pl["costes_captacion"]  / comision_bruta * 100, 2) if comision_bruta else 0.0,
            "ratio_total_pct":        round(total_costes_all  / comision_bruta * 100, 2) if comision_bruta else 0.0,
            "ratio_total_pct_norm":   round(total_costes_norm / comision_bruta * 100, 2) if comision_bruta else 0.0,
            "n_recibos":              n_recibos_costes,
            "coste_por_recibo":       coste_por_recibo,
            "coste_por_recibo_norm":  coste_por_recibo_norm,
            "cesion_estimada":     round(ces_est_costes, 2),
            "n_sin_cesion":        n_sin_ces_costes,
            "ebitda_estimado":     ebitda_estimado_costes,
            "margen_pct_estimado": round(ebitda_estimado_costes / comision_bruta * 100, 2) if comision_bruta else 0.0,
            "cesion_normalizada":       cos_ces_norm,
            "cesion_ajuste_analitico":  0.0,
            "cesion_años_ant":          0.0,
            "ebitda_normalizado":       cos_ebitda_norm,
            "margen_pct_norm":          round(cos_ebitda_norm / comision_bruta * 100, 2) if comision_bruta else 0.0,
        },
        "detalle": costes_detalle,
    }


# ── Conciliación ─────────────────────────────────────────────────────────────

def conciliacion(db: Session, ejercicio: int, tasa_cesion_estimada: float | None = None) -> dict:
    """
    Comprueba la coherencia entre el diario contable, el modelo analítico y la
    cuenta de resultados del presupuesto que usa este ejercicio como base real.
    """
    tasa_cesion_estimada = resolver_tasa(db, ejercicio, tasa_cesion_estimada)
    from ..models.presupuesto import Presupuesto
    from .cuenta_resultados import calcular_cuenta_resultados

    # ── Valores analíticos ─────────────────────────────────────────────────────
    an_rows = _q(db, _PL_SQL.format(extra=""), ej=ejercicio)
    sin_datos = not an_rows
    if not sin_datos:
        an_pl = _calc_pl(an_rows)
        an_sin_mapear = an_pl.get("sin_mapear", 0.0)  # ya incluido en an_pl["ebitda"]
    else:
        an_pl = {k: 0.0 for k in ['comision_bruta', 'comision_auxiliar', 'costes_operativos',
                                    'costes_captacion', 'margen_pct', 'ebitda', 'sin_mapear']}
        an_sin_mapear = 0.0

    # Resultado financiero (66*) no está en el EBITDA pero sí en Σ 6* del diario.
    an_financiero = -sum(float(r[2]) for r in an_rows
                         if r[0] == 'gasto' and r[1] == NATURALEZA_RESULTADO_FINANCIERO)
    an_total_costes = (an_pl["costes_operativos"] + an_pl["comision_auxiliar"]
                       + an_pl["costes_captacion"] + an_sin_mapear + an_financiero)

    # _calc_pl ya incluye sin_mapear en ebitda — no hay que corregir
    an_ebitda_real = an_pl["ebitda"]
    an_margen_real = an_pl["margen_pct"]

    # Cesión estimada: misma regla SQL que todos los dashboards
    an_cesion_estimada, an_n_sin_cesion = (
        _cesion_estimada_global(db, ejercicio, tasa_cesion_estimada)
        if not sin_datos else (0.0, 0)
    )
    an_ebitda_estimado      = round(an_ebitda_real - an_cesion_estimada, 2)
    an_margen_pct_estimado  = (
        round(an_ebitda_estimado / an_pl["comision_bruta"] * 100, 2)
        if an_pl["comision_bruta"] else 0.0
    )

    # Cesión normalizada: elimina desfase temporal y añade devengado no pagado
    if not sin_datos:
        an_ces_norm, _, _, _ = _calc_cesion_normalizada(db, ejercicio, tasa_cesion_estimada)
        an_ces_ant = 0.0
        an_ces_directa   = round(an_ces_norm - an_cesion_estimada, 2)
        an_delta_norm    = an_pl["comision_auxiliar"] - an_ces_norm
        an_cn_norm       = round(an_pl["comision_neta"] + an_delta_norm, 2)
        an_ebitda_norm   = round(an_ebitda_real + an_delta_norm, 2)
        an_margen_norm   = round(an_ebitda_norm / an_pl["comision_bruta"] * 100, 2) if an_pl["comision_bruta"] else 0.0
    else:
        an_ces_norm = an_ces_ant = an_cn_norm = an_ebitda_norm = an_margen_norm = an_ces_directa = 0.0

    # ── Valores del diario (cuentas del ejercicio) ─────────────────────────────
    def _sd(sql, **kw):
        return float(_q(db, sql, ej=ejercicio, **kw)[0][0])

    diario_ingresos = _sd("""
        SELECT COALESCE(SUM(CAST(haber AS FLOAT) - CAST(debe AS FLOAT)), 0)
        FROM diario_apuntes
        WHERE ejercicio = :ej AND numero_cuenta LIKE :p AND estado::text != 'excluido'
    """, p='7%')

    diario_cesion = _sd("""
        SELECT COALESCE(SUM(CAST(debe AS FLOAT) - CAST(haber AS FLOAT)), 0)
        FROM diario_apuntes
        WHERE ejercicio = :ej AND numero_cuenta LIKE :p AND estado::text != 'excluido'
    """, p='623%')

    diario_gastos_6 = _sd("""
        SELECT COALESCE(SUM(CAST(debe AS FLOAT) - CAST(haber AS FLOAT)), 0)
        FROM diario_apuntes
        WHERE ejercicio = :ej AND numero_cuenta LIKE :p AND estado::text != 'excluido'
    """, p='6%')

    # Cesión analítica filtrada solo a cuentas 623* para comparar con el diario.
    # Los AnaliticoAjusteCoste generan filas naturaleza='Cesión auxiliar' con
    # numero_cuenta='640'/'642' — se excluyen aquí porque el diario no las tiene
    # como 623* y causarían una diferencia permanente e inexplicable en la conciliación.
    an_cesion_623 = float((_q(db, """
        SELECT COALESCE(SUM(-CAST(importe AS FLOAT)), 0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej
          AND naturaleza = 'Cesión auxiliar'
          AND numero_cuenta LIKE '623%%'
    """, ej=ejercicio) or [[0.0]])[0][0])

    # Importe de AnaliticoAjusteCoste (cuentas no-623 clasificadas como cesión analítica)
    an_cesion_ajuste = float((_q(db, """
        SELECT COALESCE(SUM(-CAST(importe AS FLOAT)), 0)
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej
          AND naturaleza = 'Cesión auxiliar'
          AND numero_cuenta NOT LIKE '623%%'
    """, ej=ejercicio) or [[0.0]])[0][0])

    # ── EBITDA cuenta de resultados (presupuesto con ejercicio_base = este ejercicio) ──
    ppto = db.query(Presupuesto).filter(Presupuesto.ejercicio_base == ejercicio).first()
    cr_ebitda = None
    ppto_info = None
    if ppto:
        cr = calcular_cuenta_resultados(db, ppto)
        cr_ebitda = float(cr["ebitda"]["base"])
        ppto_info = {
            "ejercicio_presupuesto": ppto.ejercicio,
            "ebitda_base": round(cr_ebitda, 2),
        }

    # ── Construir checks ───────────────────────────────────────────────────────
    TOL = 0.50

    def _chk(label, a, b, desc_a, desc_b, nota=None):
        diff = round(a - b, 2)
        c = {
            "label": label,
            "tipo": "importe",
            "valor_a": round(a, 2), "desc_a": desc_a,
            "valor_b": round(b, 2), "desc_b": desc_b,
            "diferencia": diff,
            "ok": abs(diff) <= TOL,
        }
        if nota:
            c["nota"] = nota
        return c

    checks = [
        _chk(
            "Comisiones brutas",
            diario_ingresos, an_pl["comision_bruta"],
            "Σ Cuentas 7* · Diario", "Comisiones Brutas · Analítico",
            nota="Todos los ingresos del diario (cuentas 7*) deben estar capturados en el modelo.",
        ),
        _chk(
            "Cesión auxiliar (623*)",
            diario_cesion, round(an_cesion_623, 2),
            "Σ Cuentas 623* · Diario", "Σ Cuentas 623* · Analítico (fact)",
            nota=(
                "Compara solo las cuentas 623* en ambos lados. Deben coincidir exactamente "
                "una vez que el recálculo analítico está actualizado y todas las 623* tienen auxiliar resuelto. "
                + (f"Nota: hay {round(an_cesion_ajuste, 2):,.0f} € de ajustes analíticos (cuentas 640/642 reclasificadas "
                   f"como cesión en AnaliticoAjusteCoste) que NO están en el diario 623* y son esperados."
                   if an_cesion_ajuste > 0.5 else "")
            ),
        ),
        _chk(
            "Total costes (6*)",
            diario_gastos_6, an_total_costes,
            "Σ Cuentas 6* · Diario", "Total Costes · Analítico (mapeados + sin mapear)",
            nota="Si difiere, hay cuentas 6* excluidas del modelo por tipo de cuenta (tesorería).",
        ),
    ]

    if cr_ebitda is not None:
        checks.append(_chk(
            "EBITDA",
            an_ebitda_real, cr_ebitda,
            "EBITDA · Analítico", f"EBITDA real · Cuenta Resultados (ppto {ppto.ejercicio})",
            nota="Ambos modelos leen el mismo diario; deben producir el mismo EBITDA.",
        ))

    # ── Compañías con cesión > ingresos (anomalía de imputación) ──────────────
    # Excluimos filas con dim IS NULL: las cuentas 623* no tienen compañía asignada
    # (son GASTO, no INGRESO) por lo que NULL compañía es esperado, no una anomalía.
    _anomalia_sql = """
        SELECT
            {dim},
            COALESCE(SUM(CASE WHEN tipo_cuenta = 'ingreso'
                              THEN CAST(importe AS FLOAT) ELSE 0 END), 0) AS bruta,
            COALESCE(SUM(CASE WHEN naturaleza = 'Cesión auxiliar'
                              THEN -CAST(importe AS FLOAT) ELSE 0 END), 0) AS cesion
        FROM fact_resultado_analitico
        WHERE ejercicio = :ej
          AND {dim} IS NOT NULL
        GROUP BY {dim}
        HAVING COALESCE(SUM(CASE WHEN naturaleza = 'Cesión auxiliar'
                                 THEN -CAST(importe AS FLOAT) ELSE 0 END), 0)
               > COALESCE(SUM(CASE WHEN tipo_cuenta = 'ingreso'
                                   THEN CAST(importe AS FLOAT) ELSE 0 END), 0)
        ORDER BY 3 DESC
    """

    def _parse_anomalias(rows, key_field):
        return [
            {
                key_field:           r[0],
                "comision_bruta":    round(float(r[1]), 2),
                "comision_auxiliar": round(float(r[2]), 2),
                "exceso":            round(float(r[2]) - float(r[1]), 2),
            }
            for r in rows
        ]

    if not sin_datos:
        cia_rows = _q(db, _anomalia_sql.format(dim="compania", dim_label="compañía"), ej=ejercicio)
        aux_rows_anom = _q(db, _anomalia_sql.format(dim="auxiliar", dim_label="auxiliar"), ej=ejercicio)
    else:
        cia_rows = []
        aux_rows_anom = []

    companias_anomalas = _parse_anomalias(cia_rows, "compania")
    auxiliares_anomalos = _parse_anomalias(aux_rows_anom, "auxiliar")

    # Solo añadir el check al módulo de control si existen diferencias
    n_anomalas = len(companias_anomalas)
    if n_anomalas > 0:
        checks.append({
            "label":      "Cesión ≤ Ingresos / Cía.",
            "tipo":       "count",
            "valor_a":    n_anomalas,
            "desc_a":     "Compañías con cesión > ingresos",
            "valor_b":    0,
            "desc_b":     "Anomalías esperadas",
            "diferencia": n_anomalas,
            "ok":         False,
            "nota":       f"{n_anomalas} compañía(s) con cesión superior a sus ingresos — ver detalle abajo.",
        })

    n_aux_anom = len(auxiliares_anomalos)
    if n_aux_anom > 0:
        checks.append({
            "label":      "Cesión ≤ Ingresos / Aux.",
            "tipo":       "count",
            "valor_a":    n_aux_anom,
            "desc_a":     "Auxiliares con cesión > ingresos",
            "valor_b":    0,
            "desc_b":     "Anomalías esperadas",
            "diferencia": n_aux_anom,
            "ok":         False,
            "nota":       f"{n_aux_anom} auxiliar(es) con cesión superior a sus ingresos — ver detalle abajo.",
        })

    # ── Cesiones 623* sin recibo vinculado (solo si hay recibos para el ejercicio) ──
    n_recibos_ej = int((_q(db, "SELECT COUNT(*) FROM recibos WHERE ejercicio = :ej", ej=ejercicio) or [[0]])[0][0] or 0)
    tiene_recibos = n_recibos_ej > 0

    if tiene_recibos:
        # Solo cuenta los que no tienen auxiliar resuelto: si el recálculo asignó auxiliar
        # vía cuenta/descripción (niveles 2-4), quedan fuera de este check.
        cesion_sin_recibo_rows = _q(db, """
            SELECT
                numero_cuenta,
                COALESCE(NULLIF(descripcion_cuenta, ''), numero_cuenta) AS desc_label,
                COUNT(*)                                                 AS n_apuntes,
                COALESCE(SUM(CAST(debe AS FLOAT) - CAST(haber AS FLOAT)), 0) AS importe
            FROM diario_apuntes
            WHERE ejercicio = :ej
              AND numero_cuenta LIKE '623%'
              AND recibo_id IS NULL
              AND (auxiliar IS NULL OR auxiliar = '' OR auxiliar IN ('None', 'nan'))
              AND estado::text != 'excluido'
            GROUP BY numero_cuenta, descripcion_cuenta
            ORDER BY 4 DESC
        """, ej=ejercicio)

        cesion_sin_recibo = [
            {
                "auxiliar":   r[1] or r[0],
                "n_apuntes":  int(r[2]),
                "importe":    round(float(r[3]), 2),
            }
            for r in cesion_sin_recibo_rows
        ]
        n_sin_recibo = sum(r["n_apuntes"] for r in cesion_sin_recibo)
        total_sin_recibo = sum(r["importe"] for r in cesion_sin_recibo)
        if n_sin_recibo > 0:
            checks.append({
                "label":      "Recibo vinculado en 623*",
                "tipo":       "count",
                "valor_a":    n_sin_recibo,
                "desc_a":     "Apuntes 623* sin recibo ni auxiliar resuelto",
                "valor_b":    0,
                "desc_b":     "Esperado (0)",
                "diferencia": n_sin_recibo,
                "ok":         False,
                "nota":       (
                    f"{n_sin_recibo} apunte(s) · {round(total_sin_recibo, 0):,.0f} € sin recibo vinculado "
                    "ni auxiliar identificable — asigna el auxiliar manualmente o añade la cuenta al mapa."
                ),
            })
    else:
        cesion_sin_recibo = []

    # ── Cesiones 623* sin auxiliar identificado ──────────────────────────────
    cesion_sin_aux_rows = _q(db, """
        SELECT
            numero_cuenta,
            COALESCE(descripcion_cuenta, numero_cuenta),
            COUNT(*) AS n_apuntes,
            COALESCE(SUM(CAST(debe AS FLOAT) - CAST(haber AS FLOAT)), 0) AS importe
        FROM diario_apuntes
        WHERE ejercicio = :ej
          AND numero_cuenta LIKE '623%'
          AND (auxiliar IS NULL OR auxiliar = '' OR auxiliar = 'None' OR auxiliar = 'nan')
          AND estado::text != 'excluido'
        GROUP BY numero_cuenta, descripcion_cuenta
        ORDER BY 4 DESC
    """, ej=ejercicio)

    cesion_sin_auxiliar = [
        {
            "numero_cuenta":    r[0],
            "descripcion":      r[1],
            "n_apuntes":        int(r[2]),
            "importe":          round(float(r[3]), 2),
        }
        for r in cesion_sin_aux_rows
    ]

    n_sin_aux = len(cesion_sin_auxiliar)
    checks.append({
        "label":      "Cesión 623* con auxiliar",
        "tipo":       "count",
        "valor_a":    n_sin_aux,
        "desc_a":     "Cuentas 623* sin auxiliar asignado",
        "valor_b":    0,
        "desc_b":     "Esperado (0)",
        "diferencia": n_sin_aux,
        "ok":         n_sin_aux == 0,
        "nota":       (
            f"{n_sin_aux} cuenta(s) 623* sin auxiliar identificado — ver tabla abajo para asignarlos."
            if n_sin_aux > 0 else
            "Todas las cesiones 623* tienen auxiliar identificado."
        ),
    })

    return {
        "ejercicio": ejercicio,
        "sin_datos_analitico": sin_datos,
        "checks": checks,
        "companias_anomalas": companias_anomalas,
        "auxiliares_anomalos": auxiliares_anomalos,
        "cesion_sin_recibo": cesion_sin_recibo,
        "cesion_sin_auxiliar": cesion_sin_auxiliar,
        "analitico": {
            "comision_bruta":     round(an_pl["comision_bruta"],    2),
            "comision_auxiliar":  round(an_pl["comision_auxiliar"], 2),  # total incl. ajustes
            "cesion_623":         round(an_cesion_623,               2),  # solo 623* = comparable con diario
            "cesion_ajuste":      round(an_cesion_ajuste,            2),  # AnaliticoAjusteCoste (640/642)
            "costes_operativos":  round(an_pl["costes_operativos"], 2),
            "costes_captacion":   round(an_pl["costes_captacion"],  2),
            "sin_mapear":          round(an_sin_mapear,               2),
            "ebitda":              an_ebitda_real,
            "margen_pct":          an_margen_real,
            # Estimación: recibos con auxiliar y cesión 0
            "cesion_estimada":     an_cesion_estimada,
            "n_sin_cesion":        an_n_sin_cesion,
            "ebitda_estimado":     an_ebitda_estimado,
            "margen_pct_estimado": an_margen_pct_estimado,
            # Normalizada: elimina desfase temporal y añade devengado no pagado
            "cesion_normalizada":     an_ces_norm,
            "cesion_directa":         an_ces_directa,
            "cesion_años_anteriores": 0.0,
            "comision_neta_norm":     an_cn_norm,
            "ebitda_normalizado":     an_ebitda_norm,
            "margen_pct_norm":        an_margen_norm,
        },
        "diario": {
            "ingresos_7": round(diario_ingresos, 2),
            "cesion_623": round(diario_cesion,   2),
            "gastos_6":   round(diario_gastos_6, 2),
        },
        "presupuesto": ppto_info,
    }


# ── Asignación manual de auxiliar en 623 sin auxiliar ────────────────────────

def asignar_auxiliar_cesion(db: Session, ejercicio: int, numero_cuenta: str, auxiliar: str) -> int:
    """Asigna auxiliar a todos los apuntes 623 sin auxiliar del ejercicio+cuenta."""
    result = db.execute(
        _text("""
            UPDATE diario_apuntes
               SET auxiliar = :aux
             WHERE ejercicio = :ej
               AND numero_cuenta = :cta
               AND (auxiliar IS NULL OR auxiliar = '')
               AND estado::text != 'excluido'
        """),
        {"aux": auxiliar.strip(), "ej": ejercicio, "cta": numero_cuenta},
    )
    db.commit()
    return result.rowcount


# ── Valoración de correduría ─────────────────────────────────────────────────

# Múltiplos de mercado (SegurosNews / Recoletos Consultores 2025)
_MULT_COM  = {"pesimista": 1.5, "base": 1.8, "optimista": 2.2}
_MULT_EBIT = {"pesimista": 4.0, "base": 5.0, "optimista": 7.0}

# Ramos considerados de "alta calidad" (mayor comisión + mayor retención)
_RAMOS_PREMIUM = {"Multirriesgos", "Responsabilidad Civil", "Accidentes",
                  "Transporte", "Ingeniería", "Crédito"}


def _cagr(inicio: float, fin: float, años: int) -> float | None:
    if años <= 0 or inicio <= 0:
        return None
    return round((fin / inicio) ** (1 / años) - 1, 4)


def calcular_valoracion(db: Session, ejercicio: int, crecimiento_manual: float | None = None) -> dict:
    """
    Calcula la valoración de la correduría usando datos del modelo analítico.
    Aplica cuatro factores de ajuste automáticos sobre los múltiplos base de mercado.
    """
    # ── 1. Métricas del ejercicio seleccionado ────────────────────────────────
    pl = _q(db, _PL_SQL.format(extra=""), ej=ejercicio)
    if not pl:
        return {"sin_datos": True}

    total_pl = _calc_pl(pl)
    comision_bruta = total_pl["comision_bruta"]
    ebitda         = total_pl["ebitda"]
    margen_pct     = total_pl["margen_pct"]
    ratio_cesion   = total_pl["ratio_cesion_pct"]

    n_recibos = db.execute(
        _text(f"SELECT COUNT(*) FROM recibos WHERE id IN ({_REC_EN_EJ})"), {"ej": ejercicio}
    ).scalar() or 0

    # ── 2. Split cartera / NP ─────────────────────────────────────────────────
    split = _q(db, """
        SELECT es_nueva_produccion,
               COALESCE(SUM(CASE WHEN tipo_cuenta='ingreso' THEN importe END),0) AS ing
        FROM fact_resultado_analitico WHERE ejercicio=:ej
        GROUP BY es_nueva_produccion
    """, ej=ejercicio)
    ing_np   = sum(float(r[1]) for r in split if r[0])
    ing_cart = sum(float(r[1]) for r in split if not r[0])
    cart_pct = round(ing_cart / comision_bruta * 100, 1) if comision_bruta else 0
    np_pct   = round(100 - cart_pct, 1)

    # ── 3. Concentración auxiliares (top 3 y top 4) ──────────────────────────
    aux_rows = _q(db, """
        SELECT auxiliar, COALESCE(SUM(CASE WHEN tipo_cuenta='ingreso' THEN importe ELSE 0 END),0) AS ing
        FROM fact_resultado_analitico WHERE ejercicio=:ej AND auxiliar IS NOT NULL
        GROUP BY auxiliar ORDER BY ing DESC
    """, ej=ejercicio)
    top3_aux_ing = sum(float(r[1]) for r in aux_rows[:3])
    top3_aux_pct = round(top3_aux_ing / comision_bruta * 100, 1) if comision_bruta else 0
    top3_aux_names = [r[0] for r in aux_rows[:3]]
    top4_aux_ing = sum(float(r[1]) for r in aux_rows[:4])
    top4_aux_pct = round(top4_aux_ing / comision_bruta * 100, 1) if comision_bruta else 0
    top4_aux_names = [r[0] for r in aux_rows[:4]]
    n_auxiliares = len(aux_rows)
    aux_detail = [
        {
            "auxiliar": r[0],
            "ingreso":  round(float(r[1]), 2),
            "pct":      round(float(r[1]) / comision_bruta * 100, 1) if comision_bruta else 0,
        }
        for r in aux_rows
    ]

    # ── 4. Concentración compañías (top 3) ────────────────────────────────────
    comp_rows = _q(db, """
        SELECT compania, COALESCE(SUM(CASE WHEN tipo_cuenta='ingreso' THEN importe ELSE 0 END),0) AS ing
        FROM fact_resultado_analitico WHERE ejercicio=:ej AND compania IS NOT NULL
        GROUP BY compania ORDER BY ing DESC
    """, ej=ejercicio)
    top3_comp_ing = sum(float(r[1]) for r in comp_rows[:3])
    top3_comp_pct = round(top3_comp_ing / comision_bruta * 100, 1) if comision_bruta else 0
    top3_comp_names = [r[0] for r in comp_rows[:3]]
    n_companias = len(comp_rows)

    # ── 5. Ramo mix (% high-value) ────────────────────────────────────────────
    ramo_rows = _q(db, """
        SELECT ramo, COALESCE(SUM(CASE WHEN tipo_cuenta='ingreso' THEN importe ELSE 0 END),0) AS ing
        FROM fact_resultado_analitico WHERE ejercicio=:ej AND ramo IS NOT NULL
        GROUP BY ramo ORDER BY ing DESC
    """, ej=ejercicio)
    ing_premium = sum(float(r[1]) for r in ramo_rows if r[0] in _RAMOS_PREMIUM)
    ramo_premium_pct = round(ing_premium / comision_bruta * 100, 1) if comision_bruta else 0
    top3_ramos = [(r[0], round(float(r[1]), 2)) for r in ramo_rows[:3]]
    ramos_detail = [
        {
            "ramo":       r[0],
            "ingreso":    round(float(r[1]), 2),
            "pct":        round(float(r[1]) / comision_bruta * 100, 1) if comision_bruta else 0,
            "es_premium": r[0] in _RAMOS_PREMIUM,
        }
        for r in ramo_rows
    ]
    # Umbral siguiente para ramos premium: <30%→-0.10×, 30-50%→0×, 50-70%→+0.10×, >70%→+0.20×
    _umbrales_premium = [30.0, 50.0, 70.0]
    umbral_premium_sig = next((u for u in _umbrales_premium if ramo_premium_pct < u), None)
    ing_premium_faltante = (
        round(comision_bruta * umbral_premium_sig / 100 - ing_premium, 2)
        if umbral_premium_sig else None
    )

    # ── 6. CAGR histórico de ingresos ────────────────────────────────────────
    hist = _q(db, """
        SELECT ejercicio, COALESCE(SUM(haber - debe),0) AS ing
        FROM diario_apuntes
        WHERE numero_cuenta LIKE '7%%' AND estado::text != 'excluido'
        GROUP BY ejercicio ORDER BY ejercicio
    """, ej=ejercicio)
    hist_sorted = sorted([(int(r[0]), float(r[1])) for r in hist], key=lambda x: x[0])
    cagr_5y = cagr_3y = None
    ej_actual = next((v for ej, v in hist_sorted if ej == ejercicio), None)
    if ej_actual:
        ej_5 = next((v for ej, v in hist_sorted if ej == ejercicio - 5), None)
        ej_3 = next((v for ej, v in hist_sorted if ej == ejercicio - 3), None)
        if ej_5: cagr_5y = _cagr(ej_5, ej_actual, 5)
        if ej_3: cagr_3y = _cagr(ej_3, ej_actual, 3)

    # Usa 3 años como referencia principal (tendencia reciente);
    # si no hay 3 años de datos, usa 5 años; None = sin datos históricos suficientes.
    if crecimiento_manual is not None:
        cagr_ref = crecimiento_manual
    elif cagr_3y is not None:
        cagr_ref = cagr_3y   # 3Y más representativo de la tendencia actual
    elif cagr_5y is not None:
        cagr_ref = cagr_5y
    else:
        cagr_ref = 0.0

    # ── 7. Factores de ajuste sobre el múltiplo ───────────────────────────────

    # A) Calidad de cartera (cartera recurrente vs NP)
    if cart_pct >= 80:   adj_cartera = +0.25
    elif cart_pct >= 70: adj_cartera = +0.15
    elif cart_pct >= 55: adj_cartera = 0.0
    else:                adj_cartera = -0.20

    # B) Concentración auxiliares
    if top3_aux_pct > 70:   adj_aux = -0.30
    elif top3_aux_pct > 55: adj_aux = -0.15
    elif top3_aux_pct > 40: adj_aux = -0.05
    else:                   adj_aux = 0.0

    # C) Ramo mix (% en ramos premium)
    if ramo_premium_pct > 70:   adj_ramos = +0.20
    elif ramo_premium_pct > 50: adj_ramos = +0.10
    elif ramo_premium_pct > 30: adj_ramos = 0.0
    else:                       adj_ramos = -0.10

    # D) Crecimiento (CAGR)
    if cagr_ref >= 0.08:    adj_crec = +0.25
    elif cagr_ref >= 0.05:  adj_crec = +0.15
    elif cagr_ref >= 0.02:  adj_crec = +0.05
    elif cagr_ref >= 0.0:   adj_crec = 0.0
    else:                   adj_crec = -0.15

    adj_total = round(adj_cartera + adj_aux + adj_ramos + adj_crec, 3)

    # ── 8. Valoración por múltiplo de comisiones ─────────────────────────────
    def _val_com(escen: str) -> dict:
        mult_base = _MULT_COM[escen]
        # Escenario pessimista: ajuste negativo pesa más; optimista: positivo pesa más
        peso = {"pesimista": 0.5, "base": 1.0, "optimista": 1.5}[escen]
        mult = round(mult_base + adj_total * peso, 3)
        return {
            "multiplo_base":    mult_base,
            "ajuste_aplicado":  round(adj_total * peso, 3),
            "multiplo_final":   mult,
            "valor":            round(comision_bruta * mult, 0),
        }

    # ── 9. Valoración por múltiplo de EBITDA ─────────────────────────────────
    def _val_ebit(escen: str) -> dict | None:
        if ebitda <= 0:
            return None  # EBITDA negativo: método no aplicable
        mult_base = _MULT_EBIT[escen]
        peso = {"pesimista": 0.5, "base": 1.0, "optimista": 1.5}[escen]
        adj_ebit = adj_total * 2 * peso  # factor de ajuste amplificado para EBITDA
        mult = round(mult_base + adj_ebit, 3)
        return {
            "multiplo_base":    mult_base,
            "ajuste_aplicado":  round(adj_ebit, 3),
            "multiplo_final":   mult,
            "valor":            round(ebitda * mult, 0),
        }

    # ── 10. Fórmula combinada (mercado español) ───────────────────────────────
    # Recoletos: (2×comisiones + 5×EBITDA) / 2
    val_combinado = None
    if ebitda > 0:
        val_combinado = round((2 * comision_bruta + 5 * ebitda) / 2, 0)

    return {
        "ejercicio": ejercicio,

        # Métricas financieras
        "financiero": {
            "comision_bruta":  round(comision_bruta, 2),
            "ebitda":          round(ebitda, 2),
            "margen_pct":      margen_pct,
            "ratio_cesion_pct": ratio_cesion,
            "n_recibos":       n_recibos,
            "comision_por_recibo": round(comision_bruta / n_recibos, 2) if n_recibos else 0,
        },

        # Perfil de cartera
        "perfil": {
            "cartera_pct":       cart_pct,
            "np_pct":            np_pct,
            "ramo_premium_pct":  ramo_premium_pct,
            "top3_aux_pct":      top3_aux_pct,
            "top4_aux_pct":      top4_aux_pct,
            "top3_comp_pct":     top3_comp_pct,
            "n_auxiliares":      n_auxiliares,
            "n_companias":       n_companias,
            "top3_aux_names":    top3_aux_names,
            "top4_aux_names":    top4_aux_names,
            "top3_comp_names":   top3_comp_names,
            "top3_ramos":        top3_ramos,
            "aux_detail":        aux_detail,
            "ramos_detail":      ramos_detail,
            "umbral_premium_siguiente":   umbral_premium_sig,
            "ingreso_premium_faltante":   ing_premium_faltante,
            "ingreso_premium_actual":     round(ing_premium, 2),
        },

        # Crecimiento histórico
        "crecimiento": {
            "cagr_5y":      cagr_5y,
            "cagr_3y":      cagr_3y,
            "cagr_usado":   round(cagr_ref, 4),
            "cagr_periodo": "manual" if crecimiento_manual is not None
                            else ("3 años" if cagr_3y is not None
                                  else ("5 años" if cagr_5y is not None else "—")),
            "manual":       crecimiento_manual is not None,
            "historico":    [{"ejercicio": e, "ingresos": round(v, 2)} for e, v in hist_sorted],
        },

        # Ajustes
        "ajustes": {
            "cartera":       {"valor": adj_cartera, "desc": "Calidad cartera recurrente",
                              "referencia": f"Cartera {cart_pct}% del total"},
            "concentracion": {"valor": adj_aux, "desc": "Concentración auxiliares",
                              "referencia": f"Top 3 auxiliares = {top3_aux_pct}%"},
            "ramos":         {"valor": adj_ramos, "desc": "Mix de ramos premium",
                              "referencia": f"Ramos premium = {ramo_premium_pct}%"},
            "crecimiento":   {"valor": adj_crec, "desc": "Tendencia de crecimiento",
                              "referencia": f"CAGR {round(cagr_ref*100,1)}%"},
            "total":         adj_total,
        },

        # Valoraciones
        "valoracion": {
            "comisiones": {
                "pesimista":  _val_com("pesimista"),
                "base":       _val_com("base"),
                "optimista":  _val_com("optimista"),
            },
            "ebitda": {
                "pesimista":  _val_ebit("pesimista"),
                "base":       _val_ebit("base"),
                "optimista":  _val_ebit("optimista"),
            },
            "combinado":      val_combinado,
        },

        # Referencias de mercado
        "mercado": {
            "multiples_comisiones": _MULT_COM,
            "multiples_ebitda":     _MULT_EBIT,
            "fuente": "SegurosNews / Recoletos Consultores 2025",
            "nota": "Múltiplos para corredurías españolas < 600k€ comisiones anuales. "
                    "Grupos aseguradores pagan prima adicional del 20-40% por sinergia.",
        },
    }


# ── Ajustes de coste CRUD ────────────────────────────────────────────────────

def listar_ajustes_coste(db: Session, ejercicio: int) -> list:
    return (
        db.query(AnaliticoAjusteCoste)
        .filter(AnaliticoAjusteCoste.ejercicio == ejercicio)
        .order_by(AnaliticoAjusteCoste.auxiliar, AnaliticoAjusteCoste.numero_cuenta)
        .all()
    )


def crear_ajuste_coste(
    db: Session, ejercicio: int, auxiliar: str, numero_cuenta: str,
    descripcion: str, importe_mensual: float,
) -> AnaliticoAjusteCoste:
    aj = AnaliticoAjusteCoste(
        ejercicio=ejercicio,
        auxiliar=auxiliar.strip(),
        numero_cuenta=numero_cuenta.strip(),
        descripcion=descripcion.strip(),
        importe_mensual=importe_mensual,
    )
    db.add(aj)
    db.commit()
    db.refresh(aj)
    return aj


def actualizar_ajuste_coste(
    db: Session, ajuste_id: str, **kwargs
) -> AnaliticoAjusteCoste | None:
    aj = db.query(AnaliticoAjusteCoste).filter_by(id=ajuste_id).first()
    if not aj:
        return None
    for k, v in kwargs.items():
        if hasattr(aj, k):
            setattr(aj, k, v)
    db.commit()
    db.refresh(aj)
    return aj


def eliminar_ajuste_coste(db: Session, ajuste_id: str) -> bool:
    aj = db.query(AnaliticoAjusteCoste).filter_by(id=ajuste_id).first()
    if not aj:
        return False
    db.delete(aj)
    db.commit()
    return True


# ── MAP_CUENTAS CRUD ──────────────────────────────────────────────────────────

def listar_map_cuentas(db: Session) -> list:
    return db.query(AnaliticoMapCuenta).order_by(AnaliticoMapCuenta.numero_cuenta).all()


def upsert_map_cuenta(db: Session, numero_cuenta: str, naturaleza: str, descripcion: str | None = None):
    mc = db.query(AnaliticoMapCuenta).filter_by(numero_cuenta=numero_cuenta).first()
    if mc:
        mc.naturaleza = naturaleza
        mc.descripcion = descripcion
    else:
        mc = AnaliticoMapCuenta(numero_cuenta=numero_cuenta, naturaleza=naturaleza, descripcion=descripcion)
        db.add(mc)
    db.commit()
    db.refresh(mc)
    return mc


def delete_map_cuenta(db: Session, numero_cuenta: str) -> bool:
    mc = db.query(AnaliticoMapCuenta).filter_by(numero_cuenta=numero_cuenta).first()
    if not mc:
        return False
    db.delete(mc)
    db.commit()
    return True


# ── MAP_DRIVERS CRUD ──────────────────────────────────────────────────────────

def listar_map_drivers(db: Session) -> list:
    stored = {md.naturaleza: md.driver for md in db.query(AnaliticoMapDriver).all()}
    result = []
    from ..models.analitico import NATURALEZAS, DRIVERS_DEFAULT
    for nat in NATURALEZAS:
        result.append({
            "naturaleza": nat,
            "driver": stored.get(nat, DRIVERS_DEFAULT.get(nat, "RECIBOS")),
        })
    return result


def upsert_map_driver(db: Session, naturaleza: str, driver: str):
    md = db.query(AnaliticoMapDriver).filter_by(naturaleza=naturaleza).first()
    if md:
        md.driver = driver
    else:
        md = AnaliticoMapDriver(naturaleza=naturaleza, driver=driver)
        db.add(md)
    db.commit()
    return {"naturaleza": naturaleza, "driver": driver}


# ── Importar desde map_cuentas_contables ─────────────────────────────────────

# Mapeo familia_gasto (existente) → naturaleza (analítico)
# Incluye tanto los nombres estándar como los nombres reales de la base de datos
_FAMILIA_A_NATURALEZA: dict[str, str | None] = {
    # ── Nombres estándar ──
    "Personal":                "Personal",
    "Cesiones a auxiliares":   "Cesión auxiliar",
    "Alquiler y oficina":      "Alquiler",
    "Tecnología y software":   "Tecnología",
    "Servicios profesionales": "Servicios profesionales",
    "Marketing y captación":   "Marketing",
    "Gastos financieros":      "Financiero",
    "Tributos y seguros":      "Impuestos",
    "Amortizaciones y ajustes": None,
    "Otros gastos":            "Suministros",
    # ── Nombres reales de la correduría ──
    "Cesión Auxiliar":         "Cesión auxiliar",
    "Cesion Auxiliar":         "Cesión auxiliar",
    "Alquiler":                "Alquiler",
    "Renting":                 "Alquiler",
    "Otros Servicios":         "Servicios profesionales",
    "Reparaciones":            "Servicios profesionales",
    "Seguros":                 "Seguros",   # 625 primas de seguros: no es un impuesto
    "Financieros":             "Financiero",
    "Relaciones Publicas":     "Marketing",
    "Relaciones Públicas":     "Marketing",
    "Suministros":             "Suministros",
    "Descuentos":              "Suministros",
    "Telefono":                "Comunicaciones",
    "Teléfono":                "Comunicaciones",
    "software":                "Tecnología",
    "Software":                "Tecnología",
    "Impuestos":               "Impuestos",
    "Amortizacion":            None,
    "Amortización":            None,
    "extraordinarios":         None,
    "Extraordinarios":         None,
}


def importar_desde_mapeo(db: Session) -> dict:
    """
    Copia las cuentas de gasto de map_cuentas_contables a analitico_map_cuentas,
    traduciendo familia_gasto → naturaleza.
    Omite amortizaciones. No sobreescribe entradas existentes.
    """
    from ..models.parametros import MapCuentaContable, TipoCuentaParam

    # Sin filtro activo: incluye todas (activo NULL también se importa)
    gastos = db.query(MapCuentaContable).filter(
        MapCuentaContable.tipo == TipoCuentaParam.GASTO,
        MapCuentaContable.activo.isnot(False),   # True o NULL — excluye solo False explícito
    ).all()

    # Índice case-insensitive del diccionario para tolerar variaciones de tildes/espacios
    _familia_lower = {k.strip().lower(): v for k, v in _FAMILIA_A_NATURALEZA.items()}

    insertadas = 0
    omitidas_amort = 0
    omitidas_existentes = 0
    familias_no_mapeadas: dict[str, list[str]] = {}  # familia → [cuentas]

    for cuenta in gastos:
        familia = (cuenta.familia_gasto or "").strip()
        familia_key = familia.lower()

        if familia_key not in _familia_lower:
            # Familia desconocida — registrar para diagnóstico
            familias_no_mapeadas.setdefault(familia or "(sin familia)", []).append(
                cuenta.numero_cuenta
            )
            continue

        naturaleza = _familia_lower[familia_key]
        if naturaleza is None:
            # Amortizaciones — excluidas del modelo analítico
            omitidas_amort += 1
            continue

        existing = db.query(AnaliticoMapCuenta).filter_by(
            numero_cuenta=cuenta.numero_cuenta
        ).first()
        if existing:
            omitidas_existentes += 1
            continue

        db.add(AnaliticoMapCuenta(
            numero_cuenta=cuenta.numero_cuenta,
            naturaleza=naturaleza,
            descripcion=cuenta.descripcion or cuenta.familia_gasto,
        ))
        insertadas += 1

    db.commit()
    return {
        "insertadas": insertadas,
        "omitidas_amortizaciones": omitidas_amort,
        "omitidas_ya_existentes": omitidas_existentes,
        "familias_no_mapeadas": {
            fam: cuentas for fam, cuentas in familias_no_mapeadas.items()
        },
    }


# ── Ejercicios disponibles ────────────────────────────────────────────────────

def ejercicios_disponibles(db: Session) -> list[int]:
    rows = db.query(DiarioApunte.ejercicio).distinct().order_by(
        DiarioApunte.ejercicio.desc()
    ).all()
    return [r[0] for r in rows]
