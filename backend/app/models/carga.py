from sqlalchemy import Column, String, Integer, Numeric, DateTime, Date, Enum as SAEnum, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class TipoCarga(str, enum.Enum):
    BASE_PRESUPUESTARIA = "base_presupuestaria"
    MENSUAL_REAL = "mensual_real"
    RECIBOS = "recibos"
    HISTORICO_ESTADISTICO = "historico_estadistico"


class EstadoCarga(str, enum.Enum):
    EN_PROCESO = "en_proceso"
    CON_INCIDENCIAS = "con_incidencias"
    VALIDADO = "validado"
    CERRADO = "cerrado"


class CargaContable(Base):
    __tablename__ = "cargas_contables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=True)  # None = carga anual base
    tipo_carga = Column(SAEnum(TipoCarga), nullable=False)
    estado = Column(SAEnum(EstadoCarga), default=EstadoCarga.EN_PROCESO)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    nombre_fichero = Column(String(255), nullable=True)
    total_registros = Column(Integer, default=0)
    registros_correctos = Column(Integer, default=0)
    registros_con_incidencia = Column(Integer, default=0)
    importe_debe_total = Column(Numeric(18, 2), default=0)
    importe_haber_total = Column(Numeric(18, 2), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
