"""
Anular una venta tiene que devolver la mercancía.

Antes no lo hacía: marcaba la venta como eliminada y ya. El tendero
escaneaba mal, borraba la venta, y el inventario se quedaba corto para
siempre — sin rastro en el libro de movimientos y sin ninguna pantalla que
lo delatara.

Es de los peores fallos posibles en este sistema porque se acumula en
silencio: cada corrección deja el stock un poco más torcido, y cuando el
tendero por fin nota que los números no cuadran ya no hay forma de
reconstruir qué pasó.
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.models.movimiento import MovimientoInventario, DEVOLUCION
from app.services import cliente_service, product_service, venta_service


@pytest.fixture
def cuaderno(db, usuario):
    return product_service.agregar(db, usuario.id, "Cuaderno", 20, 5000, 3500)


def test_anular_devuelve_el_stock(db, usuario, cuaderno):
    venta = venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 5}])
    db.refresh(cuaderno)
    assert cuaderno.cantidad == 15

    venta_service.eliminar_venta(db, usuario.id, venta.id)
    db.refresh(cuaderno)
    assert cuaderno.cantidad == 20


def test_anular_deja_rastro_en_el_libro(db, usuario, cuaderno):
    """Sin el movimiento, el stock sube y nadie sabe por qué. El libro es
    lo que hace auditable el inventario."""
    venta = venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 5}])
    venta_service.eliminar_venta(db, usuario.id, venta.id)

    movimiento = (
        db.query(MovimientoInventario)
        .filter(MovimientoInventario.tipo == DEVOLUCION)
        .one()
    )
    assert movimiento.cantidad == 5           # con signo positivo: entró
    assert movimiento.stock_antes == 15
    assert movimiento.stock_despues == 20
    assert movimiento.venta_id == venta.id    # se puede ir del libro a la venta


def test_anular_una_venta_de_varios_productos_los_devuelve_todos(db, usuario, cuaderno):
    lapiz = product_service.agregar(db, usuario.id, "Lápiz", 50, 1000, 600)
    venta = venta_service.vender(db, usuario.id, [
        {"producto_id": cuaderno.id, "cantidad": 2},
        {"producto_id": lapiz.id, "cantidad": 10},
    ])

    venta_service.eliminar_venta(db, usuario.id, venta.id)

    db.refresh(cuaderno)
    db.refresh(lapiz)
    assert (cuaderno.cantidad, lapiz.cantidad) == (20, 50)


def test_anular_dos_veces_no_devuelve_el_stock_por_partida_doble(db, usuario, cuaderno):
    """La segunda llamada debe fallar. Si devolviera el stock otra vez, el
    inventario quedaría inflado — el error contrario al original, y
    igual de invisible."""
    venta = venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 5}])
    venta_service.eliminar_venta(db, usuario.id, venta.id)

    with pytest.raises(NoEncontrado):
        venta_service.eliminar_venta(db, usuario.id, venta.id)

    db.refresh(cuaderno)
    assert cuaderno.cantidad == 20


def test_anular_saca_la_venta_de_los_totales(db, usuario, cuaderno):
    venta = venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 5}])
    venta_service.eliminar_venta(db, usuario.id, venta.id)

    ventas, ganancia = venta_service.ventas_por_fecha(db, usuario.id)
    assert ventas == []
    assert ganancia == 0


def test_no_se_anula_un_fiado_que_ya_tiene_abonos(db, usuario, cuaderno):
    """Los abonos son plata que el cliente YA entregó.

    Anular la venta los dejaría apuntando a algo que no existe: el dinero
    desaparecería del sistema sin que nadie lo note, y la señora seguiría
    creyendo que abonó.
    """
    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, None)
    venta = venta_service.vender(
        db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 2}],
        cliente_id=cliente.id, es_fiado=True,
    )
    cliente_service.registrar_abono(db, usuario.id, venta.id, 4000, None)

    with pytest.raises(ErrorNegocio):
        venta_service.eliminar_venta(db, usuario.id, venta.id)

    # Y la mercancía NO volvió: la venta sigue viva.
    db.refresh(cuaderno)
    assert cuaderno.cantidad == 18


def test_un_fiado_sin_abonos_si_se_puede_anular(db, usuario, cuaderno):
    """Si no se ha recibido plata, no hay nada que resolver."""
    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, None)
    venta = venta_service.vender(
        db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 2}],
        cliente_id=cliente.id, es_fiado=True,
    )

    venta_service.eliminar_venta(db, usuario.id, venta.id)

    db.refresh(cuaderno)
    assert cuaderno.cantidad == 20
    assert cliente_service.libreta_de_fiados(db, usuario.id) == []


def test_no_se_anula_la_venta_de_otro_negocio(db, usuario, otro_usuario, cuaderno):
    venta = venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 5}])

    with pytest.raises(NoEncontrado):
        venta_service.eliminar_venta(db, otro_usuario.id, venta.id)

    db.refresh(cuaderno)
    assert cuaderno.cantidad == 15


def test_se_puede_anular_aunque_el_producto_ya_no_exista(db, usuario, cuaderno):
    """Negarse dejaría al tendero atrapado con una venta falsa que no
    puede quitar de sus cuentas."""
    venta = venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 5}])
    product_service.eliminar(db, usuario.id, cuaderno.id)

    venta_service.eliminar_venta(db, usuario.id, venta.id)

    ventas, _ = venta_service.ventas_por_fecha(db, usuario.id)
    assert ventas == []
