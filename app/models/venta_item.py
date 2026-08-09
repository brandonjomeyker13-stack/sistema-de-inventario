"""
app/models/venta_item.py — Las líneas de una venta.

Hasta ahora una venta era un producto. Eso no aguanta el caso real de una
tienda: el cliente pone cinco cosas en el mostrador y eso es UNA venta,
no cinco. Y en cuanto entre el lector de código de barras, escanear una
canasta es multi-ítem por definición.

`ventas` pasa a ser la cabecera (quién, cuándo, cuánto en total) y esta
tabla guarda el detalle. Los campos `nombre_producto` y `cantidad_vendida`
que siguen en `ventas` no desaparecieron: ahora son un resumen calculado,
para que el frontend actual no se rompa mientras se actualiza.

Igual que en `ventas`, `nombre_producto` y `precio_unitario` se guardan
como copia del momento de la venta. Si mañana sube el precio del arroz,
las ventas de ayer siguen contando lo que realmente se cobró.
"""

import uuid

from sqlalchemy import Column, String, Integer, Float, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database.session import Base


class VentaItem(Base):
    __tablename__ = "venta_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venta_id = Column(String(36), ForeignKey("ventas.id"), nullable=False, index=True)
    producto_id = Column(String(36), ForeignKey("productos.id"), nullable=True)
    nombre_producto = Column(String(255), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    precio_total = Column(Float, nullable=False)
    ganancia_total = Column(Float, nullable=False)

    venta = relationship("Venta", back_populates="items")


# Para responder "¿qué tanto se vende este producto?" sin recorrer la
# tabla entera. Es la consulta base del análisis de mercado.
Index("ix_venta_items_producto", VentaItem.producto_id)
