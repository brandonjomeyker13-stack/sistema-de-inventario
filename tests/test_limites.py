"""
Límite de intentos.

Antes no había ninguno: treinta contraseñas erróneas seguidas se
procesaban igual que la primera, y el endpoint del asistente —que cuesta
dinero en cada llamada— se podía disparar en bucle.
"""

import time

import pytest

from app.core import limites


@pytest.fixture(autouse=True)
def limpiar_contadores():
    """Cada prueba arranca sin contadores de las anteriores."""
    limites._eventos.clear()
    yield
    limites._eventos.clear()


def test_deja_pasar_hasta_el_maximo():
    for _ in range(5):
        limites.exigir("prueba", maximo=5, segundos=60)


def test_bloquea_al_pasarse():
    for _ in range(5):
        limites.exigir("prueba", maximo=5, segundos=60)
    with pytest.raises(limites.DemasiadosIntentos):
        limites.exigir("prueba", maximo=5, segundos=60)


def test_dice_cuanto_hay_que_esperar():
    """Para la cabecera Retry-After: el frontend puede mostrar una cuenta
    atrás en vez de un error opaco que invita a seguir pulsando."""
    limites.exigir("prueba", maximo=1, segundos=60)
    with pytest.raises(limites.DemasiadosIntentos) as exc:
        limites.exigir("prueba", maximo=1, segundos=60)
    assert 0 < exc.value.segundos <= 61


def test_insistir_no_alarga_el_castigo():
    """Si los intentos bloqueados también contaran, seguir pulsando
    extendería el bloqueo para siempre y una persona real que se equivocó
    no podría volver a entrar nunca."""
    for _ in range(2):
        limites.exigir("prueba", maximo=2, segundos=1)
    for _ in range(30):
        with pytest.raises(limites.DemasiadosIntentos):
            limites.exigir("prueba", maximo=2, segundos=1)

    time.sleep(1.1)
    limites.exigir("prueba", maximo=2, segundos=1)      # ya se puede


def test_las_claves_son_independientes():
    """Que a un tendero le limiten no puede afectar a otro."""
    for _ in range(3):
        limites.exigir("tienda-a", maximo=3, segundos=60)
    limites.exigir("tienda-b", maximo=3, segundos=60)


def test_acertar_perdona_los_fallos_previos():
    """Quien se equivoca tres veces antes de acertar no debe arrastrar el
    castigo el resto del día."""
    for _ in range(4):
        limites.exigir("login:cuenta:x", maximo=5, segundos=900)
    limites.limpiar("login:cuenta:x")
    for _ in range(5):
        limites.exigir("login:cuenta:x", maximo=5, segundos=900)


def test_la_ip_real_viene_de_x_forwarded_for():
    """Detrás del proxy de Render, `request.client.host` es la IP del
    PROXY: la misma para todo el mundo. Limitar por esa clave castigaría a
    todos los tenderos a la vez en cuanto alguien insistiera."""

    class PeticionFalsa:
        headers = {"x-forwarded-for": "190.1.2.3, 172.16.0.1"}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert limites.ip_del_cliente(PeticionFalsa()) == "190.1.2.3"


def test_sin_proxy_usa_la_ip_directa():
    class PeticionFalsa:
        headers = {}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert limites.ip_del_cliente(PeticionFalsa()) == "10.0.0.1"


def test_no_crece_sin_limite():
    """Sin poda, un atacante que rote la IP en cada intento haría crecer
    el diccionario hasta tumbar el proceso: el antídoto sería el veneno."""
    for i in range(limites.MAX_CLAVES + 500):
        limites.exigir(f"ip-{i}", maximo=1, segundos=1)
    assert len(limites._eventos) <= limites.MAX_CLAVES + 1000
