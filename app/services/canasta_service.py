"""
app/services/canasta_service.py — La venta en curso compartida.

Aquí vive el control de acceso de la canasta, que es la parte con riesgo.
Hay dos formas de tocar una canasta:

  - Con la sesión del tendero (JWT): puede todo, incluido cobrar.
  - Con el token del celular: SOLO puede leer y agregar productos a esa
    canasta concreta. No puede cobrar, no puede ver otras canastas, no
    puede tocar el inventario.

Esa asimetría es deliberada. El token viaja en un QR mostrado en la
pantalla del PC; cualquiera que pase por delante puede fotografiarlo. Con
él, lo peor que puede hacer un curioso es meterle productos a una venta
que el tendero está viendo en pantalla en ese momento — y que va a
revisar antes de cobrar.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.repositories import canasta_repository, producto_repository
from app.services import venta_service


def _canasta_vigente(db: Session, canasta_id: str):
    canasta = canasta_repository.obtener_por_id(db, canasta_id)
    if not canasta:
        raise NoEncontrado("Canasta no encontrada")
    if not canasta_repository.esta_vigente(canasta):
        raise ErrorNegocio("Esta venta ya se cerró o caducó. Abre una nueva.")
    return canasta


def _autorizar(db: Session, canasta_id: str, usuario_id: str | None, token: str | None,
               exige_dueno: bool = False):
    """Devuelve la canasta si quien pide tiene derecho a tocarla."""
    canasta = _canasta_vigente(db, canasta_id)

    if usuario_id and canasta.usuario_id == usuario_id:
        return canasta

    if exige_dueno:
        # Cobrar, descartar: solo el tendero con su sesión.
        raise NoEncontrado("Canasta no encontrada")

    # El token debe corresponder a ESTA canasta. Se compara con
    # secrets.compare_digest para no filtrar información por el tiempo
    # que tarda la comparación.
    if token and canasta.token_celular and _iguales(token, canasta.token_celular):
        return canasta

    raise NoEncontrado("Canasta no encontrada")


def _iguales(a: str, b: str) -> bool:
    import secrets
    return secrets.compare_digest(a, b)


def _pintar(db: Session, canasta) -> dict:
    """Arma la vista de la canasta con nombres, precios y totales.

    Los precios se leen del producto en este momento, no de una copia:
    mientras la venta está en curso interesa el precio de ahora. La foto
    se toma al cobrar, en `venta_items`.
    """
    lineas = []
    total = 0.0
    for item in canasta.items:
        producto = producto_repository.obtener_por_id(db, canasta.usuario_id, item.producto_id)
        if not producto:
            # El producto se borró con la canasta abierta. Se omite en vez
            # de romper la pantalla; al cobrar fallaría con un mensaje claro.
            continue
        subtotal = round(producto.precio * item.cantidad, 2)
        total += subtotal
        lineas.append({
            "id": item.id,
            "producto_id": producto.id,
            "nombre": producto.nombre,
            "cantidad": item.cantidad,
            "precio_unitario": producto.precio,
            "subtotal": subtotal,
            # Para que el PC pueda avisar en rojo antes de intentar cobrar.
            "stock_disponible": producto.cantidad,
            "hay_stock": producto.cantidad >= item.cantidad,
        })

    return {
        "id": canasta.id,
        "estado": canasta.estado,
        "items": lineas,
        "total": round(total, 2),
        "unidades": sum(l["cantidad"] for l in lineas),
        "expira_en": canasta.expira_en,
    }


def abrir(db: Session, usuario_id: str) -> dict:
    """Abre la venta en curso, o devuelve la que ya estaba abierta.

    No crea una nueva si ya hay una viva. El frontend llama a esto cada
    vez que se entra a la pantalla de ventas, y crear un carrito por
    visita dejaría huérfanos por todas partes — y peor, perdería la venta
    a medias que el tendero tenía en pantalla si recarga sin querer.

    Para empezar de cero está DELETE /canastas/{id}.
    """
    canasta = canasta_repository.obtener_abierta(db, usuario_id)
    if not canasta:
        canasta = canasta_repository.crear(db, usuario_id)

    vista = _pintar(db, canasta)
    # El token solo viaja aquí: es lo que el PC mete dentro del QR.
    vista["token_celular"] = canasta.token_celular
    return vista


def ver(db: Session, canasta_id: str, usuario_id: str | None, token: str | None) -> dict:
    canasta = _autorizar(db, canasta_id, usuario_id, token)
    return _pintar(db, canasta)


def agregar(db: Session, canasta_id: str, usuario_id: str | None, token: str | None,
            codigo_barras: str | None, nombre_producto: str | None,
            producto_id: str | None, cantidad: int) -> dict:
    canasta = _autorizar(db, canasta_id, usuario_id, token)

    # Se resuelve siempre contra el usuario DUEÑO de la canasta, nunca
    # contra quien manda la petición: el celular no tiene identidad
    # propia, opera dentro del negocio de esta canasta.
    if producto_id:
        producto = producto_repository.obtener_por_id(db, canasta.usuario_id, producto_id)
        if not producto:
            raise NoEncontrado("Producto no encontrado")
    elif codigo_barras:
        producto = producto_repository.obtener_por_codigo_barras(
            db, canasta.usuario_id, codigo_barras
        )
        if not producto:
            raise NoEncontrado(f"No hay ningún producto con el código {codigo_barras}")
    elif nombre_producto:
        producto = producto_repository.obtener_por_nombre(db, canasta.usuario_id, nombre_producto)
        if not producto:
            raise NoEncontrado("Ese producto no existe en el inventario")
    else:
        raise ErrorNegocio("Falta identificar el producto: código, nombre o id")

    canasta_repository.agregar_o_sumar(db, canasta, producto.id, cantidad)
    db.refresh(canasta)
    return _pintar(db, canasta)


def cambiar_cantidad(db: Session, canasta_id: str, usuario_id: str, item_id: str,
                     cantidad: int) -> dict:
    canasta = _autorizar(db, canasta_id, usuario_id, None, exige_dueno=True)
    item = canasta_repository.obtener_item(db, canasta.id, item_id)
    if not item:
        raise NoEncontrado("Ese producto no está en la canasta")
    canasta_repository.cambiar_cantidad(db, canasta, item, cantidad)
    db.refresh(canasta)
    return _pintar(db, canasta)


def quitar(db: Session, canasta_id: str, usuario_id: str, item_id: str) -> dict:
    canasta = _autorizar(db, canasta_id, usuario_id, None, exige_dueno=True)
    item = canasta_repository.obtener_item(db, canasta.id, item_id)
    if not item:
        raise NoEncontrado("Ese producto no está en la canasta")
    canasta_repository.quitar_item(db, canasta, item)
    db.refresh(canasta)
    return _pintar(db, canasta)


def descartar(db: Session, canasta_id: str, usuario_id: str) -> None:
    canasta = _autorizar(db, canasta_id, usuario_id, None, exige_dueno=True)
    canasta_repository.descartar(db, canasta)


def cobrar(db: Session, canasta_id: str, usuario_id: str, cliente_id: str | None = None,
           es_fiado: bool = False, dias_plazo: int | None = None,
           fecha_vencimiento: str | None = None):
    """Convierte la canasta en venta real.

    No duplica nada: delega en venta_service.vender, que ya sabe descontar
    el stock de varios productos en una sola transacción y validar el
    fiado. La canasta solo aporta la lista.
    """
    canasta = _autorizar(db, canasta_id, usuario_id, None, exige_dueno=True)
    if not canasta.items:
        raise ErrorNegocio("La canasta está vacía")

    items = [{"producto_id": i.producto_id, "cantidad": i.cantidad} for i in canasta.items]

    venta = venta_service.vender(
        db, usuario_id, items, cliente_id=cliente_id, es_fiado=es_fiado,
        dias_plazo=dias_plazo, fecha_vencimiento=fecha_vencimiento,
    )
    canasta_repository.marcar_cobrada(db, canasta, venta.id)
    return venta
