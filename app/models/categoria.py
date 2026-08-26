"""
app/models/categoria.py — Categorías de producto, por negocio.

Se modela como tabla y no como un texto suelto en `productos` por una
razón práctica: escrito a mano acabas con "Bebidas", "bebidas" y
"Bevidas" conviviendo, y los filtros y reportes dejan de servir. Con
tabla, renombrar es una fila y no un UPDATE masivo.

Cada negocio tiene las suyas. Una tienda organiza por "Granos / Aseo /
Bebidas" y otra por lo que le sirva; no hay una lista universal que
imponerles.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index

from app.database.session import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(120), nullable=False)
    eliminado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Index(
    "uq_categoria_usuario_nombre_activo",
    Categoria.usuario_id, Categoria.nombre,
    unique=True,
    postgresql_where=Categoria.eliminado.is_(False),
)
