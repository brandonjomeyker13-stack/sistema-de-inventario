"""
app/models/venta.py — Tabla de ventas.

`nombre_producto` se guarda como copia (snapshot) del nombre al momento
de la venta, no solo el producto_id: si el producto se renombra o se
borra después, el historial de ventas sigue siendo legible tal como
ocurrió, sin depender de un JOIN que podría cambiar de significado.

`fecha` es un string 'YYYY-MM-DD' en la hora LOCAL del negocio (se genera
en el servicio, no con NOW() de Postgres que trabaja en UTC) — así una
venta de las 11pm no se cuela en el reporte del día siguiente.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey

from app.database.session import Base


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    producto_id = Column(String(36), ForeignKey("productos.id"), nullable=True)
    nombre_producto = Column(String(255), nullable=False)
    cantidad_vendida = Column(Integer, nullable=False)
    precio_venta_total = Column(Float, nullable=False)
    ganancia_total = Column(Float, nullable=False)
    fecha = Column(String(10), nullable=False, index=True)
    eliminado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))