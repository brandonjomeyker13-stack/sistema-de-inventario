from pydantic import BaseModel, Field, ConfigDict, field_validator


class CategoriaCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return " ".join(v.split())


class CategoriaActualizar(CategoriaCrear):
    pass


class CategoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
