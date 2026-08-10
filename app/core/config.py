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
    CORS_ORIGINS: str = "stocktrack-ai.lovable.app"

    # Client ID de Google (Google Cloud Console -> APIs & Services ->
    # Credentials -> OAuth 2.0 Client ID -> "Web application"). El mismo
    # Client ID lo usa Lovable (frontend) y esta API: aquí sirve para
    # confirmar que el ID token que llega fue emitido para nuestra app y
    # no para otra. Queda opcional (None) para no romper el arranque si
    # todavía no lo configuras — el endpoint /auth/google simplemente
    # fallará con un error claro hasta que lo agregues en Render.
    GOOGLE_CLIENT_ID: str | None = None

    # Envío de correo (Resend: resend.com). Opcional — sin clave, el
    # registro sigue funcionando y solo se salta el correo, para no
    # bloquear el desarrollo por una integración externa.
    RESEND_API_KEY: str | None = None
    # Debe ser una dirección de un dominio VERIFICADO en Resend. Con un
    # gmail.com no funciona: el proveedor exige demostrar que el dominio
    # es tuyo antes de dejarte enviar desde él.
    #
    # El valor por defecto es el remitente de pruebas de Resend, que
    # funciona sin verificar ningún dominio — pero SOLO envía al correo
    # con el que se creó la cuenta de Resend. Se eligió así a propósito:
    # un default que apunte a un dominio propio sin verificar haría que
    # los correos fallaran en silencio (enviar() devuelve False y el
    # registro sigue adelante), y verías cuentas creándose sin que llegue
    # nada, sin ningún error visible.
    CORREO_REMITENTE: str = "StockTrack <onboarding@resend.dev>"

    # Dónde vive el frontend. Los enlaces de los correos apuntan aquí, no
    # a la API: el usuario debe aterrizar en una pantalla, no en un JSON.
    URL_FRONTEND: str = "https://stocktrack-ai.lovable.app"

    # Asistente de IA. La clave es de Groq (console.groq.com). Queda
    # opcional: sin ella la API arranca igual y solo el endpoint del
    # asistente responde que no está configurado.
    GROQ_API_KEY: str | None = None

    # El modelo va en variable de entorno y NO fijo en el código a
    # propósito: Groq deprecó los Llama en junio de 2026 y volverá a
    # rotar modelos. Cuando pase, se cambia esta variable en Render sin
    # tocar el código ni desplegar.
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    # Groq responde rápido; si tarda más que esto, algo va mal y es
    # preferible un error claro que un tendero mirando una ruedita.
    LLM_TIMEOUT_SEGUNDOS: int = 25

    # Días de prueba al crear una cuenta nueva. Sin esto, una cuenta
    # recién creada nacería vencida y no podría ni registrar su primer
    # producto. El cobro se controla a mano por ahora: se edita
    # `usuarios.suscripcion_hasta` en la base cuando alguien paga.
    DIAS_DE_PRUEBA: int = 30

    # Zona horaria del negocio. Determina qué se considera "hoy" al
    # registrar una venta y al cortar los reportes diarios. NO se puede
    # dejar que esto lo decida el servidor: Render corre en UTC, así que
    # sin esto toda venta después de las 7 p.m. hora Colombia caía en el
    # día siguiente. Ver app/core/fechas.py.
    ZONA_HORARIA: str = "America/Bogota"

    # Días de margen para confirmar el correo antes de que la cuenta pase
    # a solo lectura. No se bloquea desde el primer minuto a propósito:
    # quien acaba de registrarse quiere probar la aplicación, y obligarlo
    # a ir a su bandeja antes de ver nada es la forma más rápida de
    # perderlo. Con unos días de margen prueba, se convence, y verifica.
    DIAS_GRACIA_VERIFICACION: int = 4

    # Mientras estás en testing sin dominio ni proveedor de correo, deja
    # esto en False para poder loguearte sin haber verificado el email.
    # Cuando tengas Resend/SendGrid conectado, cámbialo a True en Render.
    REQUERIR_EMAIL_VERIFICADO: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()