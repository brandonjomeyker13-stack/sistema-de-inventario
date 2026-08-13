"""
app/services/canasta_service.py — La venta en curso compartida.

Aquí vive el control de acceso de la canasta, que es la parte con riesgo.
Hay dos formas de tocar una canasta:

  - Con la sesión del tendero (JWT): puede todo, incluido cobrar.
  - Con el token del celular: puede LEER y EDITAR los productos de esa
    canasta concreta (agregar, cambiar cantidad, quitar). No puede
    cobrar, no puede descartarla, no puede ver otras canastas, no puede
    tocar el inventario.

La línea está puesta donde importa: el token nunca mueve dinero ni stock.
Editar la lista de una venta que el tendero tiene delante en pantalla es
otra cosa — la ve, la revisa y la lee en voz alta antes de cobrar.

El riesgo residual, para que quede escrito: quien fotografíe el QR puede
manipular esa venta en curso hasta que se cobre o caduque. No puede robar
mercancía ni datos, pero sí puede hacer que la cuenta salga mal si el
tendero cobra sin mirar. Si algún día molesta, la respuesta no es quitar
el borrado (poner la cantidad en 0 equivale a borrar) sino acortar la
vida del token o regenerarlo tras cada cobro.
"""

from sqlalchemy.orm import Session

from app.core.codigos import normalizar, checksum_valido
from app.core.exceptions import ErrorNegocio, NoEncontrado, CredencialesInvalidas
from app.models.canasta import PROPOSITO_VENTA, PROPOSITO_INVENTARIO, PROPOSITOS
from app.repositories import canasta_repository, producto_repository
from app.services import venta_service, movimiento_service


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

    if token:
        # compare_digest para no filtrar información por el tiempo que
        # tarda la comparación.
        if canasta.token_celular and _iguales(token, canasta.token_celular):
            return canasta
        raise NoEncontrado("Canasta no encontrada")

    if usuario_id:
        # Hay sesión, pero de otro negocio. No le falta credencial: le
        # falta permiso. Un 404 no le confirma que esta canasta exista.
        raise NoEncontrado("Canasta no encontrada")

    # No llegó NADA: ni sesión ni token. Se distingue del caso anterior a
    # propósito. No revela nada de la canasta (es un error del cliente,
    # no una pista), y sin este mensaje depurar por qué el celular no
    # entra es adivinar: un proxy que se come la cabecera personalizada
    # se ve exactamente igual que un token equivocado.
    raise CredencialesInvalidas(
        "No llegó el token de emparejamiento. La página del escáner debe mandarlo "
        "en la cabecera X-Canasta-Token o en el campo 'token' del cuerpo."
    )


def _iguales(a: str, b: str) -> bool:
    import secrets
    return secrets.compare_digest(a, b)


def _resolver_todos(db: Session, canasta) -> dict[str, object]:
    """Los productos de TODAS las líneas, en dos consultas como mucho.

    Antes se resolvía línea por línea. El PC sondea esta vista cada
    segundo y medio mientras hay una venta en curso, así que una canasta
    de diez productos generaba once consultas por sondeo — unas
    cuatrocientas por minuto contra Supabase, y con NullPool cada una abre
    su propia conexión.

    Un código que se escaneó cuando no existía puede existir ya: el
    tendero lo dio de alta desde el PC mientras el celular seguía
    escaneando. Se resuelve al leer, sin escribir nada — un GET que
    modifica datos es una fuente de sorpresas.
    """
    ids = [i.producto_id for i in canasta.items if i.producto_id]
    codigos = [i.codigo_pendiente for i in canasta.items
               if not i.producto_id and i.codigo_pendiente]

    por_id = producto_repository.mapa_por_id(db, canasta.usuario_id, ids)
    por_codigo = producto_repository.mapa_por_codigo_barras(db, canasta.usuario_id, codigos)

    resueltos: dict[str, object] = {}
    for item in canasta.items:
        if item.producto_id:
            producto = por_id.get(item.producto_id)
        elif item.codigo_pendiente:
            # El mapa está indexado por el código normalizado, que es como
            # se guarda; el pendiente puede haberse escrito en otra forma.
            producto = por_codigo.get(normalizar(item.codigo_pendiente))
        else:
            producto = None
        resueltos[item.id] = producto
    return resueltos


def _pintar(db: Session, canasta) -> dict:
    """Arma la vista de la canasta con nombres, precios y totales.

    Los precios se leen del producto en este momento, no de una copia:
    mientras la venta está en curso interesa el precio de ahora. La foto
    se toma al cobrar, en `venta_items`.
    """
    lineas = []
    total = 0.0
    pendientes = 0
    productos = _resolver_todos(db, canasta)

    for item in canasta.items:
        producto = productos.get(item.id)

        if not producto:
            if item.codigo_pendiente:
                # Código escaneado que aún no es ningún producto. En una
                # canasta de inventario es lo normal: el PC lo usa para
                # abrir el formulario de alta con el código ya puesto.
                pendientes += 1
                lineas.append({
                    "id": item.id,
                    "producto_id": None,
                    "codigo_pendiente": item.codigo_pendiente,
                    "nombre": None,
                    "cantidad": item.cantidad,
                    "precio_unitario": 0.0,
                    "subtotal": 0.0,
                    "stock_disponible": 0,
                    "hay_stock": False,
                    "existe": False,
                    # None = el formato no lleva dígito de control (Code
                    # 128, QR propio). False = la lectura casi seguro está
                    # mal, avisar antes de crear un producto fantasma.
                    "checksum_ok": checksum_valido(item.codigo_pendiente),
                })
            # Si no hay código ni producto, la fila quedó huérfana (el
            # producto se borró con la canasta abierta): se omite en vez
            # de romper la pantalla.
            continue

        subtotal = round(producto.precio * item.cantidad, 2)
        total += subtotal
        lineas.append({
            "id": item.id,
            "producto_id": producto.id,
            "codigo_pendiente": None,
            "nombre": producto.nombre,
            "cantidad": item.cantidad,
            "precio_unitario": producto.precio,
            "subtotal": subtotal,
            # Para que el PC pueda avisar en rojo antes de intentar cobrar.
            "stock_disponible": producto.cantidad,
            "hay_stock": producto.cantidad >= item.cantidad,
            "existe": True,
            "checksum_ok": None,
        })

    return {
        "id": canasta.id,
        "estado": canasta.estado,
        "proposito": canasta.proposito,
        "items": lineas,
        "total": round(total, 2),
        "unidades": sum(l["cantidad"] for l in lineas),
        # Cuántas líneas siguen sin producto. En inventario, mientras sea
        # mayor que cero no se puede recibir la mercancía.
        "pendientes": pendientes,
        "expira_en": canasta.expira_en,
    }


def abrir(db: Session, usuario_id: str, proposito: str = PROPOSITO_VENTA) -> dict:
    """Abre la canasta en curso, o devuelve la que ya estaba abierta.

    No crea una nueva si ya hay una viva del mismo propósito. El frontend
    llama a esto cada vez que se entra a la pantalla, y crear un carrito
    por visita dejaría huérfanos por todas partes — y peor, perdería el
    trabajo a medias si el tendero recarga sin querer.

    Una venta en curso y una recepción de mercancía en curso conviven sin
    pisarse: son propósitos distintos.

    Para empezar de cero está DELETE /canastas/{id}.
    """
    if proposito not in PROPOSITOS:
        raise ErrorNegocio(f"Propósito no válido. Debe ser uno de: {', '.join(PROPOSITOS)}")

    canasta = canasta_repository.obtener_abierta(db, usuario_id, proposito)
    if not canasta:
        canasta = canasta_repository.crear(db, usuario_id, proposito)

    vista = _pintar(db, canasta)
    # El token solo viaja aquí: es lo que el PC mete dentro del QR.
    vista["token_celular"] = canasta.token_celular
    return vista


def listar_abiertas(db: Session, usuario_id: str) -> list[dict]:
    """Canastas a medias que siguen vivas, de cualquier propósito.

    Existe para que cerrar el navegador no pierda el trabajo. El frontend
    puede avisar "tienes una venta sin cobrar" al entrar, en vez de
    dejarla huérfana hasta que caduque.

    No devuelve el token: eso solo sale de POST /canastas, que además
    reutiliza la que ya estuviera abierta. Así el token se entrega a quien
    retoma el trabajo de forma explícita, no a cualquiera que liste.
    """
    return [_pintar(db, c) for c in canasta_repository.listar_abiertas(db, usuario_id)]


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
            if canasta.proposito == PROPOSITO_INVENTARIO:
                # Aquí un código desconocido NO es un error: es justo lo
                # que se viene a dar de alta. Se guarda como pendiente y
                # el PC abre el formulario con el código ya puesto.
                canasta_repository.agregar_codigo_pendiente(
                    db, canasta, normalizar(codigo_barras), cantidad
                )
                db.refresh(canasta)
                return _pintar(db, canasta)
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


def cambiar_cantidad(db: Session, canasta_id: str, usuario_id: str | None, token: str | None,
                     item_id: str, cantidad: int) -> dict:
    """Corregir cantidades también desde el celular.

    Quien escanea de más tiene que poder corregirlo ahí mismo. Obligar a
    caminar hasta el PC para arreglar un escaneo doble haría que nadie
    use el celular como lector.
    """
    canasta = _autorizar(db, canasta_id, usuario_id, token)
    item = canasta_repository.obtener_item(db, canasta.id, item_id)
    if not item:
        raise NoEncontrado("Ese producto no está en la canasta")
    canasta_repository.cambiar_cantidad(db, canasta, item, cantidad)
    db.refresh(canasta)
    return _pintar(db, canasta)


def quitar(db: Session, canasta_id: str, usuario_id: str | None, token: str | None,
           item_id: str) -> dict:
    """Quitar una línea, también desde el celular.

    Va junto con cambiar_cantidad: poner la cantidad en 0 ya equivale a
    quitar la línea, así que permitir una y no la otra no protegería de
    nada y solo complicaría el frontend.
    """
    canasta = _autorizar(db, canasta_id, usuario_id, token)
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
    if canasta.proposito != PROPOSITO_VENTA:
        # Guarda explícita: una recepción de mercancía nunca puede
        # cobrarse como si fuera una venta.
        raise ErrorNegocio("Esta canasta es de inventario, no de venta")
    if not canasta.items:
        raise ErrorNegocio("La canasta está vacía")

    items = [{"producto_id": i.producto_id, "cantidad": i.cantidad} for i in canasta.items]

    venta = venta_service.vender(
        db, usuario_id, items, cliente_id=cliente_id, es_fiado=es_fiado,
        dias_plazo=dias_plazo, fecha_vencimiento=fecha_vencimiento,
    )
    canasta_repository.marcar_cobrada(db, canasta, venta.id)
    return venta


def recibir(db: Session, canasta_id: str, usuario_id: str,
            costos: dict[str, float] | None = None, motivo: str | None = None) -> dict:
    """Convierte una canasta de inventario en entradas de stock.

    El equivalente de `cobrar`, pero al revés: en vez de sacar mercancía
    y cobrarla, la mete y la registra en el libro de movimientos.

    Se exige que NO queden códigos pendientes. Recibir mercancía a medias
    dejaría cajas escaneadas que no entraron a ningún inventario, y nadie
    se enteraría hasta el siguiente conteo físico. Es mejor devolver la
    lista de lo que falta identificar.

    `costos` permite decir a cuánto se compró cada producto esta vez: es
    justo el momento en que se conoce ese dato.
    """
    canasta = _autorizar(db, canasta_id, usuario_id, None, exige_dueno=True)
    if canasta.proposito != PROPOSITO_INVENTARIO:
        raise ErrorNegocio("Esta canasta es de venta, no de inventario")
    if not canasta.items:
        raise ErrorNegocio("La canasta está vacía")

    vista = _pintar(db, canasta)
    if vista["pendientes"]:
        sin_identificar = [
            l["codigo_pendiente"] for l in vista["items"] if not l["existe"]
        ]
        raise ErrorNegocio(
            f"Faltan {len(sin_identificar)} código(s) por dar de alta antes de recibir: "
            + ", ".join(sin_identificar[:5])
            + ("..." if len(sin_identificar) > 5 else "")
        )

    costos = costos or {}
    movimientos = []
    for linea in vista["items"]:
        movimientos.append(
            movimiento_service.registrar_entrada(
                db, usuario_id, linea["producto_id"], linea["cantidad"],
                costos.get(linea["producto_id"]),
                motivo or "Recepción escaneada",
            )
        )

    canasta_repository.marcar_cobrada(db, canasta, None)
    return {
        "productos_recibidos": len(movimientos),
        "unidades_recibidas": sum(m.cantidad for m in movimientos),
        "movimientos": movimientos,
    }
