"""
app/repositories/analitica_repository.py — Consultas agregadas de ventas.

Solo consulta y agrupa: no decide qué significa un número ni qué es
"poco" o "mucho". Eso es del servicio. Aquí solo vive el SQL.

Todas las agregaciones parten de `venta_items`, no de `ventas`. La
cabecera tiene el total de la venta, pero el análisis necesita el detalle
por producto — y desde que existen las ventas multi-producto, el
`nombre_producto` de la cabecera puede ser "3 productos".

Como `venta_items` no lleva usuario_id, todas las consultas hacen JOIN
con `ventas` para filtrar por negocio. Es la misma barrera multi-tenant
de siempre: sin ese JOIN, un negocio vería las ventas de otro.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.producto import Producto
from app.models.venta import Venta
from app.models.venta_item import VentaItem


def ventas_por_producto(db: Session, usuario_id: str, desde: str, hasta: str) -> list[dict]:
    """Unidades, ingresos y ganancia por producto en un rango de fechas.

    Se agrupa también por nombre porque `producto_id` puede ser NULL
    (el producto se borró después de la venta) y esas líneas no deben
    fundirse todas en un mismo grupo sin nombre.
    """
    filas = (
        db.query(
            VentaItem.producto_id.label("producto_id"),
            VentaItem.nombre_producto.label("nombre"),
            func.coalesce(func.sum(VentaItem.cantidad), 0).label("unidades"),
            func.coalesce(func.sum(VentaItem.precio_total), 0).label("ingresos"),
            func.coalesce(func.sum(VentaItem.ganancia_total), 0).label("ganancia"),
            func.count(func.distinct(VentaItem.venta_id)).label("veces"),
        )
        .join(Venta, Venta.id == VentaItem.venta_id)
        .filter(
            Venta.usuario_id == usuario_id,
            Venta.eliminado.is_(False),
            Venta.fecha >= desde,
            Venta.fecha <= hasta,
        )
        .group_by(VentaItem.producto_id, VentaItem.nombre_producto)
        .all()
    )

    return [
        {
            "producto_id": f.producto_id,
            "nombre": f.nombre,
            "unidades": int(f.unidades),
            "ingresos": round(float(f.ingresos), 2),
            "ganancia": round(float(f.ganancia), 2),
            # En cuántas ventas distintas apareció. Un producto que sale en
            # muchas ventas es un producto de tráfico, aunque venda pocas
            # unidades; no es lo mismo que uno que se llevó alguien de golpe.
            "veces": int(f.veces),
        }
        for f in filas
    ]


def inventario_con_ultima_venta(db: Session, usuario_id: str) -> list[dict]:
    """Cada producto vivo con la fecha de su última venta (o None).

    LEFT JOIN a propósito: los productos que NUNCA se han vendido son
    justamente los que más interesan, y un INNER JOIN los dejaría fuera.
    """
    filas = (
        db.query(
            Producto.id.label("id"),
            Producto.nombre.label("nombre"),
            Producto.cantidad.label("stock"),
            Producto.precio.label("precio"),
            Producto.cuanto_costo.label("costo"),
            Producto.controla_stock.label("controla_stock"),
            Producto.stock_minimo.label("stock_minimo"),
            Producto.creado_en.label("creado_en"),
            func.max(Venta.fecha).label("ultima_venta"),
        )
        .outerjoin(VentaItem, VentaItem.producto_id == Producto.id)
        .outerjoin(
            Venta,
            (Venta.id == VentaItem.venta_id) & (Venta.eliminado.is_(False)),
        )
        .filter(Producto.usuario_id == usuario_id, Producto.eliminado.is_(False))
        .group_by(
            Producto.id, Producto.nombre, Producto.cantidad,
            Producto.precio, Producto.cuanto_costo, Producto.controla_stock,
            Producto.stock_minimo, Producto.creado_en,
        )
        .all()
    )

    return [
        {
            "id": f.id,
            "nombre": f.nombre,
            "stock": int(f.stock),
            "precio": float(f.precio),
            "costo": float(f.costo),
            # Los servicios se devuelven igual, y es el servicio quien los
            # descarta. Filtrarlos aquí dejaría este método sirviendo solo
            # para una de las dos vistas que lo usan.
            "controla_stock": bool(f.controla_stock),
            # None significa "usa el umbral por defecto del negocio". Lo
            # resuelve el servicio, que es quien conoce al usuario.
            "stock_minimo": f.stock_minimo,
            "creado_en": f.creado_en,
            "ultima_venta": f.ultima_venta,
        }
        for f in filas
    ]


def totales_por_fecha(db: Session, usuario_id: str, desde: str, hasta: str) -> list[dict]:
    """Total vendido y ganancia por día, en un rango.

    Se devuelve por fecha y no agrupado por día de la semana a propósito:
    hacer eso en SQL obliga a funciones de fecha distintas en Postgres y
    SQLite. El servicio lo agrupa en Python y funciona igual en los dos.
    """
    filas = (
        db.query(
            Venta.fecha.label("fecha"),
            func.coalesce(func.sum(Venta.precio_venta_total), 0).label("vendido"),
            func.coalesce(func.sum(Venta.ganancia_total), 0).label("ganancia"),
            func.count(Venta.id).label("ventas"),
        )
        .filter(
            Venta.usuario_id == usuario_id,
            Venta.eliminado.is_(False),
            Venta.fecha >= desde,
            Venta.fecha <= hasta,
        )
        .group_by(Venta.fecha)
        .all()
    )

    return [
        {
            "fecha": f.fecha,
            "vendido": round(float(f.vendido), 2),
            "ganancia": round(float(f.ganancia), 2),
            "ventas": int(f.ventas),
        }
        for f in filas
    ]
