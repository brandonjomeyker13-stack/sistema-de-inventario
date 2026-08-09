from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator

from app.core.fechas import normalizar_fecha


class VentaItemCrear(BaseModel):
    """Una línea de la venta. Se identifica el producto por código de
    barras (preferido, es exacto) o por nombre."""

    producto_id: str | None = None
    nombre_producto: str | None = None
    codigo_barras: str | None = None
    cantidad: int = Field(gt=0)

    @model_validator(mode="after")
    def exige_identificador(self):
        if not self.producto_id and not self.nombre_producto and not self.codigo_barras:
            raise ValueError("Cada ítem necesita producto_id, codigo_barras o nombre_producto")
        return self


class VentaCrear(BaseModel):
    """Acepta dos formas a propósito.

    La nueva:   {"items": [{"nombre_producto": "Arroz", "cantidad": 2}, ...]}
    La antigua: {"nombre_producto": "Arroz", "cantidad": 2}

    La antigua sigue viva porque el frontend actual la usa; si se quitara
    de golpe, la aplicación dejaría de poder vender hasta que Lovable se
    actualizara. Internamente todo se normaliza a `items`, así que el
    resto del código solo conoce una forma.
    """

    items: list[VentaItemCrear] | None = None

    # Fiado. Si es_fiado va en True, cliente_id es obligatorio (se valida
    # en el servicio, que es quien puede comprobar que el cliente exista
    # y sea de este negocio).
    cliente_id: str | None = None
    es_fiado: bool = False
    # Plazo del fiado. Prioridad: fecha_vencimiento explícita > dias_plazo
    # de esta venta > dias_plazo habitual del cliente > sin plazo.
    dias_plazo: int | None = Field(default=None, ge=0, le=365)
    fecha_vencimiento: str | None = None

    @field_validator("fecha_vencimiento")
    @classmethod
    def validar_vencimiento(cls, v: str | None) -> str | None:
        """Normaliza lo que mande el calendario del frontend.

        Un date picker de JavaScript suele entregar un ISO completo
        ('2026-08-23T05:00:00.000Z'); aquí se reduce a la fecha. Cualquier
        otro formato se rechaza con un 422 explícito, que es mucho mejor
        que guardarlo y que reviente días después al calcular atrasos.
        """
        if v is None or not v.strip():
            return None
        return normalizar_fecha(v)

    # Campos de la forma antigua (una venta = un producto).
    nombre_producto: str | None = None
    codigo_barras: str | None = None
    cantidad: int | None = None

    @model_validator(mode="after")
    def normalizar(self):
        if self.items:
            return self

        if self.cantidad is None or (not self.nombre_producto and not self.codigo_barras):
            raise ValueError(
                "Manda 'items' con la lista de productos, o 'nombre_producto'/'codigo_barras' "
                "junto con 'cantidad' para una venta de un solo producto"
            )
        if self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero")

        self.items = [VentaItemCrear(
            nombre_producto=self.nombre_producto,
            codigo_barras=self.codigo_barras,
            cantidad=self.cantidad,
        )]
        return self


class VentaItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    producto_id: str | None
    nombre_producto: str
    cantidad: int
    precio_unitario: float
    precio_total: float
    ganancia_total: float


class VentaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Resumen de la venta. Con un solo producto es su nombre; con varios,
    # un recuento ("3 productos"). Se mantiene para no romper al frontend
    # actual: el detalle real está en `items`.
    nombre_producto: str
    cantidad_vendida: int
    precio_venta_total: float
    ganancia_total: float
    fecha: str
    items: list[VentaItemOut] = []
    es_fiado: bool = False
    cliente_id: str | None = None
    saldo_pendiente: float = 0.0
    fecha_vencimiento: str | None = None


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
    # Parte de total_vendido que se fió: vendido pero todavía no cobrado.
    total_fiado: float = 0.0


class ResumenVentasOut(BaseModel):
    """Los días vienen del más reciente al más antiguo, sin huecos: un día
    sin ventas viene en cero, no ausente."""

    dias: list[DiaResumenOut]
    total_vendido: float
    ganancia_total: float
    total_fiado: float = 0.0
