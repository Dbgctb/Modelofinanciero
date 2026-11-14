"""Resumen del estado del módulo: cuánto diario hay cargado y cuánto está punteado."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def resumen_por_ejercicio(db: Session) -> dict:
    """Apuntes, punteados y extractos bancarios por ejercicio.

    Con las tablas vacías devuelve listas vacías: las pantallas lo usan para
    mostrar el estado "sin datos todavía".
    """
    apuntes = db.execute(text("""
        SELECT ejercicio,
               COUNT(*)                                   AS total,
               COUNT(*) FILTER (WHERE reconciled)         AS punteados
        FROM cc_apuntes
        GROUP BY ejercicio
        ORDER BY ejercicio
    """)).mappings().all()
    extractos = db.execute(text("""
        SELECT ejercicio,
               COUNT(*)                                   AS total,
               COUNT(*) FILTER (WHERE reconciled)         AS conciliados
        FROM cc_extractos
        GROUP BY ejercicio
        ORDER BY ejercicio
    """)).mappings().all()
    return {
        "apuntes": [dict(r) for r in apuntes],
        "extractos": [dict(r) for r in extractos],
    }
