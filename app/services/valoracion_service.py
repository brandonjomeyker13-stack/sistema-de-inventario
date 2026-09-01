"""
Las calificaciones que el tendero le pone a Trackie.

EL PROBLEMA QUE RESUELVE LA FIRMA

Para calificar, el frontend manda de vuelta la pregunta y la respuesta. El
servidor no las tiene guardadas —guardar todos los intercambios es
justamente lo que se evita— así que tiene que fiarse de lo que le llega.

Sin firma, cualquiera podría llenar el panel de "Trackie dijo esto" con
cosas que Trackie nunca dijo. Y ese panel es el conjunto con el que algún
día se entrena un clasificador: datos inventados ahí no se notan hasta
mucho después, cuando ya no hay forma de saber cuáles eran.

Con firma, solo se puede calificar lo que de verdad salió de aquí, y sin
guardar nada mientras tanto. Ver app/core/firma.py.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core import firma as sello
from app.models.valoracion import (
    MALA, ORIGENES, PENDIENTE, REVISADA, VALORACIONES, Valoracion,
)
from app.services.consulta_service import ETIQUETAS_VALIDAS

MAX_COMENTARIO = 500


def firmar(pregunta: str, respuesta: str, origen: str, intencion: str | None) -> str:
    """El sello que viaja con la respuesta y vuelve al calificarla.

    Se firman los cuatro campos y no solo el texto: así el origen y la
    intención tampoco se pueden cambiar por el camino, y las estadísticas de
    "el enrutador acierta más que el modelo" siguen siendo ciertas.
    """
    return sello.firmar(pregunta, respuesta, origen, intencion or "")


def valorar(db: Session, usuario_id: str, pregunta: str, respuesta: str,
            origen: str, intencion: str | None, firma: str, valoracion: str,
            comentario: str | None = None) -> Valoracion:
    """Guarda la calificación, si el texto de verdad salió de aquí.

    `usuario_id` se guarda porque revisar una queja como "me dijo 3 y en
    verdad son 5" obliga a ir a ver de dónde salió el 3. Al tendero se le
    dice en la pantalla: no es una anonimidad que él crea tener.
    """
    if valoracion not in VALORACIONES:
        raise ErrorNegocio("La calificación solo puede ser buena o mala")
    if origen not in ORIGENES:
        raise ErrorNegocio("Origen desconocido")
    if not sello.es_valida(firma, pregunta, respuesta, origen, intencion or ""):
        # Mensaje vago a propósito: quien esté probando a falsificar no
        # necesita saber qué parte no le cuadró.
        raise ErrorNegocio("No se pudo registrar la calificación")

    fila = Valoracion(
        usuario_id=usuario_id,
        pregunta=pregunta[:1000],
        respuesta=respuesta[:4000],
        origen=origen,
        intencion_detectada=intencion,
        valoracion=valoracion,
        comentario=(comentario or "").strip()[:MAX_COMENTARIO] or None,
        estado=PENDIENTE,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def listar(db: Session, valoracion: str | None = None, estado: str | None = None,
           limite: int = 100) -> dict:
    consulta = db.query(Valoracion)
    if valoracion in VALORACIONES:
        consulta = consulta.filter(Valoracion.valoracion == valoracion)
    if estado in (PENDIENTE, REVISADA):
        consulta = consulta.filter(Valoracion.estado == estado)

    return {
        **resumen(db),
        # joinedload y no lazy: el panel muestra el nombre del negocio en
        # cada fila, y sin esto serían cien consultas para una lista de cien.
        "valoraciones": (consulta
                         .options(joinedload(Valoracion.usuario))
                         .order_by(Valoracion.creado_en.desc())
                         .limit(limite).all()),
    }


def resumen(db: Session) -> dict:
    """Los números de arriba del panel.

    `malas_del_enrutador` es el que hay que vigilar: si el enrutador se lleva
    más quejas que el modelo, hay disparadores que están respondiendo
    preguntas que no eran suyas — y eso se arregla quitando disparadores, no
    agregándolos.
    """
    por_valoracion = dict(
        db.query(Valoracion.valoracion, func.count(Valoracion.id))
        .group_by(Valoracion.valoracion).all()
    )
    return {
        "total": sum(por_valoracion.values()),
        "buenas": por_valoracion.get("buena", 0),
        "malas": por_valoracion.get(MALA, 0),
        "sin_revisar": db.query(func.count(Valoracion.id)).filter(
            Valoracion.valoracion == MALA, Valoracion.estado == PENDIENTE,
        ).scalar() or 0,
        "malas_del_enrutador": db.query(func.count(Valoracion.id)).filter(
            Valoracion.valoracion == MALA, Valoracion.origen == "enrutador",
        ).scalar() or 0,
    }


def revisar(db: Session, admin, valoracion_id: str,
            intencion_correcta: str | None = None) -> Valoracion:
    """Marca la queja como atendida, y de paso la etiqueta si procede."""
    fila = db.query(Valoracion).filter(Valoracion.id == valoracion_id).first()
    if fila is None:
        raise NoEncontrado("Esa calificación no existe")

    if intencion_correcta is not None:
        if intencion_correcta not in ETIQUETAS_VALIDAS:
            raise ErrorNegocio(
                f"'{intencion_correcta}' no es una intención válida. "
                f"Las que hay: {', '.join(ETIQUETAS_VALIDAS)}"
            )
        fila.intencion_correcta = intencion_correcta

    fila.estado = REVISADA
    fila.revisada_por = admin.id
    db.commit()
    db.refresh(fila)
    return fila
