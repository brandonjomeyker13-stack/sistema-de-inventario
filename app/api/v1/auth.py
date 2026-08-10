"""
app/api/v1/auth.py — Endpoints de "cómo entro": registro, login, refresh,
verificación de correo y logout.

registro, login, refresh y verificar son públicos (no requieren
Depends(obtener_usuario_actual)); logout recibe el refresh_token en el
body, no requiere el access_token porque puede llamarse aunque el access
token ya haya expirado.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.auth import (
    UsuarioRegistro, UsuarioLogin, Token, RefrescarToken, GoogleLogin, TokenGoogle,
    DefinirPassword, ReenviarVerificacion, RecuperarPassword, RestablecerPassword,
)
from app.schemas.usuario import UsuarioOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/registro", response_model=UsuarioOut, status_code=201)
def registro(datos: UsuarioRegistro, db: Session = Depends(get_db)):
    return auth_service.registrar(db, datos.email, datos.password, datos.nombre_negocio)


@router.get("/verificar/{token}")
def verificar_email(token: str, db: Session = Depends(get_db)):
    auth_service.verificar_email(db, token)
    return {"detalle": "Correo verificado correctamente"}


@router.post("/login", response_model=Token)
def login(datos: UsuarioLogin, request: Request, db: Session = Depends(get_db)):
    return auth_service.iniciar_sesion(
        db, datos.email, datos.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/refresh", response_model=Token)
def refresh(datos: RefrescarToken, db: Session = Depends(get_db)):
    return auth_service.refrescar(db, datos.refresh_token)


@router.post("/google", response_model=TokenGoogle)
def login_google(datos: GoogleLogin, request: Request, db: Session = Depends(get_db)):
    """Entra o crea la cuenta con Google.

    El `id_token` se verifica contra Google en el servidor. Si ya existe
    una cuenta con ese correo, se enlaza en vez de fallar.

    La respuesta trae `requiere_password` y `perfil_completo` para que el
    frontend sepa si debe pedir contraseña y datos del negocio después de
    entrar.
    """
    return auth_service.iniciar_sesion_google(
        db, datos.id_token, datos.nombre_negocio,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/definir-password", status_code=status.HTTP_204_NO_CONTENT)
def definir_password(
    datos: DefinirPassword,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Pone contraseña a una cuenta creada con Google.

    Requiere sesión iniciada. Falla si la cuenta ya tiene contraseña: para
    cambiarla está PUT /usuarios/yo/password, que pide la actual.
    """
    auth_service.definir_password(db, usuario_actual.id, datos.password)


@router.post("/reenviar-verificacion", status_code=status.HTTP_202_ACCEPTED)
def reenviar_verificacion(datos: ReenviarVerificacion, db: Session = Depends(get_db)):
    """Manda otra vez el correo de verificación.

    Responde 202 siempre, exista o no la cuenta: si contestara distinto,
    sería una forma cómoda de averiguar qué correos están registrados.
    """
    auth_service.reenviar_verificacion(db, datos.email)
    return {"detalle": "Si el correo está registrado y sin verificar, recibirás el enlace"}


@router.post("/recuperar-password", status_code=status.HTTP_202_ACCEPTED)
def recuperar_password(datos: RecuperarPassword, db: Session = Depends(get_db)):
    """Manda el enlace para restablecer la contraseña.

    Responde 202 siempre, exista o no la cuenta: si contestara distinto,
    sería una forma cómoda de averiguar qué correos están registrados.
    """
    auth_service.recuperar_password(db, datos.email)
    return {"detalle": "Si ese correo tiene cuenta, te llegará el enlace en unos minutos"}


@router.post("/restablecer-password", status_code=status.HTTP_204_NO_CONTENT)
def restablecer_password(datos: RestablecerPassword, db: Session = Depends(get_db)):
    """Cambia la contraseña con el token del correo.

    Cierra todas las sesiones abiertas del usuario: si alguien había
    entrado a la cuenta, este es el momento en que se le echa.
    """
    auth_service.restablecer_password(db, datos.token, datos.password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(datos: RefrescarToken, db: Session = Depends(get_db)):
    auth_service.cerrar_sesion(db, datos.refresh_token)