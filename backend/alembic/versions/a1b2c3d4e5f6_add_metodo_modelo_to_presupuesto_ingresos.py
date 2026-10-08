"""add metodo_modelo to presupuesto_ingresos

Revision ID: a1b2c3d4e5f6
Revises: f6a1b5e4d9c3
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f6a1b5e4d9c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'presupuesto_ingresos',
        sa.Column('metodo_modelo', sa.String(60), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('presupuesto_ingresos', 'metodo_modelo')
