"""
Pruebas a través de HTTP real.

Las demás pruebas llaman a los servicios directamente. Estas montan la
aplicación entera y hablan por HTTP, que es lo único que ve Lovable. Sirven
para lo que las otras no pueden comprobar: que los códigos de estado
lleguen bien al frontend.

Ese detalle importa más de lo que parece: el frontend decide a qué
pantalla mandar al tendero según el código (402 renovar, 403 verificar,
429 esperar). Si un manejador de excepciones no estuviera registrado, el
servicio devolvería un 500 y el tendero vería "error inesperado" en vez de
"tu plan venció".
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import limites
from app.core.security import hash_password
from app.database.session import Base, get_db
from app.main import app
from app.models import Usuario


@pytest.fixture
def cliente():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def get_db_de_prueba():
        db = Sesion()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = get_db_de_prueba

    db = Sesion()
    db.add(Usuario(
        id="u1", email="tienda@ejemplo.com",
        password_hash=hash_password("clave-de-prueba"),
        nombre_negocio="Tienda", activo=True, email_verificado=True,
        suscripcion_hasta="2099-12-31",
    ))
    db.commit()
    db.close()

    limites._eventos.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    limites._eventos.clear()


def test_la_api_responde(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


def test_login_correcto_devuelve_los_dos_tokens(cliente):
    r = cliente.post("/api/v1/auth/login",
                     json={"email": "tienda@ejemplo.com", "password": "clave-de-prueba"})
    assert r.status_code == 200
    assert r.json()["access_token"] and r.json()["refresh_token"]


def test_login_incorrecto_es_401(cliente):
    r = cliente.post("/api/v1/auth/login",
                     json={"email": "tienda@ejemplo.com", "password": "equivocada"})
    assert r.status_code == 401


def test_demasiados_intentos_devuelven_429_con_retry_after(cliente):
    """El límite por cuenta es de 8 intentos. El noveno debe salir como
    429 CON la cabecera Retry-After, no como un 500 ni como otro 401."""
    for _ in range(8):
        cliente.post("/api/v1/auth/login",
                     json={"email": "tienda@ejemplo.com", "password": "equivocada"})

    r = cliente.post("/api/v1/auth/login",
                     json={"email": "tienda@ejemplo.com", "password": "equivocada"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert r.json()["reintentar_en"] > 0


def test_el_limite_no_bloquea_a_otra_cuenta(cliente):
    """Que a un tendero le limiten no puede dejar fuera a los demás."""
    for _ in range(9):
        cliente.post("/api/v1/auth/login",
                     json={"email": "tienda@ejemplo.com", "password": "equivocada"})

    r = cliente.post("/api/v1/auth/login",
                     json={"email": "otra@ejemplo.com", "password": "loquesea"})
    assert r.status_code == 401          # no existe, pero NO está bloqueada


def test_sin_token_no_se_entra_al_inventario(cliente):
    # 401 y no 403: falta la credencial, no el permiso.
    assert cliente.get("/api/v1/productos").status_code == 401


def test_con_token_si(cliente):
    login = cliente.post("/api/v1/auth/login",
                         json={"email": "tienda@ejemplo.com", "password": "clave-de-prueba"})
    token = login.json()["access_token"]
    r = cliente.get("/api/v1/productos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_suscripcion_vencida_devuelve_402(cliente):
    """El código que el frontend usa para mostrar la pantalla de renovar.
    Si fuera un 400 habría que comparar el TEXTO del mensaje para saberlo,
    y eso se rompe en cuanto alguien lo reescriba."""
    login = cliente.post("/api/v1/auth/login",
                         json={"email": "tienda@ejemplo.com", "password": "clave-de-prueba"})
    token = login.json()["access_token"]
    cabeceras = {"Authorization": f"Bearer {token}"}

    # Se le vence el plan (como se haría a mano en Supabase).
    from app.database.session import get_db as _
    db = next(app.dependency_overrides[get_db]())
    u = db.query(Usuario).first()
    u.suscripcion_hasta = "2020-01-01"
    u.prueba_hasta = "2020-01-01"
    db.commit()

    # Leer sigue permitido: quitarle el inventario a un tendero no lo hace
    # pagar, lo hace no volver.
    assert cliente.get("/api/v1/productos", headers=cabeceras).status_code == 200

    # Escribir, no.
    r = cliente.post("/api/v1/productos", headers=cabeceras, json={
        "nombre": "Arroz", "cantidad": 1, "precio": 3000, "cuanto_costo": 2000,
    })
    assert r.status_code == 402


def test_la_cabecera_idempotency_key_evita_la_venta_duplicada(cliente):
    """La ruta que va a usar Lovable de verdad.

    Que funcione llamando al servicio no garantiza que funcione por HTTP:
    si el nombre del parámetro no correspondiera a la cabecera, FastAPI la
    ignoraría en silencio y cada reintento crearía una venta.
    """
    login = cliente.post("/api/v1/auth/login",
                         json={"email": "tienda@ejemplo.com", "password": "clave-de-prueba"})
    cabeceras = {"Authorization": f"Bearer {login.json()['access_token']}"}

    cliente.post("/api/v1/productos", headers=cabeceras, json={
        "nombre": "Arroz", "cantidad": 10, "precio": 3000, "cuanto_costo": 2000,
    })

    venta = {"nombre_producto": "Arroz", "cantidad": 2}
    con_clave = {**cabeceras, "Idempotency-Key": "cobro-de-las-3pm"}

    primera = cliente.post("/api/v1/ventas", headers=con_clave, json=venta)
    segunda = cliente.post("/api/v1/ventas", headers=con_clave, json=venta)

    assert primera.status_code == 201
    assert segunda.status_code == 201
    assert primera.json()["id"] == segunda.json()["id"]

    # Y el stock se descontó UNA vez.
    productos = cliente.get("/api/v1/productos", headers=cabeceras).json()
    arroz = next(p for p in productos if p["nombre"] == "Arroz")
    assert arroz["cantidad"] == 8


def test_una_fecha_corrupta_no_devuelve_500(cliente):
    """Esa columna se edita a mano. Un dedazo no puede tumbar la cuenta."""
    login = cliente.post("/api/v1/auth/login",
                         json={"email": "tienda@ejemplo.com", "password": "clave-de-prueba"})
    token = login.json()["access_token"]

    db = next(app.dependency_overrides[get_db]())
    u = db.query(Usuario).first()
    u.suscripcion_hasta = "31/12/2099"
    u.prueba_hasta = None
    db.commit()

    r = cliente.get("/api/v1/productos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200          # lectura sigue funcionando, no 500
