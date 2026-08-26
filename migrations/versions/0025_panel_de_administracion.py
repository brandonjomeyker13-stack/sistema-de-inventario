"""Panel de administración: quién es admin, y bitácora de lo que hace.

Hasta ahora, cobrarle a un cliente era entrar a Supabase y editarle la fecha
a mano. Eso tiene tres problemas: es fácil equivocarse de fila, no queda
rastro de quién lo hizo, y obliga a darle acceso a la base entera a quien
solo necesita cobrar.

DOS COSAS

`usuarios.es_admin` — quién puede entrar al panel. Arranca en false para
TODOS, incluido quien lo despliegue: no hay forma de que esta migración
sepa qué cuenta es la de los dueños. El primero se marca a mano, una sola
vez:

    UPDATE usuarios SET es_admin = true WHERE email = 'tu@correo.com';

y desde ahí el panel permite marcar al socio sin volver a tocar la base.

`registros_admin` — la bitácora. Cambiar la fecha de suscripción de un
negocio decide si ese cliente puede vender mañana, y el proyecto lo llevan
dos personas. Sin registro de quién cambió qué, el día que discrepen —"yo
no le puse esa fecha", "a este ya le habíamos cobrado"— no hay forma de
saberlo. Se guardan el valor de antes y el de después: con solo el nuevo,
una fila dice "le puso hasta el 30" pero no si eso fue extenderle un mes o
quitarle tres.

Las dos llaves van con SET NULL y no CASCADE, y las columnas admiten NULL:
es lo que permite que la bitácora sobreviva a borrar una cuenta. Con
CASCADE, eliminar un negocio se llevaría por delante el registro de que lo
eliminaste. Por eso también se guarda `descripcion`, con el nombre y el
correo en texto: una fila con el id en NULL diría "alguien le hizo algo a
alguien".

Revision ID: 0025
Revises: 0024
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default: la columna es NOT NULL y las cuentas que ya existen
    # necesitan valor. El default de SQLAlchemy solo actúa al insertar desde
    # la aplicación, no sobre lo que ya está guardado.
    op.add_column(
        "usuarios",
        sa.Column("es_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Se retira el default de la base: a partir de aquí el valor lo decide la
    # aplicación. SQLite no sabe alterar columnas y allí sobra.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("usuarios", "es_admin", server_default=None)

    op.create_table(
        "registros_admin",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("admin_id", sa.String(length=36), nullable=True),
        sa.Column("usuario_id", sa.String(length=36), nullable=True),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("accion", sa.String(length=20), nullable=False),
        sa.Column("valor_antes", sa.String(length=64), nullable=True),
        sa.Column("valor_despues", sa.String(length=64), nullable=True),
        sa.Column("nota", sa.String(length=255), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registros_admin_admin_id", "registros_admin", ["admin_id"])
    op.create_index("ix_registros_admin_usuario_id", "registros_admin", ["usuario_id"])
    op.create_index(
        "ix_registros_admin_usuario_fecha", "registros_admin",
        ["usuario_id", "creado_en"],
    )


def downgrade() -> None:
    op.drop_index("ix_registros_admin_usuario_fecha", table_name="registros_admin")
    op.drop_index("ix_registros_admin_usuario_id", table_name="registros_admin")
    op.drop_index("ix_registros_admin_admin_id", table_name="registros_admin")
    op.drop_table("registros_admin")
    op.drop_column("usuarios", "es_admin")
