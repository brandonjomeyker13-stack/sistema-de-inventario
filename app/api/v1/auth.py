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
from app.schemas.auth import UsuarioRegistro, UsuarioLogin, Token, RefrescarToken
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(datos: RefrescarToken, db: Session = Depends(get_db)):
    auth_service.cerrar_sesion(db, datos.refresh_token)