"""Normalización de recibos y conceptos del diario (copia fiel de app/utils/normalizer.py
del programa original). La usan la importación del diario y las reglas de punteo a
través de las columnas recibo_norm y concepto_norm.

Única diferencia: el original usaba pandas solo para detectar NaN; aquí se detecta
sin pandas (un float NaN no es igual a sí mismo).
"""
import re
import unicodedata


def _vacio(valor) -> bool:
    return not valor or (isinstance(valor, float) and valor != valor)


def extract_recibo(concepto) -> str:
    """Número de recibo del concepto.

    "Emisión Recibo Nº 236313" -> "236313"; "Venta Recibo Nº REC00000123" -> "00000123";
    "ASIENTO DE APERTURA" -> "".
    """
    if _vacio(concepto):
        return ""
    concepto_str = str(concepto)
    match = re.search(r"REC(\d+)", concepto_str, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"Recibo\s+(?:N[ºo°]?\s*)?(\d+)", concepto_str, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def remove_accents(texto) -> str:
    if not texto:
        return ""
    nfd = unicodedata.normalize("NFD", texto)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize_concepto(concepto) -> str:
    """Sin acentos, mayúsculas, sin "Nº" ni números de 6+ cifras, espacios simples.

    "Emisión Recibo Nº 236313" -> "EMISION RECIBO".
    """
    if _vacio(concepto):
        return ""
    mayus = remove_accents(str(concepto)).upper()
    sin_numero_simbolo = re.sub(r"N[ºo°]\.?\s*", "", mayus)
    sin_recibos = re.sub(r"\b\d{6,}\b", "", sin_numero_simbolo)
    return re.sub(r"\s+", " ", sin_recibos).strip()
