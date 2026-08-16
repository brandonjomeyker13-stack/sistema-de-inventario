"""
Importar el inventario desde una plantilla.

Es la función que decide si un cliente se queda: teclear a mano los
cientos de productos de una tienda es la razón número uno por la que estas
aplicaciones se abandonan en la primera semana.

Y es también la más peligrosa, porque escribe en masa. Estas pruebas
cubren cada forma en que puede corromper el inventario.
"""

import pytest

from app.core.exceptions import ErrorNegocio
from app.models.movimiento import AJUSTE, MovimientoInventario
from app.schemas.importacion import FilaImportar
from app.services import importacion_service, product_service


def fila(nombre, cantidad=10, precio="1.500", costo="1.000", categoria=None, servicio=None):
    return FilaImportar(nombre=nombre, cantidad=cantidad, precio=precio,
                        cuanto_costo=costo, categoria=categoria, es_servicio=servicio)


# --- La vista previa no toca nada ----------------------------------------

def test_previsualizar_no_guarda_nada(db, usuario):
    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz"), fila("Aceite")])

    assert reporte["a_crear"] == 2
    assert reporte["se_puede_importar"] is True
    assert product_service.listar(db, usuario.id) == []      # nada guardado


def test_la_vista_previa_dice_el_numero_de_fila_de_excel(db, usuario):
    """+2 porque la fila 1 es el encabezado y Excel cuenta desde 1. Si
    diéramos un índice interno, el tendero tendría que contar filas a mano
    para encontrar el error."""
    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz"), fila("")])

    assert reporte["crear"][0]["fila"] == 2
    assert reporte["errores"][0]["fila"] == 3


# --- El formato de los números -------------------------------------------

def test_los_precios_colombianos_se_leen_bien(db, usuario):
    """El fallo que arruinaría una tienda: "1.500" son mil quinientos."""
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Arroz", precio="1.500", costo="1.000")],
    )
    creado = reporte["crear"][0]
    assert creado["precio"] == 1500
    assert creado["cuanto_costo"] == 1000


def test_acepta_el_simbolo_de_peso(db, usuario):
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Arroz", precio="$3.000", costo="$2.500")],
    )
    assert reporte["crear"][0]["precio"] == 3000


def test_una_cantidad_con_decimales_se_rechaza(db, usuario):
    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz", cantidad="10,5")])
    assert reporte["con_error"] == 1
    assert "entero" in reporte["errores"][0]["problema"]


# --- Todo o nada ---------------------------------------------------------

def test_una_sola_fila_mala_impide_importar_todo(db, usuario):
    """Una carga a medias deja al tendero sin saber qué entró, y al
    reintentar duplica lo que ya estaba."""
    filas = [fila("Arroz"), fila("Aceite"), fila("", cantidad=5)]

    reporte = importacion_service.analizar(db, usuario.id, filas)
    assert reporte["se_puede_importar"] is False

    with pytest.raises(ErrorNegocio):
        importacion_service.importar(db, usuario.id, filas)

    assert product_service.listar(db, usuario.id) == []      # ni el arroz entró


def test_el_error_dice_la_fila_y_el_motivo(db, usuario):
    with pytest.raises(ErrorNegocio) as exc:
        importacion_service.importar(db, usuario.id, [fila("Arroz"), fila("")])
    assert "fila 3" in str(exc.value)


# --- Crear y actualizar --------------------------------------------------

def test_importar_crea_los_productos(db, usuario):
    resultado = importacion_service.importar(
        db, usuario.id, [fila("Arroz"), fila("Aceite", precio="8.000", costo="6.000")],
    )

    assert resultado["creados"] == 2
    productos = {p.nombre: p for p in product_service.listar(db, usuario.id)}
    assert productos["Arroz"].precio == 1500
    assert productos["Aceite"].precio == 8000


def test_un_producto_que_ya_existe_se_actualiza(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 5, 1000, 800)

    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Arroz", cantidad=50, precio="2.000", costo="1.500")],
    )
    assert reporte["a_crear"] == 0
    assert reporte["a_actualizar"] == 1

    importacion_service.importar(
        db, usuario.id, [fila("Arroz", cantidad=50, precio="2.000", costo="1.500")],
    )

    p = product_service.listar(db, usuario.id)[0]
    assert (p.cantidad, p.precio, p.cuanto_costo) == (50, 2000, 1500)


def test_la_vista_previa_muestra_el_valor_de_antes(db, usuario):
    """Para que el tendero pueda frenar si ve que le van a bajar el precio
    del arroz a la mitad. Un "12 productos actualizados" no se lo dice."""
    product_service.agregar(db, usuario.id, "Arroz", 5, 3000, 2000)

    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Arroz", cantidad=50, precio="1.500", costo="1.000")],
    )
    cambio = reporte["actualizar"][0]
    assert cambio["precio_antes"] == 3000
    assert cambio["precio_despues"] == 1500
    assert cambio["cantidad_antes"] == 5
    assert cambio["cantidad_despues"] == 50


def test_el_nombre_no_distingue_mayusculas(db, usuario):
    """"ARROZ" en la plantilla y "Arroz" en el sistema son el mismo
    producto. Si no, la importación crearía un duplicado."""
    product_service.agregar(db, usuario.id, "Arroz", 5, 1000, 800)

    reporte = importacion_service.analizar(db, usuario.id, [fila("ARROZ")])
    assert reporte["a_actualizar"] == 1
    assert reporte["a_crear"] == 0


def test_actualizar_NO_borra_el_codigo_de_barras(db, usuario):
    """La plantilla no trae códigos, y el tendero ya se los fue poniendo
    escaneando. Pisarlos con None borraría ese trabajo en silencio."""
    product_service.agregar(db, usuario.id, "Arroz", 5, 1000, 800,
                            codigo_barras="7702001234567")

    importacion_service.importar(db, usuario.id, [fila("Arroz", cantidad=50)])

    p = product_service.listar(db, usuario.id)[0]
    assert p.codigo_barras == "7702001234567"
    assert p.cantidad == 50


def test_actualizar_deja_rastro_en_el_libro(db, usuario):
    """Una importación que mueve existencias sin anotarlo descuadra el
    libro de inventario."""
    product_service.agregar(db, usuario.id, "Arroz", 5, 1000, 800)
    importacion_service.importar(db, usuario.id, [fila("Arroz", cantidad=50)])

    mov = db.query(MovimientoInventario).filter(MovimientoInventario.tipo == AJUSTE).one()
    assert mov.cantidad == 45              # de 5 a 50
    assert mov.stock_antes == 5
    assert mov.stock_despues == 50


# --- Duplicados dentro del archivo ---------------------------------------

def test_el_mismo_nombre_dos_veces_en_el_archivo_es_error(db, usuario):
    """No se puede adivinar cuál gana, y aplicar las dos dejaría el stock
    de la última en vez de la suma."""
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Arroz", cantidad=10), fila("Arroz", cantidad=20)],
    )
    assert reporte["se_puede_importar"] is False
    assert "fila 2" in reporte["errores"][0]["problema"]


def test_los_espacios_dobles_cuentan_como_el_mismo_nombre(db, usuario):
    """"Cuaderno  amarillo" con doble espacio se ve idéntico en pantalla."""
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Cuaderno amarillo"), fila("Cuaderno  amarillo")],
    )
    assert reporte["se_puede_importar"] is False


# --- Precio por debajo del costo -----------------------------------------

def test_precio_bajo_el_costo_se_rechaza_por_defecto(db, usuario):
    """La misma regla que al crear a mano. Si el importador fuera más
    permisivo, la plantilla sería la puerta de atrás para meter datos que
    el formulario rechaza."""
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Lápices", precio="5.000", costo="6.000")],
    )
    assert reporte["se_puede_importar"] is False
    assert "casilla del precio" in reporte["errores"][0]["problema"]


def test_con_confirmacion_pasa_y_queda_avisado(db, usuario):
    """Una liquidación es legítima, pero tiene que salir en los avisos para
    que el tendero la vea antes de confirmar."""
    filas = [fila("Yogur por vencer", precio="1.500", costo="2.500")]

    reporte = importacion_service.analizar(db, usuario.id, filas, permitir_perdida=True)
    assert reporte["se_puede_importar"] is True
    assert any("pierde" in a["aviso"] for a in reporte["avisos"])

    importacion_service.importar(db, usuario.id, filas, permitir_perdida=True)
    assert product_service.listar(db, usuario.id)[0].precio == 1500


# --- Categorías ----------------------------------------------------------

def test_sin_categoria_se_avisa(db, usuario):
    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz")])
    assert any("sin categoría" in a["aviso"] for a in reporte["avisos"])
    assert reporte["se_puede_importar"] is True


def test_una_categoria_nueva_se_anuncia_y_se_crea(db, usuario):
    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz", categoria="Granos")])
    assert reporte["categorias_nuevas"] == ["Granos"]

    resultado = importacion_service.importar(db, usuario.id, [fila("Arroz", categoria="Granos")])
    assert resultado["categorias_creadas"] == ["Granos"]

    from app.repositories import categoria_repository
    assert [c.nombre for c in categoria_repository.listar(db, usuario.id)] == ["Granos"]


def test_una_categoria_repetida_se_crea_una_sola_vez(db, usuario):
    filas = [fila("Arroz", categoria="Granos"), fila("Frijol", categoria="Granos")]
    reporte = importacion_service.analizar(db, usuario.id, filas)
    assert reporte["categorias_nuevas"] == ["Granos"]


def test_una_categoria_que_ya_existe_no_se_duplica(db, usuario):
    from app.services import categoria_service
    categoria_service.agregar(db, usuario.id, "Granos")

    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz", categoria="Granos")])
    assert reporte["categorias_nuevas"] == []


# --- Servicios -----------------------------------------------------------

def test_se_puede_importar_un_servicio(db, usuario):
    importacion_service.importar(
        db, usuario.id,
        [fila("Fotocopia", cantidad=0, precio="200", costo="50", servicio="si")],
    )
    p = product_service.listar(db, usuario.id)[0]
    assert p.controla_stock is False


def test_un_servicio_ignora_la_cantidad_de_la_plantilla(db, usuario):
    """Poner un número ahí es un malentendido, no un error que valga la
    pena frenar."""
    importacion_service.importar(
        db, usuario.id,
        [fila("Fotocopia", cantidad=999, precio="200", costo="50", servicio="si")],
    )
    assert product_service.listar(db, usuario.id)[0].cantidad == 0


@pytest.mark.parametrize("si", ["si", "sí", "SI", "x", "1", "true", "Verdadero"])
def test_la_columna_de_servicio_acepta_varias_formas(db, usuario, si):
    """La plantilla la llena gente distinta y cada uno escribe lo que le
    parece."""
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Fotocopia", precio="200", costo="50", servicio=si)],
    )
    assert reporte["crear"][0]["es_servicio"] is True


def test_la_columna_de_servicio_rechaza_lo_que_no_entiende(db, usuario):
    reporte = importacion_service.analizar(
        db, usuario.id, [fila("Fotocopia", servicio="tal vez")],
    )
    assert reporte["se_puede_importar"] is False


# --- Aislamiento entre negocios ------------------------------------------

def test_la_importacion_no_ve_los_productos_de_otro_negocio(db, usuario, otro_usuario):
    """Si los viera, importar "Arroz" actualizaría el del vecino en vez de
    crear el propio."""
    product_service.agregar(db, otro_usuario.id, "Arroz", 5, 1000, 800)

    reporte = importacion_service.analizar(db, usuario.id, [fila("Arroz")])
    assert reporte["a_crear"] == 1
    assert reporte["a_actualizar"] == 0
