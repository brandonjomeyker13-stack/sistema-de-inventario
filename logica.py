"""
logica.py — Reglas de negocio. No conoce SQL: solo llama a `database`.

Cambios clave respecto a la versión anterior:
  1. `agregar_producto` ya no permite nombres duplicados (antes se podían
     crear dos productos "Cuaderno" distintos, y `vender_producto` solo
     encontraba el primero, vendiendo del producto equivocado).
  2. `vender_producto` ahora usa `registrar_venta_atomica`, así que un
     corte de luz o un crash a mitad de una venta ya no deja el stock
     descontado sin la venta registrada (o viceversa).
  3. Todos los montos se redondean de forma consistente con
     `config.redondear` antes de guardarse, para evitar que los centavos
     se vayan acumulando en errores de punto flotante con el tiempo.
"""

import database as db
from config import redondear


def agregar_producto(nombre, cantidad_str, precio_str, costo_str):
    nombre = str(nombre).strip()
    if not nombre:
        return "El nombre no puede estar vacío"
    try:
        cantidad = int(cantidad_str)
        precio = redondear(precio_str)
        costo = redondear(costo_str)
    except ValueError:
        return "Los campos numéricos deben ser números válidos"

    if cantidad < 0 or precio < 0 or costo < 0:
        return "No se permiten valores negativos"

    if db.existe_producto_con_nombre(nombre):
        return f"Ya existe un producto llamado '{nombre}'. Usa Editar en vez de crear uno nuevo."

    db.guardar_datos(nombre, cantidad, precio, costo)
    return "Producto guardado con éxito"


def vender_producto(nombre_producto, cantidad_a_vender_str):
    nombre_producto = str(nombre_producto).strip()
    if not nombre_producto:
        return "Escribe o selecciona un producto para vender"

    try:
        cantidad_a_vender = int(cantidad_a_vender_str)
    except ValueError:
        return "Ingresa una cantidad numérica válida"

    if cantidad_a_vender <= 0:
        return "La cantidad debe ser mayor a cero"

    producto = db.buscar_producto_por_nombre(nombre_producto)
    if not producto:
        return "Ese producto no existe en el inventario"

    id_p, nombre_p, cantidad_actual, precio_venta, precio_costo = producto

    if cantidad_actual < cantidad_a_vender:
        return f"No puedes vender más de lo que hay en stock (disponible: {cantidad_actual})"

    total_venta = redondear(cantidad_a_vender * precio_venta)
    ganancia_venta = redondear((precio_venta - precio_costo) * cantidad_a_vender)

    try:
        db.registrar_venta_atomica(
            id_producto=id_p,
            nueva_cantidad=cantidad_actual - cantidad_a_vender,
            nombre=nombre_p,
            cantidad_vendida=cantidad_a_vender,
            total=total_venta,
            ganancia=ganancia_venta,
        )
    except ValueError as e:
        return f"Error: {e}"

    return f"Venta exitosa: ganancia de ${ganancia_venta:.2f}"


def obtener_inventario():
    return db.cargar_datos_productos()


def buscar_en_inventario(query: str):
    """Filtra en Python porque el inventario de una tienda pequeña cabe
    perfecto en memoria; si el catálogo crece a miles de productos, esto
    se reemplaza por un `WHERE nombre LIKE ?` en la base de datos."""
    query = query.strip().lower()
    if not query:
        return []
    return [p for p in obtener_inventario() if query in p[1].lower()][:6]


def obtener_ganancia_hoy():
    return db.obtener_ganancia_hoy()


def obtener_ventas_por_fecha(fecha):
    fecha = fecha.strip()
    if not fecha:
        return [], 0
    ventas = db.cargar_ventas_por_fecha(fecha)
    ganancia = db.obtener_ganancia_por_fecha(fecha)
    return ventas, ganancia


def editar_producto(id_p, nombre, cantidad_str, precio_str, costo_str):
    nombre = str(nombre).strip()
    if not nombre:
        return "El nombre no puede estar vacío"
    try:
        cantidad = int(cantidad_str)
        precio = redondear(precio_str)
        costo = redondear(costo_str)
    except ValueError:
        return "Los campos numéricos deben ser números válidos"

    if cantidad < 0 or precio < 0 or costo < 0:
        return "No se permiten valores negativos"

    if db.existe_producto_con_nombre(nombre, excluir_id=id_p):
        return f"Ya existe otro producto llamado '{nombre}'"

    db.actualizar_producto_completo(id_p, nombre, cantidad, precio, costo)
    return "Guardado con éxito"


def eliminar_producto(id_p):
    return db.eliminar_producto(id_p)


def eliminar_venta(id_v):
    return db.eliminar_venta_db(id_v)