"""
Las preguntas que le hacen a Trackie: registrarlas y etiquetarlas.

Dos usos muy distintos en el mismo sitio:

  · `registrar` lo llama el asistente en cada pregunta. Es de paso, tiene que
    ser barato y NO puede romper nada.
  · el resto lo llama el panel de administración, a mano y de vez en cuando.
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.models.consulta import (
    ConsultaRegistrada, DESCARTADA, ETIQUETADA, NINGUNA, PENDIENTE,
)
from app.repositories import consulta_repository
from app.services.enrutador_service.intenciones import NOMBRES, normalizar

log = logging.getLogger(__name__)

# Con qué se puede etiquetar una pregunta: las intenciones que el enrutador
# ya conoce, más "ninguna".
#
# "ninguna" no sobra y no es lo mismo que descartar. Un clasificador también
# tiene que aprender a NO clasificar —a apartarse y dejar que responda el
# modelo— y para eso necesita ejemplos de preguntas que no son de ninguna
# intención. Descartada es otra cosa: es una fila que no sirve ni para eso.
ETIQUETAS_VALIDAS = NOMBRES + (NINGUNA,)


def registrar(db: Session, pregunta: str, intencion: str | None) -> None:
    """Anota la pregunta para el panel y para el entrenamiento futuro.

    NUNCA lanza. Se llama después de haber respondido, y una estadística no
    puede tumbar la respuesta del tendero: si esto falla, lo correcto es que
    él ni se entere y que quede en el log.

    Es la única parte del proyecto donde se traga una excepción a propósito.
    En cualquier otro sitio esconder un fallo tapa un problema real; aquí el
    fallo no afecta a lo que el usuario pidió.
    """
    try:
        consulta_repository.registrar(
            db, normalizar(pregunta).strip(), (pregunta or "").strip(), intencion,
        )
    except Exception:  # noqa: BLE001
        log.warning("No se pudo registrar la consulta", exc_info=True)
        db.rollback()


def listar(db: Session, estado: str | None = None, sin_reconocer: bool = False,
           limite: int = 100) -> dict:
    """Lo que ve el panel: los números de arriba y la lista."""
    perdidas = consulta_repository.huerfanas(db, ETIQUETAS_VALIDAS)
    return {
        **consulta_repository.resumen(db),
        # Normalmente cero. Si aparece un número, alguien renombró o borró
        # una intención y esas etiquetas dejaron de valer.
        "huerfanas": perdidas["cuantas"],
        "intenciones_huerfanas": perdidas["intenciones"],
        "consultas": consulta_repository.listar(db, estado, sin_reconocer, limite),
    }


def _obtener(db: Session, consulta_id: str) -> ConsultaRegistrada:
    consulta = consulta_repository.obtener(db, consulta_id)
    if consulta is None:
        raise NoEncontrado("Esa pregunta no existe")
    return consulta


def etiquetar(db: Session, admin, consulta_id: str, intencion: str) -> ConsultaRegistrada:
    """Le pone a una pregunta la intención que de verdad tenía.

    Esta es LA operación de toda la tabla: cada llamada es un ejemplo más del
    conjunto de entrenamiento.
    """
    if intencion not in ETIQUETAS_VALIDAS:
        # Catálogo cerrado, como el de las acciones del asistente. Una
        # etiqueta libre haría que el conjunto acabara con "compras",
        # "compra" y "lista_compra" como si fueran tres cosas distintas, y
        # eso no se arregla después.
        raise ErrorNegocio(
            f"'{intencion}' no es una intención válida. "
            f"Las que hay: {', '.join(ETIQUETAS_VALIDAS)}"
        )

    consulta = _obtener(db, consulta_id)
    consulta.intencion_correcta = intencion
    consulta.estado = ETIQUETADA
    consulta.revisada_por = admin.id
    db.commit()
    db.refresh(consulta)
    return consulta


def descartar(db: Session, admin, consulta_id: str) -> ConsultaRegistrada:
    """La pregunta no sirve ni como ejemplo: una prueba, un pegado, ruido.

    No se borra. Si se borrara, la siguiente vez que alguien la escribiera
    volvería a aparecer como pendiente y habría que descartarla otra vez.
    """
    consulta = _obtener(db, consulta_id)
    consulta.intencion_correcta = None
    consulta.estado = DESCARTADA
    consulta.revisada_por = admin.id
    db.commit()
    db.refresh(consulta)
    return consulta


def reabrir(db: Session, admin, consulta_id: str) -> ConsultaRegistrada:
    """Deshace una etiqueta puesta por error. Vuelve a la bandeja."""
    consulta = _obtener(db, consulta_id)
    consulta.intencion_correcta = None
    consulta.estado = PENDIENTE
    consulta.revisada_por = admin.id
    db.commit()
    db.refresh(consulta)
    return consulta


def etiquetas(db: Session) -> list[dict]:
    """Las intenciones con las que se puede etiquetar, y cuántas van de cada
    una. El panel las usa para el desplegable, y el número dice si el
    conjunto está desbalanceado: mil ejemplos de una intención y tres de otra
    no sirven para entrenar."""
    conteo = {}
    for fila in db.query(ConsultaRegistrada.intencion_correcta).filter(
        ConsultaRegistrada.estado == ETIQUETADA
    ).all():
        conteo[fila[0]] = conteo.get(fila[0], 0) + 1

    return [{"intencion": nombre, "ejemplos": conteo.get(nombre, 0)}
            for nombre in ETIQUETAS_VALIDAS]
