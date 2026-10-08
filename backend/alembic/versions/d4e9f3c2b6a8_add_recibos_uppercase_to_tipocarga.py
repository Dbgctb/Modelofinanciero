"""add RECIBOS (uppercase) to tipocarga enum

Revision ID: d4e9f3c2b6a8
Revises: c3f8e2b1d5a7
Create Date: 2026-05-16
"""
from alembic import op

revision = 'd4e9f3c2b6a8'
down_revision = 'c3f8e2b1d5a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipocarga ADD VALUE IF NOT EXISTS 'RECIBOS'")


def downgrade() -> None:
    pass
