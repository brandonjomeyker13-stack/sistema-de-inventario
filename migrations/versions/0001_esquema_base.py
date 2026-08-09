"""Esquema base: el estado que create_all ya dejó en la base.

Esta migración NO introduce cambios. Es la foto del esquema tal como
existe hoy, para que Alembic tenga un punto de partida.

Si tu base YA tiene las tablas (creadas por el create_all que había en
main.py), no ejecutes esta migración: márcala como aplicada con
    alembic stamp 0001
Si es una base nueva y vacía, `alembic upgrade head` la crea todo.

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("nombre_negocio", sa.String(length=255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("email_verificado", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    op.create_table(
        "productos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio", sa.Float(), nullable=False),
        sa.Column("cuanto_costo", sa.Float(), nullable=False),
        sa.Column("eliminado", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_productos_usuario_id", "productos", ["usuario_id"])
    # Único parcial: dos negocios pueden repetir nombre, y un mismo
    # negocio puede reutilizar el nombre de un producto que ya borró.
    op.create_index(
        "uq_producto_usuario_nombre_activo",
        "productos",
        ["usuario_id", "nombre"],
        unique=True,
        postgresql_where=sa.text("eliminado = false"),
    )

    op.create_table(
        "ventas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=True),
        sa.Column("nombre_producto", sa.String(length=255), nullable=False),
        sa.Column("cantidad_vendida", sa.Integer(), nullable=False),
        sa.Column("precio_venta_total", sa.Float(), nullable=False),
        sa.Column("ganancia_total", sa.Float(), nullable=False),
        sa.Column("fecha", sa.String(length=10), nullable=False),
        sa.Column("eliminado", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ventas_usuario_id", "ventas", ["usuario_id"])
    op.create_index("ix_ventas_fecha", "ventas", ["fecha"])

    op.create_table(
        "sesiones",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado", sa.Boolean(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sesiones_usuario_id", "sesiones", ["usuario_id"])
    op.create_index("ix_sesiones_token_hash", "sesiones", ["token_hash"], unique=True)

    op.create_table(
        "tokens_verificacion",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tokens_verificacion_usuario_id", "tokens_verificacion", ["usuario_id"])
    op.create_index("ix_tokens_verificacion_token", "tokens_verificacion", ["token"], unique=True)


def downgrade() -> None:
    op.drop_table("tokens_verificacion")
    op.drop_table("sesiones")
    op.drop_table("ventas")
    op.drop_table("productos")
    op.drop_table("usuarios")
