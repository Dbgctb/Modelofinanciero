"""drop lineas_coste (se elimina el módulo de Costes)

Revision ID: d5e2a7c41f08
Revises: b13b1ab42bc9
Create Date: 2026-10-23 00:00:00.000000

El módulo de Costes (clasificación, imputación, comparativa y KPIs de costes)
se elimina por decisión del usuario (2026-10-23): duplicaba lo que ya hace el
Modelo Analítico (reparto de indirectos por compañía/ramo/auxiliar, dashboard
de costes) y Seguimiento real (real vs presupuesto de gastos), con un reparto
más pobre. Nada fuera del propio módulo leía esta tabla.

Los datos que contenía se generaban automáticamente desde el diario, así que
no se pierde información que no pueda regenerarse. downgrade() recrea la
tabla vacía con su forma final (la de b13b1ab42bc9).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5e2a7c41f08'
down_revision: Union[str, Sequence[str], None] = 'b13b1ab42bc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUMS = ('tipocoste', 'tratamientocoste', 'driverreparto', 'motivoexclusioncoste', 'estadocoste')


def upgrade() -> None:
    op.drop_index('ix_lineas_coste_ejercicio_mes', table_name='lineas_coste')
    op.drop_table('lineas_coste')
    for enum_name in _ENUMS:
        op.execute(f'DROP TYPE IF EXISTS {enum_name}')


def downgrade() -> None:
    op.create_table(
        'lineas_coste',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('presupuesto_id', sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(['presupuesto_id'], ['presupuestos.id'],
                                name='lineas_coste_presupuesto_id_fkey', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['revisado_por_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lineas_coste_ejercicio_mes', 'lineas_coste', ['ejercicio', 'mes'])
