from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class TipoTasaMercado(str, enum.Enum):
    CRECIMIENTO = "crecimiento"
    CAIDA_CARTERA = "caida_cartera"
    CAIDA_NUEVA_PRODUCCION = "caida_nueva_produccion"


class TasaMercadoRef(Base):
    """
    Tasas de referencia de mercado por año, tipo y ramo.
    Sustituye a las tablas hardcodeadas en presupuesto_ingresos.py.
    El sistema usa el año más reciente disponible <= ejercicio_base.
    """
    __tablename__ = "tasas_mercado_ref"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fuente = Column(String(100), nullable=False)          # "ICEA", "UNESPA", etc.
    anyo = Column(Integer, nullable=False)                # 2024, 2025...
    tipo = Column(
        SAEnum(TipoTasaMercado, name='tipotasamercado', create_type=False,
               values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    ramo_keyword = Column(String(100), nullable=True)     # null = fila default
    tasa_pct = Column(Numeric(8, 4), nullable=False)
    es_default = Column(Boolean, default=False)           # True = se usa si no hay match por keyword
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
