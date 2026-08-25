"""
Pegarle un código de barras a un producto que ya existe.

Es la pieza que conecta la importación con el lector, y sin ella la cadena
estaba rota:

  1. La plantilla crea los productos SIN código de barras.
  2. Para vender con el celular hacen falta códigos.
  3. Y lo único que había para ponerlos era PUT /productos/{id}, que exige
     reenviar el producto entero — desde el celular, imposible.

O sea que el celular como lector, que es la función que más piden porque
casi nadie tiene lector USB, no servía después de importar. Que es
exactamente como se monta a cada cliente.
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.services import canasta_service, product_service, venta_service


@pytest.fixture
def importado(db, usuario):
    """Un producto como queda al importarlo: sin código."""
    return product_service.agregar(db, usuario.id, "Cuaderno argollado", 30, 6500, 4800)


def test_se_le_pega_el_codigo(db, usuario, importado):
    assert importado.codigo_barras is None

    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")

    db.refresh(importado)
    assert importado.codigo_barras == "7702001234567"


def test_no_toca_nada_mas(db, usuario, importado):
    """La razón de que exista aparte de `editar`: desde el celular no se
    manda la cantidad, y reenviarla desde una pantalla que no la muestra
    sería una forma cómoda de pisar el stock sin querer."""
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")

    db.refresh(importado)
    assert importado.nombre == "Cuaderno argollado"
    assert importado.cantidad == 30
    assert importado.precio == 6500
    assert importado.cuanto_costo == 4800


def test_despues_de_asignarlo_ya_se_puede_vender_escaneando(db, usuario, importado):
    """Cierra la cadena: importar, pegar el código, vender con el lector."""
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")

    venta = venta_service.vender(
        db, usuario.id, [{"codigo_barras": "7702001234567", "cantidad": 2}],
    )
    assert venta.precio_venta_total == 13000


def test_el_upc_de_12_digitos_se_guarda_como_ean13(db, usuario, importado):
    """Misma normalización que en todos lados: el mismo producto leído por
    dos lectores distintos tiene que seguir siendo uno solo."""
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "012345678905")

    db.refresh(importado)
    assert importado.codigo_barras == "0012345678905"


def test_se_le_puede_quitar(db, usuario, importado):
    """Hace falta cuando se pegó al producto equivocado, que escaneando en
    una estantería pasa."""
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, None)

    db.refresh(importado)
    assert importado.codigo_barras is None


def test_un_codigo_repetido_dice_de_quien_es(db, usuario, importado):
    """Saber A CUÁL se lo pegaste antes es lo que permite corregirlo sin ir
    a buscar entre trescientos productos."""
    otro = product_service.agregar(db, usuario.id, "Lápiz Mirado", 50, 1200, 800)
    product_service.agregar_codigo_barras(db, usuario.id, otro.id, "7702001234567")

    with pytest.raises(ErrorNegocio) as exc:
        product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")

    assert "Lápiz Mirado" in str(exc.value)


def test_reasignarle_el_mismo_codigo_al_mismo_producto_no_falla(db, usuario, importado):
    """Escanear dos veces el mismo producto no puede dar error."""
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")
    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")

    db.refresh(importado)
    assert importado.codigo_barras == "7702001234567"


def test_no_se_le_asigna_a_un_producto_de_otro_negocio(db, usuario, otro_usuario, importado):
    with pytest.raises(NoEncontrado):
        product_service.agregar_codigo_barras(
            db, otro_usuario.id, importado.id, "7702001234567",
        )


def test_dos_negocios_pueden_usar_el_mismo_codigo(db, usuario, otro_usuario, importado):
    """Dos tiendas venden el mismo arroz con el mismo EAN. Eso es
    justamente lo que hará comparables sus datos algún día."""
    ajeno = product_service.agregar(db, otro_usuario.id, "Cuaderno", 10, 6000, 4000)

    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")
    product_service.agregar_codigo_barras(db, otro_usuario.id, ajeno.id, "7702001234567")

    db.refresh(importado)
    db.refresh(ajeno)
    assert importado.codigo_barras == ajeno.codigo_barras


def test_el_pendiente_de_la_canasta_se_resuelve_solo(db, usuario, importado):
    """El flujo completo de caminar la estantería.

    El celular escanea un código que no conoce nadie, queda pendiente en la
    canasta, se le asigna al producto, y la línea se resuelve sola en el
    siguiente sondeo — sin tocar la canasta.
    """
    from app.models.canasta import PROPOSITO_INVENTARIO

    canasta = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    vista = canasta_service.agregar(db, canasta["id"], usuario.id, None,
                                    "7702001234567", None, None, 1)
    assert vista["pendientes"] == 1
    assert vista["items"][0]["existe"] is False

    product_service.agregar_codigo_barras(db, usuario.id, importado.id, "7702001234567")

    vista = canasta_service.ver(db, canasta["id"], usuario.id, None)
    assert vista["pendientes"] == 0
    assert vista["items"][0]["nombre"] == "Cuaderno argollado"
