"""Golden master de funciones de solo lectura contra la base real (no escribe nada).

Uso (desde backend/):
    venv/Scripts/python.exe RUTA/golden_master.py capturar   guarda la salida actual
    venv/Scripts/python.exe RUTA/golden_master.py comparar   compara con lo guardado (igualdad EXACTA)

Uso en refactors (auditoría, fase 5): `capturar` ANTES de tocar el código y `comparar` después;
la salida debe ser idéntica. Capturas en la carpeta temporal del sistema (mf_golden), no en el repo.
"""
import hashlib
import json
import logging
import pathlib
import tempfile
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.services.analitico import calcular_valoracion  # noqa: E402
from app.services.rentabilidad_cliente import calcular_rentabilidad_clientes  # noqa: E402

# Capturas fuera del repositorio (contienen datos reales)
DIR = pathlib.Path(tempfile.gettempdir()) / "mf_golden" / "lectura"
DIR.mkdir(parents=True, exist_ok=True)
modo = sys.argv[1]

db = SessionLocal()
db.execute(text("SET TRANSACTION READ ONLY"))  # garantía: si algo intentara escribir, fallaría
ejercicios = [r[0] for r in db.execute(text("SELECT DISTINCT ejercicio FROM fact_resultado_analitico ORDER BY 1"))]
casos = []
for ej in ejercicios + [1999]:  # 1999: ejercicio sin datos (rama "sin_datos")
    for mc in (0.0, 50.0, 1000.0):
        for tasa in (None, 0.0, 0.3):
            casos.append((f"rentabilidad_{ej}_{mc}_{tasa}", lambda ej=ej, mc=mc, tasa=tasa:
                          calcular_rentabilidad_clientes(db, ej, mc, tasa)))
    for crec in (None, 0.0, 5.0, -3.5):
        casos.append((f"valoracion_{ej}_{crec}", lambda ej=ej, crec=crec: calcular_valoracion(db, ej, crec)))

def canonico(o):
    """-0.0 → 0.0: PostgreSQL suma floats en orden no fijo y el signo del cero varía
    entre ejecuciones (mismo valor numérico). Cualquier otra diferencia sí cuenta."""
    if isinstance(o, float):
        return 0.0 if o == 0 else o
    if isinstance(o, dict):
        return {k: canonico(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [canonico(v) for v in o]
    return o


fallos = 0
for nombre, fn in casos:
    try:
        salida = json.dumps(canonico(fn()), sort_keys=True, default=str, ensure_ascii=False)
    except Exception as e:  # una excepción también es un comportamiento a conservar
        salida = f"EXCEPCION {type(e).__name__}: {e}"
        db.rollback()
        db.execute(text("SET TRANSACTION READ ONLY"))
    f = DIR / f"{nombre}.json"
    if modo == "capturar":
        f.write_text(salida, encoding="utf-8")
    else:
        igual = f.read_text(encoding="utf-8") == salida
        if not igual:
            fallos += 1
            print("DIFERENTE:", nombre)
            try:
                va, vn = json.loads(f.read_text(encoding="utf-8")), json.loads(salida)
                def dif(a, b, ruta=""):
                    if isinstance(a, dict):
                        for k in a: yield from dif(a[k], b.get(k), f"{ruta}.{k}")
                    elif isinstance(a, list):
                        if len(a) != len(b): yield (ruta, f"len {len(a)} vs {len(b)}"); return
                        for i, (x, y) in enumerate(zip(a, b, strict=True)): yield from dif(x, y, f"{ruta}[{i}]")
                    elif a != b: yield (ruta, (a, b))
                for d in list(dif(va, vn))[:6]: print("    ", d)
            except Exception as e:
                print("    no comparable:", e)
db.rollback()
db.close()
huella = hashlib.sha256("".join((DIR / f"{n}.json").read_text(encoding="utf-8") for n, _ in casos).encode()).hexdigest()[:16]
print(f"{modo}: {len(casos)} casos, ejercicios con datos {ejercicios}, huella {huella}"
      + ("" if modo == "capturar" else f", diferencias: {fallos}"))
sys.exit(1 if fallos else 0)
