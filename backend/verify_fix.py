from app.services.carga_diario import _str_or_none
from app.services.analitico import _recalcular_worker

print("_str_or_none(None)    =", repr(_str_or_none(None)))
print("_str_or_none('None')  =", repr(_str_or_none('None')))
print("_str_or_none('nan')   =", repr(_str_or_none('nan')))
print("_str_or_none('')      =", repr(_str_or_none('')))
print("_str_or_none('G7')    =", repr(_str_or_none('G7')))
print("Imports OK")
