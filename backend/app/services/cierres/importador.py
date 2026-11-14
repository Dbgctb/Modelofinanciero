"""Importación del diario completo a cc_apuntes (Excel o TXT/CSV separado por "|").

Traducción de app/services/importer.py del programa original:
- Completa: valida, borra el ejercicio si se pide e inserta todo. Aquí el borrado y la
  inserción van en UNA transacción (en el original, si fallaba la inserción, el
  ejercicio quedaba borrado).
- Incremental: compara el fichero con la base por (numero, fecha, cuenta, debe, haber,
  concepto); inserta solo los nuevos (es_nuevo) y marca los huérfanos (es_huerfano),
  sin tocar el punteo.

Sin dependencias nuevas: el original usaba chardet para adivinar la codificación del
TXT; aquí se prueba UTF-8 y, si falla, Windows-1252 (la del ERP en España).
"""
import csv
import io
import logging
from collections import defaultdict
from decimal import Decimal

import pandas as pd
from sqlalchemy import text

from .normalizador import extract_recibo, normalize_concepto
from ...core.errores import ErrorApp

log = logging.getLogger(__name__)

COLUMNAS_REQUERIDAS = ["Linea", "Serie", "Numero", "Ejercicio", "Fecha",
                       "Debe", "Haber", "Numero de Cuenta", "Concepto"]
COLUMNAS_BD = ["linea", "serie", "numero", "ejercicio", "fecha", "debe", "haber", "cuenta",
               "descripcion_cuenta", "concepto", "neto", "recibo_norm", "concepto_norm", "asiento_key"]


# ── Lectura ──────────────────────────────────────────────────────────────────

def _comprobar_columnas(df: pd.DataFrame, es_txt: bool = False) -> None:
    """Antes de usar ninguna columna: si no es el diario del ERP, decir qué le falta.

    Si un TXT/CSV sale con una sola columna, se mira si está separado por otro carácter
    (p. ej. los excel_AAAA.csv del programa antiguo van por comas) para decirlo claro.
    """
    columnas = [str(c).strip() for c in df.columns]
    if es_txt and len(columnas) == 1:
        for sep in (";", ",", "\t"):
            partes = [c.strip() for c in columnas[0].split(sep)]
            if len(partes) > 1:
                if all(c in partes for c in COLUMNAS_REQUERIDAS):
                    raise ErrorApp("CC-IMP-004", separador="tabulador" if sep == "\t" else sep)
                columnas = partes
                break
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in columnas]
    if faltan:
        raise ErrorApp("CC-IMP-003", faltan=", ".join(faltan), encontradas=", ".join(columnas))


def _leer_excel(contenido: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(contenido), dtype={
        "Linea": int, "Serie": str, "Numero": int, "Ejercicio": int,
        "Numero de Cuenta": int, "Descripcion Cuenta": str, "Concepto": str,
    })
    _comprobar_columnas(df)
    df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
    return df


def _leer_txt(contenido: bytes) -> pd.DataFrame:
    for codificacion in ("utf-8", "cp1252"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ErrorApp("CC-IMP-001")
    df = pd.read_csv(io.StringIO(texto), sep="|", decimal=",", thousands=".", dtype={
        "Linea": int, "Serie": str, "Numero": int, "Ejercicio": int, "Numero de Cuenta": int,
    })
    if df.columns[-1] == "" or "Unnamed" in str(df.columns[-1]):
        df = df.iloc[:, :-1]
    _comprobar_columnas(df, es_txt=True)
    df["Fecha"] = pd.to_datetime(df["Fecha"], format="%d/%m/%Y", errors="coerce")
    return df


def leer_fichero(nombre: str, contenido: bytes) -> pd.DataFrame:
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    try:
        if ext in ("xlsx", "xls"):
            df = _leer_excel(contenido)
        elif ext in ("txt", "csv"):
            df = _leer_txt(contenido)
        else:
            raise ErrorApp("CC-IMP-002", ext=ext)
    except ErrorApp:
        raise
    except Exception as e:  # incluye ValueError de pandas (p. ej. texto en una columna numérica)
        log.warning("Cierres importar | no se pudo leer '%s': %s: %s", nombre, type(e).__name__, e)
        raise ErrorApp("CC-IMP-005", tipo=type(e).__name__) from e
    return df


def _validar_y_normalizar(df: pd.DataFrame) -> pd.DataFrame:
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltan:
        raise ErrorApp("CC-IMP-003", faltan=", ".join(faltan), encontradas=", ".join(map(str, df.columns)))
    df = df.copy()
    df["Debe"] = df["Debe"].fillna(0)
    df["Haber"] = df["Haber"].fillna(0)
    sin_fecha = int(df["Fecha"].isna().sum())
    if sin_fecha:
        raise ErrorApp("CC-IMP-006", n=sin_fecha)
    if "Descripcion Cuenta" not in df.columns:
        df["Descripcion Cuenta"] = None
    df["recibo_norm"] = df["Concepto"].apply(extract_recibo)
    df["concepto_norm"] = df["Concepto"].apply(normalize_concepto)
    df["neto"] = df["Debe"] - df["Haber"]
    df["asiento_key"] = df["Ejercicio"].astype(str) + "|" + df["Serie"].astype(str) + "|" + df["Numero"].astype(str)
    return df.rename(columns={
        "Linea": "linea", "Serie": "serie", "Numero": "numero", "Ejercicio": "ejercicio",
        "Fecha": "fecha", "Debe": "debe", "Haber": "haber", "Numero de Cuenta": "cuenta",
        "Descripcion Cuenta": "descripcion_cuenta", "Concepto": "concepto",
    })


def _importe(v) -> Decimal:
    return Decimal(repr(float(v))).quantize(Decimal("0.01"))


def _fila_bd(r) -> list:
    """Fila del DataFrame normalizado → valores para cc_apuntes."""
    concepto = None if pd.isna(r.concepto) else str(r.concepto)
    desc = None if pd.isna(r.descripcion_cuenta) else str(r.descripcion_cuenta)
    return [int(r.linea), str(r.serie), int(r.numero), int(r.ejercicio), r.fecha.date(),
            _importe(r.debe), _importe(r.haber), str(int(r.cuenta)), desc, concepto,
            _importe(r.debe) - _importe(r.haber), r.recibo_norm, r.concepto_norm, r.asiento_key]


def _copiar(conn, filas, es_nuevo=False):
    """Inserta con COPY (rápido para ~140.000 filas)."""
    if not filas:
        return 0
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for f in filas:
        w.writerow([r"\N" if v is None else v for v in f] + (["t"] if es_nuevo else []))
    buf.seek(0)
    cols = ", ".join(COLUMNAS_BD + (["es_nuevo"] if es_nuevo else []))
    raw = conn.connection.dbapi_connection
    raw.cursor().copy_expert(f"COPY cc_apuntes ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
    return len(filas)


# ── Importación completa ─────────────────────────────────────────────────────

def importar_completo(engine, nombre, contenido, ejercicio: int, limpiar: bool, progreso=lambda *a, **k: None):
    progreso("Leyendo el fichero…")
    df = leer_fichero(nombre, contenido)
    ejercicios = sorted(df["Ejercicio"].dropna().astype(int).unique().tolist())
    if not ejercicios:
        raise ErrorApp("CC-IMP-007")
    if ejercicio not in ejercicios:
        raise ErrorApp("CC-IMP-008", ejercicio=ejercicio, ejercicios=", ".join(map(str, ejercicios)))
    df = df[df["Ejercicio"] == ejercicio]
    progreso(f"Normalizando {len(df):,} apuntes…".replace(",", "."))
    df = _validar_y_normalizar(df)
    filas = [_fila_bd(r) for r in df.itertuples(index=False)]

    with engine.begin() as conn:
        borrados = 0
        if limpiar:
            progreso(f"Borrando el ejercicio {ejercicio}…")
            borrados = conn.execute(text("DELETE FROM cc_apuntes WHERE ejercicio = :ej"),
                                    {"ej": ejercicio}).rowcount
        progreso(f"Insertando {len(filas):,} apuntes…".replace(",", "."))
        insertados = _copiar(conn, filas)
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(text("ANALYZE cc_apuntes"))
    return {"modo": "completo", "ejercicio": ejercicio, "ejercicios_en_fichero": ejercicios,
            "borrados": borrados, "insertados": insertados}


# ── Importación incremental ──────────────────────────────────────────────────

def _clave(numero, fecha, cuenta, debe, haber, concepto):
    return (int(numero), str(fecha)[:10], str(int(cuenta)), _importe(debe), _importe(haber),
            (concepto or "").strip())


def importar_incremental(engine, nombre, contenido, ejercicio: int, progreso=lambda *a, **k: None):
    progreso("Leyendo el fichero…")
    df = leer_fichero(nombre, contenido)
    df = df[df["Ejercicio"] == ejercicio]
    if len(df) == 0:
        raise ErrorApp("CC-IMP-009", ejercicio=ejercicio)
    progreso(f"Comparando {len(df):,} apuntes con la base…".replace(",", "."))
    df = _validar_y_normalizar(df)

    with engine.begin() as conn:
        conn.execute(text("UPDATE cc_apuntes SET es_nuevo = false, es_huerfano = false WHERE ejercicio = :ej"),
                     {"ej": ejercicio})
        en_bd = defaultdict(list)
        for r in conn.execute(text("""
            SELECT id, numero, fecha, cuenta, debe, haber, concepto
            FROM cc_apuntes WHERE ejercicio = :ej ORDER BY id
        """), {"ej": ejercicio}):
            en_bd[_clave(r.numero, r.fecha, r.cuenta, r.debe, r.haber, r.concepto)].append(r.id)

        nuevos = []
        for r in df.itertuples(index=False):
            concepto = None if pd.isna(r.concepto) else str(r.concepto)
            k = _clave(r.numero, r.fecha.date(), r.cuenta, r.debe, r.haber, concepto)
            if en_bd.get(k):
                en_bd[k].pop(0)          # existe: se consume uno (duplicados legítimos)
            else:
                nuevos.append(_fila_bd(r))
        huerfanos = [i for ids in en_bd.values() for i in ids]

        progreso(f"Insertando {len(nuevos):,} nuevos…".replace(",", "."))
        _copiar(conn, nuevos, es_nuevo=True)
        if huerfanos:
            conn.execute(text("UPDATE cc_apuntes SET es_huerfano = true WHERE id = ANY(:ids)"),
                         {"ids": huerfanos})
    return {"modo": "incremental", "ejercicio": ejercicio, "total_fichero": len(df),
            "nuevos": len(nuevos), "huerfanos": len(huerfanos), "sin_cambios": len(df) - len(nuevos)}


def eliminar_huerfanos(conn, ejercicio: int, ids: list[int]) -> dict:
    """Borra huérfanos NO punteados de la lista. Los punteados nunca se borran."""
    borrados = conn.execute(text("""
        DELETE FROM cc_apuntes
        WHERE id = ANY(:ids) AND ejercicio = :ej AND es_huerfano AND NOT reconciled
    """), {"ids": ids, "ej": ejercicio}).rowcount
    return {"borrados": borrados, "ignorados": len(set(ids)) - borrados}
