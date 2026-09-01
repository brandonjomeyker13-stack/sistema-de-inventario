from pydantic import BaseModel, Field


class TurnoConversacion(BaseModel):
    # "usuario" o "asistente".
    rol: str
    texto: str = Field(max_length=1000)


class PreguntaCrear(BaseModel):
    pregunta: str = Field(min_length=1, max_length=1000)
    # Turnos anteriores, para que "¿y ayer?" tenga sentido. Los mantiene
    # el frontend: el chat no se guarda en base por ahora.
    historial: list[TurnoConversacion] = []


class AccionPropuesta(BaseModel):
    """Algo que el asistente sugiere hacer, y que NO ha hecho.

    El backend nunca ejecuta estas acciones. El frontend muestra
    `confirmacion`, y solo si el tendero acepta llama al endpoint normal
    (POST /productos, POST /movimientos/entrada) con `datos`.
    """

    tipo: str
    datos: dict
    confirmacion: str


class RespuestaAsistente(BaseModel):
    respuesta: str
    accion: AccionPropuesta | None = None

    # Lo que sigue es para poder calificar la respuesta después. El frontend
    # los guarda tal cual y los devuelve en /valorar sin tocarlos.
    #
    # "enrutador" si respondió el sistema sin gastar tokens, "modelo" si
    # respondió la IA. Sirve para medir si el enrutador ayuda o estorba.
    origen: str = "modelo"
    intencion: str | None = None
    # El sello del intercambio. El servidor NO guarda lo que responde —eso
    # metería las cifras de cada negocio en una tabla global—, así que al
    # calificar hay que devolverle el texto, y la firma es lo que le permite
    # comprobar que salió de él. Ver app/core/firma.py.
    firma: str = ""


class ValorarRespuesta(BaseModel):
    """Lo que manda el frontend cuando el tendero califica una respuesta.

    Los cinco primeros campos vienen tal cual de la respuesta que se está
    calificando. Si alguno se modifica, la firma deja de cuadrar y se rechaza.
    """

    pregunta: str = Field(max_length=1000)
    respuesta: str = Field(max_length=4000)
    origen: str = Field(max_length=20)
    intencion: str | None = Field(default=None, max_length=40)
    firma: str = Field(max_length=128)

    # "buena" o "mala".
    valoracion: str = Field(max_length=10)
    # Opcional, y lo más valioso de la fila cuando está: "me dijo 3 y en
    # verdad son 5".
    comentario: str | None = Field(default=None, max_length=500)
