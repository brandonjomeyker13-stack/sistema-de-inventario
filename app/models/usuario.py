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
    # Nullable desde que existe el inicio de sesión con Google: una cuenta
    # creada así no tiene contraseña hasta que su dueño decide ponerle
    # una. Guardar un hash falso o una cadena vacía sería peor — habría
    # que acordarse en todos lados de que ese valor "no cuenta".
    password_hash = Column(String(255), nullable=True)
    nombre_negocio = Column(String(255), nullable=False)
    # Sector del negocio (ver app/core/sectores.py). Nullable porque las
    # cuentas que ya existen no lo tienen y no se les puede inventar. Se
    # recoge desde ya aunque el análisis comparado todavía no exista: los
    # datos que no capturas hoy no se recuperan después.
    sector = Column(String(50), nullable=True, index=True)
    activo = Column(Boolean, nullable=False, default=True)
    # Arranca en False: quien se registra con correo y contraseña tiene
    # que confirmar que ese correo es suyo. Estuvo en True mientras no
    # había forma de mandar el correo — ahora sí la hay.
    #
    # Que esto bloquee o no el login lo decide REQUERIR_EMAIL_VERIFICADO
    # (ver config.py y auth_service.iniciar_sesion), no este campo. Las
    # cuentas creadas con Google se marcan verificadas al entrar, porque
    # Google ya lo confirmó.
    email_verificado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))