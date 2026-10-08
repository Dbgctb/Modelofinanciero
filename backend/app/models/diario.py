from sqlalchemy import Column, String, Integer, Numeric, DateTime, Date, Enum as SAEnum, ForeignKey, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class TipoCuenta(str, enum.Enum):
    INGRESO = "ingreso"
    GASTO = "gasto"
    TESORERIA_EXCLUIDA = "tesoreria_excluida"
    NO_CLASIFICADA = "no_clasificada"


class EstadoApunte(str, enum.Enum):
    CORRECTO = "correcto"
    CON_INCIDENCIA = "con_incidencia"
    EXCLUIDO = "excluido"


class DiarioApunte(Base):
    __tablename__ = "diario_apuntes"
    __table_args__ = (
        # Los dos filtros más frecuentes de toda la aplicación
        Index("ix_diario_ejercicio_estado",        "ejercicio", "estado"),
        Index("ix_diario_ejercicio_recibo",        "ejercicio", "recibo_id"),
        Index("ix_diario_ejercicio_num_cuenta",    "ejercicio", "numero_cuenta"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("cargas_contables.id", ondelete="CASCADE"), nullable=False)
    ejercicio = Column(Integer, nullable=False, index=True)
    mes = Column(Integer, nullable=True)

    # Campos originales del Excel
    linea = Column(Integer, nullable=True)
    serie = Column(String(20), nullable=True)
    numero = Column(String(50), nullable=True)
    fecha = Column(Date, nullable=True)
    debe = Column(Numeric(18, 2), default=0)
    haber = Column(Numeric(18, 2), default=0)
    numero_cuenta = Column(String(20), nullable=False)
    descripcion_cuenta = Column(String(255), nullable=True)
    concepto = Column(Text, nullable=True)

    # Campos enriquecidos
    tipo_cuenta = Column(SAEnum(TipoCuenta), default=TipoCuenta.NO_CLASIFICADA, index=True)
    compania = Column(String(150), nullable=True)
    codigo_recibo = Column(String(20), nullable=True)   # extraído del concepto
    recibo_id = Column(UUID(as_uuid=True), ForeignKey("recibos.id", ondelete="SET NULL"), nullable=True)
    ramo = Column(String(100), nullable=True)
    auxiliar = Column(String(150), nullable=True)
    tipo_negocio = Column(String(30), nullable=True)    # cartera / nueva_produccion
    familia_gasto = Column(String(100), nullable=True)

    estado = Column(SAEnum(EstadoApunte), default=EstadoApunte.CON_INCIDENCIA)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
