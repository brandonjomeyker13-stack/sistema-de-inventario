from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.core.codigos import normalizar


class ProductoCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)
    cantidad: int = Field(ge=0)
    precio: float = Field(ge=0)
    cuanto_costo: float = Field(ge=0)
    codigo_barras: str | None = Field(default=None, max_length=64)
    categoria_id: str | None = None

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return v.strip()

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


class ProductoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    cantidad: int
    precio: float
    cuanto_costo: float
    codigo_barras: str | None = None
    categoria_id: str | None = None