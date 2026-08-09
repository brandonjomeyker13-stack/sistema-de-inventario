"""
app/repositories/producto_repository.py — Acceso a datos de productos.

Toda función recibe `usuario_id` y filtra por él: es la barrera técnica
que garantiza que un negocio nunca vea ni modifique el inventario de
otro, sin importar qué producto_id le manden en la URL.
"""

from sqlalchemy.orm import Session

from app.models.producto import Producto


def listar(db: Session, usuario_id: str) -> list[Producto]:
    return (
        db.query(Producto)
        .filter(Producto.usuario_id == usuario_id, Producto.eliminado.is_(False))
        .order_by(Producto.nombre)
        .all()
    )


def obtener_por_id(db: Session, usuario_id: str, producto_id: str) -> Producto | None:
    return (
        db.query(Producto)
        .filter(Producto.id == producto_id, Producto.usuario_id == usuario_id, Producto.eliminado.is_(False))
        .first()
    )


def obtener_por_nombre(db: Session, usuario_id: str, nombre: str) -> Producto | None:
    return (
        db.query(Producto)
        .filter(
            Producto.usuario_id == usuario_id,
            Producto.eliminado.is_(False),
            Producto.nombre.ilike(nombre.strip()),
        )
        .first()
    )


def obtener_por_codigo_barras(db: Session, usuario_id: str, codigo: str) -> Producto | None:
    return (
        db.query(Producto)
        .filter(
            Producto.usuario_id == usuario_id,
            Producto.eliminado.is_(False),
            Producto.codigo_barras == codigo.strip(),
        )
        .first()
    )


def existe_codigo_barras(db: Session, usuario_id: str, codigo: str, excluir_id: str | None = None) -> bool:
    query = db.query(Producto).filter(
        Producto.usuario_id == usuario_id,
        Producto.eliminado.is_(False),
        Producto.codigo_barras == codigo.strip(),
    )
    if excluir_id:
        query = query.filter(Producto.id != excluir_id)
    return db.query(query.exists()).scalar()


def existe_nombre(db: Session, usuario_id: str, nombre: str, excluir_id: str | None = None) -> bool:
    query = db.query(Producto).filter(
        Producto.usuario_id == usuario_id,
        Producto.eliminado.is_(False),
        Producto.nombre.ilike(nombre.strip()),
    )
    if excluir_id:
        query = query.filter(Producto.id != excluir_id)
    return db.query(query.exists()).scalar()


def crear(
    db: Session, usuario_id: str, nombre: str, cantidad: int, precio: float, costo: float,
    codigo_barras: str | None = None, categoria_id: str | None = None,
) -> Producto:
    producto = Producto(
        usuario_id=usuario_id, nombre=nombre.strip(), cantidad=cantidad, precio=precio, cuanto_costo=costo,
        codigo_barras=codigo_barras.strip() if codigo_barras else None,
        categoria_id=categoria_id,
    )
    db.add(producto)
    db.commit()
    db.refresh(producto)
    return producto


def actualizar(
    db: Session, producto: Producto, nombre: str, cantidad: int, precio: float, costo: float,
    codigo_barras: str | None = None, categoria_id: str | None = None,
) -> Producto:
    producto.nombre = nombre.strip()
    producto.cantidad = cantidad
    producto.precio = precio
    producto.cuanto_costo = costo
    # Cadena vacía se guarda como NULL: si no, el índice único trataría
    # dos productos "sin código" como duplicados y el segundo fallaría.
    producto.codigo_barras = codigo_barras.strip() if codigo_barras and codigo_barras.strip() else None
    producto.categoria_id = categoria_id
    db.commit()
    db.refresh(producto)
    return producto


def eliminar(db: Session, producto: Producto) -> None:
    producto.eliminado = True
    db.commit()