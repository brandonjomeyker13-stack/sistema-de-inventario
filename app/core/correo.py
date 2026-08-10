"""
app/core/correo.py — Envío de correo, solo el transporte.

Igual que app/core/llm.py: habla HTTP y nada más. No sabe qué es un
usuario ni qué es verificar una cuenta; eso vive en auth_service.

Se usa Resend porque su plan gratuito (3.000 correos al mes) cubre de
sobra el arranque y su API es una petición HTTP sin SDK.

DECISIÓN IMPORTANTE: si el envío falla, esta función NO lanza excepción,
devuelve False. El motivo es concreto — que el proveedor de correo esté
caído no puede impedir que alguien se registre. Se crea la cuenta, y el
usuario puede pedir el reenvío desde la pantalla de login. Lo contrario
sería perder usuarios por un fallo ajeno.
"""

import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

URL_RESEND = "https://api.resend.com/emails"


def esta_configurado() -> bool:
    return bool(settings.RESEND_API_KEY)


def enviar(destinatario: str, asunto: str, html: str) -> bool:
    """Manda un correo. Devuelve True si salió, False si no.

    Nunca lanza: quien llama decide qué hacer con un False, y en el
    registro lo correcto es seguir adelante.
    """
    if not esta_configurado():
        log.warning("No se envió el correo a %s: falta RESEND_API_KEY", destinatario)
        return False

    try:
        respuesta = httpx.post(
            URL_RESEND,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.CORREO_REMITENTE,
                "to": [destinatario],
                "subject": asunto,
                "html": html,
            },
            timeout=15,
        )
    except httpx.HTTPError as e:
        log.error("Fallo de red enviando correo a %s: %s", destinatario, e)
        return False

    if respuesta.status_code >= 400:
        # El cuerpo de Resend explica bien el problema (dominio sin
        # verificar, remitente inválido) y va al log del servidor, nunca
        # al usuario.
        log.error(
            "Resend rechazó el correo a %s (%s): %s",
            destinatario, respuesta.status_code, respuesta.text[:300],
        )
        return False

    return True


def plantilla_recuperacion(nombre_negocio: str, enlace: str) -> str:
    """El correo de "olvidé mi contraseña".

    Dice explícitamente cuánto dura el enlace y qué hacer si no fuiste tú.
    Lo segundo importa: si alguien está intentando entrar a una cuenta
    ajena, este correo es el primer aviso que recibe el dueño.
    """
    return f"""\
<div style="font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; \
max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
  <h2 style="margin: 0 0 16px; font-size: 20px;">Restablecer tu contraseña</h2>
  <p style="margin: 0 0 16px; line-height: 1.5;">
    Pediste cambiar la contraseña de <strong>{nombre_negocio}</strong>.
    Este enlace sirve una sola vez y caduca en <strong>1 hora</strong>.
  </p>
  <p style="margin: 0 0 24px;">
    <a href="{enlace}" style="display: inline-block; background: #2563eb; \
color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; \
font-weight: 600;">Cambiar mi contraseña</a>
  </p>
  <p style="margin: 0 0 8px; font-size: 13px; color: #666; line-height: 1.5;">
    Si el botón no funciona, copia esta dirección en tu navegador:<br>
    <span style="word-break: break-all;">{enlace}</span>
  </p>
  <p style="margin: 16px 0 0; font-size: 13px; color: #666; line-height: 1.5;">
    Si no pediste esto, ignora el mensaje: tu contraseña no cambia hasta
    que alguien abra ese enlace. Si te pasa varias veces, cambia tu
    contraseña por precaución.
  </p>
</div>"""


def plantilla_verificacion(nombre_negocio: str, enlace: str) -> str:
    """El correo de verificación.

    HTML sencillo y con estilos en línea a propósito: los clientes de
    correo ignoran las hojas de estilo externas y muchos recortan el CSS
    del <head>. Lo que se ve raro en Gmail no se puede depurar después.
    """
    return f"""\
<div style="font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; \
max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
  <h2 style="margin: 0 0 16px; font-size: 20px;">Confirma tu correo</h2>
  <p style="margin: 0 0 16px; line-height: 1.5;">
    Creaste la cuenta de <strong>{nombre_negocio}</strong>. Solo falta
    confirmar que este correo es tuyo.
  </p>
  <p style="margin: 0 0 24px;">
    <a href="{enlace}" style="display: inline-block; background: #2563eb; \
color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; \
font-weight: 600;">Confirmar mi correo</a>
  </p>
  <p style="margin: 0 0 8px; font-size: 13px; color: #666; line-height: 1.5;">
    Si el botón no funciona, copia esta dirección en tu navegador:<br>
    <span style="word-break: break-all;">{enlace}</span>
  </p>
  <p style="margin: 16px 0 0; font-size: 13px; color: #666;">
    Si no fuiste tú, ignora este mensaje.
  </p>
</div>"""
