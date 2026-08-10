"""
app/core/google.py — Verificación de los ID token de Google.

Lo que llega del frontend es un JWT firmado por Google. Verificarlo
significa comprobar cuatro cosas, y las cuatro importan:

  - La FIRMA, contra las claves públicas de Google. Sin esto, cualquiera
    fabrica un token diciendo ser quien quiera.
  - La AUDIENCIA (`aud`), que debe ser tu Client ID. Un token válido
    emitido para otra aplicación no sirve aquí: si no se comprueba,
    alguien puede reutilizar el token que su app obtuvo para entrar en la
    tuya.
  - El EMISOR (`iss`), que debe ser Google.
  - La CADUCIDAD.

Todo eso lo hace `google.oauth2.id_token.verify_oauth2_token`. No se
valida a mano a propósito: es exactamente el tipo de código donde un
descuido no da error, solo deja un agujero abierto.
"""

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.core.exceptions import CredencialesInvalidas, ErrorNegocio


def verificar_id_token(token: str) -> dict:
    """Devuelve los datos del usuario de Google, o lanza.

    El diccionario trae al menos: email, email_verified, name, sub.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise ErrorNegocio(
            "El inicio de sesión con Google no está configurado en el servidor"
        )

    try:
        datos = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError:
        # La librería lanza ValueError para firma inválida, audiencia
        # equivocada y token expirado por igual. No se distingue en el
        # mensaje a propósito: decirle a quien lo intenta cuál de las
        # comprobaciones falló le ayuda a afinar el siguiente intento.
        raise CredencialesInvalidas("El token de Google no es válido")

    if not datos.get("email"):
        raise CredencialesInvalidas("Google no entregó un correo para esta cuenta")

    if not datos.get("email_verified"):
        # Google permite cuentas con correo sin verificar. Aceptarlas
        # dejaría entrar a alguien que registró un correo ajeno, y peor:
        # con el enlace de cuentas, tomaría una cuenta existente.
        raise CredencialesInvalidas(
            "Tu correo de Google no está verificado. Verifícalo antes de continuar."
        )

    return datos
