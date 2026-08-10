"""Libro de movimientos de inventario.

Entradas de mercancía, mermas, ajustes por conteo y salidas por venta.
Hasta ahora el stock solo se corregía editando el producto, sin dejar
rastro de por qué había cambiado.

NO se rellena con el histórico: no hay forma de reconstruir por qué el
stock de un producto es el que es. El libro empieza desde aquí, y las
ventas anteriores no aparecen en él. Es preferible un libro que empieza
en una fecha conocida a uno con movimientos inventados.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movimientos_inventario",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("stock_antes", sa.Integer(), nullable=False),
        sa.Column("stock_despues", sa.Integer(), nullable=False),
        sa.Column("costo_unitario", sa.Float(), nullable=True),
        sa.Column("motivo", sa.String(length=255), nullable=True),
        sa.Column("venta_id", sa.String(length=36), nullable=True),
        sa.Column("fecha", sa.String(length=10), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"]),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_movimientos_inventario_usuario_id", "movimientos_inventario", ["usuario_id"])
    op.create_index("ix_movimientos_inventario_producto_id", "movimientos_inventario", ["producto_id"])
    op.create_index(
        "ix_movimientos_producto_fecha", "movimientos_inventario", ["producto_id", "fecha"]
    )


def downgrade() -> None:
    op.drop_table("movimientos_inventario")
