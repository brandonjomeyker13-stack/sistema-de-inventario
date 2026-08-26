"""
app/database/session.py — Conexión a Postgres (Supabase).

Este es el único archivo que sabe cómo se abre una conexión a la base de
datos. Los repositorios reciben una `Session` ya armada vía Depends(get_db);
nunca crean su propia conexión.

Nota sobre NullPool: si tu DATABASE_URL apunta al connection pooler de
Supabase (puerto 6543, pgbouncer en modo "transaction"), Supabase YA hace
el pooling de conexiones del lado del servidor. Si SQLAlchemy también
intenta poolear encima con su comportamiento por defecto, terminas con
errores intermitentes o agotando el cupo de conexiones bajo carga. Con
NullPool, SQLAlchemy abre/cierra una conexión real por cada uso y deja
que pgbouncer se encargue de reutilizarlas.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)


@event.listens_for(Engine, "connect")
def _activar_llaves_foraneas(conexion, _registro):
    """Hace que SQLite respete las llaves foráneas. PostgreSQL siempre lo hace.

    SQLite las IGNORA por defecto: acepta la declaración, no se queja, y
    simplemente no las aplica. Sin esta línea, las reglas de borrado en
    cascada existirían en producción y no en las pruebas — o sea que ningún
    test podría comprobar que borrar un negocio borra sus productos, ni que
    borrar un producto NO borra las ventas que lo incluyeron.

    Es la misma clase de divergencia entre motores que ya nos mordió con
    ILIKE y los acentos: la prueba pasa en verde y producción se comporta
    distinto.

    Se registra sobre `Engine` y no sobre nuestro engine concreto para que
    también valga en las pruebas, que crean el suyo propio.
    """
    if conexion.__class__.__module__.startswith("sqlite3"):
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()