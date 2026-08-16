"""
app/schemas/auth.py — Schemas de "cómo se entra": registro, login, tokens.

Todo lo que es "qué es un usuario" (perfil, cambio de contraseña) vive en
app/schemas/usuario.py; aquí solo lo necesario para autenticar.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator


def _nombre_limpio(v: str | None) -> str | None:
    """Colapsa los espacios y rechaza lo que quede vacío.

    `min_length=1` NO basta: "   " tiene tres caracteres y pasa la
    validación, pero el repositorio le hace .strip() antes de guardarlo y
    llega vacío a la base. En producción hay una restricción que exige un
    nombre no vacío, así que eso era un error 500 al registrarse — un
    fallo del servidor por un campo que el usuario dejó en blanco con la
    barra espaciadora.

    Devuelve None cuando no queda nada, para que quien llame decida: en el
    registro es obligatorio, y en el login con Google significa "usa el
    nombre que manda Google".
    """
    if v is None:
        return None
    limpio = " ".join(v.split())
    return limpio or None


class UsuarioRegistro(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")
    nombre_negocio: str = Field(min_length=1, max_length=255)

    @field_validator("nombre_negocio")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        limpio = _nombre_limpio(v)
        if not limpio:
            raise ValueError("El nombre del negocio no puede estar vacío")
        return limpio


class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefrescarToken(BaseModel):
    refresh_token: str


class GoogleLogin(BaseModel):
    # El ID token que devuelve Google Identity Services en el navegador.
    # Se verifica en el servidor contra Google; nunca se confía en él tal
    # cual, ni se acepta un correo mandado por el frontend.
    id_token: str
    # Solo se usa si la cuenta es nueva. Si no viene, se toma el nombre
    # de la cuenta de Google como provisional.
    nombre_negocio: str | None = Field(default=None, max_length=255)

    @field_validator("nombre_negocio")
    @classmethod
    def limpiar_nombre(cls, v: str | None) -> str | None:
        # "   " se convierte en None, no en "". Importa el detalle: el
        # servicio elige con `nombre_negocio or datos.get("name")`, y una
        # cadena de espacios es TRUTHY — ganaba sobre el nombre real que
        # manda Google y llegaba vacía a la base.
        return _nombre_limpio(v)


class TokenGoogle(Token):
    """Como Token, más lo que el frontend necesita para saber si tiene que
    mandar al usuario a completar su perfil."""

    es_nuevo: bool = False
    # True cuando la cuenta no tiene contraseña todavía.
    requiere_password: bool = False
    # False cuando falta el sector o el nombre real del negocio.
    perfil_completo: bool = True


class DefinirPassword(BaseModel):
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")


class ReenviarVerificacion(BaseModel):
    email: EmailStr


class RecuperarPassword(BaseModel):
    email: EmailStr


class RestablecerPassword(BaseModel):
    # El token que venía en el enlace del correo.
    token: str
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")