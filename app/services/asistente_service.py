"""
app/services/asistente_service.py — El asistente que conoce el negocio.

Dos decisiones que definen todo este archivo:

1. EL CONTEXTO NO ES EL INVENTARIO ENTERO. Mandarle los 500 productos al
   modelo en cada pregunta es caro, lento y deja de caber. Se le manda el
   resumen de analítica —lo que ya calculamos— más los productos que la
   pregunta menciona. Compacto y suficiente para lo que un tendero
   pregunta de verdad.

2. EL ASISTENTE PROPONE, NO EJECUTA. Cuando detecta que le están pidiendo
   crear un producto o registrar mercancía, devuelve una acción propuesta
   con su frase de confirmación. Quien ejecuta es el frontend, llamando al
   endpoint normal, y solo después de que el tendero diga que sí.

   Esto no es exceso de celo: la entrada suele ser voz, y "cuatro mil" y
   "catorce mil" suenan casi igual con una nevera de fondo. Un producto
   creado con el precio mal se vende mal durante días sin que nadie lo
   note.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio
from app.core.fechas import hoy_local
from app.core.llm import completar_json
from app.repositories import producto_repository, usuario_repository
from app.core.sectores import SECTORES
from app.services import analitica_service, cliente_service, venta_service

# Acciones que el asistente puede PROPONER. Lista cerrada: si el modelo
# se inventa otra, se descarta. Un catálogo abierto significaría ejecutar
# lo que se le ocurra al modelo, y eso no puede pasar ni con confirmación.
ACCIONES_PERMITIDAS = ("crear_producto", "registrar_entrada")

MAX_PRODUCTOS_EN_CONTEXTO = 12

INSTRUCCIONES = """\
Eres el asistente de una tienda pequeña en Colombia. Hablas con el dueño \
del negocio, que no es técnico. Responde en español, corto y directo, \
como quien está detrás del mostrador. Nada de tecnicismos ni listas largas.

Solo puedes usar los datos que te doy en el contexto. Si te preguntan algo \
que no está ahí, dilo claramente en vez de inventarlo. Nunca te inventes \
cifras, precios ni nombres de productos.

Los precios son pesos colombianos: escríbelos como $4.000, sin decimales.

Si el dueño te pide crear un producto o registrar mercancía que llegó, NO \
digas que ya lo hiciste. Devuelve la acción propuesta y una frase de \
confirmación clara con todos los datos, para que él confirme antes.

Responde SIEMPRE con este JSON y nada más:
{
  "respuesta": "lo que le dices al dueño",
  "accion": null
}

Cuando detectes una intención de crear producto o registrar entrada, en \
lugar de null pon:
{
  "tipo": "crear_producto",
  "datos": {"nombre": "...", "precio": 0, "cuanto_costo": 0, "cantidad": 0, "codigo_barras": null},
  "confirmacion": "¿Creo el producto X a $Y, con Z unidades?"
}
o
{
  "tipo": "registrar_entrada",
  "datos": {"nombre_producto": "...", "cantidad": 0, "costo_unitario": null},
  "confirmacion": "¿Registro la entrada de N unidades de X?"
}

Si falta algún dato para la acción, no la propongas: pregunta por lo que \
falta en "respuesta" y deja "accion" en null.
"""


def _palabras_clave(pregunta: str) -> list[str]:
    """Palabras de la pregunta que valen para buscar productos.

    Se descartan las cortas porque 'de', 'que' o 'hay' harían coincidir
    medio inventario y llenarían el contexto de ruido.

    De cada palabra en plural se genera también el singular. No es un
    lujo: el tendero pregunta "¿cuántos cuadernos me quedan?" y el
    producto se llama "Cuaderno argollado" — sin esto, la búsqueda no
    encuentra nada y el asistente responde que no sabe de un producto que
    tiene delante.
    """
    limpio = "".join(c if c.isalnum() else " " for c in pregunta.lower())

    terminos: list[str] = []
    for palabra in limpio.split():
        if len(palabra) <= 3:
            continue
        if palabra not in terminos:
            terminos.append(palabra)
        # "cuadernos" -> "cuaderno", "lapices" -> "lapice" (que igual
        # coincide con "lápiz" por prefijo en muchos casos).
        for sufijo in ("es", "s"):
            if palabra.endswith(sufijo) and len(palabra) - len(sufijo) > 3:
                raiz = palabra[: -len(sufijo)]
                if raiz not in terminos:
                    terminos.append(raiz)
                break

    return terminos[:8]


def _productos_relevantes(db: Session, usuario_id: str, pregunta: str) -> list[dict]:
    """Los productos que la pregunta menciona, no el catálogo entero."""
    encontrados: dict[str, object] = {}
    for palabra in _palabras_clave(pregunta):
        for p in producto_repository.listar(db, usuario_id, q=palabra, limite=5):
            encontrados[p.id] = p
        if len(encontrados) >= MAX_PRODUCTOS_EN_CONTEXTO:
            break

    return [
        {
            "nombre": p.nombre,
            "precio": p.precio,
            "costo": p.cuanto_costo,
            "stock": p.cantidad,
            "codigo_barras": p.codigo_barras,
        }
        for p in list(encontrados.values())[:MAX_PRODUCTOS_EN_CONTEXTO]
    ]


def construir_contexto(db: Session, usuario_id: str, pregunta: str) -> dict:
    """Todo lo que el modelo necesita saber, en pocos cientos de tokens."""
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    resumen = analitica_service.resumen(db, usuario_id, 30)
    ventas_hoy, ganancia_hoy = venta_service.ventas_por_fecha(db, usuario_id, hoy_local())
    deudores = cliente_service.libreta_de_fiados(db, usuario_id)

    return {
        "negocio": usuario.nombre_negocio if usuario else "",
        "sector": SECTORES.get(usuario.sector) if usuario and usuario.sector else None,
        "fecha_de_hoy": hoy_local(),
        "hoy": {
            "numero_de_ventas": len(ventas_hoy),
            "vendido": round(sum(v.precio_venta_total for v in ventas_hoy), 2),
            "ganancia": ganancia_hoy,
        },
        "ultimos_30_dias": {
            "vendido": resumen["total_vendido"],
            "ganancia": resumen["total_ganancia"],
            "mas_vendidos": [
                {"nombre": p["nombre"], "unidades": p["unidades"], "ganancia": p["ganancia"]}
                for p in resumen["mas_vendidos"]
            ],
            "mas_rentables": [
                {"nombre": p["nombre"], "unidades": p["unidades"], "ganancia": p["ganancia"]}
                for p in resumen["mas_rentables"]
            ],
        },
        "se_acaban_pronto": [
            {"nombre": a["nombre"], "stock": a["stock"], "dias_restantes": a["dias_restantes"]}
            for a in resumen["por_agotarse"][:5]
        ],
        "plata_quieta": {
            "total_al_costo": resumen["capital_parado"]["total"],
            "cuantos_productos": resumen["capital_parado"]["productos"],
        },
        "fiados": {
            "cuantos_deben": len(deudores),
            "total_por_cobrar": round(sum(d["deuda_total"] for d in deudores), 2),
            "deudores": [
                {"nombre": d["nombre"], "debe": d["deuda_total"], "dias_atraso": d["dias_atraso"]}
                for d in deudores[:5]
            ],
        },
        "productos_mencionados": _productos_relevantes(db, usuario_id, pregunta),
    }


def _validar_accion(accion) -> dict | None:
    """Deja pasar solo acciones del catálogo cerrado y bien formadas.

    Un modelo puede devolver un tipo inventado o datos incompletos. Antes
    de que eso llegue al frontend —que lo va a mostrar como una propuesta
    con un botón de confirmar— hay que descartarlo aquí.
    """
    if not isinstance(accion, dict):
        return None
    if accion.get("tipo") not in ACCIONES_PERMITIDAS:
        return None
    if not isinstance(accion.get("datos"), dict):
        return None
    if not accion.get("confirmacion"):
        return None
    return {
        "tipo": accion["tipo"],
        "datos": accion["datos"],
        "confirmacion": str(accion["confirmacion"]),
    }


def preguntar(db: Session, usuario_id: str, pregunta: str,
              historial: list[dict] | None = None) -> dict:
    """Responde una pregunta sobre el negocio.

    `historial` son los turnos anteriores de la conversación, para que
    "¿y ayer?" tenga sentido. No se guarda en base: el chat es efímero
    por ahora y el frontend lo mantiene en memoria.
    """
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise ErrorNegocio("La pregunta está vacía")

    contexto = construir_contexto(db, usuario_id, pregunta)

    mensajes = [
        {"role": "system", "content": INSTRUCCIONES},
        {
            "role": "system",
            # El contexto va como mensaje de sistema aparte, no mezclado
            # con la pregunta del usuario: así lo que escribe el tendero
            # nunca puede confundirse con instrucciones.
            "content": "Datos del negocio en este momento:\n"
                       + _como_texto(contexto),
        },
    ]

    for turno in (historial or [])[-6:]:
        papel = "assistant" if turno.get("rol") == "asistente" else "user"
        mensajes.append({"role": papel, "content": str(turno.get("texto", ""))[:1000]})

    mensajes.append({"role": "user", "content": pregunta[:1000]})

    salida = completar_json(mensajes)

    return {
        "respuesta": str(salida.get("respuesta", "")).strip()
                     or "No supe cómo responder a eso.",
        "accion": _validar_accion(salida.get("accion")),
    }


def _como_texto(contexto: dict) -> str:
    import json

    return json.dumps(contexto, ensure_ascii=False, indent=None)
