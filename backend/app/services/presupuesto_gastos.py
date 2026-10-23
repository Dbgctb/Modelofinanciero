"""
Servicio de presupuestación de gastos.
RF-GAS-01 a RF-GAS-21
"""
from decimal import Decimal
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..models.presupuesto import (
    Presupuesto, PresupuestoGasto, TipoReglaGasto, DistribucionGasto,
    PresupuestoCesionAuxiliar, PresupuestoIngreso,
)
from ..models.diario import DiarioApunte, TipoCuenta, EstadoApunte
from ..models.auxiliares import AuxiliarComisionRef

MESES = list(range(1, 13))


def _safe_div(a: float, b: float) -> float:
    return (a / b) if b else 0.0


def calcular_base_gastos(db: Session, ejercicio_base: int) -> List[Dict]:
    """
    RF-GAS-01/04: agrupa gastos del ejercicio base por cuenta y familia.
    Calcula totales anuales y estacionalidad.
    """
    # Gastos 2025 = diario de cuentas que empiezan por '6'
    apuntes = db.query(DiarioApunte).filter(
        DiarioApunte.ejercicio == ejercicio_base,
        DiarioApunte.numero_cuenta.like('6%'),
        DiarioApunte.estado != EstadoApunte.EXCLUIDO,
    ).all()

    grupos: Dict[str, Dict] = {}
    for ap in apuntes:
        clave = ap.numero_cuenta or 'SIN_CUENTA'
        if clave not in grupos:
            grupos[clave] = {
                'numero_cuenta': ap.numero_cuenta,
                'descripcion_cuenta': ap.descripcion_cuenta,
                'familia_gasto': ap.familia_gasto or 'Otros gastos',
                'por_mes': {m: 0.0 for m in MESES},   # importes con mes conocido
                'sin_mes': 0.0,                          # importes sin fecha (se reparten linealmente)
                'total': 0.0,
            }
        importe = float(ap.debe - ap.haber)  # gastos en el debe
        if ap.mes and 1 <= ap.mes <= 12:
            grupos[clave]['por_mes'][ap.mes] += importe
        else:
            grupos[clave]['sin_mes'] += importe
        grupos[clave]['total'] += importe

    resultado = []
    for g in grupos.values():
        total = g['total']
        sin_mes = g['sin_mes']
        # Parte sin fecha se distribuye linealmente entre los 12 meses
        lineal_por_mes = sin_mes / 12.0
        # Estacionalidad = (importe_mes_conocido + reparto_lineal) / total
        if total:
            estacionalidad = [
                round(_safe_div(g['por_mes'][m] + lineal_por_mes, total), 6)
                for m in MESES
            ]
        else:
            estacionalidad = [round(1 / 12, 6)] * 12
        # Ajuste de redondeo para que sumen exactamente 1.0
        diff = round(1.0 - sum(estacionalidad), 6)
        estacionalidad[11] = round(estacionalidad[11] + diff, 6)

        resultado.append({
            'numero_cuenta': g['numero_cuenta'],
            'descripcion_cuenta': g['descripcion_cuenta'],
            'familia_gasto': g['familia_gasto'],
            'gasto_base_anual': total,
            'por_mes': g['por_mes'],
            'estacionalidad': estacionalidad,
        })

    return sorted(resultado, key=lambda x: (x['familia_gasto'], x['numero_cuenta'] or ''))


def aplicar_regla(
    gasto_base_anual: float,
    estacionalidad: List[float],
    por_mes: Dict[int, float],
    tipo_regla: TipoReglaGasto,
    porcentaje_variacion: Optional[float],
    mes_inicio_variacion: Optional[int],
    importe_anual_manual: Optional[float],
    distribucion: DistribucionGasto,
) -> List[float]:
    """
    RF-GAS-07 a RF-GAS-16: calcula los 12 importes mensuales según la regla.
    """
    if tipo_regla == TipoReglaGasto.EXCLUIR:
        return [0.0] * 12

    if tipo_regla == TipoReglaGasto.MANTENER:
        # RF-GAS-07: mantener el gasto real del ejercicio base
        return _distribuir(gasto_base_anual, estacionalidad, por_mes, distribucion)

    if tipo_regla == TipoReglaGasto.IPC:
        # RF-GAS-09/11: aplicar porcentaje desde un mes concreto
        pct = (porcentaje_variacion or 0) / 100
        mes_inicio = mes_inicio_variacion or 1
        base_mensual = _distribuir(gasto_base_anual, estacionalidad, por_mes, distribucion)
        resultado = []
        for i, imp in enumerate(base_mensual):
            mes = i + 1
            if mes >= mes_inicio:
                resultado.append(round(imp * (1 + pct), 2))
            else:
                resultado.append(round(imp, 2))
        return resultado

    if tipo_regla in (TipoReglaGasto.IMPORTE_ANUAL, TipoReglaGasto.NUEVO):
        # RF-GAS-12/15: importe anual definido manualmente + distribución
        total = importe_anual_manual or 0.0
        return _distribuir(total, estacionalidad, por_mes, distribucion)

    return [0.0] * 12


def _distribuir(
    total: float,
    estacionalidad: List[float],
    por_mes: Dict[int, float],
    distribucion: DistribucionGasto,
) -> List[float]:
    if distribucion == DistribucionGasto.LINEAL:
        mensual = round(total / 12, 2)
        # Ajuste céntimo para que sume exacto
        base = [mensual] * 12
        diferencia = round(total - sum(base), 2)
        base[11] = round(base[11] + diferencia, 2)
        return base
    # ESTACIONALIDAD por defecto
    result = [round(total * w, 2) for w in estacionalidad]
    diferencia = round(total - sum(result), 2)
    result[11] = round(result[11] + diferencia, 2)
    return result


def generar_lineas_gastos(db: Session, presupuesto: Presupuesto) -> int:
    """
    RF-GAS-01/04: genera las líneas de presupuesto de gastos desde el ejercicio base.
    """
    db.query(PresupuestoGasto).filter(
        PresupuestoGasto.presupuesto_id == presupuesto.id,
        PresupuestoGasto.bloqueado == False,
        PresupuestoGasto.es_gasto_nuevo == False,
    ).delete()

    base = calcular_base_gastos(db, presupuesto.ejercicio_base)
    creadas = 0

    for item in base:
        # Distribución LINEAL por defecto: el 2025 se cargó como una única
        # carga anual, por lo que el campo `mes` no refleja la distribución
        # mensual real del negocio (64% de apuntes sin mes). Las cuentas 640*
        # (nóminas) ya reciben distribución uniforme porque tienen mes=NULL;
        # aplicar LINEAL a todas garantiza coherencia con los ingresos.
        importes = aplicar_regla(
            gasto_base_anual=item['gasto_base_anual'],
            estacionalidad=item['estacionalidad'],
            por_mes=item['por_mes'],
            tipo_regla=TipoReglaGasto.MANTENER,
            porcentaje_variacion=None,
            mes_inicio_variacion=None,
            importe_anual_manual=None,
            distribucion=DistribucionGasto.LINEAL,
        )
        linea = PresupuestoGasto(
            presupuesto_id=presupuesto.id,
            numero_cuenta=item['numero_cuenta'],
            descripcion_cuenta=item['descripcion_cuenta'],
            familia_gasto=item['familia_gasto'],
            gasto_base_anual=item['gasto_base_anual'],
            estacionalidad=item['estacionalidad'],
            tipo_regla=TipoReglaGasto.MANTENER,
            distribucion=DistribucionGasto.LINEAL,
            importes_mensuales=importes,
            importes_manuales=[None] * 12,
            total_anual=round(sum(importes), 2),
        )
        db.add(linea)
        creadas += 1

    db.commit()
    return creadas


def recalcular_linea_gasto(db: Session, linea: PresupuestoGasto) -> PresupuestoGasto:
    """Recalcula importes de una línea tras cambio de regla."""
    base = float(linea.gasto_base_anual or 0)
    estac = linea.estacionalidad or [round(1/12, 6)] * 12
    # Reconstruir por_mes a partir de los pesos reales almacenados en estacionalidad
    por_mes = {m: estac[m - 1] * base for m in MESES}
    importes = aplicar_regla(
        gasto_base_anual=base,
        estacionalidad=estac,
        por_mes=por_mes,
        tipo_regla=linea.tipo_regla,
        porcentaje_variacion=float(linea.porcentaje_variacion) if linea.porcentaje_variacion else None,
        mes_inicio_variacion=linea.mes_inicio_variacion,
        importe_anual_manual=float(linea.importe_anual_manual) if linea.importe_anual_manual else None,
        distribucion=linea.distribucion,
    )
    linea.importes_mensuales = importes
    linea.total_anual = round(sum(importes), 2)
    db.commit()
    db.refresh(linea)
    return linea


def generar_cesiones_auxiliar(db: Session, presupuesto: Presupuesto) -> int:
    """
    Genera/actualiza las filas de cesiones de auxiliares a partir del
    presupuesto de ingresos. Solo considera líneas con auxiliar informado.
    Mantiene los parámetros (tipo, pct_comision, pct_retencion) ya configurados.
    """
    # Leer ingresos presupuestados con auxiliar
    lineas_ingreso = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == presupuesto.id,
        PresupuestoIngreso.auxiliar.isnot(None),
        PresupuestoIngreso.auxiliar != '',
        PresupuestoIngreso.auxiliar != 'Sin auxiliar',
    ).all()

    # Agrupar por auxiliar → suma de totales e importes mensuales
    grupos: Dict[str, Dict] = {}
    for l in lineas_ingreso:
        aux = l.auxiliar
        if aux not in grupos:
            grupos[aux] = {'total': 0.0, 'mensuales': [0.0] * 12}
        grupos[aux]['total'] += float(l.total_anual or 0)
        for i, imp in enumerate(l.importes_mensuales or []):
            if i < 12:
                grupos[aux]['mensuales'][i] += float(imp or 0)

    # Cargar cesiones ya existentes para preservar parámetros
    existentes = {
        c.auxiliar: c
        for c in db.query(PresupuestoCesionAuxiliar).filter(
            PresupuestoCesionAuxiliar.presupuesto_id == presupuesto.id
        ).all()
    }

    creadas = 0
    auxiliares_nuevos = set(grupos.keys()) - set(existentes.keys())

    # Catálogo de % comisión y % retención por auxiliar para el año del presupuesto
    # (Administración → Auxiliares). Se aplica tanto a las cesiones nuevas como a las
    # ya existentes que todavía no tengan el % configurado (0 y, para comisión, sin
    # override manual), para que cargar/editar el catálogo y pulsar "Sincronizar desde
    # ingresos" también las rellene. Nunca pisa una cesión bloqueada ni un % ya
    # configurado (a mano o porque ya se sincronizó antes con un valor >0).
    catalogo = {
        c.auxiliar: {'comision': float(c.comision_colaborador), 'retencion': float(c.pct_retencion)}
        for c in db.query(AuxiliarComisionRef).filter(
            AuxiliarComisionRef.anyo == presupuesto.ejercicio,
            AuxiliarComisionRef.auxiliar.in_(grupos.keys()),
        ).all()
    }

    for aux in auxiliares_nuevos:
        cat = catalogo.get(aux, {})
        c = PresupuestoCesionAuxiliar(
            presupuesto_id=presupuesto.id,
            auxiliar=aux,
            pct_comision=cat.get('comision', 0),
            pct_retencion=cat.get('retencion', 0),
            importes_mensuales=[0.0] * 12,
        )
        db.add(c)
        existentes[aux] = c
        creadas += 1

    # Flush para que los nuevos objetos tengan ID y se puedan actualizar
    db.flush()

    for aux, cat in catalogo.items():
        c = existentes.get(aux)
        if not c or c.bloqueado:
            continue
        if float(c.pct_comision or 0) == 0 and c.gasto_comision_manual is None:
            c.pct_comision = cat['comision']
        if float(c.pct_retencion or 0) == 0:
            c.pct_retencion = cat['retencion']

    # Actualizar totales e importes calculados en todos usando los importes de INGRESO
    for aux, g in grupos.items():
        c = existentes[aux]
        pct_c = float(c.pct_comision or 0)
        c.total_ingreso_base = round(g['total'], 2)
        c.gasto_comision_total = round(g['total'] * pct_c / 100, 2)
        # Importes mensuales del GASTO = % comisión aplicado sobre importes del INGRESO
        c.importes_mensuales = [round(imp * pct_c / 100, 2) for imp in g['mensuales']]

    db.commit()
    return len(grupos)


def recalcular_cesion(db: Session, cesion: PresupuestoCesionAuxiliar) -> PresupuestoCesionAuxiliar:
    """
    Recalcula gasto_comision_total e importes_mensuales tras cambio de parámetros.
    Siempre relee los importes del presupuesto de ingresos para evitar doble aplicación
    del porcentaje sobre importes ya calculados.
    """
    pct_c = float(cesion.pct_comision or 0)

    # Releer la distribución mensual del INGRESO presupuestado para este auxiliar
    lineas_ingreso = db.query(PresupuestoIngreso).filter(
        PresupuestoIngreso.presupuesto_id == cesion.presupuesto_id,
        PresupuestoIngreso.auxiliar == cesion.auxiliar,
    ).all()

    ingreso_mensuales = [0.0] * 12
    total_ingreso = 0.0
    for l in lineas_ingreso:
        total_ingreso += float(l.total_anual or 0)
        for i, imp in enumerate(l.importes_mensuales or []):
            if i < 12:
                ingreso_mensuales[i] += float(imp or 0)

    if total_ingreso == 0.0:
        gasto_total = 0.0
        gasto_mensuales = [0.0] * 12
    elif cesion.gasto_comision_manual is not None:
        # Override manual: distribuir el importe fijo proporcionalmente al ingreso mensual
        gasto_total = float(cesion.gasto_comision_manual)
        gasto_mensuales = [
            round(imp / total_ingreso * gasto_total, 2) for imp in ingreso_mensuales
        ]
    else:
        gasto_total = round(total_ingreso * pct_c / 100, 2)
        gasto_mensuales = [round(imp * pct_c / 100, 2) for imp in ingreso_mensuales]

    cesion.total_ingreso_base = round(total_ingreso, 2)
    cesion.gasto_comision_total = gasto_total
    cesion.importes_mensuales = gasto_mensuales
    db.commit()
    db.refresh(cesion)
    return cesion


def ajuste_manual_mes(
    db: Session,
    linea: PresupuestoGasto,
    mes: int,
    nuevo_importe: float,
    mantener_total: bool,
    usuario: str,
    motivo: str,
):
    """
    RF-GAS-17/19: ajuste manual de un mes con trazabilidad completa.
    Si mantener_total=True, redistribuye la diferencia en los meses restantes.
    """
    manuales = list(linea.importes_manuales or linea.importes_mensuales)
    calculados = list(linea.importes_mensuales)

    antes = manuales[mes - 1]
    diferencia = nuevo_importe - (antes if antes is not None else calculados[mes - 1])
    manuales[mes - 1] = nuevo_importe

    if mantener_total:
        otros = [i for i in range(12) if i != mes - 1 and manuales[i] is not None]
        if otros:
            ajuste_por_mes = round(-diferencia / len(otros), 2)
            for i in otros:
                manuales[i] = round((manuales[i] or 0) + ajuste_por_mes, 2)

    linea.importes_manuales = manuales
    total = sum(v if v is not None else calculados[i] for i, v in enumerate(manuales))
    linea.total_anual = round(total, 2)

    historial = list(linea.ajustes_historial or [])
    historial.append({
        'mes': mes,
        'antes': antes,
        'despues': nuevo_importe,
        'mantener_total': mantener_total,
        'usuario': usuario,
        'fecha': datetime.now(timezone.utc).isoformat(),
        'motivo': motivo,
    })
    linea.ajustes_historial = historial
    db.commit()
    db.refresh(linea)
    return linea


def importar_cesiones_excel(db: Session, presupuesto: Presupuesto, contenido: bytes) -> dict:
    """
    Importa parámetros de cesiones desde Excel.
    Aplica automáticamente 15% de retención a físicos si no se especifica.
    Crea cesiones nuevas si el auxiliar no existe todavía.
    """
    import io as _io
    import unicodedata
    import pandas as pd
    from ..models.presupuesto import TipoPersonaAuxiliar

    df = pd.read_excel(_io.BytesIO(contenido), dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]

    # Búsqueda de columnas tolerante a acentos y mayúsculas
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
    tipo_col = _find('tipo')
    comision_col = _find('comis')
    retencion_col = _find('reten')

    if not auxiliar_col:
        raise ValueError("Columna 'Auxiliar' requerida no encontrada")

    def _f(val) -> float:
        try:
            s = str(val or '').strip().replace(',', '.')
            return float(s) if s and s.lower() != 'nan' else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _row(row, col: Optional[str], default=0):
        if col is None:
            return default
        return row.get(col, default)

    existentes = {
        c.auxiliar: c
        for c in db.query(PresupuestoCesionAuxiliar).filter(
            PresupuestoCesionAuxiliar.presupuesto_id == presupuesto.id
        ).all()
    }

    actualizadas = 0
    errores: List[str] = []

    for idx, row in df.iterrows():
        try:
            auxiliar = str(_row(row, auxiliar_col, '') or '').strip()
            if not auxiliar:
                errores.append(f"Fila {idx + 2}: auxiliar vacío")
                continue

            if auxiliar not in existentes:
                c = PresupuestoCesionAuxiliar(
                    presupuesto_id=presupuesto.id,
                    auxiliar=auxiliar,
                    pct_comision=0,
                    pct_retencion=0,
                    importes_mensuales=[0.0] * 12,
                )
                db.add(c)
                db.flush()
                existentes[auxiliar] = c

            c = existentes[auxiliar]
            if c.bloqueado:
                errores.append(f"Fila {idx + 2}: '{auxiliar}' está bloqueado")
                continue

            tipo_raw = str(_row(row, tipo_col, '') or '').strip().lower()
            if 'fis' in tipo_raw:
                c.tipo_persona = TipoPersonaAuxiliar.FISICO
            elif 'jur' in tipo_raw:
                c.tipo_persona = TipoPersonaAuxiliar.JURIDICO

            c.pct_comision = _f(_row(row, comision_col, 0))

            retencion_raw = _f(_row(row, retencion_col, 0))
            if retencion_raw > 0:
                c.pct_retencion = retencion_raw
            elif c.tipo_persona == TipoPersonaAuxiliar.FISICO:
                c.pct_retencion = 15.0
            else:
                c.pct_retencion = 0.0

            recalcular_cesion(db, c)
            actualizadas += 1
        except Exception as exc:
            errores.append(f"Fila {idx + 2}: {exc}")

    db.commit()
    return {'actualizadas': actualizadas, 'errores': errores}
