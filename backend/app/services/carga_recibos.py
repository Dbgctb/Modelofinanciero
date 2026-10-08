"""
Servicio de carga del CSV de recibos.
Detecta el separador automáticamente y carga en la tabla recibos.
"""
import io
import logging
import re as _re
import time
import pandas as pd
from datetime import date
from typing import Tuple
from sqlalchemy.orm import Session
from ..models.carga import CargaContable, EstadoCarga
from ..models.recibo import Recibo
from .normalizer import extraer_ramo, norm_col

log = logging.getLogger(__name__)

# Mapa: clave normalizada → nombre de campo interno.
_RECIBOS_RENAMES = {
    'recibo':    'recibo_cia',    # "Recibo"
    'n_poliza':  'numero_poliza', # "Nº Póliza", "N° Póliza", "Nº Poliza"
    'abrev_cia': 'compania',      # "Abrev.Cía", "Abrev.Cia"
    'pr_tot':    'pr_total',      # "Pr.Tot"
    'pr_net':    'pr_neto',       # "Pr.Net"
}

_CLASE_TIPO_NEGOCIO = {
    'CARTERA':    'cartera',
    'PRODUCCION': 'nueva_produccion',
    'PRODUCCIÓN': 'nueva_produccion',
}

# Abreviaturas de mes en español → inglés para que pandas pueda parsear fechas
# como "14-ene-2026", "01-abr-2025", "15-ago-2025", "03-dic-2026".
_MES_ES_RE = _re.compile(
    r'\b(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b', _re.IGNORECASE
)
_MES_ES_MAP = {
    'ene': 'Jan', 'feb': 'Feb', 'mar': 'Mar', 'abr': 'Apr',
    'may': 'May', 'jun': 'Jun', 'jul': 'Jul', 'ago': 'Aug',
    'sep': 'Sep', 'oct': 'Oct', 'nov': 'Nov', 'dic': 'Dec',
}


def _parse_fecha(valor) -> date | None:
    if pd.isna(valor) or not valor:
        return None
    s = _MES_ES_RE.sub(lambda m: _MES_ES_MAP[m.group().lower()], str(valor).strip())
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:
        return None


def _parse_decimal(valor) -> float | None:
    if pd.isna(valor) or valor == '' or valor is None:
        return None
    try:
        return float(str(valor).replace('.', '').replace(',', '.'))
    except Exception:
        return None


def cargar_csv_recibos(db: Session, contenido: bytes, ejercicio: int, carga: CargaContable) -> Tuple[int, int]:
    """
    Carga el CSV de recibos en la tabla recibos para el ejercicio dado.
    Devuelve (insertados, actualizados).
    """
    # Detectar separador (punto y coma o coma)
    muestra = contenido[:2000].decode('latin-1', errors='replace')
    sep = ';' if muestra.count(';') > muestra.count(',') else ','

    df = pd.read_csv(
        io.BytesIO(contenido),
        sep=sep,
        encoding='latin-1',
        dtype=str,
        keep_default_na=False,
    )
    # Normalizar: eliminar acentos/mayúsculas/puntos/espacios,
    # luego aplicar renombrados donde la clave normalizada ≠ campo interno.
    df.columns = [_RECIBOS_RENAMES.get(norm_col(c), norm_col(c)) for c in df.columns]

    # Pre-carga completa en memoria: 1 query en lugar de N queries
    recibo_dict: dict[str, Recibo] = {
        r.codigo: r
        for r in db.query(Recibo).filter(Recibo.ejercicio == ejercicio).all()
    }

    insertados = 0
    actualizados = 0
    nuevos_bulk: list[Recibo] = []

    total_filas = len(df)
    t_inicio = time.monotonic()
    log.info("Recibos [ejercicio=%d]: iniciando proceso de %d filas", ejercicio, total_filas)

    for fila_num, (_, row) in enumerate(df.iterrows(), start=1):
        if fila_num % 500 == 0 or fila_num == total_filas:
            elapsed = time.monotonic() - t_inicio
            velocidad = fila_num / elapsed if elapsed > 0 else fila_num
            eta = (total_filas - fila_num) / velocidad if velocidad > 0 else 0
            log.info(
                "Recibos: %d/%d filas | %.1fs transcurridos | ~%.0fs restantes",
                fila_num, total_filas, elapsed, eta,
            )

        codigo = str(row.get('codigo', '')).strip()
        if not codigo or codigo == 'nan':
            continue

        producto = str(row.get('producto', '')).strip()
        ramo = extraer_ramo(producto) if producto else None

        clase_raw = str(row.get('clase', '')).strip().upper()
        tipo_negocio = _CLASE_TIPO_NEGOCIO.get(clase_raw)

        datos = {
            'ejercicio': ejercicio,
            'codigo': codigo,
            'recibo_cia': str(row.get('recibo_cia', '')).strip() or None,
            'desde': _parse_fecha(row.get('desde')),
            'hasta': _parse_fecha(row.get('hasta')),
            'numero_poliza': str(row.get('numero_poliza', '')).strip() or None,
            'compania': str(row.get('compania', '')).strip() or None,
            'pr_total': _parse_decimal(row.get('pr_total')),
            'pr_neto': _parse_decimal(row.get('pr_neto')),
            'c_ced': _parse_decimal(row.get('c_ced')),
            'reten': _parse_decimal(row.get('reten')),
            'liqui': _parse_decimal(row.get('liqui')),
            'ente': str(row.get('ente', '')).strip() or None,
            'cobro': str(row.get('cobro', '')).strip() or None,
            'tomador': str(row.get('tomador', '')).strip() or None,
            'producto': producto or None,
            'estado': str(row.get('estado', '')).strip() or None,
            'ramo': ramo,
            'tipo_negocio': tipo_negocio,
        }

        recibo = recibo_dict.get(codigo)
        if recibo:
            for k, v in datos.items():
                setattr(recibo, k, v)
            actualizados += 1
        else:
            nuevos_bulk.append(Recibo(**datos))
            insertados += 1

    # Inserción masiva: 1 round-trip en lugar de N inserts individuales
    if nuevos_bulk:
        db.bulk_save_objects(nuevos_bulk)

    carga.total_registros = insertados + actualizados
    carga.registros_correctos = insertados + actualizados
    carga.registros_con_incidencia = 0
    carga.estado = EstadoCarga.VALIDADO

    db.commit()
    elapsed_total = time.monotonic() - t_inicio
    log.info(
        "Recibos [ejercicio=%d]: completado — %d insertados, %d actualizados, %.1fs total",
        ejercicio, insertados, actualizados, elapsed_total,
    )
    return insertados, actualizados
