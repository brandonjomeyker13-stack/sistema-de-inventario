"""
app/api/v1/router.py — Punto de entrada de la versión 1 de la API.

Junta todos los routers de recursos bajo el prefijo /api/v1. main.py solo
conoce este archivo; no conoce auth.py, usuario.py, producto.py ni
venta.py directamente — así el día que exista una v2, se agrega
app/api/v2/ sin tocar main.py.
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth, usuario, producto, venta, cliente, categoria, canasta, analitica, sector,
)

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(usuario.router)
router.include_router(producto.router)
router.include_router(venta.router)
router.include_router(cliente.router)
router.include_router(categoria.router)
router.include_router(canasta.router)
router.include_router(analitica.router)
router.include_router(sector.router)