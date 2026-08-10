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

import hashlib
import secrets

def generar_token_verificacion() -> str:
    """Token aleatorio para el link de verificación de correo (y, más
    adelante, reset de contraseña). No es un JWT: no necesita llevar
    información adentro, solo ser único e imposible de adivinar."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash determinístico (SHA-256) para poder buscar un refresh token en
    la base de datos por su hash, sin guardar el valor real.

    A propósito NO se usa bcrypt aquí: bcrypt genera un salt distinto cada
    vez, así que dos hashes del mismo password nunca son iguales — perfecto
    para contraseñas, pero imposible de usar para "busca la sesión con este
    token" (tendrías que comparar contra todas las filas). Como el refresh
    token ya es aleatorio y largo (un JWT firmado), SHA-256 sin salt es
    seguro aquí y permite la búsqueda directa por índice."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _crear_token(usuario_id: str, expira_en: timedelta, tipo: str) -> str:
    payload = {
        "sub": usuario_id,
        "tipo": tipo,
        "exp": datetime.now(timezone.utc) + expira_en,
        # Identificador único del token. Sin esto, dos inicios de sesión
        # del mismo usuario en el MISMO SEGUNDO producen exactamente el
        # mismo JWT: el payload solo cambiaba con `exp`, que tiene
        # precisión de segundos. Y como `sesiones.token_hash` es único,
        # el segundo login reventaba con un 500 — un doble clic en el
        # botón de entrar bastaba para provocarlo.
        "jti": secrets.token_urlsafe(16),
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