"""
app/repositories/movimiento_repository.py — Acceso al libro de movimientos.

`registrar` NO hace commit. Es deliberado: un movimiento nunca existe por
su cuenta, siempre acompaña a un cambio de stock. Si hiciera commit
propio, una venta que falla a mitad dejaría el movimiento escrito y el
stock sin tocar — un libro que miente. Quien llama decide cuándo cerrar
la transacción, y así ambos se guardan o ninguno.
"""

from sqlalchemy.orm import Session

from app.models.movimiento import MovimientoInventario


def registrar(
    db: Session, usuario_id: str, producto_id: str, tipo: str, cantidad: int,
    stock_antes: int, fecha: str, motivo: str | None = None,
    costo_unitario: float | None = None, venta_id: str | None = None,
) -> MovimientoInventario:
    movimiento = MovimientoInventario(
        usuario_id=usuario_id,
        producto_id=producto_id,
        tipo=tipo,
        cantidad=cantidad,
        stock_antes=stock_antes,
        stock_despues=stock_antes + cantidad,
        costo_unitario=costo_unitario,
        motivo=motivo,
        venta_id=venta_id,
        fecha=fecha,
    )
    db.add(movimiento)
    return movimiento


def listar(
    db: Session, usuario_id: str, producto_id: str | None = None,
    tipo: str | None = None, desde: str | None = None, hasta: str | None = None,
    limite: int = 100, offset: int = 0,
) -> list[MovimientoInventario]:
    query = db.query(MovimientoInventario).filter(
        MovimientoInventario.usuario_id == usuario_id
    )
    if producto_id:
        query = query.filter(MovimientoInventario.producto_id == producto_id)
    if tipo:
        query = query.filter(MovimientoInventario.tipo == tipo)
    if desde:
        query = query.filter(MovimientoInventario.fecha >= desde)
    if hasta:
        query = query.filter(MovimientoInventario.fecha <= hasta)

    return (
        query
        # Por creado_en y no solo por fecha: varios movimientos del mismo
        # día tienen que salir en el orden real en que ocurrieron.
        .order_by(MovimientoInventario.fecha.desc(), MovimientoInventario.creado_en.desc())
        .limit(limite)
        .offset(offset)
        .all()
    )


def contar(
    db: Session, usuario_id: str, producto_id: str | None = None,
    tipo: str | None = None, desde: str | None = None, hasta: str | None = None,
) -> int:
    query = db.query(MovimientoInventario).filter(
        MovimientoInventario.usuario_id == usuario_id
    )
    if producto_id:
        query = query.filter(MovimientoInventario.producto_id == producto_id)
    if tipo:
        query = query.filter(MovimientoInventario.tipo == tipo)
    if desde:
        query = query.filter(MovimientoInventario.fecha >= desde)
    if hasta:
        query = query.filter(MovimientoInventario.fecha <= hasta)
    return query.count()
