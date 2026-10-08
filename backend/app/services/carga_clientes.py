"""
Servicio de carga de clientes desde CSV o Excel.
Campos esperados: codigo_cliente, nombre, fecha_alta, fecha_nacimiento, tipo
"""
import io
import logging
import re
from datetime import date
from typing import Tuple

import pandas as pd
from sqlalchemy.orm import Session

from ..models.cliente import Cliente, TipoCliente

log = logging.getLogger(__name__)

_MES_ES_RE = re.compile(r'\b(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b', re.IGNORECASE)
_MES_ES_MAP = {
    'ene': 'Jan', 'feb': 'Feb', 'mar': 'Mar', 'abr': 'Apr',
    'may': 'May', 'jun': 'Jun', 'jul': 'Jul', 'ago': 'Aug',
    'sep': 'Sep', 'oct': 'Oct', 'nov': 'Nov', 'dic': 'Dec',
}

_COL_MAP = {
    'codigo': 'codigo_cliente',
    'codigo_cliente': 'codigo_cliente',
    'id_cliente': 'codigo_cliente',
    'id': 'codigo_cliente',
    'nombre': 'nombre',
    'razon_social': 'nombre',
    'nombre_cliente': 'nombre',
    'fecha_alta': 'fecha_alta',
    'alta': 'fecha_alta',
    'f_alta': 'fecha_alta',
    'fecha_nacimiento': 'fecha_nacimiento',
    'nacimiento': 'fecha_nacimiento',
    'f_nacimiento': 'fecha_nacimiento',
    'fnac': 'fecha_nacimiento',
    'f_nacimie': 'fecha_nacimiento',   # "F.Nacimie" → f_nacimie
    'fnacimie': 'fecha_nacimiento',
    'tipo': 'tipo',
    'tipo_cliente': 'tipo',
    'categoria': 'tipo',
    'fis_jur': 'tipo',                 # "Fis/Jur" → fis_jur
    'fisico_juridico': 'tipo',
    'telefono_fijo': 'telefono_fijo',
    'tel_fijo': 'telefono_fijo',
    'tfno_fijo': 'telefono_fijo',
    'fijo': 'telefono_fijo',
    't_fijo': 'telefono_fijo',         # "T. Fijo" → t_fijo
    'telefono_movil': 'telefono_movil',
    'tel_movil': 'telefono_movil',
    'movil': 'telefono_movil',
    'telefono': 'telefono_movil',
    'celular': 'telefono_movil',
    't_movil': 'telefono_movil',       # "T. Móvil" → t_movil
    'email': 'email',
    'correo': 'email',
    'e_mail': 'email',
    'mail': 'email',
}

_JURIDICO_VALUES = {'juridico', 'jurídico', 'empresa', 'sociedad', 'j', 'juridica', 'jurídica', 's.l.', 'sl', 's.a.', 'sa'}


def _str_opt(val) -> str | None:
    """Convierte a string limpio o None si está vacío/NaN."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s and s.lower() != 'nan' else None


def _norm_col(col: str) -> str:
    import unicodedata
    sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', col) if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '_', sin_acentos.lower()).strip('_')


def _reordenar_nombre(nombre: str) -> str:
    """
    Convierte de formato fichero 'NOMBRE APELLIDO1 APELLIDO2'
    al formato de recibos 'APELLIDO1 APELLIDO2 NOMBRE'.
    Asume que los dos últimos tokens son los apellidos.
    Con menos de 3 palabras no toca el orden.
    """
    partes = nombre.split()
    if len(partes) < 3:
        return nombre
    apellidos = partes[-2:]
    nombre_parts = partes[:-2]
    return ' '.join(apellidos + nombre_parts)


def _normalizar_nombre(nombre: str) -> str:
    limpio = re.sub(r'\s+', ' ', str(nombre).strip().upper())
    return _reordenar_nombre(limpio)


def _parse_fecha(valor) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, date):
        return valor
    s = _MES_ES_RE.sub(lambda m: _MES_ES_MAP[m.group().lower()], str(valor).strip())
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:
        return None


def cargar_csv_clientes(db: Session, contenido: bytes) -> Tuple[int, int]:
    """
    Carga clientes desde CSV o Excel. Devuelve (insertados, actualizados).
    """
    df = None

    # Intentar Excel primero (gestiona encoding internamente)
    try:
        df = pd.read_excel(io.BytesIO(contenido), dtype=str)
    except Exception:
        pass

    # CSV: probar separadores y encodings habituales en ficheros españoles
    if df is None:
        for sep in [';', ',', '\t']:
            for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                try:
                    candidate = pd.read_csv(io.BytesIO(contenido), sep=sep, dtype=str, encoding=enc)
                    if len(candidate.columns) > 1:
                        df = candidate
                        break
                except Exception:
                    continue
            if df is not None:
                break

    if df is None:
        raise ValueError("No se pudo leer el archivo. Asegúrate de que es CSV o Excel.")

    df.columns = [_norm_col(c) for c in df.columns]
    df.rename(columns={k: v for k, v in _COL_MAP.items() if k in df.columns}, inplace=True)

    missing = [c for c in ['codigo_cliente', 'nombre'] if c not in df.columns]
    if missing:
        raise ValueError(
            f"Columnas requeridas no encontradas: {missing}. "
            f"Columnas detectadas: {list(df.columns)}"
        )

    df = df.dropna(subset=['codigo_cliente', 'nombre'])
    insertados = 0
    actualizados = 0

    for _, row in df.iterrows():
        codigo = str(row['codigo_cliente']).strip()
        nombre = str(row['nombre']).strip()
        if not codigo or not nombre or codigo == 'nan' or nombre == 'nan':
            continue

        fecha_alta = _parse_fecha(row.get('fecha_alta')) if 'fecha_alta' in df.columns else None
        fecha_nac = _parse_fecha(row.get('fecha_nacimiento')) if 'fecha_nacimiento' in df.columns else None

        tipo_raw = str(row.get('tipo', '')).strip().lower() if 'tipo' in df.columns else ''
        tipo = TipoCliente.JURIDICO if tipo_raw in _JURIDICO_VALUES else TipoCliente.FISICO

        tel_fijo = _str_opt(row.get('telefono_fijo')) if 'telefono_fijo' in df.columns else None
        tel_movil = _str_opt(row.get('telefono_movil')) if 'telefono_movil' in df.columns else None
        email = _str_opt(row.get('email')) if 'email' in df.columns else None

        existente = db.query(Cliente).filter(Cliente.codigo_cliente == codigo).first()
        if existente:
            existente.nombre = nombre
            existente.nombre_normalizado = _normalizar_nombre(nombre)
            existente.fecha_alta = fecha_alta
            existente.fecha_nacimiento = fecha_nac
            existente.tipo = tipo
            if tel_fijo is not None:
                try:
                    existente.telefono_fijo = tel_fijo
                except Exception:
                    pass
            if tel_movil is not None:
                try:
                    existente.telefono_movil = tel_movil
                except Exception:
                    pass
            if email is not None:
                try:
                    existente.email = email
                except Exception:
                    pass
            actualizados += 1
        else:
            # Solo incluir campos de contacto si tienen valor,
            # para no forzar un INSERT con columnas que podrían no existir aún en BD.
            contacto = {}
            if tel_fijo is not None:
                contacto['telefono_fijo'] = tel_fijo
            if tel_movil is not None:
                contacto['telefono_movil'] = tel_movil
            if email is not None:
                contacto['email'] = email
            db.add(Cliente(
                codigo_cliente=codigo,
                nombre=nombre,
                nombre_normalizado=_normalizar_nombre(nombre),
                fecha_alta=fecha_alta,
                fecha_nacimiento=fecha_nac,
                tipo=tipo,
                **contacto,
            ))
            insertados += 1

    log.info("Carga clientes | insertados=%d actualizados=%d", insertados, actualizados)
    return insertados, actualizados
