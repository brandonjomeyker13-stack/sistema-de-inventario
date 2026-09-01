"""
Qué preguntas reconoce el enrutador. SOLO DATOS Y CLASIFICACIÓN.

Aquí no se consulta la base ni se redacta nada: este archivo solo sabe que
"¿qué tengo que comprar?" y "hazme el pedido del proveedor" son la misma
intención. Qué se consulta para responderla está en datos.py, y cómo se
escribe la respuesta en redaccion.py.

LA REGLA QUE GOBIERNA TODO ESTE ARCHIVO

Fallar hacia el lado barato. Si una pregunta no coincide con nada, o
coincide con DOS intenciones a la vez, el enrutador no responde: cede al
modelo, que es exactamente lo que pasa hoy siempre.

Perder una coincidencia cuesta una llamada al modelo. Acertar de más cuesta
darle al tendero una respuesta que no era la que preguntó, con toda
seguridad y sin ningún error visible. Por eso ante la duda no se contesta.

LOS DISPARADORES SE ESCRIBEN COMO SE HABLA

Se guardan aquí en su forma natural, con tildes, y se normalizan al cargar
el módulo con la MISMA función que normaliza la pregunta del tendero. Es
deliberado: escritos ya normalizados a mano, un disparador como "añadir"
—que normalizado es "anadir"— se escribiría mal una vez y no coincidiría
nunca, sin dar ningún error.
"""

from app.core.texto import clave_nombre


def normalizar(texto: str | None) -> str:
    """La forma en que se comparan pregunta y disparadores.

    Sobre lo que ya hace `clave_nombre` (minúsculas, sin tildes, espacios
    colapsados) se añade convertir todo lo que no sea letra o número en un
    espacio. Sin eso, "¿qué comprar?" no contendría "que comprar", porque
    los signos quedarían pegados a las palabras de los extremos.
    """
    base = clave_nombre(texto)
    limpio = "".join(c if c.isalnum() else " " for c in base)
    # Se rodea de espacios para poder exigir palabras completas más abajo.
    return " " + " ".join(limpio.split()) + " "


def _normalizados(frases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalizar(f).strip() for f in frases)


# Si la pregunta trae una de estas, el enrutador NO responde aunque coincida
# con alguna intención. Son verbos de hacer, y hacer no es cosa suya: el
# asistente propone acciones y el tendero las confirma (ver
# asistente_service/acciones.py). Una plantilla que respondiera "tienes 12
# productos" a un "créame un producto" sería peor que no responder.
PALABRAS_DE_ACCION = _normalizados((
    "crear", "crea", "creame", "registrar", "registra", "registrame",
    "agregar", "agrega", "agregame", "añadir", "añade", "añademe",
    "meter", "mete", "meteme", "vender", "vende", "vendeme",
    "borrar", "borra", "eliminar", "elimina", "quitar", "quita",
    "cambiar", "cambia", "actualizar", "actualiza", "modificar", "modifica",
    "ponle", "cambiale", "subir", "sube", "bajar", "baja",
    "llegaron", "llego", "me llego", "entro mercancia",
))


# El catálogo. El orden no importa: si dos coinciden, no responde ninguna.
#
# Cada intención nombra una función de datos.py y una de redaccion.py. Se
# nombran con texto y no con la función misma para que este archivo no tenga
# que importar nada que toque la base de datos: así se puede leer, probar y
# ajustar sin levantar una sesión.
INTENCIONES: tuple[dict, ...] = (
    {
        "nombre": "lista_de_compra",
        "disparadores": (
            "comprar", "que compro", "pedido", "pedir", "proveedor",
            "hace falta", "acabando", "por acabarse", "reponer", "surtir",
        ),
    },
    {
        "nombre": "ventas_de_hoy",
        "disparadores": (
            "cuanto vendi", "cuanto he vendido", "cuanto llevo vendido",
            "ventas de hoy", "vendi hoy", "venta de hoy",
        ),
    },
    {
        "nombre": "ganancia_de_hoy",
        "disparadores": (
            "cuanto gane", "cuanto he ganado", "cuanto llevo ganado",
            "ganancia de hoy", "ganancia hoy", "gane hoy", "utilidad de hoy",
        ),
    },
    {
        "nombre": "fiados",
        "disparadores": (
            "quien me debe", "quien debe", "cuanto me deben", "fiado", "fiados",
            "deudas", "deudores", "libreta", "por cobrar",
        ),
    },
    {
        "nombre": "sin_codigo",
        "disparadores": (
            "sin codigo", "sin codigos", "no tienen codigo", "no tiene codigo",
            "falta el codigo", "faltan codigo", "faltan por codigo",
            "por escanear", "sin qr",
        ),
    },
    {
        "nombre": "agotados",
        "disparadores": (
            "agotado", "agotados", "sin stock", "en cero", "se acabo",
            "se me acabo", "no me queda", "no queda nada",
        ),
    },
    {
        "nombre": "valor_inventario",
        "disparadores": (
            "cuanto vale mi inventario", "cuanto vale el inventario",
            "valor del inventario", "valor de mi inventario",
            "cuanto tengo invertido", "cuanto tengo en inventario",
        ),
    },
)

# Se precalcula al cargar para no normalizar el catálogo entero en cada
# pregunta. Es un diccionario {nombre: disparadores ya normalizados}.
_DISPARADORES = {
    i["nombre"]: _normalizados(i["disparadores"]) for i in INTENCIONES
}

NOMBRES = tuple(i["nombre"] for i in INTENCIONES)


def _contiene(pregunta: str, frase: str) -> bool:
    """Si la frase aparece como palabras completas dentro de la pregunta.

    Con un `in` a secas, el disparador "pedir" coincidiría dentro de
    "impedir" y "en cero" dentro de "en ceros". Como `normalizar` deja la
    pregunta rodeada de espacios, basta con rodear también la frase.
    """
    return f" {frase} " in pregunta


def clasificar(pregunta: str) -> str | None:
    """La intención de la pregunta, o None si no hay una sola clara.

    Devuelve None en tres casos, y los tres significan lo mismo —que
    responda el modelo—: la pregunta pide una acción, no coincide con
    ninguna intención, o coincide con más de una.
    """
    normalizada = normalizar(pregunta)
    if not normalizada.strip():
        return None

    if any(_contiene(normalizada, p) for p in PALABRAS_DE_ACCION):
        return None

    encontradas = [
        nombre for nombre, frases in _DISPARADORES.items()
        if any(_contiene(normalizada, f) for f in frases)
    ]

    return encontradas[0] if len(encontradas) == 1 else None
