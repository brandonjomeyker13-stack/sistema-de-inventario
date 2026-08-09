from sqlalchemy.orm import Session

from app.core.exceptions import NoEncontrado, ErrorNegocio
from app.core.fechas import hoy_local, ultimos_dias
from app.repositories import producto_repository, venta_repository


def vender(db: Session, usuario_id: str, nombre_producto: str, cantidad: int):
    producto = producto_repository.obtener_por_nombre(db, usuario_id, nombre_producto)
    if not producto:
        raise NoEncontrado("Ese producto no existe en el inventario")
    if producto.cantidad < cantidad:
        raise ErrorNegocio(f"No puedes vender más de lo que hay en stock (disponible: {producto.cantidad})")

    total = round(cantidad * producto.precio, 2)
    ganancia = round((producto.precio - producto.cuanto_costo) * cantidad, 2)

    return venta_repository.crear_venta_atomica(
        db, usuario_id, producto, cantidad, total, ganancia, hoy_local(),
    )


def ventas_por_fecha(db: Session, usuario_id: str, fecha: str):
    # La ganancia se suma aquí y no con un segundo SELECT: ya tenemos las
    # filas en memoria, y una ida menos a la base importa cuando la base
    # está en Supabase y el servicio en Render.
    ventas = venta_repository.listar_por_fecha(db, usuario_id, fecha)
    ganancia = round(sum(v.ganancia_total for v in ventas), 2)
    return ventas, ganancia


def ganancia_hoy(db: Session, usuario_id: str) -> float:
    return venta_repository.ganancia_por_fecha(db, usuario_id, hoy_local())


def resumen_ultimos_dias(db: Session, usuario_id: str, dias: int) -> dict:
    """Un total por día para las tarjetas del panel.

    Existe para matar un N+1: el frontend pedía /ventas?fecha=... catorce
    veces (y cada una hacía dos consultas), o sea 28 idas a la base para
    pintar una pantalla. Esto es una sola consulta con GROUP BY.

    Devuelve SIEMPRE `dias` elementos, del más reciente al más antiguo,
    rellenando en cero los días sin ventas — si faltaran, el frontend
    tendría que reconstruir el calendario por su cuenta y volveríamos a
    tener lógica de negocio en la interfaz.
    """
    fechas = ultimos_dias(dias)
    agregados = venta_repository.resumen_por_fechas(db, usuario_id, fechas)
    dia_vacio = {"total_vendido": 0.0, "ganancia_total": 0.0, "numero_ventas": 0}

    resumen = [{"fecha": fecha, **agregados.get(fecha, dia_vacio)} for fecha in fechas]

    return {
        "dias": resumen,
        "total_vendido": round(sum(d["total_vendido"] for d in resumen), 2),
        "ganancia_total": round(sum(d["ganancia_total"] for d in resumen), 2),
    }


def eliminar_venta(db: Session, usuario_id: str, venta_id: str):
    venta = venta_repository.obtener_por_id(db, usuario_id, venta_id)
    if not venta:
        raise NoEncontrado("Venta no encontrada")
    venta_repository.eliminar(db, venta)