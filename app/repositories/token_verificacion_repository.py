"""
app/repositories/token_verificacion_repository.py — Acceso a datos de
tokens de verificación de correo.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.token_verificacion import TokenVerificacion


def crear(db: Session, usuario_id: str, token: str, horas_validez: int = 24) -> TokenVerificacion:
    registro = TokenVerificacion(
        usuario_id=usuario_id,
        token=token,
        expira_en=datetime.now(timezone.utc) + timedelta(hours=horas_validez),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def obtener_valido(db: Session, token: str) -> TokenVerificacion | None:
    """Devuelve el registro solo si existe, no se ha usado y no ha expirado.
    Si cualquiera de esas condiciones falla, devuelve None (el caller lo
    trata como "token inválido", sin distinguir el motivo al usuario)."""
    registro = db.query(TokenVerificacion).filter(TokenVerificacion.token == token).first()
    if not registro or registro.usado:
        return None

    # `expira_en` se guardó en UTC, pero no todos los motores devuelven la
    # zona horaria al leerlo (SQLite no la guarda). Comparar un datetime
    # sin zona contra uno con zona lanza TypeError, así que se asume UTC
    # cuando falta — que es en lo que se escribió.
    expira = registro.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)

    if expira < datetime.now(timezone.utc):
        return None
    return registro


def marcar_usado(db: Session, registro: TokenVerificacion) -> None:
    registro.usado = True
    db.commit()