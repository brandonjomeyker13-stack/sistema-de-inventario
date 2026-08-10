from pydantic import BaseModel


class ProductoRankingOut(BaseModel):
    producto_id: str | None = None
    nombre: str
    unidades: int
    ingresos: float
    ganancia: float
    # En cuántas ventas distintas apareció: distingue el producto de
    # tráfico diario del que alguien se llevó de golpe una sola vez.
    veces: int


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
