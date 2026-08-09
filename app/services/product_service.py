from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.repositories import producto_repository, categoria_repository


def listar(db: Session, usuario_id: str):
    return producto_repository.listar(db, usuario_id)


def buscar_por_codigo_barras(db: Session, usuario_id: str, codigo: str):
    """Lo que consulta el lector al escanear.

    Si devuelve None no es un error: significa "este código no lo conozco
    todavía", y el frontend debe ofrecer darlo de alta. Por eso no lanza
    NoEncontrado — es un caso normal, no un fallo.
    """
    return producto_repository.obtener_por_codigo_barras(db, usuario_id, codigo)


def _validar_categoria(db: Session, usuario_id: str, categoria_id: str | None):
    """Que la categoría exista y sea de este negocio.

    Sin esto, mandar el categoria_id de otro usuario dejaría un producto
    apuntando a una categoría ajena — una fuga silenciosa entre tiendas.
    """
    if categoria_id and not categoria_repository.obtener_por_id(db, usuario_id, categoria_id):
        raise NoEncontrado("Categoría no encontrada")


def agregar(
    db: Session, usuario_id: str, nombre: str, cantidad: int, precio: float, costo: float,
    codigo_barras: str | None = None, categoria_id: str | None = None,
):
    if producto_repository.existe_nombre(db, usuario_id, nombre):
        raise ErrorNegocio(f"Ya existe un producto llamado '{nombre.strip()}'")
    if codigo_barras and producto_repository.existe_codigo_barras(db, usuario_id, codigo_barras):
        raise ErrorNegocio(f"Ya tienes un producto con el código {codigo_barras.strip()}")
    _validar_categoria(db, usuario_id, categoria_id)
    return producto_repository.crear(
        db, usuario_id, nombre, cantidad, precio, costo, codigo_barras, categoria_id
    )


def editar(
    db: Session, usuario_id: str, producto_id: str, nombre: str, cantidad: int, precio: float,
    costo: float, codigo_barras: str | None = None, categoria_id: str | None = None,
):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    if producto_repository.existe_nombre(db, usuario_id, nombre, excluir_id=producto_id):
        raise ErrorNegocio(f"Ya existe otro producto llamado '{nombre.strip()}'")
    if codigo_barras and producto_repository.existe_codigo_barras(
        db, usuario_id, codigo_barras, excluir_id=producto_id
    ):
        raise ErrorNegocio(f"Otro producto ya usa el código {codigo_barras.strip()}")
    _validar_categoria(db, usuario_id, categoria_id)
    return producto_repository.actualizar(
        db, producto, nombre, cantidad, precio, costo, codigo_barras, categoria_id
    )


def eliminar(db: Session, usuario_id: str, producto_id: str):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    producto_repository.eliminar(db, producto)
