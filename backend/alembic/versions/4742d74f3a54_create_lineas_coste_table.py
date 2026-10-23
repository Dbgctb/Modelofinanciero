"""create lineas_coste table

Revision ID: 4742d74f3a54
Revises: ca6c9b8acf62
Create Date: 2026-10-17 00:00:00.000000

El módulo de Costes (modelo, servicio, router, páginas React) se escribió
en su día pero nunca se conectó: el router no estaba registrado en main.py
y, como su modelo nunca se importaba en ningún punto alcanzable, tampoco
`Base.metadata.create_all()` llegó a crear esta tabla. Confirmado antes de
escribir esto: ni la tabla `lineas_coste` ni sus tipos enum existen en la
base de datos real. Esta migración, escrita a mano (no autogenerate, para
no arrastrar el resto de drift de alembic/env.py), crea la tabla y los 5
enums que el modelo declara.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4742d74f3a54'
down_revision: Union[str, Sequence[str], None] = 'ca6c9b8acf62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lineas_coste',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('presupuesto_id', sa.UUID(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('ejercicio', sa.Integer(), nullable=False),
        sa.Column('numero_cuenta', sa.String(length=20), nullable=True),
        sa.Column('descripcion_cuenta', sa.String(length=255), nullable=True),
        sa.Column('familia_gasto', sa.String(length=100), nullable=True),
        sa.Column('importe_real', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('importe_presupuesto', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('tipo_coste', sa.Enum('FIJO', 'VARIABLE', name='tipocoste'), nullable=True),
        sa.Column('tratamiento', sa.Enum('DIRECTO', 'INDIRECTO', 'EXCLUIDO', name='tratamientocoste'), nullable=True),
        sa.Column('driver', sa.Enum(
            'COMISION_CONTABLE', 'NUEVA_PRODUCCION', 'NUMERO_POLIZAS', 'NUMERO_RECIBOS', 'MANUAL_PORCENTUAL',
            name='driverreparto',
        ), nullable=True),
        sa.Column('clasificacion_automatica', sa.Boolean(), nullable=True),
        sa.Column('motivo_exclusion', sa.Enum(
            'AMORTIZACION', 'AJUSTE_CONTABLE', 'EXTRAORDINARIO', 'SIN_IMPACTO_CAJA', 'NO_OPERATIVO', 'DECISION_DIRECCION',
            name='motivoexclusioncoste',
        ), nullable=True),
        sa.Column('imputacion', sa.JSON(), nullable=True),
        sa.Column('reparto_manual', sa.JSON(), nullable=True),
        sa.Column('estado', sa.Enum(
            'CLASIFICADO', 'PENDIENTE', 'IMPUTADO', 'EXCLUIDO', 'CON_ALERTA', name='estadocoste',
        ), nullable=True),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('revisado_por_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['presupuesto_id'], ['presupuestos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revisado_por_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lineas_coste_presupuesto_mes', 'lineas_coste', ['presupuesto_id', 'mes'])


def downgrade() -> None:
    op.drop_index('ix_lineas_coste_presupuesto_mes', table_name='lineas_coste')
    op.drop_table('lineas_coste')
    for enum_name in ('tipocoste', 'tratamientocoste', 'driverreparto', 'motivoexclusioncoste', 'estadocoste'):
        op.execute(f'DROP TYPE IF EXISTS {enum_name}')
