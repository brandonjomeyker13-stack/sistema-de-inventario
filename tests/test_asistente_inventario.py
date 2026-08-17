"""
Lo que el asistente sabe del inventario.

El asistente no consulta la base: solo ve lo que va en el contexto. Así que
"puede responder preguntas de inventario" se traduce en una cosa concreta y
comprobable — que el dato esté en el contexto.

El caso que lo motivó: después de importar la plantilla NINGÚN producto tiene
código de barras, y el tendero necesita poder preguntar "¿cuántos me faltan
por escanear?".
"""

import pytest

from app.services import asistente_service, product_service
from app.services.asistente_service import contexto as ctx
from app.services.asistente_service.instrucciones import INSTRUCCIONES


def _ctx(db, usuario, pregunta="cómo va el inventario"):
    return asistente_service.construir_contexto(db, usuario.id, pregunta)["inventario"]


# --- Lo que faltaba: los que no tienen código ----------------------------

def test_sabe_cuantos_productos_no_tienen_codigo(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500,
                            codigo_barras="7702001234567")
    product_service.agregar(db, usuario.id, "Panela", 5, 3000, 2000)
    product_service.agregar(db, usuario.id, "Frijol", 8, 4000, 3000)

    inventario = _ctx(db, usuario)
    assert inventario["sin_codigo_de_barras"]["cuantos"] == 2
    assert set(inventario["sin_codigo_de_barras"]["algunos"]) == {"Panela", "Frijol"}


def test_da_la_cuenta_exacta_pero_solo_unos_nombres(db, usuario):
    """Trescientos nombres reventarían el contexto. La cuenta es lo que
    responde la pregunta; los nombres solo hacen la respuesta concreta."""
    for n in range(20):
        product_service.agregar(db, usuario.id, f"Producto {n}", 5, 2000, 1500)

    grupo = _ctx(db, usuario)["sin_codigo_de_barras"]
    assert grupo["cuantos"] == 20                       # exacta
    assert len(grupo["algunos"]) == ctx.MAX_EJEMPLOS    # una muestra
    assert grupo["hay_mas"] is True


def test_hay_mas_es_falso_cuando_caben_todos(db, usuario):
    """El modelo lo usa para saber si puede listarlos todos o si tiene que
    mandar al tendero a la pantalla de inventario."""
    product_service.agregar(db, usuario.id, "Panela", 5, 3000, 2000)

    grupo = _ctx(db, usuario)["sin_codigo_de_barras"]
    assert grupo["cuantos"] == 1
    assert grupo["hay_mas"] is False


def test_las_instrucciones_le_prohiben_hacer_pasar_la_muestra_por_el_total():
    """Sin esto el modelo diría "te faltan estos ocho" cuando son
    trescientos, y el tendero creería que ya casi termina."""
    assert "Nunca insinúes que los nombres que tienes son" in INSTRUCCIONES


# --- Los otros grupos ----------------------------------------------------

def test_sabe_cuantos_estan_agotados(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 0, 2000, 1500)
    product_service.agregar(db, usuario.id, "Panela", 5, 3000, 2000)

    assert _ctx(db, usuario)["agotados"]["cuantos"] == 1
    assert _ctx(db, usuario)["agotados"]["algunos"] == ["Arroz"]


def test_sabe_cuantos_no_tienen_categoria(db, usuario):
    from app.services import categoria_service

    categoria = categoria_service.agregar(db, usuario.id, "Granos")
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500,
                            categoria_id=categoria.id)
    product_service.agregar(db, usuario.id, "Panela", 5, 3000, 2000)

    assert _ctx(db, usuario)["sin_categoria"]["cuantos"] == 1


def test_sabe_cuantos_productos_hay_en_total(db, usuario):
    for n in range(4):
        product_service.agregar(db, usuario.id, f"Producto {n}", 5, 2000, 1500)

    assert _ctx(db, usuario)["cuantos_productos"] == 4


def test_sabe_cuantos_son_servicios(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500)
    product_service.agregar(db, usuario.id, "Fotocopia", 0, 200, 50, controla_stock=False)
    product_service.agregar(db, usuario.id, "Plastificado", 0, 3000, 500,
                            controla_stock=False)

    assert _ctx(db, usuario)["cuantos_servicios"] == 2


# --- El valor del inventario ---------------------------------------------

def test_sabe_cuanto_vale_el_inventario(db, usuario):
    """Al costo es lo que tiene invertido; al precio de venta es lo que
    valdría si lo vendiera todo. El tendero pregunta las dos cosas."""
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500)
    product_service.agregar(db, usuario.id, "Panela", 5, 4000, 3000)

    inventario = _ctx(db, usuario)
    assert inventario["valor_al_costo"] == 30000          # 10x1500 + 5x3000
    assert inventario["valor_al_precio_de_venta"] == 40000  # 10x2000 + 5x4000


def test_los_servicios_no_suman_al_valor_del_inventario(db, usuario):
    """Una fotocopia que todavía no se ha hecho no es plata invertida."""
    product_service.agregar(db, usuario.id, "Fotocopia", 0, 200, 50, controla_stock=False)
    assert _ctx(db, usuario)["valor_al_costo"] == 0


# --- Aislamiento ---------------------------------------------------------

def test_no_cuenta_los_productos_de_otro_negocio(db, usuario, otro_usuario):
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500)
    for n in range(5):
        product_service.agregar(db, otro_usuario.id, f"Ajeno {n}", 5, 2000, 1500)

    assert _ctx(db, usuario)["cuantos_productos"] == 1


# --- El filtro que hace la respuesta accionable --------------------------

def test_el_inventario_se_puede_filtrar_por_los_que_faltan_codigo(db, usuario):
    """El asistente dice cuántos son y manda a esta pantalla. Sin el filtro,
    su respuesta sería un dato sin nada que hacer con él."""
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500,
                            codigo_barras="7702001234567")
    product_service.agregar(db, usuario.id, "Panela", 5, 3000, 2000)

    sin_codigo = product_service.listar(db, usuario.id, sin_codigo=True)
    assert [p.nombre for p in sin_codigo] == ["Panela"]
    assert product_service.contar(db, usuario.id, sin_codigo=True) == 1

    # Y sin el filtro siguen saliendo los dos.
    assert len(product_service.listar(db, usuario.id)) == 2


# --- La estructura del paquete -------------------------------------------

def test_el_prompt_no_contiene_datos_del_negocio():
    """La frontera que hay que mantener: instrucciones.py dice CÓMO
    responder, contexto.py dice QUÉ. Si algún día hace falta escribir un
    precio o un nombre de producto en el prompt, es que falta un campo en
    el contexto.

    Se comprueba con nombres de producto y no con el signo de peso: el
    prompt sí lleva "$4.000" y "$Y" como ejemplos de FORMATO, que es
    justamente el tipo de cosa que le toca decir a este archivo.
    """
    for nombre_real in ("Arroz", "Panela", "Fotocopia", "Cuaderno", "Gaseosa"):
        assert nombre_real not in INSTRUCCIONES

    # Y no debe hablar de la base de datos: el modelo nunca la toca, solo ve
    # el contexto. Se buscan términos que no pueden aparecer en prosa
    # española por casualidad — "productos." sí puede, y de hecho aparece en
    # la frase "nombres de productos.".
    for filtracion in ("SELECT", "usuario_id", "SQL", "tabla"):
        assert filtracion not in INSTRUCCIONES


def test_los_imports_de_siempre_siguen_funcionando():
    """El paquete conserva la cara pública del módulo que reemplazó, para
    que partir el archivo no obligue a tocar a quien lo usa."""
    from app.services import asistente_service as modulo

    assert callable(modulo.preguntar)
    assert callable(modulo.construir_contexto)
    assert modulo.INSTRUCCIONES
    assert modulo.ACCIONES_PERMITIDAS == ("crear_producto", "registrar_entrada")
