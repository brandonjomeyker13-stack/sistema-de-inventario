"""Arregla la rotación de refresh tokens.

El problema: `refrescar` revocaba el token usado y emitía otro. Si dos
pestañas del mismo tendero refrescaban a la vez —que es lo que pasa
cuando el access token expira con el inventario abierto en una y las
ventas en otra— la segunda se encontraba el token ya revocado, recibía un
401 y sacaba al tendero de la sesión en mitad de una venta.

Tres columnas lo resuelven:

  - `revocado_en`: cuándo se revocó. Permite distinguir la carrera de dos
    pestañas (segundos) de un token robado que reaparece días después.
  - `motivo`: por qué se cerró. La ventana de gracia solo vale para la
    rotación normal — si valiera para todas, cerrar una familia por
    seguridad metería esas sesiones en la ventana y el token robado
    seguiría sirviendo medio minuto después de detectarlo. Lo mismo al
    cerrar sesión a mano en un computador ajeno.
  - `familia`: todas las sesiones que salen de un mismo inicio de sesión
    comparten familia. Si aparece un token robado se corta esa cadena y
    solo esa, sin echar al tendero de sus otros dispositivos.

A las sesiones que ya existen se les asigna una familia propia a cada una.
Es lo correcto: no hay forma de reconstruir qué cadena venía de qué login,
y darles a todas la misma haría que un solo token sospechoso cerrara todas
las sesiones del usuario.

Revision ID: 0015
Revises: 0014
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sesiones", sa.Column("revocado_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sesiones", sa.Column("motivo", sa.String(length=20), nullable=True))
    op.add_column("sesiones", sa.Column("familia", sa.String(length=36), nullable=True))
    op.create_index("ix_sesiones_familia", "sesiones", ["familia"])

    # `revocado_en` y `motivo` se quedan en NULL para las filas viejas a
    # propósito: no sabemos cuándo ni por qué se revocaron, y
    # en_ventana_de_gracia() trata ambos NULL como "fuera de gracia", que
    # es la opción segura.
    conexion = op.get_bind()
    filas = conexion.execute(sa.text("SELECT id FROM sesiones WHERE familia IS NULL")).fetchall()
    for f in filas:
        conexion.execute(
            sa.text("UPDATE sesiones SET familia = :familia WHERE id = :id"),
            {"familia": str(uuid.uuid4()), "id": f.id},
        )


def downgrade() -> None:
    op.drop_index("ix_sesiones_familia", table_name="sesiones")
    op.drop_column("sesiones", "familia")
    op.drop_column("sesiones", "motivo")
    op.drop_column("sesiones", "revocado_en")
