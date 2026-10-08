"""
Servicio de carga del diario contable (Excel .xlsx).
Enriquece cada apunte y genera incidencias automáticamente.
"""
import io
import logging
import time
import uuid
from decimal import Decimal
from typing import Tuple
import pandas as pd
from sqlalchemy import insert as sa_insert
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from ..models.carga import CargaContable, EstadoCarga, TipoCarga
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..models.incidencia import Incidencia, TipoIncidencia, EstadoIncidencia, INCIDENCIAS_CRITICAS
from ..models.parametros import MapCuentaContable
from ..models.recibo import Recibo
from .normalizer import norm_col, extraer_codigo_recibo, tipo_cuenta_desde_mapa

_DIARIO_RENAMES = {
    'ejercicio':        'ejercicio_col',
    'numero_de_cuenta': 'numero_cuenta',
}


def _buscar_mapa(numero_cuenta: str, mapa_dict: dict) -> MapCuentaContable | None:
    if numero_cuenta in mapa_dict:
        return mapa_dict[numero_cuenta]
    for length in range(min(len(numero_cuenta) - 1, 7), 2, -1):
        prefix = numero_cuenta[:length]
        if prefix in mapa_dict:
            return mapa_dict[prefix]
    return None


def _to_int_or_none(val) -> int | None:
    try:
        s = str(val).strip()
        return int(float(s)) if s and s != 'nan' else None
    except (ValueError, TypeError):
        return None


def _str_or_none(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s not in ('nan', 'None', 'none', 'NaN') else None


def _descripcion_incidencia(
    tipo: TipoIncidencia,
    numero_cuenta: str,
    codigo_recibo: str | None,
    concepto: str | None,
) -> str:
    msgs = {
        TipoIncidencia.CUENTA_SIN_MAPEAR:        f"Cuenta {numero_cuenta} no tiene clasificación configurada",
        TipoIncidencia.COMPANIA_NO_IDENTIFICADA: f"Cuenta de ingreso {numero_cuenta} sin compañía asignada",
        TipoIncidencia.RECIBO_NO_EXTRAIDO:        f"No se pudo extraer código de recibo del concepto: '{concepto}'",
        TipoIncidencia.RECIBO_NO_ENCONTRADO:      f"Recibo {codigo_recibo} no encontrado en tabla de recibos",
        TipoIncidencia.RECIBO_SIN_RAMO:           f"Recibo {codigo_recibo} encontrado pero sin ramo asignado",
        TipoIncidencia.RECIBO_SIN_CARTERA:        f"Recibo {codigo_recibo} sin clasificación cartera/nueva producción",
        TipoIncidencia.GASTO_SIN_FAMILIA:         f"Cuenta de gasto {numero_cuenta} sin familia asignada",
    }
    return msgs.get(tipo, str(tipo))


def _parse_decimal_series(series: pd.Series) -> list[float]:
    """Vectorized decimal parsing. Handles European format (1.234,56) and standard format (1234.56)."""
    s = series.astype(str).str.strip()
    has_comma = s.str.contains(',', regex=False)
    # European: dot=thousands sep → remove dots, then comma→dot
    european = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    # Standard: dot=decimal → use as-is
    processed = european.where(has_comma, other=s)
    return pd.to_numeric(processed, errors='coerce').fillna(0.0).tolist()


def _parse_fecha_series(series: pd.Series) -> list:
    """Vectorized date parsing. Returns a Python list of date | None — never NaT.
    El diario exporta fechas en formato ISO YYYY-MM-DD, por lo que dayfirst=False
    es imprescindible: con dayfirst=True pandas invierte día/mes cuando día<=12
    y devuelve NaT cuando día>12, corrompiendo la distribución mensual.
    """
    dt = pd.to_datetime(series.astype(str), dayfirst=False, errors='coerce')
    return [v.date() if pd.notna(v) else None for v in dt]


def procesar_diario_excel(
    db: Session,
    contenido: bytes,
    carga: CargaContable,
    ejercicio: int,
    tipo_carga: 'TipoCarga | None' = None,
) -> Tuple[int, int]:
    """
    Carga y enriquece el Excel del diario contable.
    Devuelve (correctos, con_incidencia).
    """
    t_inicio = time.monotonic()

    df = pd.read_excel(io.BytesIO(contenido), dtype=str, keep_default_na=False)
    df.columns = [_DIARIO_RENAMES.get(norm_col(c), norm_col(c)) for c in df.columns]

    # ── Vectorized pre-processing ─────────────────────────────────────────
    # Keep only 6*/7* accounts — eliminate irrelevant rows before the loop
    mask = df['numero_cuenta'].str.match(r'^[67]', na=False)
    df = df[mask].reset_index(drop=True)

    if df.empty:
        carga.total_registros = 0
        carga.registros_correctos = 0
        carga.registros_con_incidencia = 0
        carga.importe_debe_total = Decimal('0')
        carga.importe_haber_total = Decimal('0')
        carga.estado = EstadoCarga.VALIDADO
        db.commit()
        return 0, 0

    # Parse dates — returns plain Python date | None list (no NaT risk)
    fechas: list = _parse_fecha_series(df['fecha'] if 'fecha' in df.columns else pd.Series('', index=df.index))

    # Parse decimals — returns Python float list
    debes: list[float] = _parse_decimal_series(df['debe'] if 'debe' in df.columns else pd.Series('0', index=df.index))
    habers: list[float] = _parse_decimal_series(df['haber'] if 'haber' in df.columns else pd.Series('0', index=df.index))

    total_debe = sum(debes)
    total_haber = sum(habers)

    # Convert remaining columns to Python lists for fast loop access (avoids per-row pandas overhead)
    cuentas: list[str] = df['numero_cuenta'].tolist()
    conceptos: list = df['concepto'].tolist() if 'concepto' in df.columns else [''] * len(df)
    lineas: list = df['linea'].tolist() if 'linea' in df.columns else [None] * len(df)
    series_col: list = df['serie'].tolist() if 'serie' in df.columns else [None] * len(df)
    numeros: list = df['numero'].tolist() if 'numero' in df.columns else [None] * len(df)
    desc_cuentas: list = df['descripcion_cuenta'].tolist() if 'descripcion_cuenta' in df.columns else [None] * len(df)
    auxiliares_col: list = df['auxiliar'].tolist() if 'auxiliar' in df.columns else [None] * len(df)

    # ── Pre-load lookups (2 queries total) ────────────────────────────────
    mapa_dict: dict[str, MapCuentaContable] = {
        m.numero_cuenta: m
        for m in db.query(MapCuentaContable).filter(MapCuentaContable.activo == True).all()
    }

    # For historical loads: search all exercises (most recent wins) so ramo/tipo_negocio
    # can be resolved even when historical-year recibos are not loaded.
    if tipo_carga == TipoCarga.HISTORICO_ESTADISTICO:
        recibo_dict: dict[str, Recibo] = {}
        for r in db.query(Recibo).order_by(Recibo.ejercicio.asc()).all():
            recibo_dict[r.codigo] = r  # later (more recent) year overrides
    else:
        recibo_dict: dict[str, Recibo] = {
            r.codigo: r
            for r in db.query(Recibo).filter(Recibo.ejercicio == ejercicio).all()
        }

    # ── Row processing — plain dicts, no ORM object overhead ──────────────
    correctos = 0
    con_incidencia = 0
    apuntes_data: list[dict] = []
    incidencias_data: list[dict] = []
    carga_id = carga.id
    total_filas = len(df)

    log.info("Diario [carga_id=%s]: procesando %d filas", carga_id, total_filas)

    for idx in range(total_filas):
        if (idx + 1) % 1000 == 0 or (idx + 1) == total_filas:
            elapsed = time.monotonic() - t_inicio
            eta = (total_filas - idx - 1) / ((idx + 1) / elapsed) if elapsed > 0 else 0
            log.info("Diario: %d/%d | %.1fs | ~%.0fs restantes", idx + 1, total_filas, elapsed, eta)

        numero_cuenta = str(cuentas[idx]).strip()
        if not numero_cuenta or numero_cuenta == 'nan':
            continue

        fecha = fechas[idx]          # Python date | None — never NaT
        debe_val = debes[idx]        # Python float
        haber_val = habers[idx]      # Python float
        concepto = _str_or_none(conceptos[idx])
        mes = fecha.month if fecha is not None else None

        apunte_id = uuid.uuid4()
        mapa = _buscar_mapa(numero_cuenta, mapa_dict)
        tipo_cuenta = tipo_cuenta_desde_mapa(mapa)

        apunte: dict = {
            'id': apunte_id,
            'carga_id': carga_id,
            'ejercicio': ejercicio,
            'mes': mes,
            'linea': _to_int_or_none(lineas[idx]),
            'serie': _str_or_none(series_col[idx]),
            'numero': _str_or_none(numeros[idx]),
            'fecha': fecha,
            'debe': debe_val,
            'haber': haber_val,
            'numero_cuenta': numero_cuenta,
            'descripcion_cuenta': _str_or_none(desc_cuentas[idx]),
            'concepto': concepto,
            'tipo_cuenta': tipo_cuenta.value,    # serialize enum → str for Core INSERT
            'compania': mapa.compania if mapa else None,
            'familia_gasto': mapa.familia_gasto if mapa else None,
            'codigo_recibo': None,
            'recibo_id': None,
            'ramo': None,
            'auxiliar': None,
            'tipo_negocio': None,
            'estado': EstadoApunte.CORRECTO.value,
        }

        incidencias_apunte: list[TipoIncidencia] = []

        if tipo_cuenta == TipoCuenta.NO_CLASIFICADA:
            incidencias_apunte.append(TipoIncidencia.CUENTA_SIN_MAPEAR)

        elif tipo_cuenta == TipoCuenta.INGRESO:
            if not apunte['compania']:
                incidencias_apunte.append(TipoIncidencia.COMPANIA_NO_IDENTIFICADA)

            codigo = extraer_codigo_recibo(concepto)
            apunte['codigo_recibo'] = codigo

            if not codigo:
                incidencias_apunte.append(TipoIncidencia.RECIBO_NO_EXTRAIDO)
            else:
                recibo = recibo_dict.get(codigo)
                if not recibo:
                    incidencias_apunte.append(TipoIncidencia.RECIBO_NO_ENCONTRADO)
                else:
                    apunte['recibo_id'] = recibo.id
                    apunte['ramo'] = recibo.ramo
                    apunte['auxiliar'] = recibo.ente
                    apunte['tipo_negocio'] = recibo.tipo_negocio
                    if not recibo.ramo:
                        incidencias_apunte.append(TipoIncidencia.RECIBO_SIN_RAMO)
                    if not recibo.tipo_negocio:
                        incidencias_apunte.append(TipoIncidencia.RECIBO_SIN_CARTERA)

        elif tipo_cuenta == TipoCuenta.GASTO:
            apunte['auxiliar'] = _str_or_none(auxiliares_col[idx])
            # Para cuentas 623* el concepto lleva el código de recibo (últimas 6 cifras).
            # Vinculamos recibo_id para trazabilidad y como fuente de auxiliar si falta.
            if numero_cuenta.startswith('623'):
                codigo = extraer_codigo_recibo(concepto)
                if codigo:
                    apunte['codigo_recibo'] = codigo
                    recibo = recibo_dict.get(codigo)
                    if recibo:
                        apunte['recibo_id'] = recibo.id
                        apunte['ramo'] = recibo.ramo
                        apunte['tipo_negocio'] = recibo.tipo_negocio
                        if not apunte['auxiliar']:
                            apunte['auxiliar'] = recibo.ente
                # Sin recibo ni auxiliar del Excel → la descripción de cuenta tiene el auxiliar
                if not apunte['auxiliar']:
                    apunte['auxiliar'] = _str_or_none(desc_cuentas[idx])
            if not apunte['familia_gasto']:
                incidencias_apunte.append(TipoIncidencia.GASTO_SIN_FAMILIA)

        if incidencias_apunte:
            apunte['estado'] = EstadoApunte.CON_INCIDENCIA.value
            con_incidencia += 1
        else:
            correctos += 1

        apuntes_data.append(apunte)

        for tipo in incidencias_apunte:
            incidencias_data.append({
                'id': uuid.uuid4(),
                'carga_id': carga_id,
                'apunte_id': apunte_id,
                'tipo': tipo.value,              # serialize enum → str for Core INSERT
                'es_critica': 'si' if tipo in INCIDENCIAS_CRITICAS else 'no',
                'descripcion': _descripcion_incidencia(tipo, numero_cuenta, apunte['codigo_recibo'], concepto),
                'estado': EstadoIncidencia.PENDIENTE.value,
            })

    # ── Core bulk INSERT — bypasses ORM overhead, 3-5x faster than bulk_save_objects ──
    if apuntes_data:
        db.execute(sa_insert(DiarioApunte), apuntes_data)
    if incidencias_data:
        db.execute(sa_insert(Incidencia), incidencias_data)

    carga.total_registros = correctos + con_incidencia
    carga.registros_correctos = correctos
    carga.registros_con_incidencia = con_incidencia
    carga.importe_debe_total = Decimal(str(round(total_debe, 2)))
    carga.importe_haber_total = Decimal(str(round(total_haber, 2)))
    carga.estado = EstadoCarga.CON_INCIDENCIAS if con_incidencia > 0 else EstadoCarga.VALIDADO

    db.commit()
    elapsed_total = time.monotonic() - t_inicio
    log.info(
        "Diario [carga_id=%s]: completado — %d correctos, %d incidencias, %.1fs total",
        carga_id, correctos, con_incidencia, elapsed_total,
    )
    return correctos, con_incidencia
