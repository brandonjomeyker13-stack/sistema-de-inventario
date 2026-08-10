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
