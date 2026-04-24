import database as db 

def agregar_producto(nombre, cantidad_str, precio_str,costo_str):
    if not str(nombre).strip():
        return "el nombre no puede estar vacio"
    try:
        cantidad = int(cantidad_str)
        precio = float(precio_str)
        costo = float(costo_str)
        if cantidad < 0 or precio < 0 or costo < 0:
         return "error ingresaste un valor invalido o negativo"
     
        db.guardar_datos(nombre,cantidad,precio,costo)
        return " guardado con exito"
    except ValueError:
        return "error debes escribir numeros no letras"   
               
def vender_producto(nombre_producto,cantidad_avender_str):
    
    try:
        cantidad_avender =  int(cantidad_avender_str)
        if cantidad_avender <= 0:
            return "la cantidad debe ser mayor a cero"
        
        producto = db.cargar_datos_productos()
        producto_encontrado = None
        for p in producto:
            if p[1].lower() == nombre_producto.lower().strip():
                producto_encontrado = p
                break
        if not producto_encontrado:
             return "Error: El producto no existe en el inventario"    
        
        id_p, nombre_p, cantidad_actual, p_Venta, p_costo = producto_encontrado
        
        if cantidad_actual < cantidad_avender:
           return f'error, no puedes vender mas de lo q hay en el stock, hay: {cantidad_actual} '
       
        total_venta = cantidad_avender * p_Venta
        ganancia_venta = (p_Venta - p_costo) * cantidad_avender
        nueva_cantidad = cantidad_actual - cantidad_avender
        
        db.actualizar_producto(id_p,nueva_cantidad)
        
        db.registrar_venta_db(nombre_p, cantidad_avender, total_venta, ganancia_venta)
        return f"Venta exitosa: Ganancia de ${ganancia_venta}"
                
    except ValueError:
        return "Error: Ingresa una cantidad numérica válida"


# ------------------- nuevas funciones -------------------

def obtener_inventario():
    return db.cargar_datos_productos()

def obtener_ganancia_hoy():
    return db.obtener_ganancia_hoy()

def obtener_ventas_por_fecha(fecha):
    if not fecha.strip():
        return [], 0
    ventas = db.cargar_ventas_por_fecha(fecha.strip())
    ganancia = db.obtener_ganancia_por_fecha(fecha.strip())
    return ventas, ganancia

def editar_producto(id_p, nombre, cantidad_str, precio_str, costo_str):
    if not str(nombre).strip():
        return "el nombre no puede estar vacio"
    try:
        cantidad = int(cantidad_str)
        precio = float(precio_str)
        costo = float(costo_str)
        if cantidad < 0 or precio < 0 or costo < 0:
            return "error ingresaste un valor invalido o negativo"
        db.actualizar_producto_completo(id_p, nombre, cantidad, precio, costo)
        return "guardado con exito"
    except ValueError:
        return "error debes escribir numeros no letras"

def eliminar_producto(id_p):
    db.eliminar_prodcuto(id_p)

def eliminar_venta(id_v):
    db.eliminar_venta_db(id_v)