"""La bitácora sobrevive al borrado de una cuenta.

POR QUÉ ESTA MIGRACIÓN EXISTE APARTE

Este cambio debería haber estado en la 0025, que creó `registros_admin`.
Pero la 0025 ya había corrido en producción, y una migración aplicada es
historia: editarla no tiene ningún efecto —Alembic no vuelve a ejecutar una
revisión ya registrada— y además hace que el archivo mienta sobre lo que
realmente pasó en la base.

El síntoma de haberlo intentado fue este, al abrir el panel de admin:

    column registros_admin.descripcion does not exist

El modelo pedía una columna que la migración aplicada nunca creó.

QUÉ CAMBIA

  · `descripcion` — quién era el negocio, en texto: "Papelería Sol
    (sol@correo.com)". Sin esto, una fila con el id en NULL diría "alguien
    le hizo algo a alguien".

  · `admin_id` y `usuario_id` pasan a admitir NULL, y sus llaves foráneas a
    ON DELETE SET NULL.

Lo segundo es lo importante y es una corrección de fondo: con las llaves en
CASCADE, borrar una cuenta se llevaría por delante el registro de que la
borraste — justo el que más falta hace después. Y con las columnas en NOT
NULL, un SET NULL fallaría al intentarlo, así que el borrado de una cuenta
con historial habría reventado.

Es idempotente a propósito: corre igual si la 0026 ya dejó las llaves en
SET NULL o si no llegó a correr.

Revision ID: 0027
Revises: 0026
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LLAVES = (("admin_id", "registros_admin_admin_id_fkey"),
          ("usuario_id", "registros_admin_usuario_id_fkey"))


def upgrade() -> None:
    dialecto = op.get_bind().dialect.name

    if dialecto != "postgresql":
        # SQLite sí sabe agregar una columna, y hay que hacerlo: la prueba
        # de deriva construye una base corriendo las migraciones y la
        # compara con los modelos. Sin esto, ahí faltaría `descripcion` y la
        # prueba fallaría con razón.
        #
        # Lo que SÍ se salta en SQLite es cambiar las llaves foráneas y la
        # obligatoriedad: eso exige recrear la tabla entera, y la prueba de
        # deriva no compara ninguna de las dos cosas.
        op.add_column(
            "registros_admin", sa.Column("descripcion", sa.String(length=255), nullable=True),
        )
        return

    # IF NOT EXISTS porque una base creada desde cero después del arreglo ya
    # la tiene: sin esto, esta migración fallaría justo en el entorno donde
    # todo estaba bien.
    op.execute(
        "ALTER TABLE registros_admin "
        "ADD COLUMN IF NOT EXISTS descripcion VARCHAR(255)"
    )

    for columna, nombre in LLAVES:
        # El orden importa: primero se relaja NOT NULL, porque una llave con
        # SET NULL sobre una columna obligatoria no puede cumplirse — y el
        # fallo aparecería tarde, al borrar la primera cuenta con historial.
        op.execute(f"ALTER TABLE registros_admin ALTER COLUMN {columna} DROP NOT NULL")

        op.execute(f'ALTER TABLE registros_admin DROP CONSTRAINT IF EXISTS "{nombre}"')
        op.execute(
            f'ALTER TABLE registros_admin ADD CONSTRAINT "{nombre}" '
            f"FOREIGN KEY ({columna}) REFERENCES usuarios (id) ON DELETE SET NULL"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        with op.batch_alter_table("registros_admin") as batch:
            batch.drop_column("descripcion")
        return

    # Las filas huérfanas impedirían volver a NOT NULL, así que se van. Son
    # justamente las de cuentas ya borradas: sin la columna que las
    # identifica, esa historia no se puede leer de todos modos.
    op.execute("DELETE FROM registros_admin WHERE admin_id IS NULL OR usuario_id IS NULL")

    for columna, nombre in LLAVES:
        op.execute(f'ALTER TABLE registros_admin DROP CONSTRAINT IF EXISTS "{nombre}"')
        op.execute(
            f'ALTER TABLE registros_admin ADD CONSTRAINT "{nombre}" '
            f"FOREIGN KEY ({columna}) REFERENCES usuarios (id)"
        )
        op.execute(f"ALTER TABLE registros_admin ALTER COLUMN {columna} SET NOT NULL")

    op.execute("ALTER TABLE registros_admin DROP COLUMN IF EXISTS descripcion")
