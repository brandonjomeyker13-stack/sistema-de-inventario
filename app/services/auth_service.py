from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, CredencialesInvalidas
from app.core.security import (
    hash_password, verificar_password, crear_access_token, crear_refresh_token, decodificar_token,
)
from app.repositories import usuario_repository


def registrar(db: Session, email: str, password: str, nombre_negocio: str):
    if usuario_repository.obtener_por_email(db, email):
        raise ErrorNegocio("Ya existe una cuenta registrada con ese correo")
    return usuario_repository.crear(db, email, hash_password(password), nombre_negocio)


def iniciar_sesion(db: Session, email: str, password: str) -> dict:
    usuario = usuario_repository.obtener_por_email(db, email)
    if not usuario or not verificar_password(password, usuario.password_hash):
        raise CredencialesInvalidas("Correo o contraseña incorrectos")
    if not usuario.activo:
        raise CredencialesInvalidas("Esta cuenta está deshabilitada")
    return {
        "access_token": crear_access_token(usuario.id),
        "refresh_token": crear_refresh_token(usuario.id),
    }


def refrescar(db: Session, refresh_token: str) -> dict:
    try:
        payload = decodificar_token(refresh_token)
    except Exception:
        raise CredencialesInvalidas("El refresh token es inválido o expiró")

    if payload.get("tipo") != "refresh":
        raise CredencialesInvalidas("Token inválido: se esperaba un refresh token")

    usuario = usuario_repository.obtener_por_id(db, payload["sub"])
    if not usuario or not usuario.activo:
        raise CredencialesInvalidas("Usuario no encontrado o deshabilitado")

    return {
        "access_token": crear_access_token(usuario.id),
        "refresh_token": crear_refresh_token(usuario.id),
    }