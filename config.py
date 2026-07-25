"""
config.py — Configuración central de NorBox.

Todo lo que hoy vive disperso (rutas de bases de datos, claves de API,
constantes de negocio) se centraliza aquí. Cuando en el futuro se agregue
sincronización con Supabase u otro backend en la nube, este es el único
archivo que necesita nuevas variables (SUPABASE_URL, SUPABASE_KEY, etc.).
"""

import os
from pathlib import Path

# ─── Rutas base ────────────────────────────────────────────────────────────
# BASE_DIR apunta siempre a la carpeta del proyecto, sin importar desde
# dónde se ejecute el script. Esto evita bugs cuando la app se empaqueta
# como ejecutable y el "directorio actual" cambia.
BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "inventario.db"

# ─── Variables de entorno (.env) ───────────────────────────────────────────
def _cargar_env(nombre_archivo: str = ".env") -> None:
    """Carga variables de entorno desde un .env sin depender de python-dotenv,
    para no agregar una dependencia extra. Si ya existe la variable en el
    entorno del sistema, esa tiene prioridad."""
    ruta = BASE_DIR / nombre_archivo
    if not ruta.exists():
        return
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            os.environ.setdefault(clave, valor)


_cargar_env()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# Cuando se agregue Supabase para sincronización en la nube, se agregan
# aquí y NO se tocan database.py, logica.py ni main.py para leerlas:
# SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
# SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# ─── Constantes de negocio ─────────────────────────────────────────────────
UMBRAL_STOCK_BAJO = 5          # a partir de este número, el stock se marca "bajo"
LIMITE_HISTORIAL_IA = 40       # mensajes de chat a conservar en memoria
LIMITE_FILAS_CONSULTA_IA = 200 # tope de filas que la IA puede leer por consulta

# ─── Utilidades compartidas ────────────────────────────────────────────────
def redondear(valor) -> float:
    """Redondeo consistente a 2 decimales para todo valor monetario.

    Se centraliza aquí porque sumar/restar floats sin redondear de forma
    consistente es una fuente clásica de errores de "un centavo" que se
    acumulan con el tiempo en un sistema de ventas.
    """
    return round(float(valor), 2)