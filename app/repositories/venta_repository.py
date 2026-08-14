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
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ErrorNegocio
from app.models.venta import Venta
from app.models.venta_item import VentaItem
from app.models.producto import Producto
from app.models.movimiento import (
    VENTA as MOVIMIENTO_VENTA,
    DEVOLUCION as MOVIMIENTO_DEVOLUCION,
)
from app.repositories import movimiento_repository


def obtener_por_clave(db: Session, usuario_id: str, clave: str) -> Venta | None:
    """La venta ya registrada con esa clave de idempotencia, si existe.

    Incluye las eliminadas a propósito: si el tendero anuló la venta y el
    celular reintenta la petición original que se había quedado sin
    respuesta, lo correcto es devolverle la venta anulada, no crear una
    nueva. Resucitar una venta que alguien decidió borrar sería peor que
    el problema que resuelve.
    """
    return (
        db.query(Venta)
        .filter(Venta.usuario_id == usuario_id, Venta.clave_idempotencia == clave)
        .first()
    )


def crear_venta_atomica(
    db: Session, usuario_id: str, lineas: list[dict], fecha: str,
    cliente_id: str | None = None, es_fiado: bool = False,
    fecha_vencimiento: str | None = None, clave_idempotencia: str | None = None,
) -> Venta:
    """Registra una venta de uno o varios productos, todo o nada.

    `lineas` es una lista de dicts con: producto, cantidad, total, ganancia.

    La defensa contra condiciones de carrera es la misma de siempre — el
    UPDATE solo aplica si en ESE instante hay stock suficiente — pero
    ahora se repite por cada producto. Si el último ítem de la canasta
    falla, se deshacen también los descuentos de los anteriores: por eso
    todo ocurre en una sola transacción y el commit está al final.

    `clave_idempotencia` hace que reintentar no duplique. Se apoya en el
    índice único (usuario_id, clave), no en una comprobación previa: dos
    reintentos que llegan a la vez pasarían los dos cualquier comprobación
    y los dos insertarían.
    """
    if not lineas:
        raise ErrorNegocio("La venta no tiene productos")

    # El stock de cada producto ANTES de tocar nada. Hay que leerlo aquí
    # y no después: el UPDATE de más abajo sincroniza la sesión, así que
    # producto.cantidad ya no valdría lo de antes cuando lo necesitemos
    # para el libro de movimientos.
    stock_previo = {l["producto"].id: l["producto"].cantidad for l in lineas}

    for linea in lineas:
        producto = linea["producto"]
        cantidad = linea["cantidad"]
        if not producto.controla_stock:
            # Servicio (una fotocopia, un plastificado): no hay existencias
            # que descontar. Tampoco hay carrera que vigilar — dos cajeros
            # vendiendo la misma fotocopia a la vez no se quitan nada.
            continue

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
        clave_idempotencia=clave_idempotencia,
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

    try:
        db.add(venta)
        # flush y no commit: necesitamos el id de la venta para enlazar los
        # movimientos, pero todo tiene que guardarse junto. Si esto fuera un
        # commit y el registro del libro fallara después, quedaría una venta
        # sin su movimiento y el inventario dejaría de ser auditable.
        #
        # OJO: el INSERT ocurre AQUÍ, no en el commit. Por eso el `try`
        # empieza antes del flush y no solo alrededor del commit — es
        # justo en este punto donde salta el choque de claves repetidas.
        db.flush()

        for linea in lineas:
            producto = linea["producto"]
            # Los servicios no van al libro de movimientos. El libro
            # existe para auditar existencias sumando: cada fila cumple
            # `stock_antes + cantidad == stock_despues`. Una fotocopia no
            # mueve existencias, así que su fila rompería esa igualdad o
            # sería una línea vacía que solo ensucia el historial. La
            # venta queda registrada en `ventas`, que es donde toca.
            if not producto.controla_stock:
                continue
            movimiento_repository.registrar(
                db, usuario_id, producto.id, MOVIMIENTO_VENTA, -linea["cantidad"],
                stock_previo[producto.id], fecha, venta_id=venta.id,
            )

        db.commit()
    except IntegrityError:
        # Otra petición con la MISMA clave ganó la carrera. Es el caso que
        # justifica toda esta columna: el celular reintentó porque no le
        # llegó la respuesta, no porque quisiera vender dos veces.
        #
        # El rollback deshace TODO lo de esta transacción, incluidos los
        # descuentos de stock de más arriba. Por eso el commit está al
        # final y hay uno solo: si el stock se hubiera confirmado antes, el
        # duplicado se habría evitado en la tabla de ventas pero el
        # inventario ya estaría descontado dos veces.
        db.rollback()
        if clave_idempotencia:
            existente = obtener_por_clave(db, usuario_id, clave_idempotencia)
            if existente:
                return existente
        # Sin clave, o si la venta no aparece, el choque es de otra cosa y
        # no hay que disimularlo.
        raise

    db.refresh(venta)
    return venta


def listar_por_rango(db: Session, usuario_id: str, desde: str, hasta: str) -> list[Venta]:
    """Ventas entre dos fechas, ambas incluidas.

    `fecha` es texto 'YYYY-MM-DD', un formato que ordena igual como texto
    que como fecha, así que la comparación funciona sin conversiones.
    """
    return (
        db.query(Venta)
        .filter(
            Venta.usuario_id == usuario_id,
            Venta.fecha >= desde,
            Venta.fecha <= hasta,
            Venta.eliminado.is_(False),
        )
        .order_by(Venta.fecha.desc(), Venta.creado_en.desc())
        .all()
    )


def listar_por_fecha(db: Session, usuario_id: str, fecha: str) -> list[Venta]:
    return listar_por_rango(db, usuario_id, fecha, fecha)


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
    """Anula una venta Y devuelve la mercancía al inventario.

    Antes esto solo marcaba `eliminado = True`. El stock NO volvía, y en el
    libro de movimientos no quedaba nada: el tendero escaneaba mal, borraba
    la venta, y el inventario se quedaba corto para siempre sin que
    ninguna pantalla lo delatara. Los números dejaban de cuadrar y no
    había forma de averiguar por qué.

    Todo en una sola transacción: si el libro fallara a mitad, quedaría
    stock devuelto sin rastro de por qué — que es exactamente el problema
    que se está arreglando.
    """
    lineas = _lineas_devueltas(venta)

    for producto_id, cantidad in lineas:
        producto = (
            db.query(Producto)
            .filter(Producto.id == producto_id, Producto.usuario_id == venta.usuario_id)
            .first()
        )
        if not producto:
            # El producto se borró después de venderse. No hay dónde
            # devolver el stock, pero la venta sí se anula: negarse a
            # anularla dejaría al tendero atrapado con una venta falsa que
            # no puede quitar.
            continue
        if not producto.controla_stock:
            # Un servicio no se devuelve al inventario: nunca salió de él.
            # Anular una venta de fotocopias quita la plata de las cuentas
            # y ya está.
            continue

        stock_antes = producto.cantidad
        producto.cantidad = stock_antes + cantidad
        movimiento_repository.registrar(
            db, venta.usuario_id, producto.id, MOVIMIENTO_DEVOLUCION, cantidad,
            stock_antes, venta.fecha, motivo="Venta anulada", venta_id=venta.id,
        )

    venta.eliminado = True
    db.commit()


def _lineas_devueltas(venta: Venta) -> list[tuple[str, int]]:
    """Qué productos y cuántas unidades hay que devolver.

    Normalmente salen de `venta.items`. El caso del `elif` es para las
    ventas anteriores a la migración 0003, cuando una venta era un solo
    producto y no había tabla de ítems: siguen en la base y también deben
    poder anularse.
    """
    if venta.items:
        return [(i.producto_id, i.cantidad) for i in venta.items if i.producto_id]
    if venta.producto_id:
        return [(venta.producto_id, venta.cantidad_vendida)]
    return []