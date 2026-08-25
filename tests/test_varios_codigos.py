"""
Un producto con varios códigos de barras.

El caso real: una papelería vende cuadernos de cien hojas de tres marcas.
Mismo tamaño, mismo precio, mismo costo — para el tendero es UN producto, y
así lo cuenta y así se lo pide al proveedor. Pero cada marca trae su propio
EAN impreso de fábrica.

Antes había que elegir entre tres productos separados (el stock partido en
tres, el ranking fragmentado) o un solo código (las otras dos marcas no se
podían escanear).
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.services import canasta_service, product_service, venta_service

NORMA = "7702001111111"
SCRIBE = "7702002222222"
KIUT = "7702003333333"


@pytest.fixture
def cuaderno(db, usuario):
    """Un cuaderno con las tres marcas apuntando al mismo producto."""
    p = product_service.agregar(db, usuario.id, "Cuaderno 100 hojas", 30, 6500, 4800,
                                codigo_barras=NORMA)
    product_service.agregar_codigo_barras(db, usuario.id, p.id, SCRIBE)
    product_service.agregar_codigo_barras(db, usuario.id, p.id, KIUT)
    return p


# --- Lo que resuelve ------------------------------------------------------

def test_las_tres_marcas_son_un_solo_producto(db, usuario, cuaderno):
    assert len(product_service.listar(db, usuario.id)) == 1
    db.refresh(cuaderno)
    assert set(cuaderno.codigos_barras) == {NORMA, SCRIBE, KIUT}


@pytest.mark.parametrize("marca", [NORMA, SCRIBE, KIUT])
def test_cualquiera_de_las_tres_encuentra_el_producto(db, usuario, cuaderno, marca):
    encontrado = product_service.buscar_por_codigo_barras(db, usuario.id, marca)
    assert encontrado.id == cuaderno.id


@pytest.mark.parametrize("marca", [NORMA, SCRIBE, KIUT])
def test_se_vende_escaneando_cualquiera(db, usuario, cuaderno, marca):
    venta = venta_service.vender(db, usuario.id, [{"codigo_barras": marca, "cantidad": 1}])
    assert venta.precio_venta_total == 6500


def test_el_stock_es_uno_solo(db, usuario, cuaderno):
    """Lo que se perdía con tres productos separados: vender un Norma y un
    Scribe tiene que descontar dos del mismo montón."""
    venta_service.vender(db, usuario.id, [
        {"codigo_barras": NORMA, "cantidad": 1},
        {"codigo_barras": SCRIBE, "cantidad": 1},
    ])
    db.refresh(cuaderno)
    assert cuaderno.cantidad == 28


def test_el_ranking_no_se_fragmenta(db, usuario, cuaderno):
    """Con tres productos, el ranking mostraría tres líneas de 5 unidades en
    vez de una de 15, y el tendero no vería que es su producto estrella."""
    from app.services import analitica_service

    for marca in (NORMA, SCRIBE, KIUT):
        venta_service.vender(db, usuario.id, [{"codigo_barras": marca, "cantidad": 5}])

    ranking = analitica_service.mas_vendidos(db, usuario.id, 30, "unidades", 10)
    assert len(ranking) == 1
    assert ranking[0]["unidades"] == 15


def test_la_canasta_agrupa_las_marcas_en_una_linea(db, usuario, cuaderno):
    """Pasar tres marcas distintas por el lector tiene que dar "Cuaderno x3",
    no tres líneas — que es lo que espera cualquiera con un lector."""
    canasta = canasta_service.abrir(db, usuario.id)
    for marca in (NORMA, SCRIBE, KIUT):
        vista = canasta_service.agregar(db, canasta["id"], usuario.id, None,
                                        marca, None, None, 1)

    assert len(vista["items"]) == 1
    assert vista["items"][0]["cantidad"] == 3
    assert vista["total"] == 19500


# --- Agregar y quitar -----------------------------------------------------

def test_agregar_no_borra_los_que_ya_tenia(db, usuario, cuaderno):
    """La parte delicada: si esto reemplazara la lista, escanear la segunda
    marca borraría la primera."""
    db.refresh(cuaderno)
    assert len(cuaderno.codigos_barras) == 3


def test_agregar_el_mismo_dos_veces_no_hace_nada(db, usuario, cuaderno):
    """Escanear dos veces el mismo producto en la estantería no puede dar
    error ni duplicar."""
    product_service.agregar_codigo_barras(db, usuario.id, cuaderno.id, NORMA)

    db.refresh(cuaderno)
    assert len(cuaderno.codigos_barras) == 3


def test_se_quita_uno_solo_y_los_demas_quedan(db, usuario, cuaderno):
    """Cuando se pegó al producto equivocado."""
    product_service.quitar_codigo_barras(db, usuario.id, cuaderno.id, SCRIBE)

    db.refresh(cuaderno)
    assert set(cuaderno.codigos_barras) == {NORMA, KIUT}
    assert product_service.buscar_por_codigo_barras(db, usuario.id, SCRIBE) is None
    assert product_service.buscar_por_codigo_barras(db, usuario.id, NORMA) is not None


def test_con_none_se_quitan_todos(db, usuario, cuaderno):
    product_service.agregar_codigo_barras(db, usuario.id, cuaderno.id, None)

    db.refresh(cuaderno)
    assert cuaderno.codigos_barras == []
    assert cuaderno.codigo_barras is None


# --- Unicidad -------------------------------------------------------------

def test_un_codigo_no_puede_ser_de_dos_productos(db, usuario, cuaderno):
    """Si lo fuera, escanearlo sería ambiguo y la caja no sabría qué cobrar."""
    otro = product_service.agregar(db, usuario.id, "Lápiz Mirado", 50, 1200, 800)

    with pytest.raises(ErrorNegocio) as exc:
        product_service.agregar_codigo_barras(db, usuario.id, otro.id, NORMA)

    assert "Cuaderno 100 hojas" in str(exc.value)


def test_dos_negocios_pueden_usar_el_mismo_codigo(db, usuario, otro_usuario, cuaderno):
    """Dos papelerías venden el mismo cuaderno con el mismo EAN."""
    ajeno = product_service.agregar(db, otro_usuario.id, "Cuaderno", 10, 6000, 4000)
    product_service.agregar_codigo_barras(db, otro_usuario.id, ajeno.id, NORMA)

    assert product_service.buscar_por_codigo_barras(db, usuario.id, NORMA).id == cuaderno.id
    assert product_service.buscar_por_codigo_barras(db, otro_usuario.id, NORMA).id == ajeno.id


def test_borrar_el_producto_libera_sus_codigos(db, usuario, cuaderno):
    """El índice único viejo era parcial —solo entre productos vivos— así que
    borrar liberaba el código. Se conserva ese comportamiento: si no, un
    código quedaría atrapado para siempre por un producto que nadie ve."""
    product_service.eliminar(db, usuario.id, cuaderno.id)

    nuevo = product_service.agregar(db, usuario.id, "Cuaderno nuevo", 10, 7000, 5000,
                                    codigo_barras=NORMA)
    assert nuevo.codigo_barras == NORMA


# --- Compatibilidad con lo que ya existe ---------------------------------

def test_codigo_barras_sigue_devolviendo_el_primero(db, usuario, cuaderno):
    """Para que las pantallas que esperan un solo código no se rompan."""
    db.refresh(cuaderno)
    assert cuaderno.codigo_barras == NORMA


def test_editar_el_producto_no_borra_las_otras_marcas(db, usuario, cuaderno):
    """El caso que más daño haría: el formulario de editar manda UN código,
    y si eso reemplazara la lista, cambiarle el precio a un producto le
    borraría dos marcas sin que nadie se entere."""
    product_service.editar(db, usuario.id, cuaderno.id, "Cuaderno 100 hojas",
                           30, 7000, 4800, codigo_barras=NORMA)

    db.refresh(cuaderno)
    assert set(cuaderno.codigos_barras) == {NORMA, SCRIBE, KIUT}
    assert cuaderno.precio == 7000


def test_editar_sin_codigo_no_toca_nada(db, usuario, cuaderno):
    """None significa "no toco los códigos", no "quítaselos todos": un campo
    de un solo valor no puede expresar la diferencia."""
    product_service.editar(db, usuario.id, cuaderno.id, "Cuaderno 100 hojas",
                           30, 7000, 4800, codigo_barras=None)

    db.refresh(cuaderno)
    assert len(cuaderno.codigos_barras) == 3


def test_el_filtro_sin_codigo_ve_los_que_no_tienen_ninguno(db, usuario, cuaderno):
    product_service.agregar(db, usuario.id, "Panela", 10, 3000, 2000)

    sin_codigo = product_service.listar(db, usuario.id, sin_codigo=True)
    assert [p.nombre for p in sin_codigo] == ["Panela"]


def test_se_busca_por_cualquiera_de_sus_codigos(db, usuario, cuaderno):
    """El buscador del inventario acepta que el tendero teclee o escanee
    cualquiera de las marcas."""
    assert len(product_service.listar(db, usuario.id, q=SCRIBE)) == 1
    assert len(product_service.listar(db, usuario.id, q=KIUT)) == 1


def test_el_upc_de_12_digitos_se_normaliza_igual(db, usuario, cuaderno):
    product_service.agregar_codigo_barras(db, usuario.id, cuaderno.id, "012345678905")

    db.refresh(cuaderno)
    assert "0012345678905" in cuaderno.codigos_barras
    # Y se encuentra escaneando cualquiera de las dos formas.
    assert product_service.buscar_por_codigo_barras(db, usuario.id, "012345678905") is not None
