"""Adopta en el código las restricciones que solo existían en producción.

Una auditoría de la base de producción encontró diez CHECK constraints que
NINGÚN archivo del proyecto declaraba. Se habían añadido a mano en el
editor de Supabase:

    productos_cantidad_check          CHECK (cantidad >= 0)
    productos_precio_check            CHECK (precio >= 0)
    productos_cuanto_costo_check      CHECK (cuanto_costo >= 0)
    productos_nombre_check            CHECK (char_length(trim(nombre)) > 0)
    usuarios_nombre_negocio_check     CHECK (char_length(trim(nombre_negocio)) > 0)
    ventas_cantidad_vendida_check     CHECK (cantidad_vendida > 0)
    ventas_precio_venta_total_check   CHECK (precio_venta_total >= 0)
    ventas_nombre_producto_check      CHECK (char_length(trim(nombre_producto)) > 0)
    ventas_fecha_check                CHECK (fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    ventas_ganancia_total_check       CHECK (ganancia_total >= 0)   <- la mala

Nueve son correctas. La última era el fallo que tumbaba las ventas con
pérdida, y la quita la migración 0019.

EL PROBLEMA DE FONDO no era esa restricción: era que la base de producción
tenía reglas que el código no conocía. Consecuencias concretas:

  · Ninguna prueba podía detectar una violación, porque la base de pruebas
    se construye desde los modelos y los modelos no las tenían.
  · Una base creada desde cero (otro entorno, un restore, el Postgres
    local de otra persona) NO las habría tenido. Los precios podrían ser
    negativos ahí y no en producción: el peor tipo de diferencia, la que
    hace que un fallo aparezca en un sitio y no en el otro.

Esta migración cierra ese hueco: las nueve buenas quedan declaradas en los
modelos (ver __table_args__ en producto.py, venta.py y usuario.py) y aquí
se reconcilian sobre la base que ya existe.

Es idempotente: DROP IF EXISTS y luego ADD. Da igual si la restricción ya
estaba o no, y se puede volver a correr sin romper nada.

Revision ID: 0020
Revises: 0019
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, nombre, condición). Las condiciones usan length(trim(...)) en vez
# de char_length(...) para que la misma expresión valga en PostgreSQL y en
# SQLite; en Postgres length() es sinónimo de char_length() para texto.
RESTRICCIONES = (
    ("productos", "productos_cantidad_check", "cantidad >= 0"),
    ("productos", "productos_precio_check", "precio >= 0"),
    ("productos", "productos_cuanto_costo_check", "cuanto_costo >= 0"),
    ("productos", "productos_nombre_check", "length(trim(nombre)) > 0"),
    ("usuarios", "usuarios_nombre_negocio_check", "length(trim(nombre_negocio)) > 0"),
    ("ventas", "ventas_cantidad_vendida_check", "cantidad_vendida > 0"),
    ("ventas", "ventas_precio_venta_total_check", "precio_venta_total >= 0"),
    ("ventas", "ventas_nombre_producto_check", "length(trim(nombre_producto)) > 0"),
)

# La del formato de fecha se queda solo en PostgreSQL y fuera de los
# modelos: el operador de expresiones regulares `~` no existe en SQLite, y
# meterlo en el modelo rompería la creación de la base de pruebas. La regla
# de verdad vive en app/core/fechas.py, que es quien genera esas fechas.
RESTRICCION_FECHA = (
    "ventas", "ventas_fecha_check",
    r"fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'",
)


def upgrade() -> None:
    # SQLite no sabe añadir restricciones con ALTER TABLE. No hace falta:
    # allí la base se crea desde los modelos, que ya las declaran.
    if op.get_bind().dialect.name != "postgresql":
        return

    for tabla, nombre, condicion in RESTRICCIONES + (RESTRICCION_FECHA,):
        # DROP antes del ADD para poder correr esto sobre la base que ya
        # las tiene sin que falle por nombre repetido.
        op.execute(f'ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS "{nombre}"')
        op.execute(f'ALTER TABLE {tabla} ADD CONSTRAINT "{nombre}" CHECK ({condicion})')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for tabla, nombre, _ in RESTRICCIONES + (RESTRICCION_FECHA,):
        op.execute(f'ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS "{nombre}"')
