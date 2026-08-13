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
from app.core.exceptions import (
    ErrorNegocio, NoEncontrado, CredencialesInvalidas, SuscripcionVencida,
    CorreoSinVerificar,
)
from app.core.limites import DemasiadosIntentos
from app.api.v1.router import router as api_v1_router

app = FastAPI(title="NorBox API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# El esquema ya no se crea al arrancar. Lo gestiona Alembic
# (`alembic upgrade head`, que corre en el startCommand de render.yaml).
# create_all servía para el MVP, pero no sabe hacer ALTER TABLE: en
# cuanto hay datos guardados y cambia una columna, deja de funcionar.


@app.exception_handler(ErrorNegocio)
def manejar_error_negocio(request: Request, exc: ErrorNegocio):
    return JSONResponse(status_code=400, content={"detalle": str(exc)})


@app.exception_handler(NoEncontrado)
def manejar_no_encontrado(request: Request, exc: NoEncontrado):
    return JSONResponse(status_code=404, content={"detalle": str(exc)})


@app.exception_handler(CredencialesInvalidas)
def manejar_credenciales_invalidas(request: Request, exc: CredencialesInvalidas):
    return JSONResponse(status_code=401, content={"detalle": str(exc)})


@app.exception_handler(CorreoSinVerificar)
def manejar_correo_sin_verificar(request: Request, exc: CorreoSinVerificar):
    # 403 y no 402: el problema no es el dinero, y la pantalla que hay que
    # mostrar es otra (reenviar el enlace, no renovar el plan).
    return JSONResponse(status_code=403, content={"detalle": str(exc)})


@app.exception_handler(DemasiadosIntentos)
def manejar_demasiados_intentos(request: Request, exc: DemasiadosIntentos):
    # Retry-After es estándar: dice cuántos segundos esperar. El frontend
    # puede mostrar una cuenta atrás en vez de un error opaco que invita a
    # seguir pulsando el botón.
    return JSONResponse(
        status_code=429,
        content={"detalle": str(exc), "reintentar_en": exc.segundos},
        headers={"Retry-After": str(exc.segundos)},
    )


@app.exception_handler(SuscripcionVencida)
def manejar_suscripcion_vencida(request: Request, exc: SuscripcionVencida):
    # 402 Payment Required. Código propio para que el frontend distinga
    # "hay que renovar" de un error de validación sin leer el mensaje.
    return JSONResponse(status_code=402, content={"detalle": str(exc)})


app.include_router(api_v1_router)


@app.get("/")
def salud():
    """Útil para que Render confirme que el servicio está vivo, y para
    verificar rápido en el navegador que el deploy funcionó."""
    return {"estado": "ok", "servicio": "NorBox API"}



