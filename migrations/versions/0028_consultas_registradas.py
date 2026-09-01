"""Guardar qué le pregunta la gente a Trackie.

POR QUÉ

Hoy el chat es efímero: se responde y no queda nada. Eso significa que
decidir qué preguntas vale la pena responder sin modelo es adivinar, y que
el día que queramos entrenar un clasificador propio no habrá con qué.

Esta tabla es las dos cosas. A corto plazo dice qué se pregunta de verdad; a
largo plazo es el conjunto de entrenamiento, porque guarda la pregunta junto
con la intención que un administrador dice que era.

LO QUE NO LLEVA

No hay `usuario_id` y no se guarda la respuesta. Para entrenar no hace falta
saber quién preguntó, y la respuesta lleva las cifras del negocio que la
hizo. Sin esas dos columnas, el panel no puede atar una pregunta a un
cliente ni por descuido.

`revisada_por` va con ON DELETE SET NULL, como la bitácora: si se borra la
cuenta de quien etiquetó, la etiqueta sigue siendo válida.

Revision ID: 0028
Revises: 0027
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consultas",
        sa.Column("id", sa.String(length=36), nullable=False),
        # La pregunta normalizada. Única: es lo que agrupa "¿Cuánto vendí
        # hoy?" y "cuanto vendi hoy" en una fila con el contador en dos, y
        # lo que hace que dos personas preguntando a la vez no creen dos.
        sa.Column("clave", sa.String(length=255), nullable=False),
        sa.Column("pregunta", sa.String(length=500), nullable=False),
        sa.Column("veces", sa.Integer(), nullable=False),
        # NULL = el enrutador se apartó y respondió el modelo. Son las filas
        # más valiosas: cada una es una pregunta que hoy cuesta tokens.
        sa.Column("intencion_detectada", sa.String(length=40), nullable=True),
        # La etiqueta, puesta a mano desde el panel.
        sa.Column("intencion_correcta", sa.String(length=40), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("revisada_por", sa.String(length=36), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_vez", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["revisada_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultas_clave", "consultas", ["clave"], unique=True)
    op.create_index("ix_consultas_estado", "consultas", ["estado"])
    # El panel entra siempre por "qué falta por revisar, lo más preguntado
    # primero": etiquetar la pregunta que se hizo cuarenta veces vale
    # cuarenta veces más que etiquetar la que se hizo una.
    op.create_index("ix_consultas_estado_veces", "consultas", ["estado", "veces"])


def downgrade() -> None:
    op.drop_index("ix_consultas_estado_veces", table_name="consultas")
    op.drop_index("ix_consultas_estado", table_name="consultas")
    op.drop_index("ix_consultas_clave", table_name="consultas")
    op.drop_table("consultas")
