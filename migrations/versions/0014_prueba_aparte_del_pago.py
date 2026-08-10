"""Separa el periodo de prueba del pago.

Antes, la 0013 escribía una fecha de cortesía en `suscripcion_hasta`, y
esa columna acababa significando dos cosas a la vez: "pagó hasta" y "está
probando". Así no se puede saber quién es cliente.

Ahora:
  - `suscripcion_hasta`: SOLO "pagado hasta". NULL = nunca ha pagado.
    Es la columna que se edita a mano cuando alguien paga.
  - `prueba_hasta`: fin de los días gratis. Se escribe una vez al crear la
    cuenta y no se toca más.

Que la prueba tenga columna propia resuelve un caso concreto: si a alguien
que ya pagó se le borra la suscripción, NO recupera los días gratis. Su
`prueba_hasta` está en el pasado y nada la revive. Calculándola desde
`creado_en` no sería así — una cuenta joven que ya pagó recuperaría la
prueba al limpiarle el pago.

Revision ID: 0014
Revises: 0013
"""
from datetime import timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIAS_DE_PRUEBA = 4


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("prueba_hasta", sa.String(length=10), nullable=True))

    # A cada cuenta que ya existe se le pone la prueba que le habría
    # correspondido: desde su fecha de creación. Para las cuentas viejas
    # eso cae en el pasado, que es lo correcto — ya usaron su periodo.
    conexion = op.get_bind()
    filas = conexion.execute(sa.text("SELECT id, creado_en FROM usuarios")).fetchall()
    for f in filas:
        if not f.creado_en:
            continue
        hasta = (f.creado_en.date() + timedelta(days=DIAS_DE_PRUEBA)).strftime("%Y-%m-%d")
        conexion.execute(
            sa.text("UPDATE usuarios SET prueba_hasta = :hasta WHERE id = :id"),
            {"hasta": hasta, "id": f.id},
        )

    # NO se limpia `suscripcion_hasta`. La 0013 escribió ahí una fecha de
    # cortesía que ahora significaría "pagó", lo cual es falso — pero
    # borrarla dejaría esas cuentas sin acceso de golpe, y esa decisión es
    # de quien lleva el negocio, no de una migración. Para limpiarlas:
    #     UPDATE usuarios SET suscripcion_hasta = NULL;
    # y después poner la fecha a mano solo a quien de verdad pagó.


def downgrade() -> None:
    op.drop_column("usuarios", "prueba_hasta")
