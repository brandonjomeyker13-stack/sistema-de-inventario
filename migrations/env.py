"""
migrations/env.py — Puente entre Alembic y la aplicación.

Dos decisiones que conviene entender:

1. La URL de la base sale de `settings.DATABASE_URL`, no de alembic.ini.
   Una sola fuente de verdad: la misma variable de entorno que usa la API.

2. Se importan todos los modelos aquí abajo aunque no se usen. Alembic
   compara `Base.metadata` contra la base real para detectar cambios, y
   un modelo que nadie importó no está en `Base.metadata` — Alembic lo
   leería como "esta tabla sobra" y generaría un DROP TABLE. Si algún día
   agregas un modelo nuevo, agrégalo también a esta lista.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app.core.config import settings
from app.database.session import Base

# Importar los modelos puebla Base.metadata. No se usan directamente.
from app.models import usuario, producto, venta, sesion, token_verificacion  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Se conecta a la base y aplica las migraciones pendientes.

    El engine se construye directamente desde settings.DATABASE_URL, sin
    pasar por alembic.ini. No es un capricho: escribir la URL en el ini
    la hace pasar por configparser, que trata `%` como sintaxis de
    interpolación y revienta con cualquier contraseña que lleve
    caracteres escapados (`%40` para una arroba, por ejemplo).
    """
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
