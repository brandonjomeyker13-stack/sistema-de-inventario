"""
Acceso a las preguntas registradas.

LA PARTE DELICADA ES `registrar`

Se llama en CADA pregunta al asistente, así que tiene que ser barata y, sobre
todo, no puede tumbar la respuesta del tendero. Anotar para estadísticas es
lo último que debe romper una petición.
"""

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.fechas import ahora_local
from app.models.consulta import ConsultaRegistrada, ESTADOS, PENDIENTE

# Más largo que esto no es una pregunta frecuente: es un pegado accidental o
# un texto que nadie va a repetir palabra por palabra. Guardarlo solo llenaría
# el panel de filas con veces=1.
MAX_CLAVE = 200


def registrar(db: Session, clave: str, pregunta: str,
              intencion: str | None) -> ConsultaRegistrada | None:
    """Anota la pregunta, o le suma uno si ya estaba.

    Devuelve None cuando no vale la pena guardarla (vacía o demasiado larga).

    La carrera de dos personas preguntando lo mismo a la vez NO se resuelve
    comprobando antes si existe: dos peticiones simultáneas pasarían las dos
    por ese `if` y la segunda reventaría al insertar. Se resuelve dejando que
    el índice único la rechace y contando el intento perdido como una
    repetición, que es exactamente lo que fue.
    """
    clave = (clave or "").strip()
    if not clave or len(clave) > MAX_CLAVE:
        return None

    fila = db.query(ConsultaRegistrada).filter(
        ConsultaRegistrada.clave == clave
    ).first()

    if fila is not None:
        fila.veces += 1
        fila.ultima_vez = ahora_local()
        # La detección se actualiza a propósito: si mañana se le agrega un
        # disparador al enrutador, esta fila tiene que reflejar lo que pasa
        # AHORA, no lo que pasaba la primera vez que alguien preguntó.
        fila.intencion_detectada = intencion
        db.commit()
        return fila

    fila = ConsultaRegistrada(
        clave=clave,
        pregunta=pregunta[:500],
        veces=1,
        intencion_detectada=intencion,
        estado=PENDIENTE,
    )
    db.add(fila)
    try:
        db.commit()
    except IntegrityError:
        # Otra petición la creó entre el SELECT y el INSERT. Se suma allí.
        db.rollback()
        fila = db.query(ConsultaRegistrada).filter(
            ConsultaRegistrada.clave == clave
        ).first()
        if fila is None:
            return None
        fila.veces += 1
        fila.ultima_vez = ahora_local()
        db.commit()

    return fila


def listar(db: Session, estado: str | None = None, sin_reconocer: bool = False,
           limite: int = 100) -> list[ConsultaRegistrada]:
    """Las preguntas, lo más preguntado primero.

    `sin_reconocer` deja solo las que el enrutador no supo responder. Son las
    que más valen: cada una es una pregunta que hoy cuesta tokens y espera al
    proveedor.
    """
    consulta = db.query(ConsultaRegistrada)

    if estado in ESTADOS:
        consulta = consulta.filter(ConsultaRegistrada.estado == estado)
    if sin_reconocer:
        consulta = consulta.filter(ConsultaRegistrada.intencion_detectada.is_(None))

    return (consulta
            .order_by(ConsultaRegistrada.veces.desc(),
                      ConsultaRegistrada.ultima_vez.desc())
            .limit(limite)
            .all())


def obtener(db: Session, consulta_id: str) -> ConsultaRegistrada | None:
    return db.query(ConsultaRegistrada).filter(
        ConsultaRegistrada.id == consulta_id
    ).first()


def resumen(db: Session) -> dict:
    """Los números de arriba del panel.

    `etiquetadas` es el que de verdad importa: es cuántos ejemplos hay ya
    listos para entrenar, y por tanto cuánto falta.
    """
    por_estado = dict(
        db.query(ConsultaRegistrada.estado, func.count(ConsultaRegistrada.id))
        .group_by(ConsultaRegistrada.estado).all()
    )
    sin_reconocer = db.query(func.count(ConsultaRegistrada.id)).filter(
        ConsultaRegistrada.intencion_detectada.is_(None)
    ).scalar() or 0

    return {
        "total": sum(por_estado.values()),
        "pendientes": por_estado.get(PENDIENTE, 0),
        "etiquetadas": por_estado.get("etiquetada", 0),
        "descartadas": por_estado.get("descartada", 0),
        "sin_reconocer": sin_reconocer,
        # Cuántas preguntas se han hecho en total, contando repeticiones.
        "veces_en_total": db.query(
            func.coalesce(func.sum(ConsultaRegistrada.veces), 0)
        ).scalar() or 0,
    }
