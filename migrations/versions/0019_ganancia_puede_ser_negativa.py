"""Quita la restricción que prohibía registrar una venta con pérdida.

La base de producción tenía un CHECK hecho A MANO en Supabase,
`ventas_ganancia_total_check`, que exigía ganancia_total >= 0. No lo creó
ninguna migración ni ningún modelo: se añadió directamente en el editor.

Lo que provocaba: un producto con el precio de venta por debajo del costo
—casi siempre porque se invirtieron los campos al crearlo— se guardaba sin
problema, y REVENTABA DESPUÉS al venderlo, con un error 500 y un traceback
de SQL. El tendero veía "error inesperado" al cobrar y no había forma de
saber que el problema era el precio de un producto.

Se quita, y no se reemplaza, por dos razones:

1. Vender por debajo del costo ES un hecho real del negocio: liquidar algo
   que se va a vencer, sacar mercancía dañada a mitad de precio, o una
   promoción gancho. Un libro de cuentas que no puede registrar una
   pérdida está roto — obligaría a falsear el costo para poder vender.

2. Una restricción de base de datos es el peor sitio para una regla de
   negocio: solo sabe decir "no", en forma de excepción, cuando la
   operación ya está a medio camino. La validación correcta va en el
   servicio, donde se puede explicar el problema y señalar el producto.
   Eso está en product_service.

Ojo: esta migración es la primera señal de un problema más amplio. La
migración 0001 se limitó a "sellar" (stamp) una base que ya había creado
`create_all`, así que producción puede tener MÁS objetos que ningún
archivo del proyecto declara. Para auditarlo:

    SELECT conname, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace AND contype = 'c';

Revision ID: 0019
Revises: 0018
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Se quita UNA y solo una.
#
# La auditoría de producción reveló diez restricciones hechas a mano, y
# nueve de ellas son correctas: los precios y las cantidades no pueden ser
# negativos, los nombres no pueden estar vacíos, la fecha tiene que tener
# el formato AAAA-MM-DD. Esas se conservan y se adoptan en la 0020.
#
# `ganancia_total >= 0` es la única equivocada, porque una pérdida SÍ es un
# dato real del negocio.
#
# En particular NO se toca `ventas_precio_venta_total_check`: los ingresos
# de una venta nunca pueden ser negativos. Un cero sí (un regalo, una
# muestra), y `>= 0` ya lo permite.
#
# DROP ... IF EXISTS no falla si la restricción no está, así que la
# migración es segura tanto en producción como en una base nueva.
RESTRICCION = ("ventas", "ventas_ganancia_total_check")


def upgrade() -> None:
    # SQLite no sabe quitar restricciones, y una base nueva nunca la tuvo
    # (ninguna migración la creó). Este arreglo es solo para la base que se
    # editó a mano.
    if op.get_bind().dialect.name != "postgresql":
        return

    tabla, nombre = RESTRICCION
    op.execute(f'ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS "{nombre}"')


def downgrade() -> None:
    # A propósito NO se vuelven a crear. Restaurarlas devolvería el fallo
    # que esta migración arregla: bajar de versión no debería reintroducir
    # un error 500 al cobrar.
    pass
