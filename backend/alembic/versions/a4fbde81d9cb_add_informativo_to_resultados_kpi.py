"""add informativo to resultados_kpi

Revision ID: a4fbde81d9cb
Revises: 18290dae47bf
Create Date: 2026-10-17 00:00:00.000000

Marca explícita (en vez de adivinar por el texto del nombre en el frontend)
de qué KPIs no tienen un umbral comparable en el modo actual. Arregla un bug
real: KPI-08 pasa de ser "% cumplimiento de gastos" (con umbral en puntos
porcentuales) a "Gastos operativos propios (€)" en modo presupuesto (sin
datos reales todavía) -- el frontend mostraba la "Meta" de 5 puntos
porcentuales como si fueran 5 euros, al lado de un valor real en miles de
euros.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4fbde81d9cb'
down_revision: Union[str, Sequence[str], None] = '18290dae47bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'resultados_kpi',
        sa.Column('informativo', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.alter_column('resultados_kpi', 'informativo', server_default=None)


def downgrade() -> None:
    op.drop_column('resultados_kpi', 'informativo')
