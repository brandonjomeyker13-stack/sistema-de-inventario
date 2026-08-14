"""Clave de idempotencia en ventas: reintentar no duplica el cobro.

El caso real que resuelve, de una papelería que trabaja con datos móviles:
el tendero cobra, la petición sale, y la señal se cae antes de que llegue
la respuesta. El frontend no tiene forma de saber si la venta se guardó.

Si reintenta, sin esta columna la venta se registra dos veces: el stock se
descuenta doble y se suma plata que nadie pagó. Es el peor tipo de error
porque no se nota — parece un buen día de ventas, y el descuadre solo
aparece en el conteo físico de fin de mes.

El índice único (usuario_id, clave_idempotencia) es lo que de verdad
impide el duplicado. Comprobar en el código "¿ya existe esta clave?" no
basta: dos reintentos simultáneos pasan los dos la comprobación y los dos
insertan. La base es el único árbitro que no se equivoca.

Único POR NEGOCIO y no global: dos tiendas podrían generar el mismo
identificador sin que signifique nada, y hacerlo global dejaría que una
tienda bloqueara las ventas de otra mandando claves a propósito.

Revision ID: 0017
Revises: 0016
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: las ventas que ya existen no tienen clave, y vender desde
    # el PC con buena conexión no la necesita. Tanto Postgres como SQLite
    # tratan los NULL como distintos entre sí, así que todas esas filas
    # conviven en el índice único sin chocar.
    op.add_column("ventas", sa.Column("clave_idempotencia", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_ventas_usuario_clave",
        "ventas",
        ["usuario_id", "clave_idempotencia"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ventas_usuario_clave", table_name="ventas")
    op.drop_column("ventas", "clave_idempotencia")
