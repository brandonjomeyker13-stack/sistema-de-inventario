"""Normalizar los códigos UPC-A de 12 dígitos a EAN-13.

Un código de 12 dígitos y ese mismo con un cero delante son el MISMO
producto: UPC-A es el subconjunto americano de EAN-13. Distintos lectores
devuelven una forma u otra, así que sin normalizar el mismo producto se
registra dos veces y el tendero acaba con el inventario partido en dos
sin entender por qué.

Se convierte a EAN-13, que es la forma larga y de la que siempre se puede
volver atrás quitando el cero.

Los códigos de otras longitudes no se tocan: EAN-8 es su propio estándar,
y Code 128 o las etiquetas propias no tienen forma canónica que imponer.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _es_upc(codigo: str | None) -> bool:
    return bool(codigo) and codigo.isdigit() and len(codigo) == 12


def upgrade() -> None:
    conexion = op.get_bind()

    # Se filtra en Python y no en SQL a propósito: comprobar "solo
    # dígitos" necesita expresiones regulares, que Postgres y SQLite
    # escriben distinto. Con el volumen de estas tablas da igual.
    productos = conexion.execute(
        sa.text("SELECT id, codigo_barras FROM productos WHERE codigo_barras IS NOT NULL")
    ).fetchall()
    for p in productos:
        if _es_upc(p.codigo_barras):
            conexion.execute(
                sa.text("UPDATE productos SET codigo_barras = :nuevo WHERE id = :id"),
                {"nuevo": "0" + p.codigo_barras, "id": p.id},
            )

    items = conexion.execute(
        sa.text(
            "SELECT id, codigo_pendiente FROM canasta_items "
            "WHERE codigo_pendiente IS NOT NULL"
        )
    ).fetchall()
    for i in items:
        if _es_upc(i.codigo_pendiente):
            conexion.execute(
                sa.text("UPDATE canasta_items SET codigo_pendiente = :nuevo WHERE id = :id"),
                {"nuevo": "0" + i.codigo_pendiente, "id": i.id},
            )


def downgrade() -> None:
    """Quita el cero inicial de los EAN-13 que en realidad son UPC-A.

    No es exactamente inverso: un EAN-13 legítimo que empiece por cero
    también se acortaría. En la práctica no existen —el prefijo 0 está
    reservado justo para los UPC-A— pero conviene saberlo antes de
    ejecutarlo.
    """
    conexion = op.get_bind()
    for tabla, columna in (("productos", "codigo_barras"), ("canasta_items", "codigo_pendiente")):
        filas = conexion.execute(
            sa.text(f"SELECT id, {columna} AS cod FROM {tabla} WHERE {columna} IS NOT NULL")
        ).fetchall()
        for f in filas:
            if f.cod.isdigit() and len(f.cod) == 13 and f.cod.startswith("0"):
                conexion.execute(
                    sa.text(f"UPDATE {tabla} SET {columna} = :nuevo WHERE id = :id"),
                    {"nuevo": f.cod[1:], "id": f.id},
                )
