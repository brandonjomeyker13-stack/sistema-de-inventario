"""
app/models/producto.py — Tabla de productos.

`eliminado` es borrado suave: nunca se borra una fila físicamente. Un
producto "eliminado" simplemente deja de aparecer en el inventario, pero
sigue existiendo para que las ventas históricas que lo referencian no
queden huérfanas.

El índice único parcial (solo entre productos NO eliminados, por
usuario) es lo que te deja: (a) que dos negocios distintos repitan
nombres de producto sin problema, y (b) que un mismo negocio reutilice
el nombre de un producto que ya había borrado.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


class Producto(Base):
    __tablename__ = "productos"

    # Estas restricciones EXISTÍAN solo en la base de producción, añadidas
    # a mano en el editor de Supabase. Se declaran aquí para que una base
    # creada desde cero (otro entorno, un restore, el Postgres local de
    # otra persona) tenga exactamente las mismas reglas. Ver la migración
    # 0020, que reconcilia la base que ya existe.
    #
    # Son la última barrera, no la única: la validación de verdad está en
    # los schemas y en los servicios, donde se puede explicar el problema.
    # Estas solo garantizan que ni un error de programación futuro pueda
    # dejar un dato imposible guardado.
    #
    # Se usa length(trim(...)) y no char_length(...) porque length existe
    # tanto en PostgreSQL como en SQLite, y las pruebas corren en SQLite.
    __table_args__ = (
        CheckConstraint("cantidad >= 0", name="productos_cantidad_check"),
        CheckConstraint("precio >= 0", name="productos_precio_check"),
        CheckConstraint("cuanto_costo >= 0", name="productos_cuanto_costo_check"),
        CheckConstraint("length(trim(nombre)) > 0", name="productos_nombre_check"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    nombre = Column(String(255), nullable=False)

    # El nombre en su forma canónica —minúsculas, sin tildes, espacios
    # colapsados— para comparar y detectar duplicados. Ver app/core/texto.py.
    #
    # Existe como columna y no se calcula al vuelo por dos razones: se puede
    # indexar, y la comparación deja de depender del motor de base de datos.
    # El `ILIKE` que se usaba antes trataba 'CAFÉ' y 'Café' como iguales en
    # PostgreSQL y como distintos en SQLite, así que las pruebas y
    # producción no se comportaban igual.
    #
    # `nombre` sigue guardando lo que escribió el tendero, con sus tildes y
    # mayúsculas: es lo que se muestra en pantalla.
    nombre_clave = Column(String(255), nullable=True, index=True)
    categoria_id = Column(String(36), ForeignKey("categorias.id"), nullable=True, index=True)
    cantidad = Column(Integer, nullable=False, default=0)
    precio = Column(Float, nullable=False, default=0)
    cuanto_costo = Column(Float, nullable=False, default=0)

    # Cuántas unidades tienen que quedar para que avise "hay que comprar".
    #
    # NULL = usa el valor por defecto del negocio (usuarios.stock_minimo_defecto).
    # Va por producto porque un solo número global no sirve: el arroz vende
    # cincuenta a la semana y hay que pedirlo con veinte todavía en la
    # estantería, mientras que un cuaderno específico avisa con dos. Con un
    # único umbral, la alerta o suena siempre o no suena nunca — y una
    # alerta que suena siempre se deja de mirar.
    #
    # No aplica a los servicios: una fotocopia no se acaba.
    stock_minimo = Column(Integer, nullable=True)

    # False = es un SERVICIO: no tiene existencias que contar.
    #
    # Una papelería vende fotocopias, impresiones, plastificado, anillado.
    # No se te "acaban" las fotocopias. Sin esta casilla había que
    # inventarles un stock falso, y el día que llegaba a cero el sistema
    # se negaba a vender algo que la papelería sí podía hacer.
    #
    # Un servicio no descuenta stock al venderse, no aparece en las
    # alertas de "por agotarse", y no cuenta como capital parado — no hay
    # plata dormida en una fotocopia que todavía no se ha hecho.
    #
    # Lo que SÍ hace igual: registrar la venta, calcular la ganancia
    # (precio menos costo del papel y el tóner) y aparecer en los más
    # vendidos. Para el análisis del negocio es un producto más.
    #
    # Por defecto True: casi todo lo que vende una tienda sí se cuenta, y
    # el valor seguro es el que avisa cuando algo se está acabando.
    controla_stock = Column(Boolean, nullable=False, default=True)

    eliminado = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actualizado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Los códigos de barras del producto. Son varios porque un mismo
    # producto —cuadernos de cien hojas— puede venir de tres marcas, cada
    # una con su EAN de fábrica. Ver app/models/producto_codigo.py.
    #
    # lazy="selectin": al listar el inventario, SQLAlchemy los trae todos en
    # UNA consulta extra en vez de una por producto. Con lazy por defecto
    # esto sería un N+1 silencioso en la pantalla más usada.
    codigos = relationship(
        "ProductoCodigo",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductoCodigo.creado_en",
    )

    @property
    def codigo_barras(self) -> str | None:
        """El primer código, para quien espere uno solo.

        Existía como columna y ahora se calcula. Se conserva para que el
        frontend actual —y todo el código que pregunta "¿cuál es el código
        de este producto?"— siga funcionando mientras adopta la lista.

        Es de solo lectura a propósito: escribir aquí daría la ilusión de
        estar cambiando "el" código cuando puede haber tres, y borraría los
        otros sin avisar. Para modificarlos están agregar_codigo y
        quitar_codigo en el repositorio.
        """
        return self.codigos[0].codigo if self.codigos else None

    @property
    def codigos_barras(self) -> list[str]:
        return [c.codigo for c in self.codigos]


# Índice único parcial: solo se aplica en Postgres (postgresql_where). En
# la validación real contra duplicados también hay una comprobación a
# nivel de aplicación en el servicio (defensa en profundidad), así que
# esto es la última barrera, no la única.
Index(
    "uq_producto_usuario_nombre_activo",
    Producto.usuario_id, Producto.nombre,
    unique=True,
    postgresql_where=Producto.eliminado.is_(False),
)

# El índice único del código de barras se fue con la columna. La unicidad
# ahora vive en `producto_codigos` (ver uq_producto_codigo_usuario), que es
# donde tiene que estar: un producto puede tener varios códigos, y cada
# código sigue identificando a uno solo dentro del negocio.
#
# Ojo con una diferencia: aquel índice era PARCIAL (solo entre productos no
# eliminados), así que borrar un producto liberaba su código. El nuevo no
# puede serlo porque `eliminado` está en la otra tabla — por eso
# producto_repository.eliminar() borra los códigos del producto al darlo de
# baja, y así el código queda libre igual que antes.

