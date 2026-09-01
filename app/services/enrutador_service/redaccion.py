"""
Cómo se escribe cada respuesta. SOLO TEXTO, ninguna consulta.

Es el equivalente de `asistente_service/instrucciones.py`: allí se le explica
al modelo cómo hablar, aquí se habla directamente. Mismo tono —corto,
directo, como quien está detrás del mostrador— y mismo formato de precios.

REGLA PARA MANTENERLO

Ninguna función de aquí recibe una sesión de base de datos. Si para redactar
algo hace falta un dato que no está en el diccionario que llega, el arreglo
es añadir ese campo en datos.py, no consultarlo aquí.

SOBRE LOS CASOS VACÍOS

Cada respuesta empieza por ellos. Una cuenta recién creada tiene cero
productos, cero ventas y cero deudores, y es justo cuando el tendero está
decidiendo si esto le sirve. Un "tienes 0 productos por comprar" suena a
error; "no te falta nada por pedir" suena a respuesta.
"""


def pesos(valor: float | int) -> str:
    """Un monto como se escribe en Colombia: $4.000, sin decimales.

    El separador de miles es el punto. Python usa la coma, así que se
    formatea con coma y se cambia — hacerlo al revés (reemplazar en el
    número) rompería los decimales antes de quitarlos.
    """
    return "$" + f"{round(valor):,}".replace(",", ".")


def _enumerar(nombres: list[str]) -> str:
    """'Cuaderno, Lápiz y Borrador'."""
    if not nombres:
        return ""
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _muestra(datos: dict, singular: str, plural: str, cierre: str) -> str:
    """El texto de un grupo del inventario: cuántos son y algunos nombres.

    Nunca da a entender que los nombres son todos: cuando la cuenta supera
    la muestra, lo dice y remite a la pantalla de inventario, que es donde
    sí están completos.
    """
    cuantos = datos["cuantos"]
    if cuantos == 0:
        return ""

    nombres = _enumerar(datos["algunos"])
    if datos["hay_mas"]:
        return f"Tienes {cuantos} {plural}. Algunos: {nombres}. {cierre}"
    if cuantos == 1:
        return f"Tienes 1 {singular}: {nombres}."
    return f"Tienes {cuantos} {plural}: {nombres}."


def lista_de_compra(datos: dict) -> str:
    """El pedido, copiado tal cual.

    El texto va sin tocar ni una palabra. Es la misma lista que el tendero
    ve en la pantalla de inventario, y si las dos no coinciden deja de
    confiar en ambas.
    """
    if datos["total"] == 0:
        return "Por ahora no te falta nada por pedir. Todo está por encima del mínimo."

    aviso = ""
    if datos["agotados"]:
        aviso = (f" Ojo que {datos['agotados']} ya está en cero."
                 if datos["agotados"] == 1
                 else f" Ojo que {datos['agotados']} ya están en cero.")

    return f"Esto es lo que te toca comprar.{aviso}\n\n{datos['texto']}"


def ventas_de_hoy(datos: dict) -> str:
    if datos["cuantas"] == 0:
        return "Hoy todavía no has registrado ninguna venta."

    veces = "1 venta" if datos["cuantas"] == 1 else f"{datos['cuantas']} ventas"
    return (f"Hoy llevas {veces} por {pesos(datos['vendido'])}, "
            f"con {pesos(datos['ganancia'])} de ganancia.")


def ganancia_de_hoy(datos: dict) -> str:
    """La misma consulta que las ventas, pero la ganancia va primero.

    No es un detalle de estilo: quien pregunta cuánto ganó no está
    preguntando cuánto vendió, y darle el número grande de las ventas
    cuando pidió la ganancia es exactamente la confusión que el producto
    vino a quitar. Se le da lo que pidió, y lo otro como referencia.
    """
    if datos["cuantas"] == 0:
        return "Hoy todavía no has registrado ninguna venta, así que no hay ganancia que contar."

    return (f"Hoy llevas {pesos(datos['ganancia'])} de ganancia, "
            f"sobre {pesos(datos['vendido'])} vendidos.")


def fiados(datos: dict) -> str:
    if datos["cuantos"] == 0:
        return "No te debe nadie. La libreta está en cero."

    quienes = _enumerar([
        f"{d['nombre']} {pesos(d['debe'])}" for d in datos["algunos"]
    ])
    gente = "1 persona" if datos["cuantos"] == 1 else f"{datos['cuantos']} personas"
    texto = f"Te deben {pesos(datos['total'])} entre {gente}: {quienes}."

    if datos["cuantos"] > len(datos["algunos"]):
        texto += " Los demás los ves en la pantalla de fiados."
    if datos["atrasados"]:
        texto += (" Hay 1 que ya se pasó de la fecha."
                  if datos["atrasados"] == 1
                  else f" Hay {datos['atrasados']} que ya se pasaron de la fecha.")
    return texto


def sin_codigo(datos: dict) -> str:
    if datos["cuantos"] == 0:
        return "Todos tus productos ya tienen código de barras."

    texto = _muestra(
        datos, "producto sin código de barras", "productos sin código de barras",
        "Los ves todos en inventario con el filtro de sin código.",
    )
    # Se explica para qué sirve ponérselos: sin eso, la cuenta es un dato
    # suelto. Con eso, es una tarea que entiende para qué hace.
    return texto + (" Poniéndoselos los puedes vender pasando el lector o "
                    "la cámara del celular, sin buscarlos por nombre.")


def agotados(datos: dict) -> str:
    if datos["cuantos"] == 0:
        return "No tienes nada agotado ahora mismo."

    return _muestra(
        datos, "producto agotado", "productos agotados",
        "Los ves todos en inventario filtrando por agotados.",
    )


def valor_inventario(datos: dict) -> str:
    if datos["cuantos_productos"] == 0:
        return "Todavía no tienes productos cargados, así que no hay inventario que valorar."

    return (f"Tienes {pesos(datos['al_costo'])} invertidos en mercancía. "
            f"Si la vendieras toda a precio de venta serían "
            f"{pesos(datos['al_precio_de_venta'])}, "
            f"repartidos en {datos['cuantos_productos']} productos.")


# --- Las tres que no miran el negocio ------------------------------------

def saludo(_datos: dict) -> str:
    """Corto a propósito: un saludo largo estorba a quien viene con prisa."""
    return ("Hola. Pregúntame por tus ventas, tu inventario o los fiados. "
            "También te digo qué te toca comprar.")


# Qué hace cada intención, en palabras del tendero. El diccionario vive aquí
# —es texto— pero la LISTA de intenciones vive en intenciones.py, y una
# prueba comprueba que no falte ninguna.
#
# Así la ayuda se genera del catálogo real y no puede quedar desactualizada:
# si mañana se agrega una intención y no se le escribe la línea, falla la
# prueba en vez de que el tendero lea una ayuda incompleta.
QUE_SE_PUEDE_PREGUNTAR = {
    "lista_de_compra": "Qué tienes que comprar",
    "ventas_de_hoy": "Cuánto has vendido hoy",
    "ganancia_de_hoy": "Cuánto has ganado hoy",
    "fiados": "Quién te debe y cuánto",
    "sin_codigo": "Qué productos no tienen código de barras",
    "agotados": "Qué se te acabó",
    "valor_inventario": "Cuánto vale tu inventario",
}


def ayuda(_datos: dict) -> str:
    """Lo que Trackie sabe hacer, sacado del catálogo de intenciones.

    Se genera y no se escribe a mano porque una lista escrita a mano se
    queda vieja en cuanto se agrega una intención — y prometerle a un
    tendero algo que no existe es peor que no explicárselo.
    """
    from app.services.enrutador_service.intenciones import NOMBRES

    lineas = [QUE_SE_PUEDE_PREGUNTAR[n] for n in NOMBRES
              if n in QUE_SE_PUEDE_PREGUNTAR]

    return ("Te respondo sobre tu negocio con los datos que ya tienes "
            "cargados. Por ejemplo:\n\n"
            + "\n".join(f"· {l}" for l in lineas)
            + "\n\nTambién puedo proponerte crear un producto o registrar "
              "mercancía que llegó, para que tú confirmes.")


def soporte(_datos: dict) -> str:
    """No se le responde con datos del negocio a quien reporta un fallo.

    Sin esta intención, "se me cierra la aplicación" se iba al modelo, que
    con el inventario delante y sin saber nada del estado del sistema
    contestaba cualquier cosa.
    """
    return ("Eso suena a un problema de la aplicación y no lo puedo arreglar "
            "yo desde aquí. Cierra y vuelve a entrar; si sigue igual, "
            "escríbenos y lo revisamos.")
