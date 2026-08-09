"""Clientes, fiados (abonos) y categorías.

Los tres huecos que la interfaz ya mostraba y la API no tenía.

`ventas` gana `cliente_id` y `es_fiado`. El saldo pendiente NO se guarda:
se calcula restando los abonos al total. Un saldo almacenado se
desincroniza en cuanto algo va mal, y aquí eso significa cobrarle de más
o de menos a una persona real.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _soporta_alter_constraint() -> bool:
    """SQLite no sabe añadir una FK a una tabla que ya existe (habría que
    recrearla entera). Postgres sí. Se comprueba el dialecto para que
    estas migraciones puedan ensayarse contra un SQLite desechable antes
    de aplicarlas a Supabase — que es lo que de verdad importa."""
    return op.get_bind().dialect.name != "sqlite"


def upgrade() -> None:
    op.create_table(
        "clientes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("telefono", sa.String(length=64), nullable=True),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("eliminado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clientes_usuario_id", "clientes", ["usuario_id"])
    op.create_index(
        "uq_cliente_usuario_nombre_activo", "clientes", ["usuario_id", "nombre"],
        unique=True, postgresql_where=sa.text("eliminado = false"),
    )

    op.create_table(
        "categorias",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("eliminado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categorias_usuario_id", "categorias", ["usuario_id"])
    op.create_index(
        "uq_categoria_usuario_nombre_activo", "categorias", ["usuario_id", "nombre"],
        unique=True, postgresql_where=sa.text("eliminado = false"),
    )

    op.create_table(
        "abonos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("venta_id", sa.String(length=36), nullable=False),
        sa.Column("monto", sa.Float(), nullable=False),
        sa.Column("fecha", sa.String(length=10), nullable=False),
        sa.Column("nota", sa.String(length=255), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abonos_venta_id", "abonos", ["venta_id"])

    op.add_column("productos", sa.Column("categoria_id", sa.String(length=36), nullable=True))
    op.create_index("ix_productos_categoria_id", "productos", ["categoria_id"])
    if _soporta_alter_constraint():
        op.create_foreign_key(
            "fk_productos_categoria", "productos", "categorias", ["categoria_id"], ["id"]
        )

    # server_default en es_fiado para que las filas que ya existen queden
    # en false sin necesidad de un UPDATE aparte. Se deja puesto: si algún
    # día alguien inserta sin especificarlo, false es la respuesta correcta.
    op.add_column(
        "ventas",
        sa.Column("es_fiado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("ventas", sa.Column("cliente_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ventas_cliente_id", "ventas", ["cliente_id"])
    if _soporta_alter_constraint():
        op.create_foreign_key("fk_ventas_cliente", "ventas", "clientes", ["cliente_id"], ["id"])


def downgrade() -> None:
    if _soporta_alter_constraint():
        op.drop_constraint("fk_ventas_cliente", "ventas", type_="foreignkey")
    op.drop_index("ix_ventas_cliente_id", table_name="ventas")
    op.drop_column("ventas", "cliente_id")
    op.drop_column("ventas", "es_fiado")

    if _soporta_alter_constraint():
        op.drop_constraint("fk_productos_categoria", "productos", type_="foreignkey")
    op.drop_index("ix_productos_categoria_id", table_name="productos")
    op.drop_column("productos", "categoria_id")

    op.drop_table("abonos")
    op.drop_table("categorias")
    op.drop_table("clientes")
