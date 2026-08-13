"""
Quién puede escribir y quién no: suscripción, prueba y verificación.

Es la parte del sistema que decide si un tendero puede registrar una
venta. Un fallo aquí no da error: deja cobrar gratis a quien no pagó, o
bloquea a quien sí. Ninguna de las dos se nota mirando la pantalla.
"""

import pytest

from app.api import deps
from app.core.exceptions import SuscripcionVencida, CorreoSinVerificar
from app.core.fechas import sumar_dias
from app.core.config import settings


def test_quien_pago_puede_escribir(usuario):
    usuario.suscripcion_hasta = sumar_dias(30)
    assert deps.estado_acceso(usuario)["activa"] is True
    assert deps.estado_acceso(usuario)["en_prueba"] is False


def test_el_ultimo_dia_de_suscripcion_todavia_cuenta(usuario):
    """Vence AL FINAL del día, no al principio.

    Con la comparación al revés, quien paga hasta el día 30 pierde el
    acceso al despertar ese mismo día — y llama enfadado, con razón.
    """
    usuario.suscripcion_hasta = sumar_dias(0)
    assert deps.estado_acceso(usuario)["activa"] is True


def test_la_prueba_sirve_aunque_nunca_haya_pagado(usuario):
    usuario.suscripcion_hasta = None
    usuario.prueba_hasta = sumar_dias(2)
    estado = deps.estado_acceso(usuario)
    assert estado["activa"] is True
    assert estado["en_prueba"] is True


def test_sin_pago_y_sin_prueba_queda_en_solo_lectura(usuario):
    usuario.suscripcion_hasta = None
    usuario.prueba_hasta = sumar_dias(-1)
    assert deps.estado_acceso(usuario)["activa"] is False


def test_borrar_el_pago_no_devuelve_los_dias_gratis(usuario):
    """La razón de que `prueba_hasta` sea una columna aparte.

    Si la prueba se calculara desde `creado_en`, limpiarle la suscripción
    a un cliente reciente le regalaría otro periodo gratis. Y limpiarla es
    exactamente lo que se hace cuando alguien deja de pagar.
    """
    usuario.prueba_hasta = sumar_dias(-10)   # ya la gastó hace tiempo
    usuario.suscripcion_hasta = None          # se le retira el pago
    assert deps.estado_acceso(usuario)["activa"] is False


@pytest.mark.parametrize("basura", ["31/12/2099", "2099-13-45", "mañana", "", "  "])
def test_una_fecha_mal_escrita_no_tumba_la_api(usuario, basura):
    """Esa columna se edita A MANO en el editor de Supabase.

    Antes, un dedazo lanzaba ValueError dentro de la comprobación de
    acceso: un 500 en TODAS las rutas protegidas de esa cuenta, con un log
    que no señalaba a la celda culpable. Ahora se trata como "sin fecha".
    """
    usuario.suscripcion_hasta = basura
    usuario.prueba_hasta = None
    assert deps.estado_acceso(usuario)["activa"] is False


def test_dias_restantes_nunca_es_negativo(usuario):
    usuario.suscripcion_hasta = sumar_dias(-5)
    usuario.prueba_hasta = None
    assert deps.estado_acceso(usuario)["dias_restantes"] == 0


def test_sin_verificar_dentro_del_plazo_se_puede_escribir(usuario, monkeypatch):
    monkeypatch.setattr(settings, "REQUERIR_EMAIL_VERIFICADO", True)
    usuario.email_verificado = False
    # Recién creada: `creado_en` sin valor se trata como sin plazo agotado.
    assert deps.verificacion_al_dia(usuario) is True


def test_pasado_el_plazo_sin_verificar_no_se_puede_escribir(usuario, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(settings, "REQUERIR_EMAIL_VERIFICADO", True)
    usuario.email_verificado = False
    usuario.creado_en = datetime.now(timezone.utc) - timedelta(
        days=settings.DIAS_GRACIA_VERIFICACION + 1
    )
    assert deps.verificacion_al_dia(usuario) is False

    with pytest.raises(CorreoSinVerificar):
        deps.exigir_suscripcion_activa(usuario)


def test_el_correo_se_comprueba_antes_que_el_pago(usuario, monkeypatch):
    """Son dos problemas con dos pantallas distintas.

    A quien le falten las dos cosas hay que mandarlo primero a verificar:
    es gratis y lo resuelve solo. Pedirle que pague antes de eso es la
    forma más rápida de perderlo.
    """
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(settings, "REQUERIR_EMAIL_VERIFICADO", True)
    usuario.email_verificado = False
    usuario.creado_en = datetime.now(timezone.utc) - timedelta(days=99)
    usuario.suscripcion_hasta = None
    usuario.prueba_hasta = None

    with pytest.raises(CorreoSinVerificar):
        deps.exigir_suscripcion_activa(usuario)


def test_suscripcion_vencida_lanza_402(usuario, monkeypatch):
    monkeypatch.setattr(settings, "REQUERIR_EMAIL_VERIFICADO", False)
    usuario.suscripcion_hasta = sumar_dias(-1)
    usuario.prueba_hasta = sumar_dias(-1)
    with pytest.raises(SuscripcionVencida):
        deps.exigir_suscripcion_activa(usuario)
