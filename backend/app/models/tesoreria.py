from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Enum as SAEnum, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from ..core.database import Base


class ReglaCobro(str, enum.Enum):
    MISMO_MES = "mismo_mes"
    MES_SIGUIENTE = "mes_siguiente"
    DIAS_30 = "dias_30"
    DIAS_60 = "dias_60"
    MANUAL = "manual"


class ReglaPago(str, enum.Enum):
    MISMO_MES = "mismo_mes"
    MES_SIGUIENTE = "mes_siguiente"
    DIAS_30 = "dias_30"
    DIAS_60 = "dias_60"
    MANUAL = "manual"


class TipoApunteManual(str, enum.Enum):
    PRESTAMO = "prestamo"
    DISPOSICION_POLIZA = "disposicion_poliza"
    AMORTIZACION_DEUDA = "amortizacion_deuda"
    INTERESES = "intereses"
    APORTACION_SOCIOS = "aportacion_socios"
    RETIRADA_SOCIOS = "retirada_socios"
    INVERSION = "inversion"
    REGULARIZACION = "regularizacion"
    OTRO = "otro"


class TesoreriaConfig(Base):
    """Configuración de reglas de cobro/pago por compañía y familia."""
    __tablename__ = "tesoreria_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    # Para ingresos: regla por compañía
    compania = Column(String(150), nullable=True)
    regla_cobro = Column(SAEnum(ReglaCobro), default=ReglaCobro.MISMO_MES)
    # Para gastos: regla por familia
    familia_gasto = Column(String(100), nullable=True)
    regla_pago = Column(SAEnum(ReglaPago), default=ReglaPago.MISMO_MES)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TesoreriaApunteManual(Base):
    """Apuntes manuales de tesorería (préstamos, pólizas, aportaciones…)."""
    __tablename__ = "tesoreria_apuntes_manuales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(SAEnum(TipoApunteManual), nullable=False)
    concepto = Column(String(255), nullable=False)
    mes = Column(Integer, nullable=False)  # 1-12
    importe_debe = Column(Numeric(18, 2), default=0)   # salida de caja
    importe_haber = Column(Numeric(18, 2), default=0)  # entrada de caja
    notas = Column(Text, nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TesoreriaEmpleado(Base):
    """Empleado con parámetros SS e IRPF para el cálculo de pagos netos en tesorería."""
    __tablename__ = "tesoreria_empleados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(150), nullable=False)
    numero_cuenta = Column(String(20), nullable=True)   # ej. 6400000001
    es_autonomo = Column(Boolean, default=False)
    pct_ss = Column(Numeric(6, 4), default=6.47)        # % SS empleado (0 si autónomo)
    pct_irpf = Column(Numeric(6, 4), default=0)         # % retención IRPF
    num_pagas = Column(Integer, default=14, server_default='14', nullable=False)
    salario_bruto_anual = Column(Numeric(18, 2), default=0)
    importes_brutos_mensuales = Column(JSON, default=list)  # 12 meses base year
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TesoreriaResultado(Base):
    """Resultado mensual de tesorería presupuestada (calculado)."""
    __tablename__ = "tesoreria_resultados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presupuesto_id = Column(UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False, unique=True)
    caja_inicial = Column(Numeric(18, 2), default=0)
    caja_minima = Column(Numeric(18, 2), nullable=True)
    # Arrays JSON de 12 posiciones (índice 0 = enero)
    cobros_mensuales = Column(JSON, default=list)
    pagos_mensuales = Column(JSON, default=list)
    entradas_manuales = Column(JSON, default=list)
    salidas_manuales = Column(JSON, default=list)
    flujo_mensual = Column(JSON, default=list)      # cobros - pagos + entradas - salidas
    caja_final_mensual = Column(JSON, default=list) # acumulado encadenado
    alertas = Column(JSON, default=list)            # meses con caja < mínima
    irpf_trimestral = Column(JSON, default=list)   # pagos mod-111 Q1-Q4
    aprobado = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
