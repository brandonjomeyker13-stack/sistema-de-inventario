"""
tests/conftest.py — Preparación común de las pruebas.

Las variables de entorno se ponen ANTES de importar nada de `app`:
`app.core.config` lee el entorno al importarse, así que hacerlo después no
tendría efecto y las pruebas acabarían apuntando a la base de datos real.

Cada prueba recibe una base SQLite en memoria, vacía y suya. Ni tocan
Supabase ni se estorban entre ellas.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-con-largo-suficiente")
os.environ.setdefault("ZONA_HORARIA", "America/Bogota")
# Sin clave de Groq ni de Resend: las pruebas no deben llamar a nadie por
# la red. Si alguna lo intenta, falla de forma evidente en vez de gastar
# cuota —o de mandar un correo de verdad— en silencio.
#
# SE ASIGNA VACÍO, NO SE BORRA. Antes aquí había un `os.environ.pop(...)` y
# no servía de nada: `Settings` está declarado con `env_file=".env"`, así
# que pydantic lee ESE ARCHIVO además del entorno. Borrar la variable del
# entorno no borra la línea del .env, y las pruebas seguían saliendo a
# internet con las claves reales sin que nadie lo notara.
#
# Las variables de entorno SÍ tienen prioridad sobre el .env, así que
# ponerlas vacías es lo que de verdad las anula. Ambos sitios que las usan
# comprueban por verdad (app/core/llm.py y app/core/correo.py), así que la
# cadena vacía se comporta igual que no tenerla.
os.environ["GROQ_API_KEY"] = ""
os.environ["RESEND_API_KEY"] = ""

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database.session import Base  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Usuario  # noqa: E402


@pytest.fixture
def db():
    """Una base limpia por prueba.

    StaticPool + `check_same_thread` para que todas las conexiones vean la
    MISMA base en memoria; sin eso, SQLite le da una base vacía a cada
    conexión y las tablas parecen no existir.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield sesion
    finally:
        sesion.close()
        engine.dispose()


@pytest.fixture
def usuario(db):
    """Un negocio con la suscripción al día."""
    u = Usuario(
        id="u1",
        email="tienda@ejemplo.com",
        password_hash=hash_password("clave-de-prueba"),
        nombre_negocio="Tienda de prueba",
        activo=True,
        email_verificado=True,
        suscripcion_hasta="2099-12-31",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def otro_usuario(db):
    """Un segundo negocio, para comprobar que no se ven entre ellos."""
    u = Usuario(
        id="u2",
        email="otra@ejemplo.com",
        password_hash=hash_password("clave-de-prueba"),
        nombre_negocio="Otra tienda",
        activo=True,
        email_verificado=True,
        suscripcion_hasta="2099-12-31",
    )
    db.add(u)
    db.commit()
    return u
