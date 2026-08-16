"""
app/core/numeros.py — Leer plata escrita como la escribe la gente.

Este archivo existe por un solo motivo, y es el fallo más peligroso que
puede tener el importador:

    En Colombia, "1.500" son mil quinientos pesos.
    Para float("1.500") son uno con cinco.

Si el importador se equivoca en eso, la tienda queda con el arroz a un peso
cincuenta en vez de a mil quinientos. Y NO HAY ERROR: la importación dice
"300 productos creados", el tendero empieza a vender, y descubre el
desastre cuando cuadra la caja al final del día. Es el peor tipo de fallo
posible en este sistema — silencioso y con plata de por medio.

Por eso la conversión vive en el backend y no en el frontend: es una regla
de negocio, no un detalle de presentación.

LA CONVENCIÓN COLOMBIANA (y de casi toda Latinoamérica menos México):
    punto  = separador de miles      1.500  = mil quinientos
    coma   = separador de decimales  1,5    = uno y medio

Excel exportado desde un Windows en español entrega los números así, y
también con el símbolo de peso pegado. Todo eso hay que aceptarlo.
"""

MAX_VALOR = 1_000_000_000  # mil millones: más que eso en una tienda es un dedazo


class NumeroInvalido(ValueError):
    """El texto no representa un número utilizable."""


def a_numero(valor, campo: str = "valor") -> float:
    """Convierte a número lo que venga de una celda de Excel.

    Acepta números ya convertidos (Excel a veces entrega float directo) y
    texto en las formas en que se escribe plata en Colombia.

    Lanza NumeroInvalido con un mensaje que nombra el campo, para que el
    reporte del importador pueda decir "fila 47, columna precio" en vez de
    un error genérico.
    """
    if valor is None:
        raise NumeroInvalido(f"Falta el {campo}")

    # Excel a veces entrega el número ya convertido. Se acepta tal cual: si
    # llegó como número, ninguna interpretación de separadores hace falta.
    if isinstance(valor, bool):
        # bool es subclase de int en Python y aquí nunca es lo que se quiere.
        raise NumeroInvalido(f"El {campo} no es un número")
    if isinstance(valor, (int, float)):
        return _validar(float(valor), campo)

    if not isinstance(valor, str):
        raise NumeroInvalido(f"El {campo} no es un número")

    limpio = valor.strip()
    if not limpio:
        raise NumeroInvalido(f"Falta el {campo}")

    # Fuera el símbolo de moneda, los espacios internos y el espacio duro
    # (\xa0), que Excel mete al formatear como moneda.
    for basura in ("$", "COP", "cop", "\xa0", " "):
        limpio = limpio.replace(basura, "")

    if not limpio:
        raise NumeroInvalido(f"Falta el {campo}")

    negativo = limpio.startswith("-")
    if negativo:
        limpio = limpio[1:]

    limpio = _quitar_separadores(limpio, campo)

    try:
        numero = float(limpio)
    except ValueError:
        raise NumeroInvalido(f"El {campo} '{valor}' no se entiende como un número")

    return _validar(-numero if negativo else numero, campo)


def _quitar_separadores(texto: str, campo: str) -> str:
    """Deja el texto en la forma que entiende float(), interpretando los
    separadores como se usan en Colombia."""
    tiene_punto = "." in texto
    tiene_coma = "," in texto

    # Caso claro: están los dos. El último que aparece es el decimal.
    # "1.500,50" -> 1500.50   y   "1,500.50" (formato inglés pegado) -> 1500.50
    if tiene_punto and tiene_coma:
        if texto.rfind(",") > texto.rfind("."):
            return texto.replace(".", "").replace(",", ".")
        return texto.replace(",", "")

    # Solo coma: es el separador decimal. "1500,50" -> 1500.50
    # Salvo que haya varias, que solo puede ser separador de miles mal
    # escrito: "1,500,000" -> 1500000
    if tiene_coma:
        if texto.count(",") > 1:
            return texto.replace(",", "")
        return texto.replace(",", ".")

    # Solo punto: es el caso ambiguo y el que importa.
    if tiene_punto:
        if texto.count(".") > 1:
            # "1.500.000" — varios puntos solo pueden ser miles.
            return texto.replace(".", "")

        entero, _, decimales = texto.partition(".")
        if len(decimales) == 3 and entero:
            # "1.500" o "12.000": tres dígitos después del punto es un
            # separador de miles en Colombia. Se lee como mil quinientos.
            #
            # ¿Y si alguien quiso decir "uno punto quinientos"? No existe:
            # en pesos colombianos no se manejan centavos, los precios son
            # números enteros. Esta es la lectura correcta el 100% de las
            # veces en este contexto, y la contraria destruiría el precio.
            return texto.replace(".", "")
        # "1.5" o "1.50": pocos decimales, se lee como decimal normal.
        return texto

    return texto


def _validar(numero: float, campo: str) -> float:
    if numero != numero or numero in (float("inf"), float("-inf")):  # NaN o infinito
        raise NumeroInvalido(f"El {campo} no es un número válido")
    if abs(numero) > MAX_VALOR:
        raise NumeroInvalido(
            f"El {campo} es demasiado grande ({numero:,.0f}). "
            "Revisa si sobra un cero o un separador."
        )
    return numero


def a_entero(valor, campo: str = "cantidad") -> int:
    """Como a_numero, pero para cantidades.

    Una cantidad con decimales se rechaza en vez de redondearse: "12,5
    cuadernos" es un error de captura, y redondearlo en silencio a 12 o 13
    esconde el problema en el inventario.
    """
    numero = a_numero(valor, campo)
    if numero != int(numero):
        raise NumeroInvalido(
            f"La {campo} '{valor}' tiene decimales. Debe ser un número entero de unidades."
        )
    return int(numero)
