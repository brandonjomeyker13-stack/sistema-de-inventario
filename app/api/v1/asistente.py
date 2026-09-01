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

from app.core import limites
from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa
from app.models.usuario import Usuario
from app.schemas.asistente import PreguntaCrear, RespuestaAsistente, ValorarRespuesta
from app.services import asistente_service, valoracion_service

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
    # Límite POR CUENTA, no por IP: aquí no hay nada que adivinar, el
    # problema es el gasto. Cada pregunta arma el contexto (varias
    # consultas a Supabase) y llama a Groq, que cuesta dinero y tiene
    # cuota por minuto compartida entre TODOS los clientes.
    #
    # Sin esto, una tienda con un bucle mal hecho en el frontend —o
    # simplemente alguien que deja pulsado el botón— agota la cuota y deja
    # sin asistente a las demás. La cuenta no se puede rotar como una IP,
    # así que el límite muerde de verdad.
    limites.exigir(
        f"asistente:{usuario_actual.id}", maximo=20, segundos=60,
        mensaje="Estás preguntando muy rápido. Espera un momento.",
    )
    limites.exigir(
        f"asistente-dia:{usuario_actual.id}", maximo=300, segundos=86400,
        mensaje="Llegaste al máximo de preguntas por hoy. Mañana se reinicia.",
    )
    return asistente_service.preguntar(
        db, usuario_actual.id, datos.pregunta,
        [t.model_dump() for t in datos.historial],
    )


@router.post("/valorar", status_code=204)
def valorar(
    datos: ValorarRespuesta,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """El tendero dice si la respuesta le sirvió.

    Es la mejor etiqueta que puede tener este proyecto. Quien sabe si
    "tienes 3 productos por comprar" era verdad es el dueño mirando su
    estantería, no nosotros desde el panel.

    Solo aquí se guarda lo que respondió el asistente, y solo porque él lo
    pidió: en el resto del sistema las respuestas no se guardan, porque
    llevan las cifras del negocio. Pulsar el botón ES el consentimiento.

    Sí queda de qué negocio es. Revisar una queja como "me dijo 3 y en
    verdad son 5" obliga a ir a ver de dónde salió el 3, y sin eso la queja
    se lee pero no arregla nada. Al tendero se le dice en la pantalla.
    """
    # Límite generoso: calificar es barato y no llama a nadie. Es solo para
    # que un bucle mal hecho en el frontend no llene la tabla.
    limites.exigir(
        f"valorar:{usuario_actual.id}", maximo=60, segundos=60,
        mensaje="Espera un momento antes de seguir calificando.",
    )
    valoracion_service.valorar(
        db, usuario_actual.id, datos.pregunta, datos.respuesta, datos.origen,
        datos.intencion, datos.firma, datos.valoracion, datos.comentario,
    )
