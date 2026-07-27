from pydantic import BaseModel, Field, ConfigDict


class VentaCrear(BaseModel):
    nombre_producto: str = Field(min_length=1)
    cantidad: int = Field(gt=0)


class VentaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre_producto: str
    cantidad_vendida: int
    precio_venta_total: float
    ganancia_total: float
    fecha: str


class GananciaOut(BaseModel):
    fecha: str
    ganancia_total: float


class VentasPorFechaOut(BaseModel):
    ventas: list[VentaOut]
    ganancia_total: float