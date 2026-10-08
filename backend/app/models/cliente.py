import enum
import uuid
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, Text, ForeignKey, JSON, Boolean, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from ..core.database import Base


class TipoCliente(str, enum.Enum):
    FISICO = "fisico"
    JURIDICO = "juridico"


class EstadoAccion(str, enum.Enum):
    PENDIENTE = "pendiente"
    CONTACTADO = "contactado"
    PROPUESTA = "propuesta"
    GANADO = "ganado"
    PERDIDO = "perdido"
    NO_INTERESADO = "no_interesado"


class TipoAccion(str, enum.Enum):
    CROSS_SELLING = "cross_selling"
    RETENCION = "retencion"


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo_cliente = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    nombre_normalizado = Column(String(200), nullable=False, index=True)
    fecha_alta = Column(Date, nullable=True)
    fecha_nacimiento = Column(Date, nullable=True)
    tipo = Column(SAEnum(TipoCliente), nullable=False, default=TipoCliente.FISICO)
    telefono_fijo = Column(String(30), nullable=True)
    telefono_movil = Column(String(30), nullable=True)
    email = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CrossSellingParametros(Base):
    """Pesos y umbrales del motor de scoring — editables desde pantalla de admin."""
    __tablename__ = "cross_selling_parametros"
    id = Column(Integer, primary_key=True)
    peso_afinidad = Column(Float, default=0.25)
    peso_propension = Column(Float, default=0.30)
    peso_valor = Column(Float, default=0.25)
    peso_timing = Column(Float, default=0.20)
    umbral_bajada_prima = Column(Float, default=0.10)
    umbral_subida_prima_riesgo = Column(Float, default=0.20)
    dias_vencimiento_urgente = Column(Integer, default=90)
    dias_vencimiento_medio = Column(Integer, default=180)
    dias_inactividad_riesgo = Column(Integer, default=540)
    matriz_afinidad = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CrossSellingOportunidad(Base):
    __tablename__ = "cross_selling_oportunidades"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio = Column(Integer, nullable=False, index=True)
    tomador = Column(String(200), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True)
    ramo_recomendado = Column(String(100), nullable=False)
    score = Column(Float, nullable=False)
    score_afinidad = Column(Float, nullable=True)
    score_propension = Column(Float, nullable=True)
    score_valor = Column(Float, nullable=True)
    score_timing = Column(Float, nullable=True)
    margen_esperado = Column(Float, nullable=True)
    prima_esperada = Column(Float, nullable=True)
    motivo = Column(Text, nullable=True)
    accion_sugerida = Column(String(100), nullable=True)
    ramos_actuales = Column(JSON, nullable=True)
    subramos_vigentes = Column(JSON, nullable=True)  # {categoria: [subramo_list]}
    n_ramos = Column(Integer, nullable=True)
    prima_total_activa = Column(Float, nullable=True)
    antiguedad_anos = Column(Float, nullable=True)
    tipo_cliente = Column(String(20), nullable=True)
    auxiliar = Column(String(150), nullable=True)
    recalculado_at = Column(DateTime(timezone=True), server_default=func.now())


class FugaAlerta(Base):
    __tablename__ = "fuga_alertas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio = Column(Integer, nullable=False, index=True)
    tomador = Column(String(200), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True)
    risk_score = Column(Float, nullable=False)
    valor_protegido = Column(Float, nullable=True)
    prioridad = Column(Float, nullable=True)
    senales = Column(JSON, nullable=True)
    accion_recomendada = Column(String(200), nullable=True)
    dias_hasta_vencimiento = Column(Integer, nullable=True)
    prima_total_activa = Column(Float, nullable=True)
    liqui_vigente = Column(Float, nullable=True)
    n_ramos = Column(Integer, nullable=True)
    antiguedad_anos = Column(Float, nullable=True)
    tipo_cliente = Column(String(20), nullable=True)
    auxiliar = Column(String(150), nullable=True)
    ramos_actuales = Column(JSON, nullable=True)
    recalculado_at = Column(DateTime(timezone=True), server_default=func.now())


class AuxiliarParticipacion(Base):
    """Marca si un auxiliar participa en las oportunidades de cross-selling."""
    __tablename__ = "auxiliar_participacion"
    auxiliar = Column(String(150), primary_key=True)
    participa = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RamoStatsEjercicio(Base):
    """Prima media y margen medio por sub-ramo y ejercicio, calculados desde recibos vigentes."""
    __tablename__ = "ramo_stats_ejercicio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ejercicio = Column(Integer, nullable=False, index=True)
    ramo = Column(String(200), nullable=False)           # sub-ramo real del dato
    ramo_categoria = Column(String(100), nullable=True)  # categoría normalizada (AUTO, HOGAR…)
    prima_media = Column(Float, nullable=False)
    margen_medio = Column(Float, nullable=False)
    n_clientes = Column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint('ejercicio', 'ramo', name='uq_ramo_stats_ej'),)


class AccionComercial(Base):
    __tablename__ = "acciones_comerciales"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(SAEnum(TipoAccion), nullable=False)
    oportunidad_id = Column(UUID(as_uuid=True), ForeignKey("cross_selling_oportunidades.id"), nullable=True)
    alerta_id = Column(UUID(as_uuid=True), ForeignKey("fuga_alertas.id"), nullable=True)
    tomador = Column(String(200), nullable=False)
    ramo_objetivo = Column(String(100), nullable=True)
    estado = Column(SAEnum(EstadoAccion), default=EstadoAccion.PENDIENTE)
    notas = Column(Text, nullable=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    margen_conseguido = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    fecha_contacto = Column(DateTime(timezone=True), nullable=True)
    fecha_cierre = Column(DateTime(timezone=True), nullable=True)
