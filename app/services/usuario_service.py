"""
app/services/usuario_service.py — Reglas de negocio sobre la cuenta/perfil
del usuario.

Separado de auth_service.py: ese archivo se encarga solo de EMITIR
credenciales (login, refresh de tokens). "¿Ya existe ese correo?",
"¿puede cambiar su nombre de negocio?", "¿la contraseña actual es
correcta antes de cambiarla?" son reglas de negocio sobre el usuario
mismo, no sobre cómo se firma un JWT — por eso viven aquí, siguiendo el
mismo patrón que producto_service.py / venta_service.py.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado, CredencialesInvalidas
from app.core.security import hash_password, verificar_password
from app.repositories import usuario_repository


def crear(db: Session, email: str, password: str, nombre_negocio: str):
    if usuario_repository.obtener_por_email(db, email):
        raise ErrorNegocio("Ya existe una cuenta registrada con ese correo")
    return usuario_repository.crear(db, email, hash_password(password), nombre_negocio)


def obtener_perfil(db: Session, usuario_id: str):
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Usuario no encontrado")
    return usuario


def actualizar_perfil(db: Session, usuario_id: str, nombre_negocio: str):
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Usuario no encontrado")
    return usuario_repository.actualizar_nombre_negocio(db, usuario, nombre_negocio)


def cambiar_password(db: Session, usuario_id: str, password_actual: str, password_nueva: str):
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Usuario no encontrado")
    if not verificar_password(password_actual, usuario.password_hash):
        raise CredencialesInvalidas("La contraseña actual no es correcta")
    usuario_repository.actualizar_password(db, usuario, hash_password(password_nueva))