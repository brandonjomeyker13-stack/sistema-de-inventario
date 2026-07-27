"""
app/schemas/usuario.py — Schemas del recurso "usuario" (el perfil del negocio).

Separado de app/schemas/auth.py a propósito: auth.py son los schemas de
"cómo entro" (login, tokens, registro); este archivo es "qué es un
usuario" y "qué puedo cambiar de mi perfil" — el mismo split que ya
tienes entre producto.py/venta.py y sus respectivos services.
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    nombre_negocio: str


class UsuarioActualizar(BaseModel):
    nombre_negocio: str = Field(min_length=1, max_length=255)


class CambiarPassword(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, description="Mínimo 8 caracteres")