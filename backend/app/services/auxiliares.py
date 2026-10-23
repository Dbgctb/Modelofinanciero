"""
Heurística de % de retención (IRPF) por auxiliar, compartida entre el alta
manual, la importación CSV y el relleno retroactivo del catálogo de
Administración → Auxiliares.
"""

PCT_RETENCION_FISICA = 15.0
PCT_RETENCION_JURIDICA = 0.0


def calcular_pct_retencion(auxiliar: str) -> float:
    """
    15% si el nombre del auxiliar no contiene "S.L." (con o sin el punto final,
    p.ej. "S.L" o "S.L."), 0% si lo contiene. No detecta otras formas jurídicas
    (S.A., S.COOP, C.B...) -- esos casos hay que corregirlos a mano.
    """
    nombre = (auxiliar or '').lower()
    return PCT_RETENCION_JURIDICA if 's.l' in nombre else PCT_RETENCION_FISICA
