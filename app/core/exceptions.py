"""
app/core/exceptions.py — Excepciones de negocio.

Los servicios (app/services/) no saben nada de HTTP: cuando algo sale
mal, lanzan una de estas excepciones. La capa de API (app/main.py) es la
única que sabe traducir "ErrorNegocio" a un 400, "NoEncontrado" a un 404,
etc. Esto es más limpio que el patrón de la app de escritorio (donde las
funciones devolvían strings como "Error: ..." y había que buscar la
palabra "éxito" en el texto) — aquí cada capa habla su propio idioma.
"""


class ErrorNegocio(Exception):
    """Regla de negocio violada (nombre duplicado, stock insuficiente, etc).
    Se traduce a HTTP 400."""


class NoEncontrado(Exception):
    """El recurso pedido no existe (o no pertenece al usuario). Se traduce
    a HTTP 404."""


class CredencialesInvalidas(Exception):
    """Login fallido o token inválido/expirado. Se traduce a HTTP 401."""


class SuscripcionVencida(Exception):
    """La cuenta existe y la sesión es válida, pero la suscripción caducó.
    Se traduce a HTTP 402 (Payment Required).

    Código propio y no un 400 o un 403 a propósito: el frontend tiene que
    poder distinguirlo sin leer el texto del mensaje. Ante un 402 muestra
    la pantalla de renovación; ante un 400 muestra un aviso y ya. Si
    fueran el mismo código, habría que comparar cadenas para decidir, y
    eso se rompe en cuanto alguien reescriba el mensaje.
    """