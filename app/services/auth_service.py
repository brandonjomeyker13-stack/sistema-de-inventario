"""
app/services/auth_service.py — Reglas de negocio de autenticación.

Además de emitir credenciales (login, refresh), este archivo ahora:
  - Genera y valida el token de verificación de correo al registrarse.
  - Registra cada refresh token emitido en la tabla `sesiones`, para poder
    revocarlo (logout real) y para que un refresh_token robado deje de
    servir en cuanto se detecte y se cierre esa sesión.
  - Rota el refresh token en cada /refresh: el anterior queda revocado y
    se emite uno nuevo. Así, si alguien más también tiene una copia del
    refresh token viejo, dejará de funcionar en cuanto el legítimo lo use.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import correo
from app.core.config import settings
from app.core.exceptions import ErrorNegocio, CredencialesInvalidas
from app.core.google import verificar_id_token
from app.models.sesion import MOTIVO_LOGOUT
from app.core.security import (
    hash_password, verificar_password, crear_access_token, crear_refresh_token,
    decodificar_token, generar_token_verificacion, hash_token,
)
from app.repositories import (
    usuario_repository, token_verificacion_repository, token_password_repository,
    sesion_repository,
)


def _enviar_verificacion(db: Session, usuario) -> bool:
    """Genera un token nuevo y manda el correo. Devuelve si salió.

    El enlace apunta al FRONTEND, no a la API: quien abre un correo espera
    aterrizar en una pantalla que le diga "listo", no en un JSON. El
    frontend recibe el token y llama a GET /auth/verificar/{token}.
    """
    token = generar_token_verificacion()
    token_verificacion_repository.crear(db, usuario.id, token)

    enlace = f"{settings.URL_FRONTEND.rstrip('/')}/verificar?token={token}"
    return correo.enviar(
        usuario.email,
        "Confirma tu correo",
        correo.plantilla_verificacion(usuario.nombre_negocio, enlace),
    )


def registrar(db: Session, email: str, password: str, nombre_negocio: str):
    existente = usuario_repository.obtener_por_email(db, email)
    if existente:
        if existente.password_hash is None:
            # Cuenta creada con Google. Decírselo evita que la persona se
            # quede intentando adivinar una contraseña que nunca puso.
            raise ErrorNegocio(
                "Ya tienes una cuenta con ese correo, creada con Google. "
                "Entra con Google y desde ahí puedes ponerle una contraseña."
            )
        raise ErrorNegocio("Ya existe una cuenta registrada con ese correo")

    usuario = usuario_repository.crear(db, email, hash_password(password), nombre_negocio)

    # Si el correo falla, la cuenta ya está creada y el usuario puede
    # pedir el reenvío. Perder un registro porque el proveedor de correo
    # tuvo un mal minuto sería mucho peor.
    _enviar_verificacion(db, usuario)

    return usuario


def reenviar_verificacion(db: Session, email: str) -> None:
    """Manda otra vez el correo de verificación.

    No revela si el correo existe ni si ya estaba verificado: responde
    igual en todos los casos. Si contestara distinto, este endpoint sería
    una forma cómoda de averiguar qué correos tienen cuenta.
    """
    usuario = usuario_repository.obtener_por_email(db, email)
    if usuario and not usuario.email_verificado:
        _enviar_verificacion(db, usuario)


def verificar_email(db: Session, token: str) -> None:
    registro = token_verificacion_repository.obtener_valido(db, token)
    if not registro:
        raise ErrorNegocio("El enlace de verificación es inválido o ya expiró")

    usuario = usuario_repository.obtener_por_id(db, registro.usuario_id)
    if not usuario:
        raise ErrorNegocio("El enlace de verificación es inválido o ya expiró")

    usuario_repository.marcar_email_verificado(db, usuario)
    token_verificacion_repository.marcar_usado(db, registro)


def iniciar_sesion(
    db: Session, email: str, password: str,
    ip: str | None = None, user_agent: str | None = None,
) -> dict:
    usuario = usuario_repository.obtener_por_email(db, email)

    if usuario and usuario.password_hash is None:
        # Cuenta de Google sin contraseña definida. Mensaje explícito: si
        # devolviéramos "correo o contraseña incorrectos", la persona
        # intentaría una y otra vez algo que no existe.
        raise CredencialesInvalidas(
            "Esta cuenta se creó con Google. Entra con Google, o define una "
            "contraseña desde tu perfil para poder entrar de las dos formas."
        )

    if not usuario or not verificar_password(password, usuario.password_hash):
        raise CredencialesInvalidas("Correo o contraseña incorrectos")
    if not usuario.activo:
        raise CredencialesInvalidas("Esta cuenta está deshabilitada")
    # El correo sin verificar YA NO impide entrar. Se comprueba al
    # escribir (ver app/api/deps.py), con unos días de margen: quien acaba
    # de registrarse quiere probar la aplicación, y mandarlo a su bandeja
    # antes de dejarle ver nada es la forma más rápida de perderlo.
    #
    # Pasado el plazo la cuenta queda en solo lectura, no fuera. Sigue
    # entrando y viendo sus datos; lo que no puede es registrar.

    return _emitir_credenciales(db, usuario, ip, user_agent)


def refrescar(db: Session, refresh_token: str) -> dict:
    """Cambia un refresh token por un par nuevo, rotando el anterior.

    La parte delicada es qué hacer cuando llega un token YA ROTADO. Hay
    dos casos que en la base se ven igual y no son lo mismo:

      - Llegó hace un instante: son dos pestañas del mismo tendero que
        refrescaron a la vez. Pasa constantemente y no es un ataque. Antes
        la segunda petición recibía un 401 y sacaba al tendero de la
        sesión en mitad de una venta.
      - Llegó días después: ese token lo tiene alguien más. Entonces se
        corta la cadena entera (ver revocar_familia).

    Los distingue `revocado_en` con una ventana de gracia de segundos.
    """
    try:
        payload = decodificar_token(refresh_token)
    except Exception:
        raise CredencialesInvalidas("El refresh token es inválido o expiró")

    if payload.get("tipo") != "refresh":
        raise CredencialesInvalidas("Token inválido: se esperaba un refresh token")

    sesion = sesion_repository.obtener_por_hash(db, hash_token(refresh_token))
    if not sesion:
        raise CredencialesInvalidas("La sesión fue cerrada o ya no es válida")

    if sesion_repository.esta_caducada(sesion):
        raise CredencialesInvalidas("La sesión expiró. Vuelve a entrar.")

    if sesion.revocado and not sesion_repository.en_ventana_de_gracia(sesion):
        # Token rotado hace rato y presentado otra vez: hay una copia por
        # ahí. Se cierra esta cadena y solo esta; los demás dispositivos
        # del tendero tienen su propia familia y siguen dentro.
        sesion_repository.revocar_familia(db, sesion.familia)
        raise CredencialesInvalidas(
            "Esta sesión se cerró por seguridad. Vuelve a iniciar sesión."
        )

    usuario = usuario_repository.obtener_por_id(db, payload["sub"])
    if not usuario or not usuario.activo:
        raise CredencialesInvalidas("Usuario no encontrado o deshabilitado")

    # Rotación: el refresh usado queda inválido de inmediato, se emite uno
    # nuevo. Si ya estaba revocado (la carrera de arriba) no se vuelve a
    # tocar: cambiarle `revocado_en` alargaría la ventana de gracia cada
    # vez que se reintenta, y con reintentos automáticos eso la haría
    # infinita.
    if not sesion.revocado:
        sesion_repository.revocar(db, sesion)

    nuevo_access = crear_access_token(usuario.id)
    nuevo_refresh = crear_refresh_token(usuario.id)
    sesion_repository.crear(
        db, usuario.id, hash_token(nuevo_refresh),
        expira_en=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip=sesion.ip, user_agent=sesion.user_agent,
        # Hereda la cadena: así se puede cortar de raíz si aparece un token
        # robado, sin echar al tendero de sus otros dispositivos.
        familia=sesion.familia,
    )

    return {"access_token": nuevo_access, "refresh_token": nuevo_refresh}


def recuperar_password(db: Session, email: str) -> None:
    """Manda el enlace para restablecer la contraseña.

    No dice si el correo existe: responde igual siempre. Si distinguiera,
    cualquiera podría averiguar qué correos tienen cuenta probando uno a
    uno.

    Funciona también para cuentas creadas con Google que aún no tienen
    contraseña: restablecerla es equivalente a ponerla por primera vez, y
    quien controla el correo ya podía entrar con Google de todos modos.
    """
    usuario = usuario_repository.obtener_por_email(db, email)
    if not usuario or not usuario.activo:
        return

    token = generar_token_verificacion()
    token_password_repository.crear(db, usuario.id, token)

    enlace = f"{settings.URL_FRONTEND.rstrip('/')}/restablecer?token={token}"
    correo.enviar(
        usuario.email,
        "Restablecer tu contraseña",
        correo.plantilla_recuperacion(usuario.nombre_negocio, enlace),
    )


def restablecer_password(db: Session, token: str, password_nueva: str) -> None:
    """Cambia la contraseña usando el token del correo.

    Y CIERRA TODAS LAS SESIONES ABIERTAS. Esa es la parte que de verdad
    importa: si alguien se metió a la cuenta, cambiar la contraseña sin
    revocar sus sesiones no lo echa — su refresh token seguiría sirviendo
    durante días.
    """
    registro = token_password_repository.obtener_valido(db, token)
    if not registro:
        raise ErrorNegocio("El enlace no es válido o ya expiró. Pide uno nuevo.")

    usuario = usuario_repository.obtener_por_id(db, registro.usuario_id)
    if not usuario or not usuario.activo:
        raise ErrorNegocio("El enlace no es válido o ya expiró. Pide uno nuevo.")

    usuario_repository.actualizar_password(db, usuario, hash_password(password_nueva))
    token_password_repository.marcar_usado(db, registro)
    sesion_repository.revocar_todas(db, usuario.id)

    # Quien recupera la contraseña por correo demuestra que controla ese
    # buzón, así que el correo queda verificado de paso.
    if not usuario.email_verificado:
        usuario_repository.marcar_email_verificado(db, usuario)


def _emitir_credenciales(db: Session, usuario, ip=None, user_agent=None) -> dict:
    """Crea el par de tokens y registra la sesión.

    Único camino por el que se emiten credenciales: lo usan el login con
    contraseña y el de Google. Duplicarlo sería garantizar que una de las
    dos copias se quede atrás.
    """
    # Aprovecha que ya se está escribiendo en esta tabla para barrer las
    # sesiones muertas de este usuario. Iniciar sesión es poco frecuente,
    # así que la limpieza no estorba a nadie y evita tener que montar una
    # tarea programada solo para esto.
    sesion_repository.purgar(db, usuario.id)

    access_token = crear_access_token(usuario.id)
    refresh_token = crear_refresh_token(usuario.id)
    sesion_repository.crear(
        db, usuario.id, hash_token(refresh_token),
        expira_en=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip=ip, user_agent=user_agent,
    )
    return {"access_token": access_token, "refresh_token": refresh_token}


def iniciar_sesion_google(
    db: Session, id_token: str, nombre_negocio: str | None = None,
    ip: str | None = None, user_agent: str | None = None,
) -> dict:
    """Entra (o crea la cuenta) con Google.

    El token se verifica contra Google en el servidor: nunca se confía en
    un correo que mande el frontend. Ver app/core/google.py.

    Si ya existe una cuenta con ese correo, se ENLAZA en vez de fallar.
    Es seguro porque Google ya confirmó que ese correo es de quien está
    entrando; sin el enlace, alguien que se registró con contraseña y
    luego pulsa "entrar con Google" se encontraría con un error absurdo
    sobre su propia cuenta.
    """
    datos = verificar_id_token(id_token)
    email = datos["email"]

    usuario = usuario_repository.obtener_por_email(db, email)
    es_nuevo = usuario is None

    if es_nuevo:
        usuario = usuario_repository.crear(
            db, email, None,
            # Google da el nombre de la persona, no el del negocio. Sirve
            # de valor provisional; el frontend debe pedir el real, y por
            # eso la respuesta avisa con perfil_completo.
            nombre_negocio or datos.get("name") or email.split("@")[0],
        )
    elif not usuario.activo:
        raise CredencialesInvalidas("Esta cuenta está deshabilitada")

    # Google ya verificó el correo (se comprueba email_verified en
    # google.py), así que no tiene sentido pedirle al usuario que lo
    # verifique otra vez con un enlace.
    if not usuario.email_verificado:
        usuario_repository.marcar_email_verificado(db, usuario)

    credenciales = _emitir_credenciales(db, usuario, ip, user_agent)
    credenciales.update({
        "es_nuevo": es_nuevo,
        # El frontend usa estos dos para decidir si mostrar la pantalla de
        # "completa tu perfil" después de entrar.
        "requiere_password": usuario.password_hash is None,
        "perfil_completo": bool(usuario.sector) and not es_nuevo,
    })
    return credenciales


def definir_password(db: Session, usuario_id: str, password_nueva: str) -> None:
    """Pone contraseña a una cuenta que no tenía (las creadas con Google).

    Es distinto de cambiar la contraseña: ahí se exige la actual, y aquí
    no hay ninguna. Por eso son dos operaciones separadas — si fueran la
    misma, habría que hacer opcional la contraseña actual, y eso deja la
    puerta abierta a cambiar la de cualquiera que la tenga.
    """
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise CredencialesInvalidas("Usuario no encontrado")
    if usuario.password_hash is not None:
        raise ErrorNegocio(
            "Esta cuenta ya tiene contraseña. Para cambiarla usa la opción de "
            "cambiar contraseña, que pide la actual."
        )
    usuario_repository.actualizar_password(db, usuario, hash_password(password_nueva))


def cerrar_sesion(db: Session, refresh_token: str) -> None:
    """Logout real: revoca la sesión asociada a este refresh_token para
    que no pueda usarse de nuevo. Es intencionalmente permisivo si el
    token ya no existe o ya estaba revocado (logout debe poder llamarse
    más de una vez sin error, y no debe filtrar si la sesión existía)."""
    sesion = sesion_repository.obtener_activa_por_hash(db, hash_token(refresh_token))
    if sesion:
        # Motivo explícito: una sesión cerrada por el usuario NO entra en
        # la ventana de gracia de la rotación. Si entrara, el token
        # seguiría valiendo medio minuto después de pulsar "cerrar sesión"
        # — que es justo cuando alguien lo pulsa en un computador ajeno.
        sesion_repository.revocar(db, sesion, motivo=MOTIVO_LOGOUT)