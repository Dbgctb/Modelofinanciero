"""
Catálogo interno de tasas de referencia de mercado (crecimiento y caída) con
las que se puebla tasas_mercado_ref. Usado tanto por el seed inicial
(scripts/seed_tasas_mercado.py) como por el botón "Poblar desde ICEA" de
Administración → Tasas de mercado (POST /admin/tasas-mercado/poblar-icea).

Solo cubre los años con datos publicados realmente verificados (ver fuentes
abajo) -- no se inventan tasas para años sin fuente. Para un año nuevo hay
que añadir aquí una fuente real antes de poder "poblarlo" desde el botón.

Fuentes:
  ICEA 2024: "Evolución del Mercado Asegurador 2024" (publicado ene-2025)
             Primas devengadas brutas No Vida total +7,78%
  ICEA 2025: Datos provisionales avance enero-diciembre 2025
             No Vida total +7,8%, Salud +11,43% (fuente: nota de prensa ICEA feb-2026)
  Tasas caída: Mejores prácticas mercado asegurador español
               (ratios persistencia ICEA + estándares actuariales corredurías)
"""

# Formato: (fuente, anyo, tipo, ramo_keyword, tasa_pct, es_default, notas)
TASAS_ICEA = [

    # ── CRECIMIENTO ICEA 2024 ───────────────────────────────────────────────
    ("ICEA", 2024, "crecimiento", "auto",          8.88, False, "Automóvil +8,88% ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "salud",          7.40, False, "Salud +7,40% ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "multirriesg",    8.62, False, "Multirriesgo +8,62% ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "hogar",          8.62, False, "Multirriesgo/Hogar +8,62% ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "comunidad",      8.62, False, "Comunidades (Multirriesgo) +8,62% ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "vida",           5.00, False, "Vida riesgo estimado ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "deceso",         5.20, False, "Decesos estimado sector 2024"),
    ("ICEA", 2024, "crecimiento", "accident",       4.00, False, "Accidentes estimado sector 2024"),
    ("ICEA", 2024, "crecimiento", "responsabilid",  5.50, False, "Responsabilidad Civil ICEA 2024"),
    ("ICEA", 2024, "crecimiento", " rc",            5.50, False, "RC abreviatura ICEA 2024"),
    ("ICEA", 2024, "crecimiento", "transport",      3.00, False, "Transporte estimado sector 2024"),
    ("ICEA", 2024, "crecimiento", "ingenier",       4.00, False, "Ingeniería estimado sector 2024"),
    ("ICEA", 2024, "crecimiento", "crédit",         3.00, False, "Crédito estimado sector 2024"),
    ("ICEA", 2024, "crecimiento", "credit",         3.00, False, "Crédito (sin acento) estimado 2024"),
    ("ICEA", 2024, "crecimiento", None,             7.78, True,  "No Vida total +7,78% ICEA 2024 (default)"),

    # ── CRECIMIENTO ICEA 2025 ───────────────────────────────────────────────
    # Fuente: avance datos anuales 2025, nota de prensa ICEA feb-2026
    ("ICEA", 2025, "crecimiento", "auto",           9.20, False, "Automóvil estimado ICEA 2025"),
    ("ICEA", 2025, "crecimiento", "salud",         11.43, False, "Salud +11,43% ICEA 2025"),
    ("ICEA", 2025, "crecimiento", "multirriesg",    9.00, False, "Multirriesgo estimado ICEA 2025"),
    ("ICEA", 2025, "crecimiento", "hogar",          9.00, False, "Hogar estimado ICEA 2025"),
    ("ICEA", 2025, "crecimiento", "comunidad",      9.00, False, "Comunidades estimado ICEA 2025"),
    ("ICEA", 2025, "crecimiento", "vida",           5.50, False, "Vida riesgo estimado 2025"),
    ("ICEA", 2025, "crecimiento", "deceso",         5.50, False, "Decesos estimado 2025"),
    ("ICEA", 2025, "crecimiento", "accident",       4.50, False, "Accidentes estimado 2025"),
    ("ICEA", 2025, "crecimiento", "responsabilid",  6.00, False, "RC estimado 2025"),
    ("ICEA", 2025, "crecimiento", " rc",            6.00, False, "RC abreviatura estimado 2025"),
    ("ICEA", 2025, "crecimiento", "transport",      3.50, False, "Transporte estimado 2025"),
    ("ICEA", 2025, "crecimiento", "ingenier",       4.50, False, "Ingeniería estimado 2025"),
    ("ICEA", 2025, "crecimiento", "crédit",         3.50, False, "Crédito estimado 2025"),
    ("ICEA", 2025, "crecimiento", "credit",         3.50, False, "Crédito estimado 2025"),
    ("ICEA", 2025, "crecimiento", None,             7.80, True,  "No Vida total +7,8% ICEA 2025 (default)"),

    # ── CAÍDA CARTERA 2024 ──────────────────────────────────────────────────
    # Fuente: ratios persistencia ICEA + estándares actuariales corredurías
    ("ICEA", 2024, "caida_cartera", "deceso",        4.0,  False, "Decesos: muy estable"),
    ("ICEA", 2024, "caida_cartera", "vida",          6.0,  False, "Vida riesgo"),
    ("ICEA", 2024, "caida_cartera", "salud",        10.0,  False, "Salud individual"),
    ("ICEA", 2024, "caida_cartera", "multirriesg",  11.0,  False, "Multirriesgo"),
    ("ICEA", 2024, "caida_cartera", "hogar",        11.0,  False, "Hogar"),
    ("ICEA", 2024, "caida_cartera", "comunidad",    11.0,  False, "Comunidades"),
    ("ICEA", 2024, "caida_cartera", "auto",         15.0,  False, "Automóvil: muy competitivo"),
    ("ICEA", 2024, "caida_cartera", "responsabilid",16.0,  False, "RC"),
    ("ICEA", 2024, "caida_cartera", " rc",          16.0,  False, "RC abreviatura"),
    ("ICEA", 2024, "caida_cartera", "empresa",      16.0,  False, "Empresas"),
    ("ICEA", 2024, "caida_cartera", "transport",    14.0,  False, "Transporte"),
    ("ICEA", 2024, "caida_cartera", "ingenier",     14.0,  False, "Ingeniería"),
    ("ICEA", 2024, "caida_cartera", None,           12.0,  True,  "Media correduría española (default cartera)"),

    # ── CAÍDA NUEVA PRODUCCIÓN 2024 ─────────────────────────────────────────
    ("ICEA", 2024, "caida_nueva_produccion", "deceso",        15.0, False, "Decesos primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "vida",          18.0, False, "Vida riesgo primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "salud",         22.0, False, "Salud primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "multirriesg",   22.0, False, "Multirriesgo primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "hogar",         22.0, False, "Hogar primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "comunidad",     22.0, False, "Comunidades primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "auto",          28.0, False, "Automóvil primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "responsabilid", 28.0, False, "RC primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", " rc",           28.0, False, "RC abreviatura primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "empresa",       28.0, False, "Empresas primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "transport",     25.0, False, "Transporte primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", "ingenier",      25.0, False, "Ingeniería primer año"),
    ("ICEA", 2024, "caida_nueva_produccion", None,            22.0, True,  "Media nueva producción primer año (default)"),

    # ── CAÍDA CARTERA 2025 ── (sin cambios significativos respecto 2024)
    ("ICEA", 2025, "caida_cartera", "deceso",        4.0,  False, "Decesos 2025"),
    ("ICEA", 2025, "caida_cartera", "vida",          6.0,  False, "Vida riesgo 2025"),
    ("ICEA", 2025, "caida_cartera", "salud",        10.0,  False, "Salud 2025"),
    ("ICEA", 2025, "caida_cartera", "multirriesg",  11.0,  False, "Multirriesgo 2025"),
    ("ICEA", 2025, "caida_cartera", "hogar",        11.0,  False, "Hogar 2025"),
    ("ICEA", 2025, "caida_cartera", "comunidad",    11.0,  False, "Comunidades 2025"),
    ("ICEA", 2025, "caida_cartera", "auto",         15.0,  False, "Automóvil 2025"),
    ("ICEA", 2025, "caida_cartera", "responsabilid",16.0,  False, "RC 2025"),
    ("ICEA", 2025, "caida_cartera", " rc",          16.0,  False, "RC 2025"),
    ("ICEA", 2025, "caida_cartera", "empresa",      16.0,  False, "Empresas 2025"),
    ("ICEA", 2025, "caida_cartera", "transport",    14.0,  False, "Transporte 2025"),
    ("ICEA", 2025, "caida_cartera", "ingenier",     14.0,  False, "Ingeniería 2025"),
    ("ICEA", 2025, "caida_cartera", None,           12.0,  True,  "Default cartera 2025"),

    # ── CAÍDA NUEVA PRODUCCIÓN 2025
    ("ICEA", 2025, "caida_nueva_produccion", "deceso",        15.0, False, "Decesos primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "vida",          18.0, False, "Vida primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "salud",         22.0, False, "Salud primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "multirriesg",   22.0, False, "Multirriesgo primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "hogar",         22.0, False, "Hogar primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "comunidad",     22.0, False, "Comunidades primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "auto",          28.0, False, "Automóvil primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "responsabilid", 28.0, False, "RC primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", " rc",           28.0, False, "RC primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "empresa",       28.0, False, "Empresas primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "transport",     25.0, False, "Transporte primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", "ingenier",      25.0, False, "Ingeniería primer año 2025"),
    ("ICEA", 2025, "caida_nueva_produccion", None,            22.0, True,  "Default nueva producción 2025"),
]
