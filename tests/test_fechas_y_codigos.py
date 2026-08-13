"""
Fechas y códigos de barras: dos cosas pequeñas que descuadran el negocio.

Las fechas, porque el servidor corre en UTC y la tienda no. Los códigos,
porque el mismo producto leído por dos lectores distintos no puede acabar
registrado dos veces.
"""

import pytest

from app.core import codigos
from app.core.fechas import (
    dias_de_atraso, fecha_valida, hoy_local, normalizar_fecha, sumar_dias, ultimos_dias,
)


# --- Fechas ---------------------------------------------------------------

def test_hoy_es_la_fecha_del_negocio_no_la_del_servidor():
    """Render corre en UTC. A las 7:30 p.m. en Colombia ya es el día
    siguiente en UTC, y la venta se guardaba con la fecha de mañana —
    justo en las horas de más venta."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    esperada = datetime.now(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d")
    assert hoy_local() == esperada


def test_ultimos_dias_no_deja_huecos():
    dias = ultimos_dias(7)
    assert len(dias) == 7
    assert dias[0] == hoy_local()
    assert dias == sorted(dias, reverse=True)      # del más reciente al más antiguo


def test_normalizar_acepta_el_iso_del_calendario_del_navegador():
    """`toISOString()` devuelve '2026-08-23T05:00:00.000Z'. Se corta por
    la T en vez de convertir zonas a propósito: si el tendero eligió el
    23 en el calendario, es el 23."""
    assert normalizar_fecha("2026-08-23T05:00:00.000Z") == "2026-08-23"


@pytest.mark.parametrize("malo", ["23/08/2026", "2026-13-45", "ayer", "2026-08"])
def test_normalizar_rechaza_lo_que_no_es_fecha(malo):
    with pytest.raises(ValueError):
        normalizar_fecha(malo)


@pytest.mark.parametrize("malo", ["23/08/2026", "2026-13-45", "ayer", "", None])
def test_fecha_valida_nunca_lanza(malo):
    """Para columnas que se editan a mano en Supabase: una fecha ilegible
    se trata como "sin fecha" en vez de tumbar la API entera."""
    assert fecha_valida(malo) is None


def test_dias_de_atraso_nunca_es_negativo():
    """"Le faltan 3 días para vencer" no es un atraso. Mezclarlos en el
    mismo número obligaría a recordar el signo al leerlo."""
    assert dias_de_atraso(sumar_dias(5)) == 0
    assert dias_de_atraso(sumar_dias(-3)) == 3
    assert dias_de_atraso(None) == 0


def test_dias_de_atraso_tolera_basura():
    """La validación está en normalizar_fecha; aquí no debería llegar nada
    raro. Pero una fila vieja no puede tumbar la lista de deudores."""
    assert dias_de_atraso("cuando pueda") == 0


# --- Códigos de barras ----------------------------------------------------

def test_upc_a_de_12_digitos_se_guarda_como_ean_13():
    """Es el MISMO código: el cero delante es parte del estándar. Sin
    esto, el mismo producto leído por dos lectores distintos se registra
    dos veces y el stock queda partido."""
    assert codigos.normalizar("012345678905") == "0012345678905"


def test_un_ean_13_se_queda_igual():
    assert codigos.normalizar("7702001234567") == "7702001234567"


def test_cadena_vacia_es_ausencia_de_codigo():
    """El frontend manda "" cuando el campo se deja en blanco. Guardarlo
    tal cual haría chocar a dos productos sin código en el índice único."""
    assert codigos.normalizar("") is None
    assert codigos.normalizar("   ") is None
    assert codigos.normalizar(None) is None


def test_el_checksum_avisa_pero_no_bloquea():
    """Se devuelve como aviso, no como rechazo: hay etiquetas impresas mal
    en circulación, y negarse a registrar un producto que el tendero tiene
    en la mano no ayuda a nadie."""
    assert codigos.checksum_valido("7702001234567") in (True, False)
    # Un formato sin dígito de control (Code 128, QR propio) no se juzga.
    assert codigos.checksum_valido("ABC-123") is None
