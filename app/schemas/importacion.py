"""
app/schemas/importacion.py — Qué entra y qué sale de la importación.

Las filas llegan del frontend TAL CUAL salieron de las celdas de Excel: sin
convertir, sin limpiar. Por eso los campos numéricos aceptan cualquier tipo
(`Any`) — una celda puede llegar como texto ("$1.500"), como entero (1500) o
como decimal (1500.0), según cómo la formateó quien armó el archivo.

Convertirlas es trabajo del backend, no del frontend: interpretar que
"1.500" son mil quinientos y no uno con cinco es una regla de negocio, y si
viviera en la interfaz habría que mantenerla ahí y aquí. Ver
app/core/numeros.py.
"""

from typing import Any

from pydantic import BaseModel, Field

# Tope de filas por importación. Una tienda de barrio grande no pasa de mil
# productos; más que esto es un archivo equivocado. El límite también
# protege la memoria del servidor, que en el plan gratuito de Render es
# poca.
MAX_FILAS = 2000


class FilaImportar(BaseModel):
    """Una fila de la plantilla, sin procesar.

    NO hay columna de código de barras a propósito: los productos se crean
    sin código y el tendero se los va poniendo después, escaneándolos. Eso
    además evita el problema clásico de Excel, que convierte un EAN-13 en
    notación científica (7.70200E+12) y destruye el código.
    """

    nombre: Any = None
    cantidad: Any = None
    precio: Any = None
    cuanto_costo: Any = None
    # Opcional. Vacía significa "sin categoría", y se avisa en la vista previa.
    categoria: Any = None
    # Opcional. Para fotocopias, impresiones, plastificado: no llevan
    # existencias. Acepta sí/no, true/false, 1/0.
    es_servicio: Any = None


class PeticionImportar(BaseModel):
    filas: list[FilaImportar] = Field(min_length=1, max_length=MAX_FILAS)
    # Confirma que los productos con precio por debajo del costo son a
    # propósito. La vista previa dice exactamente cuáles son, así que un
    # solo interruptor basta: no hace falta uno por fila.
    permitir_perdida: bool = False


class ProblemaFila(BaseModel):
    """Una fila que no se puede importar, y por qué."""

    # Número de fila EN EL ARCHIVO, contando el encabezado. Es lo que el
    # tendero ve en Excel a la izquierda; darle un índice interno lo
    # obligaría a contar filas a mano.
    fila: int
    nombre: str | None = None
    problema: str


class AvisoFila(BaseModel):
    """Algo que conviene que el tendero sepa, pero no impide importar."""

    fila: int
    nombre: str
    aviso: str


class ProductoACrear(BaseModel):
    fila: int
    nombre: str
    cantidad: int
    precio: float
    cuanto_costo: float
    categoria: str | None = None
    es_servicio: bool = False


class ProductoAActualizar(BaseModel):
    """Lo que va a cambiar, con el valor de antes al lado.

    Se muestran los dos para que el tendero pueda frenar si ve algo raro.
    Un resumen que solo dijera "12 productos actualizados" no le permite
    darse cuenta de que le va a bajar el precio del arroz a la mitad.
    """

    fila: int
    nombre: str
    cantidad_antes: int
    cantidad_despues: int
    precio_antes: float
    precio_despues: float
    costo_antes: float
    costo_despues: float


class ResumenImportacion(BaseModel):
    """El reporte de la vista previa.

    `se_puede_importar` es lo que el frontend debe mirar para habilitar el
    botón de confirmar. Si hay un solo error, no se importa NADA: una
    importación a medias deja al tendero sin saber qué entró y qué no, y al
    reintentar duplicaría lo que ya estaba.
    """

    total_filas: int
    se_puede_importar: bool

    a_crear: int
    a_actualizar: int
    con_error: int

    crear: list[ProductoACrear] = []
    actualizar: list[ProductoAActualizar] = []
    errores: list[ProblemaFila] = []
    avisos: list[AvisoFila] = []

    # Categorías que no existen todavía y se crearían con la importación.
    categorias_nuevas: list[str] = []


class ResultadoImportacion(BaseModel):
    creados: int
    actualizados: int
    categorias_creadas: list[str] = []
