"""app/services/categoria_service.py — Categorías de producto."""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.repositories import categoria_repository


def listar(db: Session, usuario_id: str):
    return categoria_repository.listar(db, usuario_id)


def agregar(db: Session, usuario_id: str, nombre: str):
    if categoria_repository.existe_nombre(db, usuario_id, nombre):
        raise ErrorNegocio(f"Ya existe la categoría '{nombre.strip()}'")
    return categoria_repository.crear(db, usuario_id, nombre)


def editar(db: Session, usuario_id: str, categoria_id: str, nombre: str):
    categoria = categoria_repository.obtener_por_id(db, usuario_id, categoria_id)
    if not categoria:
        raise NoEncontrado("Categoría no encontrada")
    if categoria_repository.existe_nombre(db, usuario_id, nombre, excluir_id=categoria_id):
        raise ErrorNegocio(f"Ya existe otra categoría '{nombre.strip()}'")
    return categoria_repository.actualizar(db, categoria, nombre)


def eliminar(db: Session, usuario_id: str, categoria_id: str):
    categoria = categoria_repository.obtener_por_id(db, usuario_id, categoria_id)
    if not categoria:
        raise NoEncontrado("Categoría no encontrada")
    # Los productos no se borran: quedan sin categoría (ver el repositorio).
    categoria_repository.eliminar(db, categoria)
