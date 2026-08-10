"""
app/repositories/usuario_repository.py — Acceso a datos de usuarios.

Los repositorios NUNCA deciden si algo "está permitido" (eso es trabajo
de app/services/); solo saben leer y escribir filas.
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.fechas import sumar_dias
from app.models.usuario import Usuario


def obtener_por_email(db: Session, email: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.email == email.lower().strip()).first()


def obtener_por_id(db: Session, usuario_id: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.id == usuario_id).first()


def crear(db: Session, email: str, password_hash: str | None, nombre_negocio: str) -> Usuario:
    """password_hash puede ser None: las cuentas creadas con Google no
    tienen contraseña hasta que su dueño decide ponerle una."""
    usuario = Usuario(
        email=email.lower().strip(),
        password_hash=password_hash,
        nombre_negocio=nombre_negocio.strip(),
        # Periodo de prueba. Sin esto la cuenta nacería vencida y no
        # podría ni registrar su primer producto.
        suscripcion_hasta=sumar_dias(settings.DIAS_DE_PRUEBA),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def actualizar_perfil(db: Session, usuario: Usuario, nombre_negocio: str,
                      sector: str | None = None) -> Usuario:
    usuario.nombre_negocio = nombre_negocio.strip()
    # Solo se toca el sector si viene algo. Mandar el perfil sin sector no
    # debe borrar el que ya estaba: el frontend edita el nombre del
    # negocio desde varios sitios y no siempre incluye este campo.
    if sector is not None:
        usuario.sector = sector
    db.commit()
    db.refresh(usuario)
    return usuario


def actualizar_password(db: Session, usuario: Usuario, password_hash: str) -> None:
    usuario.password_hash = password_hash
    db.commit()
    
def marcar_email_verificado(db: Session, usuario: Usuario) -> None:
    usuario.email_verificado = True
    db.commit()