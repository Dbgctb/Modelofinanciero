"""add_auxiliar_to_cross_selling_oportunidad

Revision ID: d6881c833049
Revises: c8d3e9f2a7b1
Create Date: 2026-07-04 17:49:38.860233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd6881c833049'
down_revision: Union[str, Sequence[str], None] = 'c8d3e9f2a7b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'cross_selling_oportunidades',
        sa.Column('auxiliar', sa.String(150), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('cross_selling_oportunidades', 'auxiliar')
