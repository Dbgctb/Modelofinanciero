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
    "Suministros",
    "Cesión auxiliar",
]

DRIVERS = ["RECIBOS", "COMISION_NETA", "NUEVA_PRODUCCION"]

# Driver por defecto para cada naturaleza
DRIVERS_DEFAULT: dict[str, str] = {
    "Personal":               "RECIBOS",
    "Alquiler":               "COMISION_NETA",
    "Tecnología":             "RECIBOS",
    "Marketing":              "NUEVA_PRODUCCION",
    "Financiero":             "RECIBOS",
    "Bancos":                 "RECIBOS",
    "Servicios profesionales":"RECIBOS",
    "Comunicaciones":         "RECIBOS",
    "Viajes":                 "COMISION_NETA",
    "Impuestos":              "COMISION_NETA",
    "Suministros":            "COMISION_NETA",
    "Cesión auxiliar":        "COMISION_NETA",
}

# Naturalezas que forman los costes operativos (L4) — todo excepto Marketing y Cesión
NATURALEZAS_COSTE_OP = {
    "Personal", "Alquiler", "Tecnología", "Financiero",
    "Bancos", "Servicios profesionales", "Comunicaciones",
    "Viajes", "Impuestos", "Suministros",
}


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
