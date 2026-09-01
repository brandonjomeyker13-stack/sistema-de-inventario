"""
Qué se consulta para responder cada intención. SOLO CONSULTAS, ningún texto.

LA DIFERENCIA CON EL CONTEXTO DEL ASISTENTE

`asistente_service/contexto.py` arma el panorama COMPLETO del negocio en
cada pregunta, porque el modelo no sabe de antemano qué le van a preguntar y
tiene que poder responder cualquier cosa. Eso son hasta catorce idas a
Supabase, y con NullPool cada una abre su propia conexión.

Aquí ya sabemos la intención antes de consultar, así que se trae SOLO lo que
esa pregunta necesita. "¿Quién me debe?" no barre el inventario.

Cada función recibe (db, usuario_id) y devuelve un diccionario de valores
planos. Ninguna redacta: eso es de redaccion.py.
"""

from sqlalchemy.orm import Session

from app.core.fechas import hoy_local
from app.repositories import producto_repository
from app.services import analitica_service, cliente_service, venta_service

# Cuántos nombres se nombran al listar un grupo. La cuenta es lo que responde
# la pregunta; los nombres solo hacen que la respuesta suene concreta. Es el
# mismo criterio que usa el contexto del asistente.
MAX_EJEMPLOS = 8


def lista_de_compra(db: Session, usuario_id: str) -> dict:
    """El pedido para el proveedor, con su texto ya armado.

    El texto sale de `analitica_service`, el mismo que alimenta la pantalla
    de inventario. Por eso responder esto sin el modelo no es solo más
    barato: es la única forma de garantizar que la lista del chat y la de la
    pantalla sean idénticas. Hoy el prompt se lo PIDE al modelo, y pedir no
    es garantizar.
    """
    compra = analitica_service.que_comprar(db, usuario_id)
    return {
        "total": compra["total"],
        "agotados": compra["agotados"],
        "texto": compra["texto"],
    }


def _ventas_de_hoy(db: Session, usuario_id: str) -> dict:
    ventas, ganancia = venta_service.ventas_por_fecha(db, usuario_id, hoy_local())
    return {
        "cuantas": len(ventas),
        "vendido": round(sum(v.precio_venta_total for v in ventas), 2),
        "ganancia": ganancia,
    }


# Las dos preguntas se responden con la misma consulta y cambian solo en qué
# se destaca. Se separan porque la intención es distinta: un tendero que
# pregunta cuánto vendió no está preguntando cuánto ganó, y confundirlas es
# justamente lo que el producto vino a arreglar.
ventas_de_hoy = _ventas_de_hoy
ganancia_de_hoy = _ventas_de_hoy


def fiados(db: Session, usuario_id: str) -> dict:
    deudores = cliente_service.libreta_de_fiados(db, usuario_id)
    return {
        "cuantos": len(deudores),
        "total": round(sum(d["deuda_total"] for d in deudores), 2),
        "atrasados": sum(1 for d in deudores if d["dias_atraso"] > 0),
        "algunos": [
            {"nombre": d["nombre"], "debe": d["deuda_total"], "dias_atraso": d["dias_atraso"]}
            for d in deudores[:MAX_EJEMPLOS]
        ],
    }


def _grupo(productos: list) -> dict:
    """La cuenta exacta y unos nombres de ejemplo, separados a propósito.

    Se separan para que la redacción no pueda dar a entender que la muestra
    son todos cuando la cuenta es mayor.
    """
    return {
        "cuantos": len(productos),
        "algunos": [p.nombre for p in productos[:MAX_EJEMPLOS]],
        "hay_mas": len(productos) > MAX_EJEMPLOS,
    }


def sin_codigo(db: Session, usuario_id: str) -> dict:
    productos = producto_repository.listar(db, usuario_id)
    return _grupo([p for p in productos if not p.codigo_barras])


def agotados(db: Session, usuario_id: str) -> dict:
    productos = producto_repository.listar(db, usuario_id)
    # Los servicios no llevan stock: una fotocopiadora nunca está "agotada",
    # y contarla ahí sería una alarma falsa todos los días.
    return _grupo([p for p in productos if p.controla_stock and p.cantidad <= 0])


def valor_inventario(db: Session, usuario_id: str) -> dict:
    productos = producto_repository.listar(db, usuario_id)
    con_stock = [p for p in productos if p.controla_stock]
    return {
        "cuantos_productos": len(productos),
        # Al costo es lo que tiene invertido; al precio de venta es lo que
        # valdría si lo vendiera todo. El tendero pregunta las dos cosas y
        # confundirlas le cambia la idea de cuánto vale su negocio.
        "al_costo": round(sum(p.cuanto_costo * p.cantidad for p in con_stock), 2),
        "al_precio_de_venta": round(sum(p.precio * p.cantidad for p in con_stock), 2),
    }
