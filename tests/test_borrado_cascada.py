"""
Qué se va y qué sobrevive al borrar una fila.

Existe para poder borrar una cuenta completa desde el editor de Supabase
con un solo DELETE, sin ir tabla por tabla en el orden correcto.

Pero "en cascada para todo" habría sido peor que el problema: borrar un
producto se habría llevado por delante las líneas de todas las ventas que
lo incluyeron, y los ingresos del mes habrían cambiado solos, sin error y
sin aviso. Estas pruebas fijan la frontera entre las dos cosas.

NOTA SOBRE SQLITE: no aplica las llaves foráneas por defecto — las acepta y
las ignora. Lo activa `app/database/session.py` con PRAGMA foreign_keys=ON,
y sin eso estas pruebas pasarían en verde sin comprobar nada.
"""

import pytest

from app.models.abono import Abono
from app.models.canasta import Canasta, CanastaItem
from app.models.cliente import Cliente
from app.models.movimiento import MovimientoInventario
from app.models.producto import Producto
from app.models.producto_codigo import ProductoCodigo
from app.models.registro_admin import RegistroAdmin
from app.models.sesion import Sesion
from app.models.usuario import Usuario
from app.models.venta import Venta
from app.models.venta_item import VentaItem
from app.services import (
    canasta_service, cliente_service, product_service, venta_service,
)


@pytest.fixture
def negocio_lleno(db, usuario):
    """Una cuenta con datos en casi todas las tablas."""
    p = product_service.agregar(db, usuario.id, "Cuaderno", 30, 6500, 4800,
                                codigo_barras="7702001234567")
    cliente = cliente_service.agregar(db, usuario.id, "Rosa", None, None, None)

    venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 2}])
    fiada = venta_service.vender(
        db, usuario.id, [{"producto_id": p.id, "cantidad": 1}],
        cliente_id=cliente.id, es_fiado=True,
    )
    cliente_service.registrar_abono(db, usuario.id, fiada.id, 3000, None)
    canasta_service.abrir(db, usuario.id)
    return {"producto": p, "cliente": cliente}


def _cuenta(db, modelo) -> int:
    return db.query(modelo).count()


# --- Borrar la cuenta se lo lleva todo ------------------------------------

def test_borrar_el_negocio_borra_todos_sus_datos(db, usuario, negocio_lleno):
    """Es lo que permite limpiar una cuenta de prueba con un solo DELETE
    desde Supabase, sin ir tabla por tabla en el orden correcto."""
    for modelo in (Producto, ProductoCodigo, Venta, VentaItem, Cliente,
                   Abono, MovimientoInventario, Canasta):
        assert _cuenta(db, modelo) > 0, modelo.__name__

    db.delete(usuario)
    db.commit()

    for modelo in (Producto, ProductoCodigo, Venta, VentaItem, Cliente,
                   Abono, MovimientoInventario, Canasta, CanastaItem, Usuario):
        assert _cuenta(db, modelo) == 0, f"quedaron filas de {modelo.__name__}"


def test_borrar_el_negocio_cierra_sus_sesiones(db, usuario):
    from app.services import auth_service

    auth_service.iniciar_sesion(db, usuario.email, "clave-de-prueba")
    assert _cuenta(db, Sesion) == 1

    db.delete(usuario)
    db.commit()
    assert _cuenta(db, Sesion) == 0


def test_no_toca_los_datos_de_otro_negocio(db, usuario, otro_usuario, negocio_lleno):
    ajeno = product_service.agregar(db, otro_usuario.id, "Arroz", 10, 2000, 1500)

    db.delete(usuario)
    db.commit()

    assert _cuenta(db, Usuario) == 1
    assert _cuenta(db, Producto) == 1
    db.refresh(ajeno)
    assert ajeno.nombre == "Arroz"


# --- La bitácora SOBREVIVE -----------------------------------------------

def test_la_bitacora_sobrevive_al_borrado(db, usuario, otro_usuario):
    """La razón de que esta tabla NO vaya en cascada: con CASCADE, borrar
    una cuenta se llevaría por delante el registro de que la borraste, que
    es justo el que más falta hace después."""
    from app.services import admin_service
    from app.core.fechas import sumar_dias

    usuario.es_admin = True
    db.commit()
    admin_service.cambiar_suscripcion(db, usuario, otro_usuario.id,
                                      sumar_dias(30), "pagó por Nequi")
    assert _cuenta(db, RegistroAdmin) == 1

    db.delete(otro_usuario)
    db.commit()

    registro = db.query(RegistroAdmin).one()
    assert registro.usuario_id is None          # la cuenta ya no existe
    assert "Otra tienda" in registro.descripcion  # pero se sabe cuál era
    assert registro.nota == "pagó por Nequi"


# --- Lo que NO se puede llevar por delante -------------------------------

def test_borrar_un_producto_NO_borra_las_ventas(db, usuario, negocio_lleno):
    """LA PRUEBA MÁS IMPORTANTE DE ESTE ARCHIVO.

    Con CASCADE aquí, borrar un producto habría borrado las líneas de todas
    las ventas que lo incluyeron: los ingresos y la ganancia del mes
    cambiarían solos, sin error y sin aviso.

    La venta ocurrió y esa plata entró. El producto puede desaparecer; la
    venta, no.
    """
    ventas_antes = _cuenta(db, Venta)
    lineas_antes = _cuenta(db, VentaItem)

    db.delete(negocio_lleno["producto"])
    db.commit()

    assert _cuenta(db, Venta) == ventas_antes
    assert _cuenta(db, VentaItem) == lineas_antes


def test_la_linea_conserva_el_nombre_y_el_precio(db, usuario, negocio_lleno):
    """Por esto `venta_items` guarda copia: para seguir siendo legible
    cuando el producto que describe ya no exista."""
    db.delete(negocio_lleno["producto"])
    db.commit()

    linea = db.query(VentaItem).first()
    assert linea.producto_id is None            # perdió la referencia
    assert linea.nombre_producto == "Cuaderno"  # pero se sabe qué se vendió
    assert linea.precio_unitario == 6500


def test_los_totales_del_mes_no_cambian(db, usuario, negocio_lleno):
    """La consecuencia práctica: el reporte de ayer sigue diciendo lo
    mismo mañana."""
    _, antes = venta_service.ventas_por_fecha(db, usuario.id)

    db.delete(negocio_lleno["producto"])
    db.commit()

    _, despues = venta_service.ventas_por_fecha(db, usuario.id)
    assert antes == despues


def test_borrar_un_producto_SI_borra_sus_codigos(db, usuario, negocio_lleno):
    """Un código sin producto no significa nada, y dejarlo ahí bloquearía
    ese código para siempre."""
    assert _cuenta(db, ProductoCodigo) == 1

    db.delete(negocio_lleno["producto"])
    db.commit()

    assert _cuenta(db, ProductoCodigo) == 0


def test_borrar_un_cliente_NO_borra_sus_ventas(db, usuario, negocio_lleno):
    """La mercancía salió y se cobró (o se fió). Que el cliente se borre no
    deshace la venta."""
    ventas_antes = _cuenta(db, Venta)

    db.delete(negocio_lleno["cliente"])
    db.commit()

    assert _cuenta(db, Venta) == ventas_antes
    fiada = db.query(Venta).filter(Venta.es_fiado.is_(True)).one()
    assert fiada.cliente_id is None


def test_borrar_una_categoria_NO_borra_sus_productos(db, usuario):
    """Sería la forma más rápida de perder el inventario entero sin
    querer."""
    from app.services import categoria_service

    categoria = categoria_service.agregar(db, usuario.id, "Papelería")
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 6500, 4800,
                            categoria_id=categoria.id)

    db.delete(categoria)
    db.commit()

    producto = db.query(Producto).one()
    assert producto.categoria_id is None
    assert producto.nombre == "Cuaderno"


# --- Borrar una venta ----------------------------------------------------

def test_borrar_una_venta_borra_sus_lineas_y_abonos(db, usuario, negocio_lleno):
    """Una línea o un abono sin su venta son basura: no se pueden sumar a
    nada ni leer por separado."""
    fiada = db.query(Venta).filter(Venta.es_fiado.is_(True)).one()

    db.delete(fiada)
    db.commit()

    assert _cuenta(db, Abono) == 0
    assert _cuenta(db, VentaItem) == 1      # queda la línea de la otra venta
