"""
app/repositories/venta_repository.py — Acceso a datos de ventas.

`crear_venta_atomica` es el equivalente de `registrar_venta_atomica` que
ya tenías en el proyecto de escritorio: descuenta stock e inserta la
venta en la misma transacción de SQLAlchemy, con la misma defensa contra
condiciones de carrera (el UPDATE solo aplica si `cantidad >= lo vendido`
en ese instante).
"""

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.exceptions import ErrorNegocio
from app.models.venta import Venta
from app.models.venta_item import VentaItem
from app.models.producto import Producto


def crear_venta_atomica(
    db: Session, usuario_id: str, lineas: list[dict], fecha: str,
    cliente_id: str | None = None, es_fiado: bool = False,
    fecha_vencimiento: str | None = None,
) -> Venta:
    """Registra una venta de uno o varios productos, todo o nada.

    `lineas` es una lista de dicts con: producto, cantidad, total, ganancia.

    La defensa contra condiciones de carrera es la misma de siempre — el
    UPDATE solo aplica si en ESE instante hay stock suficiente — pero
    ahora se repite por cada producto. Si el último ítem de la canasta
    falla, se deshacen también los descuentos de los anteriores: por eso
    todo ocurre en una sola transacción y el commit está al final.
    """
    if not lineas:
        raise ErrorNegocio("La venta no tiene productos")

    for linea in lineas:
        producto = linea["producto"]
        cantidad = linea["cantidad"]
        filas_afectadas = (
            db.query(Producto)
            .filter(
                Producto.id == producto.id,
                Producto.cantidad >= cantidad,
                Producto.eliminado.is_(False),
            )
            .update({Producto.cantidad: Producto.cantidad - cantidad})
        )
        if filas_afectadas == 0:
            db.rollback()
            raise ErrorNegocio(
                f"El stock de '{producto.nombre}' cambió antes de completar la venta. Intenta de nuevo."
            )

    total_venta = round(sum(l["total"] for l in lineas), 2)
    ganancia_venta = round(sum(l["ganancia"] for l in lineas), 2)
    unidades = sum(l["cantidad"] for l in lineas)

    # Resumen en la cabecera para que el frontend actual siga leyendo lo
    # mismo que antes. Con un solo producto es idéntico a como era; con
    # varios, el nombre pasa a ser un recuento y el producto_id queda en
    # NULL porque ya no apunta a uno solo.
    if len(lineas) == 1:
        nombre_resumen = lineas[0]["producto"].nombre
        producto_id_resumen = lineas[0]["producto"].id
    else:
        nombre_resumen = f"{len(lineas)} productos"
        producto_id_resumen = None

    venta = Venta(
        usuario_id=usuario_id,
        producto_id=producto_id_resumen,
        nombre_producto=nombre_resumen,
        cantidad_vendida=unidades,
        precio_venta_total=total_venta,
        ganancia_total=ganancia_venta,
        fecha=fecha,
        cliente_id=cliente_id,
        es_fiado=es_fiado,
        fecha_vencimiento=fecha_vencimiento,
    )
    venta.items = [
        VentaItem(
            producto_id=l["producto"].id,
            nombre_producto=l["producto"].nombre,
            cantidad=l["cantidad"],
            precio_unitario=l["producto"].precio,
            precio_total=l["total"],
            ganancia_total=l["ganancia"],
        )
        for l in lineas
    ]

    db.add(venta)
    db.commit()
    db.refresh(venta)
    return venta


def listar_por_fecha(db: Session, usuario_id: str, fecha: str) -> list[Venta]:
    return (
        db.query(Venta)
        .filter(Venta.usuario_id == usuario_id, Venta.fecha == fecha, Venta.eliminado.is_(False))
        .order_by(Venta.creado_en.desc())
        .all()
    )


def ganancia_por_fecha(db: Session, usuario_id: str, fecha: str) -> float:
    resultado = (
        db.query(func.coalesce(func.sum(Venta.ganancia_total), 0))
        .filter(Venta.usuario_id == usuario_id, Venta.fecha == fecha, Venta.eliminado.is_(False))
        .scalar()
    )
    return float(resultado or 0)


def resumen_por_fechas(db: Session, usuario_id: str, fechas: list[str]) -> dict[str, dict]:
    """Totales agrupados por día, en una sola consulta.

    Devuelve un dict indexado por fecha con solo los días que tuvieron
    ventas; rellenar los vacíos es trabajo del servicio, que es quien
    sabe qué rango de días se pidió.
    """
    filas = (
        db.query(
            Venta.fecha,
            func.coalesce(func.sum(Venta.precio_venta_total), 0).label("total_vendido"),
            func.coalesce(func.sum(Venta.ganancia_total), 0).label("ganancia_total"),
            func.count(Venta.id).label("numero_ventas"),
        )
        .filter(
            Venta.usuario_id == usuario_id,
            Venta.eliminado.is_(False),
            Venta.fecha.in_(fechas),
        )
        .group_by(Venta.fecha)
        .all()
    )

    return {
        fila.fecha: {
            "total_vendido": round(float(fila.total_vendido), 2),
            "ganancia_total": round(float(fila.ganancia_total), 2),
            "numero_ventas": int(fila.numero_ventas),
        }
        for fila in filas
    }


def obtener_por_id(db: Session, usuario_id: str, venta_id: str) -> Venta | None:
    return (
        db.query(Venta)
        .filter(Venta.id == venta_id, Venta.usuario_id == usuario_id, Venta.eliminado.is_(False))
        .first()
    )


def eliminar(db: Session, venta: Venta) -> None:
    venta.eliminado = True
    db.commit()