"""
La venta: donde el sistema toca dinero y mercancía.

Un fallo aquí no se ve. El stock queda mal, la ganancia queda mal, y el
tendero solo lo descubre en el conteo físico de fin de mes.
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core.fechas import hoy_local, sumar_dias
from app.services import product_service, venta_service, cliente_service


@pytest.fixture
def arroz(db, usuario):
    return product_service.agregar(db, usuario.id, "Arroz", 10, 3000, 2000)


@pytest.fixture
def aceite(db, usuario):
    return product_service.agregar(db, usuario.id, "Aceite", 5, 8000, 6000)


def test_vender_descuenta_el_stock(db, usuario, arroz):
    venta_service.vender(db, usuario.id, [{"producto_id": arroz.id, "cantidad": 3}])
    db.refresh(arroz)
    assert arroz.cantidad == 7


def test_la_ganancia_es_precio_menos_costo(db, usuario, arroz):
    venta = venta_service.vender(db, usuario.id, [{"producto_id": arroz.id, "cantidad": 3}])
    assert venta.precio_venta_total == 9000      # 3 x 3000
    assert venta.ganancia_total == 3000          # 3 x (3000 - 2000)


def test_no_se_puede_vender_mas_de_lo_que_hay(db, usuario, arroz):
    with pytest.raises(ErrorNegocio):
        venta_service.vender(db, usuario.id, [{"producto_id": arroz.id, "cantidad": 11}])
    db.refresh(arroz)
    assert arroz.cantidad == 10                  # no se tocó nada


def test_el_mismo_producto_dos_veces_se_suma_antes_de_validar(db, usuario, arroz):
    """Escanear el mismo producto en dos líneas.

    Sin agrupar, cada línea se validaba por separado contra el stock
    COMPLETO: con 10 unidades, dos líneas de 6 pasaban el control una a
    una y dejaban el inventario en -2.
    """
    with pytest.raises(ErrorNegocio):
        venta_service.vender(db, usuario.id, [
            {"producto_id": arroz.id, "cantidad": 6},
            {"producto_id": arroz.id, "cantidad": 6},
        ])
    db.refresh(arroz)
    assert arroz.cantidad == 10


def test_venta_de_varios_productos_en_una_sola(db, usuario, arroz, aceite):
    venta = venta_service.vender(db, usuario.id, [
        {"producto_id": arroz.id, "cantidad": 2},
        {"producto_id": aceite.id, "cantidad": 1},
    ])
    assert venta.precio_venta_total == 14000     # 6000 + 8000
    db.refresh(arroz)
    db.refresh(aceite)
    assert (arroz.cantidad, aceite.cantidad) == (8, 4)


def test_si_un_producto_falla_no_se_vende_ninguno(db, usuario, arroz, aceite):
    """Todo o nada. Una venta a medias descuadra el inventario en
    silencio y nadie se entera hasta el conteo físico."""
    with pytest.raises(ErrorNegocio):
        venta_service.vender(db, usuario.id, [
            {"producto_id": arroz.id, "cantidad": 2},
            {"producto_id": aceite.id, "cantidad": 99},
        ])
    db.refresh(arroz)
    assert arroz.cantidad == 10


def test_no_se_vende_el_producto_de_otro_negocio(db, usuario, otro_usuario, arroz):
    with pytest.raises(NoEncontrado):
        venta_service.vender(db, otro_usuario.id, [{"producto_id": arroz.id, "cantidad": 1}])


def test_la_venta_se_guarda_con_la_fecha_del_negocio(db, usuario, arroz):
    """Render corre en UTC. Sin zona horaria, toda venta después de las
    7 p.m. hora Colombia se guardaba con la fecha del día siguiente —
    justo en las horas de más venta de una tienda."""
    venta = venta_service.vender(db, usuario.id, [{"producto_id": arroz.id, "cantidad": 1}])
    assert venta.fecha == hoy_local()


def test_fiar_exige_decir_a_quien(db, usuario, arroz):
    """Una deuda sin deudor es una pérdida disfrazada de venta."""
    with pytest.raises(ErrorNegocio):
        venta_service.vender(
            db, usuario.id, [{"producto_id": arroz.id, "cantidad": 1}], es_fiado=True,
        )


def test_fiar_saca_la_mercancia_igual(db, usuario, arroz):
    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, None)
    venta_service.vender(
        db, usuario.id, [{"producto_id": arroz.id, "cantidad": 2}],
        cliente_id=cliente.id, es_fiado=True,
    )
    db.refresh(arroz)
    assert arroz.cantidad == 8


def test_el_plazo_del_cliente_se_aplica_solo(db, usuario, arroz):
    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, dias_plazo=15)
    venta = venta_service.vender(
        db, usuario.id, [{"producto_id": arroz.id, "cantidad": 1}],
        cliente_id=cliente.id, es_fiado=True,
    )
    assert venta.fecha_vencimiento == sumar_dias(15)


def test_un_fiado_sin_plazo_nunca_sale_atrasado(db, usuario, arroz):
    """"Cuando puedas" es un acuerdo válido. No se incumple un plazo que
    no existe, y marcarlo en rojo haría que el tendero desconfíe de la
    lista entera."""
    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, None)
    venta_service.vender(
        db, usuario.id, [{"producto_id": arroz.id, "cantidad": 1}],
        cliente_id=cliente.id, es_fiado=True,
    )
    deudores = cliente_service.libreta_de_fiados(db, usuario.id)
    assert deudores[0]["dias_atraso"] == 0


def test_el_resumen_devuelve_todos_los_dias_aunque_no_haya_ventas(db, usuario, arroz):
    """Rellenar los huecos en cero es trabajo del backend. Si faltaran
    días, el frontend tendría que reconstruir el calendario — o sea,
    lógica de negocio en la interfaz."""
    venta_service.vender(db, usuario.id, [{"producto_id": arroz.id, "cantidad": 1}])
    resumen = venta_service.resumen_ultimos_dias(db, usuario.id, 7)
    assert len(resumen["dias"]) == 7
    assert resumen["dias"][0]["fecha"] == hoy_local()
    assert resumen["total_vendido"] == 3000


def test_un_rango_al_reves_es_un_error(db, usuario):
    with pytest.raises(ErrorNegocio):
        venta_service.ventas_por_fecha(db, usuario.id, desde="2026-08-20", hasta="2026-08-01")
