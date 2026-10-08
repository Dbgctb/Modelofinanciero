"""add excluir_tesoreria to map_cuentas_contables

Revision ID: b2e7f1a4c8d9
Revises: 30c1004bbb58
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2e7f1a4c8d9'
down_revision = '30c1004bbb58'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'map_cuentas_contables',
        sa.Column('excluir_tesoreria', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('map_cuentas_contables', 'excluir_tesoreria')
