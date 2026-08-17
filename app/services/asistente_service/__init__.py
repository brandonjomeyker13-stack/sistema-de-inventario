"""
app/services/asistente_service — El asistente que conoce el negocio.

Este paquete es la cara pública: quien lo use solo necesita `preguntar()`.
Antes era un único archivo de 267 líneas que hacía tres trabajos a la vez, y
casi la mitad era el texto del prompt. Está partido por responsabilidad:

    instrucciones.py   CÓMO responde. Solo texto, ningún cálculo.
    contexto.py        QUÉ datos ve. Solo consultas, ningún texto de prompt.
    acciones.py        Qué puede proponer, y la validación de la propuesta.
    __init__.py        Orquesta los tres y arma la llamada al modelo.

La frontera entre los dos primeros es la que importa mantener: si alguna vez
hace falta escribir un precio o un nombre de producto dentro de
instrucciones.py, es señal de que falta un campo en el contexto.

El transporte hacia el proveedor vive fuera, en app/core/llm.py, y no sabe
nada de tiendas. Cambiar de Groq a otro proveedor toca ese archivo y ninguno
de estos.

DOS REGLAS QUE NO SE NEGOCIAN

1. El modelo solo ve lo que hay en el contexto. Nunca se le da acceso a la
   base de datos ni se ejecuta nada que devuelva.

2. El asistente PROPONE, no ejecuta. Ver acciones.py.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio
from app.core.llm import completar_json
from app.services.asistente_service import acciones, contexto
from app.services.asistente_service.instrucciones import (
    ACCIONES_PERMITIDAS, INSTRUCCIONES,
)

# Cuántos turnos anteriores de la conversación se le recuerdan. Suficiente
# para que "¿y ayer?" tenga sentido, sin que el historial acabe pesando más
# que los datos del negocio.
MAX_TURNOS = 6

# Tope de caracteres por mensaje. Corta un pegado accidental de media
# pantalla, que además del gasto empujaría el contexto fuera de la ventana.
MAX_CARACTERES = 1000

# Se re-exportan para que quien importe el servicio siga encontrándolos
# donde estaban antes de partir el archivo.
__all__ = ["preguntar", "construir_contexto", "INSTRUCCIONES", "ACCIONES_PERMITIDAS"]


def construir_contexto(db: Session, usuario_id: str, pregunta: str) -> dict:
    """Los datos del negocio que verá el modelo. Ver contexto.py."""
    return contexto.construir(db, usuario_id, pregunta)


def preguntar(db: Session, usuario_id: str, pregunta: str,
              historial: list[dict] | None = None) -> dict:
    """Responde una pregunta sobre el negocio.

    `historial` son los turnos anteriores de la conversación, para que
    "¿y ayer?" tenga sentido. No se guarda en base: el chat es efímero
    por ahora y el frontend lo mantiene en memoria.
    """
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise ErrorNegocio("La pregunta está vacía")

    datos = construir_contexto(db, usuario_id, pregunta)

    mensajes = [
        {"role": "system", "content": INSTRUCCIONES},
        {
            "role": "system",
            # El contexto va como mensaje de sistema aparte, no mezclado
            # con la pregunta del usuario: así lo que escribe el tendero
            # nunca puede confundirse con instrucciones.
            "content": "Datos del negocio en este momento:\n" + _como_texto(datos),
        },
    ]

    for turno in (historial or [])[-MAX_TURNOS:]:
        papel = "assistant" if turno.get("rol") == "asistente" else "user"
        mensajes.append({"role": papel, "content": str(turno.get("texto", ""))[:MAX_CARACTERES]})

    mensajes.append({"role": "user", "content": pregunta[:MAX_CARACTERES]})

    salida = completar_json(mensajes)

    return {
        "respuesta": str(salida.get("respuesta", "")).strip()
                     or "No supe cómo responder a eso.",
        "accion": acciones.validar(salida.get("accion")),
    }


def _como_texto(datos: dict) -> str:
    import json

    return json.dumps(datos, ensure_ascii=False, indent=None)
