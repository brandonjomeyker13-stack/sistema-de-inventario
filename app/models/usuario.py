"""
app/models/usuario.py — Tabla de usuarios (dueños de negocio).

Cada usuario es, en la práctica, "un negocio" en este MVP (una cuenta =
una tienda). Productos y ventas siempre están atados a un usuario_id,
así que desde el día uno el sistema es multi-tenant: dos negocios nunca
pueden ver ni tocar los datos del otro.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Integer, CheckConstraint

from app.database.session import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    # Existía solo en la base de producción, puesta a mano. Y descubrió un
    # fallo real: el schema pedía `min_length=1`, que "   " cumple, pero el
    # repositorio le hace .strip() antes de guardar y llegaba vacío. En
    # producción eso era un error 500 al registrarse — una caída del
    # servidor por un campo rellenado con la barra espaciadora.
    #
    # El arreglo de verdad está en los schemas (auth.py y usuario.py), que
    # ahora devuelven un 422 explicando el campo. Esto es la última red.
    __table_args__ = (
        CheckConstraint(
            "length(trim(nombre_negocio)) > 0", name="usuarios_nombre_negocio_check",
        ),
    )

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

    # Hasta cuándo puede usar la aplicación completa. Se edita a mano en
    # la base cuando alguien paga (por ahora no hay cobro automático).
    #
    # Es una FECHA y no un booleano a propósito: con `es_premium = true`
    # habría que acordarse de apagarlo cada mes, cliente por cliente, y el
    # día que se olvide alguien usa gratis medio año. Una fecha vence sola.
    #
    # NULL = nunca ha pagado. Ver app/api/deps.py.
    suscripcion_hasta = Column(String(10), nullable=True)

    # Fin del periodo gratis. Se escribe UNA SOLA VEZ al crear la cuenta y
    # no se vuelve a tocar.
    #
    # Va en su propia columna, y no calculada desde `creado_en`, por un
    # caso concreto: si alguien pagó y luego se le borra la fecha de
    # suscripción, no puede volver a tener los días gratis. Con la prueba
    # en una columna propia eso es imposible — ya está en el pasado y
    # nada la revive. Derivarla de `creado_en` haría que una cuenta joven
    # que ya pagó recuperara la prueba al limpiarle el pago.
    prueba_hasta = Column(String(10), nullable=True)
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
    cedula = Column(String(20), nullable=True)

    # Umbral de stock bajo para los productos que no tienen uno propio.
    #
    # Arranca en 5 y no en NULL a propósito: así la lista de compra sirve
    # desde el primer día, sin que nadie tenga que configurar nada. Una
    # función que exige configuración previa no la usa nadie.
    stock_minimo_defecto = Column(Integer, nullable=False, default=5)

    # Quién puede entrar al panel de administración (nosotros, no los
    # clientes). Da acceso a ver el estado de TODAS las cuentas y a cambiar
    # sus fechas de suscripción.
    #
    # NUNCA se pone desde la API. No aparece en ningún schema de entrada —
    # ni en el registro, ni al editar el perfil, ni en el login con Google.
    # Si algún día se colara en uno, cualquiera podría hacerse
    # administrador con una petición.
    #
    # El primer admin se marca a mano en Supabase:
    #     UPDATE usuarios SET es_admin = true WHERE email = '...';
    # y desde ahí se pueden marcar los demás desde el panel.
    es_admin = Column(Boolean, nullable=False, default=False)