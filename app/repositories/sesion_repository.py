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
    if sesion.expira_en < datetime.now(timezone.utc):
        return None
    return sesion


def revocar(db: Session, sesion: Sesion) -> None:
    sesion.revocado = True
    db.commit()