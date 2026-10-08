from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class TipoIncidencia(str, enum.Enum):
    CUENTA_SIN_MAPEAR = "cuenta_sin_mapear"
    COMPANIA_NO_IDENTIFICADA = "compania_no_identificada"
    RECIBO_NO_EXTRAIDO = "recibo_no_extraido"
    RECIBO_NO_ENCONTRADO = "recibo_no_encontrado"
    RECIBO_SIN_RAMO = "recibo_sin_ramo"
    RECIBO_SIN_CARTERA = "recibo_sin_cartera"
    GASTO_SIN_FAMILIA = "gasto_sin_familia"
    PERIODO_INCORRECTO = "periodo_incorrecto"
    POSIBLE_DUPLICADO = "posible_duplicado"


INCIDENCIAS_CRITICAS = {
    TipoIncidencia.RECIBO_SIN_RAMO,
    TipoIncidencia.RECIBO_SIN_CARTERA,
    TipoIncidencia.GASTO_SIN_FAMILIA,
    TipoIncidencia.CUENTA_SIN_MAPEAR,
}


class EstadoIncidencia(str, enum.Enum):
    PENDIENTE = "pendiente"
    RESUELTA = "resuelta"
    EXCLUIDA = "excluida"


class Incidencia(Base):
    __tablename__ = "incidencias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("cargas_contables.id", ondelete="CASCADE"), nullable=False)
    apunte_id = Column(UUID(as_uuid=True), ForeignKey("diario_apuntes.id", ondelete="CASCADE"), nullable=True)
    tipo = Column(SAEnum(TipoIncidencia), nullable=False)
    es_critica = Column(String(5), default="si")
    descripcion = Column(Text, nullable=True)
    estado = Column(SAEnum(EstadoIncidencia), default=EstadoIncidencia.PENDIENTE)
    resolucion = Column(Text, nullable=True)
    resuelta_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
