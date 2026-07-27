"""
app/api/v1/usuario.py — Endpoints del perfil del usuario autenticado.

Todos requieren Bearer token (Depends(obtener_usuario_actual)): un usuario
solo puede ver/editar su propio perfil, nunca el de otro.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioOut, UsuarioActualizar, CambiarPassword
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["Usuario"])


@router.get("/yo", response_model=UsuarioOut)
def obtener_perfil(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return usuario_service.obtener_perfil(db, usuario_actual.id)


@router.put("/yo", response_model=UsuarioOut)
def actualizar_perfil(
    datos: UsuarioActualizar,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return usuario_service.actualizar_perfil(db, usuario_actual.id, datos.nombre_negocio)


@router.put("/yo/password", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_password(
    datos: CambiarPassword,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    usuario_service.cambiar_password(
        db, usuario_actual.id, datos.password_actual, datos.password_nueva
    )