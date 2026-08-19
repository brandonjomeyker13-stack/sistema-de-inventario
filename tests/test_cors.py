"""
Por dónde entra el frontend: CORS y los enlaces de los correos.

Es la parte que conecta stocktraking.com con esta API, y la que falla de
la peor manera posible: en silencio. Si el servidor no autoriza el origen
del frontend, la petición sale, vuelve, y el navegador la descarta sin
que aparezca nada en el log del servidor. Desde la tienda se ve una
pantalla que no carga y un "error de red" que no dice qué falta.

Si tienes un `.env` local, estas pruebas comprueban TU configuración: que
alguna falle significa que, con ese `.env`, el frontend de producción no
podría llamar a la API. Los valores por defecto del código se comprueban
aparte, con `_ajustes_por_defecto()`, que ignora el `.env`.
"""

import pytest
from fastapi.testclient import TestClient

from app.core import correo
from app.core.config import Settings, settings
from app.main import app
from app.services import auth_service

DOMINIO = "https://stocktraking.com"


def _ajustes_por_defecto() -> Settings:
    """Los valores que trae el código, sin `.env` de por medio.

    Las dos obligatorias van como argumento —ganan a cualquier otra
    fuente— para poder construir los ajustes sin base de datos real.
    """
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite://",
        SECRET_KEY="clave-solo-para-pruebas-con-largo-suficiente",
    )


@pytest.fixture
def cliente():
    """Sin base de datos: ninguna prueba de este archivo llega a una ruta.

    El preflight lo contesta el middleware antes de enrutar, y "/" es el
    chequeo de salud, que no toca Postgres.
    """
    return TestClient(app)


# ─── El navegador llamando a la API ────────────────────────────────────

def test_el_dominio_propio_puede_llamar_a_la_api(cliente):
    respuesta = cliente.get("/", headers={"Origin": DOMINIO})
    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == DOMINIO


def test_el_login_desde_el_dominio_propio_pasa_el_preflight(cliente):
    """El preflight es la llamada que de verdad decide.

    Antes de un POST con `Content-Type: application/json` el navegador
    manda un OPTIONS, y si no lo autorizan el POST nunca sale. Por eso un
    CORS mal puesto rompe el login entero sin dejar una sola línea en el
    log del servidor.
    """
    respuesta = cliente.options(
        "/api/v1/auth/login",
        headers={
            "Origin": DOMINIO,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == DOMINIO


def test_www_es_otro_origen_y_tambien_esta_autorizado(cliente):
    """Para el navegador `www` y el dominio raíz no son el mismo sitio.

    Si el DNS sirve los dos sin redirigir, quien entre por www se queda
    fuera aunque el dominio raíz esté autorizado.
    """
    origen = "https://www.stocktraking.com"
    respuesta = cliente.get("/", headers={"Origin": origen})
    assert respuesta.headers["access-control-allow-origin"] == origen


def test_un_dominio_parecido_no_recibe_autorizacion(cliente):
    """La comparación es exacta, no "empieza por".

    `stocktraking.com.ejemplo-ajeno.com` es un dominio de otro dueño: con
    una comparación por prefijo, cualquiera podría registrarse uno así y
    llamar a la API con las credenciales del tendero.
    """
    respuesta = cliente.get(
        "/", headers={"Origin": "https://stocktraking.com.ejemplo-ajeno.com"}
    )
    assert "access-control-allow-origin" not in respuesta.headers


# ─── La lista de orígenes ──────────────────────────────────────────────

def test_el_dominio_propio_viene_autorizado_de_fabrica():
    """Sin tocar nada en Render, el frontend de producción ya entra.

    El valor por defecto de antes era "stocktrack-ai.lovable.app", sin
    esquema: no coincidía con ninguna cabecera `Origin` real, así que en
    la práctica no autorizaba a nadie.
    """
    origenes = _ajustes_por_defecto().cors_origins_list
    assert DOMINIO in origenes
    assert "https://www.stocktraking.com" in origenes


def test_los_origenes_se_normalizan_como_los_manda_el_navegador():
    """Dominio sin esquema y barra final: los dos descuidos habituales.

    Ninguno da error al arrancar; los dos dejan al frontend fuera. Se
    corrigen aquí para que escribir la variable en Render mal no cueste
    un despliegue y una tarde de depurar.
    """
    ajustes = Settings(
        _env_file=None,
        DATABASE_URL="sqlite://",
        SECRET_KEY="clave-solo-para-pruebas-con-largo-suficiente",
        CORS_ORIGINS=(
            " stocktraking.com , https://www.stocktraking.com/ , ,"
            "https://stocktraking.com"
        ),
    )
    assert ajustes.cors_origins_list == [
        "https://stocktraking.com",
        "https://www.stocktraking.com",
    ]


def test_localhost_conserva_su_esquema():
    """En desarrollo el frontend va por http, y con https no entraría."""
    ajustes = Settings(
        _env_file=None,
        DATABASE_URL="sqlite://",
        SECRET_KEY="clave-solo-para-pruebas-con-largo-suficiente",
        CORS_ORIGINS="http://localhost:3000",
    )
    assert ajustes.cors_origins_list == ["http://localhost:3000"]


# ─── Los enlaces de los correos ────────────────────────────────────────

def test_los_correos_apuntan_al_dominio_propio():
    """Un correo se abre días después de recibirlo.

    Para entonces el subdominio de la vista previa de Lovable puede haber
    cambiado, y el enlace de verificar la cuenta llevaría a ninguna
    parte. El dominio propio sigue estando.
    """
    assert _ajustes_por_defecto().URL_FRONTEND == DOMINIO


def test_el_enlace_de_verificacion_lleva_a_una_pantalla_del_frontend(db, monkeypatch):
    """La ruta es del frontend (`/verificar?token=`), no de la API.

    Y se comprueba con barra final en la configuración a propósito: es
    fácil escribirla en Render, y una barra de más deja el enlace en
    `https://stocktraking.com//verificar`, que en muchos hosts es un 404.
    """
    monkeypatch.setattr(settings, "URL_FRONTEND", "https://stocktraking.com/")

    capturado = {}

    def plantilla_espia(nombre_negocio: str, enlace: str) -> str:
        capturado["enlace"] = enlace
        return "<p>correo de prueba</p>"

    monkeypatch.setattr(correo, "plantilla_verificacion", plantilla_espia)

    auth_service.registrar(db, "nueva@ejemplo.com", "clave-de-prueba", "Tienda")

    assert capturado["enlace"].startswith("https://stocktraking.com/verificar?token=")
