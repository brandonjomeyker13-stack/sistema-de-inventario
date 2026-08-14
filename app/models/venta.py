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
    # Hasta cuándo tiene el cliente para pagar. Lo decide el tendero en
    # cada fiado; nullable porque hay fiados sin fecha acordada ("cuando
    # puedas"), y forzar una inventada sería peor que no tenerla.
    fecha_vencimiento = Column(String(10), nullable=True)
    eliminado = Column(Boolean, nullable=False, default=False)

    # Identificador que manda el frontend para que reintentar una venta no
    # la registre dos veces.
    #
    # El caso: el tendero cobra, la petición sale, y la señal se cae antes
    # de que llegue la respuesta. El frontend no sabe si la venta se
    # guardó o no. Si reintenta, sin esta columna se registra otra vez: se
    # descuenta el stock dos veces y se suma plata que nadie pagó. Y es el
    # error más difícil de notar, porque parece un buen día.
    #
    # Con la clave, el reintento devuelve la MISMA venta. La garantía no
    # está en el código sino en el índice único de más abajo: dos
    # peticiones simultáneas con la misma clave chocan en la base, que es
    # el único árbitro que no se equivoca.
    #
    # Nullable porque las ventas anteriores no la tienen, y porque un
    # tendero vendiendo desde el PC con buena conexión no la necesita.
    clave_idempotencia = Column(String(64), nullable=True)

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

# La clave de idempotencia es única DENTRO de cada negocio, no en toda la
# tabla: dos tiendas distintas podrían generar el mismo identificador sin
# que eso signifique nada, y hacerlo global permitiría que una tienda
# bloqueara la venta de otra mandando claves a propósito.
#
# Este índice es lo que de verdad impide el duplicado. Comprobar antes
# "¿ya existe esta clave?" no basta: dos reintentos que llegan a la vez
# pasan los dos la comprobación y los dos insertan. La base es el único
# árbitro que no se equivoca; el código solo tiene que saber recoger el
# error y devolver la venta que ya estaba.
#
# Los NULL no chocan entre sí ni en Postgres ni en SQLite, así que las
# ventas sin clave conviven sin estorbarse.
Index(
    "uq_ventas_usuario_clave",
    Venta.usuario_id, Venta.clave_idempotencia,
    unique=True,
)

# Se importa al final para que la relación "VentaItem" de arriba pueda
# resolverse siempre que alguien importe Venta. Va aquí abajo y no en la
# cabecera porque venta_item.py referencia a Venta por su nombre.
from app.models.venta_item import VentaItem  # noqa: E402,F401
from app.models.abono import Abono  # noqa: E402,F401