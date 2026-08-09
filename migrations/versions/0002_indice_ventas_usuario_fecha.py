"""Índice compuesto (usuario_id, fecha) en ventas.

Los índices que había eran uno por columna suelta. La consulta del nuevo
GET /ventas/resumen filtra siempre por las dos a la vez
(usuario_id = ? AND fecha IN (...)), y con índices separados Postgres
tiene que combinarlos o quedarse con uno y descartar filas a mano.

Con pocos datos da igual. Con un año de ventas de varias tiendas, no.
Es barato ponerlo ahora que la tabla está prácticamente vacía.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_ventas_usuario_fecha", "ventas", ["usuario_id", "fecha"])


def downgrade() -> None:
    op.drop_index("ix_ventas_usuario_fecha", table_name="ventas")
