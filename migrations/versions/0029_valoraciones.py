"""Cuando el tendero dice si Trackie acertó.

POR QUÉ ESTA TABLA SÍ GUARDA LA RESPUESTA, Y `consultas` NO

`consultas` (migración 0028) guarda solo la pregunta: la respuesta lleva las
cifras del negocio y el panel no muestra los datos de nadie.

Aquí la diferencia es el consentimiento. Una fila solo existe porque el dueño
pulsó un botón pidiendo que revisemos ESE intercambio. Sin ese gesto no se
guarda nada, así que la tabla se llena a cuentagotas y con permiso en vez de
acumular en silencio lo que responde el asistente.

Tampoco lleva `usuario_id`: calificar es decir "revisen esto", no "miren mi
negocio".

Revision ID: 0029
Revises: 0028
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "valoraciones",
        sa.Column("id", sa.String(length=36), nullable=False),
        # Una fila por calificación, no una por pregunta: la misma pregunta
        # puede responderse bien un día y mal otro, y las dos veces son datos.
        sa.Column("pregunta", sa.String(length=1000), nullable=False),
        sa.Column("respuesta", sa.String(length=4000), nullable=False),
        # 'enrutador' o 'modelo'. Es la métrica que dice si el enrutador
        # ayuda o estorba.
        sa.Column("origen", sa.String(length=20), nullable=False),
        sa.Column("intencion_detectada", sa.String(length=40), nullable=True),
        sa.Column("valoracion", sa.String(length=10), nullable=False),
        # Lo que escriba al marcar el pulgar abajo. Es lo más valioso de la
        # fila cuando está: "me dijo 3 y en verdad son 5".
        sa.Column("comentario", sa.String(length=500), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("intencion_correcta", sa.String(length=40), nullable=True),
        sa.Column("revisada_por", sa.String(length=36), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["revisada_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_valoraciones_valoracion", "valoraciones", ["valoracion"])
    op.create_index("ix_valoraciones_estado", "valoraciones", ["estado"])
    # El panel entra por "las malas sin revisar, las más recientes primero".
    op.create_index(
        "ix_valoraciones_valoracion_estado", "valoraciones",
        ["valoracion", "estado", "creado_en"],
    )


def downgrade() -> None:
    op.drop_index("ix_valoraciones_valoracion_estado", table_name="valoraciones")
    op.drop_index("ix_valoraciones_estado", table_name="valoraciones")
    op.drop_index("ix_valoraciones_valoracion", table_name="valoraciones")
    op.drop_table("valoraciones")
