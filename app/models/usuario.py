"""
app/models/usuario.py — Tabla de usuarios (dueños de negocio).

Cada usuario es, en la práctica, "un negocio" en este MVP (una cuenta =
una tienda). Productos y ventas siempre están atados a un usuario_id,
así que desde el día uno el sistema es multi-tenant: dos negocios nunca
pueden ver ni tocar los datos del otro.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime

from app.database.session import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nombre_negocio = Column(String(255), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))