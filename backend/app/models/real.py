from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Enum as SAEnum, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class EstadoMesReal(str, enum.Enum):
    NO_CARGADO = "no_cargado"
    CARGADO = "cargado"
    CON_INCIDENCIAS = "con_incidencias"
    VALIDADO = "validado"
    CERRADO = "cerrado"
    REABIERTO = "reabierto"


class MesReal(Base):
    """Control del estado de cada mes real cargado para un ejercicio."""
    __tablename__ = "meses_reales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    ejercicio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)  # 1-12
    estado = Column(SAEnum(EstadoMesReal), default=EstadoMesReal.NO_CARGADO)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("cargas_contables.id", ondelete="SET NULL"), nullable=True)
    cerrado_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cerrado_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DesvIngreso(Base):
    """Desviación real vs presupuesto de ingresos por dimensión y mes."""
    __tablename__ = "desv_ingresos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    mes = Column(Integer, nullable=False)
    compania = Column(String(150), nullable=True)
    ramo = Column(String(100), nullable=True)
    auxiliar = Column(String(150), nullable=True)
    tipo_negocio = Column(String(30), nullable=True)
    real = Column(Numeric(18, 2), default=0)
    presupuesto = Column(Numeric(18, 2), default=0)
    desviacion_abs = Column(Numeric(18, 2), default=0)   # real - presupuesto
    desviacion_pct = Column(Numeric(10, 4), default=0)   # desv_abs / presupuesto
    es_favorable = Column(Boolean, default=True)          # en ingresos: real > presupuesto es favorable
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DesvGasto(Base):
    """Desviación real vs presupuesto de gastos por cuenta/familia y mes."""
    __tablename__ = "desv_gastos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    mes = Column(Integer, nullable=False)
    numero_cuenta = Column(String(20), nullable=True)
    familia_gasto = Column(String(100), nullable=True)
    real = Column(Numeric(18, 2), default=0)
    presupuesto = Column(Numeric(18, 2), default=0)
    desviacion_abs = Column(Numeric(18, 2), default=0)
    desviacion_pct = Column(Numeric(10, 4), default=0)
    es_favorable = Column(Boolean, default=True)  # en gastos: real < presupuesto es favorable
    created_at = Column(DateTime(timezone=True), server_default=func.now())
