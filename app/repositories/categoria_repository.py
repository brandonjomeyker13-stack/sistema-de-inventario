"""app/repositories/categoria_repository.py — Acceso a datos de categorías."""

from sqlalchemy.orm import Session

from app.models.categoria import Categoria
from app.models.producto import Producto


def listar(db: Session, usuario_id: str) -> list[Categoria]:
    return (
        db.query(Categoria)
        .filter(Categoria.usuario_id == usuario_id, Categoria.eliminado.is_(False))
        .order_by(Categoria.nombre)
        .all()
    )


def obtener_por_id(db: Session, usuario_id: str, categoria_id: str) -> Categoria | None:
    return (
        db.query(Categoria)
        .filter(
            Categoria.id == categoria_id,
            Categoria.usuario_id == usuario_id,
            Categoria.eliminado.is_(False),
        )
        .first()
    )


def existe_nombre(db: Session, usuario_id: str, nombre: str, excluir_id: str | None = None) -> bool:
    query = db.query(Categoria).filter(
        Categoria.usuario_id == usuario_id,
        Categoria.eliminado.is_(False),
        Categoria.nombre.ilike(nombre.strip()),
    )
    if excluir_id:
        query = query.filter(Categoria.id != excluir_id)
    return db.query(query.exists()).scalar()


def crear(db: Session, usuario_id: str, nombre: str) -> Categoria:
    categoria = Categoria(usuario_id=usuario_id, nombre=nombre.strip())
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


def actualizar(db: Session, categoria: Categoria, nombre: str) -> Categoria:
    categoria.nombre = nombre.strip()
    db.commit()
    db.refresh(categoria)
    return categoria


def eliminar(db: Session, categoria: Categoria) -> None:
    """Borrado suave, y los productos que la usaban quedan sin categoría.

    Se desasignan explícitamente en vez de dejar el categoria_id apuntando
    a una fila borrada: si no, esos productos quedarían con una categoría
    fantasma que no aparece en ninguna lista y no se puede quitar desde la
    interfaz.
    """
    db.query(Producto).filter(Producto.categoria_id == categoria.id).update(
        {Producto.categoria_id: None}
    )
    categoria.eliminado = True
    db.commit()
