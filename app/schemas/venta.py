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


class DiaResumenOut(BaseModel):
    fecha: str
    total_vendido: float
    ganancia_total: float
    numero_ventas: int


class ResumenVentasOut(BaseModel):
    """Los días vienen del más reciente al más antiguo, sin huecos: un día
    sin ventas viene en cero, no ausente."""

    dias: list[DiaResumenOut]
    total_vendido: float
    ganancia_total: float