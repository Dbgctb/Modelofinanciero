from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Enum as SAEnum, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class EstadoPresupuesto(str, enum.Enum):
    BORRADOR = "borrador"
    INGRESOS_APROBADOS = "ingresos_aprobados"
    GASTOS_APROBADOS = "gastos_aprobados"
    TESORERIA_APROBADA = "tesoreria_aprobada"
    CERRADO = "cerrado"


class TipoReglaGasto(str, enum.Enum):
    MANTENER = "mantener"
    IPC = "ipc"
    IMPORTE_ANUAL = "importe_anual"
    EXCLUIR = "excluir"
    NUEVO = "nuevo"


class DistribucionGasto(str, enum.Enum):
    ESTACIONALIDAD = "estacionalidad"
    LINEAL = "lineal"
    MANUAL = "manual"


class Presupuesto(Base):
    __tablename__ = "presupuestos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio = Column(Integer, nullable=False, unique=True)
    ejercicio_base = Column(Integer, nullable=False)   # ejercicio anterior cerrado
    estado = Column(SAEnum(EstadoPresupuesto), default=EstadoPresupuesto.BORRADOR)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ingresos_aprobados_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ingresos_aprobados_at = Column(DateTime(timezone=True), nullable=True)
    gastos_aprobados_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    gastos_aprobados_at = Column(DateTime(timezone=True), nullable=True)
    cerrado_por_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cerrado_at = Column(DateTime(timezone=True), nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PresupuestoIngreso(Base):
    """Una línea de presupuesto de ingresos por dimensión (compañía + ramo + auxiliar + tipo_negocio)."""
    __tablename__ = "presupuesto_ingresos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)

    # Dimensiones
    compania = Column(String(150), nullable=True)
    ramo = Column(String(100), nullable=True)
    auxiliar = Column(String(150), nullable=True)
    tipo_negocio = Column(String(30), nullable=True)   # cartera / nueva_produccion / sin_auxiliar

    # Base del ejercicio cerrado
    ingreso_base_anual = Column(Numeric(18, 2), default=0)
    tiene_atipicos = Column(Boolean, default=False)
    atipicos_excluidos = Column(Numeric(18, 2), default=0)
    ingreso_base_limpio = Column(Numeric(18, 2), default=0)  # base sin atípicos

    # Estacionalidad mensual (pesos, suman 1.0)
    estacionalidad = Column(JSON, default=list)   # lista de 12 floats [0.08, 0.07, ...]

    # Tasa de caída por anulaciones (% sobre base limpia, mejores prácticas ICEA)
    tasa_caida = Column(Numeric(6, 4), default=0)             # % anulaciones esperadas

    # Crecimiento (aplica sobre base superviviente = base_limpia * (1 - tasa_caida/100))
    crecimiento_modelo = Column(Numeric(8, 4), default=0)     # % estadístico propio
    crecimiento_mercado = Column(Numeric(8, 4), default=0)    # % referencia mercado
    coeficiente_prudencia = Column(Numeric(6, 4), default=1)  # ajuste mercado
    crecimiento_manual = Column(Numeric(8, 4), nullable=True) # sobrescribe todo si se informa
    crecimiento_final = Column(Numeric(8, 4), default=0)      # aplicado realmente

    # Importes mensuales presupuestados (lista de 12)
    importes_mensuales = Column(JSON, default=list)
    total_anual = Column(Numeric(18, 2), default=0)

    # Trazabilidad del modelo estadístico usado al generar
    metodo_modelo = Column(String(60), nullable=True)

    # Estado
    bloqueado = Column(Boolean, default=False)   # True tras aprobación
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TipoPersonaAuxiliar(str, enum.Enum):
    FISICO = "fisico"
    JURIDICO = "juridico"


class PresupuestoCesionAuxiliar(Base):
    """Parámetros de comisión por auxiliar para calcular el gasto de cesión."""
    __tablename__ = "presupuesto_cesiones_auxiliar"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)

    auxiliar = Column(String(150), nullable=False)
    tipo_persona = Column(SAEnum(TipoPersonaAuxiliar), nullable=True)
    pct_comision = Column(Numeric(8, 4), default=0)       # % sobre el ingreso presupuestado
    pct_retencion = Column(Numeric(8, 4), default=0)      # % IRPF (físicos)

    # Override manual: si se especifica, prevalece sobre el cálculo por %
    gasto_comision_manual = Column(Numeric(18, 2), nullable=True)

    # Importes calculados (se recalculan al cambiar parámetros)
    total_ingreso_base = Column(Numeric(18, 2), default=0)   # ingreso presupuestado del auxiliar
    gasto_comision_total = Column(Numeric(18, 2), default=0) # = total_ingreso * pct_comision/100 (o manual)
    importes_mensuales = Column(JSON, default=list)           # 12 importes mensuales del gasto

    bloqueado = Column(Boolean, default=False)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PresupuestoGasto(Base):
    """Una línea de presupuesto de gastos por cuenta contable."""
    __tablename__ = "presupuesto_gastos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)

    numero_cuenta = Column(String(20), nullable=True)
    descripcion_cuenta = Column(String(255), nullable=True)
    familia_gasto = Column(String(100), nullable=False)
    es_gasto_nuevo = Column(Boolean, default=False)

    # Base del ejercicio cerrado
    gasto_base_anual = Column(Numeric(18, 2), default=0)
    estacionalidad = Column(JSON, default=list)  # 12 pesos

    # Regla de proyección
    tipo_regla = Column(SAEnum(TipoReglaGasto), default=TipoReglaGasto.MANTENER)
    porcentaje_variacion = Column(Numeric(8, 4), nullable=True)  # para regla IPC
    mes_inicio_variacion = Column(Integer, nullable=True)         # mes desde el que aplica (1-12)
    importe_anual_manual = Column(Numeric(18, 2), nullable=True)  # para regla IMPORTE_ANUAL
    distribucion = Column(SAEnum(DistribucionGasto), default=DistribucionGasto.ESTACIONALIDAD)
    motivo_exclusion = Column(String(255), nullable=True)

    # Importes finales
    importes_mensuales = Column(JSON, default=list)  # 12 importes calculados
    importes_manuales = Column(JSON, default=list)   # 12 importes ajustados manualmente (sobreescribe)
    total_anual = Column(Numeric(18, 2), default=0)

    # Trazabilidad de ajustes manuales
    ajustes_historial = Column(JSON, default=list)  # [{mes, antes, despues, usuario, fecha, motivo}]

    bloqueado = Column(Boolean, default=False)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
