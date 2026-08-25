"""Un producto puede tener VARIOS códigos de barras.

El caso real: una papelería vende cuadernos de cien hojas de tres marcas.
Mismo tamaño, mismo precio, mismo costo — para el tendero es UN producto,
"cuadernos de cien hojas", y así lo cuenta y así lo pide al proveedor. Pero
cada marca trae su propio EAN impreso de fábrica.

Con un solo código por producto había que elegir entre dos cosas malas:
tres productos separados (el stock se parte en tres y el ranking queda
fragmentado), o un producto con el código de una sola marca (las otras dos
no se pueden escanear, que es justo la función que más piden).

Es la distinción de siempre entre lo que TÚ vendes —un producto, con su
precio y su stock— y lo que el FABRICANTE etiqueta —un código por marca.

QUÉ HACE ESTA MIGRACIÓN

  1. Crea `producto_codigos`, con índice único (usuario_id, codigo): un
     código sigue identificando a UN producto dentro de cada negocio.
  2. Mueve ahí los códigos que hoy están en `productos.codigo_barras`.
  3. Borra esa columna y su índice único.

UNA SOLA FUENTE DE VERDAD. Estaría tentador dejar la columna como "el
código principal" y usar la tabla solo para los extra, pero entonces la
misma verdad viviría en dos sitios y uno se quedaría atrás. `ProductoOut`
sigue exponiendo `codigo_barras` para que el frontend actual no se rompa,
pero ahora se calcula: es el primero de la lista.

OJO CON UNA DIFERENCIA DE COMPORTAMIENTO

El índice viejo era PARCIAL (`postgresql_where: eliminado = false`), así que
borrar un producto liberaba su código para otro. El nuevo no puede serlo,
porque `eliminado` vive en la otra tabla. Se conserva el comportamiento
desde el código: `producto_repository.eliminar()` ahora suelta los códigos
del producto al darlo de baja.

Por eso el traspaso de más abajo IGNORA los productos eliminados: sus
códigos ya estaban libres bajo la regla anterior, y traerlos ocuparía
códigos que el tendero puede querer reutilizar.

Revision ID: 0024
Revises: 0023
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "producto_codigos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("producto_id", sa.String(length=36), nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_producto_codigos_usuario_id", "producto_codigos", ["usuario_id"])
    op.create_index("ix_producto_codigos_producto_id", "producto_codigos", ["producto_id"])
    op.create_index(
        "uq_producto_codigo_usuario", "producto_codigos",
        ["usuario_id", "codigo"], unique=True,
    )

    # Traspaso. Solo de los productos VIVOS: ver el aviso de arriba.
    conexion = op.get_bind()
    filas = conexion.execute(sa.text(
        "SELECT id, usuario_id, codigo_barras FROM productos "
        "WHERE codigo_barras IS NOT NULL AND codigo_barras <> '' "
        "AND eliminado = false"
    )).fetchall()

    ahora = datetime.now(timezone.utc)
    for f in filas:
        conexion.execute(
            sa.text(
                "INSERT INTO producto_codigos (id, usuario_id, producto_id, codigo, creado_en) "
                "VALUES (:id, :usuario_id, :producto_id, :codigo, :creado_en)"
            ),
            {
                "id": str(uuid.uuid4()),
                "usuario_id": f.usuario_id,
                "producto_id": f.id,
                "codigo": f.codigo_barras,
                "creado_en": ahora,
            },
        )

    # El índice único viejo se quita ANTES de borrar la columna, y en los
    # DOS motores.
    #
    # Es imprescindible en SQLite y no es obvio: `batch_alter_table` recrea
    # la tabla entera copiando sus índices, así que si el índice sigue vivo
    # intenta recrearlo sobre una columna que se acaba de borrar y falla con
    # "no such column: codigo_barras".
    #
    # Con IF EXISTS porque en producción esa base se ha editado a mano y no
    # se puede dar por seguro qué hay.
    op.execute('DROP INDEX IF EXISTS "uq_producto_usuario_codigo_activo"')

    # batch_alter_table: SQLite no sabe hacer DROP COLUMN y necesita
    # recrear la tabla. En PostgreSQL es un ALTER normal.
    with op.batch_alter_table("productos") as batch:
        batch.drop_column("codigo_barras")


def downgrade() -> None:
    with op.batch_alter_table("productos") as batch:
        batch.add_column(sa.Column("codigo_barras", sa.String(length=64), nullable=True))

    # Se recrea el índice tal como lo dejó la 0003. No es opcional: el
    # downgrade de esa migración hace `drop_index` sobre él, y sin esto
    # bajar hasta el principio falla con "no such index".
    #
    # Es seguro que sea único: un código no puede estar en dos productos
    # (lo impide uq_producto_codigo_usuario), y como abajo se devuelve UNO
    # por producto, no puede haber repetidos. Los productos sin código
    # quedan en NULL y los NULL no chocan entre sí.
    op.create_index(
        "uq_producto_usuario_codigo_activo",
        "productos",
        ["usuario_id", "codigo_barras"],
        unique=True,
        postgresql_where=sa.text("eliminado = false"),
    )

    # Se devuelve UNO por producto: la columna no puede guardar más. Los
    # códigos de las otras marcas se pierden, que es la consecuencia
    # inevitable de volver a un modelo que no los admite.
    conexion = op.get_bind()
    filas = conexion.execute(sa.text(
        "SELECT producto_id, MIN(codigo) AS codigo FROM producto_codigos GROUP BY producto_id"
    )).fetchall()
    for f in filas:
        conexion.execute(
            sa.text("UPDATE productos SET codigo_barras = :codigo WHERE id = :id"),
            {"codigo": f.codigo, "id": f.producto_id},
        )

    op.drop_index("uq_producto_codigo_usuario", table_name="producto_codigos")
    op.drop_index("ix_producto_codigos_producto_id", table_name="producto_codigos")
    op.drop_index("ix_producto_codigos_usuario_id", table_name="producto_codigos")
    op.drop_table("producto_codigos")
