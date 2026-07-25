"""
database.py — Capa de acceso a datos (SQLite local).

Cambios clave respecto a la versión anterior:
  1. Una sola función `_conectar()` centraliza la conexión (antes se repetía
     `db.connect("inventario.db")` en cada función).
  2. Operaciones que tocan más de una tabla (ej. vender un producto) ahora
     corren en UNA sola transacción: o se aplican completas, o no se aplica
     nada. Antes, si la app se cerraba justo entre el UPDATE de stock y el
     INSERT de la venta, quedaban datos inconsistentes.
  3. Las fechas de venta se generan en Python (hora local) en vez de
     CURRENT_DATE de SQLite (que usa UTC), evitando que una venta hecha de
     noche quede registrada "un día antes" en el reporte diario.
  4. `ejecutar_consulta_ia` bloquea múltiples sentencias, comentarios SQL y
     restringe las tablas consultables, no solo palabras clave de escritura.

Esta capa sigue siendo SQLite puro a propósito: es la pieza que se
reemplazará (o se le agregará sincronización) cuando se conecte un backend
en la nube, sin tener que tocar logica.py ni main.py, porque ambos solo
conocen estas funciones, nunca SQL crudo.
"""

import sqlite3
import re
from contextlib import contextmanager
from datetime import datetime

from config import DB_PATH, LIMITE_FILAS_CONSULTA_IA

TABLAS_PERMITIDAS = {"productos", "ventas"}


# ─── Conexión y transacciones ───────────────────────────────────────────────

def _conectar() -> sqlite3.Connection:
    conexion = sqlite3.connect(DB_PATH)
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


@contextmanager
def _transaccion():
    """Context manager que abre una conexión, hace commit si todo sale bien,
    y rollback automático si algo falla adentro del bloque `with`."""
    conexion = _conectar()
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def _fecha_local_hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ─── Inicialización ─────────────────────────────────────────────────────────

def inicializar_db() -> None:
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                cantidad INTEGER NOT NULL CHECK (cantidad >= 0),
                precio REAL NOT NULL CHECK (precio >= 0),
                cuanto_costo REAL NOT NULL CHECK (cuanto_costo >= 0)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_producto TEXT NOT NULL,
                cantidad_vendida INTEGER NOT NULL CHECK (cantidad_vendida > 0),
                precio_venta_total REAL NOT NULL,
                ganancia_total REAL NOT NULL,
                fecha TEXT NOT NULL
            )
        """)
        # Índice para que los reportes por fecha no escaneen toda la tabla
        # a medida que crece el historial de ventas.
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha)")


# ─── Productos ───────────────────────────────────────────────────────────────

def cargar_datos_productos():
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT id, nombre, cantidad, precio, cuanto_costo FROM productos ORDER BY nombre")
        return cursor.fetchall()


def buscar_producto_por_nombre(nombre: str):
    """Devuelve el producto exacto (insensible a mayúsculas) o None."""
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT id, nombre, cantidad, precio, cuanto_costo FROM productos WHERE LOWER(nombre) = LOWER(?)",
            (nombre.strip(),),
        )
        return cursor.fetchone()


def existe_producto_con_nombre(nombre: str, excluir_id: int | None = None) -> bool:
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        if excluir_id is None:
            cursor.execute("SELECT 1 FROM productos WHERE LOWER(nombre) = LOWER(?)", (nombre.strip(),))
        else:
            cursor.execute(
                "SELECT 1 FROM productos WHERE LOWER(nombre) = LOWER(?) AND id != ?",
                (nombre.strip(), excluir_id),
            )
        return cursor.fetchone() is not None


def guardar_datos(nombre, cantidad, precio, costo):
    with _transaccion() as conexion:
        conexion.execute(
            "INSERT INTO productos (nombre, cantidad, precio, cuanto_costo) VALUES (?, ?, ?, ?)",
            (nombre.strip(), cantidad, precio, costo),
        )


def eliminar_producto(id_p):
    with _transaccion() as conexion:
        cursor = conexion.execute("DELETE FROM productos WHERE id = ?", (id_p,))
        return cursor.rowcount > 0


def actualizar_producto_completo(id_p, nombre, cantidad, precio, costo):
    with _transaccion() as conexion:
        conexion.execute(
            "UPDATE productos SET nombre = ?, cantidad = ?, precio = ?, cuanto_costo = ? WHERE id = ?",
            (nombre.strip(), cantidad, precio, costo, id_p),
        )


# ─── Ventas ──────────────────────────────────────────────────────────────────

def cargar_datos_ventas():
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM ventas ORDER BY id DESC")
        return cursor.fetchall()


def registrar_venta_atomica(id_producto: int, nueva_cantidad: int, nombre: str,
                             cantidad_vendida: int, total: float, ganancia: float) -> None:
    """Descuenta el stock y registra la venta en UNA sola transacción.

    Antes esto eran dos funciones separadas (`actualizar_producto` +
    `registrar_venta_db`) llamadas una tras otra desde logica.py. Si el
    proceso se interrumpía entre medio, el stock bajaba pero la venta no
    quedaba registrada (o viceversa). Con esta función, ambas escrituras
    se confirman juntas o no se confirma ninguna.
    """
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        # WHERE cantidad >= ? evita una condición de carrera: si el stock
        # cambió entre que se leyó y que se escribe, la venta no se aplica.
        cursor.execute(
            "UPDATE productos SET cantidad = cantidad - ? WHERE id = ? AND cantidad >= ?",
            (cantidad_vendida, id_producto, cantidad_vendida),
        )
        if cursor.rowcount == 0:
            raise ValueError("El stock cambió antes de completar la venta. Intenta de nuevo.")

        cursor.execute(
            """INSERT INTO ventas (nombre_producto, cantidad_vendida, precio_venta_total, ganancia_total, fecha)
               VALUES (?, ?, ?, ?, ?)""",
            (nombre, cantidad_vendida, total, ganancia, _fecha_local_hoy()),
        )


def eliminar_venta_db(id_v):
    with _transaccion() as conexion:
        cursor = conexion.execute("DELETE FROM ventas WHERE id = ?", (id_v,))
        return cursor.rowcount > 0


def obtener_ganancia_hoy():
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT SUM(ganancia_total) FROM ventas WHERE fecha = ?", (_fecha_local_hoy(),))
        return cursor.fetchone()[0] or 0


def cargar_ventas_por_fecha(fecha):
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM ventas WHERE fecha = ? ORDER BY id DESC", (fecha,))
        return cursor.fetchall()


def obtener_ganancia_por_fecha(fecha):
    with _transaccion() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT SUM(ganancia_total) FROM ventas WHERE fecha = ?", (fecha,))
        return cursor.fetchone()[0] or 0


# ─── Consultas del asistente de IA ──────────────────────────────────────────

_PALABRAS_PROHIBIDAS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
]


def ejecutar_consulta_ia(sql: str) -> dict:
    """Ejecuta una consulta SQL generada por la IA, con varias capas de defensa.

    Esto NUNCA debe tratarse como "suficientemente seguro" para producción
    multi-cliente en la nube: es un blocklist, y todo blocklist tiene huecos.
    El día que esto corra contra una base de datos compartida entre varios
    negocios, la consulta debe ejecutarse con un rol de base de datos de
    solo lectura y con Row Level Security (filtrado por negocio) a nivel de
    motor de base de datos, no solo aquí en la aplicación.
    """
    sql_limpio = sql.strip().rstrip(";")

    if not sql_limpio:
        raise ValueError("Consulta vacía.")

    # 1) Debe ser una única sentencia SELECT.
    if ";" in sql_limpio:
        raise ValueError("Seguridad: no se permite más de una sentencia SQL por consulta.")

    sql_upper = sql_limpio.upper()
    if not sql_upper.lstrip().startswith("SELECT"):
        raise ValueError(f"Seguridad: solo se permiten consultas SELECT. Recibido: {sql_upper[:20]!r}")

    # 2) Sin comentarios SQL (forma común de esconder código tras un `--` o `/* */`).
    if "--" in sql_limpio or "/*" in sql_limpio:
        raise ValueError("Seguridad: no se permiten comentarios dentro de la consulta.")

    # 3) Palabras clave de escritura/destrucción, como respaldo adicional.
    for palabra in _PALABRAS_PROHIBIDAS:
        if re.search(r"\b" + palabra + r"\b", sql_upper):
            raise ValueError(f"Seguridad: operación no permitida detectada: '{palabra}'")

    # 4) Solo se puede leer de las tablas del negocio, nada de tablas internas
    #    de SQLite (sqlite_master, etc.) ni de archivos adjuntos.
    tablas_mencionadas = set(re.findall(r"\bFROM\s+([a-zA-Z_][\w]*)", sql_upper))
    tablas_mencionadas |= set(re.findall(r"\bJOIN\s+([a-zA-Z_][\w]*)", sql_upper))
    tablas_no_permitidas = {t.lower() for t in tablas_mencionadas} - TABLAS_PERMITIDAS
    if tablas_no_permitidas:
        raise ValueError(f"Seguridad: consulta a tabla no permitida: {tablas_no_permitidas}")

    with _transaccion() as conexion:
        cursor = conexion.cursor()
        try:
            cursor.execute(sql_limpio)
            columnas = [d[0] for d in cursor.description] if cursor.description else []
            filas = cursor.fetchmany(LIMITE_FILAS_CONSULTA_IA)
            return {"columnas": columnas, "filas": filas}
        except sqlite3.Error as e:
            raise ValueError(f"Error al ejecutar la consulta SQL: {e}") from e


if __name__ == "__main__":
    inicializar_db()
    print("Base de datos lista.")
    print("Productos:", cargar_datos_productos())
    print("Ventas:", cargar_datos_ventas())