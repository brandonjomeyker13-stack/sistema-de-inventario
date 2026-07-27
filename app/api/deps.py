"""
app/api/deps.py — Dependencias reutilizables entre rutas.

`obtener_usuario_actual` es lo que convierte "Authorization: Bearer <token>"
en un objeto Usuario real, validado contra la base de datos (no solo el
token). Cualquier ruta que reciba `usuario: Usuario = Depends(obtener_usuario_actual)`
queda protegida automáticamente.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.security import decodificar_token
from app.repositories import usuario_repository
from app.models.usuario import Usuario

_esquema_bearer = HTTPBearer()


def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(_esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        payload = decodificar_token(credenciales.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    if payload.get("tipo") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Se esperaba un access token")

    usuario = usuario_repository.obtener_por_id(db, payload.get("sub", ""))
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido")

    return usuario