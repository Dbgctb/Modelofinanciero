"""add recibos value to tipocarga enum

Revision ID: c3f8e2b1d5a7
Revises: b2e7f1a4c8d9
Create Date: 2026-05-16
"""
from alembic import op

revision = 'c3f8e2b1d5a7'
down_revision = 'b2e7f1a4c8d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipocarga ADD VALUE IF NOT EXISTS 'RECIBOS'")


def downgrade() -> None:
    # PostgreSQL no permite eliminar valores de un enum; la migración inversa es no-op
    pass
