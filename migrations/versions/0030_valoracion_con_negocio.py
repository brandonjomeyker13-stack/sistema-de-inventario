"""De qué negocio es cada calificación.

POR QUÉ NO ESTABA Y AHORA SÍ

La 0029 dejó esta tabla sin `usuario_id`, aplicando la misma regla que a
`consultas`: el panel no muestra los datos de negocio de nadie.

Era pasarse. `consultas` se recoge en silencio y ahí la regla es correcta.
Una calificación existe porque el dueño pulsó un botón pidiendo que la
revisáramos, y revisar una queja como "me dijo 3 y en verdad son 5" obliga a
ir a ver de dónde salió el 3. Sin saber qué cuenta fue, la queja se lee pero
no se puede comprobar, y por tanto no arregla nada.

Guardarlo tampoco expone nada nuevo: la respuesta que esta tabla ya guarda
lleva sus cifras. No saber de quién son no las escondía — solo impedía
usarlas.

SET NULL y no CASCADE: si la cuenta se borra, lo aprendido de su queja sigue
valiendo.

Revision ID: 0030
Revises: 0029
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable sin más: las filas que ya existan se quedan sin negocio, que
    # es la verdad —se guardaron cuando no se pedía—. Rellenarlas sería
    # inventar.
    op.add_column(
        "valoraciones",
        sa.Column("usuario_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_valoraciones_usuario_id", "valoraciones", ["usuario_id"])

    # SQLite no sabe agregar una llave foránea a una tabla existente sin
    # recrearla, y la prueba de deriva no compara llaves foráneas. En
    # Postgres, que es donde importa, sí se crea.
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "valoraciones_usuario_id_fkey", "valoraciones", "usuarios",
            ["usuario_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("valoraciones_usuario_id_fkey", "valoraciones", type_="foreignkey")

    op.drop_index("ix_valoraciones_usuario_id", table_name="valoraciones")
    with op.batch_alter_table("valoraciones") as batch:
        batch.drop_column("usuario_id")
