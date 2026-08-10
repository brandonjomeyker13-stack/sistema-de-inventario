"""Sector del negocio.

La llave del análisis de mercado comparado que vendrá cuando haya
suficientes negocios por sector. Se empieza a recoger desde ya: un dato
que no se captura hoy no se puede reconstruir mañana.

Nullable porque las cuentas existentes no lo tienen. El frontend lo pide
al registrarse y ofrece completarlo a quien ya estaba.

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("sector", sa.String(length=50), nullable=True))
    op.create_index("ix_usuarios_sector", "usuarios", ["sector"])


def downgrade() -> None:
    op.drop_index("ix_usuarios_sector", table_name="usuarios")
    op.drop_column("usuarios", "sector")
