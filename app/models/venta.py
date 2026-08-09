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

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

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
    # Fiado: la mercancía salió pero el dinero no entró. `cliente_id` es
    # obligatorio cuando es_fiado es True (se valida en el servicio): una
    # deuda sin deudor no sirve de nada.
    cliente_id = Column(String(36), ForeignKey("clientes.id"), nullable=True, index=True)
    es_fiado = Column(Boolean, nullable=False, default=False)
    eliminado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # lazy="selectin": al listar las ventas de un día, SQLAlchemy trae
    # todos los ítems en UNA consulta extra en vez de una por venta.
    # Con lazy por defecto esto sería un N+1 silencioso.
    items = relationship(
        "VentaItem",
        back_populates="venta",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    abonos = relationship("Abono", cascade="all, delete-orphan", lazy="selectin")

    @property
    def total_abonado(self) -> float:
        return round(sum(a.monto for a in self.abonos), 2)

    @property
    def saldo_pendiente(self) -> float:
        """Lo que falta por cobrar. Se calcula, nunca se guarda: un saldo
        almacenado se desincroniza y el tendero acaba cobrando mal."""
        if not self.es_fiado:
            return 0.0
        return round(self.precio_venta_total - self.total_abonado, 2)


# Todas las consultas de reportes filtran por usuario y fecha a la vez
# (ver venta_repository.resumen_por_fechas), así que el índice compuesto
# es el que realmente se usa; los de columna suelta se quedan porque
# otras consultas los aprovechan.
Index("ix_ventas_usuario_fecha", Venta.usuario_id, Venta.fecha)

# Se importa al final para que la relación "VentaItem" de arriba pueda
# resolverse siempre que alguien importe Venta. Va aquí abajo y no en la
# cabecera porque venta_item.py referencia a Venta por su nombre.
from app.models.venta_item import VentaItem  # noqa: E402,F401
from app.models.abono import Abono  # noqa: E402,F401