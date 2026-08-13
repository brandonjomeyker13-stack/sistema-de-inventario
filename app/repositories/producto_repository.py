"""
app/repositories/producto_repository.py — Acceso a datos de productos.

Toda función recibe `usuario_id` y filtra por él: es la barrera técnica
que garantiza que un negocio nunca vea ni modifique el inventario de
otro, sin importar qué producto_id le manden en la URL.
"""

from sqlalchemy.orm import Session

from app.core.codigos import normalizar
from app.models.producto import Producto


def _query_listado(db: Session, usuario_id: str, q: str | None = None,
                   categoria_id: str | None = None):
    query = db.query(Producto).filter(
        Producto.usuario_id == usuario_id, Producto.eliminado.is_(False)
    )
    if q:
        termino = f"%{q.strip()}%"
        # Busca por nombre o por código: el tendero teclea "arr" o pasa el
        # lector, y en los dos casos espera encontrar lo mismo.
        query = query.filter(
            Producto.nombre.ilike(termino) | Producto.codigo_barras.ilike(termino)
        )
    if categoria_id:
        query = query.filter(Producto.categoria_id == categoria_id)
    return query


def listar(db: Session, usuario_id: str, q: str | None = None,
           categoria_id: str | None = None, limite: int | None = None,
           offset: int = 0) -> list[Producto]:
    """El inventario, con búsqueda y paginación opcionales.

    `limite` es None por defecto a propósito: poner un tope por defecto
    truncaría en silencio el inventario de quien ya tiene 500 productos, y
    la caja mostraría un catálogo incompleto sin que nadie se entere. Es
    preferible una respuesta grande a una respuesta incorrecta; quien
    quiera paginar, que lo pida.
    """
    query = _query_listado(db, usuario_id, q, categoria_id).order_by(Producto.nombre)
    if offset:
        query = query.offset(offset)
    if limite is not None:
        query = query.limit(limite)
    return query.all()


def contar(db: Session, usuario_id: str, q: str | None = None,
           categoria_id: str | None = None) -> int:
    return _query_listado(db, usuario_id, q, categoria_id).count()


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
            # Se normaliza también al buscar: si el catálogo guarda el
            # EAN-13 y el lector manda el UPC-A de 12 dígitos, tienen que
            # encontrarse igual.
            Producto.codigo_barras == normalizar(codigo),
        )
        .first()
    )


def mapa_por_id(db: Session, usuario_id: str, ids: list[str]) -> dict[str, Producto]:
    """Varios productos de golpe, indexados por id.

    Existe para el pintado de la canasta, que se consulta cada segundo y
    medio mientras hay una venta en curso. Resolviendo producto a
    producto, una canasta de diez líneas eran once consultas por cada
    sondeo: unas cuatrocientas por minuto contra Supabase, para mostrar
    una lista que casi nunca cambia.
    """
    if not ids:
        return {}
    productos = (
        db.query(Producto)
        .filter(
            Producto.usuario_id == usuario_id,
            Producto.eliminado.is_(False),
            Producto.id.in_(ids),
        )
        .all()
    )
    return {p.id: p for p in productos}


def mapa_por_codigo_barras(db: Session, usuario_id: str, codigos: list[str]) -> dict[str, Producto]:
    """Igual que mapa_por_id, para los códigos que aún no tienen producto.

    Se indexa por el código NORMALIZADO, que es como está guardado y como
    hay que buscarlo. Quien llame debe normalizar también su clave antes
    de consultar el diccionario.
    """
    normalizados = [c for c in (normalizar(c) for c in codigos if c) if c]
    if not normalizados:
        return {}
    productos = (
        db.query(Producto)
        .filter(
            Producto.usuario_id == usuario_id,
            Producto.eliminado.is_(False),
            Producto.codigo_barras.in_(normalizados),
        )
        .all()
    )
    return {p.codigo_barras: p for p in productos}


def existe_codigo_barras(db: Session, usuario_id: str, codigo: str, excluir_id: str | None = None) -> bool:
    query = db.query(Producto).filter(
        Producto.usuario_id == usuario_id,
        Producto.eliminado.is_(False),
        # Misma normalización que al buscar: si no, registrar el UPC-A
        # corto de un producto que ya está guardado como EAN-13 pasaría
        # el control de duplicados y lo duplicaría.
        Producto.codigo_barras == normalizar(codigo),
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
        # Normalizado también aquí, no solo en el schema: el servicio se
        # llama desde sitios que no pasan por Pydantic (la recepción de
        # mercancía, por ejemplo) y el dato guardado tiene que ser
        # canónico venga de donde venga.
        codigo_barras=normalizar(codigo_barras),
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
    producto.codigo_barras = normalizar(codigo_barras)
    producto.categoria_id = categoria_id
    db.commit()
    db.refresh(producto)
    return producto


def eliminar(db: Session, producto: Producto) -> None:
    producto.eliminado = True
    db.commit()