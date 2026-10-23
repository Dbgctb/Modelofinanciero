from sqlalchemy import Column, String, Integer, Numeric, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from ..core.database import Base


class AuxiliarComisionRef(Base):
    """
    Catálogo de % de comisión de colaborador por auxiliar y año, cargado por
    CSV en Administración. Al generar las cesiones de auxiliares del
    presupuesto de gastos, el % comisión de cada auxiliar nuevo se rellena
    automáticamente buscando aquí por (año del presupuesto, auxiliar).
    """
    __tablename__ = "auxiliares_comision_ref"
    __table_args__ = (
        UniqueConstraint('anyo', 'auxiliar', name='uq_auxiliares_comision_anyo_auxiliar'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anyo = Column(Integer, nullable=False)
    auxiliar = Column(String(150), nullable=False)
    comision_colaborador = Column(Numeric(8, 4), nullable=False)
    # % IRPF. Se autorrellena a 15% si el nombre del auxiliar no contiene "S.L."
    # (heurística de persona física vs jurídica, ver services/auxiliares.py). Editable
    # a mano para los casos que la heurística no detecta bien (S.A., S.COOP, C.B...).
    pct_retencion = Column(Numeric(8, 4), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
