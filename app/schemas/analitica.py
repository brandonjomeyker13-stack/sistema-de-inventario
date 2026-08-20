from pydantic import BaseModel


class ProductoRankingOut(BaseModel):
    producto_id: str | None = None
    # El nombre con el que se VENDIÓ. Es una copia guardada en cada venta, así
    # que puede no ser el nombre actual del producto.
    nombre: str
    # El nombre de ahora, si el producto sigue existiendo. None si se borró.
    nombre_actual: str | None = None
    unidades: int
    ingresos: float
    ganancia: float
    # En cuántas ventas distintas apareció: distingue el producto de
    # tráfico diario del que alguien se llevó de golpe una sola vez.
    veces: int

    # Si TODAVÍA se puede vender. False cuando el producto se borró después
    # de esas ventas.
    #
    # Existe por un fallo real: el frontend pintaba botones de "más vendidos"
    # con este ranking, y al tocar uno de un producto borrado el backend
    # respondía 404 y parecía que la venta estaba rota. Con esta bandera se
    # sabe cuáles son tocables sin traerse el inventario entero para
    # cruzarlo.
    disponible: bool = True


class ProductoParadoOut(BaseModel):
    producto_id: str
    nombre: str
    stock: int
    # Valorado al COSTO: es lo que el tendero pagó y no ha recuperado.
    valor_costo: float
    ultima_venta: str | None = None
    dias_sin_venderse: int | None = None
    nunca_vendido: bool


class CapitalParadoOut(BaseModel):
    dias_evaluados: int
    total_inmovilizado: float
    productos: list[ProductoParadoOut]


class AlertaAgotarseOut(BaseModel):
    producto_id: str
    nombre: str
    stock: int
    ritmo_diario: float
    dias_restantes: float
    ya_agotado: bool


class ProductoPorComprarOut(BaseModel):
    producto_id: str
    nombre: str
    stock: int
    # El umbral que se aplicó: el propio del producto, o el del negocio si
    # no tenía uno. El frontend lo muestra para que el tendero entienda por
    # qué está en la lista y pueda ajustarlo.
    stock_minimo: int
    vende_por_dia: float
    # None cuando el producto no se ha vendido en la ventana: está bajo de
    # existencias pero no hay prisa medible.
    dias_restantes: float | None = None
    # Frase corta y en español de por qué aparece. Se arma en el backend
    # para que la pantalla y el asistente digan lo mismo.
    motivo: str
    ya_agotado: bool


class ListaDeCompraOut(BaseModel):
    """Lo que hay que pedirle al proveedor.

    `texto` es la lista ya armada para pegar en WhatsApp. Se genera en el
    backend a propósito: tiene dos consumidores —esta pantalla y el
    asistente— y si cada uno la formateara por su cuenta, algún día no
    coincidirían. La pantalla diría doce productos y el chat ocho, y el
    tendero dejaría de confiar en los dos.
    """

    total: int
    agotados: int
    productos: list[ProductoPorComprarOut]
    texto: str


class DiaSemanaOut(BaseModel):
    dia: str
    promedio_vendido: float
    total_vendido: float
    ventas: int
    dias_con_datos: int


class CapitalParadoResumen(BaseModel):
    total: float
    productos: int


class ResumenAnaliticaOut(BaseModel):
    dias: int
    desde: str
    hasta: str
    total_vendido: float
    total_ganancia: float
    productos_distintos_vendidos: int
    mas_vendidos: list[ProductoRankingOut]
    mas_rentables: list[ProductoRankingOut]
    volumen_y_ganancia_coinciden: bool
    capital_parado: CapitalParadoResumen
    por_agotarse: list[AlertaAgotarseOut]


class SectorOut(BaseModel):
    clave: str
    nombre: str
