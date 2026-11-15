"""Golden master de recalcular_cross_selling, que ESCRIBE: se ejecuta en una transacción que
se deshace SIEMPRE (no hay commit en la función; aquí tampoco). No cambia la base.

Uso (desde backend/): venv/Scripts/python.exe RUTA/golden_cross.py capturar|comparar

Uso en refactors (auditoría, fase 5): `capturar` ANTES de tocar el código y `comparar` después;
la salida debe ser idéntica. Capturas en la carpeta temporal del sistema (mf_golden), no en el repo.
Fijar PYTHONHASHSEED=0 en ambas ejecuciones: el orden de los conjuntos influye en algunos desempates.
"""
import json
import logging
import pathlib
import tempfile
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from sqlalchemy import inspect as sa_inspect, text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.cliente import CrossSellingOportunidad, FugaAlerta  # noqa: E402
from app.services.cross_selling import recalcular_cross_selling  # noqa: E402

# Capturas fuera del repositorio (contienen datos reales)
DIR = pathlib.Path(tempfile.gettempdir()) / "mf_golden" / "cross_selling"
DIR.mkdir(parents=True, exist_ok=True)
modo = sys.argv[1]
IGNORAR = {"id", "recalculado_at", "created_at", "updated_at"}


def canon(v):
    if isinstance(v, float):
        return 0.0 if v == 0 else v
    if isinstance(v, dict):
        return {k: canon(x) for k, x in sorted(v.items())}
    if isinstance(v, (list, tuple, set)):
        return sorted((canon(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True, default=str))
    return v


def filas(db, modelo, ej):
    cols = [c.key for c in sa_inspect(modelo).mapper.column_attrs if c.key not in IGNORAR]
    out = [{c: canon(getattr(o, c)) for c in cols} for o in db.query(modelo).filter(modelo.ejercicio == ej).all()]
    return sorted(out, key=lambda d: json.dumps(d, sort_keys=True, default=str))


db = SessionLocal()
try:
    ejercicios = [r[0] for r in db.execute(text("SELECT DISTINCT ejercicio FROM recibos ORDER BY 1"))]
    resultado = {}
    for ej in ejercicios + [1999]:
        antes = (db.query(CrossSellingOportunidad).filter_by(ejercicio=ej).count(),
                 db.query(FugaAlerta).filter_by(ejercicio=ej).count())
        r = recalcular_cross_selling(db, ej)
        db.flush()
        resultado[str(ej)] = {"retorno": canon(r), "oportunidades": filas(db, CrossSellingOportunidad, ej),
                              "alertas": filas(db, FugaAlerta, ej), "filas_previas": antes}
finally:
    db.rollback()  # SIEMPRE: nada de lo calculado llega a la base
    db.close()

salida = json.dumps(resultado, sort_keys=True, default=str, ensure_ascii=False)
f = DIR / "cross.json"
if modo == "capturar":
    f.write_text(salida, encoding="utf-8")
    print("capturado:", {ej: (len(v["oportunidades"]), len(v["alertas"])) for ej, v in resultado.items()})
else:
    viejo = json.loads(f.read_text(encoding="utf-8"))
    nuevo = json.loads(salida)
    if viejo == nuevo:
        print("comparar: IDÉNTICO", {ej: (len(v["oportunidades"]), len(v["alertas"])) for ej, v in nuevo.items()})
    else:
        for ej in viejo:
            for k in ("retorno", "oportunidades", "alertas"):
                if viejo[ej][k] != nuevo.get(ej, {}).get(k):
                    a, b = viejo[ej][k], nuevo[ej][k]
                    print(f"DIFERENTE {ej}.{k}:", (len(a), len(b)) if isinstance(a, list) else (a, b))
                    if isinstance(a, list):
                        for x, y in zip(a, b, strict=True):
                            if x != y:
                                print("   ", {kk: (x[kk], y.get(kk)) for kk in x if x[kk] != y.get(kk)})
                                break
        sys.exit(1)
