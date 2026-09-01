"""
app/core/firma.py — Sellar un texto para reconocerlo cuando vuelva.

PARA QUÉ HACE FALTA

Cuando el tendero califica una respuesta de Trackie, el frontend nos manda
de vuelta la pregunta y la respuesta que se calificaron. El servidor no las
tiene guardadas: guardar todos los intercambios sería justamente lo que se
está evitando, porque una respuesta lleva las cifras del negocio.

Pero si el servidor acepta cualquier texto que le manden, cualquiera puede
llenar el panel de "Trackie dijo esto" con cosas que Trackie nunca dijo. Y
ese panel es el conjunto con el que algún día se entrena un clasificador:
datos envenenados ahí no se notan hasta mucho después.

CÓMO SE RESUELVE SIN GUARDAR NADA

Al responder, se devuelve también una firma del texto. Para calificar hay
que devolverla, y el servidor la recalcula: si no coincide, ese texto no
salió de aquí.

Es el mismo truco de las cookies firmadas. No cifra nada —la respuesta viaja
en claro, que para eso es del propio usuario— solo demuestra su origen.

LA COMPARACIÓN VA CON compare_digest

Comparar con `==` tarda distinto según cuántos caracteres coincidan, y de esa
diferencia se puede deducir la firma correcta byte a byte. `compare_digest`
tarda lo mismo siempre.
"""

import hashlib
import hmac

from app.core.config import settings

# Un separador que no puede aparecer dentro de los campos. Sin él, firmar
# ("ab", "c") y ("a", "bc") daría lo mismo, y se podría mover texto de la
# pregunta a la respuesta sin invalidar la firma.
SEPARADOR = "\x1f"


def firmar(*partes: str) -> str:
    """La firma de unos textos, en hexadecimal."""
    mensaje = SEPARADOR.join(partes).encode("utf-8")
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), mensaje, hashlib.sha256,
    ).hexdigest()


def es_valida(firma: str | None, *partes: str) -> bool:
    """Si esos textos salieron de aquí con esa firma."""
    if not firma:
        return False
    return hmac.compare_digest(firma, firmar(*partes))
