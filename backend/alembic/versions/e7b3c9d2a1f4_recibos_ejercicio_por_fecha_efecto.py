"""recibos.ejercicio = año de la fecha de efecto (desde)

Revision ID: e7b3c9d2a1f4
Revises: d5e2a7c41f08
Create Date: 2026-10-23 00:00:00.000000

Hasta ahora cada recibo tomaba el ejercicio de la carga, y como el CSV real
trae la historia completa (efectos 2017-2027) los 102.297 recibos quedaron
como 2025: Cross-selling analizaba todos los años como si fueran uno y la
detección de fuga no tenía ejercicio anterior. Desde esta versión la carga
usa el año de `desde` (ver carga_recibos.cargar_csv_recibos); esta migración
pone los datos existentes en el mismo criterio.

Solo cambia la columna ejercicio; los vínculos diario → recibo (recibo_id) no
se tocan. downgrade() reproduce el criterio anterior: el ejercicio de la
última carga de recibos para todos.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7b3c9d2a1f4'
down_revision: Union[str, Sequence[str], None] = 'd5e2a7c41f08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE recibos SET ejercicio = EXTRACT(YEAR FROM desde)::int "
        "WHERE desde IS NOT NULL AND ejercicio <> EXTRACT(YEAR FROM desde)::int"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE recibos SET ejercicio = c.ejercicio FROM ("
        "  SELECT ejercicio FROM cargas_contables WHERE tipo_carga = 'RECIBOS'"
        "  ORDER BY created_at DESC LIMIT 1"
        ") c"
    )
