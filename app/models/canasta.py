"""
app/models/canasta.py — La venta en curso, compartida entre dispositivos.

Existe para un caso concreto: el tendero atiende en el PC, pero la webcam
de un portátil es pésima leyendo códigos de barras. Con esto, el celular
hace de lector y el PC muestra la cuenta.

Dos navegadores en dos dispositivos no pueden hablarse entre ellos, así
que el carrito tiene que vivir en el servidor. Eso es todo lo que es esta
tabla: un carrito con dueño y fecha de caducidad.

No confundir con `ventas`. Una canasta es efímera y se puede editar; una
venta ya ocurrió y es historia. Al cobrar, la canasta se convierte en
venta y se cierra.

Los ítems NO guardan copia del nombre ni del precio, al revés que
`venta_items`. Es a propósito: mientras la venta está en curso quieres el
precio actual, no el de hace cinco minutos. La foto del momento se toma
al cobrar.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database.session import Base

# Estados posibles de una canasta.
ABIERTA = "abierta"
COBRADA = "cobrada"

# Para qué se abrió la canasta. La máquina de emparejar el celular con el
# PC es la misma en los dos casos —token, caducidad, polling—; lo único
# que cambia es qué pasa con lo escaneado y cómo se trata un código que
# no está en el catálogo:
#
#   VENTA:      un código desconocido es un error, no se puede vender algo
#               que no existe.
#   INVENTARIO: un código desconocido es lo esperado, es justo lo que se
#               viene a dar de alta.
#
# Tener un solo mecanismo con dos propósitos evita mantener dos veces el
# mismo control de acceso, que es donde se acumulan los errores.
PROPOSITO_VENTA = "venta"
PROPOSITO_INVENTARIO = "inventario"
PROPOSITOS = (PROPOSITO_VENTA, PROPOSITO_INVENTARIO)


class Canasta(Base):
    __tablename__ = "canastas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)

    # Credencial del celular para esta canasta y solo esta. NO es un JWT:
    # si le pasáramos la sesión completa por la URL del QR, cualquiera que
    # viera esa pantalla se llevaría la cuenta entera. Esto solo permite
    # leer y agregar ítems a este carrito.
    token_celular = Column(String(64), unique=True, nullable=False, index=True)

    estado = Column(String(20), nullable=False, default=ABIERTA)
    proposito = Column(String(20), nullable=False, default=PROPOSITO_VENTA)

    # Caducidad técnica, en UTC (no es una fecha de negocio como las de
    # ventas, así que no pasa por app/core/fechas.py). Se estira cada vez
    # que alguien toca la canasta: una venta puede tardar, pero un
    # carrito abandonado no debe quedar vivo para siempre.
    expira_en = Column(DateTime(timezone=True), nullable=False)

    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    venta_id = Column(String(36), ForeignKey("ventas.id", ondelete="SET NULL"), nullable=True)

    items = relationship(
        "CanastaItem",
        back_populates="canasta",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CanastaItem(Base):
    __tablename__ = "canasta_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    canasta_id = Column(String(36), ForeignKey("canastas.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable desde que existen las canastas de inventario: al dar de
    # alta mercancía se escanean códigos que todavía no son ningún
    # producto. La línea existe, el producto aún no.
    producto_id = Column(String(36), ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)
    # El código escaneado que no está en el catálogo. Se guarda para que
    # el PC pueda abrir el formulario de alta con el código ya puesto.
    codigo_pendiente = Column(String(64), nullable=True)
    cantidad = Column(Integer, nullable=False, default=1)
    agregado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    canasta = relationship("Canasta", back_populates="items")


# Un producto aparece una sola vez por canasta: escanearlo dos veces sube
# la cantidad en lugar de crear otra línea. Sin esto, una canasta con
# quince escaneos del mismo producto sería ilegible en pantalla.
Index(
    "uq_canasta_item_producto",
    CanastaItem.canasta_id, CanastaItem.producto_id,
    unique=True,
)

# Lo mismo para los códigos aún sin producto. Ambos índices conviven sin
# estorbarse porque tanto Postgres como SQLite tratan los NULL como
# distintos entre sí: las líneas pendientes tienen producto_id NULL y no
# chocan en el índice de arriba, y viceversa.
Index(
    "uq_canasta_item_codigo",
    CanastaItem.canasta_id, CanastaItem.codigo_pendiente,
    unique=True,
)
