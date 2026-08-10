"""Fecha hasta la que la cuenta puede usar la aplicación completa.

El cobro se controla a mano por ahora: se edita esta columna en Supabase
cuando alguien paga. Una fecha y no un booleano — un booleano habría que
apagarlo a mano cada mes por cliente, y el día que se olvide, alguien usa
gratis medio año.

A las cuentas que YA existen se les da el periodo de prueba desde hoy: no
sería razonable dejar vencidas de golpe a las que estaban usando la app.

Revision ID: 0013
Revises: 0012
"""
from datetime import date, timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIAS_DE_CORTESIA = 30


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("suscripcion_hasta", sa.String(length=10), nullable=True))

    # Cortesía para las cuentas existentes. Si se dejaran en NULL, la
    # próxima vez que entraran se encontrarían la aplicación en solo
    # lectura sin haber hecho nada — mala forma de estrenar la función.
    hasta = (date.today() + timedelta(days=DIAS_DE_CORTESIA)).strftime("%Y-%m-%d")
    op.execute(
        sa.text("UPDATE usuarios SET suscripcion_hasta = :hasta").bindparams(hasta=hasta)
    )


def downgrade() -> None:
    op.drop_column("usuarios", "suscripcion_hasta")
