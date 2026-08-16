"""
Un producto que se vende por menos de lo que cuesta.

Nació de una caída real en producción. Un producto quedó guardado con el
precio y el costo invertidos (se vendía a $5.000 y costaba $6.000). El alta
no dijo nada, y al VENDERLO reventaba con un error 500 y un traceback de
SQL: la base tenía un CHECK hecho a mano que prohibía la ganancia
negativa.

Dos fallos encadenados, y los dos se arreglaron:

  1. La restricción de la base convertía un hecho legítimo (vender con
     pérdida) en un error 500. Se quitó en la migración 0019.
  2. La aplicación no validaba nada al crear el producto. Ahora avisa en
     el alta, que es donde la persona tiene los dos números delante.
"""

import pytest

from app.core.exceptions import ErrorNegocio
from app.services import product_service, venta_service


def test_no_se_crea_un_producto_que_pierde_plata(db, usuario):
    """El error de dedo más común: el costo escrito en la casilla del
    precio."""
    with pytest.raises(ErrorNegocio) as exc:
        product_service.agregar(db, usuario.id, "Lápices", 10, 5000, 6000)

    mensaje = str(exc.value)
    assert "5,000" in mensaje and "6,000" in mensaje   # nombra los dos números
    assert "1,000" in mensaje                          # y lo que se perdería


def test_el_mensaje_sugiere_la_causa_probable(db, usuario):
    """Decir "precio inválido" no ayuda. Hay que nombrar la equivocación
    concreta para que la persona sepa qué mirar."""
    with pytest.raises(ErrorNegocio) as exc:
        product_service.agregar(db, usuario.id, "Lápices", 10, 5000, 6000)
    assert "casilla del precio" in str(exc.value)


def test_precio_igual_al_costo_se_permite(db, usuario):
    """Vender al costo no es una pérdida. Es raro, pero es una decisión
    válida (un producto gancho que se vende sin margen para atraer
    clientes)."""
    p = product_service.agregar(db, usuario.id, "Bolsa", 100, 200, 200)
    assert p.precio == 200


def test_con_confirmacion_explicita_si_se_crea(db, usuario):
    """Liquidar algo por vencer o sacar mercancía dañada a mitad de precio
    son hechos reales. El sistema tiene que poder registrarlos — solo
    exige que sea a propósito."""
    p = product_service.agregar(db, usuario.id, "Yogur por vencer", 20, 1500, 2500,
                                permitir_perdida=True)
    assert p.precio == 1500
    assert p.cuanto_costo == 2500


def test_editar_bajando_el_precio_bajo_el_costo_tambien_avisa(db, usuario):
    """El mismo error se puede cometer editando, no solo creando."""
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 5000, 3500)
    p = product_service.listar(db, usuario.id, q="Cuaderno")[0]

    with pytest.raises(ErrorNegocio):
        product_service.editar(db, usuario.id, p.id, "Cuaderno", 10, 3000, 3500)

    db.refresh(p)
    assert p.precio == 5000        # no se cambió nada


def test_editar_con_confirmacion_si_baja_el_precio(db, usuario):
    """Poner en promoción un producto que ya existe."""
    product_service.agregar(db, usuario.id, "Cuaderno", 10, 5000, 3500)
    p = product_service.listar(db, usuario.id, q="Cuaderno")[0]

    product_service.editar(db, usuario.id, p.id, "Cuaderno", 10, 3000, 3500,
                           permitir_perdida=True)
    db.refresh(p)
    assert p.precio == 3000


def test_vender_con_perdida_registra_ganancia_negativa(db, usuario):
    """Lo que reventaba en producción con un 500.

    La pérdida se registra tal cual: es la verdad de lo que pasó. Un libro
    que no puede anotar una pérdida obligaría a falsear el costo.
    """
    p = product_service.agregar(db, usuario.id, "Yogur por vencer", 20, 1500, 2500,
                                permitir_perdida=True)

    venta = venta_service.vender(db, usuario.id, [{"producto_id": p.id, "cantidad": 2}])

    assert venta.precio_venta_total == 3000
    assert venta.ganancia_total == -2000       # 2 x (1500 - 2500)
    db.refresh(p)
    assert p.cantidad == 18                     # el stock baja igual


def test_la_perdida_se_refleja_en_las_cuentas_del_dia(db, usuario):
    """Si la pérdida no bajara el total, el tendero creería que ganó más de
    lo que ganó — que es peor que ver un número en rojo."""
    bueno = product_service.agregar(db, usuario.id, "Arroz", 10, 3000, 2000)
    malo = product_service.agregar(db, usuario.id, "Yogur por vencer", 10, 1500, 2500,
                                   permitir_perdida=True)

    venta_service.vender(db, usuario.id, [{"producto_id": bueno.id, "cantidad": 3}])
    venta_service.vender(db, usuario.id, [{"producto_id": malo.id, "cantidad": 2}])

    _, ganancia = venta_service.ventas_por_fecha(db, usuario.id)
    assert ganancia == 1000                     # 3000 de ganancia - 2000 de pérdida


def test_un_servicio_tambien_se_valida(db, usuario):
    """Una fotocopia cobrada por menos de lo que cuesta el papel es el
    mismo error."""
    with pytest.raises(ErrorNegocio):
        product_service.agregar(db, usuario.id, "Fotocopia", 0, 50, 200,
                                controla_stock=False)
