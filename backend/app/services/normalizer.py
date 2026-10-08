"""
Lógica de enriquecimiento de apuntes contables:
  cuenta → tipo/compañía/familia
  concepto → código de recibo (últimas 6 posiciones numéricas)
  código → recibo → ramo, auxiliar, tipo_negocio
"""
import re
import unicodedata
from typing import Optional
from sqlalchemy.orm import Session


def norm_col(nombre: str) -> str:
    """
    Normaliza un nombre de columna de fichero externo a clave canónica.
    'Número de Cuenta' → 'numero_de_cuenta'
    'Compañía'         → 'compania'
    'Abrev.Cía'        → 'abrev_cia'
    'Nº Póliza'        → 'n_poliza'
    """
    # 1. Descomponer acentos (NFD) y eliminar marcas diacríticas (categoría Mn)
    sin_acentos = ''.join(
        c for c in unicodedata.normalize('NFD', nombre)
        if unicodedata.category(c) != 'Mn'
    )
    # 2. Minúsculas
    lower = sin_acentos.lower()
    # 3. Secuencias de caracteres no alfanuméricos → un solo '_'
    clean = re.sub(r'[^a-z0-9]+', '_', lower)
    # 4. Eliminar '_' al inicio/final
    return clean.strip('_')
from ..models.parametros import MapCuentaContable, TipoCuentaParam
from ..models.recibo import Recibo
from ..models.diario import TipoCuenta

CODIGO_REGEX = re.compile(r'(\d{6})\D*$')

RAMO_MAP = {
    '<A>': 'Autos',
    '<V>': 'Vida',
    '<D>': 'Diversos',
    '<H>': 'Hogar',
    '<S>': 'Salud',
    '<E>': 'Empresas',
    '<T>': 'Transportes',
    '<R>': 'Responsabilidad Civil',
}

SUBPRODUCTO_RAMO = {
    'AUTOS': 'Autos',
    'VIDA': 'Vida',
    'MULTIRRIESGOS': 'Multirriesgos',
    'R.C.': 'Responsabilidad Civil',
    'DECESOS': 'Decesos',
    'A.SANITARIA': 'Asistencia Sanitaria',
    'CREDITO': 'Crédito',
    'ACCIDENTES': 'Accidentes',
    'ENFERMEDAD': 'Enfermedad',
    'TRANSPORTE': 'Transporte',
    'INGENIERIA': 'Ingeniería',
    'CAUCION': 'Caución',
}


def extraer_codigo_recibo(concepto: Optional[str]) -> Optional[str]:
    """Extrae las últimas 6 posiciones numéricas del concepto contable (RF-DAT-06)."""
    if not concepto:
        return None
    match = CODIGO_REGEX.search(concepto.strip())
    if match:
        return match.group(1)
    # Buscar cualquier secuencia de 6 dígitos al final
    digits = re.findall(r'\d+', concepto)
    if digits:
        last = digits[-1]
        if len(last) >= 6:
            return last[-6:]
    return None


def extraer_ramo(producto: Optional[str]) -> Optional[str]:
    """Extrae el ramo desde el campo Producto del CSV de recibos."""
    if not producto:
        return None
    upper = producto.upper()
    for clave, ramo in SUBPRODUCTO_RAMO.items():
        if clave in upper:
            return ramo
    for prefijo, ramo in RAMO_MAP.items():
        if producto.startswith(prefijo):
            return ramo
    return None


def buscar_mapa_cuenta(db: Session, numero_cuenta: str) -> Optional[MapCuentaContable]:
    """
    Busca la configuración de una cuenta contable.
    Busca primero coincidencia exacta, luego por prefijos de longitud decreciente (RF-DAT-04).
    """
    # Exacta
    mapa = db.query(MapCuentaContable).filter(
        MapCuentaContable.numero_cuenta == numero_cuenta,
        MapCuentaContable.activo == True,
    ).first()
    if mapa:
        return mapa

    # Prefijos: 7 chars, 6, 5, 4, 3
    for length in range(min(len(numero_cuenta) - 1, 7), 2, -1):
        prefix = numero_cuenta[:length]
        mapa = db.query(MapCuentaContable).filter(
            MapCuentaContable.numero_cuenta == prefix,
            MapCuentaContable.activo == True,
        ).first()
        if mapa:
            return mapa

    return None


def tipo_cuenta_desde_mapa(mapa: Optional[MapCuentaContable]) -> TipoCuenta:
    if not mapa:
        return TipoCuenta.NO_CLASIFICADA
    # Campo explícito tiene precedencia sobre el valor legado del enum
    if getattr(mapa, 'excluir_tesoreria', False) or mapa.tipo == TipoCuentaParam.TESORERIA_EXCLUIDA:
        return TipoCuenta.TESORERIA_EXCLUIDA
    mapping = {
        TipoCuentaParam.INGRESO: TipoCuenta.INGRESO,
        TipoCuentaParam.GASTO: TipoCuenta.GASTO,
    }
    return mapping.get(mapa.tipo, TipoCuenta.NO_CLASIFICADA)


def buscar_recibo(db: Session, codigo: str, ejercicio: int) -> Optional[Recibo]:
    """Busca el recibo por código en el ejercicio dado (RF-DAT-07)."""
    return db.query(Recibo).filter(
        Recibo.codigo == codigo,
        Recibo.ejercicio == ejercicio,
    ).first()
