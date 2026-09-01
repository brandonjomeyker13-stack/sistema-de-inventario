"""
Guardar qué le pregunta la gente a Trackie.

Sirve para dos cosas y las pruebas siguen ese orden: saber hoy qué se
pregunta, y tener mañana con qué entrenar. Lo segundo es lo que obliga a
guardar la etiqueta —qué intención era de verdad— y no solo la pregunta.

Las últimas son las que protegen la privacidad, y son estructurales a
propósito: comprueban que la tabla NO tenga dónde guardar de quién es cada
pregunta ni qué se le respondió.
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.models.consulta import ConsultaRegistrada, DESCARTADA, ETIQUETADA, PENDIENTE
from app.repositories import consulta_repository
from app.services import asistente_service, consulta_service, product_service


@pytest.fixture
def admin(db, usuario):
    usuario.es_admin = True
    db.commit()
    return usuario


def _filas(db):
    return db.query(ConsultaRegistrada).all()


# --- Registrar -----------------------------------------------------------

def test_anota_la_pregunta_con_la_intencion_que_se_reconocio(db):
    consulta_service.registrar(db, "¿Qué tengo que comprar?", "lista_de_compra")

    fila = _filas(db)[0]
    assert fila.pregunta == "¿Qué tengo que comprar?"   # tal como la escribió
    assert fila.veces == 1
    assert fila.intencion_detectada == "lista_de_compra"
    assert fila.estado == PENDIENTE


def test_la_misma_pregunta_escrita_distinto_es_una_sola_fila(db):
    """Es lo que convierte el panel en una lista de trabajo en vez de un
    registro interminable: la clave normalizada agrupa las variantes."""
    consulta_service.registrar(db, "¿Cuánto vendí hoy?", "ventas_de_hoy")
    consulta_service.registrar(db, "cuanto vendi hoy", "ventas_de_hoy")
    consulta_service.registrar(db, "  CUANTO   VENDI HOY  ", "ventas_de_hoy")

    filas = _filas(db)
    assert len(filas) == 1
    assert filas[0].veces == 3


def test_lo_que_el_enrutador_no_supo_queda_marcado(db):
    """Son las filas que más valen: cada una es una pregunta que hoy cuesta
    tokens y hace esperar al tendero."""
    consulta_service.registrar(db, "¿me conviene vender por docena?", None)

    assert _filas(db)[0].intencion_detectada is None
    assert consulta_repository.resumen(db)["sin_reconocer"] == 1


def test_no_guarda_pegados_de_media_pantalla(db):
    """Un texto larguísimo no es una pregunta frecuente: nadie lo va a
    repetir palabra por palabra, y solo llenaría el panel de filas con
    veces=1."""
    consulta_service.registrar(db, "a" * 500, None)
    assert _filas(db) == []


def test_registrar_nunca_tumba_la_respuesta(db):
    """Se llama en cada pregunta. Una estadística que falla no puede dejar
    al tendero sin respuesta, así que esta es la única función del proyecto
    que se traga una excepción a propósito."""
    consulta_service.registrar(db, "", None)          # sin texto
    consulta_service.registrar(db, None, None)        # ni siquiera un str
    assert _filas(db) == []


# --- Etiquetar, que es de lo que sale el entrenamiento -------------------

def test_etiquetar_deja_el_ejemplo_listo(db, admin):
    consulta_service.registrar(db, "¿qué me falta?", None)
    consulta = _filas(db)[0]

    resultado = consulta_service.etiquetar(db, admin, consulta.id, "lista_de_compra")

    assert resultado.intencion_correcta == "lista_de_compra"
    assert resultado.estado == ETIQUETADA
    assert resultado.revisada_por == admin.id


def test_solo_se_puede_etiquetar_con_intenciones_del_catalogo(db, admin):
    """Con etiquetas libres el conjunto acabaría con 'compras', 'compra' y
    'lista_compra' como tres cosas distintas, y eso no se arregla después."""
    consulta_service.registrar(db, "¿qué me falta?", None)
    consulta = _filas(db)[0]

    with pytest.raises(ErrorNegocio):
        consulta_service.etiquetar(db, admin, consulta.id, "cosas_de_compras")


def test_ninguna_es_una_etiqueta_valida(db, admin):
    """Un clasificador también tiene que aprender a NO clasificar, y para eso
    necesita ejemplos de preguntas que no son de ninguna intención."""
    consulta_service.registrar(db, "¿cómo estás?", None)
    consulta = _filas(db)[0]

    resultado = consulta_service.etiquetar(db, admin, consulta.id, "ninguna")
    assert resultado.intencion_correcta == "ninguna"
    assert resultado.estado == ETIQUETADA


def test_descartar_no_borra(db, admin):
    """Borrada, la siguiente vez que alguien la escribiera volvería a la
    bandeja y habría que descartarla otra vez."""
    consulta_service.registrar(db, "asdfgh", None)
    consulta = _filas(db)[0]

    consulta_service.descartar(db, admin, consulta.id)

    assert len(_filas(db)) == 1
    assert _filas(db)[0].estado == DESCARTADA


def test_se_puede_deshacer_una_etiqueta_mal_puesta(db, admin):
    consulta_service.registrar(db, "¿qué me falta?", None)
    consulta = _filas(db)[0]
    consulta_service.etiquetar(db, admin, consulta.id, "fiados")

    resultado = consulta_service.reabrir(db, admin, consulta.id)

    assert resultado.estado == PENDIENTE
    assert resultado.intencion_correcta is None


def test_etiquetar_algo_que_no_existe_da_no_encontrado(db, admin):
    with pytest.raises(NoEncontrado):
        consulta_service.etiquetar(db, admin, "no-existe", "fiados")


def test_el_recuento_de_etiquetas_muestra_el_desbalance(db, admin):
    """Mil ejemplos de una intención y tres de otra no entrenan nada, y eso
    solo se ve mirándolos juntos."""
    for texto in ("¿qué compro?", "¿qué me falta?", "¿qué pido?"):
        consulta_service.registrar(db, texto, None)
    for consulta in _filas(db):
        consulta_service.etiquetar(db, admin, consulta.id, "lista_de_compra")

    conteo = {e["intencion"]: e["ejemplos"] for e in consulta_service.etiquetas(db)}
    assert conteo["lista_de_compra"] == 3
    assert conteo["fiados"] == 0


# --- La lista del panel --------------------------------------------------

def test_lo_mas_preguntado_va_primero(db):
    """Etiquetar la pregunta que se hizo cuarenta veces vale cuarenta veces
    más que etiquetar la que se hizo una."""
    consulta_service.registrar(db, "pregunta rara", None)
    for _ in range(5):
        consulta_service.registrar(db, "pregunta comun", None)

    lista = consulta_service.listar(db)["consultas"]
    assert lista[0].pregunta == "pregunta comun"


def test_se_pueden_pedir_solo_las_que_cuestan_tokens(db):
    consulta_service.registrar(db, "¿qué tengo que comprar?", "lista_de_compra")
    consulta_service.registrar(db, "¿me conviene el fiado?", None)

    lista = consulta_service.listar(db, sin_reconocer=True)["consultas"]
    assert [c.pregunta for c in lista] == ["¿me conviene el fiado?"]


# --- Enchufado al asistente ----------------------------------------------

def test_preguntar_por_el_enrutador_queda_anotado(db, usuario):
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 3000, 2000)

    asistente_service.preguntar(db, usuario.id, "¿cuánto vale mi inventario?")

    fila = _filas(db)[0]
    assert fila.intencion_detectada == "valor_inventario"


def test_una_pregunta_que_hace_fallar_al_modelo_tambien_queda_anotada(db, usuario):
    """Por esto se anota ANTES de llamar al modelo y no después. Las
    preguntas que rompen la llamada son justo de las que hay que ver en el
    panel; anotándolas al final se perderían.

    Las pruebas corren sin clave de Groq, así que llamar al modelo falla.
    """
    with pytest.raises(ErrorNegocio):
        asistente_service.preguntar(db, usuario.id, "¿me conviene vender por docena?")

    fila = _filas(db)[0]
    assert fila.pregunta == "¿me conviene vender por docena?"
    assert fila.intencion_detectada is None


# --- Privacidad, por construcción ----------------------------------------

def test_la_tabla_no_tiene_donde_guardar_de_quien_es_la_pregunta(db):
    """La garantía no es que nadie escriba el usuario_id: es que no hay
    columna donde ponerlo. Así el panel no puede atar una pregunta a un
    negocio ni por descuido, y no depende de que alguien lo recuerde."""
    assert "usuario_id" not in ConsultaRegistrada.__table__.columns


def test_la_tabla_no_tiene_donde_guardar_la_respuesta(db):
    """La respuesta lleva las cifras del negocio que preguntó —lo vendido,
    lo que le deben, lo que tiene invertido—. Guardarla sería meter en una
    tabla global lo que el panel justamente no muestra."""
    columnas = set(ConsultaRegistrada.__table__.columns.keys())
    assert "respuesta" not in columnas
    assert not [c for c in columnas if "respuest" in c]
