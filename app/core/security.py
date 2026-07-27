"""
app/core/security.py — Hashing de contraseñas y JWT.

Usamos `bcrypt` directamente (no passlib) porque las últimas versiones de
passlib han tenido problemas de compatibilidad con versiones nuevas de
bcrypt que generan errores confusos en producción. Menos capas, menos
sorpresas.

Dos tokens, mismo patrón que ya usas en OlivoSport:
  - access_token: vida corta (minutos), se manda en cada request.
  - refresh_token: vida larga (días), solo se usa para pedir un access
    token nuevo cuando el anterior expira.
"""

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _crear_token(usuario_id: str, expira_en: timedelta, tipo: str) -> str:
    payload = {
        "sub": usuario_id,
        "tipo": tipo,
        "exp": datetime.now(timezone.utc) + expira_en,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def crear_access_token(usuario_id: str) -> str:
    return _crear_token(usuario_id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def crear_refresh_token(usuario_id: str) -> str:
    return _crear_token(usuario_id, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")


def decodificar_token(token: str) -> dict:
    """Puede lanzar jwt.PyJWTError (token inválido, expirado, firma
    incorrecta, etc). Quien llama decide cómo traducir eso a HTTP
    (ver app/api/deps.py)."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])