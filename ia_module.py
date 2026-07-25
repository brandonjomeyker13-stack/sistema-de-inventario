"""
ia_module.py — Asistente de IA (texto → SQL) usando Groq.

Cambios respecto a la versión anterior:
  1. La API key ahora se lee de config.py (una sola fuente de verdad para
     configuración), en vez de tener su propia lógica de carga de .env
     duplicada aquí.
  2. Ya no se imprime ni un fragmento de la API key en consola. Antes se
     logueaba `GROQ_API_KEY[:8]...`; en desarrollo puede parecer inofensivo,
     pero es un hábito que tarde o temprano termina con una clave completa
     en un log de producción.
"""

import json
import re

from config import GROQ_API_KEY

try:
    from groq import Groq
    _SDK_DISPONIBLE = True
except ImportError:
    _SDK_DISPONIBLE = False


_MODELOS_CANDIDATOS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
]

_cache = {"cliente": None, "modelo": None}


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres "NorBox", asistente de inventario y ventas para pequeños negocios.

REGLAS:
1. Solo hablas de: saludos, inventario, ventas, finanzas del negocio.
2. Si la pregunta es ajena a esos temas, responde SOLO con tipo "fuera_tema".
3. Se claro y profesional. No uses emojis.
4. Tienes memoria de la conversación: recuerda lo que el usuario preguntó antes.
5. NUNCA incluyas bloques JSON dentro de respuestas de tipo "texto".

ESQUEMA SQLite:
- productos: id, nombre, cantidad, precio (precio de venta), cuanto_costo (costo de compra)
- ventas: id, nombre_producto, cantidad_vendida, precio_venta_total, ganancia_total, fecha (YYYY-MM-DD)

RESPONDE SIEMPRE EN JSON PURO (sin markdown, sin bloques de código):

Cuando necesitas consultar datos:
{"tipo":"sql","sql":"SELECT ..."}

Para saludos o conversación general (SIN bloques JSON adentro):
{"tipo":"texto","respuesta":"tu respuesta aquí, solo texto plano"}

Para temas fuera de alcance:
{"tipo":"fuera_tema"}

REGLAS SQL — SOLO SELECT, una sola sentencia, solo tablas productos/ventas.
Nunca INSERT/UPDATE/DELETE/DROP/ALTER/CREATE. Nunca comentarios (-- o /* */).
- Hoy: WHERE fecha = DATE('now')
- Este mes: WHERE strftime('%Y-%m',fecha) = strftime('%Y-%m','now')
- Usa aliases: SUM(ganancia_total) AS total_ganancia
"""

SYSTEM_PROMPT_P2 = (
    "Eres NorBox, asistente profesional de negocios. Explica resultados de "
    "forma clara en español para el dueño del negocio. Destaca números con "
    "$ o unidades. No menciones SQL ni términos técnicos. No uses emojis. "
    "Si no hay datos, dilo con amabilidad. Responde solo con texto, sin JSON."
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _obtener_cliente():
    if not _SDK_DISPONIBLE:
        raise ValueError("El paquete 'groq' no está instalado.\nEjecuta: pip install groq")
    if not GROQ_API_KEY:
        raise ValueError(
            "No se encontró GROQ_API_KEY.\n"
            "1. Regístrate en console.groq.com\n"
            "2. Crea una API Key gratis\n"
            "3. Agrégala al archivo .env como: GROQ_API_KEY=tu_key"
        )
    if _cache["cliente"] is None:
        _cache["cliente"] = Groq(api_key=GROQ_API_KEY)
        _cache["modelo"] = _MODELOS_CANDIDATOS[0]
    return _cache["cliente"], _cache["modelo"]


def _generar(cliente, modelo: str, messages: list) -> str:
    modelos_a_probar = [modelo] + [m for m in _MODELOS_CANDIDATOS if m != modelo]

    for m in modelos_a_probar:
        try:
            respuesta = cliente.chat.completions.create(
                model=m, messages=messages, temperature=0.3, max_tokens=1024,
            )
            if m != _cache["modelo"]:
                _cache["modelo"] = m
            return respuesta.choices[0].message.content
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                raise Exception("429|" + err)
            elif "model" in err.lower() and ("not found" in err.lower() or "404" in err):
                continue
            else:
                raise

    raise RuntimeError("Todos los modelos de Groq fallaron.")


def _limpiar_json(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"^```json\s*\n?", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^```\s*\n?", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\n?```\s*$", "", texto, flags=re.MULTILINE)
    return texto.strip()


def _limpiar_respuesta_texto(texto: str) -> str:
    def _quitar_json(m):
        bloque = m.group()
        if '"tipo"' in bloque or '"sql"' in bloque or '"respuesta"' in bloque:
            return ""
        return bloque

    texto = re.sub(r'\{[^{}]{0,800}\}', _quitar_json, texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'  +', ' ', texto)
    return texto.strip()


def _construir_mensajes(historial: list, nuevo_usuario: str, sistema: str) -> list:
    mensajes = [{"role": "system", "content": sistema}]
    historial_reciente = historial[-20:] if historial else []
    mensajes.extend(historial_reciente)
    mensajes.append({"role": "user", "content": nuevo_usuario})
    return mensajes


# ─── Función principal ────────────────────────────────────────────────────────

def procesar_pregunta(pregunta: str, modulo_db, historial: list = None) -> dict:
    if historial is None:
        historial = []

    texto_raw = None
    try:
        cliente, modelo = _obtener_cliente()

        mensajes_p1 = _construir_mensajes(historial, f"Pregunta: {pregunta}", SYSTEM_PROMPT)
        texto_raw = _generar(cliente, modelo, mensajes_p1)
        datos = json.loads(_limpiar_json(texto_raw))
        tipo = datos.get("tipo", "texto")

        if tipo == "fuera_tema":
            return {
                "tipo": "fuera_tema",
                "respuesta": "Solo puedo ayudarte con temas de inventario y ventas de tu negocio.",
            }

        elif tipo == "sql":
            sql = datos.get("sql", "").strip()
            if not sql:
                return {"tipo": "error", "respuesta": "No pude generar una consulta válida. Intenta reformular la pregunta."}

            resultado_db = modulo_db.ejecutar_consulta_ia(sql)

            usuario_p2 = (
                f'El usuario preguntó: "{pregunta}"\n'
                f"Columnas: {resultado_db['columnas']}\n"
                f"Resultados: {str(resultado_db['filas'][:50])}"
            )
            mensajes_p2 = _construir_mensajes(historial, usuario_p2, SYSTEM_PROMPT_P2)
            explicacion = _generar(cliente, _cache["modelo"], mensajes_p2)
            explicacion_limpia = _limpiar_respuesta_texto(explicacion.strip())

            return {"tipo": "sql", "sql": sql, "datos": resultado_db, "respuesta": explicacion_limpia}

        else:
            respuesta_raw = datos.get("respuesta", "Hola, soy NorBox. ¿En qué te puedo ayudar?")
            return {"tipo": "texto", "respuesta": _limpiar_respuesta_texto(respuesta_raw)}

    except json.JSONDecodeError:
        if texto_raw and texto_raw.strip():
            return {"tipo": "texto", "respuesta": _limpiar_respuesta_texto(texto_raw.strip())}
        return {"tipo": "error", "respuesta": "Error interpretando la respuesta. Intenta de nuevo."}

    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate" in msg.lower():
            return {"tipo": "error", "respuesta": "Límite de consultas alcanzado. Espera un momento e intenta de nuevo."}
        if "401" in msg or "invalid" in msg.lower() or "api_key" in msg.lower():
            return {
                "tipo": "error",
                "respuesta": (
                    "API Key de Groq inválida.\n"
                    "Verifica tu GROQ_API_KEY en el archivo .env\n"
                    "Crea una key gratis en: console.groq.com"
                ),
            }
        if "groq" in msg.lower() and "not" in msg.lower():
            return {"tipo": "error", "respuesta": "Instala la librería: pip install groq"}
        return {"tipo": "error", "respuesta": f"Error: {msg}"}