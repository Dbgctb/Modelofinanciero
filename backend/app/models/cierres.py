"""Tablas del módulo "Cierres contabilidad" (prefijo cc_).

Reconstrucción en PostgreSQL del programa de escritorio "Cuadre Contable"
(punteo del diario completo y conciliación bancaria). Ver
docs/PLAN_CIERRES_CONTABILIDAD.md.

Decisiones:
- Los nombres de columna son los del programa original (reconciled,
  recon_rule, recon_group_id...). Las 19 reglas y los niveles del banco son
  mucho SQL; conservar los nombres reduce los errores de traducción y deja la
  prueba de paridad comparable columna a columna.
- Los ids de cc_apuntes son los originales. Los referencian, sin clave
  foránea (igual que en el original, donde una reimportación completa borra
  y vuelve a crear apuntes), cc_emparejamientos_h.cobro_id,
  cc_incidencias.line_ids y cc_extractos.recon_journal_id.
- Importes NUMERIC(18,2) en lugar de REAL; cuenta como texto.
- Estas tablas no tienen relación con diario_apuntes (grupos 6 y 7 para la
  Cuenta de Resultados): el punteo necesita el diario completo.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func

from ..core.database import Base


class CCApunte(Base):
    """Apunte del diario completo (todas las cuentas, todos los ejercicios)."""
    __tablename__ = "cc_apuntes"
    __table_args__ = (
        Index("ix_cc_apuntes_ej_cuenta_rec", "ejercicio", "cuenta", "reconciled"),
        Index("ix_cc_apuntes_ej_numero", "ejercicio", "numero"),
        Index("ix_cc_apuntes_recibo_norm", "recibo_norm"),
        Index("ix_cc_apuntes_asiento_key", "asiento_key"),
        Index("ix_cc_apuntes_recon_group", "recon_group_id"),
    )

    id = Column(Integer, primary_key=True)
    linea = Column(Integer)
    serie = Column(String(10))
    numero = Column(Integer)
    ejercicio = Column(Integer, nullable=False)
    fecha = Column(Date, nullable=False)
    debe = Column(Numeric(18, 2), nullable=False, server_default="0")
    haber = Column(Numeric(18, 2), nullable=False, server_default="0")
    cuenta = Column(String(20), nullable=False)
    descripcion_cuenta = Column(String(255))
    concepto = Column(Text)
    neto = Column(Numeric(18, 2))
    recibo_norm = Column(String(30))
    concepto_norm = Column(Text)
    asiento_key = Column(String(40))
    reconciled = Column(Boolean, nullable=False, server_default="false")
    recon_rule = Column(String(30))
    recon_group_id = Column(String(100))
    recon_run_id = Column(Integer)
    recon_timestamp = Column(DateTime)
    es_nuevo = Column(Boolean, nullable=False, server_default="false")
    es_huerfano = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime, server_default=func.now())


class CCRegla(Base):
    """Regla del motor de punteo con su prioridad y tolerancias."""
    __tablename__ = "cc_reglas"

    rule_code = Column(String(30), primary_key=True)
    rule_name = Column(String(150), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, nullable=False, server_default="true")
    active = Column(Boolean, nullable=False, server_default="true")
    priority = Column(Integer, nullable=False, server_default="0")
    tolerance_amount = Column(Numeric(12, 2), nullable=False, server_default="0.01")
    tolerance_days = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class CCEjecucion(Base):
    """Historial de ejecuciones del motor de punteo."""
    __tablename__ = "cc_ejecuciones"

    id = Column(Integer, primary_key=True)
    ejercicio = Column(Integer, nullable=False)
    start_time = Column(DateTime, server_default=func.now())
    end_time = Column(DateTime)
    total_lines = Column(Integer, nullable=False, server_default="0")
    total_lines_reconciled = Column(Integer, nullable=False, server_default="0")
    rules_executed = Column(JSONB)
    status = Column(String(20))
    created_at = Column(DateTime, server_default=func.now())


class CCIncidencia(Base):
    """Incidencia de un control de calidad (C, D, K, L)."""
    __tablename__ = "cc_incidencias"
    __table_args__ = (
        Index("ix_cc_incidencias_tipo_ej", "control_type", "ejercicio"),
    )

    id = Column(Integer, primary_key=True)
    control_type = Column(String(5), nullable=False)
    ejercicio = Column(Integer, nullable=False)
    cuenta = Column(String(20))
    recibo_norm = Column(String(30))
    mes = Column(Integer)
    severity = Column(String(20))
    issue_description = Column(Text)
    run_id = Column(Integer)
    line_ids = Column(ARRAY(Integer))
    created_at = Column(DateTime, server_default=func.now())


class CCCuentaControl(Base):
    """Cuenta vigilada por un control de calidad.

    Une las cuatro tablas control_accounts* del original. Según `tipo`:
    C usa min_mov/max_mov, D usa tolerance_pct, K y L solo la cuenta.
    """
    __tablename__ = "cc_cuentas_control"

    id = Column(Integer, primary_key=True)
    tipo = Column(String(1), nullable=False)
    name = Column(String(150))
    cuenta = Column(String(20), nullable=False)
    min_mov = Column(Integer)
    max_mov = Column(Integer)
    tolerance_pct = Column(Numeric(8, 2))
    active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, server_default=func.now())


class CCConfig(Base):
    """Parámetros clave/valor (p. ej. tolerancias de los niveles 8 y 9 del banco)."""
    __tablename__ = "cc_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, server_default=func.now())


class CCEmparejamientoH(Base):
    """Emparejamiento recobro → cobro guardado a mano en el Diagnóstico H."""
    __tablename__ = "cc_emparejamientos_h"
    __table_args__ = (
        UniqueConstraint("asiento_key", "concepto_norm", "cuenta_440", "recibo", "cobro_id",
                         name="uq_cc_emparejamientos_h"),
    )

    id = Column(Integer, primary_key=True)
    asiento_key = Column(String(40), nullable=False)
    concepto_norm = Column(Text, nullable=False)
    cuenta_440 = Column(String(20), nullable=False)
    neto_recobros = Column(Numeric(18, 2), nullable=False)
    recibo = Column(String(30), nullable=False)
    cobro_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class CCBanco(Base):
    """Banco con su cuenta 572."""
    __tablename__ = "cc_bancos"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False, unique=True)
    codigo = Column(String(20))
    cuenta_572 = Column(String(20))
    iban = Column(String(34))
    entidad = Column(String(150))
    activo = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, server_default=func.now())


class CCExtracto(Base):
    """Movimiento de un extracto bancario y su conciliación con el diario."""
    __tablename__ = "cc_extractos"
    __table_args__ = (
        Index("ix_cc_extractos_banco_ej", "banco_id", "ejercicio", "reconciled"),
        Index("ix_cc_extractos_recon_group", "recon_group_id"),
    )

    id = Column(Integer, primary_key=True)
    banco_id = Column(Integer, nullable=False)
    ejercicio = Column(Integer)
    fecha = Column(Date)
    fecha_operacion = Column(Date)
    fecha_valor = Column(Date)
    fecha_contable = Column(Date)
    concepto = Column(Text)
    concepto_banco = Column(Text)
    concepto_contable = Column(Text)
    referencia = Column(String(100))
    cuenta_banco = Column(String(40))
    cuenta_contable = Column(String(20))
    importe = Column(Numeric(18, 2))
    cargo = Column(Numeric(18, 2), nullable=False, server_default="0")
    abono = Column(Numeric(18, 2), nullable=False, server_default="0")
    neto = Column(Numeric(18, 2))
    saldo = Column(Numeric(18, 2))
    reconciled = Column(Boolean, nullable=False, server_default="false")
    recon_level = Column(String(30))
    recon_group_id = Column(String(100))
    recon_journal_id = Column(Integer)
    recon_difference = Column(Numeric(18, 2))
    recon_timestamp = Column(DateTime)
    asiento_key = Column(String(40))
    created_at = Column(DateTime, server_default=func.now())


class CCBancoEjecucion(Base):
    """Historial de ejecuciones de la conciliación bancaria."""
    __tablename__ = "cc_banco_ejecuciones"

    id = Column(Integer, primary_key=True)
    ejercicio = Column(Integer, nullable=False)
    banco_id = Column(Integer)
    cuenta_contable = Column(String(20))
    cuenta_banco = Column(String(40))
    fecha_conciliacion = Column(DateTime, nullable=False)
    mes = Column(Integer)
    status = Column(String(20))
    pct = Column(Numeric(8, 2))
    created_at = Column(DateTime, server_default=func.now())


class CCBancoConfig(Base):
    """Días y tolerancias de los niveles 2 y 3 por cuenta 572."""
    __tablename__ = "cc_banco_config"

    cuenta_572 = Column(String(20), primary_key=True)
    level_2_days = Column(Integer, nullable=False, server_default="3")
    level_2_amount = Column(Numeric(12, 2), nullable=False, server_default="0.01")
    level_3_amount = Column(Numeric(12, 2), nullable=False, server_default="0.01")
    updated_at = Column(DateTime, server_default=func.now())
