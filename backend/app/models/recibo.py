from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from ..core.database import Base


class Recibo(Base):
    __tablename__ = "recibos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ejercicio = Column(Integer, nullable=False, index=True)

    # Columnas del CSV
    codigo = Column(String(20), nullable=False, index=True)   # columna "Código" — clave de búsqueda
    recibo_cia = Column(String(100), nullable=True)           # columna "Recibo"
    desde = Column(Date, nullable=True)
    hasta = Column(Date, nullable=True)
    numero_poliza = Column(String(100), nullable=True)
    compania = Column(String(150), nullable=True)             # "Abrev.Cía"
    pr_total = Column(Numeric(14, 2), nullable=True)
    pr_neto = Column(Numeric(14, 2), nullable=True)
    c_ced = Column(Numeric(14, 2), nullable=True)
    reten = Column(Numeric(14, 2), nullable=True)
    liqui = Column(Numeric(14, 2), nullable=True)             # comisión neta
    ente = Column(String(150), nullable=True, index=True)     # auxiliar — GROUP BY frecuente
    cobro = Column(String(100), nullable=True)
    tomador = Column(String(255), nullable=True, index=True)  # GROUP BY / WHERE en rentabilidad
    producto = Column(String(255), nullable=True)
    estado = Column(String(50), nullable=True)

    # Campos derivados
    ramo = Column(String(100), nullable=True)                 # extraído de "producto"
    subramo = Column(String(120), nullable=True)              # importado desde Ramo2.xlsx
    tipo_negocio = Column(String(30), nullable=True)          # cartera / nueva_produccion (asignable manualmente)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
