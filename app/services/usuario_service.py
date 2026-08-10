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

from datetime import datetime

from sqlalchemy.orm import Session

from app.api.deps import suscripcion_activa, verificacion_al_dia, dias_para_verificar
from app.core.exceptions import ErrorNegocio, NoEncontrado, CredencialesInvalidas
from app.core.fechas import FORMATO_FECHA, hoy_local
from app.core.security import hash_password, verificar_password
from app.repositories import usuario_repository


def crear(db: Session, email: str, password: str, nombre_negocio: str):
    if usuario_repository.obtener_por_email(db, email):
        raise ErrorNegocio("Ya existe una cuenta registrada con ese correo")
    return usuario_repository.crear(db, email, hash_password(password), nombre_negocio)


def _con_suscripcion(usuario):
    """Añade el estado de la suscripción ya calculado.

    Se calcula aquí y no en el frontend porque depende de la fecha del
    NEGOCIO (ver app/core/fechas.py), no de la del navegador de quien
    mira. Un tendero con el reloj del computador mal puesto vería un
    estado equivocado, y sería justo el tipo de fallo del que nadie
    sospecha.
    """
    activa = suscripcion_activa(usuario)
    if usuario.suscripcion_hasta:
        restantes = (
            datetime.strptime(usuario.suscripcion_hasta, FORMATO_FECHA).date()
            - datetime.strptime(hoy_local(), FORMATO_FECHA).date()
        ).days
    else:
        restantes = 0

    usuario.suscripcion_activa = activa
    # Nunca negativo: "te quedan -5 días" no se lo dices a nadie.
    usuario.dias_restantes = max(restantes, 0)

    verificado = verificacion_al_dia(usuario)
    usuario.dias_para_verificar = dias_para_verificar(usuario)
    # Las dos condiciones ya resueltas, para que el frontend no tenga que
    # combinarlas y arriesgarse a hacerlo distinto en cada pantalla.
    usuario.puede_registrar = activa and verificado
    return usuario


def obtener_perfil(db: Session, usuario_id: str):
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Usuario no encontrado")
    return _con_suscripcion(usuario)


def actualizar_perfil(db: Session, usuario_id: str, nombre_negocio: str,
                      sector: str | None = None):
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Usuario no encontrado")
    return _con_suscripcion(
        usuario_repository.actualizar_perfil(db, usuario, nombre_negocio, sector)
    )


def cambiar_password(db: Session, usuario_id: str, password_actual: str, password_nueva: str):
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Usuario no encontrado")
    if not verificar_password(password_actual, usuario.password_hash):
        raise CredencialesInvalidas("La contraseña actual no es correcta")
    usuario_repository.actualizar_password(db, usuario, hash_password(password_nueva))