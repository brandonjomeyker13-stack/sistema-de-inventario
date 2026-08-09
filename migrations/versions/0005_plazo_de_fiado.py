"""Plazo de pago en los fiados.

Una libreta de deudores sin fecha de pago no responde la pregunta que el
tendero hace de verdad: no "cuánto me deben", sino "quién va tarde".

  - `ventas.fecha_vencimiento`: hasta cuándo tiene ese fiado concreto.
  - `clientes.dias_plazo`: el plazo habitual del cliente, para no
    teclearlo cada vez.

Ambas nullable: hay fiados sin fecha acordada ("cuando puedas"), y forzar
una inventada daría alertas de atraso falsas.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ventas", sa.Column("fecha_vencimiento", sa.String(length=10), nullable=True))
    op.add_column("clientes", sa.Column("dias_plazo", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("clientes", "dias_plazo")
    op.drop_column("ventas", "fecha_vencimiento")
