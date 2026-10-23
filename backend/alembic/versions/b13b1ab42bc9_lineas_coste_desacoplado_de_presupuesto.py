"""lineas_coste desacoplado de presupuesto

Revision ID: b13b1ab42bc9
Revises: a4fbde81d9cb
Create Date: 2026-10-18 00:00:00.000000

Costes pasa a identificarse por ejercicio+mes, no por presupuesto_id: así
funciona con solo tener diario real cargado, sin necesitar un presupuesto
creado para ese año (pedido en vivo 2026-10-18). presupuesto_id se queda
como columna opcional (se rellena solo si existe un Presupuesto para el
mismo ejercicio, para poder comparar contra importe_presupuesto).

La tabla lineas_coste está vacía en este momento (módulo recién conectado,
sin diario de 2026 cargado todavía), así que no hace falta migrar datos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b13b1ab42bc9'
down_revision: Union[str, Sequence[str], None] = 'a4fbde81d9cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_lineas_coste_presupuesto_mes', table_name='lineas_coste')
    op.drop_constraint('lineas_coste_presupuesto_id_fkey', 'lineas_coste', type_='foreignkey')
    op.alter_column('lineas_coste', 'presupuesto_id', nullable=True)
    op.create_foreign_key(
        'lineas_coste_presupuesto_id_fkey', 'lineas_coste', 'presupuestos',
        ['presupuesto_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_lineas_coste_ejercicio_mes', 'lineas_coste', ['ejercicio', 'mes'])


def downgrade() -> None:
    op.drop_index('ix_lineas_coste_ejercicio_mes', table_name='lineas_coste')
    op.drop_constraint('lineas_coste_presupuesto_id_fkey', 'lineas_coste', type_='foreignkey')
    op.alter_column('lineas_coste', 'presupuesto_id', nullable=False)
    op.create_foreign_key(
        'lineas_coste_presupuesto_id_fkey', 'lineas_coste', 'presupuestos',
        ['presupuesto_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index('ix_lineas_coste_presupuesto_mes', 'lineas_coste', ['presupuesto_id', 'mes'])
