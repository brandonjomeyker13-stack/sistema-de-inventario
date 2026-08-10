"""
app/repositories/sesion_repository.py — Acceso a datos de sesiones
(refresh tokens emitidos).
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.sesion import Sesion


def crear(
    db: Session,
    usuario_id: str,
    token_hash: str,
    expira_en: datetime,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Sesion:
    sesion = Sesion(
        usuario_id=usuario_id,
        token_hash=token_hash,
        expira_en=expira_en,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


def obtener_activa_por_hash(db: Session, token_hash: str) -> Sesion | None:
    """Devuelve la sesión solo si existe, no ha sido revocada y no ha
    expirado. Si cualquiera de esas condiciones falla, devuelve None."""
    sesion = db.query(Sesion).filter(Sesion.token_hash == token_hash).first()
    if not sesion or sesion.revocado:
        return None

    # Se asume UTC cuando la fecha viene sin zona: se guardó en UTC, pero
    # no todos los motores la devuelven con tzinfo (SQLite no la guarda) y
    # comparar naive contra aware lanza TypeError.
    expira = sesion.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if expira < datetime.now(timezone.utc):
        return None
    return sesion


def revocar(db: Session, sesion: Sesion) -> None:
    sesion.revocado = True
    db.commit()


def revocar_todas(db: Session, usuario_id: str) -> int:
    """Cierra todas las sesiones abiertas de un usuario.

    Se usa al restablecer la contraseña. Es la parte que de verdad
    importa de ese flujo: si alguien entró a tu cuenta, cambiar la
    contraseña sin cerrar sus sesiones no lo echa — su refresh token
    sigue sirviendo durante días.
    """
    afectadas = (
        db.query(Sesion)
        .filter(Sesion.usuario_id == usuario_id, Sesion.revocado.is_(False))
        .update({Sesion.revocado: True})
    )
    db.commit()
    return afectadas