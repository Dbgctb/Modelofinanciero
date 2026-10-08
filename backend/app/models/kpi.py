from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Enum as SAEnum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class SemaforoColor(str, enum.Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"


class UmbralKPI(Base):
    """Umbrales configurables por KPI para el semáforo verde/amarillo/rojo."""
    __tablename__ = "umbrales_kpi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_codigo = Column(String(50), unique=True, nullable=False)
    umbral_verde = Column(Numeric(10, 4), nullable=False)    # >= verde
    umbral_amarillo = Column(Numeric(10, 4), nullable=False)  # >= amarillo < verde
    # < amarillo = rojo
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ResultadoKPI(Base):
    """Resultado calculado de cada KPI por presupuesto y mes."""
    __tablename__ = "resultados_kpi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    mes = Column(Integer, nullable=True)     # None = acumulado anual
    kpi_codigo = Column(String(50), nullable=False)
    kpi_nombre = Column(String(150), nullable=False)
    valor = Column(Numeric(18, 4), nullable=True)
    semaforo = Column(SAEnum(SemaforoColor), nullable=True)
    dimension = Column(String(150), nullable=True)  # compañía / ramo / auxiliar (para KPIs dimensionados)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
