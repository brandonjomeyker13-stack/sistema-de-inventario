"""
app/api/deps.py — Dependencias reutilizables entre rutas.

`obtener_usuario_actual` es lo que convierte "Authorization: Bearer <token>"
en un objeto Usuario real, validado contra la base de datos (no solo el
token). Cualquier ruta que reciba `usuario: Usuario = Depends(obtener_usuario_actual)`
queda protegida automáticamente.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database.session import get_db
from datetime import datetime, timezone

from app.core.config import settings
from app.core.exceptions import SuscripcionVencida, CorreoSinVerificar
from app.core.fechas import FORMATO_FECHA, fecha_valida, hoy_local
from app.core.security import decodificar_token
from app.repositories import usuario_repository
from app.models.usuario import Usuario

_esquema_bearer = HTTPBearer()
# auto_error=False: sin token no falla, devuelve None. Lo usa la canasta
# compartida, donde el celular se identifica con el token del QR en vez
# de con una sesión.
_esquema_bearer_opcional = HTTPBearer(auto_error=False)


def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(_esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        payload = decodificar_token(credenciales.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    if payload.get("tipo") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Se esperaba un access token")

    usuario = usuario_repository.obtener_por_id(db, payload.get("sub", ""))
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido")

    return usuario


def _dias_hasta(fecha: str) -> int:
    return (
        datetime.strptime(fecha, FORMATO_FECHA).date()
        - datetime.strptime(hoy_local(), FORMATO_FECHA).date()
    ).days


def estado_acceso(usuario: Usuario) -> dict:
    """Si la cuenta puede usar la aplicación completa, y por qué.

    Dos vías, en este orden:

      1. PAGÓ: `suscripcion_hasta` tiene una fecha que no ha pasado.
      2. PRUEBA: `prueba_hasta` no ha pasado.

    Son columnas separadas a propósito. `suscripcion_hasta` significa una
    sola cosa —"pagado hasta"— y por eso se lee de un vistazo en Supabase:
    NULL es "nunca ha pagado". Y `prueba_hasta` se escribe una vez al
    registrarse y no se toca nunca más, así que **borrar la suscripción de
    alguien no le devuelve los días gratis**: su prueba ya quedó en el
    pasado y nada la revive.

    Las fechas se comparan como texto porque el formato 'YYYY-MM-DD'
    ordena igual como cadena que como fecha. Y se usa la fecha del
    NEGOCIO, no la del servidor: si no, en Colombia el plan vencería a
    las 7 de la tarde del último día.
    """
    # `fecha_valida` devuelve None ante cualquier cosa que no sea una
    # fecha utilizable: la cadena vacía que guarda Supabase al limpiar una
    # celda, y también un dedazo tipo '31/12/2026'. Esto último no es
    # teórico — es una columna que se edita a mano, y antes una fecha mal
    # escrita hacía que TODAS las rutas protegidas de esa cuenta
    # respondieran 500 sin decir por qué.
    pagado = fecha_valida(usuario.suscripcion_hasta)
    prueba = fecha_valida(usuario.prueba_hasta)

    if pagado and pagado >= hoy_local():
        return {
            "activa": True, "en_prueba": False,
            "dias_restantes": max(_dias_hasta(pagado), 0),
        }

    if prueba and prueba >= hoy_local():
        return {
            "activa": True, "en_prueba": True,
            "dias_restantes": max(_dias_hasta(prueba), 0),
        }

    return {"activa": False, "en_prueba": False, "dias_restantes": 0}


def suscripcion_activa(usuario: Usuario) -> bool:
    return estado_acceso(usuario)["activa"]


def dias_para_verificar(usuario: Usuario) -> int:
    """Días que le quedan para confirmar el correo. 0 si ya se le acabaron.

    Cuenta desde que se creó la cuenta. `creado_en` puede venir sin zona
    horaria según el motor, así que se asume UTC cuando falta.
    """
    if usuario.email_verificado or not usuario.creado_en:
        return 0
    creado = usuario.creado_en
    if creado.tzinfo is None:
        creado = creado.replace(tzinfo=timezone.utc)
    transcurridos = (datetime.now(timezone.utc) - creado).days
    return max(settings.DIAS_GRACIA_VERIFICACION - transcurridos, 0)


def verificacion_al_dia(usuario: Usuario) -> bool:
    """Si el correo está verificado, o todavía está dentro del plazo."""
    if not settings.REQUERIR_EMAIL_VERIFICADO:
        return True
    if usuario.email_verificado:
        return True
    return dias_para_verificar(usuario) > 0


def exigir_suscripcion_activa(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
) -> Usuario:
    """Igual que obtener_usuario_actual, pero exige poder escribir.

    Se pone en las rutas que ESCRIBEN (vender, registrar, editar) y en las
    de análisis. Las de solo lectura se quedan con obtener_usuario_actual:
    una cuenta restringida sigue viendo sus productos, sus ventas y sus
    fiados.

    Ese límite es deliberado. Quitarle a un tendero el acceso a su propio
    inventario no lo hace pagar ni verificar: lo hace no volver. Que no
    pueda vender duele lo justo y se revierte solo en cuanto resuelve.

    Son DOS condiciones independientes y se comprueban por separado:
    alguien puede haber pagado sin verificar el correo, y al revés. Cada
    una lanza su propia excepción para que el frontend mande al usuario a
    la pantalla que le corresponde.
    """
    if not verificacion_al_dia(usuario_actual):
        raise CorreoSinVerificar(
            "Se acabó el plazo para confirmar tu correo. Puedes seguir viendo "
            "tus datos, pero para registrar ventas necesitas confirmarlo. "
            "Pídenos el enlace de nuevo si no te llegó."
        )

    if not suscripcion_activa(usuario_actual):
        # Mensaje distinto según haya pagado antes o no: a quien se le
        # acabó la prueba hay que explicarle que empieza a pagar, y a
        # quien ya era cliente, que renueve. Decirle "renueva" a quien
        # nunca pagó suena a error del sistema.
        if usuario_actual.suscripcion_hasta:
            mensaje = (
                "Tu suscripción venció. Puedes seguir viendo tus productos y tu "
                "historial, pero para registrar ventas necesitas renovar."
            )
        else:
            mensaje = (
                "Se acabaron tus días de prueba. Puedes seguir viendo tus "
                "productos y tu historial, pero para registrar ventas hay que "
                "activar el plan."
            )
        raise SuscripcionVencida(mensaje)
    return usuario_actual


def exigir_admin(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
) -> Usuario:
    """Solo para nosotros. Protege TODO el panel de administración.

    Esta es la única dependencia del proyecto que abre la puerta a los
    datos de OTROS negocios, y por eso conviene entender qué la hace
    distinta.

    En todo lo demás, la seguridad no depende de una comprobación: depende
    de que cada consulta lleve `usuario_id` y solo pueda alcanzar las filas
    de quien pregunta. Aunque alguien se colara, no habría nada que ver.
    Aquí no: aquí la única barrera es este `if`.

    Por eso no hay ningún endpoint de admin sin esta dependencia, y por eso
    `es_admin` no se puede escribir desde ninguna parte de la API.

    NO exige suscripción al día ni correo verificado: un administrador
    tiene que poder entrar precisamente cuando hay que arreglar cuentas, y
    dejarnos fuera del panel por nuestra propia fecha de pago sería
    absurdo.
    """
    if not usuario_actual.es_admin:
        # 403 y no 404: las rutas del panel son conocidas, esconder su
        # existencia no protege de nada y sí complica depurar por qué a
        # alguien no le funciona.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta sección es solo para administradores",
        )
    return usuario_actual


def obtener_usuario_opcional(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer_opcional),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Igual que la anterior, pero devuelve None en vez de rechazar.

    Para endpoints que aceptan dos formas de identificarse. Nunca la uses
    en una ruta que solo admita sesión: ahí un None silencioso convertiría
    una ruta protegida en pública.
    """
    if not credenciales:
        return None
    try:
        return obtener_usuario_actual(credenciales, db)
    except HTTPException:
        return None