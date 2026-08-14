"""
Reintentar un cobro no puede duplicar la venta.

Escrito para una papelería que trabaja con datos móviles: el tendero
cobra, la petición sale, y la señal se cae antes de que llegue la
respuesta. El frontend no sabe si la venta quedó guardada.

Si reintenta y se registra otra vez, el stock se descuenta doble y se suma
plata que nadie pagó. Es el peor error posible en este sistema porque no
se nota: parece un buen día, y el descuadre aparece semanas después en el
conteo físico, cuando ya no hay forma de saber qué pasó.
"""

import pytest

from app.core.exceptions import ErrorNegocio
from app.models.venta import Venta
from app.services import canasta_service, product_service, venta_service


@pytest.fixture
def arroz(db, usuario):
    return product_service.agregar(db, usuario.id, "Arroz", 10, 3000, 2000,
                                   codigo_barras="7702001234567")


def test_la_misma_clave_devuelve_la_misma_venta(db, usuario, arroz):
    linea = [{"producto_id": arroz.id, "cantidad": 2}]

    primera = venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")
    segunda = venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")

    assert primera.id == segunda.id
    assert db.query(Venta).count() == 1


def test_el_reintento_no_descuenta_el_stock_otra_vez(db, usuario, arroz):
    """Lo que de verdad importa. Una venta duplicada se puede borrar; un
    inventario descontado dos veces hay que reconstruirlo contando."""
    linea = [{"producto_id": arroz.id, "cantidad": 3}]

    venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")
    venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")

    db.refresh(arroz)
    assert arroz.cantidad == 7          # 10 - 3, una sola vez


def test_el_reintento_no_suma_plata_dos_veces(db, usuario, arroz):
    linea = [{"producto_id": arroz.id, "cantidad": 2}]

    venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")
    venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")

    _, ganancia = venta_service.ventas_por_fecha(db, usuario.id)
    assert ganancia == 2000             # 2 x (3000 - 2000), no 4000


def test_sin_clave_dos_ventas_iguales_son_dos_ventas(db, usuario, arroz):
    """En una tienda, dos personas comprando lo mismo seguido es lo NORMAL.

    El servidor no puede distinguir eso de un reintento — por eso la clave
    la genera quien pulsó el botón, que es el único que lo sabe. Sin
    clave, cada petición es una venta.
    """
    linea = [{"producto_id": arroz.id, "cantidad": 1}]

    venta_service.vender(db, usuario.id, linea)
    venta_service.vender(db, usuario.id, linea)

    assert db.query(Venta).count() == 2
    db.refresh(arroz)
    assert arroz.cantidad == 8


def test_claves_distintas_son_ventas_distintas(db, usuario, arroz):
    linea = [{"producto_id": arroz.id, "cantidad": 1}]

    a = venta_service.vender(db, usuario.id, linea, clave_idempotencia="venta-1")
    b = venta_service.vender(db, usuario.id, linea, clave_idempotencia="venta-2")

    assert a.id != b.id
    assert db.query(Venta).count() == 2


def test_la_clave_de_un_negocio_no_afecta_a_otro(db, usuario, otro_usuario, arroz):
    """La clave es única DENTRO de cada negocio. Si fuera global, una
    tienda podría bloquear las ventas de otra mandando claves a propósito
    — y dos tiendas generando el mismo identificador por casualidad no
    significa nada."""
    otro_arroz = product_service.agregar(db, otro_usuario.id, "Arroz", 10, 3000, 2000)

    venta_service.vender(db, usuario.id, [{"producto_id": arroz.id, "cantidad": 1}],
                         clave_idempotencia="misma-clave")
    venta_service.vender(db, otro_usuario.id, [{"producto_id": otro_arroz.id, "cantidad": 1}],
                         clave_idempotencia="misma-clave")

    assert db.query(Venta).count() == 2


def test_el_reintento_funciona_aunque_ya_no_quede_stock(db, usuario, arroz):
    """Sutil, y es la razón del atajo en venta_service.

    Se venden las 10 unidades. Al reintentar, si el código volviera a
    validar el stock encontraría 0 disponibles y respondería "no hay
    suficiente" — un error por culpa de su PROPIO descuento anterior. El
    tendero vería fallar una venta que en realidad sí se hizo.
    """
    linea = [{"producto_id": arroz.id, "cantidad": 10}]

    primera = venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")
    db.refresh(arroz)
    assert arroz.cantidad == 0

    segunda = venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")
    assert segunda.id == primera.id


def test_una_venta_fiada_tampoco_se_duplica(db, usuario, arroz):
    """Duplicar un fiado es duplicar una deuda: el tendero le cobraría a
    la señora el doble de lo que se llevó."""
    from app.services import cliente_service

    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, None)
    linea = [{"producto_id": arroz.id, "cantidad": 2}]

    venta_service.vender(db, usuario.id, linea, cliente_id=cliente.id, es_fiado=True,
                         clave_idempotencia="fiado-1")
    venta_service.vender(db, usuario.id, linea, cliente_id=cliente.id, es_fiado=True,
                         clave_idempotencia="fiado-1")

    deudores = cliente_service.libreta_de_fiados(db, usuario.id)
    assert len(deudores) == 1
    assert deudores[0]["deuda_total"] == 6000        # 2 x 3000, no 12000


def test_el_reintento_no_duplica_el_libro_de_movimientos(db, usuario, arroz):
    """El libro es lo que hace auditable el inventario. Dos movimientos
    para una sola venta harían imposible cuadrar el stock a mano."""
    from app.models.movimiento import MovimientoInventario, VENTA

    linea = [{"producto_id": arroz.id, "cantidad": 2}]
    venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")
    venta_service.vender(db, usuario.id, linea, clave_idempotencia="abc-123")

    de_venta = db.query(MovimientoInventario).filter(
        MovimientoInventario.tipo == VENTA
    ).count()
    assert de_venta == 1


def test_cobrar_la_canasta_es_idempotente_sin_que_el_frontend_haga_nada(db, usuario, arroz):
    """La clave por defecto es el id de la canasta.

    Es la clave natural: una canasta se cobra UNA vez, así que dos cobros
    sobre la misma canasta son siempre un reintento. Con esto, el celular
    queda protegido aunque Lovable no mande ninguna cabecera.
    """
    canasta = canasta_service.abrir(db, usuario.id)
    canasta_service.agregar(db, canasta["id"], usuario.id, None,
                            "7702001234567", None, None, 2)

    venta = canasta_service.cobrar(db, canasta["id"], usuario.id)

    # El segundo cobro falla porque la canasta ya está cerrada — que es la
    # primera línea de defensa. La segunda es que, si por lo que sea
    # llegara a pasar, la clave impediría la venta duplicada.
    with pytest.raises(ErrorNegocio):
        canasta_service.cobrar(db, canasta["id"], usuario.id)

    assert db.query(Venta).count() == 1
    assert venta.clave_idempotencia == f"canasta:{canasta['id']}"
    db.refresh(arroz)
    assert arroz.cantidad == 8


def test_dos_reintentos_simultaneos_solo_crean_una_venta(db, usuario, arroz):
    """La carrera de verdad: dos peticiones que pasan a la vez la
    comprobación previa y las dos intentan insertar.

    Se simula saltándose el atajo del servicio y llamando al repositorio
    directamente dos veces, que es justo lo que pasaría con dos procesos
    concurrentes. Quien pierde la carrera choca contra el índice único y
    debe recibir la venta del otro, no un error.
    """
    from app.repositories import venta_repository

    def linea():
        db.refresh(arroz)
        return [{
            "producto": arroz, "cantidad": 1,
            "total": 3000.0, "ganancia": 1000.0,
        }]

    primera = venta_repository.crear_venta_atomica(
        db, usuario.id, linea(), "2026-08-13", clave_idempotencia="carrera",
    )
    segunda = venta_repository.crear_venta_atomica(
        db, usuario.id, linea(), "2026-08-13", clave_idempotencia="carrera",
    )

    assert primera.id == segunda.id
    assert db.query(Venta).count() == 1
    db.refresh(arroz)
    assert arroz.cantidad == 9      # el rollback deshizo el segundo descuento
