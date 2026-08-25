"""
app/models/producto_codigo.py — Los códigos de barras de un producto.

POR QUÉ UNA TABLA Y NO UNA COLUMNA

Una papelería vende cuadernos de cien hojas de tres marcas. Mismo tamaño,
mismo precio, mismo costo — para el tendero es UN producto, "cuadernos de
cien hojas", y así lo cuenta y así lo pide. Pero cada marca trae su propio
EAN impreso de fábrica.

Con un solo código por producto había que elegir entre dos cosas malas:

  · Tres productos separados. El stock se parte en tres, el ranking los
    muestra por separado, y "más vendidos" queda fragmentado en algo que no
    refleja lo que de verdad se vende.
  · Un producto con el código de una sola marca. Las otras dos no se pueden
    escanear, que es justo la función que más piden.

Es la distinción de siempre entre lo que TÚ vendes (un producto, con su
precio y su stock) y lo que el FABRICANTE etiqueta (un código por marca y
presentación). Cualquier sistema de punto de venta serio la tiene.

UNA SOLA FUENTE DE VERDAD

`productos.codigo_barras` desapareció. Estaría tentador dejarla como "el
código principal" y usar esta tabla solo para los extra, pero entonces la
misma verdad viviría en dos sitios y uno de los dos se quedaría atrás.

`ProductoOut` sigue exponiendo `codigo_barras` —el primero de la lista— para
que el frontend actual no se rompa, pero se calcula desde aquí.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Index

from app.database.session import Base


class ProductoCodigo(Base):
    __tablename__ = "producto_codigos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Denormalizado a propósito. Se podría llegar al negocio por el
    # producto, pero tenerlo aquí permite dos cosas que importan: el índice
    # único por negocio de más abajo, y que las consultas filtren por
    # usuario_id directamente, igual que todas las demás del proyecto.
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)

    producto_id = Column(
        String(36), ForeignKey("productos.id"), nullable=False, index=True,
    )

    # Ya normalizado (ver app/core/codigos.py): un UPC-A de 12 dígitos se
    # guarda como su EAN-13, para que el mismo producto leído por dos
    # lectores distintos siga siendo uno solo.
    codigo = Column(String(64), nullable=False)

    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Un código identifica a UN producto dentro de un negocio. Si el mismo
# código apuntara a dos, escanearlo sería ambiguo y la caja no sabría qué
# cobrar.
#
# Único por NEGOCIO y no global: dos tiendas venden el mismo arroz con el
# mismo EAN, y eso es justamente lo que hará comparables sus datos algún día.
Index(
    "uq_producto_codigo_usuario",
    ProductoCodigo.usuario_id, ProductoCodigo.codigo,
    unique=True,
)
