"""
app/models/producto.py — Tabla de productos.

`eliminado` es borrado suave: nunca se borra una fila físicamente. Un
producto "eliminado" simplemente deja de aparecer en el inventario, pero
sigue existiendo para que las ventas históricas que lo referencian no
queden huérfanas.

El índice único parcial (solo entre productos NO eliminados, por
usuario) es lo que te deja: (a) que dos negocios distintos repitan
nombres de producto sin problema, y (b) que un mismo negocio reutilice
el nombre de un producto que ya había borrado.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index

from app.database.session import Base


class Producto(Base):
    __tablename__ = "productos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    nombre = Column(String(255), nullable=False)
    # EAN-13 y similares. Nullable a propósito: la mayoría de productos de
    # una tienda de barrio (el arroz a granel, los huevos sueltos) no
    # tienen código, y obligar a inventárselo sería peor que no tenerlo.
    codigo_barras = Column(String(64), nullable=True)
    categoria_id = Column(String(36), ForeignKey("categorias.id"), nullable=True, index=True)
    cantidad = Column(Integer, nullable=False, default=0)
    precio = Column(Float, nullable=False, default=0)
    cuanto_costo = Column(Float, nullable=False, default=0)
    eliminado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actualizado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# Índice único parcial: solo se aplica en Postgres (postgresql_where). En
# la validación real contra duplicados también hay una comprobación a
# nivel de aplicación en el servicio (defensa en profundidad), así que
# esto es la última barrera, no la única.
Index(
    "uq_producto_usuario_nombre_activo",
    Producto.usuario_id, Producto.nombre,
    unique=True,
    postgresql_where=Producto.eliminado.is_(False),
)

# Mismo criterio para el código de barras: único dentro de un negocio,
# entre los productos vivos. Dos tiendas distintas pueden (y van a) tener
# el mismo EAN, eso es justamente lo que hará comparables sus datos.
# El índice ignora las filas con codigo_barras NULL, así que los muchos
# productos sin código no chocan entre sí.
Index(
    "uq_producto_usuario_codigo_activo",
    Producto.usuario_id, Producto.codigo_barras,
    unique=True,
    postgresql_where=Producto.eliminado.is_(False),
)

