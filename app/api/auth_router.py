from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.auth import UsuarioRegistro, UsuarioLogin, UsuarioOut, Token, RefrescarToken
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/registro", response_model=UsuarioOut, status_code=201)
def registro(datos: UsuarioRegistro, db: Session = Depends(get_db)):
    return auth_service.registrar(db, datos.email, datos.password, datos.nombre_negocio)


@router.post("/login", response_model=Token)
def login(datos: UsuarioLogin, db: Session = Depends(get_db)):
    return auth_service.iniciar_sesion(db, datos.email, datos.password)


@router.post("/refresh", response_model=Token)
def refresh(datos: RefrescarToken, db: Session = Depends(get_db)):
    return auth_service.refrescar(db, datos.refresh_token)