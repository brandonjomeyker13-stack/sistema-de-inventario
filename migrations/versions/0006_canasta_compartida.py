"""Canasta compartida entre el PC y el celular.

El carrito de una venta en curso, viviendo en el servidor para que dos
dispositivos puedan verlo a la vez: el celular escanea, el PC muestra.

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canastas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("token_celular", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="abierta"),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("venta_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_canastas_usuario_id", "canastas", ["usuario_id"])
    op.create_index("ix_canastas_token_celular", "canastas", ["token_celular"], unique=True)

    op.create_table(
        "canasta_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canasta_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("agregado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["canasta_id"], ["canastas.id"]),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_canasta_items_canasta_id", "canasta_items", ["canasta_id"])
    op.create_index(
        "uq_canasta_item_producto", "canasta_items", ["canasta_id", "producto_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("canasta_items")
    op.drop_table("canastas")
