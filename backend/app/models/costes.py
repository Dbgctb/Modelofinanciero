from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Enum as SAEnum, ForeignKey, Text, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class TipoCoste(str, enum.Enum):
    FIJO = "fijo"
    VARIABLE = "variable"


class TratamientoCoste(str, enum.Enum):
    DIRECTO = "directo"
    INDIRECTO = "indirecto"
    EXCLUIDO = "excluido"


class DriverReparto(str, enum.Enum):
    COMISION_CONTABLE = "comision_contable"
    NUEVA_PRODUCCION = "nueva_produccion"
    NUMERO_POLIZAS = "numero_polizas"
    NUMERO_RECIBOS = "numero_recibos"
    MANUAL_PORCENTUAL = "manual_porcentual"


class MotivoExclusionCoste(str, enum.Enum):
    AMORTIZACION = "amortizacion"
    AJUSTE_CONTABLE = "ajuste_contable"
    EXTRAORDINARIO = "extraordinario"
    SIN_IMPACTO_CAJA = "sin_impacto_caja"
    NO_OPERATIVO = "no_operativo"
    DECISION_DIRECCION = "decision_direccion"


class EstadoCoste(str, enum.Enum):
    CLASIFICADO = "clasificado"
    PENDIENTE = "pendiente"
    IMPUTADO = "imputado"
    EXCLUIDO = "excluido"
    CON_ALERTA = "con_alerta"


# Clasificación automática predefinida por familia (REQ-028).
# Cada entrada "estándar" es la definición real; las claves de más abajo
# ("nombres reales de la correduría") son alias que apuntan al mismo dict,
# porque el familia_gasto que trae el diario real no usa los nombres
# genéricos del Mapeo de cuentas RF, sino estos (comprobado contra datos
# reales 2020-2025, el mismo problema que ya resolvía _FAMILIA_A_NATURALEZA
# en el modelo analítico). Sin estos alias, una línea real con
# familia_gasto="Alquiler" no encontraba "Alquiler y oficina" y se quedaba
# siempre en estado CON_ALERTA.
_PERSONAL = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_CESION_AUXILIAR = {"tipo": TipoCoste.VARIABLE, "tratamiento": TratamientoCoste.DIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_ALQUILER = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_TECNOLOGIA = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_SERVICIOS_PROFESIONALES = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_MARKETING = {"tipo": TipoCoste.VARIABLE, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.NUEVA_PRODUCCION}
_FINANCIERO = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_TRIBUTOS_SEGUROS = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_AMORTIZACIONES = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.EXCLUIDO, "driver": DriverReparto.COMISION_CONTABLE}
_OTROS_GASTOS = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE}
_EXTRAORDINARIOS = {"tipo": TipoCoste.FIJO, "tratamiento": TratamientoCoste.EXCLUIDO, "driver": DriverReparto.COMISION_CONTABLE}

CLASIFICACION_POR_FAMILIA = {
    # ── Nombres estándar ──
    "Personal":                 _PERSONAL,
    "Cesiones a auxiliares":    _CESION_AUXILIAR,
    "Alquiler y oficina":       _ALQUILER,
    "Tecnología y software":    _TECNOLOGIA,
    "Servicios profesionales":  _SERVICIOS_PROFESIONALES,
    "Marketing y captación":    _MARKETING,
    "Gastos financieros":       _FINANCIERO,
    "Tributos y seguros":       _TRIBUTOS_SEGUROS,
    "Amortizaciones y ajustes": _AMORTIZACIONES,
    "Otros gastos":             _OTROS_GASTOS,
    # ── Nombres reales de la correduría (familia_gasto tal cual en el diario) ──
    "Cesión Auxiliar":          _CESION_AUXILIAR,
    "Cesion Auxiliar":          _CESION_AUXILIAR,
    "Alquiler":                 _ALQUILER,
    "Renting":                  _ALQUILER,
    "Otros Servicios":          _SERVICIOS_PROFESIONALES,
    "Reparaciones":             _SERVICIOS_PROFESIONALES,
    "Seguros":                  _TRIBUTOS_SEGUROS,
    "Impuestos":                _TRIBUTOS_SEGUROS,
    "Financieros":              _FINANCIERO,
    "Relaciones Publicas":      _MARKETING,
    "Relaciones Públicas":      _MARKETING,
    "Suministros":              _OTROS_GASTOS,
    "Descuentos":               _OTROS_GASTOS,
    "Telefono":                 _OTROS_GASTOS,
    "Teléfono":                 _OTROS_GASTOS,
    "software":                 _TECNOLOGIA,
    "Software":                 _TECNOLOGIA,
    "Amortizacion":             _AMORTIZACIONES,
    "Amortización":             _AMORTIZACIONES,
    "extraordinarios":          _EXTRAORDINARIOS,
    "Extraordinarios":          _EXTRAORDINARIOS,
}


class LineaCoste(Base):
    """
    Cada línea de coste clasificada para un periodo. Se identifica por
    ejercicio+mes, no por presupuesto -- funciona con solo tener diario real
    cargado, sin necesitar que exista ningún presupuesto para ese año.
    presupuesto_id se rellena solo si existe un Presupuesto para el mismo
    ejercicio (se usa únicamente para comparar importe_real vs
    importe_presupuesto); si no existe, queda a NULL.
    """
    __tablename__ = "lineas_coste"
    __table_args__ = (
        Index('ix_lineas_coste_ejercicio_mes', 'ejercicio', 'mes'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="SET NULL"), nullable=True)
    mes = Column(Integer, nullable=False)
    ejercicio = Column(Integer, nullable=False)

    # Origen contable
    numero_cuenta = Column(String(20), nullable=True)
    descripcion_cuenta = Column(String(255), nullable=True)
    familia_gasto = Column(String(100), nullable=True)
    importe_real = Column(Numeric(18, 2), default=0)
    importe_presupuesto = Column(Numeric(18, 2), default=0)

    # Clasificación (REQ-021/022)
    tipo_coste = Column(SAEnum(TipoCoste), nullable=True)
    tratamiento = Column(SAEnum(TratamientoCoste), nullable=True)
    driver = Column(SAEnum(DriverReparto), nullable=True)
    clasificacion_automatica = Column(Boolean, default=True)  # False si el usuario la cambió

    # Exclusión
    motivo_exclusion = Column(SAEnum(MotivoExclusionCoste), nullable=True)

    # Imputación por dimensiones (resultado del reparto)
    imputacion = Column(JSON, default=dict)  # {compania: importe, ramo: importe, auxiliar: importe, ...}
    reparto_manual = Column(JSON, nullable=True)  # {dim: pct} para driver MANUAL_PORCENTUAL

    estado = Column(SAEnum(EstadoCoste), default=EstadoCoste.PENDIENTE)
    notas = Column(Text, nullable=True)
    revisado_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
