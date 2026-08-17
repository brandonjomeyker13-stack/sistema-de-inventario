"""Umbral de stock bajo, para saber qué hay que comprar.

Hasta ahora la única alerta de "se está acabando" era `por_agotarse`, que
calcula por RITMO DE VENTA: cuántas unidades salen al día y cuántos días
queda de existencias. Es útil, pero tiene un punto ciego grande — un
producto sin historial de ventas tiene ritmo cero, así que NUNCA aparece. Un
producto nuevo, o uno que se vende poco, se agota en silencio.

Y no es como piensa un tendero. Él piensa "avísame cuando queden menos de
cinco", no "avísame cuando el ritmo indique tres días".

Dos columnas:

  productos.stock_minimo          umbral propio de ese producto. NULL = usa
                                  el del negocio.
  usuarios.stock_minimo_defecto   el del negocio. Arranca en 5.

Por producto y no solo global porque un único número no sirve: el arroz
vende cincuenta a la semana y hay que pedirlo con veinte todavía en la
estantería, mientras que un cuaderno avisa con dos. Con un solo umbral la
alerta o suena siempre o no suena nunca, y una que suena siempre se deja de
mirar — incluida la de los productos que sí importan.

El defecto es 5 y no NULL para que la lista de compra funcione desde el
primer día. Una función que exige configurarla antes de servir para algo no
la usa nadie.

Revision ID: 0022
Revises: 0021
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("productos", sa.Column("stock_minimo", sa.Integer(), nullable=True))

    # server_default: la columna es NOT NULL y las cuentas que ya existen
    # necesitan un valor. El default de SQLAlchemy solo actúa al insertar
    # desde la aplicación, no sobre las filas guardadas.
    op.add_column(
        "usuarios",
        sa.Column("stock_minimo_defecto", sa.Integer(), nullable=False, server_default="5"),
    )

    # Se retira el default de la base una vez rellenadas las filas viejas:
    # a partir de aquí el valor lo decide la aplicación, que es donde está
    # la regla. Dejarlo escondería el día que el modelo y la base dejaran
    # de coincidir. SQLite no sabe alterar columnas y allí sobra.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("usuarios", "stock_minimo_defecto", server_default=None)


def downgrade() -> None:
    op.drop_column("usuarios", "stock_minimo_defecto")
    op.drop_column("productos", "stock_minimo")
