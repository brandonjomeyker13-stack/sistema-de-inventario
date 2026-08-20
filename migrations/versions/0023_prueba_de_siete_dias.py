"""La prueba gratis pasa de 4 a 7 días, también para quien ya se registró.

Cambiar `DIAS_DE_PRUEBA` en config solo afecta a las cuentas NUEVAS: la
fecha se calcula al registrarse y se guarda en `usuarios.prueba_hasta`, que
después no se vuelve a tocar. Sin esta migración, quien se registró ayer
seguiría con 4 días y quien se registre mañana tendría 7 — misma aplicación,
trato distinto, y sin ninguna forma de explicárselo.

Se le suman 3 días a cada `prueba_hasta` que exista, que es exactamente lo
que habrían tenido de haberse registrado bajo la regla nueva
(`creado_en + 7` en vez de `creado_en + 4`).

DOS COSAS QUE CONVIENE SABER

1. También se ajustan las pruebas que YA vencieron. Una que terminó
   anteayer revive por un día. Es deliberado: la alternativa —dejar fuera a
   quien se registró justo antes del cambio— es peor, y son los primeros
   clientes, los que más conviene cuidar.

2. Se ajustan también las cuentas que ya pagaron. Ahí no cambia nada
   mientras la suscripción esté al día, porque `estado_acceso` mira primero
   el pago. El único efecto posible es que a un cliente muy reciente cuya
   suscripción venza en los próximos días le queden un par de días de
   prueba por detrás. Es un caso raro y a favor del cliente.

La fecha se recalcula en Python y no con aritmética de SQL porque
`prueba_hasta` es una columna de TEXTO (String(10)), no un DATE: sumarle un
intervalo requeriría convertir de ida y vuelta con sintaxis propia de
PostgreSQL, y estas migraciones también corren en SQLite.

Revision ID: 0023
Revises: 0022
"""
from datetime import datetime, timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORMATO = "%Y-%m-%d"
DIAS_ANTES = 4
DIAS_AHORA = 7
DIAS_EXTRA = DIAS_AHORA - DIAS_ANTES


def _mover(fecha: str, dias: int) -> str | None:
    """Suma días a una fecha 'AAAA-MM-DD'. None si no se puede leer.

    Tolerante a propósito: `prueba_hasta` es texto y alguna fila pudo
    quedar con algo raro (una edición a mano en Supabase, una cadena
    vacía). Una fila ilegible se deja como está en vez de tumbar la
    migración y con ella el arranque del servicio.
    """
    try:
        base = datetime.strptime((fecha or "").strip(), FORMATO)
    except ValueError:
        return None
    return (base + timedelta(days=dias)).strftime(FORMATO)


def upgrade() -> None:
    conexion = op.get_bind()
    filas = conexion.execute(
        sa.text("SELECT id, prueba_hasta FROM usuarios WHERE prueba_hasta IS NOT NULL")
    ).fetchall()

    for f in filas:
        nueva = _mover(f.prueba_hasta, DIAS_EXTRA)
        if nueva is None:
            continue
        conexion.execute(
            sa.text("UPDATE usuarios SET prueba_hasta = :hasta WHERE id = :id"),
            {"hasta": nueva, "id": f.id},
        )


def downgrade() -> None:
    conexion = op.get_bind()
    filas = conexion.execute(
        sa.text("SELECT id, prueba_hasta FROM usuarios WHERE prueba_hasta IS NOT NULL")
    ).fetchall()

    for f in filas:
        nueva = _mover(f.prueba_hasta, -DIAS_EXTRA)
        if nueva is None:
            continue
        conexion.execute(
            sa.text("UPDATE usuarios SET prueba_hasta = :hasta WHERE id = :id"),
            {"hasta": nueva, "id": f.id},
        )
