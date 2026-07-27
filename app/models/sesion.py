"""
app/models/sesion.py — Registro de refresh tokens emitidos, para poder
revocarlos.

Los access_token viven y mueren solos (duran minutos, no vale la pena
trackearlos). Los refresh_token sí se registran aquí: sin esto, un JWT de
refresh es válido hasta que expira sin que el servidor pueda "apagarlo"
antes — no hay forma de cerrar sesión de verdad ni de reaccionar a un
robo de sesión reportado por el usuario.

Nunca se guarda el refresh_token en texto plano, solo su hash (ver
app/core/security.py -> hash_token). Así, aunque alguien lea esta tabla,
no puede reconstruir un token válido a partir de la fila.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey

from app.database.session import Base


class Sesion(Base):
    __tablename__ = "sesiones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expira_en = Column(DateTime(timezone=True), nullable=False)
    revocado = Column(Boolean, nullable=False, default=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))