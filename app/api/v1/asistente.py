"""
app/api/v1/asistente.py — El asistente de IA, servido desde tu backend.

Antes esto vivía en el servidor de Lovable, con su pasarela y su clave.
Traerlo aquí tiene tres efectos concretos: la clave es tuya, los datos de
las tiendas no pasan por un tercero que no elegiste, y el asistente puede
ver los datos reales sin que el frontend se los tenga que mandar.

El endpoint NUNCA modifica nada. Si el asistente entiende que le piden
crear un producto, devuelve una acción PROPUESTA con su frase de
confirmación; ejecutarla es cosa del frontend, contra los endpoints
normales, y solo tras la confirmación del tendero.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa
from app.models.usuario import Usuario
from app.schemas.asistente import PreguntaCrear, RespuestaAsistente
from app.services import asistente_service

# El asistente también exige suscripción: cada pregunta cuesta dinero real
# en el proveedor de IA, así que no puede quedar abierto a cuentas vencidas.
router = APIRouter(
    prefix="/asistente",
    tags=["Asistente"],
    dependencies=[Depends(exigir_suscripcion_activa)],
)


@router.post("/preguntar", response_model=RespuestaAsistente)
def preguntar(
    datos: PreguntaCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Responde sobre el negocio del usuario autenticado.

    El contexto se arma en el servidor con los datos reales de ESTE
    negocio: nunca se puede preguntar por el de otro, porque el usuario
    sale del token y no de la petición.
    """
    return asistente_service.preguntar(
        db, usuario_actual.id, datos.pregunta,
        [t.model_dump() for t in datos.historial],
    )
