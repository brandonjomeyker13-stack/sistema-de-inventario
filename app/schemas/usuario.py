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
    # Fecha 'YYYY-MM-DD' hasta la que la cuenta puede usar la aplicación
    # completa. None = sin suscripción.
    suscripcion_hasta: str | None = None
    # Calculados, para que el frontend no tenga que comparar fechas ni
    # decidir qué zona horaria usar — la del negocio, no la del navegador.
    suscripcion_activa: bool = True
    dias_restantes: int = 0
    # Verificación del correo. Es una condición SEPARADA de la
    # suscripción: alguien puede haber pagado sin verificar, y al revés.
    email_verificado: bool = False
    # Días que le quedan para confirmar antes de pasar a solo lectura.
    # 0 si ya verificó o si se le acabó el plazo.
    dias_para_verificar: int = 0
    # Resultado de las dos condiciones juntas: si puede registrar ventas.
    puede_registrar: bool = True


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