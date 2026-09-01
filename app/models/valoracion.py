"""
app/models/valoracion.py — Cuando el tendero dice si Trackie acertó.

POR QUÉ ESTA TABLA SÍ GUARDA LA RESPUESTA

`consultas` guarda solo la pregunta, nunca la respuesta, porque la respuesta
lleva las cifras del negocio y el panel no muestra los datos de nadie.

Aquí es distinto, y la diferencia es el consentimiento: esta fila solo existe
porque el dueño del negocio pulsó un botón pidiendo que revisemos ESE
intercambio. Sin ese gesto no se guarda nada.

Por eso la tabla se llena a cuentagotas y con permiso, en vez de acumular en
silencio lo que responde el asistente.

POR QUÉ SÍ LLEVA usuario_id, AL CONTRARIO QUE `consultas`

`consultas` se recoge en silencio, sin que nadie la autorice, y por eso no
guarda de quién es cada pregunta.

Aquí es al revés: la fila existe porque él pidió que la revisáramos. Y
revisar una queja como "me dijo 3 y en verdad son 5" significa ir a mirar de
dónde salió el 3. Sin saber qué cuenta fue, se ve QUÉ estuvo mal pero no se
puede comprobar nada, y la queja no sirve para arreglar el problema.

Guardarlo tampoco expone nada nuevo: la respuesta que ya está en esta tabla
lleva sus cifras. No saber de quién son no las esconde — solo impide
usarlas. Y como se le dice en la pantalla al calificar, no es una
anonimidad que él crea tener.

LA MEJOR ETIQUETA DEL PROYECTO

Un pulgar abajo de quien está mirando su propia estantería vale más que cien
clasificaciones hechas desde el panel. El tendero es el único que sabe si
"tienes 3 productos por comprar" era verdad.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database.session import Base

BUENA = "buena"
MALA = "mala"
VALORACIONES = (BUENA, MALA)

# De dónde salió la respuesta que se calificó. Es la métrica que dice si el
# enrutador está ayudando o estorbando: si sus respuestas se llevan más
# pulgares abajo que las del modelo, hay disparadores que sobran.
DEL_ENRUTADOR = "enrutador"
DEL_MODELO = "modelo"
ORIGENES = (DEL_ENRUTADOR, DEL_MODELO)

PENDIENTE = "pendiente"
REVISADA = "revisada"
ESTADOS = (PENDIENTE, REVISADA)


class Valoracion(Base):
    __tablename__ = "valoraciones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # De quién es la queja. SET NULL, no CASCADE: si la cuenta se borra, lo
    # que se aprendió de su queja sigue valiendo aunque ya no se pueda ir a
    # comprobar nada contra sus datos.
    usuario_id = Column(
        String(36), ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    usuario = relationship("Usuario", foreign_keys=[usuario_id])

    # Una fila por calificación, no una por pregunta: la misma pregunta puede
    # responderse bien un día y mal otro, y las dos veces son datos.
    pregunta = Column(String(1000), nullable=False)
    respuesta = Column(String(4000), nullable=False)

    origen = Column(String(20), nullable=False)
    intencion_detectada = Column(String(40), nullable=True)

    valoracion = Column(String(10), nullable=False, index=True)

    # Lo que escriba el tendero al marcar el pulgar abajo. Opcional, y es lo
    # más valioso de la fila cuando está: "me dijo 3 y en verdad son 5".
    comentario = Column(String(500), nullable=True)

    estado = Column(String(20), nullable=False, default=PENDIENTE, index=True)

    # Qué intención era en realidad, según quien la revisó. Es lo que conecta
    # esta tabla con el entrenamiento: una queja etiquetada es un ejemplo.
    intencion_correcta = Column(String(40), nullable=True)

    # SET NULL como en la bitácora: si esa cuenta se borra, la revisión sigue
    # siendo válida.
    revisada_por = Column(
        String(36), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True,
    )

    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    @property
    def negocio(self) -> str | None:
        """El nombre del negocio, para que el panel no muestre un id crudo.

        Devuelve None cuando la cuenta ya se borró, y ahí el panel dice
        "cuenta eliminada" — igual que en la bitácora.
        """
        return self.usuario.nombre_negocio if self.usuario else None


# El panel entra por "las malas sin revisar, las más recientes primero".
Index(
    "ix_valoraciones_valoracion_estado",
    Valoracion.valoracion, Valoracion.estado, Valoracion.creado_en,
)
