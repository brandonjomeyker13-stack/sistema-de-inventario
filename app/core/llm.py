"""
app/core/llm.py — El transporte hacia el modelo de lenguaje.

Solo habla HTTP. No sabe nada de tiendas, productos ni ventas: eso vive
en app/services/asistente_service.py. Separarlo tiene dos ventajas
concretas — cambiar de proveedor toca un archivo, y las pruebas del
asistente pueden sustituir esta función sin gastar llamadas reales.

Se usa la API de Groq, que es compatible con el formato de OpenAI. Por
eso la URL termina en /openai/v1/chat/completions aunque el proveedor sea
otro: es el formato, no la empresa.
"""

import json

import httpx

from app.core.config import settings
from app.core.exceptions import ErrorNegocio


class AsistenteNoConfigurado(ErrorNegocio):
    """Falta la clave del proveedor. Es un fallo de configuración, no del
    usuario, pero se le devuelve como error de negocio para que el
    frontend pueda mostrar un mensaje comprensible en vez de un 500."""


def completar_json(mensajes: list[dict], modelo: str | None = None,
                   temperatura: float = 0.2) -> dict:
    """Pide una respuesta al modelo y la devuelve ya parseada como dict.

    Se fuerza `response_format: json_object`: pedirle JSON en el prompt y
    confiar en que obedezca funciona el 95% de las veces, y ese 5% son
    errores en producción difíciles de reproducir. Con el formato forzado
    el proveedor garantiza JSON válido.

    La temperatura va baja porque esto no es escritura creativa: se le
    pide leer cifras de un negocio y no adornarlas.
    """
    if not settings.GROQ_API_KEY:
        raise AsistenteNoConfigurado(
            "El asistente no está configurado: falta la clave del proveedor de IA"
        )

    cuerpo = {
        "model": modelo or settings.GROQ_MODEL,
        "messages": mensajes,
        "temperature": temperatura,
        "response_format": {"type": "json_object"},
    }

    try:
        respuesta = httpx.post(
            settings.GROQ_URL,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json=cuerpo,
            timeout=settings.LLM_TIMEOUT_SEGUNDOS,
        )
    except httpx.TimeoutException:
        raise ErrorNegocio("El asistente tardó demasiado en responder. Intenta de nuevo.")
    except httpx.HTTPError:
        raise ErrorNegocio("No se pudo contactar al asistente. Revisa tu conexión.")

    if respuesta.status_code == 429:
        # Groq tiene límite de peticiones por minuto. Merece un mensaje
        # propio: no es un fallo, es que hay que esperar un momento.
        raise ErrorNegocio("El asistente está saturado ahora mismo. Espera unos segundos.")
    if respuesta.status_code == 401:
        raise AsistenteNoConfigurado("La clave del proveedor de IA no es válida")
    if respuesta.status_code >= 400:
        # El detalle del proveedor no se le enseña al tendero: puede traer
        # nombres de modelos y datos de la cuenta.
        raise ErrorNegocio("El asistente no pudo responder en este momento")

    datos = respuesta.json()
    try:
        contenido = datos["choices"][0]["message"]["content"]
        return json.loads(contenido)
    except (KeyError, IndexError, json.JSONDecodeError):
        raise ErrorNegocio("El asistente devolvió una respuesta que no se pudo interpretar")
