"""
Servicios: productos que no llevan existencias.

Una papelería vende fotocopias, impresiones, plastificado, anillado. No se
te acaban las fotocopias. Antes había que inventarles un stock falso y el
sistema se negaba a venderlos al llegar a cero:

    "No puedes vender más 'Fotocopia' de lo que hay en stock
     (pides 20, disponible: 0)"

Lo que un servicio SÍ hace igual que un producto: se vende, deja ganancia
(el papel y el tóner cuestan) y cuenta para el análisis del negocio.
"""

import pytest

from app.core.exceptions import ErrorNegocio
from app.models.movimiento import MovimientoInventario
from app.services import analitica_service, canasta_service, movimiento_service
from app.services import product_service, venta_service


@pytest.fixture
def fotocopia(db, usuario):
    return product_service.agregar(db, usuario.id, "Fotocopia", 0, 200, 50,
                                   controla_stock=False)


@pytest.fixture
def cuaderno(db, usuario):
    return product_service.agregar(db, usuario.id, "Cuaderno", 20, 5000, 3500)


def test_un_servicio_se_vende_sin_limite(db, usuario, fotocopia):
    """El fallo original: a las 100 fotocopias dejaba de vender."""
    for _ in range(20):
        venta_service.vender(db, usuario.id, [{"producto_id": fotocopia.id, "cantidad": 50}])

    db.refresh(fotocopia)
    assert fotocopia.cantidad == 0          # sigue en cero, y no estorba


def test_un_servicio_deja_ganancia(db, usuario, fotocopia):
    """No es gratis: el papel y el tóner cuestan. Si la ganancia no se
    calculara, la papelería vería su servicio más rentable como si no
    aportara nada."""
    venta = venta_service.vender(db, usuario.id, [{"producto_id": fotocopia.id, "cantidad": 10}])
    assert venta.precio_venta_total == 2000
    assert venta.ganancia_total == 1500     # 10 x (200 - 50)


def test_un_servicio_no_ensucia_el_libro_de_movimientos(db, usuario, fotocopia):
    """El libro se audita sumando: stock_antes + cantidad = stock_despues.
    Una fotocopia no mueve existencias, así que su fila rompería esa
    igualdad o sería una línea vacía."""
    venta_service.vender(db, usuario.id, [{"producto_id": fotocopia.id, "cantidad": 10}])
    assert db.query(MovimientoInventario).count() == 0


def test_los_productos_normales_siguen_controlando_stock(db, usuario, cuaderno):
    """La regresión que más importa: esto no puede haber aflojado el
    control de los productos de verdad."""
    with pytest.raises(ErrorNegocio):
        venta_service.vender(db, usuario.id, [{"producto_id": cuaderno.id, "cantidad": 21}])

    db.refresh(cuaderno)
    assert cuaderno.cantidad == 20


def test_una_venta_mixta_descuenta_solo_lo_que_lleva_stock(db, usuario, fotocopia, cuaderno):
    """Lo normal en una papelería: un cuaderno y diez fotocopias."""
    venta = venta_service.vender(db, usuario.id, [
        {"producto_id": cuaderno.id, "cantidad": 1},
        {"producto_id": fotocopia.id, "cantidad": 10},
    ])

    assert venta.precio_venta_total == 7000     # 5000 + 2000
    db.refresh(cuaderno)
    db.refresh(fotocopia)
    assert cuaderno.cantidad == 19
    assert fotocopia.cantidad == 0


def test_anular_una_venta_de_servicio_no_infla_el_inventario(db, usuario, fotocopia):
    """Un servicio nunca salió del inventario, así que no vuelve a él."""
    venta = venta_service.vender(db, usuario.id, [{"producto_id": fotocopia.id, "cantidad": 10}])
    venta_service.eliminar_venta(db, usuario.id, venta.id)

    db.refresh(fotocopia)
    assert fotocopia.cantidad == 0
    ventas, ganancia = venta_service.ventas_por_fecha(db, usuario.id)
    assert (ventas, ganancia) == ([], 0)


def test_un_servicio_no_aparece_en_por_agotarse(db, usuario, fotocopia):
    """Sin este filtro, el servicio más vendido de la papelería
    encabezaría permanentemente la alerta de "se te está acabando". Y una
    alerta siempre encendida deja de mirarse — incluida la de los
    productos que sí se acaban."""
    for _ in range(5):
        venta_service.vender(db, usuario.id, [{"producto_id": fotocopia.id, "cantidad": 100}])

    alertas = analitica_service.por_agotarse(db, usuario.id)
    assert all(a["nombre"] != "Fotocopia" for a in alertas)


def test_un_servicio_no_cuenta_como_capital_parado(db, usuario, fotocopia):
    """Nadie compró por adelantado un lote de fotocopias."""
    parado = analitica_service.capital_parado(db, usuario.id)
    assert all(p["nombre"] != "Fotocopia" for p in parado["productos"])
    assert parado["total_inmovilizado"] == 0


def test_un_servicio_si_aparece_en_los_mas_vendidos(db, usuario, fotocopia):
    """Para el análisis del negocio es un producto más — y en una
    papelería las fotocopias suelen ser lo que más deja."""
    venta_service.vender(db, usuario.id, [{"producto_id": fotocopia.id, "cantidad": 500}])

    resumen = analitica_service.resumen(db, usuario.id, 30)
    assert any(p["nombre"] == "Fotocopia" for p in resumen["mas_vendidos"])


def test_no_se_registran_entradas_de_un_servicio(db, usuario, fotocopia):
    """No llegan fotocopias del proveedor. Se rechaza con un mensaje claro
    en vez de ignorarlo: si no pasara nada, el tendero lo intentaría otra
    vez pensando que falló."""
    with pytest.raises(ErrorNegocio):
        movimiento_service.registrar_entrada(db, usuario.id, fotocopia.id, 100)


def test_no_se_registran_mermas_ni_ajustes_de_un_servicio(db, usuario, fotocopia):
    with pytest.raises(ErrorNegocio):
        movimiento_service.registrar_merma(db, usuario.id, fotocopia.id, 5)
    with pytest.raises(ErrorNegocio):
        movimiento_service.ajustar(db, usuario.id, fotocopia.id, 30)


def test_un_servicio_nace_en_cero_aunque_manden_cantidad(db, usuario):
    """Guardar la cantidad del formulario dejaría un número sin significado
    pintado en pantalla como si fueran existencias reales."""
    s = product_service.agregar(db, usuario.id, "Plastificado", 999, 3000, 500,
                                controla_stock=False)
    assert s.cantidad == 0


def test_en_la_canasta_un_servicio_nunca_sale_sin_stock(db, usuario, fotocopia):
    """Pintar una fotocopia en rojo por tener cero existencias asusta al
    tendero con un problema que no existe."""
    canasta = canasta_service.abrir(db, usuario.id)
    vista = canasta_service.agregar(db, canasta["id"], usuario.id, None,
                                    None, "Fotocopia", None, 50)

    linea = vista["items"][0]
    assert linea["hay_stock"] is True
    assert linea["controla_stock"] is False

    venta = canasta_service.cobrar(db, canasta["id"], usuario.id)
    assert venta.precio_venta_total == 10000


def test_editar_sin_mandar_el_campo_no_convierte_nada_en_servicio(db, usuario, cuaderno):
    """None significa "el frontend no mandó el campo". Tratarlo como False
    convertiría en servicio cualquier producto editado desde una pantalla
    que no incluya la casilla, y perdería sus existencias de vista."""
    product_service.editar(db, usuario.id, cuaderno.id, "Cuaderno grande", 20, 6000, 4000)

    db.refresh(cuaderno)
    assert cuaderno.controla_stock is True
    assert cuaderno.cantidad == 20


def test_convertir_un_producto_en_servicio_le_pone_el_stock_en_cero(db, usuario, cuaderno):
    product_service.editar(db, usuario.id, cuaderno.id, "Cuaderno", 20, 5000, 3500,
                           controla_stock=False)
    db.refresh(cuaderno)
    assert cuaderno.controla_stock is False
    assert cuaderno.cantidad == 0
