"""
Modelos del Modelo Analítico de Rentabilidad.
Tablas: analitico_map_cuentas, analitico_map_drivers, fact_resultado_analitico
"""
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from ..core.database import Base


NATURALEZAS = [
    "Personal",
    "Alquiler",
    "Tecnología",
    "Marketing",
    "Financiero",
    "Bancos",
    "Servicios profesionales",
    "Comunicaciones",
    "Viajes",
    "Impuestos",
    "Seguros",
    "Suministros",
    "Cesión auxiliar",
]

# POLIZAS: cada póliza pesa lo mismo, tenga 1 recibo (anual) o 12 (mensual). Con
# RECIBOS una póliza mensual absorbía 12 veces más coste de gestión: en 2025 Salud
# (Asistencia Sanitaria) era el 30,8% de los recibos pero el 5,9% de las pólizas y
# el 5,4% de la comisión, y recibía 52.236 € de Personal sobre 23.976 € de comisión.
DRIVERS = ["RECIBOS", "POLIZAS", "COMISION_NETA", "NUEVA_PRODUCCION"]

# Peso de una póliza INTERMEDIADA (con auxiliar) frente a una DIRECTA (1,0) en el
# driver POLIZAS: el auxiliar hace parte de la gestión con el cliente, así que
# consume menos tiempo de la correduría. Calibrado con datos 2025 para que el
# negocio directo no supere un 30% de margen EBITDA normalizado (decisión del
# usuario 2026-10-27): con 1,0 salía un 58,3%; con 0,49 sale un 29,4%
# (≈ 63 € de gestión por póliza directa y 31 € por intermediada).
PESO_POLIZA_INTERMEDIADA = 0.49

# Driver por defecto para cada naturaleza (revisión con datos 2025, decisión del
# usuario 2026-10-26): gestión → POLIZAS; estructura → COMISION_NETA.
DRIVERS_DEFAULT: dict[str, str] = {
    "Personal":               "POLIZAS",
    "Alquiler":               "COMISION_NETA",
    "Tecnología":             "RECIBOS",
    "Marketing":              "NUEVA_PRODUCCION",
    # Comisiones bancarias (626): el 95,6% de los recibos los cobra la compañía, no
    # el banco de la correduría; es coste de estructura, no de volumen de recibos.
    "Financiero":             "COMISION_NETA",
    "Bancos":                 "RECIBOS",
    "Servicios profesionales":"POLIZAS",
    "Comunicaciones":         "POLIZAS",
    "Viajes":                 "COMISION_NETA",
    "Impuestos":              "COMISION_NETA",
    "Seguros":                "COMISION_NETA",
    "Suministros":            "COMISION_NETA",
    "Cesión auxiliar":        "COMISION_NETA",
}

# Naturalezas que forman los costes operativos (L4) — todo excepto Marketing y Cesión
NATURALEZAS_COSTE_OP = {
    "Personal", "Alquiler", "Tecnología", "Financiero",
    "Bancos", "Servicios profesionales", "Comunicaciones",
    "Viajes", "Impuestos", "Seguros", "Suministros",
}

# Gastos financieros (intereses, cuentas 66*): van DEBAJO del EBITDA, igual que en
# la Cuenta de Resultados del presupuesto (EBITDA → amort. → EBIT → financieros → BAI).
# El recálculo les asigna esta naturaleza por cuenta, con independencia del mapeo
# (la naturaleza "Financiero" del mapeo también agrupa las comisiones bancarias 626,
# que sí son gasto operativo). No está en NATURALEZAS_COSTE_OP, así que _calc_pl no
# la cuenta en el EBITDA. Decisión del usuario 2026-10-25.
NATURALEZA_RESULTADO_FINANCIERO = "Resultado financiero"
PREFIJOS_RESULTADO_FINANCIERO = ("66",)


class AnaliticoMapCuenta(Base):
    """Mapeo cuenta contable → naturaleza económica (del modelo analítico)."""
    __tablename__ = "analitico_map_cuentas"

    numero_cuenta = Column(String(20), primary_key=True)
    naturaleza = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AnaliticoMapDriver(Base):
    """Mapeo naturaleza económica → driver de reparto."""
    __tablename__ = "analitico_map_drivers"

    naturaleza = Column(String(100), primary_key=True)
    driver = Column(String(50), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AnaliticoAjusteCoste(Base):
    """
    Reclasificación manual de coste: extrae un importe del pool indirecto de una cuenta
    (ej. 640 Personal, 642 SS) y lo asigna como coste directo a un auxiliar concreto.
    Caso típico: sueldo de un trabajador adscrito a un colaborador específico.
    """
    __tablename__ = "analitico_ajustes_coste"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio       = Column(Integer, nullable=False, index=True)
    auxiliar        = Column(String(150), nullable=False)
    numero_cuenta   = Column(String(20), nullable=False)   # prefijo: '640', '642', …
    descripcion     = Column(String(255), nullable=False)
    importe_mensual = Column(Numeric(14, 2), nullable=False, default=0)
    activo          = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FactResultadoAnalitico(Base):
    """Tabla resultado analítico (persistente, recalculable por ejercicio)."""
    __tablename__ = "fact_resultado_analitico"
    __table_args__ = (
        # Cubre las queries más frecuentes: GROUP BY tipo_cuenta, naturaleza WHERE ejercicio=X
        Index("ix_fact_ejercicio_tipo_nat",   "ejercicio", "tipo_cuenta", "naturaleza"),
        # Cubre el JOIN con recibos en rentabilidad_cliente
        Index("ix_fact_ejercicio_recibo",     "ejercicio", "recibo_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio = Column(Integer, nullable=False, index=True)
    mes = Column(Integer, nullable=True)
    fecha = Column(Date, nullable=True)

    # Origen contable
    apunte_id = Column(UUID(as_uuid=True), ForeignKey("diario_apuntes.id", ondelete="SET NULL"), nullable=True)
    numero_cuenta = Column(String(20), nullable=True)
    descripcion_cuenta = Column(String(255), nullable=True)

    # Clasificación analítica
    tipo_cuenta = Column(String(20), nullable=True, index=True)
    naturaleza = Column(String(100), nullable=True, index=True)
    driver = Column(String(50), nullable=True)
    tipo_imputacion = Column(String(20), nullable=False)  # DIRECTA | INDIRECTA

    # Dimensiones
    recibo_id = Column(UUID(as_uuid=True), ForeignKey("recibos.id", ondelete="SET NULL"), nullable=True, index=True)
    compania = Column(String(150), nullable=True, index=True)
    ramo = Column(String(100), nullable=True, index=True)
    subramo = Column(String(120), nullable=True, index=True)
    auxiliar = Column(String(150), nullable=True, index=True)
    es_nueva_produccion = Column(Boolean, default=False)

    # Importe (positivo = ingreso, negativo = gasto)
    importe = Column(Numeric(18, 4), default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
