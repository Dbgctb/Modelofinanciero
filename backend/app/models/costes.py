from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Enum as SAEnum, ForeignKey, Text, JSON
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


# Clasificación automática predefinida por familia (REQ-028)
CLASIFICACION_POR_FAMILIA = {
    "Personal":                {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
    "Cesiones a auxiliares":   {"tipo": TipoCoste.VARIABLE, "tratamiento": TratamientoCoste.DIRECTO,   "driver": DriverReparto.COMISION_CONTABLE},
    "Alquiler y oficina":      {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
    "Tecnología y software":   {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
    "Servicios profesionales": {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
    "Marketing y captación":   {"tipo": TipoCoste.VARIABLE, "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.NUEVA_PRODUCCION},
    "Gastos financieros":      {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
    "Tributos y seguros":      {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
    "Amortizaciones y ajustes":{"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.EXCLUIDO,  "driver": DriverReparto.COMISION_CONTABLE},
    "Otros gastos":            {"tipo": TipoCoste.FIJO,     "tratamiento": TratamientoCoste.INDIRECTO, "driver": DriverReparto.COMISION_CONTABLE},
}


class LineaCoste(Base):
    """Cada línea de coste clasificada para un periodo y presupuesto."""
    __tablename__ = "lineas_coste"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
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
