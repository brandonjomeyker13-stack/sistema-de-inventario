"""
app/services/movimiento_service.py — Entradas, mermas y ajustes de stock.

Las tres operaciones que hasta ahora se hacían editando la cantidad del
producto a mano, ahora con causa y rastro.

Cada una toca el stock Y escribe el movimiento en la MISMA transacción.
Si se separaran, un fallo en medio dejaría el libro descuadrado — y un
libro de inventario en el que no se puede confiar es peor que no tenerlo,
porque induce a decisiones equivocadas.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core.fechas import hoy_local
from app.models.movimiento import ENTRADA, MERMA, AJUSTE
from app.repositories import producto_repository, movimiento_repository


def _producto(db: Session, usuario_id: str, producto_id: str):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    return producto


def _producto_con_stock(db: Session, usuario_id: str, producto_id: str):
    """Como _producto, pero rechaza los servicios.

    Entradas, mermas y ajustes son operaciones sobre EXISTENCIAS, y un
    servicio no las tiene: no llegan fotocopias del proveedor, no se dañan
    diez plastificados, y no se pueden contar los anillados que quedan en
    la estantería.

    Se rechaza con un mensaje explícito en vez de dejarlo pasar sin
    efecto. Si se ignorara en silencio, el tendero registraría la entrada,
    no vería cambiar nada, y volvería a intentarlo pensando que falló.
    """
    producto = _producto(db, usuario_id, producto_id)
    if not producto.controla_stock:
        raise ErrorNegocio(
            f"'{producto.nombre}' es un servicio y no lleva existencias, "
            "así que no se le pueden registrar entradas, mermas ni ajustes."
        )
    return producto


def registrar_entrada(db: Session, usuario_id: str, producto_id: str, cantidad: int,
                      costo_unitario: float | None = None, motivo: str | None = None):
    """Llegó mercancía. Suma al stock y deja constancia.

    Si viene `costo_unitario`, actualiza también el costo del producto:
    es lo que acabas de pagar, y dejar el costo viejo haría que todas las
    ganancias siguientes se calcularan mal. El costo anterior no se
    pierde — queda en los movimientos anteriores.
    """
    if cantidad <= 0:
        raise ErrorNegocio("La cantidad de una entrada debe ser mayor que cero")

    producto = _producto_con_stock(db, usuario_id, producto_id)
    stock_antes = producto.cantidad

    producto.cantidad = stock_antes + cantidad
    if costo_unitario is not None:
        if costo_unitario < 0:
            raise ErrorNegocio("El costo no puede ser negativo")
        producto.cuanto_costo = costo_unitario

    movimiento = movimiento_repository.registrar(
        db, usuario_id, producto_id, ENTRADA, cantidad, stock_antes,
        hoy_local(), motivo, costo_unitario,
    )
    db.commit()
    db.refresh(movimiento)
    return movimiento


def registrar_merma(db: Session, usuario_id: str, producto_id: str, cantidad: int,
                    motivo: str | None = None):
    """Se dañó, venció o se rompió. Resta del stock.

    Se exige que haya existencias suficientes: una merma mayor que el
    stock dejaría el inventario en negativo, y eso no es un dato, es un
    error de captura que hay que devolver.
    """
    if cantidad <= 0:
        raise ErrorNegocio("La cantidad de una merma debe ser mayor que cero")

    producto = _producto_con_stock(db, usuario_id, producto_id)
    stock_antes = producto.cantidad
    if cantidad > stock_antes:
        raise ErrorNegocio(
            f"No puedes dar de baja {cantidad} unidades de '{producto.nombre}': "
            f"solo hay {stock_antes}"
        )

    producto.cantidad = stock_antes - cantidad
    movimiento = movimiento_repository.registrar(
        db, usuario_id, producto_id, MERMA, -cantidad, stock_antes, hoy_local(), motivo,
    )
    db.commit()
    db.refresh(movimiento)
    return movimiento


def ajustar(db: Session, usuario_id: str, producto_id: str, stock_real: int,
            motivo: str | None = None):
    """Conteo físico: el stock real no coincide con el del sistema.

    Recibe el stock REAL contado, no la diferencia. Es la forma en que
    piensa quien está contando ("hay 37"), y calcular la diferencia de
    cabeza es justo donde se equivoca la gente.
    """
    if stock_real < 0:
        raise ErrorNegocio("El stock contado no puede ser negativo")

    producto = _producto_con_stock(db, usuario_id, producto_id)
    stock_antes = producto.cantidad
    diferencia = stock_real - stock_antes
    if diferencia == 0:
        raise ErrorNegocio(
            f"El stock de '{producto.nombre}' ya es {stock_real}: no hay nada que ajustar"
        )

    producto.cantidad = stock_real
    movimiento = movimiento_repository.registrar(
        db, usuario_id, producto_id, AJUSTE, diferencia, stock_antes, hoy_local(), motivo,
    )
    db.commit()
    db.refresh(movimiento)
    return movimiento


def historial(db: Session, usuario_id: str, producto_id: str | None = None,
              tipo: str | None = None, desde: str | None = None, hasta: str | None = None,
              limite: int = 100, offset: int = 0):
    if producto_id:
        # Valida de paso que el producto sea de este negocio: sin esto,
        # mandar un producto_id ajeno devolvería una lista vacía en vez
        # de un error, y parecería que ese producto no tiene movimientos.
        _producto(db, usuario_id, producto_id)
    return movimiento_repository.listar(
        db, usuario_id, producto_id, tipo, desde, hasta, limite, offset
    )


def contar_historial(db: Session, usuario_id: str, producto_id: str | None = None,
                     tipo: str | None = None, desde: str | None = None,
                     hasta: str | None = None) -> int:
    return movimiento_repository.contar(db, usuario_id, producto_id, tipo, desde, hasta)
