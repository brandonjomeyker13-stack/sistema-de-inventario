"""La contraseña pasa a ser opcional.

Con el inicio de sesión de Google, una cuenta puede existir sin
contraseña: se crea al entrar con Google y su dueño le pone una después,
si quiere poder entrar también de la forma normal.

La alternativa —guardar un hash inventado— obligaría a recordar en cada
punto del código que ese valor no cuenta como contraseña. Un NULL lo dice
solo y el motor lo hace cumplir.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch para que SQLite también pueda (recrea la tabla por debajo);
    # en Postgres se traduce a un ALTER normal e instantáneo.
    with op.batch_alter_table("usuarios") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    """Ojo: fallará si hay cuentas de Google sin contraseña definida.

    No se les inventa un hash para poder volver atrás: eso crearía
    contraseñas que nadie conoce y que nadie podría usar ni restablecer.
    Si hace falta bajar de versión, primero hay que decidir qué pasa con
    esas cuentas.
    """
    with op.batch_alter_table("usuarios") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
