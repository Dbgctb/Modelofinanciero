"""add tasas_mercado_ref table and historico_estadistico to tipocarga

Revision ID: f6a1b5e4d9c3
Revises: e5f0a4d3c7b1
Create Date: 2026-05-17
"""
from alembic import op

revision = 'f6a1b5e4d9c3'
down_revision = 'e5f0a4d3c7b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Añadir nuevo valor al enum tipocarga (idempotente)
    op.execute("ALTER TYPE tipocarga ADD VALUE IF NOT EXISTS 'historico_estadistico'")

    # 2. Crear enum tipotasamercado (idempotente, raw SQL para evitar
    #    que SQLAlchemy lo intente crear de nuevo en create_table)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tipotasamercado AS ENUM (
                'crecimiento', 'caida_cartera', 'caida_nueva_produccion'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 3. Crear tabla en raw SQL para que no haya ningún evento before_create
    #    de SQLAlchemy que intente recrear el tipo
    op.execute("""
        CREATE TABLE IF NOT EXISTS tasas_mercado_ref (
            id          UUID         NOT NULL,
            fuente      VARCHAR(100) NOT NULL,
            anyo        INTEGER      NOT NULL,
            tipo        tipotasamercado NOT NULL,
            ramo_keyword VARCHAR(100),
            tasa_pct    NUMERIC(8,4) NOT NULL,
            es_default  BOOLEAN      NOT NULL DEFAULT false,
            notas       TEXT,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tasas_mercado_ref_anyo_tipo
        ON tasas_mercado_ref (anyo, tipo)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tasas_mercado_ref_anyo_tipo")
    op.execute("DROP TABLE IF EXISTS tasas_mercado_ref")
    op.execute("DROP TYPE IF EXISTS tipotasamercado")
