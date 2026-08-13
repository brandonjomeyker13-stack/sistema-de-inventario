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


def normalizar_fecha(valor: str) -> str:
    """Deja una fecha en 'YYYY-MM-DD', o lanza ValueError.

    Acepta también un datetime ISO completo y se queda con la parte de la
    fecha. No es por capricho: los selectores de calendario del navegador
    suelen entregar `toISOString()`, que devuelve algo como
    '2026-08-23T05:00:00.000Z'. Guardar eso tal cual haría que el cálculo
    de atrasos fallara al leerlo, y el error saldría lejos de su causa.

    Se corta por la 'T' en vez de parsear el datetime a propósito: nos
    interesa el día que el usuario tocó en el calendario, no convertirlo
    de zona horaria. Si eligió el 23, es el 23.
    """
    if not isinstance(valor, str):
        raise ValueError("La fecha debe venir como texto")

    limpio = valor.strip()
    if "T" in limpio:
        limpio = limpio.split("T", 1)[0]

    try:
        datetime.strptime(limpio, FORMATO_FECHA)
    except ValueError:
        raise ValueError(
            f"Fecha inválida: '{valor}'. Se espera el formato AAAA-MM-DD (por ejemplo 2026-08-23)"
        )
    return limpio


def fecha_valida(valor: str | None) -> str | None:
    """La fecha si es utilizable, o None si no lo es. Nunca lanza.

    Para columnas que se editan A MANO en el editor de Supabase, como
    `usuarios.suscripcion_hasta`. Ahí un dedazo del tipo '31/12/2026' o
    '2026-13-45' no es hipotético, y sin esto reventaba con ValueError en
    la comprobación de acceso — es decir, un 500 en TODAS las rutas
    protegidas de esa cuenta, y el mensaje del log no señalaba a la celda
    que había que corregir.

    Una fecha ilegible se trata como "sin fecha": deja la cuenta en solo
    lectura, que es molesto pero reversible y visible. Mucho mejor que
    tumbar la sesión entera.
    """
    if not valor:
        return None
    try:
        return normalizar_fecha(valor)
    except ValueError:
        return None


def sumar_dias(dias: int, desde: str | None = None) -> str:
    """Fecha resultante de sumar `dias` a `desde` (por defecto, hoy)."""
    base = datetime.strptime(desde, FORMATO_FECHA).date() if desde else ahora_local().date()
    return (base + timedelta(days=dias)).strftime(FORMATO_FECHA)


def dias_de_atraso(vencimiento: str | None) -> int:
    """Días que lleva vencida una fecha. 0 si no ha vencido o no hay plazo.

    Nunca devuelve negativos: "le faltan 3 días para vencer" no es un
    atraso, y mezclarlos en el mismo número obligaría a quien lo lea a
    recordar el signo.
    """
    if not vencimiento:
        return 0
    try:
        limite = datetime.strptime(vencimiento, FORMATO_FECHA).date()
    except ValueError:
        # Tolerante a propósito: la validación de entrada está en
        # normalizar_fecha, así que aquí no debería llegar basura. Pero si
        # una fila vieja o cargada a mano trae algo raro, es preferible
        # tratarla como "sin plazo" que tumbar la lista de deudores entera.
        return 0
    atraso = (ahora_local().date() - limite).days
    return max(atraso, 0)


def ultimos_dias(dias: int) -> list[str]:
    """Las últimas `dias` fechas terminando hoy, de la más reciente a la
    más antigua. Incluye el día de hoy: ultimos_dias(1) == [hoy].

    Se genera en Python y no en SQL a propósito: así los días sin ninguna
    venta también aparecen en el resumen (en cero) y el frontend no tiene
    que adivinar cuáles faltan para pintar las tarjetas.
    """
    hoy = ahora_local().date()
    return [(hoy - timedelta(days=i)).strftime(FORMATO_FECHA) for i in range(dias)]
