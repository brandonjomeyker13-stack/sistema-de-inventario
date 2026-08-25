from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.core.codigos import normalizar


class ProductoCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)
    cantidad: int = Field(ge=0)
    precio: float = Field(ge=0)
    cuanto_costo: float = Field(ge=0)
    codigo_barras: str | None = Field(default=None, max_length=64)
    categoria_id: str | None = None

    # False = servicio: fotocopia, impresión, plastificado, anillado. No
    # tiene existencias, así que no se descuenta al venderlo ni aparece en
    # las alertas de "se está acabando".
    #
    # Por defecto True para no cambiar el comportamiento de lo que ya
    # existe: quien no mande el campo sigue creando productos normales.
    controla_stock: bool = True

    # Cuántas unidades tienen que quedar para que avise "hay que comprar".
    # None = usa el valor por defecto del negocio. Va por producto porque un
    # solo número global no sirve: el arroz avisa con veinte y un cuaderno
    # con dos.
    stock_minimo: int | None = Field(default=None, ge=0, le=100_000)

    # Confirmación de que el precio por debajo del costo es a propósito.
    #
    # Sin esto, guardar un producto con el precio y el costo invertidos
    # —el error de dedo más común al dar de alta— pasaba desapercibido y
    # reventaba después al venderlo, con un 500 que no señalaba al
    # producto culpable.
    #
    # No se guarda en la base: es una confirmación de este envío, no una
    # propiedad del producto. Si mañana se corrige el precio, la
    # confirmación no debe seguir viva.
    permitir_perdida: bool = False

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        # Colapsa los espacios internos, no solo los de los extremos:
        # "Cuaderno  amarillo" con dos espacios se veía idéntico a
        # "Cuaderno amarillo" en pantalla, pero el sistema los trataba
        # como productos distintos y el stock quedaba partido en dos sin
        # que nadie entendiera por qué.
        return " ".join(v.split())

    @field_validator("codigo_barras")
    @classmethod
    def limpiar_codigo(cls, v: str | None) -> str | None:
        # Cadena vacía -> None. El frontend manda "" cuando el campo se
        # deja en blanco, y guardarlo tal cual haría que dos productos
        # sin código chocaran contra el índice único.
        #
        # normalizar() además convierte un UPC-A de 12 dígitos a su forma
        # EAN-13, para que el mismo producto leído por dos escáneres
        # distintos no acabe registrado dos veces.
        return normalizar(v)


class ProductoActualizar(ProductoCrear):
    pass


class CodigoBarrasAsignar(BaseModel):
    """Un código, para SUMÁRSELO a un producto que ya existe.

    Va aparte de ProductoActualizar a propósito: ese exige el producto
    entero, y aquí se manda desde el celular mientras se camina la
    estantería. Reenviar la cantidad desde una pantalla que no la muestra
    sería una forma cómoda de pisar el stock sin querer.
    """

    # None quita TODOS los códigos, que hace falta cuando se pegaron al
    # producto equivocado. Para quitar uno solo está DELETE .../codigos/{codigo}.
    codigo_barras: str | None = Field(default=None, max_length=64)

    @field_validator("codigo_barras")
    @classmethod
    def limpiar_codigo(cls, v: str | None) -> str | None:
        return normalizar(v)


class ProductoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    cantidad: int
    precio: float
    cuanto_costo: float
    # El primero de la lista. Se conserva para que las pantallas que
    # esperan un solo código sigan funcionando.
    codigo_barras: str | None = None
    # TODOS los códigos del producto. Son varios cuando el mismo producto
    # viene de marcas distintas —cuadernos de cien hojas de tres marcas—,
    # cada una con su EAN de fábrica.
    codigos_barras: list[str] = []
    categoria_id: str | None = None
    # El frontend lo usa para saber si pintar existencias o no: mostrar
    # "quedan 0" junto a una fotocopia asusta sin motivo.
    controla_stock: bool = True
    # None = hereda el umbral del negocio.
    stock_minimo: int | None = None