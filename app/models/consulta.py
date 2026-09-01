"""
app/models/consulta.py — Qué le pregunta la gente a Trackie.

Cada pregunta que entra al asistente queda anotada aquí, junto con la
intención que el enrutador creyó reconocer. Sirve para dos cosas, y la
segunda es la que justifica la tabla:

  1. Saber qué se pregunta de verdad. Hoy no lo sabemos: el chat es efímero
     y no se guarda nada, así que decidir qué responder sin modelo es
     adivinar.

  2. Ser el conjunto de entrenamiento. Para que algún día un clasificador
     propio entienda las preguntas sin llamar a un modelo grande, hacen
     falta miles de ejemplos ETIQUETADOS: la pregunta, y cuál era la
     intención correcta. Esa etiqueta la pone una persona desde el panel, y
     es `intencion_correcta`.

LOS DOS CAMPOS DE INTENCIÓN NO SOBRAN

`intencion_detectada` es lo que el enrutador dijo. `intencion_correcta` es
lo que un administrador dice que era. Guardar los dos es lo que convierte la
tabla en algo medible: donde no coinciden está el error, y ahí es donde hay
que tocar los disparadores. Con solo la etiqueta correcta no se sabría si el
enrutador ya acertaba.

Un `intencion_detectada` en NULL significa que el enrutador se apartó y
respondió el modelo. Son las filas más valiosas: cada una es una pregunta
que hoy cuesta tokens.

LO QUE ESTA TABLA NO TIENE

No tiene `usuario_id`, y es deliberado. Para entrenar no hace falta saber
quién preguntó, y sin esa columna el panel no puede atar una pregunta a un
negocio ni por descuido. Tampoco se guarda la RESPUESTA: esa lleva las
cifras del negocio que preguntó, y aquí no tienen nada que hacer.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index

from app.database.session import Base

# Sin revisar. Es la bandeja de entrada del panel.
PENDIENTE = "pendiente"
# Alguien le puso la intención correcta. Cuenta para el entrenamiento.
ETIQUETADA = "etiquetada"
# Revisada y descartada: no encaja en ninguna intención, o no tiene sentido.
# Se queda para no volver a proponerla cada semana.
DESCARTADA = "descartada"

ESTADOS = (PENDIENTE, ETIQUETADA, DESCARTADA)

# Cuando la intención correcta es "ninguna de las que existen". Es una
# etiqueta legítima y hace falta: un clasificador también tiene que aprender
# a no clasificar, y sin esto esas preguntas se perderían entre las
# descartadas, que son otra cosa.
NINGUNA = "ninguna"


class ConsultaRegistrada(Base):
    __tablename__ = "consultas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # La pregunta normalizada: minúsculas, sin tildes, espacios colapsados
    # (ver enrutador_service/intenciones.normalizar). ÚNICA, y esa unicidad
    # es lo que agrupa "¿Cuánto vendí hoy?" y "cuanto vendi hoy" en una sola
    # fila con el contador en dos.
    #
    # Que sea única también resuelve la carrera de dos personas preguntando
    # lo mismo a la vez: no se evita comprobando antes si existe —dos
    # peticiones simultáneas pasan las dos por ese `if`— sino dejando que la
    # base rechace la segunda, igual que con las ventas repetidas.
    clave = Column(String(255), nullable=False, unique=True, index=True)

    # El texto tal como lo escribió la primera persona, con sus tildes y sus
    # erratas. Es lo que se lee en el panel para entender qué preguntan de
    # verdad, y lo que un clasificador tendría delante el día de mañana.
    pregunta = Column(String(500), nullable=False)

    veces = Column(Integer, nullable=False, default=1)

    # Lo que el enrutador creyó. NULL = se apartó y respondió el modelo.
    intencion_detectada = Column(String(40), nullable=True)

    # LA ETIQUETA. La pone una persona en el panel. NULL mientras nadie la
    # haya revisado.
    intencion_correcta = Column(String(40), nullable=True)

    estado = Column(String(20), nullable=False, default=PENDIENTE, index=True)

    # Quién la etiquetó. SET NULL como en la bitácora: si esa cuenta se
    # borra, la etiqueta sigue siendo válida. Perder el nombre de quien la
    # puso no invalida el dato.
    revisada_por = Column(
        String(36), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True,
    )

    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ultima_vez = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# El panel entra siempre por lo mismo: qué falta por revisar, y lo más
# preguntado primero. Etiquetar la pregunta que se hizo cuarenta veces vale
# cuarenta veces más que etiquetar la que se hizo una.
Index(
    "ix_consultas_estado_veces",
    ConsultaRegistrada.estado, ConsultaRegistrada.veces,
)
