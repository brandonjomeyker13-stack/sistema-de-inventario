"""app/api/v1/categoria.py — Categorías de producto."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa
from app.models.usuario import Usuario
from app.schemas.categoria import CategoriaCrear, CategoriaActualizar, CategoriaOut
from app.services import categoria_service

router = APIRouter(prefix="/categorias", tags=["Categorías"])


@router.get("", response_model=list[CategoriaOut])
def listar(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return categoria_service.listar(db, usuario_actual.id)


@router.post("", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED)
def agregar(
    datos: CategoriaCrear,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    return categoria_service.agregar(db, usuario_actual.id, datos.nombre)


@router.put("/{categoria_id}", response_model=CategoriaOut)
def editar(
    categoria_id: str,
    datos: CategoriaActualizar,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    return categoria_service.editar(db, usuario_actual.id, categoria_id, datos.nombre)


@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    categoria_id: str,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Los productos que la usaban no se borran: quedan sin categoría."""
    categoria_service.eliminar(db, usuario_actual.id, categoria_id)
