"""Reglas de borrado: qué se va con el padre y qué sobrevive.

Hasta ahora ninguna llave foránea decía qué hacer al borrar la fila a la que
apunta, y eso significaba "no dejes borrarla". Consecuencia práctica:
eliminar una cuenta de prueba desde Supabase era imposible sin ir tabla por
tabla, en el orden correcto, a mano.

Pero "en cascada para todo" habría sido peor que el problema. Hay dos
grupos, y confundirlos destruye datos:

CASCADE — el hijo no significa nada sin el padre:

    usuarios  -> productos, ventas, clientes, categorías, canastas,
                 movimientos, sesiones, tokens, bitácora
    ventas    -> venta_items, abonos
    canastas  -> canasta_items
    productos -> producto_codigos

SET NULL — el hijo SOBREVIVE y solo pierde la referencia:

    productos -> venta_items.producto_id      <- LA IMPORTANTE
    productos -> ventas.producto_id
    productos -> canasta_items.producto_id
    clientes  -> ventas.cliente_id
    categorías-> productos.categoria_id
    ventas    -> movimientos.venta_id, canastas.venta_id
    usuarios  -> registros_admin.usuario_id, .admin_id

La bitácora va en SET NULL a propósito: con CASCADE, borrar una cuenta
se llevaría por delante el registro de que la borraste. Por eso guarda
también el nombre y el correo en texto.

LA QUE MÁS IMPORTA es `venta_items.producto_id`. Con CASCADE, borrar un
producto borraría las líneas de todas las ventas que lo incluyeron: los
ingresos y la ganancia del mes cambiarían solos, sin error y sin aviso. Por
eso `venta_items` guarda copia del nombre y del precio — para sobrevivir
exactamente a esto. La venta ocurrió y esa plata entró; el producto puede
desaparecer, la venta no.

`movimientos.producto_id` sí va en CASCADE porque es NOT NULL y un asiento
sin producto no significa nada. En la práctica no se dispara: la aplicación
nunca borra productos de verdad, los marca como eliminados.

SOLO POSTGRESQL. En SQLite las tablas se crean desde los modelos, que ya
llevan las reglas; alterarlas aquí obligaría a recrear doce tablas para
nada.

Revision ID: 0026
Revises: 0025
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, columna, tabla_destino, acción)
LLAVES = [
    ("abonos", "venta_id", "ventas", "CASCADE"),
    ("canastas", "usuario_id", "usuarios", "CASCADE"),
    ("canastas", "venta_id", "ventas", "SET NULL"),
    ("canasta_items", "canasta_id", "canastas", "CASCADE"),
    ("canasta_items", "producto_id", "productos", "SET NULL"),
    ("categorias", "usuario_id", "usuarios", "CASCADE"),
    ("clientes", "usuario_id", "usuarios", "CASCADE"),
    ("movimientos_inventario", "usuario_id", "usuarios", "CASCADE"),
    ("movimientos_inventario", "producto_id", "productos", "CASCADE"),
    ("movimientos_inventario", "venta_id", "ventas", "SET NULL"),
    ("productos", "usuario_id", "usuarios", "CASCADE"),
    ("productos", "categoria_id", "categorias", "SET NULL"),
    ("producto_codigos", "usuario_id", "usuarios", "CASCADE"),
    ("producto_codigos", "producto_id", "productos", "CASCADE"),
    ("registros_admin", "admin_id", "usuarios", "SET NULL"),
    ("registros_admin", "usuario_id", "usuarios", "SET NULL"),
    ("sesiones", "usuario_id", "usuarios", "CASCADE"),
    ("tokens_password", "usuario_id", "usuarios", "CASCADE"),
    ("tokens_verificacion", "usuario_id", "usuarios", "CASCADE"),
    ("ventas", "usuario_id", "usuarios", "CASCADE"),
    ("ventas", "producto_id", "productos", "SET NULL"),
    ("ventas", "cliente_id", "clientes", "SET NULL"),
    ("venta_items", "venta_id", "ventas", "CASCADE"),
    ("venta_items", "producto_id", "productos", "SET NULL"),
]


def _rehacer(tabla: str, columna: str, destino: str, accion: str | None) -> None:
    """Cambia la regla de una llave foránea.

    PostgreSQL no permite modificar una llave existente: hay que soltarla y
    volver a crearla. El nombre sigue la convención automática de Postgres
    ({tabla}_{columna}_fkey), y se usa IF EXISTS porque esa base se ha
    editado a mano y no se puede dar por seguro qué hay.
    """
    nombre = f"{tabla}_{columna}_fkey"
    op.execute(f'ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS "{nombre}"')

    regla = f" ON DELETE {accion}" if accion else ""
    op.execute(
        f'ALTER TABLE {tabla} ADD CONSTRAINT "{nombre}" '
        f"FOREIGN KEY ({columna}) REFERENCES {destino} (id){regla}"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for tabla, columna, destino, accion in LLAVES:
        _rehacer(tabla, columna, destino, accion)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Se vuelve a la regla implícita anterior: sin ON DELETE, que en
    # PostgreSQL significa NO ACTION — no deja borrar el padre mientras
    # tenga hijos.
    for tabla, columna, destino, _ in LLAVES:
        _rehacer(tabla, columna, destino, None)
