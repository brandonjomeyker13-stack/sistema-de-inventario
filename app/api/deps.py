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
from app.core.fechas import hoy_local
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


def suscripcion_activa(usuario: Usuario) -> bool:
    """Si la cuenta puede usar la aplicación completa hoy.

    Se compara como texto porque las fechas se guardan en 'YYYY-MM-DD',
    formato que ordena igual como cadena que como fecha. Y se usa la
    fecha del NEGOCIO, no la del servidor: si no, en Colombia la
    suscripción vencería a las 7 de la tarde del último día.
    """
    if not usuario.suscripcion_hasta:
        return False
    return usuario.suscripcion_hasta >= hoy_local()


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
        raise SuscripcionVencida(
            "Tu suscripción venció. Puedes seguir viendo tus productos y tu "
            "historial, pero para registrar ventas necesitas renovar."
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