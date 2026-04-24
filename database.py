import sqlite3 as db
#------------------- base de datos de los productos-------------------------
def inicializar_db():
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio REAL NOT NULL,
            cuanto_costo REAL NOT NULL 
        )
    """)
    cursor.execute("""
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_producto TEXT NOT NULL,
    cantidad_vendida INTEGER NOT NULL,
    precio_venta_total REAL NOT NULL,
    ganancia_total REAL NOT NULL,
    fecha DATE DEFAULT (CURRENT_DATE)
)
""")
    try:
      cursor.execute("ALTER TABLE productos ADD COLUMN cuanto_costo REAL DEFAULT 0")
    except:
    # Si ya existe, no hará nada
     pass
    

    conexion.commit()  
    conexion.close()



def cargar_datos_productos():
  conexion = db.connect("inventario.db") 
  cursor = conexion.cursor()
  
  cursor.execute("SELECT * FROM productos") 
  datos_productos = cursor.fetchall()
  
  conexion.close()
  return datos_productos


def cargar_datos_ventas():
  conexion = db.connect("inventario.db")
  
  cursor = conexion.cursor()
  
  cursor.execute("SELECT * FROM ventas")
  
  datos_venta = cursor.fetchall()
  conexion.close()
  return datos_venta

    
    
def guardar_datos(nombre,cantidad,precio,costo):
    conexion = db.connect("inventario.db")
    
    cursor = conexion.cursor()
    # BUG FIX: se agrego cuanto_costo a la lista de columnas
    cursor.execute("INSERT INTO productos (nombre,cantidad,precio,cuanto_costo) VALUES (?,?,?,?)", (nombre , cantidad, precio, costo)) 
    
    conexion.commit()
    conexion.close()
    
    
def eliminar_prodcuto(id):
    conexion = db.connect("inventario.db")
    
    cursor = conexion.cursor()
    
    cursor.execute("DELETE FROM productos where id = ?", (id,))
    
    conexion.commit()
    conexion.close()
    return "producto eliminado"
    
def actualizar_producto(id, nueva_cantidad):
    conexion = db.connect("inventario.db")
    
    cursor = conexion.cursor()
    
    # BUG FIX: los parametros estaban invertidos, nueva_cantidad va primero
    cursor.execute("UPDATE productos SET cantidad = ? WHERE id = ?", (nueva_cantidad, id))
    
    conexion.commit()
    conexion.close()
    
    
def registrar_venta_db(nombre, cantidad, total, ganancia):
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute("""
        INSERT INTO ventas (nombre_producto, cantidad_vendida, precio_venta_total, ganancia_total)
        VALUES (?, ?, ?, ?)
    """, (nombre, cantidad, total, ganancia))
    conexion.commit()
    conexion.close() 


# ------------------- nuevas funciones -------------------

def obtener_ganancia_hoy():
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute("SELECT SUM(ganancia_total) FROM ventas WHERE fecha = CURRENT_DATE")
    resultado = cursor.fetchone()[0]
    conexion.close()
    return resultado or 0

def cargar_ventas_por_fecha(fecha):
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM ventas WHERE fecha = ?", (fecha,))
    datos = cursor.fetchall()
    conexion.close()
    return datos

def obtener_ganancia_por_fecha(fecha):
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute("SELECT SUM(ganancia_total) FROM ventas WHERE fecha = ?", (fecha,))
    resultado = cursor.fetchone()[0]
    conexion.close()
    return resultado or 0

def actualizar_producto_completo(id_p, nombre, cantidad, precio, costo):
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE productos SET nombre = ?, cantidad = ?, precio = ?, cuanto_costo = ? WHERE id = ?",
        (nombre, cantidad, precio, costo, id_p)
    )
    conexion.commit()
    conexion.close()

def eliminar_venta_db(id_v):
    conexion = db.connect("inventario.db")
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM ventas WHERE id = ?", (id_v,))
    conexion.commit()
    conexion.close()


if __name__ == "__main__":
  inicializar_db()
  print("Base de datos lista.")
  productos = cargar_datos_productos()
  ventas = cargar_datos_ventas()

  print("Contenido de la tabla:")
  print(productos)
  print(ventas)