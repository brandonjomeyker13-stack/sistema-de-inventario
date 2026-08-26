"""
app/models/token_password.py — Tokens de un solo uso para restablecer la
contraseña.

Tabla aparte de `tokens_verificacion` aunque tenga la misma forma, y es
una decisión de seguridad, no de estilo: con dos tablas es
ESTRUCTURALMENTE IMPOSIBLE que un token emitido para confirmar un correo
sirva para cambiar una contraseña. Con una sola tabla y una columna
`tipo`, esa garantía dependería de acordarse de filtrar por `tipo` en
cada consulta — y basta olvidarlo una vez.

La caducidad es mucho más corta que la de verificación (1 hora frente a
24): un enlace que cambia la contraseña es mucho más peligroso si queda
olvidado en una bandeja de entrada.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey

from app.database.session import Base


class TokenPassword(Base):
    __tablename__ = "tokens_password"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expira_en = Column(DateTime(timezone=True), nullable=False)
    usado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
