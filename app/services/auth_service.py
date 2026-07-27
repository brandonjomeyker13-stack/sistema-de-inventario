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

from app.core.config import settings
from app.core.exceptions import ErrorNegocio, CredencialesInvalidas
from app.core.security import (
    hash_password, verificar_password, crear_access_token, crear_refresh_token,
    decodificar_token, generar_token_verificacion, hash_token,
)
from app.repositories import usuario_repository, token_verificacion_repository, sesion_repository


def registrar(db: Session, email: str, password: str, nombre_negocio: str):
    if usuario_repository.obtener_por_email(db, email):
        raise ErrorNegocio("Ya existe una cuenta registrada con ese correo")

    usuario = usuario_repository.crear(db, email, hash_password(password), nombre_negocio)

    token = generar_token_verificacion()
    token_verificacion_repository.crear(db, usuario.id, token)
    # TODO: mandar `token` por correo al usuario cuando conectemos un
    # proveedor (Resend/SendGrid). Mientras tanto, para probar el flujo,
    # el token queda visible en la tabla tokens_verificacion en Supabase
    # y se valida contra GET /api/v1/auth/verificar/{token}.

    return usuario


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
    if not usuario or not verificar_password(password, usuario.password_hash):
        raise CredencialesInvalidas("Correo o contraseña incorrectos")
    if not usuario.activo:
        raise CredencialesInvalidas("Esta cuenta está deshabilitada")
    if not usuario.email_verificado:
        raise CredencialesInvalidas("Debes verificar tu correo antes de iniciar sesión")

    access_token = crear_access_token(usuario.id)
    refresh_token = crear_refresh_token(usuario.id)

    sesion_repository.crear(
        db, usuario.id, hash_token(refresh_token),
        expira_en=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip=ip, user_agent=user_agent,
    )

    return {"access_token": access_token, "refresh_token": refresh_token}


def refrescar(db: Session, refresh_token: str) -> dict:
    try:
        payload = decodificar_token(refresh_token)
    except Exception:
        raise CredencialesInvalidas("El refresh token es inválido o expiró")

    if payload.get("tipo") != "refresh":
        raise CredencialesInvalidas("Token inválido: se esperaba un refresh token")

    sesion = sesion_repository.obtener_activa_por_hash(db, hash_token(refresh_token))
    if not sesion:
        raise CredencialesInvalidas("La sesión fue cerrada o ya no es válida")

    usuario = usuario_repository.obtener_por_id(db, payload["sub"])
    if not usuario or not usuario.activo:
        raise CredencialesInvalidas("Usuario no encontrado o deshabilitado")

    # Rotación: el refresh usado queda inválido de inmediato, se emite uno nuevo.
    sesion_repository.revocar(db, sesion)

    nuevo_access = crear_access_token(usuario.id)
    nuevo_refresh = crear_refresh_token(usuario.id)
    sesion_repository.crear(
        db, usuario.id, hash_token(nuevo_refresh),
        expira_en=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip=sesion.ip, user_agent=sesion.user_agent,
    )

    return {"access_token": nuevo_access, "refresh_token": nuevo_refresh}


def cerrar_sesion(db: Session, refresh_token: str) -> None:
    """Logout real: revoca la sesión asociada a este refresh_token para
    que no pueda usarse de nuevo. Es intencionalmente permisivo si el
    token ya no existe o ya estaba revocado (logout debe poder llamarse
    más de una vez sin error, y no debe filtrar si la sesión existía)."""
    sesion = sesion_repository.obtener_activa_por_hash(db, hash_token(refresh_token))
    if sesion:
        sesion_repository.revocar(db, sesion)