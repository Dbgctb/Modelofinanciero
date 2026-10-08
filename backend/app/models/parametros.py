"""
Tablas de parametrización: qué cuenta contable es ingreso/gasto y de qué compañía/familia.
El administrador las configura una vez; el sistema las usa en cada carga automáticamente.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class TipoCuentaParam(str, enum.Enum):
    INGRESO = "ingreso"
    GASTO = "gasto"
    TESORERIA_EXCLUIDA = "tesoreria_excluida"


class MapCuentaContable(Base):
    __tablename__ = "map_cuentas_contables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Puede ser cuenta exacta (7600001) o prefijo (760) — se busca más específico primero
    numero_cuenta = Column(String(20), unique=True, nullable=False, index=True)
    tipo = Column(SAEnum(TipoCuentaParam), nullable=False)
    compania = Column(String(150), nullable=True)        # solo si tipo=INGRESO
    familia_gasto = Column(String(100), nullable=True)   # solo si tipo=GASTO
    descripcion = Column(String(255), nullable=True)
    # Marca explícita para excluir del cálculo de tesorería (amortizaciones, ajustes…)
    excluir_tesoreria = Column(Boolean, default=False, nullable=False)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
