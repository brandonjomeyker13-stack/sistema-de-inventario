from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class CanastaItemAgregar(BaseModel):
    """Lo que manda el celular al escanear, o el PC al agregar a mano."""

    codigo_barras: str | None = None
    nombre_producto: str | None = None
    producto_id: str | None = None
    cantidad: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def exige_identificador(self):
        if not (self.codigo_barras or self.nombre_producto or self.producto_id):
            raise ValueError("Falta identificar el producto: codigo_barras, nombre_producto o producto_id")
        return self


class CanastaCantidad(BaseModel):
    # 0 quita la línea de la canasta.
    cantidad: int = Field(ge=0)


class CanastaLineaOut(BaseModel):
    id: str
    producto_id: str
    nombre: str
    cantidad: int
    precio_unitario: float
    subtotal: float
    stock_disponible: int
    # False cuando la canasta pide más de lo que hay. No impide seguir
    # agregando; sirve para avisar en pantalla antes de intentar cobrar.
    hay_stock: bool


class CanastaOut(BaseModel):
    id: str
    estado: str
    items: list[CanastaLineaOut] = []
    total: float = 0.0
    unidades: int = 0
    expira_en: datetime | None = None


class CanastaAbiertaOut(CanastaOut):
    """Solo al abrir: incluye el token que va dentro del QR.

    No aparece en las demás respuestas a propósito. El token se entrega
    una vez, a quien abrió la venta, y de ahí pasa al QR.
    """

    token_celular: str


class CanastaCobrar(BaseModel):
    cliente_id: str | None = None
    es_fiado: bool = False
    dias_plazo: int | None = Field(default=None, ge=0, le=365)
    fecha_vencimiento: str | None = None
