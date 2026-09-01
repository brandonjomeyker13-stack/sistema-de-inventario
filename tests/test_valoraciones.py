"""
El tendero califica las respuestas de Trackie.

Es la mejor etiqueta que puede tener el proyecto: quien sabe si "tienes 3
productos por comprar" era verdad es el dueño mirando su estantería, no
nosotros desde el panel.

Casi la mitad de estas pruebas son sobre la firma, y no es exceso de celo.
El servidor NO guarda lo que responde —eso metería las cifras de cada
negocio en una tabla global—, así que para calificar hay que devolverle el
texto. Sin firma, cualquiera podría llenar el panel de "Trackie dijo esto"
con cosas que Trackie nunca dijo. Y ese panel es el conjunto de
entrenamiento: datos inventados ahí no se notan hasta mucho después.
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.models.valoracion import PENDIENTE, REVISADA, Valoracion
from app.services import asistente_service, product_service, valoracion_service


@pytest.fixture
def admin(db, usuario):
    usuario.es_admin = True
    db.commit()
    return usuario


@pytest.fixture
def respondida(db, usuario):
    """Una respuesta real del asistente, con su firma."""
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 3000, 2000)
    salida = asistente_service.preguntar(db, usuario.id, "¿cuánto vale mi inventario?")
    return {"usuario_id": usuario.id, "pregunta": "¿cuánto vale mi inventario?", **salida}


def _valorar(db, r, valoracion="mala", comentario=None, **cambios):
    datos = {**r, **cambios}
    return valoracion_service.valorar(
        db, datos.pop("usuario_id"), datos["pregunta"], datos["respuesta"],
        datos["origen"], datos["intencion"], datos["firma"], valoracion,
        comentario,
    )


# --- La respuesta viene sellada ------------------------------------------

def test_la_respuesta_del_asistente_trae_con_que_calificarla(respondida):
    assert respondida["origen"] == "enrutador"
    assert respondida["intencion"] == "valor_inventario"
    assert respondida["firma"]


def test_se_puede_calificar_lo_que_de_verdad_respondio(db, respondida):
    fila = _valorar(db, respondida, "buena")

    assert fila.valoracion == "buena"
    assert fila.origen == "enrutador"
    assert fila.estado == PENDIENTE


def test_el_comentario_es_lo_mas_valioso_cuando_esta(db, respondida):
    fila = _valorar(db, respondida, "mala", "me dijo 3 y en verdad son 5")
    assert fila.comentario == "me dijo 3 y en verdad son 5"


# --- Nadie puede inventar lo que dijo Trackie ----------------------------

def test_no_se_puede_calificar_una_respuesta_inventada(db, respondida):
    """El caso que motivó la firma: alguien mandando texto que el asistente
    nunca produjo, para envenenar el conjunto de entrenamiento."""
    with pytest.raises(ErrorNegocio):
        _valorar(db, respondida, respuesta="Trackie dijo una barbaridad")

    assert db.query(Valoracion).all() == []


def test_tampoco_se_puede_cambiar_la_pregunta(db, respondida):
    with pytest.raises(ErrorNegocio):
        _valorar(db, respondida, pregunta="otra cosa completamente distinta")


def test_ni_hacer_pasar_por_del_modelo_lo_que_dijo_el_enrutador(db, respondida):
    """Se firman los cuatro campos y no solo el texto. Si el origen se
    pudiera cambiar, la métrica de "el enrutador acierta más que el modelo"
    dejaría de significar nada."""
    with pytest.raises(ErrorNegocio):
        _valorar(db, respondida, origen="modelo")


def test_sin_firma_no_se_guarda(db, respondida):
    with pytest.raises(ErrorNegocio):
        _valorar(db, respondida, firma="")


def test_la_calificacion_solo_puede_ser_buena_o_mala(db, respondida):
    with pytest.raises(ErrorNegocio):
        _valorar(db, respondida, valoracion="regular")


# --- Lo que ve el panel --------------------------------------------------

def test_el_resumen_vigila_las_malas_del_enrutador(db, respondida):
    """Si el enrutador se lleva más quejas que el modelo, hay disparadores
    respondiendo preguntas que no eran suyas — y eso se arregla QUITANDO
    disparadores, no agregándolos."""
    _valorar(db, respondida, "mala")

    resumen = valoracion_service.resumen(db)
    assert resumen["malas"] == 1
    assert resumen["malas_del_enrutador"] == 1
    assert resumen["sin_revisar"] == 1


def test_revisar_la_etiqueta_y_la_cierra(db, admin, respondida):
    """Una queja etiquetada vale más que una pregunta etiquetada a ojo:
    viene con la prueba de que estaba mal."""
    fila = _valorar(db, respondida, "mala", "esto no era lo que pregunté")

    resultado = valoracion_service.revisar(db, admin, fila.id, "lista_de_compra")

    assert resultado.estado == REVISADA
    assert resultado.intencion_correcta == "lista_de_compra"
    assert resultado.revisada_por == admin.id


def test_se_puede_cerrar_sin_etiquetar(db, admin, respondida):
    fila = _valorar(db, respondida, "mala")
    resultado = valoracion_service.revisar(db, admin, fila.id)

    assert resultado.estado == REVISADA
    assert resultado.intencion_correcta is None


def test_no_se_puede_etiquetar_con_algo_que_no_existe(db, admin, respondida):
    fila = _valorar(db, respondida, "mala")
    with pytest.raises(ErrorNegocio):
        valoracion_service.revisar(db, admin, fila.id, "cosas_raras")


def test_revisar_algo_que_no_existe_da_no_encontrado(db, admin):
    with pytest.raises(NoEncontrado):
        valoracion_service.revisar(db, admin, "no-existe")


# --- Privacidad ----------------------------------------------------------

def test_la_queja_dice_de_que_negocio_es(db, usuario, respondida):
    """Al contrario que las preguntas, que se recogen en silencio y van
    anónimas. Aquí la fila existe porque él pidió que la revisáramos, y
    revisar "me dijo 3 y en verdad son 5" obliga a ver de dónde salió el 3."""
    fila = _valorar(db, respondida, "mala", "me dijo 3 y en verdad son 5")

    assert fila.usuario_id == usuario.id
    assert fila.negocio == usuario.nombre_negocio


def test_las_preguntas_en_cambio_siguen_siendo_anonimas(db):
    """La distinción que justifica todo: `consultas` se recoge sin permiso,
    así que no guarda de quién es. `valoraciones` sí, porque él lo pidió."""
    from app.models.consulta import ConsultaRegistrada

    assert "usuario_id" not in ConsultaRegistrada.__table__.columns
    assert "usuario_id" in Valoracion.__table__.columns


def test_nada_se_guarda_si_el_tendero_no_califica(db, respondida):
    """Preguntar no deja rastro de la respuesta. La fila solo aparece cuando
    él pulsa el botón, y ese gesto ES el consentimiento."""
    assert db.query(Valoracion).all() == []
