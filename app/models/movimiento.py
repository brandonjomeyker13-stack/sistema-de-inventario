"""
app/models/movimiento.py — El libro de movimientos del inventario.

Hasta ahora el stock solo se podía corregir editando la cantidad del
producto, y esa edición no dejaba rastro: si el lunes había 40 unidades y
el martes 12, no había forma de saber si se vendieron, se dañaron, o
alguien tecleó mal.

Cada fila es un cambio de existencias con su causa. `cantidad` va con
signo: una entrada suma, una venta o una merma restan, y un ajuste puede
ir en cualquier dirección. Así `stock_antes + cantidad == stock_despues`
siempre, y el libro se puede auditar sumando.

Se guardan `stock_antes` y `stock_despues` aunque sean derivables. Es
redundancia a propósito: si algún día un movimiento se pierde o llega
desordenado, esas dos columnas delatan el hueco. Sin ellas, un libro
descuadrado es indistinguible de uno correcto.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index

from app.database.session import Base

# Tipos de movimiento.
ENTRADA = "entrada"    # llegó mercancía del proveedor
VENTA = "venta"        # salió por una venta
MERMA = "merma"        # se dañó, venció o se rompió
AJUSTE = "ajuste"      # conteo físico: el stock real no era el del sistema
# La mercancía volvió porque se anuló la venta: el cliente la devolvió, o
# el tendero registró mal y lo está corrigiendo.
#
# Es un tipo propio y no una ENTRADA a propósito. Una entrada es mercancía
# que se COMPRÓ, y mezclarlas haría que el día que se anula una venta
# grande parezca un día de reposición del proveedor. Con tipo propio, el
# libro dice la verdad y las devoluciones se pueden contar aparte —
# muchas devoluciones seguidas del mismo producto son una señal.
DEVOLUCION = "devolucion"

TIPOS = (ENTRADA, VENTA, MERMA, AJUSTE, DEVOLUCION)


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    producto_id = Column(String(36), ForeignKey("productos.id", ondelete="CASCADE"), nullable=False, index=True)

    tipo = Column(String(20), nullable=False)
    # Con signo: +10 entró, -3 salió. stock_antes + cantidad = stock_despues.
    cantidad = Column(Integer, nullable=False)
    stock_antes = Column(Integer, nullable=False)
    stock_despues = Column(Integer, nullable=False)

    # Solo en entradas: a cuánto se compró esta vez. Permite ver cómo
    # sube el costo del proveedor con el tiempo, que es un dato que hoy
    # se pierde porque `productos.cuanto_costo` solo guarda el último.
    costo_unitario = Column(Float, nullable=True)

    motivo = Column(String(255), nullable=True)
    # Presente cuando el movimiento vino de una venta. Permite ir del
    # libro a la venta que lo causó sin adivinar por fecha.
    venta_id = Column(String(36), ForeignKey("ventas.id", ondelete="SET NULL"), nullable=True)

    # Fecha del negocio (ver app/core/fechas.py), no la del servidor.
    fecha = Column(String(10), nullable=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# El historial siempre se pide de un producto y en orden cronológico.
Index(
    "ix_movimientos_producto_fecha",
    MovimientoInventario.producto_id, MovimientoInventario.fecha,
)
