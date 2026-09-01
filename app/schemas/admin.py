"""
app/schemas/admin.py — Qué entra y sale del panel de administración.

Ninguno de estos schemas expone datos del NEGOCIO de un cliente: ni sus
ventas, ni sus productos, ni sus fiados. Solo el estado de la cuenta.

De los conteos de uso salen dos números —cuántos productos tiene y cuántas
ventas hizo esta semana— y son a propósito solo eso: sirven para saber a
quién llamar porque no está usando la aplicación, sin revelar qué vende ni
cuánto gana.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NegocioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre_negocio: str
    email: str
    sector: str | None = None

    # "pagando" | "prueba" | "vencida" | "sin_pagar"
    #
    # Se separan "vencida" y "sin_pagar" porque son dos conversaciones
    # distintas: a quien fue cliente se le pide que renueve, y a quien
    # nunca pagó se le pregunta si le sirvió la prueba.
    situacion: str
    dias_restantes: int
    suscripcion_hasta: str | None = None
    prueba_hasta: str | None = None
    # Se le acaba esta semana: es la lista de a quién cobrarle.
    por_vencer: bool = False

    activo: bool
    email_verificado: bool
    es_admin: bool
    creado_en: datetime | None = None

    # Señales de si la cuenta está viva. Un negocio con cero productos a los
    # tres días de registrarse es alguien a quien hay que llamar, no
    # esperar.
    productos: int = 0
    ventas_ultimos_dias: int = 0


class RegistroAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # NULABLES, y no es un detalle. Las llaves quedaron en ON DELETE SET NULL
    # (migración 0027) para que borrar una cuenta no se lleve por delante el
    # registro de que la borraste — justo el que más falta hace después.
    #
    # Declarados obligatorios, la primera cuenta borrada en cascada hacía
    # reventar la bitácora entera con un 500 al validar la respuesta.
    admin_id: str | None = None
    usuario_id: str | None = None
    # Quién era el negocio, en texto: "Papelería Sol (sol@correo.com)". Es lo
    # único que queda cuando el id ya es NULL; sin esto una fila diría
    # "alguien le hizo algo a alguien".
    descripcion: str | None = None
    accion: str
    valor_antes: str | None = None
    valor_despues: str | None = None
    nota: str | None = None
    creado_en: datetime | None = None


class NegocioDetalleOut(NegocioOut):
    """Como NegocioOut, más lo que se le ha hecho a esa cuenta."""

    historial: list[RegistroAdminOut] = []


class ListaNegociosOut(BaseModel):
    """La lista, con los recuentos que interesan de un vistazo.

    `por_vencer` es el número que de verdad se mira cada semana: a cuántos
    hay que cobrarles antes del lunes.
    """

    total: int
    pagando: int
    en_prueba: int
    vencidas: int
    por_vencer: int
    negocios: list[NegocioOut] = []


class CambiarSuscripcion(BaseModel):
    # None deja la cuenta sin suscripción: así se marca a quien dejó de
    # pagar. No le devuelve los días de prueba — esos están en otra columna
    # y ya quedaron en el pasado.
    hasta: str | None = None
    # Por qué. "pagó por Nequi el 12", "cortesía por la caída del sábado".
    # Es lo que hace que la bitácora se pueda leer dentro de seis meses.
    nota: str | None = Field(default=None, max_length=255)


class CambiarActivo(BaseModel):
    activo: bool
    nota: str | None = Field(default=None, max_length=255)


class CambiarAdmin(BaseModel):
    es_admin: bool
    nota: str | None = Field(default=None, max_length=255)
