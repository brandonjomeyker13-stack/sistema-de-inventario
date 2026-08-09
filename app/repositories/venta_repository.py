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
from app.models.producto import Producto


def crear_venta_atomica(
    db: Session, usuario_id: str, producto: Producto, cantidad_vendida: int,
    total: float, ganancia: float, fecha: str,
) -> Venta:
    filas_afectadas = (
        db.query(Producto)
        .filter(Producto.id == producto.id, Producto.cantidad >= cantidad_vendida, Producto.eliminado.is_(False))
        .update({Producto.cantidad: Producto.cantidad - cantidad_vendida})
    )
    if filas_afectadas == 0:
        db.rollback()
        raise ErrorNegocio("El stock cambió antes de completar la venta. Intenta de nuevo.")

    venta = Venta(
        usuario_id=usuario_id, producto_id=producto.id, nombre_producto=producto.nombre,
        cantidad_vendida=cantidad_vendida, precio_venta_total=total, ganancia_total=ganancia, fecha=fecha,
    )
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