"""
app/api/v1/sector.py — Catálogo de sectores de negocio.

Sin autenticación a propósito: el frontend lo necesita en la pantalla de
registro, antes de que exista un usuario. No expone ningún dato — es una
lista fija definida en app/core/sectores.py.
"""

from fastapi import APIRouter

from app.core.sectores import listar
from app.schemas.analitica import SectorOut

router = APIRouter(prefix="/sectores", tags=["Sectores"])


@router.get("", response_model=list[SectorOut])
def listar_sectores():
    """Las opciones válidas para el campo `sector` del negocio."""
    return listar()
