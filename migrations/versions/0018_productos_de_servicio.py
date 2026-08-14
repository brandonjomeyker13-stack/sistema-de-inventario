"""Productos que no llevan existencias: los servicios.

Una papelería no solo vende cosas; vende fotocopias, impresiones,
plastificado, anillado. Esos no tienen existencias — no se te "acaban" las
fotocopias.

Hasta ahora había que inventarles un stock falso, y el día que llegaba a
cero el sistema se negaba a venderlos:

    "No puedes vender más 'Fotocopia' de lo que hay en stock
     (pides 20, disponible: 0)"

Con `controla_stock = false`, el producto se vende y deja ganancia como
cualquier otro, pero no descuenta existencias, no entra al libro de
movimientos, no aparece en la alerta de "se está acabando" y no cuenta
como capital parado (no hay plata dormida en una fotocopia que aún no se
ha hecho).

El valor por defecto es TRUE, tanto para las filas que ya existen como
para las nuevas: casi todo lo que vende una tienda sí se cuenta, y el
valor seguro es el que avisa cuando algo se está agotando.

Revision ID: 0018
Revises: 0017
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default y no solo el default de Python: la columna es NOT
    # NULL, y sin un valor por defecto en la BASE el ALTER falla sobre las
    # filas que ya existen. El default de SQLAlchemy solo actúa al insertar
    # desde la aplicación, no sobre lo que ya está guardado.
    op.add_column(
        "productos",
        sa.Column("controla_stock", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # Se retira el server_default una vez rellenadas las filas viejas: a
    # partir de aquí el valor lo decide la aplicación, que es donde está
    # la regla. Dejarlo puesto escondería el día que el modelo y la base
    # dejaran de coincidir.
    #
    # SQLite no sabe alterar columnas, así que allí se omite; el default
    # sobrante es inofensivo y las pruebas corren sobre base nueva.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("productos", "controla_stock", server_default=None)


def downgrade() -> None:
    op.drop_column("productos", "controla_stock")
