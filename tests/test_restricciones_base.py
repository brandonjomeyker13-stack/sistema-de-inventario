"""
Las restricciones de la base de datos: la última red.

Estas nueve reglas vivían SOLO en la base de producción, añadidas a mano en
el editor de Supabase. Ningún archivo del proyecto las declaraba, con dos
consecuencias:

  · Ninguna prueba podía detectar una violación, porque la base de pruebas
    se construye desde los modelos.
  · Una base creada desde cero no las habría tenido. Los precios podrían
    ser negativos ahí y no en producción — el peor tipo de diferencia, la
    que hace que un fallo aparezca en un entorno y no en el otro.

Ahora están en los modelos (__table_args__) y la migración 0020 las
reconcilia sobre la base que ya existe. Estas pruebas confirman que
efectivamente se crean y bloquean.

NO sustituyen a la validación de los servicios: un dato malo debe pararse
mucho antes, con un mensaje que explique el problema. Estas solo garantizan
que ni un error de programación futuro pueda dejar guardado algo imposible.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models import Usuario
from app.models.producto import Producto
from app.models.venta import Venta


def _guardar(db, objeto):
    db.add(objeto)
    db.commit()


# --- productos ------------------------------------------------------------

def test_un_producto_no_puede_tener_stock_negativo(db, usuario):
    with pytest.raises(IntegrityError):
        _guardar(db, Producto(usuario_id=usuario.id, nombre="Arroz",
                              cantidad=-1, precio=1000, cuanto_costo=500))


def test_un_producto_no_puede_tener_precio_negativo(db, usuario):
    with pytest.raises(IntegrityError):
        _guardar(db, Producto(usuario_id=usuario.id, nombre="Arroz",
                              cantidad=1, precio=-1000, cuanto_costo=500))


def test_un_producto_no_puede_tener_costo_negativo(db, usuario):
    with pytest.raises(IntegrityError):
        _guardar(db, Producto(usuario_id=usuario.id, nombre="Arroz",
                              cantidad=1, precio=1000, cuanto_costo=-500))


def test_un_producto_no_puede_llamarse_solo_espacios(db, usuario):
    """El nombre vacío es el que produjo el error 500 en producción."""
    with pytest.raises(IntegrityError):
        _guardar(db, Producto(usuario_id=usuario.id, nombre="   ",
                              cantidad=1, precio=1000, cuanto_costo=500))


def test_un_producto_a_precio_cero_si_se_permite(db, usuario):
    """Un regalo o una muestra son válidos. La restricción es >= 0, no > 0."""
    _guardar(db, Producto(usuario_id=usuario.id, nombre="Muestra gratis",
                          cantidad=10, precio=0, cuanto_costo=0))


# --- ventas ---------------------------------------------------------------

def test_una_venta_no_puede_ser_de_cero_unidades(db, usuario):
    with pytest.raises(IntegrityError):
        _guardar(db, Venta(usuario_id=usuario.id, nombre_producto="Arroz",
                           cantidad_vendida=0, precio_venta_total=1000,
                           ganancia_total=500, fecha="2026-08-15"))


def test_una_venta_no_puede_tener_ingresos_negativos(db, usuario):
    """Los ingresos de una venta nunca son negativos. Una devolución se
    registra anulando la venta, no con una venta en negativo."""
    with pytest.raises(IntegrityError):
        _guardar(db, Venta(usuario_id=usuario.id, nombre_producto="Arroz",
                           cantidad_vendida=1, precio_venta_total=-1000,
                           ganancia_total=0, fecha="2026-08-15"))


def test_una_venta_SI_puede_tener_ganancia_negativa(db, usuario):
    """La restricción que se quitó en la migración 0019.

    Producción exigía ganancia_total >= 0, y eso tumbaba con un error 500
    cualquier venta con pérdida: liquidar algo por vencer, sacar mercancía
    dañada. Una pérdida es un hecho real y el libro tiene que poder
    anotarla.
    """
    _guardar(db, Venta(usuario_id=usuario.id, nombre_producto="Yogur por vencer",
                       cantidad_vendida=2, precio_venta_total=3000,
                       ganancia_total=-2000, fecha="2026-08-15"))

    guardada = db.query(Venta).filter(Venta.ganancia_total < 0).one()
    assert guardada.ganancia_total == -2000


# --- usuarios -------------------------------------------------------------

def test_un_negocio_no_puede_llamarse_solo_espacios(db):
    """El fallo concreto: el schema pedía min_length=1, que "   " cumple,
    pero el repositorio le hace .strip() y llegaba vacío. En producción eso
    era un error 500 al registrarse."""
    with pytest.raises(IntegrityError):
        _guardar(db, Usuario(email="x@y.com", password_hash=hash_password("clave"),
                             nombre_negocio="", activo=True))
