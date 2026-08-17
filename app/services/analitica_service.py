"""
app/services/analitica_service.py — Lo que los números significan.

El repositorio devuelve sumas; aquí se decide qué es relevante. La idea
que guía todo este archivo:

    lo que más vende, el tendero YA lo sabe.

Lo ve todos los días. Si el análisis solo le devuelve eso, lo mira una
vez y no vuelve. El valor está en lo que no puede calcular de cabeza:
cuánta plata tiene parada en un estante, qué producto le deja más
ganancia aunque venda menos, y qué se le va a acabar esta semana.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.fechas import FORMATO_FECHA, hoy_local, sumar_dias
from app.repositories import analitica_repository, usuario_repository

# Un producto se considera parado si lleva este tiempo sin una sola venta.
DIAS_SIN_MOVIMIENTO = 60

# Red de seguridad para el umbral de stock bajo: se usa si la cuenta no
# tiene valor (una fila anterior a la migración 0022, o un 0 guardado a
# mano). Un umbral de cero haría que un producto solo apareciera en la
# lista cuando YA se agotó, que es demasiado tarde para pedirlo.
MINIMO_POR_DEFECTO = 5

# Por debajo de esto se avisa de que el producto se está por acabar.
DIAS_PARA_AGOTARSE = 7

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _rango(dias: int) -> tuple[str, str]:
    """Ventana de `dias` días terminando hoy, ambos incluidos."""
    return sumar_dias(-(dias - 1)), hoy_local()


def mas_vendidos(db: Session, usuario_id: str, dias: int = 30,
                 por: str = "unidades", limite: int = 10) -> list[dict]:
    """Ranking de productos. `por` puede ser unidades, ingresos o ganancia.

    Que se pueda ordenar por ganancia y no solo por unidades no es un
    detalle: es la diferencia entre "vendo mucho arroz" y "gano más con
    el aceite", que es lo que de verdad cambia decisiones de compra.
    """
    if por not in ("unidades", "ingresos", "ganancia"):
        por = "unidades"

    desde, hasta = _rango(dias)
    productos = analitica_repository.ventas_por_producto(db, usuario_id, desde, hasta)
    productos.sort(key=lambda p: p[por], reverse=True)
    return productos[:limite]


def capital_parado(db: Session, usuario_id: str, dias: int = DIAS_SIN_MOVIMIENTO) -> dict:
    """Productos sin una sola venta en `dias`, y cuánto dinero representan.

    Incluye los que nunca se han vendido — son los peores y un INNER JOIN
    los habría dejado fuera.

    El valor se calcula al COSTO, no al precio de venta: es lo que el
    tendero pagó y todavía no ha recuperado. Valorarlo al precio de venta
    inflaría la cifra con una ganancia que no ha ocurrido.
    """
    limite = sumar_dias(-dias)
    inventario = analitica_repository.inventario_con_ultima_venta(db, usuario_id)

    parados = []
    for p in inventario:
        if not p["controla_stock"]:
            # Un servicio no tiene plata dormida: nadie compró por
            # adelantado un lote de fotocopias. Que lleve dos meses sin
            # venderse no es capital parado, es simplemente un servicio
            # que no se pide.
            continue
        if p["stock"] <= 0:
            # Sin existencias no hay plata parada, por mucho que no se venda.
            continue
        if p["ultima_venta"] and p["ultima_venta"] > limite:
            continue

        dias_quieto = None
        if p["ultima_venta"]:
            dias_quieto = (
                datetime.strptime(hoy_local(), FORMATO_FECHA)
                - datetime.strptime(p["ultima_venta"], FORMATO_FECHA)
            ).days

        parados.append({
            "producto_id": p["id"],
            "nombre": p["nombre"],
            "stock": p["stock"],
            "valor_costo": round(p["stock"] * p["costo"], 2),
            "ultima_venta": p["ultima_venta"],
            "dias_sin_venderse": dias_quieto,
            "nunca_vendido": p["ultima_venta"] is None,
        })

    # Primero lo que más dinero tiene inmovilizado: es donde está el
    # problema, no en el producto barato que lleva más tiempo quieto.
    parados.sort(key=lambda p: p["valor_costo"], reverse=True)

    return {
        "dias_evaluados": dias,
        "total_inmovilizado": round(sum(p["valor_costo"] for p in parados), 2),
        "productos": parados,
    }


def por_agotarse(db: Session, usuario_id: str, dias_historial: int = 30) -> list[dict]:
    """Qué se va a acabar, según el ritmo de venta reciente.

    Ritmo = unidades vendidas en la ventana / días de la ventana.
    Días restantes = stock / ritmo.

    Solo aparecen los productos que SE VENDEN. Uno parado tiene stock
    para siempre y su sitio es la lista de capital parado, no esta.
    """
    desde, hasta = _rango(dias_historial)
    vendidos = analitica_repository.ventas_por_producto(db, usuario_id, desde, hasta)
    ritmos = {v["producto_id"]: v["unidades"] / dias_historial
              for v in vendidos if v["producto_id"]}

    inventario = analitica_repository.inventario_con_ultima_venta(db, usuario_id)

    alertas = []
    for p in inventario:
        if not p["controla_stock"]:
            # Las fotocopias no se agotan. Sin este filtro, el servicio más
            # vendido de la papelería encabezaría permanentemente la
            # alerta de "se te está acabando" — y una alerta que siempre
            # está encendida deja de mirarse, incluida la de los productos
            # que sí se acaban.
            continue
        ritmo = ritmos.get(p["id"], 0)
        if ritmo <= 0:
            continue
        dias_restantes = p["stock"] / ritmo
        if dias_restantes > DIAS_PARA_AGOTARSE:
            continue
        alertas.append({
            "producto_id": p["id"],
            "nombre": p["nombre"],
            "stock": p["stock"],
            "ritmo_diario": round(ritmo, 2),
            "dias_restantes": round(dias_restantes, 1),
            "ya_agotado": p["stock"] <= 0,
        })

    alertas.sort(key=lambda a: a["dias_restantes"])
    return alertas


def que_comprar(db: Session, usuario_id: str, dias_historial: int = 30) -> dict:
    """La lista de lo que hay que pedirle al proveedor.

    Junta las DOS señales, porque cada una sola tiene un punto ciego:

      · UMBRAL: quedan menos unidades que el mínimo. Funciona desde el
        primer día, y es como piensa un tendero ("avísame cuando queden
        menos de cinco"). Es la única que ve un producto sin historial de
        ventas — uno nuevo, o uno que se vende poco, se agotaría en
        silencio con solo la otra señal.

      · RITMO: al paso al que se vende, se acaba esta semana. Ve venir el
        problema antes de llegar al mínimo, que es justo lo que un umbral
        fijo no puede hacer con un producto que de pronto se puso de moda.

    Un producto entra si CUALQUIERA de las dos se cumple, y se dice cuál
    para que el tendero entienda por qué está en la lista.

    NO se sugiere cuánto comprar a propósito. Sería inventar: el tendero
    compra por bulto, por caja de veinticuatro o por paca, según lo que le
    venda su proveedor. Se le dan los datos —cuánto queda, cuánto vende al
    día— y él decide, que es quien sabe.
    """
    usuario = usuario_repository.obtener_por_id(db, usuario_id)
    minimo_negocio = (usuario.stock_minimo_defecto if usuario else None) or MINIMO_POR_DEFECTO

    desde, hasta = _rango(dias_historial)
    vendidos = analitica_repository.ventas_por_producto(db, usuario_id, desde, hasta)
    ritmos = {v["producto_id"]: v["unidades"] / dias_historial
              for v in vendidos if v["producto_id"]}

    inventario = analitica_repository.inventario_con_ultima_venta(db, usuario_id)

    lista = []
    for p in inventario:
        # Los servicios no se compran: no hay un proveedor de fotocopias.
        if not p["controla_stock"]:
            continue

        minimo = p["stock_minimo"] if p["stock_minimo"] is not None else minimo_negocio
        ritmo = ritmos.get(p["id"], 0)
        dias_restantes = round(p["stock"] / ritmo, 1) if ritmo > 0 else None

        bajo_el_minimo = p["stock"] <= minimo
        se_acaba_pronto = dias_restantes is not None and dias_restantes <= DIAS_PARA_AGOTARSE
        if not bajo_el_minimo and not se_acaba_pronto:
            continue

        if p["stock"] <= 0:
            motivo = "se acabó"
        elif bajo_el_minimo:
            motivo = f"quedan {p['stock']} y tu mínimo es {minimo}"
        else:
            motivo = f"quedan {p['stock']}, para {dias_restantes} día(s) al ritmo de ahora"

        lista.append({
            "producto_id": p["id"],
            "nombre": p["nombre"],
            "stock": p["stock"],
            "stock_minimo": minimo,
            "vende_por_dia": round(ritmo, 2) if ritmo > 0 else 0.0,
            "dias_restantes": dias_restantes,
            "motivo": motivo,
            # Lo que ya se agotó va primero y en rojo: cada hora que pasa
            # es una venta que se va a la tienda de la esquina.
            "ya_agotado": p["stock"] <= 0,
        })

    # Lo agotado arriba; después lo que menos días aguanta. Un producto sin
    # ritmo conocido va al final: está bajo de stock pero no hay prisa
    # medible.
    lista.sort(key=lambda x: (
        not x["ya_agotado"],
        x["dias_restantes"] if x["dias_restantes"] is not None else 9999,
        x["nombre"],
    ))

    return {
        "total": len(lista),
        "agotados": sum(1 for x in lista if x["ya_agotado"]),
        "productos": lista,
        "texto": _texto_del_pedido(usuario.nombre_negocio if usuario else "", lista),
    }


def _texto_del_pedido(nombre_negocio: str, lista: list[dict]) -> str:
    """La lista lista para pegar en WhatsApp.

    Se arma AQUÍ y no en el frontend porque tiene dos consumidores: la
    pantalla del inventario y el asistente. Si cada uno la formateara por su
    cuenta, algún día no coincidirían —la pantalla diría doce productos y el
    chat ocho— y el tendero dejaría de confiar en los dos.

    Sin negritas ni asteriscos: WhatsApp los interpreta, pero un SMS, un
    correo o una nota de voz transcrita no, y ahí quedarían como basura.
    """
    if not lista:
        return "No hay nada por comprar: todo está por encima de su mínimo."

    lineas = [f"Pedido - {nombre_negocio}".strip(" -"), hoy_local(), ""]

    agotados = [x for x in lista if x["ya_agotado"]]
    resto = [x for x in lista if not x["ya_agotado"]]

    if agotados:
        lineas.append("SE ACABARON:")
        lineas += [f"- {x['nombre']}" for x in agotados]
        if resto:
            lineas.append("")

    if resto:
        if agotados:
            lineas.append("SE ESTAN ACABANDO:")
        lineas += [f"- {x['nombre']} (quedan {x['stock']})" for x in resto]

    return "\n".join(lineas)


def dias_fuertes(db: Session, usuario_id: str, dias: int = 90) -> list[dict]:
    """Cuánto se vende cada día de la semana, en promedio.

    Se promedia por número de veces que ocurrió ese día en la ventana, no
    por el total: si el periodo tiene 13 lunes y 12 martes, comparar los
    totales crudos favorecería al lunes sin ninguna razón real.
    """
    desde, hasta = _rango(dias)
    totales = analitica_repository.totales_por_fecha(db, usuario_id, desde, hasta)

    acumulado = defaultdict(lambda: {"vendido": 0.0, "ventas": 0, "dias": 0})
    for t in totales:
        indice = datetime.strptime(t["fecha"], FORMATO_FECHA).weekday()
        acumulado[indice]["vendido"] += t["vendido"]
        acumulado[indice]["ventas"] += t["ventas"]
        acumulado[indice]["dias"] += 1

    resultado = []
    for indice, nombre in enumerate(DIAS_SEMANA):
        datos = acumulado.get(indice)
        if not datos or datos["dias"] == 0:
            resultado.append({
                "dia": nombre, "promedio_vendido": 0.0,
                "total_vendido": 0.0, "ventas": 0, "dias_con_datos": 0,
            })
            continue
        resultado.append({
            "dia": nombre,
            "promedio_vendido": round(datos["vendido"] / datos["dias"], 2),
            "total_vendido": round(datos["vendido"], 2),
            "ventas": datos["ventas"],
            "dias_con_datos": datos["dias"],
        })
    return resultado


def resumen(db: Session, usuario_id: str, dias: int = 30) -> dict:
    """Lo que va en la pantalla de análisis, de una sola llamada.

    Se arma aquí y no en el frontend por lo de siempre: una petición en
    vez de cinco, y las reglas de qué es "parado" o "por agotarse" viven
    en un solo sitio.
    """
    desde, hasta = _rango(dias)
    productos = analitica_repository.ventas_por_producto(db, usuario_id, desde, hasta)

    por_unidades = sorted(productos, key=lambda p: p["unidades"], reverse=True)[:5]
    por_ganancia = sorted(productos, key=lambda p: p["ganancia"], reverse=True)[:5]
    parado = capital_parado(db, usuario_id)

    # El contraste que hace pensar al tendero: el producto que más sale
    # por la puerta no suele ser el que más deja.
    estrella_volumen = por_unidades[0] if por_unidades else None
    estrella_ganancia = por_ganancia[0] if por_ganancia else None
    mismo = (
        estrella_volumen is not None
        and estrella_ganancia is not None
        and estrella_volumen["producto_id"] == estrella_ganancia["producto_id"]
    )

    return {
        "dias": dias,
        "desde": desde,
        "hasta": hasta,
        "total_vendido": round(sum(p["ingresos"] for p in productos), 2),
        "total_ganancia": round(sum(p["ganancia"] for p in productos), 2),
        "productos_distintos_vendidos": len(productos),
        "mas_vendidos": por_unidades,
        "mas_rentables": por_ganancia,
        # True cuando el más vendido es también el más rentable. Cuando es
        # False hay una historia que contar en pantalla.
        "volumen_y_ganancia_coinciden": mismo,
        "capital_parado": {
            "total": parado["total_inmovilizado"],
            "productos": len(parado["productos"]),
        },
        "por_agotarse": por_agotarse(db, usuario_id),
    }
