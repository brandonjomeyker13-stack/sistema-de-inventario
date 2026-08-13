"""
La canasta compartida: el celular como lector de códigos.

Lo que se prueba aquí es sobre todo el CONTROL DE ACCESO. El token va
dentro de un QR que está a la vista en el mostrador, así que hay que
garantizar que quien lo fotografíe no pueda cobrar, ni recibir mercancía,
ni ver las canastas de otro negocio.
"""

import pytest

from app.core.exceptions import ErrorNegocio, NoEncontrado, CredencialesInvalidas
from app.models.canasta import PROPOSITO_VENTA, PROPOSITO_INVENTARIO
from app.services import canasta_service, product_service


@pytest.fixture
def arroz(db, usuario):
    return product_service.agregar(db, usuario.id, "Arroz", 10, 3000, 2000,
                                   codigo_barras="7702001234567")


@pytest.fixture
def canasta(db, usuario):
    return canasta_service.abrir(db, usuario.id)


def test_abrir_dos_veces_devuelve_la_misma(db, usuario, canasta):
    """El frontend abre la canasta cada vez que se entra a la pantalla.
    Crear una nueva por visita perdería el trabajo a medias si el tendero
    recarga sin querer."""
    otra = canasta_service.abrir(db, usuario.id)
    assert otra["id"] == canasta["id"]


def test_venta_e_inventario_conviven_sin_pisarse(db, usuario, canasta):
    inventario = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    assert inventario["id"] != canasta["id"]
    assert inventario["proposito"] == PROPOSITO_INVENTARIO


def test_el_celular_puede_agregar_con_su_token(db, canasta, arroz):
    vista = canasta_service.agregar(
        db, canasta["id"], None, canasta["token_celular"],
        "7702001234567", None, None, 1,
    )
    assert vista["total"] == 3000
    assert vista["items"][0]["nombre"] == "Arroz"


def test_escanear_dos_veces_sube_la_cantidad(db, canasta, arroz):
    """Pasas tres yogures por el lector y quieres ver 'Yogur x3', no tres
    líneas de yogur."""
    for _ in range(3):
        vista = canasta_service.agregar(
            db, canasta["id"], None, canasta["token_celular"],
            "7702001234567", None, None, 1,
        )
    assert len(vista["items"]) == 1
    assert vista["items"][0]["cantidad"] == 3


def test_el_celular_no_puede_cobrar(db, canasta, arroz):
    """La línea que de verdad importa: el token nunca mueve dinero."""
    canasta_service.agregar(db, canasta["id"], None, canasta["token_celular"],
                            "7702001234567", None, None, 1)
    with pytest.raises(TypeError):
        # cobrar() ni siquiera acepta un token: exige usuario_id.
        canasta_service.cobrar(db, canasta["id"], None, token=canasta["token_celular"])


def test_el_token_de_otra_canasta_no_sirve(db, usuario, otro_usuario, canasta, arroz):
    ajena = canasta_service.abrir(db, otro_usuario.id)
    with pytest.raises(NoEncontrado):
        canasta_service.ver(db, canasta["id"], None, ajena["token_celular"])


def test_sin_token_ni_sesion_lo_dice_claramente(db, canasta):
    """Mensaje explícito a propósito: un proxy que se come la cabecera
    personalizada se ve IGUAL que un token equivocado, y sin este aviso
    depurar por qué el celular no entra es adivinar."""
    with pytest.raises(CredencialesInvalidas):
        canasta_service.ver(db, canasta["id"], None, None)


def test_otro_negocio_no_ve_la_canasta(db, canasta, otro_usuario):
    """404 y no 403: un 403 le confirmaría que esa canasta existe."""
    with pytest.raises(NoEncontrado):
        canasta_service.ver(db, canasta["id"], otro_usuario.id, None)


def test_cobrar_convierte_la_canasta_en_venta(db, usuario, canasta, arroz):
    canasta_service.agregar(db, canasta["id"], usuario.id, None,
                            "7702001234567", None, None, 2)
    venta = canasta_service.cobrar(db, canasta["id"], usuario.id)
    assert venta.precio_venta_total == 6000
    db.refresh(arroz)
    assert arroz.cantidad == 8


def test_no_se_puede_cobrar_dos_veces(db, usuario, canasta, arroz):
    canasta_service.agregar(db, canasta["id"], usuario.id, None,
                            "7702001234567", None, None, 1)
    canasta_service.cobrar(db, canasta["id"], usuario.id)
    with pytest.raises(ErrorNegocio):
        canasta_service.cobrar(db, canasta["id"], usuario.id)


def test_una_canasta_de_inventario_no_se_puede_cobrar(db, usuario):
    """Recibir mercancía no es vender. Sin esta guarda, una recepción
    podría cobrarse como venta."""
    inventario = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    with pytest.raises(ErrorNegocio):
        canasta_service.cobrar(db, inventario["id"], usuario.id)


def test_en_venta_un_codigo_desconocido_es_un_error(db, usuario, canasta):
    with pytest.raises(NoEncontrado):
        canasta_service.agregar(db, canasta["id"], usuario.id, None,
                                "7709999999999", None, None, 1)


def test_en_inventario_un_codigo_desconocido_es_lo_normal(db, usuario):
    """Es justo lo que se viene a dar de alta. Se guarda como pendiente y
    el PC abre el formulario con el código ya puesto."""
    inventario = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    vista = canasta_service.agregar(db, inventario["id"], usuario.id, None,
                                    "7709999999999", None, None, 3)
    assert vista["pendientes"] == 1
    assert vista["items"][0]["existe"] is False
    assert vista["items"][0]["codigo_pendiente"] == "7709999999999"


def test_no_se_recibe_mercancia_con_codigos_sin_identificar(db, usuario):
    """Recibir a medias dejaría cajas escaneadas que no entraron a ningún
    inventario, y nadie se enteraría hasta el siguiente conteo."""
    inventario = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    canasta_service.agregar(db, inventario["id"], usuario.id, None,
                            "7709999999999", None, None, 1)
    with pytest.raises(ErrorNegocio):
        canasta_service.recibir(db, inventario["id"], usuario.id)


def test_un_codigo_pendiente_se_resuelve_al_darlo_de_alta(db, usuario):
    """El tendero crea el producto desde el PC mientras el celular sigue
    escaneando. Al leer, la línea pendiente ya encuentra su producto — sin
    escribir nada: un GET que modifica datos es fuente de sorpresas."""
    inventario = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    canasta_service.agregar(db, inventario["id"], usuario.id, None,
                            "7709999999999", None, None, 4)

    product_service.agregar(db, usuario.id, "Panela", 0, 2000, 1500,
                            codigo_barras="7709999999999")

    vista = canasta_service.ver(db, inventario["id"], usuario.id, None)
    assert vista["pendientes"] == 0
    assert vista["items"][0]["nombre"] == "Panela"


def test_recibir_mete_la_mercancia_al_inventario(db, usuario, arroz):
    inventario = canasta_service.abrir(db, usuario.id, PROPOSITO_INVENTARIO)
    canasta_service.agregar(db, inventario["id"], usuario.id, None,
                            "7702001234567", None, None, 20)
    resultado = canasta_service.recibir(db, inventario["id"], usuario.id)
    assert resultado["unidades_recibidas"] == 20
    db.refresh(arroz)
    assert arroz.cantidad == 30


def test_pintar_la_canasta_no_escala_con_las_lineas(db, usuario):
    """El PC sondea esta vista cada segundo y medio. Resolviendo producto
    a producto, diez líneas eran once consultas por sondeo: unas
    cuatrocientas por minuto contra Supabase."""
    from sqlalchemy import event

    canasta = canasta_service.abrir(db, usuario.id)
    for n in range(10):
        p = product_service.agregar(db, usuario.id, f"Producto {n}", 50, 1000, 700)
        canasta_service.agregar(db, canasta["id"], usuario.id, None, None, None, p.id, 1)

    consultas = []

    def contar(conn, cursor, stmt, params, ctx, many):
        if stmt.strip().upper().startswith("SELECT"):
            consultas.append(stmt)

    motor = db.get_bind()
    event.listen(motor, "before_cursor_execute", contar)
    db.expire_all()
    canasta_service.ver(db, canasta["id"], usuario.id, None)
    event.remove(motor, "before_cursor_execute", contar)

    assert len(consultas) <= 5, f"{len(consultas)} consultas para pintar 10 líneas"
