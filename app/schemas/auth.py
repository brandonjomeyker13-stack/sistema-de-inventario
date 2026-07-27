"""
app/schemas/auth.py — Schemas de "cómo se entra": registro, login, tokens.

Todo lo que es "qué es un usuario" (perfil, cambio de contraseña) vive en
app/schemas/usuario.py; aquí solo lo necesario para autenticar.
"""

from pydantic import BaseModel, EmailStr, Field


class UsuarioRegistro(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")
    nombre_negocio: str = Field(min_length=1, max_length=255)


class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefrescarToken(BaseModel):
    refresh_token: str