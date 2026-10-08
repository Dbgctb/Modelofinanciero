"""add tasa_caida to presupuesto_ingresos

Revision ID: e5f0a4d3c7b1
Revises: d4e9f3c2b6a8
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f0a4d3c7b1'
down_revision = 'd4e9f3c2b6a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'presupuesto_ingresos',
        sa.Column('tasa_caida', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('presupuesto_ingresos', 'tasa_caida')
