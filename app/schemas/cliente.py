from pydantic import BaseModel, Field, ConfigDict, field_validator


class ClienteCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)
    telefono: str | None = Field(default=None, max_length=64)
    notas: str | None = Field(default=None, max_length=500)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return v.strip()

    @field_validator("telefono", "notas")
    @classmethod
    def vacio_a_nulo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class ClienteActualizar(ClienteCrear):
    pass


class ClienteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    telefono: str | None = None
    notas: str | None = None


class DeudorOut(BaseModel):
    """Una línea de la libreta de fiados."""

    cliente_id: str
    nombre: str
    telefono: str | None = None
    deuda_total: float
    ventas_pendientes: int
    fiado_mas_antiguo: str | None = None


class VentaFiadaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    fecha: str
    nombre_producto: str
    precio_venta_total: float
    total_abonado: float
    saldo_pendiente: float


class DetalleFiadosOut(BaseModel):
    cliente: ClienteOut
    ventas: list[VentaFiadaOut]
    deuda_total: float


class AbonoCrear(BaseModel):
    monto: float = Field(gt=0)
    nota: str | None = Field(default=None, max_length=255)


class AbonoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    venta_id: str
    monto: float
    fecha: str
    nota: str | None = None
