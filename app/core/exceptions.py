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