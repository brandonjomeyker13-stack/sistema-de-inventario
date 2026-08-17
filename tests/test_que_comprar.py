"""
La lista de lo que hay que comprar.

Es la pantalla que hace que el tendero abra la aplicación los lunes: mira
qué falta, copia la lista y se la manda al proveedor por WhatsApp.

Junta dos señales porque cada una sola tiene un punto ciego:

  · UMBRAL: quedan menos unidades que el mínimo. Sirve desde el primer día
    y es la ÚNICA que ve un producto sin historial de ventas.
  · RITMO: al paso al que se vende se acaba esta semana. Ve venir el
    problema antes de llegar al mínimo.
"""

import pytest

from app.services import analitica_service, product_service, venta_service


def _comprar(db, usuario):
    return analitica_service.que_comprar(db, usuario.id)


# --- El umbral -----------------------------------------------------------

def test_un_producto_por_debajo_de_su_minimo_entra(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 3, 2000, 1500, stock_minimo=10)

    lista = _comprar(db, usuario)
    assert lista["total"] == 1
    assert lista["productos"][0]["nombre"] == "Arroz"
    assert "tu mínimo es 10" in lista["productos"][0]["motivo"]


def test_un_producto_con_stock_de_sobra_no_entra(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 100, 2000, 1500, stock_minimo=10)
    assert _comprar(db, usuario)["total"] == 0


def test_sin_umbral_propio_usa_el_del_negocio(db, usuario):
    """Arranca en 5 para que la lista sirva desde el primer día, sin que
    nadie tenga que configurar nada."""
    assert usuario.stock_minimo_defecto == 5

    product_service.agregar(db, usuario.id, "Arroz", 4, 2000, 1500)      # sin mínimo propio
    product_service.agregar(db, usuario.id, "Aceite", 20, 8000, 6000)

    lista = _comprar(db, usuario)
    assert [p["nombre"] for p in lista["productos"]] == ["Arroz"]
    assert lista["productos"][0]["stock_minimo"] == 5


def test_el_umbral_propio_manda_sobre_el_del_negocio(db, usuario):
    """Un solo número global no sirve: el arroz vende cincuenta a la semana
    y hay que pedirlo con veinte todavía en la estantería."""
    product_service.agregar(db, usuario.id, "Arroz", 15, 2000, 1500, stock_minimo=20)
    product_service.agregar(db, usuario.id, "Cuaderno", 15, 5000, 3500)   # mínimo 5

    lista = _comprar(db, usuario)
    assert [p["nombre"] for p in lista["productos"]] == ["Arroz"]


def test_cambiar_el_umbral_del_negocio_cambia_la_lista(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 8, 2000, 1500)
    assert _comprar(db, usuario)["total"] == 0        # 8 > 5

    usuario.stock_minimo_defecto = 10
    db.commit()
    assert _comprar(db, usuario)["total"] == 1        # 8 <= 10


# --- El ritmo de venta ---------------------------------------------------

def test_un_producto_que_se_acaba_pronto_entra_aunque_este_sobre_el_minimo(db, usuario):
    """Lo que un umbral fijo no puede ver: un producto que de pronto se
    puso de moda y va a durar tres días aunque tenga treinta unidades."""
    p = product_service.agregar(db, usuario.id, "Gaseosa", 120, 2500, 1900, stock_minimo=5)
    # 100 unidades en la ventana de 30 días -> 3,33 al día.
    # Quedan 20, muy por encima del mínimo de 5, pero 20 / 3,33 = 6 días:
    # menos que los 7 del umbral, así que entra por RITMO y no por umbral.
    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 100}])

    lista = _comprar(db, usuario)
    assert lista["total"] == 1
    assert "al ritmo de ahora" in lista["productos"][0]["motivo"]
    assert lista["productos"][0]["vende_por_dia"] > 0


def test_un_producto_sin_ventas_lo_ve_el_umbral(db, usuario):
    """El punto ciego del ritmo: sin historial, el ritmo es cero y el
    producto se agotaría en silencio. El umbral es lo único que lo ve."""
    product_service.agregar(db, usuario.id, "Producto nuevo", 2, 2000, 1500)

    lista = _comprar(db, usuario)
    assert lista["total"] == 1
    assert lista["productos"][0]["dias_restantes"] is None
    assert lista["productos"][0]["vende_por_dia"] == 0


# --- Orden y urgencia ----------------------------------------------------

def test_lo_agotado_va_primero(db, usuario):
    """Cada hora que pasa es una venta que se va a la tienda de la esquina."""
    product_service.agregar(db, usuario.id, "Aceite", 3, 8000, 6000)
    product_service.agregar(db, usuario.id, "Arroz", 0, 2000, 1500)

    lista = _comprar(db, usuario)
    assert lista["productos"][0]["nombre"] == "Arroz"
    assert lista["productos"][0]["ya_agotado"] is True
    assert lista["agotados"] == 1


def test_lo_agotado_dice_que_se_acabo(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 0, 2000, 1500)
    assert _comprar(db, usuario)["productos"][0]["motivo"] == "se acabó"


# --- Los servicios quedan fuera ------------------------------------------

def test_un_servicio_no_aparece_en_la_lista_de_compra(db, usuario):
    """No hay un proveedor de fotocopias."""
    product_service.agregar(db, usuario.id, "Fotocopia", 0, 200, 50, controla_stock=False)
    assert _comprar(db, usuario)["total"] == 0


def test_un_servicio_no_guarda_umbral(db, usuario):
    p = product_service.agregar(db, usuario.id, "Fotocopia", 0, 200, 50,
                                controla_stock=False, stock_minimo=10)
    assert p.stock_minimo is None


# --- El texto para WhatsApp ----------------------------------------------

def test_el_texto_trae_el_negocio_y_la_fecha(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 2, 2000, 1500)

    texto = _comprar(db, usuario)["texto"]
    assert usuario.nombre_negocio in texto
    from app.core.fechas import hoy_local
    assert hoy_local() in texto


def test_el_texto_separa_lo_agotado_de_lo_que_se_esta_acabando(db, usuario):
    product_service.agregar(db, usuario.id, "Arroz", 0, 2000, 1500)
    product_service.agregar(db, usuario.id, "Aceite", 2, 8000, 6000)

    texto = _comprar(db, usuario)["texto"]
    assert "SE ACABARON:" in texto
    assert "SE ESTAN ACABANDO:" in texto
    # Lo agotado va antes en el texto, igual que en la lista.
    assert texto.index("Arroz") < texto.index("Aceite")


def test_el_texto_no_usa_asteriscos(db, usuario):
    """WhatsApp los interpreta como negritas, pero un SMS o un correo no:
    ahí quedarían como basura en medio del pedido."""
    product_service.agregar(db, usuario.id, "Arroz", 2, 2000, 1500)
    assert "*" not in _comprar(db, usuario)["texto"]


def test_con_todo_surtido_el_texto_lo_dice(db, usuario):
    """Devolver un texto vacío haría que el botón de copiar pegara nada, y
    el tendero pensaría que la aplicación falló."""
    product_service.agregar(db, usuario.id, "Arroz", 100, 2000, 1500)

    lista = _comprar(db, usuario)
    assert lista["total"] == 0
    assert "No hay nada por comprar" in lista["texto"]


def test_el_texto_incluye_todos_los_productos_de_la_lista(db, usuario):
    """Si el texto y la lista no coincidieran, la pantalla mostraría doce
    productos y lo copiado traería ocho."""
    for n in range(7):
        product_service.agregar(db, usuario.id, f"Producto {n}", 1, 2000, 1500)

    lista = _comprar(db, usuario)
    assert lista["total"] == 7
    for p in lista["productos"]:
        assert p["nombre"] in lista["texto"]


# --- El asistente ve lo mismo --------------------------------------------

def test_el_asistente_recibe_el_texto_exacto(db, usuario):
    """La razón de que el texto se arme en el backend: el chat y la pantalla
    tienen que decir exactamente lo mismo."""
    from app.services import asistente_service

    product_service.agregar(db, usuario.id, "Arroz", 0, 2000, 1500)
    product_service.agregar(db, usuario.id, "Aceite", 2, 8000, 6000)

    contexto = asistente_service.construir_contexto(db, usuario.id, "qué tengo que comprar")
    lista = _comprar(db, usuario)

    assert contexto["lista_de_compra"]["texto_exacto"] == lista["texto"]
    assert contexto["lista_de_compra"]["cuantos_productos"] == 2
    assert contexto["lista_de_compra"]["cuantos_agotados"] == 1


def test_las_instrucciones_le_prohiben_reescribir_la_lista(db, usuario):
    """Sin esta instrucción el modelo resumiría o reordenaría, y las dos
    listas dejarían de coincidir."""
    from app.services.asistente_service import INSTRUCCIONES

    assert "texto_exacto" in INSTRUCCIONES
    assert "sin resumirlo" in INSTRUCCIONES


# --- Aislamiento ---------------------------------------------------------

def test_la_lista_no_mezcla_negocios(db, usuario, otro_usuario):
    product_service.agregar(db, usuario.id, "Arroz", 2, 2000, 1500)
    product_service.agregar(db, otro_usuario.id, "Aceite", 1, 8000, 6000)

    lista = _comprar(db, usuario)
    assert [p["nombre"] for p in lista["productos"]] == ["Arroz"]
