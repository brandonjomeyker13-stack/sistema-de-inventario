from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core.fechas import hoy_local
from app.models.movimiento import AJUSTE
from app.repositories import producto_repository, categoria_repository, movimiento_repository


def listar(db: Session, usuario_id: str, q: str | None = None,
           categoria_id: str | None = None, limite: int | None = None, offset: int = 0,
           sin_codigo: bool = False):
    return producto_repository.listar(db, usuario_id, q, categoria_id, limite, offset,
                                      sin_codigo)


def contar(db: Session, usuario_id: str, q: str | None = None,
           categoria_id: str | None = None, sin_codigo: bool = False) -> int:
    return producto_repository.contar(db, usuario_id, q, categoria_id, sin_codigo)


def buscar_por_codigo_barras(db: Session, usuario_id: str, codigo: str):
    """Lo que consulta el lector al escanear.

    Si devuelve None no es un error: significa "este código no lo conozco
    todavía", y el frontend debe ofrecer darlo de alta. Por eso no lanza
    NoEncontrado — es un caso normal, no un fallo.
    """
    return producto_repository.obtener_por_codigo_barras(db, usuario_id, codigo)


def _validar_precio(nombre: str, precio: float, costo: float, permitir_perdida: bool):
    """Avisa cuando el producto se vendería por menos de lo que cuesta.

    Es el error de dedo más común al dar de alta un producto: escribir el
    costo en la casilla del precio y al revés. Y hasta ahora no lo veía
    nadie — el producto se guardaba tranquilo y la venta reventaba DESPUÉS
    con un error 500 que no señalaba al producto culpable.

    Se valida aquí, en el alta, y no al vender, por una razón: aquí la
    persona tiene los dos números delante y puede corregirlos. Al cobrar,
    con un cliente esperando, ya no.

    NO se prohíbe del todo: vender por debajo del costo es un hecho real
    —liquidar algo por vencer, sacar mercancía dañada, una promoción
    gancho— y el sistema tiene que poder registrarlo. Se exige que sea
    EXPLÍCITO, con el mismo criterio que el asistente: se propone, y el
    tendero confirma.
    """
    if permitir_perdida or precio >= costo:
        return

    perdida = costo - precio
    raise ErrorNegocio(
        f"'{nombre.strip()}' se vendería a ${precio:,.0f} pero te cuesta ${costo:,.0f}: "
        f"perderías ${perdida:,.0f} en cada unidad. "
        "¿Escribiste el costo en la casilla del precio? Si de verdad quieres "
        "venderlo con pérdida (una liquidación, por ejemplo), vuelve a guardarlo "
        "marcando que la pérdida es a propósito."
    )


def _validar_categoria(db: Session, usuario_id: str, categoria_id: str | None):
    """Que la categoría exista y sea de este negocio.

    Sin esto, mandar el categoria_id de otro usuario dejaría un producto
    apuntando a una categoría ajena — una fuga silenciosa entre tiendas.
    """
    if categoria_id and not categoria_repository.obtener_por_id(db, usuario_id, categoria_id):
        raise NoEncontrado("Categoría no encontrada")


def agregar(
    db: Session, usuario_id: str, nombre: str, cantidad: int, precio: float, costo: float,
    codigo_barras: str | None = None, categoria_id: str | None = None,
    controla_stock: bool = True, permitir_perdida: bool = False,
    stock_minimo: int | None = None,
):
    _validar_precio(nombre, precio, costo, permitir_perdida)
    if producto_repository.existe_nombre(db, usuario_id, nombre):
        raise ErrorNegocio(f"Ya existe un producto llamado '{nombre.strip()}'")
    if codigo_barras and producto_repository.existe_codigo_barras(db, usuario_id, codigo_barras):
        raise ErrorNegocio(f"Ya tienes un producto con el código {codigo_barras.strip()}")
    _validar_categoria(db, usuario_id, categoria_id)
    return producto_repository.crear(
        db, usuario_id, nombre, cantidad, precio, costo, codigo_barras, categoria_id,
        # Un servicio nace en cero y se queda ahí. Guardar la cantidad que
        # venga en el formulario dejaría un número que no significa nada y
        # que aparecería en pantalla como si fueran existencias reales.
        controla_stock=controla_stock, stock_minimo=stock_minimo,
    )


def editar(
    db: Session, usuario_id: str, producto_id: str, nombre: str, cantidad: int, precio: float,
    costo: float, codigo_barras: str | None = None, categoria_id: str | None = None,
    controla_stock: bool | None = None, permitir_perdida: bool = False,
    stock_minimo: int | None = None,
):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    _validar_precio(nombre, precio, costo, permitir_perdida)
    if producto_repository.existe_nombre(db, usuario_id, nombre, excluir_id=producto_id):
        raise ErrorNegocio(f"Ya existe otro producto llamado '{nombre.strip()}'")
    if codigo_barras and producto_repository.existe_codigo_barras(
        db, usuario_id, codigo_barras, excluir_id=producto_id
    ):
        raise ErrorNegocio(f"Otro producto ya usa el código {codigo_barras.strip()}")
    _validar_categoria(db, usuario_id, categoria_id)

    # None = el frontend no mandó el campo, así que se respeta lo que ya
    # estaba. Tratar la ausencia como False convertiría en servicio a
    # cualquier producto editado desde una pantalla que no incluya la
    # casilla — y perdería sus existencias de vista.
    lleva_stock = producto.controla_stock if controla_stock is None else controla_stock

    # Editar la cantidad desde el formulario también mueve el stock, así
    # que también va al libro. Si no, quedaría un hueco justo en la vía
    # más fácil de cambiar existencias, y el historial dejaría de cuadrar.
    #
    # El movimiento se registra ANTES de actualizar: registrar() no hace
    # commit, y el commit de actualizar() guarda los dos a la vez.
    #
    # Un servicio no genera ajuste: su cantidad no significa nada, así que
    # una fila diciendo que pasó de 0 a 50 sería ruido en el libro.
    if lleva_stock and cantidad != producto.cantidad:
        movimiento_repository.registrar(
            db, usuario_id, producto_id, AJUSTE, cantidad - producto.cantidad,
            producto.cantidad, hoy_local(), "Editado desde el formulario de producto",
        )

    return producto_repository.actualizar(
        db, producto, nombre, cantidad, precio, costo, codigo_barras, categoria_id,
        controla_stock=lleva_stock, stock_minimo=stock_minimo,
    )


def eliminar(db: Session, usuario_id: str, producto_id: str):
    producto = producto_repository.obtener_por_id(db, usuario_id, producto_id)
    if not producto:
        raise NoEncontrado("Producto no encontrado")
    producto_repository.eliminar(db, producto)
