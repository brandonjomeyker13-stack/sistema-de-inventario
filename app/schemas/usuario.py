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
    # 'YYYY-MM-DD' hasta cuando PAGÓ. None = nunca ha pagado.
    suscripcion_hasta: str | None = None
    # Fin de los días gratis. Se fija al registrarse y no cambia.
    prueba_hasta: str | None = None
    # True mientras el acceso venga de la prueba y no de un pago. El
    # frontend lo necesita para decir "te quedan 2 días de prueba" en vez
    # de "tu plan vence en 2 días", que no significan lo mismo.
    en_prueba: bool = False
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
    # Solo para que el frontend sepa si enseñar la entrada al panel de
    # administración. Va aquí, en un schema de SALIDA; ponerlo en uno de
    # entrada sería el agujero que convierte a cualquiera en administrador
    # con una sola petición, y hay una prueba que lo impide.
    #
    # Que lo diga el servidor no es un permiso: quien llame al panel sin
    # serlo recibe un 403 igual. Esto solo evita enseñar un enlace que no
    # lleva a ninguna parte.
    es_admin: bool = False


class UsuarioActualizar(BaseModel):
    nombre_negocio: str = Field(min_length=1, max_length=255)
    # Opcional: las cuentas viejas no lo tienen y no se les puede exigir
    # de golpe. El frontend lo pide al registrarse y lo ofrece después.
    sector: str | None = None

    @field_validator("nombre_negocio")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        # Igual que en el registro: "   " pasa min_length=1 pero llega
        # vacío a la base después del .strip() del repositorio, y ahí una
        # restricción lo rechaza con un error 500. Es un 422 explicando el
        # campo, no una caída del servidor.
        limpio = " ".join(v.split())
        if not limpio:
            raise ValueError("El nombre del negocio no puede estar vacío")
        return limpio

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