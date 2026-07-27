"""
app/main.py — Punto de entrada de la API.

Este archivo NO tiene lógica de negocio. Solo: arma la app de FastAPI,
configura CORS (para que Lovable pueda llamarla desde otro dominio),
traduce las excepciones de negocio a códigos HTTP, y monta las rutas.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import ErrorNegocio, NoEncontrado, CredencialesInvalidas
from app.database.session import Base, engine
from app.api.v1.router import router as api_v1_router

# Se importan los modelos para que Base los conozca antes del create_all
# de más abajo. No se usan directamente en este archivo.
from app.models import usuario, producto, venta  # noqa: F401

app = FastAPI(title="NorBox API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def crear_tablas():
    # Suficiente para el MVP: crea las tablas si no existen. El día que el
    # esquema cambie con datos reales ya guardados (agregar una columna,
    # por ejemplo), esto se reemplaza por migraciones con Alembic —
    # create_all no sabe hacer ALTER TABLE sobre tablas existentes.
    Base.metadata.create_all(bind=engine)


@app.exception_handler(ErrorNegocio)
def manejar_error_negocio(request: Request, exc: ErrorNegocio):
    return JSONResponse(status_code=400, content={"detalle": str(exc)})


@app.exception_handler(NoEncontrado)
def manejar_no_encontrado(request: Request, exc: NoEncontrado):
    return JSONResponse(status_code=404, content={"detalle": str(exc)})


@app.exception_handler(CredencialesInvalidas)
def manejar_credenciales_invalidas(request: Request, exc: CredencialesInvalidas):
    return JSONResponse(status_code=401, content={"detalle": str(exc)})


app.include_router(api_v1_router)


@app.get("/")
def salud():
    """Útil para que Render confirme que el servicio está vivo, y para
    verificar rápido en el navegador que el deploy funcionó."""
    return {"estado": "ok", "servicio": "NorBox API"}