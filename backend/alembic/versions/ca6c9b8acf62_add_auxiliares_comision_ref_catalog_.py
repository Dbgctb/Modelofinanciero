"""add auxiliares_comision_ref catalog table

Revision ID: ca6c9b8acf62
Revises: d6881c833049
Create Date: 2026-10-11 00:50:52.462699

Escrita a mano en vez de usar el autogenerate: el autogenerate también
proponía borrar más de 10 tablas reales con datos (clientes, fuga_alertas,
fact_resultado_analitico, password_reset_tokens...) porque sus modelos no
están importados en alembic/env.py -- un desajuste preexistente ajeno a
este cambio. Esta migración se limita a la tabla nueva.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ca6c9b8acf62'
down_revision: Union[str, Sequence[str], None] = 'd6881c833049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auxiliares_comision_ref',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('anyo', sa.Integer(), nullable=False),
        sa.Column('auxiliar', sa.String(length=150), nullable=False),
        sa.Column('comision_colaborador', sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('anyo', 'auxiliar', name='uq_auxiliares_comision_anyo_auxiliar'),
    )


def downgrade() -> None:
    op.drop_table('auxiliares_comision_ref')
