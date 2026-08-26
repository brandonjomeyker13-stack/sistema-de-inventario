"""
app/models/token_verificacion.py — Tokens de un solo uso para verificar el
correo del usuario al registrarse.

Se guarda en tabla aparte (no como un campo suelto en Usuario) porque el
mismo patrón sirve después para "olvidé mi contraseña" (otra tabla igual,
tokens_reset_password) y porque permite generar un token nuevo si el
usuario pide reenviar el correo, sin perder el historial de intentos.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey

from app.database.session import Base


class TokenVerificacion(Base):
    __tablename__ = "tokens_verificacion"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expira_en = Column(DateTime(timezone=True), nullable=False)
    usado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))