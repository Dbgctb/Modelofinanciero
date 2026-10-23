"""add pct_retencion to auxiliares_comision_ref

Revision ID: 18290dae47bf
Revises: 4742d74f3a54
Create Date: 2026-10-17 00:00:00.000000

Añade el % de retención (IRPF) por auxiliar. Solo añade la columna con
default 0 -- el relleno real según la heurística (persona física vs S.L.)
se hace aparte con services/auxiliares.calcular_pct_retencion, para no
duplicar esa regla de negocio en SQL dentro de la migración.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '18290dae47bf'
down_revision: Union[str, Sequence[str], None] = '4742d74f3a54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'auxiliares_comision_ref',
        sa.Column('pct_retencion', sa.Numeric(precision=8, scale=4), nullable=False, server_default='0'),
    )
    op.alter_column('auxiliares_comision_ref', 'pct_retencion', server_default=None)


def downgrade() -> None:
    op.drop_column('auxiliares_comision_ref', 'pct_retencion')
