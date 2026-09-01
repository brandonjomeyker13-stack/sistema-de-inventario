"""
app/services/enrutador_service — Responder sin llamar al modelo.

QUÉ PROBLEMA RESUELVE

Casi todo lo que pregunta un tendero cae en un puñado de intenciones: qué
comprar, cuánto vendí, cuánto gané, quién me debe, cuántos productos no
tienen código, cuánto vale el inventario. Todas esas respuestas ya están
calculadas antes de llamar al modelo. El modelo no calcula nada: solo
redacta. Y redactar lo hace una plantilla.

Este paquete se pone DELANTE del asistente: si reconoce la pregunta,
responde él; si no, se aparta y contesta el modelo como siempre.

Son tres cosas ganadas, y la tercera es la que más importa:

  · Cero tokens y respuesta instantánea en las preguntas frecuentes.
  · Una consulta en vez de hasta catorce. El contexto del asistente arma el
    panorama completo del negocio porque no sabe qué le van a preguntar;
    aquí la intención se conoce antes de consultar.
  · La lista de compra deja de depender de que el modelo la copie bien.
    Hoy el prompt le ruega que no le cambie ni una palabra
    (instrucciones.py, LISTA_DE_COMPRA) para que coincida con la pantalla
    de inventario. Pedir no es garantizar; salir del mismo sitio, sí.

CÓMO ESTÁ PARTIDO

    intenciones.py   QUÉ preguntas reconoce, y la clasificación. Sin base.
    datos.py         QUÉ se consulta para cada una. Sin texto.
    redaccion.py     CÓMO se escribe la respuesta. Sin consultas.
    __init__.py      Orquesta los tres.

Es la misma frontera que en asistente_service, y por la misma razón: el
texto de una respuesta se ajusta mucho más seguido que la consulta que la
alimenta, y a menudo lo ajusta alguien mirándolo como texto.

LO QUE ESTE PAQUETE NO HACE

No propone acciones. Crear un producto o registrar mercancía sigue siendo
del modelo, que las devuelve como propuesta para que el tendero confirme
(ver asistente_service/acciones.py). Por eso `clasificar` se aparta en
cuanto ve un verbo de hacer.
"""

from sqlalchemy.orm import Session

from app.services.enrutador_service import datos, intenciones, redaccion
from app.services.enrutador_service.intenciones import clasificar

__all__ = ["resolver", "clasificar", "INTENCIONES_RESUELTAS"]


def _armar_tabla() -> dict:
    """Empareja cada intención con su función de datos y la de redacción.

    Se arma al importar el módulo, no en cada pregunta, y a propósito
    revienta aquí si a una intención le falta alguna de las dos. Añadir un
    nombre al catálogo y olvidar la función es un error de programación:
    vale mucho más que no arranque el servicio a que la primera persona que
    haga esa pregunta reciba un 500.
    """
    tabla = {}
    for nombre in intenciones.NOMBRES:
        faltan = [
            modulo.__name__ for modulo in (datos, redaccion)
            if not hasattr(modulo, nombre)
        ]
        if faltan:
            raise RuntimeError(
                f"La intención '{nombre}' no tiene función en: {', '.join(faltan)}"
            )
        tabla[nombre] = (getattr(datos, nombre), getattr(redaccion, nombre))
    return tabla


INTENCIONES_RESUELTAS = _armar_tabla()


def resolver(db: Session, usuario_id: str, pregunta: str) -> dict | None:
    """Responde la pregunta sin modelo, o devuelve None para que él conteste.

    None no es un fallo: es el camino normal para todo lo que no sea una de
    las preguntas frecuentes. Quien llama simplemente sigue como antes.

    No se capturan errores a propósito. Las consultas que se hacen aquí son
    las mismas que hace el contexto del asistente, así que un fallo real
    fallaría igual por el otro camino: atraparlo aquí solo escondería el
    problema detrás de una respuesta del modelo que parecería normal.
    """
    intencion = clasificar(pregunta)
    if intencion is None:
        return None

    consultar, escribir = INTENCIONES_RESUELTAS[intencion]
    return {"intencion": intencion, "respuesta": escribir(consultar(db, usuario_id))}
