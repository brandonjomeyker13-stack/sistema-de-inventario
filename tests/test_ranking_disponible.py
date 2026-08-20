"""
El ranking de más vendidos y los productos que ya no existen.

Nació de un fallo real en producción. El frontend pintaba botones de "más
vendidos" con este ranking, y al tocar uno el backend respondía 404
"Producto no encontrado". Desde fuera parecía que la venta estaba rota.

La causa: el ranking sale del HISTORIAL DE VENTAS, no del inventario. Un
producto borrado —o renombrado y recreado— sigue apareciendo con su
producto_id viejo, que ya no resuelve.

La decisión: no se ocultan del ranking, se MARCAN con `disponible`. El
ranking es análisis histórico; si se escondiera lo que se vendió y luego se
borró, los totales de ingresos y ganancia mentirían.
"""

import pytest

from app.core.exceptions import NoEncontrado
from app.services import (
    analitica_service, canasta_service, product_service, venta_service,
)


@pytest.fixture
def vendido_y_borrado(db, usuario):
    """Un producto que se vendió y después se borró."""
    p = product_service.agregar(db, usuario.id, "Cartuchera", 20, 15000, 9500)
    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 3}])
    product_service.eliminar(db, usuario.id, p.id)
    return p


def test_un_producto_borrado_sigue_en_el_ranking(db, usuario, vendido_y_borrado):
    """Tiene que seguir: se vendió de verdad y esa plata entró. Ocultarlo
    haría que los ingresos del mes no cuadraran con la caja."""
    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)

    assert len(ranking) == 1
    assert ranking[0]["nombre"] == "Cartuchera"
    assert ranking[0]["unidades"] == 3
    assert ranking[0]["ingresos"] == 45000


def test_pero_se_marca_como_no_disponible(db, usuario, vendido_y_borrado):
    """La bandera que evita el 404: el frontend sabe que ese botón no se
    puede tocar sin traerse el inventario entero para cruzarlo."""
    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)

    assert ranking[0]["disponible"] is False
    assert ranking[0]["nombre_actual"] is None


def test_un_producto_vivo_si_esta_disponible(db, usuario):
    p = product_service.agregar(db, usuario.id, "Arroz", 20, 2000, 1500)
    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 2}])

    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)
    assert ranking[0]["disponible"] is True
    assert ranking[0]["nombre_actual"] == "Arroz"


def test_un_producto_renombrado_muestra_los_dos_nombres(db, usuario):
    """El caso exacto que se vio en producción: el ranking decía "Cuadernos
    100 hojas" (como se vendió) y el producto ya se llamaba "Cuaderno 100
    hojas". Con los dos nombres, el frontend puede mostrar el histórico sin
    perder el enlace al producto actual.
    """
    p = product_service.agregar(db, usuario.id, "Cuadernos 100 hojas", 20, 6500, 4800)
    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 5}])
    product_service.editar(db, usuario.id, p.id, "Cuaderno 100 hojas", 15, 6500, 4800)

    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)
    assert ranking[0]["nombre"] == "Cuadernos 100 hojas"       # como se vendió
    assert ranking[0]["nombre_actual"] == "Cuaderno 100 hojas"  # como se llama hoy
    assert ranking[0]["disponible"] is True                     # y se puede vender


def test_el_id_de_un_producto_disponible_si_sirve_para_vender(db, usuario):
    """Cierra el círculo: lo que el ranking marca como disponible tiene que
    poder agregarse a una canasta sin dar 404."""
    p = product_service.agregar(db, usuario.id, "Arroz", 20, 2000, 1500)
    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 2}])

    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)
    disponible = next(r for r in ranking if r["disponible"])

    canasta = canasta_service.abrir(db, usuario.id)
    vista = canasta_service.agregar(
        db, canasta["id"], usuario.id, None, None, None, disponible["producto_id"], 1,
    )
    assert vista["items"][0]["nombre"] == "Arroz"


def test_el_id_de_un_borrado_da_404_y_por_eso_hace_falta_la_bandera(db, usuario,
                                                                    vendido_y_borrado):
    """Documenta el fallo original: sin `disponible`, el frontend no tenía
    forma de saber cuáles botones iban a reventar."""
    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)
    canasta = canasta_service.abrir(db, usuario.id)

    with pytest.raises(NoEncontrado):
        canasta_service.agregar(
            db, canasta["id"], usuario.id, None, None, None,
            ranking[0]["producto_id"], 1,
        )


def test_los_totales_no_cambian_al_borrar_un_producto(db, usuario):
    """La razón de marcar en vez de excluir. Si el ranking ocultara lo
    borrado, el resumen del mes mostraría menos ingresos de los que
    realmente entraron a la caja."""
    p = product_service.agregar(db, usuario.id, "Arroz", 20, 2000, 1500)
    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 5}])

    antes = analitica_service.resumen(db, usuario.id, 30)["total_vendido"]
    product_service.eliminar(db, usuario.id, p.id)
    despues = analitica_service.resumen(db, usuario.id, 30)["total_vendido"]

    assert antes == despues == 10000
