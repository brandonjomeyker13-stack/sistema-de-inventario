"""app/repositories/token_password_repository.py — Tokens de restablecimiento."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.token_password import TokenPassword

# Una hora, no veinticuatro como la verificación de correo: este enlace
# cambia la contraseña, y cuanto menos tiempo viva en una bandeja de
# entrada, mejor.
HORAS_VALIDEZ = 1


def crear(db: Session, usuario_id: str, token: str) -> TokenPassword:
    # Se invalidan los anteriores del mismo usuario: si pidió el enlace
    # tres veces, solo el último debe funcionar. Si no, un correo viejo
    # reenviado o filtrado seguiría sirviendo.
    db.query(TokenPassword).filter(
        TokenPassword.usuario_id == usuario_id,
        TokenPassword.usado.is_(False),
    ).update({TokenPassword.usado: True})

    # Y se borran los que ya caducaron hace tiempo. Invalidarlos basta
    # para la seguridad, pero no para el tamaño de la tabla: sin esto,
    # cada enlace pedido deja una fila que nadie vuelve a mirar.
    db.query(TokenPassword).filter(
        TokenPassword.usuario_id == usuario_id,
        TokenPassword.expira_en < datetime.now(timezone.utc) - timedelta(days=7),
    ).delete(synchronize_session=False)

    registro = TokenPassword(
        usuario_id=usuario_id,
        token=token,
        expira_en=datetime.now(timezone.utc) + timedelta(hours=HORAS_VALIDEZ),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def obtener_valido(db: Session, token: str) -> TokenPassword | None:
    registro = db.query(TokenPassword).filter(TokenPassword.token == token).first()
    if not registro or registro.usado:
        return None

    expira = registro.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if expira < datetime.now(timezone.utc):
        return None
    return registro


def marcar_usado(db: Session, registro: TokenPassword) -> None:
    registro.usado = True
    db.commit()
