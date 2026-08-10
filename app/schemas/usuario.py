"""
app/schemas/usuario.py — Schemas del recurso "usuario" (el perfil del negocio).

Separado de app/schemas/auth.py a propósito: auth.py son los schemas de
"cómo entro" (login, tokens, registro); este archivo es "qué es un
usuario" y "qué puedo cambiar de mi perfil" — el mismo split que ya
tienes entre producto.py/venta.py y sus respectivos services.
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.core.sectores import SECTORES


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    nombre_negocio: str
    sector: str | None = None


class UsuarioActualizar(BaseModel):
    nombre_negocio: str = Field(min_length=1, max_length=255)
    # Opcional: las cuentas viejas no lo tienen y no se les puede exigir
    # de golpe. El frontend lo pide al registrarse y lo ofrece después.
    sector: str | None = None

    @field_validator("sector")
    @classmethod
    def validar_sector(cls, v: str | None) -> str | None:
        """Solo claves del catálogo. Texto libre aquí arruinaría el
        análisis por sector que viene después: "papeleria", "Papelería" y
        "papelerias" serían tres sectores distintos."""
        if v is None or not v.strip():
            return None
        v = v.strip()
        if v not in SECTORES:
            raise ValueError(
                f"Sector no válido: '{v}'. Consulta las opciones en GET /api/v1/sectores"
            )
        return v


class CambiarPassword(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, description="Mínimo 8 caracteres")