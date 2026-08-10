"""
app/core/codigos.py — Normalización y validación de códigos de barras.

Por qué existe: el mismo producto físico puede llegar con dos números
distintos según quién lo lea.

Un UPC-A tiene 12 dígitos y es lo que traen los productos importados de
Estados Unidos. Ese mismo código, en el estándar internacional EAN-13,
es exactamente el mismo con un cero delante. Unos lectores devuelven una
forma y otros la otra — incluso el mismo teléfono según la librería que
decodifique. Sin normalizar, el sistema cree que son dos productos y el
tendero acaba con el inventario duplicado sin entender por qué.

Se guarda todo en forma EAN-13, que es la más larga y de la que siempre
se puede volver atrás. Los códigos que no son EAN/UPC (Code 128, QR de
etiquetas propias) se dejan tal cual: no hay nada que normalizar ahí.
"""


def normalizar(codigo: str | None) -> str | None:
    """Deja el código en su forma canónica, o None si viene vacío."""
    if codigo is None:
        return None

    limpio = codigo.strip()
    if not limpio:
        return None

    # UPC-A (12 dígitos) -> EAN-13. Es el mismo código; el cero delante
    # es parte del estándar, no un relleno inventado.
    if limpio.isdigit() and len(limpio) == 12:
        return "0" + limpio

    return limpio


def checksum_valido(codigo: str | None) -> bool | None:
    """Comprueba el dígito de control de un EAN-13, UPC-A o EAN-8.

    Devuelve None cuando el código no es de un formato con dígito de
    control (Code 128, una etiqueta propia, un QR). None significa "no
    aplica", que no es lo mismo que False — y confundirlos llevaría a
    marcar como sospechoso todo lo que no sea un EAN.

    NO se usa para rechazar: sirve para avisar. Un checksum inválido casi
    siempre es una lectura mala de la cámara, y conviene decirlo antes de
    que alguien dé de alta un producto con un código fantasma.
    """
    if not codigo or not codigo.isdigit() or len(codigo) not in (8, 12, 13):
        return None

    digitos = [int(d) for d in codigo]
    control = digitos[-1]
    cuerpo = digitos[:-1]

    # De derecha a izquierda: el primero pesa 3, el siguiente 1, y así.
    total = 0
    for i, d in enumerate(reversed(cuerpo)):
        total += d * (3 if i % 2 == 0 else 1)

    return (10 - total % 10) % 10 == control
