"""
El enrutador: responder sin llamar al modelo.

Las pruebas están partidas en cuatro, y el orden es el de la importancia:

  1. Cuándo se APARTA. Es lo que más se prueba, porque el fallo caro no es
     dejar pasar una pregunta al modelo —eso cuesta lo de siempre— sino
     responder con seguridad algo que no era lo que preguntaron.
  2. Qué responde cuando sí reconoce.
  3. Que un negocio no vea nunca lo de otro.
  4. Que de verdad no llame al modelo, que es el punto de todo esto.
"""

import pytest

from app.core.exceptions import ErrorNegocio
from app.services import (
    analitica_service, asistente_service, enrutador_service,
    product_service, venta_service,
)
from app.services.enrutador_service import redaccion
from app.services.enrutador_service.intenciones import clasificar


# --- 1. Cuándo se aparta -------------------------------------------------

@pytest.mark.parametrize("pregunta, intencion", [
    ("¿qué tengo que comprar?", "lista_de_compra"),
    ("hazme el pedido del proveedor", "lista_de_compra"),
    ("¿qué se está acabando?", "lista_de_compra"),
    ("¿cuánto vendí hoy?", "ventas_de_hoy"),
    ("¿cuánto gané hoy?", "ganancia_de_hoy"),
    ("¿quién me debe?", "fiados"),
    ("¿cuántos productos están sin código?", "sin_codigo"),
    ("¿qué tengo agotado?", "agotados"),
    ("¿cuánto vale mi inventario?", "valor_inventario"),
])
def test_reconoce_las_preguntas_frecuentes(pregunta, intencion):
    assert clasificar(pregunta) == intencion


def test_las_tildes_y_las_mayusculas_no_importan():
    """El tendero escribe desde el celular y muchas veces por voz."""
    assert clasificar("¿CUÁNTO GANÉ HOY?") == "ganancia_de_hoy"
    assert clasificar("cuanto gane hoy") == "ganancia_de_hoy"


def test_no_responde_lo_que_no_reconoce():
    """None no es un fallo: es el camino normal. Responde el modelo."""
    assert clasificar("¿me conviene vender cuadernos por docena?") is None
    assert clasificar("¿y ayer?") is None
    assert clasificar("") is None


def test_no_responde_si_le_piden_hacer_algo():
    """Crear o registrar es del modelo, que lo devuelve como PROPUESTA para
    que el tendero confirme. Un atajo que contestara con una cuenta a un
    "créame un producto" sería peor que no contestar."""
    assert clasificar("créame un producto que se llama Cuaderno") is None
    assert clasificar("agrégame 10 cuadernos al inventario") is None
    assert clasificar("me llegaron 20 borradores, regístralos") is None


def test_no_responde_si_la_pregunta_cabe_en_dos_intenciones():
    """Ante la duda, el modelo. Perder una coincidencia cuesta una llamada;
    acertar de más cuesta una respuesta equivocada dicha con seguridad."""
    # "agotado" apunta a los agotados y "comprar" a la lista de compra.
    assert clasificar("¿cuántos productos agotados tengo que comprar?") is None


def test_los_disparadores_son_palabras_completas():
    """Con un `in` a secas, 'pedir' coincidiría dentro de 'impedir'."""
    assert clasificar("¿algo puede impedir que registre la venta?") is None


# --- 2. Qué responde -----------------------------------------------------

def _resolver(db, usuario, pregunta):
    return enrutador_service.resolver(db, usuario.id, pregunta)


def test_la_lista_de_compra_sale_identica_a_la_de_la_pantalla(db, usuario):
    """LA RAZÓN DE SER DEL ENRUTADOR.

    Hoy el prompt le RUEGA al modelo que copie la lista sin cambiarle una
    palabra, para que coincida con la que el tendero ve en inventario. Si no
    coinciden, deja de confiar en las dos. Pedir no es garantizar; salir del
    mismo sitio, sí.
    """
    product_service.agregar(db, usuario.id, "Cuaderno", 0, 3000, 2000)
    product_service.agregar(db, usuario.id, "Lápiz", 0, 1000, 600)

    esperado = analitica_service.que_comprar(db, usuario.id)["texto"]
    respuesta = _resolver(db, usuario, "¿qué tengo que comprar?")["respuesta"]

    assert esperado in respuesta


def test_cuenta_los_que_no_tienen_codigo_y_dice_para_que_sirve(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 10, 2000, 1500,
                            codigo_barras="7702001234567")
    product_service.agregar(db, usuario.id, "Panela", 5, 3000, 2000)

    respuesta = _resolver(db, usuario, "¿cuántos productos están sin código?")["respuesta"]

    assert "1 producto sin código de barras" in respuesta
    assert "Panela" in respuesta
    # La cuenta sola es un dato suelto; con el para qué es una tarea.
    assert "cámara del celular" in respuesta


def test_los_servicios_nunca_salen_como_agotados(db, usuario):
    """Una fotocopiadora no lleva inventario. Contarla como agotada sería
    una alarma falsa todos los días."""
    product_service.agregar(db, usuario.id, "Fotocopia", 0, 200, 50,
                            controla_stock=False)
    product_service.agregar(db, usuario.id, "Cuaderno", 0, 3000, 2000)

    respuesta = _resolver(db, usuario, "¿qué tengo agotado?")["respuesta"]

    assert "Cuaderno" in respuesta
    assert "Fotocopia" not in respuesta


def test_separa_lo_invertido_de_lo_que_valdria_vendido(db, usuario):
    """Son dos números distintos y confundirlos le cambia al tendero la idea
    de cuánto vale su negocio."""
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 3000, 2000)

    respuesta = _resolver(db, usuario, "¿cuánto vale mi inventario?")["respuesta"]

    assert "$20.000" in respuesta   # al costo
    assert "$30.000" in respuesta   # a precio de venta


def test_la_ganancia_va_primero_cuando_preguntan_por_la_ganancia(db, usuario):
    """Quien pregunta cuánto ganó no está preguntando cuánto vendió. Darle
    el número grande de las ventas es justo la confusión que el producto
    vino a quitar."""
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 3000, 2000)
    venta_service.vender(db, usuario.id, [{"nombre_producto": "Cuaderno", "cantidad": 2}])

    respuesta = _resolver(db, usuario, "¿cuánto gané hoy?")["respuesta"]

    assert respuesta.index("$2.000") < respuesta.index("$6.000")


def test_los_casos_vacios_suenan_a_respuesta_y_no_a_error(db, usuario):
    """Una cuenta recién creada está en cero en todo, y es justo cuando el
    tendero está decidiendo si esto le sirve."""
    assert "no te falta nada" in _resolver(db, usuario, "¿qué compro?")["respuesta"]
    assert "no te debe nadie" in _resolver(db, usuario, "¿quién me debe?")["respuesta"].lower()
    assert "ninguna venta" in _resolver(db, usuario, "¿cuánto vendí hoy?")["respuesta"]


def test_nunca_hace_pasar_la_muestra_por_el_total(db, usuario):
    """Con veinte agotados, decir 'tienes estos ocho' sería mentir."""
    for n in range(20):
        product_service.agregar(db, usuario.id, f"Producto {n}", 0, 2000, 1500)

    respuesta = _resolver(db, usuario, "¿qué tengo agotado?")["respuesta"]

    assert "20 productos agotados" in respuesta
    assert "Algunos:" in respuesta
    assert "filtrando por agotados" in respuesta


def test_los_pesos_se_escriben_como_en_colombia():
    assert redaccion.pesos(4000) == "$4.000"
    assert redaccion.pesos(1500000) == "$1.500.000"
    assert redaccion.pesos(0) == "$0"


# --- 3. Un negocio no ve lo de otro --------------------------------------

def test_cada_negocio_solo_ve_lo_suyo(db, usuario, otro_usuario):
    """El enrutador responde más rápido, pero por el mismo camino: el
    usuario sale del token, nunca de la pregunta."""
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 3000, 2000)
    product_service.agregar(db, otro_usuario.id, "Machete", 5, 20000, 15000)

    mia = _resolver(db, usuario, "¿cuánto vale mi inventario?")["respuesta"]

    assert "Cuaderno" not in mia or "Machete" not in mia
    assert "$20.000" in mia          # 10 x 2000, lo mío
    assert "$75.000" not in mia      # 5 x 15000, lo del otro


# --- 4. Que de verdad no llame al modelo ---------------------------------

def test_no_llama_al_modelo_cuando_reconoce_la_pregunta(db, usuario):
    """La prueba de que el ahorro es real.

    Las pruebas corren SIN clave de Groq (ver conftest), así que llamar al
    modelo levanta AsistenteNoConfigurado. Que esto devuelva una respuesta
    normal solo puede significar que no lo llamó.
    """
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 3000, 2000)

    salida = asistente_service.preguntar(db, usuario.id, "¿cuánto vale mi inventario?")

    assert "$20.000" in salida["respuesta"]
    # El enrutador nunca propone acciones: eso sigue siendo del modelo.
    assert salida["accion"] is None


def test_lo_que_no_reconoce_sigue_yendo_al_modelo(db, usuario):
    """La contraprueba de la anterior: si el enrutador se tragara todo,
    la de arriba pasaría igual y no probaría nada."""
    with pytest.raises(ErrorNegocio):
        asistente_service.preguntar(db, usuario.id, "¿me conviene vender por docena?")


def test_toda_intencion_tiene_sus_dos_funciones():
    """Añadir un nombre al catálogo y olvidar la función de datos o la de
    redacción es un error de programación. Revienta al importar el módulo,
    no en la cara del primero que pregunte."""
    from app.services.enrutador_service.intenciones import NOMBRES

    assert set(enrutador_service.INTENCIONES_RESUELTAS) == set(NOMBRES)
