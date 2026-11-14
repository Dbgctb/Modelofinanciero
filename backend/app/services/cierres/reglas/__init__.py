"""Registro de las 19 reglas de punteo (código de regla en cc_reglas → función)."""
from . import reglas_python as py
from . import reglas_sql as sql

REGLAS = {
    "RULE_A": sql.regla_a,
    "RULE_B": sql.regla_b,
    "RULE_C": py.regla_c,
    "RULE_E": py.regla_e,
    "RULE_H": py.regla_h,
    "RULE_I": sql.regla_i,
    "RULE_K": py.regla_k,
    "RULE_K2": py.regla_k2,
    "RULE_RETRO": py.regla_retro,
    "RULE_RETROCESO": py.regla_retroceso,
    "RULE_L": sql.regla_l,
    "RULE_O": sql.regla_o,
    "RULE_P": sql.regla_p,
    "RULE_Q": py.regla_q,
    "RULE_R": sql.regla_r,
    "RULE_S": sql.regla_s,
    "RULE_T": sql.regla_t,
    "RULE_V": py.regla_v,
    "CROSS_YEAR": sql.regla_cross_year,
}

# Se ejecutan una sola vez, tras el último ejercicio, sobre todos los ejercicios (en este orden).
REGLAS_FINALES = ["CROSS_YEAR", "RULE_L", "RULE_P", "RULE_Q", "RULE_R", "RULE_T"]
# Cierre de saldo 440*: siempre la última de cada ejercicio.
REGLA_ULTIMA = "RULE_V"
