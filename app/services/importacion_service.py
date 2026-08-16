"""
app/services/importacion_service.py — Cargar el inventario desde una plantilla.

Por qué existe: teclear a mano los cientos de productos de una tienda es la
razón número uno por la que este tipo de aplicaciones se abandonan en la
primera semana. El dueño se cansa, lo deja a medias, y como el inventario
está incompleto la aplicación le da datos malos y deja de confiar en ella.

Con esto, el montaje pasa de horas a minutos, y además se puede repartir:
la plantilla la puede llenar un empleado o un familiar mientras el dueño
atiende.

TRES DECISIONES QUE DEFINEN ESTE ARCHIVO

1. TODO O NADA. Si una sola fila está mal, no se importa ninguna. Una
   importación a medias deja al tendero sin saber qué entró y qué no, y al
   reintentar duplica lo que ya estaba. Es mejor devolverle la lista de
   filas malas para que corrija el archivo.

2. SE MIRA ANTES DE GUARDAR. `analizar()` no escribe nada y devuelve
   exactamente lo que va a pasar. El frontend lo muestra y el tendero
   confirma. Es el mismo patrón del asistente: se propone, no se ejecuta.

3. LA LLAVE ES EL NOMBRE. No hay columna de código de barras (los códigos
   se ponen después, escaneando), así que un producto se reconoce por su
   nombre. Si ya existe, se actualiza.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio
from app.core.fechas import hoy_local
from app.core.numeros import NumeroInvalido, a_entero, a_numero
from app.core.texto import clave_nombre
from app.models.movimiento import AJUSTE
from app.repositories import categoria_repository, movimiento_repository, producto_repository
from app.services.product_service import _validar_precio

# Palabras que cuentan como "sí" en la columna de servicio. Se acepta de
# todo porque la plantilla la llena gente distinta y cada uno escribe lo
# que le parece.
AFIRMATIVOS = {"si", "sí", "s", "yes", "y", "true", "verdadero", "v", "1", "x"}
NEGATIVOS = {"no", "n", "false", "falso", "f", "0", ""}


def _texto(valor) -> str:
    """Una celda como texto limpio, con los espacios internos colapsados.

    Excel entrega números en celdas de texto y viceversa, así que todo pasa
    por aquí antes de mirarse.
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor == int(valor):
        # 12.0 en una celda de texto debe leerse "12", no "12.0".
        valor = int(valor)
    return " ".join(str(valor).split())


def _es_servicio(valor) -> bool:
    """Lee la columna de servicio.

    Lanza ErrorNegocio y no NumeroInvalido a propósito: esta columna no es
    un número, y con la excepción equivocada se escapaba del manejo por
    filas de `analizar` y salía como un error 500 en vez de como "la fila 7
    tiene un problema".
    """
    texto = _texto(valor).lower()
    if texto in AFIRMATIVOS:
        return True
    if texto in NEGATIVOS:
        return False
    raise ErrorNegocio(
        f"No entiendo '{texto}' en la columna de servicio. Escribe 'si' o 'no'."
    )


def _revisar_fila(fila, numero: int, permitir_perdida: bool) -> dict:
    """Convierte y valida una fila. Lanza ErrorNegocio si algo no sirve.

    Devuelve un dict ya con los tipos correctos, listo para guardar.
    """
    nombre = _texto(fila.nombre)
    if not nombre:
        raise ErrorNegocio("Falta el nombre del producto")

    es_servicio = _es_servicio(fila.es_servicio)

    try:
        # Un servicio no lleva existencias: se ignora lo que diga la
        # columna de cantidad en vez de rechazar la fila. Poner un número
        # ahí es un malentendido, no un error que valga la pena frenar.
        cantidad = 0 if es_servicio else a_entero(fila.cantidad, "cantidad")
        precio = a_numero(fila.precio, "precio")
        costo = a_numero(fila.cuanto_costo, "costo")
    except NumeroInvalido as e:
        raise ErrorNegocio(str(e))

    if cantidad < 0:
        raise ErrorNegocio("La cantidad no puede ser negativa")
    if precio < 0 or costo < 0:
        raise ErrorNegocio("El precio y el costo no pueden ser negativos")

    # La MISMA validación que al crear un producto a mano. Si el importador
    # tuviera una regla distinta, la plantilla se convertiría en la puerta
    # de atrás para meter datos que el formulario rechaza.
    _validar_precio(nombre, precio, costo, permitir_perdida)

    return {
        "fila": numero,
        "nombre": nombre,
        "cantidad": cantidad,
        "precio": precio,
        "cuanto_costo": costo,
        "categoria": _texto(fila.categoria) or None,
        "es_servicio": es_servicio,
    }


def analizar(db: Session, usuario_id: str, filas: list, permitir_perdida: bool = False) -> dict:
    """Revisa la plantilla y dice qué pasaría. NO escribe nada."""
    # El inventario entero en UNA consulta, indexado por nombre en
    # minúsculas. Buscar producto por producto serían cientos de consultas
    # contra Supabase para revisar un archivo.
    existentes = {p.nombre_clave: p for p in producto_repository.listar(db, usuario_id)}
    categorias = {clave_nombre(c.nombre): c for c in categoria_repository.listar(db, usuario_id)}

    crear, actualizar, errores, avisos = [], [], [], []
    categorias_nuevas: list[str] = []
    vistos: dict[str, int] = {}

    for indice, fila in enumerate(filas):
        # +2: la fila 1 es el encabezado y Excel cuenta desde 1. Así el
        # número coincide con lo que el tendero ve a la izquierda en su
        # pantalla, y no tiene que contar a mano.
        numero = indice + 2

        try:
            datos = _revisar_fila(fila, numero, permitir_perdida)
        except ErrorNegocio as e:
            errores.append({"fila": numero, "nombre": _texto(fila.nombre) or None,
                            "problema": str(e)})
            continue

        # La MISMA llave que usa el resto del sistema: minúsculas, sin
        # tildes, espacios colapsados. Antes esto era .lower() a secas, y
        # entonces la plantilla trataba "Cafe" y "Café" como productos
        # distintos mientras el formulario de alta los trataba igual.
        clave = clave_nombre(datos["nombre"])

        # Dos filas con el mismo nombre en el MISMO archivo. No se puede
        # adivinar cuál gana, y aplicar las dos dejaría el stock de la
        # última en vez de la suma. Es un error del archivo.
        if clave in vistos:
            errores.append({
                "fila": numero, "nombre": datos["nombre"],
                "problema": f"'{datos['nombre']}' ya aparece en la fila {vistos[clave]} "
                            "de este mismo archivo. Déjalo una sola vez.",
            })
            continue
        vistos[clave] = numero

        if not datos["categoria"]:
            avisos.append({"fila": numero, "nombre": datos["nombre"],
                           "aviso": "Queda sin categoría. Se le puede poner después."})
        elif clave_nombre(datos["categoria"]) not in categorias:
            if datos["categoria"] not in categorias_nuevas:
                categorias_nuevas.append(datos["categoria"])
            avisos.append({"fila": numero, "nombre": datos["nombre"],
                           "aviso": f"Se creará la categoría '{datos['categoria']}'."})

        if datos["precio"] < datos["cuanto_costo"]:
            # Solo llega aquí con permitir_perdida activado; si no,
            # _validar_precio ya lo habría rechazado.
            avisos.append({
                "fila": numero, "nombre": datos["nombre"],
                "aviso": f"Se vende a ${datos['precio']:,.0f} y cuesta "
                         f"${datos['cuanto_costo']:,.0f}: pierde en cada unidad.",
            })

        anterior = existentes.get(clave)
        if anterior:
            actualizar.append({
                "fila": numero, "nombre": datos["nombre"],
                "cantidad_antes": anterior.cantidad, "cantidad_despues": datos["cantidad"],
                "precio_antes": anterior.precio, "precio_despues": datos["precio"],
                "costo_antes": anterior.cuanto_costo, "costo_despues": datos["cuanto_costo"],
            })
        else:
            crear.append({
                "fila": numero, "nombre": datos["nombre"], "cantidad": datos["cantidad"],
                "precio": datos["precio"], "cuanto_costo": datos["cuanto_costo"],
                "categoria": datos["categoria"], "es_servicio": datos["es_servicio"],
            })

    return {
        "total_filas": len(filas),
        "se_puede_importar": not errores,
        "a_crear": len(crear),
        "a_actualizar": len(actualizar),
        "con_error": len(errores),
        "crear": crear,
        "actualizar": actualizar,
        "errores": errores,
        "avisos": avisos,
        "categorias_nuevas": categorias_nuevas,
    }


def importar(db: Session, usuario_id: str, filas: list, permitir_perdida: bool = False) -> dict:
    """Aplica la plantilla. Todo en una sola transacción.

    Se vuelve a analizar en lugar de confiar en lo que el frontend
    previsualizó: entre la vista previa y la confirmación pudo cambiar el
    inventario (otra pestaña, el celular), y validar de nuevo cuesta una
    consulta.
    """
    reporte = analizar(db, usuario_id, filas, permitir_perdida)

    if reporte["errores"]:
        primeros = reporte["errores"][:3]
        detalle = "; ".join(f"fila {e['fila']}: {e['problema']}" for e in primeros)
        raise ErrorNegocio(
            f"El archivo tiene {len(reporte['errores'])} fila(s) con problemas y no se "
            f"importó nada. {detalle}"
            + ("..." if len(reporte["errores"]) > 3 else "")
        )

    # UNA transacción para todo. Guardar producto por producto con su propio
    # commit serían cientos de idas a Supabase, y un fallo en el medio
    # dejaría el inventario a medio cargar.
    categorias = {clave_nombre(c.nombre): c for c in categoria_repository.listar(db, usuario_id)}
    creadas: list[str] = []

    for nombre_cat in reporte["categorias_nuevas"]:
        categoria = categoria_repository.crear(db, usuario_id, nombre_cat)
        categorias[clave_nombre(nombre_cat)] = categoria
        creadas.append(nombre_cat)

    existentes = {p.nombre_clave: p for p in producto_repository.listar(db, usuario_id)}

    for datos in reporte["crear"]:
        categoria = categorias.get(clave_nombre(datos["categoria"]))
        producto_repository.crear(
            db, usuario_id, datos["nombre"], datos["cantidad"], datos["precio"],
            datos["cuanto_costo"], None, categoria.id if categoria else None,
            controla_stock=not datos["es_servicio"],
        )

    for cambio in reporte["actualizar"]:
        producto = existentes[clave_nombre(cambio["nombre"])]

        # El ajuste de stock va al libro, igual que al editar desde el
        # formulario. Sin esto, una importación movería existencias sin
        # dejar rastro y el libro dejaría de cuadrar.
        if producto.controla_stock and cambio["cantidad_despues"] != producto.cantidad:
            movimiento_repository.registrar(
                db, usuario_id, producto.id, AJUSTE,
                cambio["cantidad_despues"] - producto.cantidad,
                producto.cantidad, hoy_local(), "Importación de plantilla",
            )

        producto.cantidad = cambio["cantidad_despues"] if producto.controla_stock else 0
        producto.precio = cambio["precio_despues"]
        producto.cuanto_costo = cambio["costo_despues"]
        # El código de barras NO se toca. La plantilla no lo trae, y el
        # tendero ya se los fue poniendo escaneando: pisarlos con None
        # borraría ese trabajo en silencio.
        #
        # La categoría tampoco se pisa si la plantilla viene sin ella —
        # dejar la columna vacía no puede significar "quítale la categoría
        # que ya tenía".

    db.commit()

    return {
        "creados": len(reporte["crear"]),
        "actualizados": len(reporte["actualizar"]),
        "categorias_creadas": creadas,
    }
