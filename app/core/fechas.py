"""
app/core/fechas.py — Fechas en la hora del negocio, no la del servidor.

Por qué existe este archivo: `datetime.now()` devuelve la hora local de
la máquina donde corre el proceso. En tu portátil eso es Colombia, pero
Render corre en UTC — así que en producción una venta de las 7:30 p.m.
se guardaba con la fecha del día siguiente, y el corte del día quedaba
descuadrado justo en las horas de mayor venta de una tienda.

La solución no es "restarle 5 horas": eso se rompe si algún día hay un
cliente en otro huso. Se usa una zona horaria con nombre (ZONA_HORARIA
en config), que además maneja sola los cambios de horario de verano en
los países que lo tienen.

Nadie más en el proyecto debería llamar a `datetime.now()` para obtener
la fecha de un dato de negocio. Se usa `hoy_local()`.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

FORMATO_FECHA = "%Y-%m-%d"


def _zona() -> ZoneInfo:
    return ZoneInfo(settings.ZONA_HORARIA)


def ahora_local() -> datetime:
    """Momento actual en la zona horaria del negocio (con tzinfo)."""
    return datetime.now(_zona())


def hoy_local() -> str:
    """Fecha de hoy en el negocio, como 'YYYY-MM-DD'."""
    return ahora_local().strftime(FORMATO_FECHA)


def ultimos_dias(dias: int) -> list[str]:
    """Las últimas `dias` fechas terminando hoy, de la más reciente a la
    más antigua. Incluye el día de hoy: ultimos_dias(1) == [hoy].

    Se genera en Python y no en SQL a propósito: así los días sin ninguna
    venta también aparecen en el resumen (en cero) y el frontend no tiene
    que adivinar cuáles faltan para pintar las tarjetas.
    """
    hoy = ahora_local().date()
    return [(hoy - timedelta(days=i)).strftime(FORMATO_FECHA) for i in range(dias)]
