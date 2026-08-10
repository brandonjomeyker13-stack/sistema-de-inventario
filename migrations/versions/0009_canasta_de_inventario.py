"""Canasta con propósito: venta o inventario.

Permite usar el celular como lector también para dar de alta mercancía,
reutilizando el emparejamiento que ya existe para las ventas en vez de
montar un segundo mecanismo con su propio token y su propia caducidad.

Dos cambios en los ítems:
  - `producto_id` pasa a ser nullable: al recibir mercancía se escanean
    códigos que todavía no son ningún producto.
  - `codigo_pendiente` guarda ese código, para que el PC pueda abrir el
    formulario de alta con el dato ya puesto.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "canastas",
        sa.Column("proposito", sa.String(length=20), nullable=False, server_default="venta"),
    )

    # batch_alter_table para que funcione igual en Postgres y en SQLite.
    # SQLite no sabe cambiar la nulabilidad de una columna: Alembic
    # recrea la tabla por debajo. En Postgres se traduce a un ALTER normal.
    with op.batch_alter_table("canasta_items") as batch:
        batch.alter_column("producto_id", existing_type=sa.String(length=36), nullable=True)
        batch.add_column(sa.Column("codigo_pendiente", sa.String(length=64), nullable=True))

    op.create_index(
        "uq_canasta_item_codigo", "canasta_items",
        ["canasta_id", "codigo_pendiente"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_canasta_item_codigo", table_name="canasta_items")
    with op.batch_alter_table("canasta_items") as batch:
        batch.drop_column("codigo_pendiente")
        batch.alter_column("producto_id", existing_type=sa.String(length=36), nullable=False)
    op.drop_column("canastas", "proposito")
