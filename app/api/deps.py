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
from app.core.exceptions import SuscripcionVencida
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


def exigir_suscripcion_activa(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
) -> Usuario:
    """Igual que obtener_usuario_actual, pero además exige suscripción al día.

    Se pone en las rutas que ESCRIBEN (vender, registrar, editar) y en las
    de análisis. Las de solo lectura se quedan con obtener_usuario_actual:
    una cuenta vencida sigue viendo sus productos, sus ventas y sus
    fiados.

    Ese límite es deliberado. Quitarle a un tendero el acceso a su propio
    inventario porque se le pasó un pago no lo hace pagar: lo hace no
    volver. Que no pueda vender duele lo justo y es reversible en cuanto
    paga.
    """
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