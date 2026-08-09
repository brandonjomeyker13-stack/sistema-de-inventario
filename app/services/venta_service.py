from sqlalchemy.orm import Session

from app.core.exceptions import NoEncontrado, ErrorNegocio
from app.core.fechas import hoy_local, ultimos_dias, sumar_dias
from app.repositories import producto_repository, venta_repository, cliente_repository


def _resolver_producto(db: Session, usuario_id: str, nombre: str | None,
                       codigo_barras: str | None, producto_id: str | None = None):
    """Encuentra el producto por id, por código de barras o por nombre.

    En ese orden de preferencia: el id es exacto, el código también, y el
    nombre depende de cómo lo escribió el tendero.
    """
    if producto_id:
        producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
        if not producto:
            raise NoEncontrado("Producto no encontrado")
        return producto

    if codigo_barras:
        producto = producto_repository.obtener_por_codigo_barras(db, usuario_id, codigo_barras)
        if not producto:
            raise NoEncontrado(f"No hay ningún producto con el código {codigo_barras}")
        return producto

    producto = producto_repository.obtener_por_nombre(db, usuario_id, nombre or "")
    if not producto:
        raise NoEncontrado("Ese producto no existe en el inventario")
    return producto


def vender(
    db: Session, usuario_id: str, items: list[dict],
    cliente_id: str | None = None, es_fiado: bool = False,
    dias_plazo: int | None = None, fecha_vencimiento: str | None = None,
):
    """Registra una venta de uno o varios productos.

    `items` es una lista de dicts con nombre_producto y/o codigo_barras,
    más cantidad.

    Si `es_fiado`, la mercancía sale igual (el stock baja) pero queda una
    deuda a nombre del cliente.
    """
    if not items:
        raise ErrorNegocio("La venta no tiene productos")

    if es_fiado and not cliente_id:
        # Una deuda sin deudor es una pérdida disfrazada de venta.
        raise ErrorNegocio("Para fiar hay que decir a quién: falta el cliente")

    cliente = None
    if cliente_id:
        # Valida de paso que el cliente sea de ESTE negocio.
        cliente = cliente_repository.obtener_por_id(db, usuario_id, cliente_id)
        if not cliente:
            raise NoEncontrado("Cliente no encontrado")

    # Plazo: manda la fecha explícita; si no, los días de esta venta; si
    # tampoco, el plazo habitual del cliente. Si no hay nada, el fiado
    # queda sin vencimiento ("cuando puedas") y nunca aparece como
    # atrasado — que es lo correcto: no se incumple un plazo inexistente.
    vencimiento = None
    if es_fiado:
        if fecha_vencimiento:
            vencimiento = fecha_vencimiento
        else:
            plazo = dias_plazo if dias_plazo is not None else (cliente.dias_plazo if cliente else None)
            if plazo is not None:
                vencimiento = sumar_dias(plazo)

    # Agrupar por producto antes de validar el stock. Si no se hiciera, el
    # mismo producto escaneado dos veces se validaría dos veces por
    # separado contra el stock completo: con 5 unidades disponibles, dos
    # líneas de 3 pasarían el control individualmente y dejarían el
    # inventario en negativo.
    acumulado: dict[str, dict] = {}
    for item in items:
        producto = _resolver_producto(
            db, usuario_id, item.get("nombre_producto"), item.get("codigo_barras"),
            item.get("producto_id"),
        )
        cantidad = item["cantidad"]
        if producto.id in acumulado:
            acumulado[producto.id]["cantidad"] += cantidad
        else:
            acumulado[producto.id] = {"producto": producto, "cantidad": cantidad}

    lineas = []
    for entrada in acumulado.values():
        producto, cantidad = entrada["producto"], entrada["cantidad"]
        if producto.cantidad < cantidad:
            raise ErrorNegocio(
                f"No puedes vender más '{producto.nombre}' de lo que hay en stock "
                f"(pides {cantidad}, disponible: {producto.cantidad})"
            )
        lineas.append({
            "producto": producto,
            "cantidad": cantidad,
            "total": round(cantidad * producto.precio, 2),
            "ganancia": round((producto.precio - producto.cuanto_costo) * cantidad, 2),
        })

    return venta_repository.crear_venta_atomica(
        db, usuario_id, lineas, hoy_local(), cliente_id=cliente_id, es_fiado=es_fiado,
        fecha_vencimiento=vencimiento,
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
    fiado_por_dia = cliente_repository.total_fiado_por_fechas(db, usuario_id, fechas)
    dia_vacio = {"total_vendido": 0.0, "ganancia_total": 0.0, "numero_ventas": 0}

    resumen = [
        {
            "fecha": fecha,
            **agregados.get(fecha, dia_vacio),
            # Cuánto de lo vendido ese día se fió. Es plata que aún no
            # está en el cajón, y el tendero necesita verla separada.
            "total_fiado": fiado_por_dia.get(fecha, 0.0),
        }
        for fecha in fechas
    ]

    return {
        "dias": resumen,
        "total_vendido": round(sum(d["total_vendido"] for d in resumen), 2),
        "ganancia_total": round(sum(d["ganancia_total"] for d in resumen), 2),
        "total_fiado": round(sum(d["total_fiado"] for d in resumen), 2),
    }


def eliminar_venta(db: Session, usuario_id: str, venta_id: str):
    venta = venta_repository.obtener_por_id(db, usuario_id, venta_id)
    if not venta:
        raise NoEncontrado("Venta no encontrada")
    venta_repository.eliminar(db, venta)