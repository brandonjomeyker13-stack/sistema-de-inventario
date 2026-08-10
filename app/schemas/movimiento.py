from pydantic import BaseModel, Field, ConfigDict


class EntradaCrear(BaseModel):
    producto_id: str
    cantidad: int = Field(gt=0)
    # Opcional: si viene, pasa a ser el costo del producto. Es lo que
    # acabas de pagar, y dejar el costo viejo haría que las ganancias
    # siguientes salieran mal.
    costo_unitario: float | None = Field(default=None, ge=0)
    motivo: str | None = Field(default=None, max_length=255)


class MermaCrear(BaseModel):
    producto_id: str
    cantidad: int = Field(gt=0)
    motivo: str | None = Field(default=None, max_length=255)


class AjusteCrear(BaseModel):
    producto_id: str
    # El stock REAL contado, no la diferencia. Quien cuenta piensa "hay
    # 37", y hacerle calcular la diferencia es donde se equivoca.
    stock_real: int = Field(ge=0)
    motivo: str | None = Field(default=None, max_length=255)


class MovimientoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    producto_id: str
    tipo: str
    # Con signo: positivo entró, negativo salió.
    cantidad: int
    stock_antes: int
    stock_despues: int
    costo_unitario: float | None = None
    motivo: str | None = None
    venta_id: str | None = None
    fecha: str
