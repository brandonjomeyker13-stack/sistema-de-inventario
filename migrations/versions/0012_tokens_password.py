"""Tokens para restablecer la contraseña ("olvidé mi contraseña").

Tabla aparte de tokens_verificacion aunque la forma sea idéntica: así es
imposible por construcción que un token emitido para confirmar un correo
sirva para cambiar una contraseña. Con una sola tabla y una columna
`tipo`, esa garantía dependería de recordar el filtro en cada consulta.

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tokens_password",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tokens_password_usuario_id", "tokens_password", ["usuario_id"])
    op.create_index("ix_tokens_password_token", "tokens_password", ["token"], unique=True)


def downgrade() -> None:
    op.drop_table("tokens_password")
