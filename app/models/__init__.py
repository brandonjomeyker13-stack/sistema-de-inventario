"""
app/models/__init__.py — Registro de todos los modelos.

Existe por un motivo concreto. Las claves foráneas se declaran por nombre
de tabla (`ForeignKey("categorias.id")`), y SQLAlchemy solo las resuelve
si la clase de esa tabla ya fue importada. Si un archivo importa
`Producto` pero nadie importó `Categoria`, el mapeo revienta con
"could not find table 'categorias'" — y lo hace tarde, al primer commit,
no al arrancar.

Hasta ahora funcionaba de casualidad: la cadena de repositorios acababa
importando todo. Bastaba con importar los modelos en otro orden para
romperlo. Con este archivo, importar cualquier cosa de `app.models`
registra el esquema entero.

Si agregas un modelo nuevo, agrégalo también aquí.
"""

from app.database.session import Base

# El orden importa poco porque las relaciones se resuelven por nombre,
# pero se listan las tablas sin dependencias primero para que leerlo
# cuente la estructura del dominio.
from app.models.usuario import Usuario
from app.models.categoria import Categoria
from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.venta import Venta
from app.models.venta_item import VentaItem
from app.models.abono import Abono
from app.models.canasta import Canasta, CanastaItem
from app.models.sesion import Sesion
from app.models.token_verificacion import TokenVerificacion

__all__ = [
    "Base",
    "Usuario",
    "Categoria",
    "Cliente",
    "Producto",
    "Venta",
    "VentaItem",
    "Abono",
    "Canasta",
    "CanastaItem",
    "Sesion",
    "TokenVerificacion",
]
