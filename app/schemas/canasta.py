from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.movimiento import MovimientoOut


class CanastaItemAgregar(BaseModel):
    """Lo que manda el celular al escanear, o el PC al agregar a mano."""

    codigo_barras: str | None = None
    nombre_producto: str | None = None
    producto_id: str | None = None
    cantidad: int = Field(default=1, gt=0)

    # El token de emparejamiento también se acepta aquí, no solo en la
    # cabecera. Motivo práctico: las peticiones del frontend pasan por el
    # proxy de Lovable, y un proxy que reenvía solo cabeceras conocidas se
    # come las personalizadas sin avisar. En el cuerpo siempre llega.
    # No se pone en la URL a propósito: ahí acabaría en los logs.
    token: str | None = None

    @model_validator(mode="after")
    def exige_identificador(self):
        if not (self.codigo_barras or self.nombre_producto or self.producto_id):
            raise ValueError("Falta identificar el producto: codigo_barras, nombre_producto o producto_id")
        return self


class CanastaCantidad(BaseModel):
    # 0 quita la línea de la canasta.
    cantidad: int = Field(ge=0)
    # Igual que al agregar: el celular se identifica por aquí cuando el
    # proxy no deja pasar la cabecera.
    token: str | None = None


class CanastaLineaOut(BaseModel):
    id: str
    # None cuando el código escaneado todavía no es ningún producto
    # (solo ocurre en canastas de inventario).
    producto_id: str | None = None
    codigo_pendiente: str | None = None
    nombre: str | None = None
    cantidad: int
    precio_unitario: float
    subtotal: float
    stock_disponible: int
    # False cuando la canasta pide más de lo que hay. No impide seguir
    # agregando; sirve para avisar en pantalla antes de intentar cobrar.
    hay_stock: bool
    # False = es un servicio (fotocopia, plastificado). El frontend lo usa
    # para no pintar existencias de algo que no las tiene.
    controla_stock: bool = True
    # False = hay que dar de alta ese código antes de poder recibir.
    existe: bool = True
    # Solo en líneas pendientes. False = el dígito de control no cuadra,
    # así que casi seguro es una mala lectura de la cámara. None = ese
    # formato no lleva dígito de control, no hay nada que comprobar.
    checksum_ok: bool | None = None


class CanastaOut(BaseModel):
    id: str
    estado: str
    proposito: str = "venta"
    items: list[CanastaLineaOut] = []
    total: float = 0.0
    unidades: int = 0
    # Líneas cuyo código aún no corresponde a ningún producto.
    pendientes: int = 0
    expira_en: datetime | None = None


class CanastaAbiertaOut(CanastaOut):
    """Solo al abrir: incluye el token que va dentro del QR.

    No aparece en las demás respuestas a propósito. El token se entrega
    una vez, a quien abrió la venta, y de ahí pasa al QR.
    """

    token_celular: str


class CanastaAbrir(BaseModel):
    # "venta" (por defecto) o "inventario". El emparejamiento con el
    # celular es el mismo; lo que cambia es qué se hace con lo escaneado.
    proposito: str = "venta"


class CanastaCobrar(BaseModel):
    cliente_id: str | None = None
    es_fiado: bool = False
    dias_plazo: int | None = Field(default=None, ge=0, le=365)
    fecha_vencimiento: str | None = None


class CanastaRecibir(BaseModel):
    # producto_id -> costo unitario de esta compra. Opcional: solo los
    # productos cuyo costo haya cambiado.
    costos: dict[str, float] | None = None
    motivo: str | None = Field(default=None, max_length=255)


class RecepcionOut(BaseModel):
    productos_recibidos: int
    unidades_recibidas: int
    movimientos: list[MovimientoOut]
