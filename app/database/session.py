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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()