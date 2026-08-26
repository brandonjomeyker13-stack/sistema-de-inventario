"""
app/models/cliente.py — Los clientes del negocio, sobre todo los que fían.

En una tienda de barrio, "cliente" no es quien compra: casi todos compran
y se van. Cliente registrado es aquel a quien le fías, y por eso esta
tabla existe — es la contraparte de la libreta de deudores.

Por eso el único campo obligatorio es el nombre. Un tendero no le va a
pedir el correo a doña Rosa; le apunta "Rosa la del 3B" y el teléfono si
acaso.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Index

from app.database.session import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(255), nullable=False)
    telefono = Column(String(64), nullable=True)
    # Plazo habitual de este cliente, en días. Sirve de valor por defecto
    # al fiarle, para no teclearlo cada vez: "Juan paga los viernes" se
    # convierte en dias_plazo=7 y ya no hay que acordarse.
    dias_plazo = Column(Integer, nullable=True)
    notas = Column(String(500), nullable=True)
    eliminado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Mismo criterio que en productos: nombres únicos dentro de un negocio,
# entre los vivos. Dos "Rosa" en la misma tienda serían un lío al cobrar.
Index(
    "uq_cliente_usuario_nombre_activo",
    Cliente.usuario_id, Cliente.nombre,
    unique=True,
    postgresql_where=Cliente.eliminado.is_(False),
)
