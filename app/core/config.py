"""
app/core/config.py — Configuración central de la API.

Todo lo que viene de variables de entorno pasa por aquí. Ningún otro
archivo del proyecto debería leer os.environ directamente: si mañana
agregas una variable nueva (ej. una clave de un proveedor de pagos),
se agrega aquí y se usa como `settings.NOMBRE`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Cadena de conexión a Postgres. En Supabase: Project Settings ->
    # Database -> Connection string -> usa el "Connection pooling"
    # (puerto 6543), no el directo (5432). Render es "serverless-ish":
    # cada instancia puede abrir muchas conexiones cortas, y el directo
    # se queda sin cupo rápido. Ver database/session.py para el porqué
    # de NullPool en el engine.
    DATABASE_URL: str

    # Firma de los JWT. Genera una clave larga y aleatoria, por ejemplo:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Dominios permitidos para CORS, separados por coma. Debe incluir el
    # dominio real donde Lovable publique el frontend (y localhost para
    # cuando tu compañero prueba en su máquina).
    CORS_ORIGINS: str = "tender-ia.lovable.app"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()