"""
app/models/registro_admin.py — Bitácora de lo que hacen los administradores.

Cambiar la fecha de suscripción de un negocio es mover dinero: decide si
ese cliente puede vender mañana o no. Y el proyecto lo llevan dos personas.

Sin esta tabla, el día que discrepen —"yo no le puse esa fecha", "a este ya
le habíamos cobrado"— no hay forma de saberlo. Con ella, cada cambio dice
quién, a quién, qué y cuándo.

No es desconfianza entre socios: es que la memoria de dos personas sobre
cincuenta clientes no coincide nunca, y discutirlo sin datos daña más la
sociedad que cualquier error.

SOLO SE ESCRIBE. Nada en el proyecto borra ni edita estas filas, y no hay
endpoint que lo permita. Una bitácora que se puede editar no es una
bitácora.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Index

from app.database.session import Base

# Qué se hizo. Lista cerrada: si mañana hay una acción nueva se agrega aquí,
# y así el panel puede traducirlas a español sin adivinar.
CAMBIO_SUSCRIPCION = "suscripcion"
CAMBIO_ACTIVO = "activo"
CAMBIO_ADMIN = "admin"

ACCIONES = (CAMBIO_SUSCRIPCION, CAMBIO_ACTIVO, CAMBIO_ADMIN)


class RegistroAdmin(Base):
    __tablename__ = "registros_admin"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Quién lo hizo.
    admin_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    # A quién se lo hizo.
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)

    accion = Column(String(20), nullable=False)

    # El antes y el después, como texto. Se guardan los DOS a propósito: con
    # solo el valor nuevo, una fila dice "le puso hasta el 30" pero no si
    # eso fue extenderle un mes o quitarle tres.
    valor_antes = Column(String(64), nullable=True)
    valor_despues = Column(String(64), nullable=True)

    # Por qué. Lo escribe el admin: "pagó por Nequi el 12", "cortesía por la
    # caída del sábado". Es lo que convierte la bitácora en algo que se
    # puede leer dentro de seis meses.
    nota = Column(String(255), nullable=True)

    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# El historial se pide casi siempre de un negocio concreto y en orden
# cronológico inverso ("¿qué le hemos hecho a esta cuenta?").
Index(
    "ix_registros_admin_usuario_fecha",
    RegistroAdmin.usuario_id, RegistroAdmin.creado_en,
)
