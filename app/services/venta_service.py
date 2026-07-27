from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import NoEncontrado, ErrorNegocio
from app.repositories import producto_repository, venta_repository


def _fecha_local_hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def vender(db: Session, usuario_id: str, nombre_producto: str, cantidad: int):
    producto = producto_repository.obtener_por_nombre(db, usuario_id, nombre_producto)
    if not producto:
        raise NoEncontrado("Ese producto no existe en el inventario")
    if producto.cantidad < cantidad:
        raise ErrorNegocio(f"No puedes vender más de lo que hay en stock (disponible: {producto.cantidad})")

    total = round(cantidad * producto.precio, 2)
    ganancia = round((producto.precio - producto.cuanto_costo) * cantidad, 2)

    return venta_repository.crear_venta_atomica(
        db, usuario_id, producto, cantidad, total, ganancia, _fecha_local_hoy(),
    )


def ventas_por_fecha(db: Session, usuario_id: str, fecha: str):
    ventas = venta_repository.listar_por_fecha(db, usuario_id, fecha)
    ganancia = venta_repository.ganancia_por_fecha(db, usuario_id, fecha)
    return ventas, ganancia


def ganancia_hoy(db: Session, usuario_id: str) -> float:
    return venta_repository.ganancia_por_fecha(db, usuario_id, _fecha_local_hoy())


def eliminar_venta(db: Session, usuario_id: str, venta_id: str):
    venta = venta_repository.obtener_por_id(db, usuario_id, venta_id)
    if not venta:
        raise NoEncontrado("Venta no encontrada")
    venta_repository.eliminar(db, venta)