"""
Que los modelos y las migraciones no se separen.

Esta prueba existe por una caída real de producción. Alguien añadió
`cedula` a `app/models/usuario.py` sin crear la migración, y como
SQLAlchemy pide TODAS las columnas del modelo en cada SELECT, Postgres
respondió:

    column usuarios.cedula does not exist

Nadie podía iniciar sesión. Y `alembic upgrade head` corre en cada
arranque en Render, pero no servía de nada: no había migración que correr.

Es el fallo más traicionero de este proyecto porque **en local no se nota**.
La base de pruebas se crea con `create_all()`, que lee los modelos y por
tanto siempre tiene la columna nueva. Solo revienta en producción, donde el
esquema lo construyen las migraciones. Un fallo así no lo encuentra
probando la aplicación: hay que compararlas a propósito.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app.core.config import settings
from app.models import Base

# Diferencias que importan: una tabla o una columna que existe en los
# modelos y no en las migraciones (o al revés) rompe la aplicación en
# cuanto se despliega.
#
# Los cambios de TIPO no se comprueban: la base de prueba es SQLite y la
# real es Postgres, y sus tipos no se corresponden uno a uno (VARCHAR,
# DATETIME, BOOLEAN...). Compararlos daría avisos falsos constantes y la
# prueba acabaría ignorándose, que es peor que no tenerla.
DIFERENCIAS_GRAVES = {
    "add_table", "remove_table", "add_column", "remove_column",
}


def _describir(diferencia) -> str:
    """Traduce una diferencia de Alembic a algo legible."""
    tipo = diferencia[0]
    if tipo in ("add_table", "remove_table"):
        return f"{tipo}: tabla '{diferencia[1].name}'"
    if tipo in ("add_column", "remove_column"):
        return f"{tipo}: {diferencia[2]}.{diferencia[3].name}"
    return str(diferencia)


def test_las_migraciones_construyen_el_mismo_esquema_que_los_modelos(tmp_path, monkeypatch):
    """Corre TODAS las migraciones sobre una base vacía y la compara con
    los modelos. Si falta una migración, aquí salta."""
    ruta = str(tmp_path / "migraciones.db").replace("\\", "/")
    url = f"sqlite:///{ruta}"

    # migrations/env.py construye el engine desde settings.DATABASE_URL,
    # no desde alembic.ini (a propósito: configparser trata el '%' de una
    # contraseña escapada como sintaxis de interpolación y revienta).
    monkeypatch.setattr(settings, "DATABASE_URL", url)

    command.upgrade(Config("alembic.ini"), "head")

    motor = create_engine(url)
    try:
        with motor.connect() as conexion:
            contexto = MigrationContext.configure(conexion)
            diferencias = compare_metadata(contexto, Base.metadata)
    finally:
        motor.dispose()

    graves = [d for d in diferencias if isinstance(d, tuple) and d[0] in DIFERENCIAS_GRAVES]

    assert not graves, (
        "Los modelos y las migraciones no coinciden:\n  "
        + "\n  ".join(_describir(d) for d in graves)
        + "\n\nFalta una migración. Crea una con:\n"
          "  alembic revision -m \"descripcion\"\n"
          "y añade el add_column/add_table que corresponda."
    )


def test_todas_las_migraciones_se_pueden_deshacer(tmp_path, monkeypatch):
    """Sube hasta la última y vuelve a bajar hasta el principio.

    Un `downgrade` roto no se nota hasta el día que hay que usarlo, que es
    justo el peor día posible: con producción a medio migrar y prisa.
    """
    ruta = str(tmp_path / "ida-y-vuelta.db").replace("\\", "/")
    url = f"sqlite:///{ruta}"
    monkeypatch.setattr(settings, "DATABASE_URL", url)

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
