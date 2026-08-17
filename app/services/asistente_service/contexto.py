"""
Qué datos ve el modelo. Aquí NO hay nada de texto del prompt.

LA DECISIÓN QUE DEFINE ESTE ARCHIVO

El contexto NO es el inventario entero. Mandarle los 500 productos al modelo
en cada pregunta es caro, lento y deja de caber. Se le manda:

  · el resumen de analítica, que ya está calculado;
  · un RECUENTO de cada grupo del inventario (cuántos agotados, cuántos sin
    código de barras...) con solo unos nombres de ejemplo;
  · y los productos que la pregunta menciona.

Compacto y suficiente para lo que un tendero pregunta de verdad.

Por eso los grupos van como {cuantos, algunos}: la cuenta es exacta y los
nombres son una muestra. Las instrucciones le prohíben al modelo insinuar
que esa muestra son todos.
"""

from sqlalchemy.orm import Session

from app.core.fechas import hoy_local
from app.core.sectores import SECTORES
from app.repositories import producto_repository, usuario_repository
from app.services import analitica_service, cliente_service, venta_service

# Cuántos productos mencionados por la pregunta caben en el contexto.
MAX_PRODUCTOS_EN_CONTEXTO = 12

# Cuántos nombres de ejemplo se dan por cada grupo del inventario. Pocos a
# propósito: la cuenta es lo que responde la pregunta ("¿cuántos me faltan
# por código?"), y los nombres solo sirven para que la respuesta suene
# concreta. Mandar trescientos nombres reventaría el contexto.
MAX_EJEMPLOS = 8


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


def _grupo(productos: list) -> dict:
    """Un grupo del inventario: la cuenta exacta y unos nombres de ejemplo.

    La cuenta es lo que responde la pregunta; los nombres solo hacen que la
    respuesta suene concreta. Se separan para que el modelo no pueda
    confundir la muestra con el total.
    """
    return {
        "cuantos": len(productos),
        "algunos": [p.nombre for p in productos[:MAX_EJEMPLOS]],
        "hay_mas": len(productos) > MAX_EJEMPLOS,
    }


def _inventario(db: Session, usuario_id: str) -> dict:
    """El panorama del inventario, en recuentos.

    Se trae el inventario UNA vez y se cuenta en Python. Hacer una consulta
    por grupo serían siete idas a Supabase en cada pregunta del asistente, y
    con NullPool cada una abre su propia conexión.
    """
    productos = producto_repository.listar(db, usuario_id)
    con_stock = [p for p in productos if p.controla_stock]

    return {
        "cuantos_productos": len(productos),
        # Al costo es lo que tiene invertido; al precio de venta es lo que
        # valdría si lo vendiera todo. El tendero pregunta las dos cosas.
        "valor_al_costo": round(sum(p.cuanto_costo * p.cantidad for p in con_stock), 2),
        "valor_al_precio_de_venta": round(sum(p.precio * p.cantidad for p in con_stock), 2),

        # El grupo que motivó todo esto: después de importar la plantilla,
        # NINGÚN producto tiene código. Saber cuáles faltan es lo que le
        # dice al tendero qué le queda por escanear.
        "sin_codigo_de_barras": _grupo([p for p in productos if not p.codigo_barras]),
        "agotados": _grupo([p for p in con_stock if p.cantidad <= 0]),
        "sin_categoria": _grupo([p for p in productos if not p.categoria_id]),

        "cuantos_servicios": sum(1 for p in productos if not p.controla_stock),
    }


def construir(db: Session, usuario_id: str, pregunta: str) -> dict:
    """Todo lo que el modelo necesita saber, en pocos cientos de tokens."""
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    resumen = analitica_service.resumen(db, usuario_id, 30)
    compra = analitica_service.que_comprar(db, usuario_id)
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
        "inventario": _inventario(db, usuario_id),
        "se_acaban_pronto": [
            {"nombre": a["nombre"], "stock": a["stock"], "dias_restantes": a["dias_restantes"]}
            for a in resumen["por_agotarse"][:5]
        ],
        # La lista de compra YA ARMADA, con su texto exacto.
        #
        # Se le pasa el texto hecho en vez de dejar que el modelo lo redacte
        # a partir de los productos: si lo redactara él, la lista del chat y
        # la de la pantalla del inventario no coincidirían —el modelo
        # resumiría, ordenaría distinto, o se saltaría alguno— y el tendero
        # dejaría de confiar en las dos. Las instrucciones le piden
        # devolverlo tal cual.
        "lista_de_compra": {
            "cuantos_productos": compra["total"],
            "cuantos_agotados": compra["agotados"],
            "texto_exacto": compra["texto"],
        },
        "plata_quieta": {
            # Dentro de `resumen` estas claves ya vienen aplanadas: `total`
            # y `productos` (un recuento), no la estructura completa que
            # devuelve capital_parado() por su cuenta.
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
