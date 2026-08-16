"""Guarda el nombre del producto en forma canónica para comparar duplicados.

El problema que resuelve: la comparación de nombres se hacía con `ILIKE`, y
ese operador se comporta DISTINTO según el motor cuando hay letras
acentuadas:

    'CAFÉ' contra 'Café'   ->  PostgreSQL: iguales    SQLite: distintos

Las pruebas corren en SQLite y producción en PostgreSQL, así que una prueba
podía pasar en local mientras el comportamiento real era otro. Es la peor
clase de fallo, el que solo aparece desplegado.

Y aparte, ninguno de los dos resolvía el caso más común de todos: un tendero
que ya tiene "Café" y escribe "cafe" sin tilde porque el teclado del celular
le estorba. Se creaba un producto nuevo y su stock quedaba partido en dos.

`nombre_clave` guarda el nombre en minúsculas, sin tildes y con los espacios
colapsados. Se calcula en Python (ver app/core/texto.py), así que las dos
bases se comportan igual. `nombre` sigue guardando lo que escribió el
tendero — es lo que se muestra en pantalla.

SIN ÍNDICE ÚNICO, A PROPÓSITO

Sería lo natural, pero es peligroso aquí: si algún negocio YA tiene "Cafe" y
"Café" como productos separados, crear el índice único haría fallar esta
migración y con ella el arranque del servicio. La protección contra
duplicados nuevos está en la aplicación (producto_repository.existe_nombre).

Para encontrar los duplicados que ya existan, después de aplicar esto:

    SELECT usuario_id, nombre_clave, count(*), string_agg(nombre, ' | ')
    FROM productos WHERE eliminado = false
    GROUP BY usuario_id, nombre_clave HAVING count(*) > 1;

Revision ID: 0021
Revises: 0020
"""
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clave(valor: str) -> str:
    """Copia de app/core/texto.clave_nombre.

    Se duplica a propósito: una migración debe seguir dando el mismo
    resultado dentro de un año, aunque el código de la aplicación cambie.
    Importar la función haría que este relleno dependiera de una versión
    futura del proyecto.
    """
    if not valor:
        return ""
    descompuesto = unicodedata.normalize("NFD", valor)
    sin_acentos = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(sin_acentos.split()).lower()


def upgrade() -> None:
    op.add_column("productos", sa.Column("nombre_clave", sa.String(length=255), nullable=True))
    op.create_index("ix_productos_nombre_clave", "productos", ["nombre_clave"])

    # Relleno de las filas que ya existen. Sin esto, todo producto anterior
    # tendría la clave en NULL y dejaría de encontrarse por nombre: la venta
    # por nombre y la importación no lo reconocerían, y la importación
    # crearía un duplicado de cada producto del inventario.
    conexion = op.get_bind()
    filas = conexion.execute(sa.text("SELECT id, nombre FROM productos")).fetchall()
    for f in filas:
        conexion.execute(
            sa.text("UPDATE productos SET nombre_clave = :clave WHERE id = :id"),
            {"clave": _clave(f.nombre), "id": f.id},
        )


def downgrade() -> None:
    op.drop_index("ix_productos_nombre_clave", table_name="productos")
    op.drop_column("productos", "nombre_clave")
