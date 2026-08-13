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

# Por qué se cerró una sesión. Solo la rotación normal admite la ventana
# de gracia; las demás cierran de verdad y al instante.
MOTIVO_ROTACION = "rotacion"      # se cambió por un token nuevo (lo normal)
MOTIVO_LOGOUT = "logout"          # el usuario cerró sesión
MOTIVO_PASSWORD = "password"      # se restableció la contraseña
MOTIVO_SEGURIDAD = "seguridad"    # apareció un token ya rotado: posible copia


class Sesion(Base):
    __tablename__ = "sesiones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expira_en = Column(DateTime(timezone=True), nullable=False)
    revocado = Column(Boolean, nullable=False, default=False)

    # CUÁNDO se revocó, no solo si. Sirve para distinguir dos cosas que se
    # ven idénticas en la base pero no lo son:
    #
    #   - Revocado hace 2 segundos: es la carrera de dos pestañas que
    #     refrescaron a la vez. Normal, no es un ataque.
    #   - Revocado hace 3 días y alguien lo vuelve a presentar: ese token
    #     lo tiene alguien que no debería.
    #
    # Ver sesion_repository.SEGUNDOS_DE_GRACIA.
    revocado_en = Column(DateTime(timezone=True), nullable=True)

    # POR QUÉ se cerró. No es solo para el historial: la ventana de gracia
    # solo aplica a MOTIVO_ROTACION.
    #
    # Sin esta distinción había un agujero. Al detectar un token robado se
    # cierra la familia entera, y eso ponía `revocado_en = ahora` en todas
    # sus sesiones — es decir, las metía dentro de la ventana de gracia, y
    # el token robado seguía funcionando treinta segundos más JUSTO
    # después de haberlo detectado.
    #
    # También sirve para responderle a un tendero que llama diciendo que
    # lo sacaron: la fila dice si fue él cerrando sesión, un cambio de
    # contraseña, o algo raro.
    motivo = Column(String(20), nullable=True)

    # Todas las sesiones que salen de un mismo inicio de sesión comparten
    # familia: al refrescar, la sesión nueva hereda la del token que la
    # generó. Así, si se detecta un token robado, se puede cortar SOLO esa
    # cadena y no echar al tendero de sus otros dispositivos.
    familia = Column(String(36), nullable=True, index=True)

    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))