"""add gasto_comision_manual to presupuesto_cesiones_auxiliar

Revision ID: c8d3e9f2a7b1
Revises: a1b2c3d4e5f6
Branch Labels: None
Depends On: None

Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'c8d3e9f2a7b1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'presupuesto_cesiones_auxiliar',
        sa.Column('gasto_comision_manual', sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('presupuesto_cesiones_auxiliar', 'gasto_comision_manual')
