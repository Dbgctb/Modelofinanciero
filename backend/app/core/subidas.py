"""Lectura segura de ficheros subidos: vacío, extensión y tamaño máximo.

Se valida por extensión y no por tipo MIME a propósito: en Windows con Excel instalado
el navegador envía los .csv como "application/vnd.ms-excel", y comprobar el MIME
rechazaría ficheros válidos. El contenido lo valida después el lector (pandas).
"""
from fastapi import UploadFile

from .errores import error_http


async def leer_subida(file: UploadFile, extensiones: tuple[str, ...], max_mb: int, esperado: str) -> bytes:
    """Devuelve el contenido del fichero o lanza ARC-001 (vacío), ARC-002 (extensión) o ARC-003 (tamaño).

    Lee como mucho max_mb + 1 byte: un fichero enorme no llega a cargarse entero en memoria.
    """
    nombre = (file.filename or "").lower()
    if not nombre.endswith(extensiones):
        raise error_http("ARC-002", esperado=esperado)
    limite = max_mb * 1024 * 1024
    contenido = await file.read(limite + 1)
    if not contenido:
        raise error_http("ARC-001")
    if len(contenido) > limite:
        raise error_http("ARC-003", max_mb=max_mb)
    return contenido
