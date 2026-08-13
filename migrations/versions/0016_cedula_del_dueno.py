"""Crea la columna `usuarios.cedula`, que el modelo declaraba sin migración.

Esto tumbó producción. La columna se añadió a `app/models/usuario.py` sin
crear la migración correspondiente, así que SQLAlchemy la pedía en cada
SELECT de usuarios y Postgres respondía:

    column usuarios.cedula does not exist

Es decir: nadie podía iniciar sesión. Y `alembic upgrade head` corre en
cada arranque en Render, pero no podía arreglarlo — no había ninguna
migración que crear.

La columna se AÑADE en lugar de quitarla del modelo porque en Colombia la
cédula del dueño hace falta para facturar, y borrarla en silencio
supondría decidir por el negocio. Nace nullable: las cuentas que ya
existen no la tienen y no se la puede inventar.

Ojo: hoy no la usa nadie más — ni un schema, ni un servicio, ni un
endpoint. Si al final no se va a pedir, lo correcto es quitarla del modelo
Y añadir una migración que la elimine, no dejarla a medias otra vez.

Revision ID: 0016
Revises: 0015
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("cedula", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("usuarios", "cedula")
