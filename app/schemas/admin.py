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


# --- Las preguntas que le hacen a Trackie --------------------------------
#
# UNA ADVERTENCIA HONESTA SOBRE ESTAS FILAS
#
# El resto de este archivo no expone nada del negocio de un cliente. Estas
# sí pueden, de refilón: una pregunta como "¿cuántos cuadernos Norma me
# quedan?" lleva dentro un nombre de producto.
#
# Es inevitable —sin el texto de la pregunta no hay nada que etiquetar— y es
# mucho menos de lo que se ve en una venta. Por eso se guarda solo la
# pregunta y NUNCA la respuesta: la respuesta lleva las cifras.

class ConsultaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pregunta: str
    veces: int
    # Lo que el enrutador creyó. None = se apartó y respondió el modelo, o
    # sea que esa pregunta todavía cuesta tokens.
    intencion_detectada: str | None = None
    # La etiqueta puesta a mano. Es el dato del entrenamiento.
    intencion_correcta: str | None = None
    estado: str
    creado_en: datetime | None = None
    ultima_vez: datetime | None = None


class ListaConsultasOut(BaseModel):
    total: int
    pendientes: int
    # Cuántos ejemplos hay listos para entrenar. Es el número que dice
    # cuánto falta.
    etiquetadas: int
    descartadas: int
    # Cuántas preguntas distintas no reconoce el enrutador todavía.
    sin_reconocer: int
    # Contando repeticiones: cuántas veces se ha preguntado en total.
    veces_en_total: int
    # Etiquetas que apuntan a una intención que ya no existe. Normalmente
    # cero: si aparece un número, alguien renombró o borró una intención y
    # esos ejemplos dejaron de servir para entrenar.
    huerfanas: int = 0
    # De cuáles intenciones venían. Saber que hay 47 no sirve sin esto.
    intenciones_huerfanas: list[str] = []
    consultas: list[ConsultaOut] = []


class EtiquetarConsulta(BaseModel):
    intencion: str = Field(max_length=40)


class EtiquetaOut(BaseModel):
    intencion: str
    # Cuántas preguntas llevan ya esta etiqueta. Sirve para ver si el
    # conjunto está desbalanceado: mil de una y tres de otra no entrenan.
    ejemplos: int


# --- Las calificaciones que pone el tendero ------------------------------
#
# Estas SÍ llevan la respuesta con las cifras del negocio, y es la única
# excepción en todo el panel. La justifica el consentimiento: la fila solo
# existe porque el dueño pulsó el botón pidiendo que revisemos ese
# intercambio.

class ValoracionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # El nombre del negocio que se quejó. None cuando la cuenta ya se borró,
    # y ahí el panel dice "cuenta eliminada", igual que en la bitácora.
    negocio: str | None = None
    pregunta: str
    respuesta: str
    # "enrutador" o "modelo".
    origen: str
    intencion_detectada: str | None = None
    # "buena" o "mala".
    valoracion: str
    comentario: str | None = None
    estado: str
    intencion_correcta: str | None = None
    creado_en: datetime | None = None


class ListaValoracionesOut(BaseModel):
    total: int
    buenas: int
    malas: int
    # Malas sin atender. Es la bandeja de entrada.
    sin_revisar: int
    # El número a vigilar: si el enrutador se lleva más quejas que el modelo,
    # hay disparadores respondiendo preguntas que no eran suyas — y eso se
    # arregla QUITANDO disparadores, no agregándolos.
    malas_del_enrutador: int
    # Quejas etiquetadas con una intención que ya no está en el catálogo.
    huerfanas: int = 0
    valoraciones: list[ValoracionOut] = []


class RevisarValoracion(BaseModel):
    # Opcional: marcar como revisada sin etiquetar también vale.
    intencion_correcta: str | None = Field(default=None, max_length=40)
