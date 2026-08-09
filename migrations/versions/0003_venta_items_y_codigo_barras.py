"""Venta multi-producto y código de barras.

Tres cosas:
  1. `productos.codigo_barras`, opcional y único por negocio.
  2. Tabla `venta_items` con el detalle de cada venta.
  3. Traspaso: cada venta que ya existe se convierte en una venta de un
     solo ítem, para que el histórico quede en el modelo nuevo y no haya
     que consultar dos sitios distintos según la antigüedad del dato.

Las columnas viejas de `ventas` (nombre_producto, cantidad_vendida,
producto_id) NO se borran. Pasan a ser un resumen: el frontend actual
las sigue leyendo y no se rompe. Se podrán quitar cuando Lovable use
`items`, en otra migración.

Revision ID: 0003
Revises: 0002
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("productos", sa.Column("codigo_barras", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_producto_usuario_codigo_activo",
        "productos",
        ["usuario_id", "codigo_barras"],
        unique=True,
        postgresql_where=sa.text("eliminado = false"),
    )

    op.create_table(
        "venta_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("venta_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=True),
        sa.Column("nombre_producto", sa.String(length=255), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Float(), nullable=False),
        sa.Column("precio_total", sa.Float(), nullable=False),
        sa.Column("ganancia_total", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"]),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venta_items_venta_id", "venta_items", ["venta_id"])
    op.create_index("ix_venta_items_producto", "venta_items", ["producto_id"])

    # Traspaso del histórico: cada venta existente pasa a tener un ítem.
    #
    # Se hace en Python y no con un INSERT ... SELECT porque generar el
    # uuid en SQL ataría la migración a Postgres (gen_random_uuid) y no
    # se podría probar contra SQLite antes de tocar la base real. Con el
    # volumen de esta tabla la diferencia de velocidad es irrelevante.
    conexion = op.get_bind()
    ventas = conexion.execute(
        sa.text(
            "SELECT id, producto_id, nombre_producto, cantidad_vendida, "
            "precio_venta_total, ganancia_total FROM ventas"
        )
    ).fetchall()

    for v in ventas:
        cantidad = v.cantidad_vendida or 0
        # Guarda contra una venta con cantidad 0 (no debería existir, pero
        # una división por cero aquí abortaría la migración entera).
        unitario = round(v.precio_venta_total / cantidad, 2) if cantidad else 0.0
        conexion.execute(
            sa.text(
                "INSERT INTO venta_items (id, venta_id, producto_id, nombre_producto, "
                "cantidad, precio_unitario, precio_total, ganancia_total) "
                "VALUES (:id, :venta_id, :producto_id, :nombre, :cantidad, "
                ":unitario, :total, :ganancia)"
            ),
            {
                "id": str(uuid.uuid4()),
                "venta_id": v.id,
                "producto_id": v.producto_id,
                "nombre": v.nombre_producto,
                "cantidad": cantidad,
                "unitario": unitario,
                "total": v.precio_venta_total,
                "ganancia": v.ganancia_total,
            },
        )


def downgrade() -> None:
    op.drop_table("venta_items")
    op.drop_index("uq_producto_usuario_codigo_activo", table_name="productos")
    op.drop_column("productos", "codigo_barras")
