"""
app/core/texto.py — Comparar nombres como los compara una persona.

Un tendero que ya tiene "Café" y escribe "cafe" no está creando otro
producto: está escribiendo el mismo sin tilde porque el teclado del celular
le estorba. Si el sistema los trata como distintos, su stock queda partido
en dos y no entiende por qué las cuentas no cuadran.

POR QUÉ NO SE DEJA ESTO A LA BASE DE DATOS

Antes la comparación era un `ILIKE` de SQL, y eso se comporta DISTINTO en
cada motor:

    'CAFÉ' vs 'Café'   ->  PostgreSQL: iguales    SQLite: distintos

Las pruebas corren en SQLite y producción en PostgreSQL, así que una prueba
podía pasar en local mientras el comportamiento real era otro. Es la peor
clase de fallo: el que solo aparece desplegado.

Calculando la llave en Python, las dos bases se comportan igual y la regla
queda escrita en un sitio que se puede leer y probar.

SOBRE LA EÑE

Se le quita la virgulilla igual que a las tildes, así que "Piña" y "Pina"
son el mismo producto. Es a propósito: quien escribe "pina" en una lista de
inventario quiere decir piña. El riesgo teórico son palabras que solo se
distinguen por la eñe ("año" y "ano"), y ninguna es un nombre de producto.
"""

import unicodedata


def clave_nombre(valor: str | None) -> str:
    """La forma canónica de un nombre, para comparar y buscar duplicados.

    Minúsculas, sin tildes, con los espacios internos colapsados. NO es lo
    que se muestra en pantalla — el nombre original se guarda tal como lo
    escribió el tendero, con sus tildes y sus mayúsculas.

        clave_nombre("  CAFÉ   Molido ")  ->  "cafe molido"
        clave_nombre("Piña")              ->  "pina"
    """
    if not valor:
        return ""

    # NFD separa cada letra de su acento ("é" -> "e" + tilde suelta), y
    # luego se descartan las marcas (categoría Mn = Mark, nonspacing).
    descompuesto = unicodedata.normalize("NFD", valor)
    sin_acentos = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")

    return " ".join(sin_acentos.split()).lower()
