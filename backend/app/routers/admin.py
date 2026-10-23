import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..core.database import get_db
from ..core.dependencies import require_admin
from ..models.user import User
from ..models.mercado import TasaMercadoRef, TipoTasaMercado
from ..models.auxiliares import AuxiliarComisionRef
from ..data.tasas_mercado_icea import TASAS_ICEA
from ..services.auxiliares import calcular_pct_retencion

router = APIRouter(prefix="/admin", tags=["Administración"])
log = logging.getLogger(__name__)


def _serializar(t: TasaMercadoRef) -> dict:
    return {
        "id": str(t.id),
        "fuente": t.fuente,
        "anyo": t.anyo,
        "tipo": t.tipo.value,
        "ramo_keyword": t.ramo_keyword,
        "tasa_pct": float(t.tasa_pct),
        "es_default": t.es_default,
        "notas": t.notas,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class TasaMercadoCreate(BaseModel):
    fuente: str
    anyo: int
    tipo: TipoTasaMercado
    ramo_keyword: Optional[str] = None
    tasa_pct: float
    es_default: bool = False
    notas: Optional[str] = None


class TasaMercadoUpdate(BaseModel):
    fuente: Optional[str] = None
    tasa_pct: Optional[float] = None
    es_default: Optional[bool] = None
    notas: Optional[str] = None


def _serializar_auxiliar(a: AuxiliarComisionRef) -> dict:
    return {
        "id": str(a.id),
        "anyo": a.anyo,
        "auxiliar": a.auxiliar,
        "comision_colaborador": float(a.comision_colaborador),
        "pct_retencion": float(a.pct_retencion),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


class AuxiliarComisionCreate(BaseModel):
    anyo: int
    auxiliar: str
    comision_colaborador: float


class AuxiliarComisionUpdate(BaseModel):
    comision_colaborador: Optional[float] = None
    pct_retencion: Optional[float] = None


@router.get("/tasas-mercado")
def listar_tasas(
    anyo: Optional[int] = Query(None),
    tipo: Optional[TipoTasaMercado] = Query(None),
    fuente: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(TasaMercadoRef)
    if anyo:
        q = q.filter(TasaMercadoRef.anyo == anyo)
    if tipo:
        q = q.filter(TasaMercadoRef.tipo == tipo)
    if fuente:
        q = q.filter(TasaMercadoRef.fuente == fuente)
    tasas = q.order_by(TasaMercadoRef.anyo.desc(), TasaMercadoRef.tipo, TasaMercadoRef.ramo_keyword).all()
    return [_serializar(t) for t in tasas]


@router.get("/tasas-mercado/anyos")
def listar_anyos(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Devuelve la lista de años disponibles en la tabla de tasas."""
    from sqlalchemy import distinct
    anyos = db.query(distinct(TasaMercadoRef.anyo)).order_by(TasaMercadoRef.anyo.desc()).all()
    return [a[0] for a in anyos]


@router.post("/tasas-mercado", status_code=201)
def crear_tasa(
    body: TasaMercadoCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tasa = TasaMercadoRef(
        id=uuid.uuid4(),
        fuente=body.fuente,
        anyo=body.anyo,
        tipo=body.tipo,
        ramo_keyword=body.ramo_keyword,
        tasa_pct=body.tasa_pct,
        es_default=body.es_default,
        notas=body.notas,
    )
    db.add(tasa)
    db.commit()
    db.refresh(tasa)
    return _serializar(tasa)


@router.patch("/tasas-mercado/{tasa_id}")
def actualizar_tasa(
    tasa_id: str,
    body: TasaMercadoUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tasa = db.query(TasaMercadoRef).filter(TasaMercadoRef.id == tasa_id).first()
    if not tasa:
        raise HTTPException(status_code=404, detail="Tasa no encontrada")
    for campo, valor in body.model_dump(exclude_none=True).items():
        setattr(tasa, campo, valor)
    db.commit()
    db.refresh(tasa)
    return _serializar(tasa)


@router.delete("/tasas-mercado/{tasa_id}", status_code=204)
def eliminar_tasa(
    tasa_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tasa = db.query(TasaMercadoRef).filter(TasaMercadoRef.id == tasa_id).first()
    if not tasa:
        raise HTTPException(status_code=404, detail="Tasa no encontrada")
    db.delete(tasa)
    db.commit()


@router.get("/tasas-mercado/icea-anyos-disponibles")
def listar_anyos_icea_disponibles(
    _: User = Depends(require_admin),
):
    """
    Años para los que existe una fuente ICEA real en el catálogo interno
    (app/data/tasas_mercado_icea.py) y que por tanto se pueden poblar con
    el botón "Poblar desde ICEA". No incluye años sin fuente verificada.
    """
    return sorted({t[1] for t in TASAS_ICEA}, reverse=True)


@router.post("/tasas-mercado/poblar-icea")
def poblar_tasas_icea(
    anyo: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Mismo catálogo que scripts/seed_tasas_mercado.py, pero por año y desde la
    propia pantalla: busca las tasas ICEA de ese año en app/data/tasas_mercado_icea.py
    y las inserta en tasas_mercado_ref. Si una fila (fuente, año, tipo, ramo_keyword)
    ya existe se omite, no se duplica ni se sobrescribe.
    """
    filas = [t for t in TASAS_ICEA if t[1] == anyo]
    if not filas:
        raise HTTPException(
            status_code=404,
            detail=f"No hay tasas ICEA con fuente verificada para el año {anyo} en el catálogo interno.",
        )

    insertados = 0
    omitidos = 0
    for fuente, a, tipo, keyword, tasa_pct, es_default, notas in filas:
        ya_existe = db.query(TasaMercadoRef).filter(
            TasaMercadoRef.fuente == fuente,
            TasaMercadoRef.anyo == a,
            TasaMercadoRef.tipo == TipoTasaMercado(tipo),
            TasaMercadoRef.ramo_keyword.is_(None) if keyword is None else TasaMercadoRef.ramo_keyword == keyword,
        ).first()
        if ya_existe:
            omitidos += 1
            continue
        db.add(TasaMercadoRef(
            id=uuid.uuid4(), fuente=fuente, anyo=a, tipo=TipoTasaMercado(tipo),
            ramo_keyword=keyword, tasa_pct=tasa_pct, es_default=es_default, notas=notas,
        ))
        insertados += 1

    db.commit()
    log.info("Poblar ICEA | anyo=%d insertados=%d omitidos=%d", anyo, insertados, omitidos)
    return {"insertados": insertados, "omitidos": omitidos}


@router.post("/reset-datos")
def reset_datos(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Elimina todas las cargas (diarios, recibos, apuntes, incidencias).
    Preserva: mapeo de cuentas, tasas de mercado, usuarios, meses_reales
    (solo se le desvincula la carga).

    Bug real reportado en vivo (2026-10-10), dos vueltas:
    1) Usaba TRUNCATE sobre las 4 tablas grandes a la vez, incluyendo
       cargas_contables -- Postgres lo rechaza en bloque porque
       meses_reales tiene una FK hacia cargas_contables (da igual que esa
       fila ya se haya puesto a NULL antes: TRUNCATE comprueba la
       restricción, no el valor real fila a fila). Cambiado a DELETE para
       las 4 juntas -- correcto, pero con ~230.000 filas reales (diario +
       recibos) DELETE es muchísimo más lento que TRUNCATE: borra fila a
       fila, con mantenimiento de índice y WAL por cada una.
    2) Arreglo real: solo cargas_contables (8 filas) necesita DELETE --
       es la única con un referenciador "blando" (meses_reales) que hay
       que preservar. Las otras tres (incidencias, fact_resultado_analitico,
       diario_apuntes, recibos) no las referencia nada fuera de este
       mismo grupo, así que se pueden TRUNCATE juntas sin tocar
       cargas_contables -- recupera la velocidad O(1) de TRUNCATE donde
       de verdad importa (las tablas grandes) y dejar el DELETE solo para
       la tabla pequeña, donde el coste es irrelevante.
    """
    # Conteos aproximados desde pg_stat (instantáneo, no hace full scan)
    rows = db.execute(text(
        "SELECT relname, n_live_tup::bigint FROM pg_stat_user_tables "
        "WHERE relname IN ('cargas_contables','recibos','diario_apuntes','incidencias')"
    )).fetchall()
    stats = {r[0]: int(r[1]) for r in rows}

    # meses_reales.carga_id es FK SET NULL → desvincular antes de borrar cargas_contables
    db.execute(text("UPDATE meses_reales SET carga_id = NULL WHERE carga_id IS NOT NULL"))

    # Las tablas grandes no las referencia nada fuera de este grupo -> TRUNCATE (O(1)).
    db.execute(text("TRUNCATE TABLE incidencias, fact_resultado_analitico, diario_apuntes, recibos"))
    # cargas_contables sí la referencia meses_reales (ya desvinculada arriba) -> DELETE, pero solo 8 filas.
    db.execute(text("DELETE FROM cargas_contables"))
    db.commit()

    return {
        "mensaje": "Datos eliminados correctamente",
        "cargas_eliminadas": stats.get("cargas_contables", 0),
        "recibos_eliminados": stats.get("recibos", 0),
        "apuntes_eliminados": stats.get("diario_apuntes", 0),
        "incidencias_eliminadas": stats.get("incidencias", 0),
    }


# ─────────────────────────────────────────────
# Catálogo de comisión de colaborador por auxiliar y año
# ─────────────────────────────────────────────

@router.get("/auxiliares-comision")
def listar_auxiliares_comision(
    anyo: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(AuxiliarComisionRef)
    if anyo:
        q = q.filter(AuxiliarComisionRef.anyo == anyo)
    filas = q.order_by(AuxiliarComisionRef.anyo.desc(), AuxiliarComisionRef.auxiliar).all()
    return [_serializar_auxiliar(a) for a in filas]


@router.get("/auxiliares-comision/anyos")
def listar_auxiliares_anyos(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from sqlalchemy import distinct
    anyos = db.query(distinct(AuxiliarComisionRef.anyo)).order_by(AuxiliarComisionRef.anyo.desc()).all()
    return [a[0] for a in anyos]


@router.post("/auxiliares-comision", status_code=201)
def crear_auxiliar_comision(
    body: AuxiliarComisionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    ya_existe = db.query(AuxiliarComisionRef).filter(
        AuxiliarComisionRef.anyo == body.anyo,
        AuxiliarComisionRef.auxiliar == body.auxiliar,
    ).first()
    if ya_existe:
        raise HTTPException(status_code=400, detail="Ya existe una comisión para ese auxiliar en ese año")

    fila = AuxiliarComisionRef(
        id=uuid.uuid4(), pct_retencion=calcular_pct_retencion(body.auxiliar), **body.model_dump(),
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return _serializar_auxiliar(fila)


@router.patch("/auxiliares-comision/{auxiliar_id}")
def actualizar_auxiliar_comision(
    auxiliar_id: str,
    body: AuxiliarComisionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    fila = db.query(AuxiliarComisionRef).filter(AuxiliarComisionRef.id == auxiliar_id).first()
    if not fila:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    datos = body.model_dump(exclude_none=True)
    for campo, valor in datos.items():
        setattr(fila, campo, valor)
    db.commit()
    db.refresh(fila)
    return _serializar_auxiliar(fila)


@router.delete("/auxiliares-comision/{auxiliar_id}", status_code=204)
def eliminar_auxiliar_comision(
    auxiliar_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    fila = db.query(AuxiliarComisionRef).filter(AuxiliarComisionRef.id == auxiliar_id).first()
    if not fila:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    db.delete(fila)
    db.commit()


@router.post("/auxiliares-comision/importar-csv")
async def importar_auxiliares_comision_csv(
    anyo: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Importa el catálogo de comisión de colaborador desde un CSV con columnas
    auxiliar y comisión colaborador. El año se indica en la propia opción de
    importar (no viene en el fichero) y se aplica a todas las filas. Si ya
    existe una fila para ese (año, auxiliar) se actualiza el % en vez de
    duplicarla.
    """
    import io as _io
    import unicodedata
    import pandas as pd

    contenido = await file.read()

    df = None
    for sep in [';', ',', '\t']:
        for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                candidato = pd.read_csv(_io.BytesIO(contenido), sep=sep, dtype=str, encoding=enc, keep_default_na=False)
                if len(candidato.columns) >= 2:
                    df = candidato
                    break
            except Exception:
                continue
        if df is not None:
            break

    if df is None:
        raise HTTPException(status_code=422, detail="No se pudo leer el archivo. Debe ser un CSV con columnas auxiliar y comisión colaborador.")

    df.columns = [str(c).strip() for c in df.columns]

    def _norm(s: str) -> str:
        return ''.join(
            c for c in unicodedata.normalize('NFD', s.lower())
            if unicodedata.category(c) != 'Mn'
        )

    col_norm = {_norm(c): c for c in df.columns}

    def _find(*keywords) -> Optional[str]:
        for nk, real in col_norm.items():
            if all(k in nk for k in keywords):
                return real
        return None

    auxiliar_col = _find('auxil')
    comision_col = _find('comis')

    faltantes = [n for n, c in [('auxiliar', auxiliar_col), ('comisión colaborador', comision_col)] if not c]
    if faltantes:
        raise HTTPException(status_code=422, detail=f"Columnas requeridas no encontradas: {', '.join(faltantes)}. Columnas detectadas: {list(df.columns)}")

    def _f(val) -> float:
        try:
            s = str(val or '').strip().replace(',', '.')
            return float(s) if s and s.lower() != 'nan' else 0.0
        except (ValueError, TypeError):
            return 0.0

    existentes = {
        a.auxiliar: a
        for a in db.query(AuxiliarComisionRef).filter(AuxiliarComisionRef.anyo == anyo).all()
    }

    insertados = 0
    actualizados = 0
    errores: list[str] = []

    for idx, row in df.iterrows():
        fila_n = idx + 2
        try:
            auxiliar = str(row.get(auxiliar_col, '') or '').strip()
            if not auxiliar:
                errores.append(f"Fila {fila_n}: auxiliar vacío")
                continue
            comision = _f(row.get(comision_col, 0))

            if auxiliar in existentes:
                # No toca pct_retencion: si ya existía pudo corregirse a mano
                # (la heurística no distingue S.A./S.COOP/C.B.), el CSV no trae esa columna.
                existentes[auxiliar].comision_colaborador = comision
                actualizados += 1
            else:
                nueva = AuxiliarComisionRef(
                    id=uuid.uuid4(), anyo=anyo, auxiliar=auxiliar, comision_colaborador=comision,
                    pct_retencion=calcular_pct_retencion(auxiliar),
                )
                db.add(nueva)
                existentes[auxiliar] = nueva
                insertados += 1
        except Exception as exc:
            errores.append(f"Fila {fila_n}: {exc}")

    db.commit()
    log.info(
        "Importación auxiliares-comisión | anyo=%d insertados=%d actualizados=%d errores=%d",
        anyo, insertados, actualizados, len(errores),
    )
    return {"insertados": insertados, "actualizados": actualizados, "errores": errores}
