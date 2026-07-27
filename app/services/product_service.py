from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.repositories import producto_repository


def listar(db: Session, usuario_id: str):
    return producto_repository.listar(db, usuario_id)


def agregar(db: Session, usuario_id: str, nombre: str, cantidad: int, precio: float, costo: float):
    if producto_repository.existe_nombre(db, usuario_id, nombre):
        raise ErrorNegocio(f"Ya existe un producto llamado '{nombre.strip()}'")
    return producto_repository.crear(db, usuario_id, nombre, cantidad, precio, costo)


def editar(db: Session, usuario_id: str, producto_id: str, nombre: str, cantidad: int, precio: float, costo: float):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    if producto_repository.existe_nombre(db, usuario_id, nombre, excluir_id=producto_id):
        raise ErrorNegocio(f"Ya existe otro producto llamado '{nombre.strip()}'")
    return producto_repository.actualizar(db, producto, nombre, cantidad, precio, costo)


def eliminar(db: Session, usuario_id: str, producto_id: str):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    producto_repository.eliminar(db, producto)