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

TRES DEFENSAS CONTRA ACERTAR DE MÁS

1. Los disparadores son frases, no raíces. `acabando` y no `acab`, para que
   "acabo de vender" no se confunda con "se está acabando".
2. Las EXCLUSIONES anulan una coincidencia aunque un disparador dé positivo.
3. La tolerancia a erratas es corta a propósito: una letra, y solo entre
   palabras largas. Con dos letras, `acabo` alcanzaría a `acaban`.

LOS DISPARADORES SE ESCRIBEN COMO SE HABLA

Se guardan aquí en su forma natural, con tildes, y se normalizan al cargar
el módulo con la MISMA función que normaliza la pregunta del tendero. Es
deliberado: escritos ya normalizados a mano, un disparador como "añadir"
—que normalizado es "anadir"— se escribiría mal una vez y no coincidiría
nunca, sin dar ningún error.
"""

from app.core.texto import clave_nombre

# Solo se corrigen erratas entre palabras de este largo para arriba. En
# palabras cortas, una letra de diferencia suele ser otra palabra: "pedir" y
# "pedid", "venta" y "vento", "acabo" y "acaban".
MIN_LARGO_ERRATA = 6


def normalizar(texto: str | None) -> str:
    """La forma canónica de un texto: minúsculas, sin tildes, sin signos.

    Sobre lo que ya hace `clave_nombre` se añade convertir todo lo que no sea
    letra o número en un espacio. Sin eso, "¿qué comprar?" no contendría
    "que comprar", porque los signos quedarían pegados a las palabras.

    Esta es la forma que se GUARDA en la tabla de consultas. Se deja lo más
    fiel posible al texto original: dos maneras distintas de escribir mal la
    misma pregunta son dos ejemplos distintos para entrenar, y colapsarlas
    aquí perdería ese dato.
    """
    base = clave_nombre(texto)
    limpio = "".join(c if c.isalnum() else " " for c in base)
    # Se rodea de espacios para poder exigir palabras completas más abajo.
    return " " + " ".join(limpio.split()) + " "


def _fonetica(texto: str) -> str:
    """Pliega las letras que en español suenan igual.

    Un tendero escribiendo rápido en el celular no comete errores al azar:
    comete los de siempre, y son los que el oído no distingue. "akaban",
    "se acavan", "aora", "yamar". Plegando b/v, s/z/c, ll/y y la hache muda,
    todos esos caen en la misma forma que la palabra bien escrita.

    Se aplica igual a la pregunta y a los disparadores, así que las dos
    partes de la comparación quedan en el mismo alfabeto.

    NO se colapsan las dobles: "pero" y "perro" son palabras distintas.
    """
    salida = []
    i = 0
    while i < len(texto):
        letra = texto[i]
        siguiente = texto[i + 1] if i + 1 < len(texto) else ""

        if letra == "h":
            i += 1          # muda: "ahora" -> "aora"
            continue
        if letra == "v":
            salida.append("b")
        elif letra == "z":
            salida.append("s")
        elif letra == "c":
            # "ce/ci" suenan a s; "ca/co/cu" suenan a k.
            salida.append("s" if siguiente in "ei" else "k")
        elif letra == "q":
            salida.append("k")
            if siguiente == "u":
                i += 1      # "que" -> "ke"
        elif letra == "l" and siguiente == "l":
            salida.append("y")
            i += 1
        else:
            salida.append(letra)
        i += 1

    return "".join(salida)


def comparable(texto: str | None) -> str:
    """La forma con la que se COMPARA, más tolerante que la que se guarda."""
    return _fonetica(normalizar(texto))


def _comparables(frases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(comparable(f).strip() for f in frases)


# Si la pregunta trae una de estas, el enrutador NO responde aunque coincida
# con alguna intención. Son verbos de hacer, y hacer no es cosa suya: el
# asistente propone acciones y el tendero las confirma (ver
# asistente_service/acciones.py). Una plantilla que respondiera "tienes 12
# productos" a un "créame un producto" sería peor que no responder.
PALABRAS_DE_ACCION = _comparables((
    "crear", "crea", "creame", "registrar", "registra", "registrame",
    "agregar", "agrega", "agregame", "añadir", "añade", "añademe",
    "meter", "mete", "meteme", "vender", "vende", "vendeme",
    "borrar", "borra", "eliminar", "elimina", "quitar", "quita",
    "cambiar", "cambia", "actualizar", "actualiza", "modificar", "modifica",
    "ponle", "cambiale", "subir", "sube", "bajar", "baja",
    "llegaron", "llego", "me llego", "entro mercancia",
))


# "acabo de vender" no habla de que algo se esté acabando: habla de que algo
# pasó hace un momento. Es una perífrasis de pasado reciente —acabar + de +
# infinitivo— y en español no tiene nada que ver con agotarse.
#
# Sin esto, "acabo de hacer una venta" o "se me acaba de cerrar la
# aplicación" caerían en la lista de compra en cuanto se active la tolerancia
# a erratas, y el tendero recibiría un pedido de proveedor por contar algo
# que le acababa de pasar.
PASADO_RECIENTE = (
    "acabo de", "acaba de", "acabas de", "acabamos de", "acaban de",
    "acababa de",
)


# El catálogo. El orden no importa: si dos coinciden, no responde ninguna.
#
# Cada intención nombra una función de datos.py y una de redaccion.py. Se
# nombran con texto y no con la función misma para que este archivo no tenga
# que importar nada que toque la base de datos: así se puede leer, probar y
# ajustar sin levantar una sesión.
#
# `nunca_si` son las frases que anulan la coincidencia de ESA intención.
INTENCIONES: tuple[dict, ...] = (
    {
        "nombre": "lista_de_compra",
        "disparadores": (
            "comprar", "que compro", "pedido", "pedir", "proveedor",
            "hace falta", "acabando", "por acabarse", "reponer", "surtir",
            # Preguntar por el stock bajo es preguntar qué hay que comprar.
            "stock bajo", "poco stock", "quedan pocos", "quedan pocas",
            # En presente es "se está acabando"; en pasado ("se me acabó")
            # ya es un producto agotado, y esa es otra intención.
            "se acaban", "se me acaban", "se estan acabando", "acabandose",
        ),
        "nunca_si": PASADO_RECIENTE,
    },
    {
        "nombre": "ventas_de_hoy",
        "disparadores": (
            "cuanto vendi", "cuanto he vendido", "cuanto llevo vendido",
            "ventas de hoy", "vendi hoy", "venta de hoy",
        ),
        "nunca_si": PASADO_RECIENTE,
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
        "nunca_si": PASADO_RECIENTE,
    },
    {
        "nombre": "valor_inventario",
        "disparadores": (
            "cuanto vale mi inventario", "cuanto vale el inventario",
            "valor del inventario", "valor de mi inventario",
            "cuanto tengo invertido", "cuanto tengo en inventario",
            "cuantos productos tengo", "cuantos productos hay",
        ),
    },
    # --- Las tres que no consultan nada del negocio ----------------------
    {
        # Lo más escrito en cualquier chat: todo el mundo saluda antes de
        # preguntar. Sin esto, cada "hola" se va al modelo, gasta tokens y
        # hace esperar, para responder "hola".
        "nombre": "saludo",
        "disparadores": (
            "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
            "como estas", "que tal", "gracias", "muchas gracias", "listo gracias",
        ),
        # Un saludo es un PREFIJO, no una intención. Casi nadie escribe solo
        # "hola": escribe "hola, ¿cuántos productos tengo?".
        #
        # Sin esta regla, "hola" ganaría la clasificación de una pregunta de
        # verdad y el tendero recibiría un saludo por respuesta. Y en el mejor
        # caso chocaría con la otra intención y no respondería ninguna.
        #
        # Así que esta intención solo se activa cuando la frase ENTERA es un
        # saludo. En cuanto aparece una palabra que no lo es, se aparta y deja
        # que decidan las demás.
        "solo_si_es_todo": True,
    },
    {
        # La primera pregunta de casi cualquiera que abre el chat. Y responder
        # esto con el modelo es peligroso: tiene los datos del negocio pero no
        # la lista de sus propias capacidades, así que improvisa y puede
        # prometer funciones que no existen.
        "nombre": "ayuda",
        "disparadores": (
            "que puedes hacer", "que sabes hacer", "que es esto", "para que sirves",
            "en que me ayudas", "como funciona esto", "que preguntas puedo hacer",
            "ayuda",
        ),
    },
    {
        # "Se me cerró la aplicación" es una pregunta legítima y frecuente, y
        # no es de inventario. Sin esta intención se iría al modelo, que le
        # respondería con datos del negocio a alguien que reporta un fallo.
        "nombre": "soporte",
        "disparadores": (
            "no funciona", "no me funciona", "se traba", "se me traba",
            "se cerro", "se me cerro", "no carga", "no me carga",
            "esta fallando", "da error", "la aplicacion", "la app",
        ),
    },
)

# Se precalcula al cargar para no normalizar el catálogo entero en cada
# pregunta.
_DISPARADORES = {i["nombre"]: _comparables(i["disparadores"]) for i in INTENCIONES}
_EXCLUSIONES = {i["nombre"]: _comparables(i.get("nunca_si", ())) for i in INTENCIONES}

# Las intenciones que solo valen si la frase entera es de ellas, con su
# vocabulario: todas las palabras de todos sus disparadores.
_SOLO_SI_ES_TODO = {
    i["nombre"]: {palabra
                  for frase in _comparables(i["disparadores"])
                  for palabra in frase.split()}
    for i in INTENCIONES if i.get("solo_si_es_todo")
}

NOMBRES = tuple(i["nombre"] for i in INTENCIONES)

# Saludos que se devuelven cuando la pregunta empieza por ellos.
#
# Saludar no cambia QUÉ preguntó el tendero, cambia CÓMO se le responde. Por
# eso esto no es una intención ni una etiqueta: si lo fuera, el día de
# entrenar el modelo habría que multiplicar las clases —saludo+ganancia,
# saludo+fiados, saludo+compra— y cada una tendría una fracción de los
# ejemplos. La etiqueta se queda en la intención; el saludo se devuelve al
# redactar.
#
# Se guarda la forma bien escrita porque la comparación va sin tildes, y
# responder "Buenos dias" quedaría descuidado.
SALUDOS_INICIALES = {
    comparable(k).strip(): v for k, v in {
        "buenos días": "Buenos días",
        "buenas tardes": "Buenas tardes",
        "buenas noches": "Buenas noches",
        "hola": "Hola",
        "buenas": "Buenas",
    }.items()
}


def saludo_inicial(pregunta: str) -> str | None:
    """El saludo con el que arranca la pregunta, si hay alguno.

    Se miran primero los de dos palabras para que "buenas tardes" no se
    quede en "Buenas".
    """
    palabras = comparable(pregunta).split()
    for frase in sorted(SALUDOS_INICIALES, key=lambda f: -len(f.split())):
        trozo = frase.split()
        if palabras[:len(trozo)] == trozo:
            return SALUDOS_INICIALES[frase]
    return None

# Las que solo dan una respuesta fija, sin mirar el negocio. El asistente las
# usa para saber que no hace falta tocar la base de datos.
SIN_DATOS = ("saludo", "ayuda", "soporte")


def _a_una_letra(a: str, b: str) -> bool:
    """Si dos palabras se diferencian como mucho en una letra.

    Cubre las tres erratas de teclear rápido: cambiar una letra, comerse
    una, o meter una de más. Se para en la primera diferencia porque no
    hace falta saber cuántas hay: con dos ya no coincide.
    """
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False

    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1

    corta, larga = (a, b) if len(a) < len(b) else (b, a)
    i = j = saltos = 0
    while i < len(corta) and j < len(larga):
        if corta[i] == larga[j]:
            i += 1
        else:
            saltos += 1
            if saltos > 1:
                return False
        j += 1
    return True


def _parecidas(a: str, b: str) -> bool:
    """Iguales, o a una letra si las dos son largas.

    El corte por largo es la defensa: en palabras cortas una letra de
    diferencia suele ser otra palabra distinta, no una errata.
    """
    if a == b:
        return True
    if len(a) < MIN_LARGO_ERRATA or len(b) < MIN_LARGO_ERRATA:
        return False
    return _a_una_letra(a, b)


def _contiene(pregunta: str, frase: str) -> bool:
    """Si la frase aparece en la pregunta, tolerando erratas.

    Primero se busca la coincidencia exacta, que es lo normal y lo barato.
    Solo si falla se comparan las palabras una por una deslizando la frase
    por la pregunta.
    """
    if f" {frase} " in pregunta:
        return True

    palabras_frase = frase.split()
    palabras = pregunta.split()
    largo = len(palabras_frase)
    if largo > len(palabras):
        return False

    for inicio in range(len(palabras) - largo + 1):
        ventana = palabras[inicio:inicio + largo]
        if all(_parecidas(p, f) for p, f in zip(ventana, palabras_frase)):
            return True
    return False


def clasificar(pregunta: str) -> str | None:
    """La intención de la pregunta, o None si no hay una sola clara.

    Devuelve None en cuatro casos, y los cuatro significan lo mismo —que
    responda el modelo—: la pregunta pide una acción, no coincide con
    ninguna intención, coincide con más de una, o la única que coincidía
    quedó anulada por una exclusión.
    """
    texto = comparable(pregunta)
    if not texto.strip():
        return None

    # Las exclusiones y los verbos de hacer se comprueban SIN tolerancia a
    # erratas: son la defensa, y una defensa que se activa por parecido
    # empezaría a bloquear preguntas legítimas.
    if any(f" {p} " in texto for p in PALABRAS_DE_ACCION):
        return None

    palabras = texto.split()

    encontradas = []
    for nombre, frases in _DISPARADORES.items():
        if not any(_contiene(texto, f) for f in frases):
            continue
        if any(f" {e} " in texto for e in _EXCLUSIONES[nombre]):
            continue
        # "hola" no puede ganarle a "¿cuántos productos tengo?" solo por ir
        # delante. Ver `solo_si_es_todo` en el catálogo.
        vocabulario = _SOLO_SI_ES_TODO.get(nombre)
        if vocabulario is not None and not all(p in vocabulario for p in palabras):
            continue
        encontradas.append(nombre)

    return encontradas[0] if len(encontradas) == 1 else None
