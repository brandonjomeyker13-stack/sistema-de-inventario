"""
Cuándo dos nombres son el mismo producto.

Nació de una comprobación real: el sistema trataba "Café" y "CAFÉ" como
productos distintos, y el stock quedaba partido en dos sin que el tendero
entendiera por qué.

Y había algo peor todavía: la comparación se hacía con `ILIKE`, que se
comporta distinto según el motor con las letras acentuadas.

    'CAFÉ' contra 'Café'  ->  PostgreSQL: iguales   SQLite: distintos

Las pruebas corren en SQLite y producción en PostgreSQL, así que esto podía
pasar en verde en local y fallar desplegado. Ahora la llave se calcula en
Python (app/core/texto.py) y las dos bases se comportan igual.
"""

import pytest

from app.core.exceptions import ErrorNegocio
from app.core.texto import clave_nombre
from app.schemas.importacion import FilaImportar
from app.services import importacion_service, product_service


# --- La llave canónica ----------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("Arroz", "arroz"),
    ("ARROZ", "arroz"),
    ("aRRoz", "arroz"),
    ("  Arroz  ", "arroz"),
    ("Arroz   Blanco", "arroz blanco"),
    ("Café", "cafe"),
    ("CAFÉ", "cafe"),
    ("Piña", "pina"),
    ("Jabón Rey", "jabon rey"),
    ("", ""),
    (None, ""),
])
def test_la_llave_canonica(entrada, esperado):
    assert clave_nombre(entrada) == esperado


# --- Crear a mano ---------------------------------------------------------

@pytest.mark.parametrize("variante", [
    "Arroz", "arroz", "ARROZ", "aRRoz", "  Arroz  ", "Arroz ",
])
def test_no_se_puede_crear_el_mismo_producto_con_otra_capitalizacion(db, usuario, variante):
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500)
    with pytest.raises(ErrorNegocio):
        product_service.agregar(db, usuario.id, variante, 5, 2000, 1500)


@pytest.mark.parametrize("variante", ["Cafe", "CAFE", "CAFÉ", "café", "  cafe  "])
def test_las_tildes_no_crean_un_producto_nuevo(db, usuario, variante):
    """El caso más común: el tendero escribe sin tilde porque el teclado del
    celular le estorba."""
    product_service.agregar(db, usuario.id, "Café", 10, 3000, 2000)
    with pytest.raises(ErrorNegocio):
        product_service.agregar(db, usuario.id, variante, 5, 3000, 2000)


@pytest.mark.parametrize("otro", ["Ar roz", "Arroz Blanco", "Arrozito", "Arro"])
def test_un_nombre_de_verdad_distinto_si_se_puede_crear(db, usuario, otro):
    """No hay que pasarse de listo: "Arroz Blanco" ES otro producto."""
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500)
    product_service.agregar(db, usuario.id, otro, 5, 2000, 1500)


def test_el_nombre_se_guarda_como_lo_escribio_el_tendero(db, usuario):
    """La llave es solo para comparar. En pantalla va lo que él escribió,
    con sus tildes y mayúsculas."""
    p = product_service.agregar(db, usuario.id, "Café Molido", 10, 3000, 2000)
    assert p.nombre == "Café Molido"
    assert p.nombre_clave == "cafe molido"


def test_renombrar_actualiza_la_llave(db, usuario):
    """Si la llave se quedara atrás, el producto dejaría de encontrarse por
    su nombre nuevo."""
    p = product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500)
    product_service.editar(db, usuario.id, p.id, "Panela", 10, 2000, 1500)

    db.refresh(p)
    assert p.nombre_clave == "panela"
    assert product_service.buscar_por_codigo_barras(db, usuario.id, "x") is None
    from app.repositories import producto_repository
    assert producto_repository.obtener_por_nombre(db, usuario.id, "panela") is not None
    assert producto_repository.obtener_por_nombre(db, usuario.id, "arroz") is None


# --- Vender por nombre ----------------------------------------------------

def test_se_puede_vender_escribiendo_el_nombre_sin_tilde(db, usuario):
    """El asistente y la canasta resuelven productos por nombre. Si no
    tolerara la falta de tilde, el tendero no podría vender su propio
    producto."""
    from app.services import venta_service

    product_service.agregar(db, usuario.id, "Café", 10, 3000, 2000)
    venta = venta_service.vender(db, usuario.id, [{"nombre_producto": "cafe", "cantidad": 2}])
    assert venta.precio_venta_total == 6000


# --- El importador usa la MISMA regla ------------------------------------

@pytest.mark.parametrize("variante", ["Cafe", "CAFE", "CAFÉ", "café", "  Café  "])
def test_el_importador_reconoce_las_mismas_variantes(db, usuario, variante):
    """Antes el importador usaba .lower() a secas: trataba "Cafe" y "Café"
    como distintos mientras el formulario de alta los trataba igual. Dos
    reglas para lo mismo es garantía de que una se queda atrás."""
    product_service.agregar(db, usuario.id, "Café", 10, 3000, 2000)

    reporte = importacion_service.analizar(db, usuario.id, [
        FilaImportar(nombre=variante, cantidad=50, precio="3.500", cuanto_costo="2.500"),
    ])
    assert reporte["a_actualizar"] == 1
    assert reporte["a_crear"] == 0


def test_dos_filas_que_solo_difieren_en_tildes_son_duplicado(db, usuario):
    reporte = importacion_service.analizar(db, usuario.id, [
        FilaImportar(nombre="Café", cantidad=10, precio="3.000", cuanto_costo="2.000"),
        FilaImportar(nombre="cafe", cantidad=20, precio="3.000", cuanto_costo="2.000"),
    ])
    assert reporte["se_puede_importar"] is False
    assert "fila 2" in reporte["errores"][0]["problema"]


def test_las_categorias_tampoco_se_duplican_por_tildes(db, usuario):
    from app.services import categoria_service

    categoria_service.agregar(db, usuario.id, "Bebidas Frías")
    reporte = importacion_service.analizar(db, usuario.id, [
        FilaImportar(nombre="Gaseosa", cantidad=10, precio="2.000",
                     cuanto_costo="1.500", categoria="bebidas frias"),
    ])
    assert reporte["categorias_nuevas"] == []
