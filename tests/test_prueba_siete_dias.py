"""
Los días de prueba: 7, y los mismos para todos.

Cambiar el número en config solo afecta a las cuentas nuevas, porque la
fecha se calcula al registrarse y se guarda. Sin la migración 0023, quien se
registró ayer tendría 4 días y quien se registre mañana tendría 7 — misma
aplicación, trato distinto, y sin forma de explicárselo a nadie.
"""

import importlib.util
from datetime import datetime, timedelta

from app.api import deps
from app.core.config import settings
from app.core.fechas import FORMATO_FECHA, sumar_dias
from app.repositories import usuario_repository


def _migracion_0023():
    """Carga la migración por su ruta.

    Los archivos de migración no son un paquete importable (empiezan por
    número), así que se cargan a mano para poder probar su lógica.
    """
    ruta = "migrations/versions/0023_prueba_de_siete_dias.py"
    spec = importlib.util.spec_from_file_location("mig0023", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_una_cuenta_nueva_recibe_siete_dias(db):
    assert settings.DIAS_DE_PRUEBA == 7

    usuario = usuario_repository.crear(db, "nueva@tienda.com", "hash", "Tienda nueva")
    assert usuario.prueba_hasta == sumar_dias(7)


def test_la_prueba_da_acceso_completo_durante_esos_dias(db):
    usuario = usuario_repository.crear(db, "nueva@tienda.com", "hash", "Tienda nueva")

    estado = deps.estado_acceso(usuario)
    assert estado["activa"] is True
    assert estado["en_prueba"] is True
    assert estado["dias_restantes"] == 7


def test_al_octavo_dia_se_acaba(db):
    usuario = usuario_repository.crear(db, "nueva@tienda.com", "hash", "Tienda nueva")
    usuario.prueba_hasta = sumar_dias(-1)

    assert deps.estado_acceso(usuario)["activa"] is False


# --- La conversión de las cuentas que ya existían ------------------------

def _mover(fecha: str, dias: int) -> str:
    """La misma cuenta que hace la migración 0023."""
    base = datetime.strptime(fecha, FORMATO_FECHA)
    return (base + timedelta(days=dias)).strftime(FORMATO_FECHA)


def test_a_una_cuenta_vieja_se_le_suman_tres_dias(db):
    """Lo que hace la migración: pasar de creado_en+4 a creado_en+7."""
    usuario = usuario_repository.crear(db, "vieja@tienda.com", "hash", "Tienda vieja")
    # Se simula cómo estaba guardada bajo la regla anterior.
    usuario.prueba_hasta = sumar_dias(4)
    db.commit()

    usuario.prueba_hasta = _mover(usuario.prueba_hasta, 3)
    db.commit()

    assert usuario.prueba_hasta == sumar_dias(7)
    assert deps.estado_acceso(usuario)["dias_restantes"] == 7


def test_una_prueba_recien_vencida_revive(db):
    """Deliberado: dejar fuera a quien se registró justo antes del cambio
    sería peor, y son los primeros clientes."""
    usuario = usuario_repository.crear(db, "vieja@tienda.com", "hash", "Tienda vieja")
    usuario.prueba_hasta = sumar_dias(-2)          # se le acabó anteayer
    db.commit()
    assert deps.estado_acceso(usuario)["activa"] is False

    usuario.prueba_hasta = _mover(usuario.prueba_hasta, 3)
    db.commit()

    assert deps.estado_acceso(usuario)["activa"] is True
    assert deps.estado_acceso(usuario)["en_prueba"] is True


def test_una_prueba_vencida_hace_mucho_sigue_vencida(db):
    """Sumar tres días no resucita a quien lleva semanas sin pagar."""
    usuario = usuario_repository.crear(db, "vieja@tienda.com", "hash", "Tienda vieja")
    usuario.prueba_hasta = sumar_dias(-30)
    db.commit()

    usuario.prueba_hasta = _mover(usuario.prueba_hasta, 3)
    db.commit()

    assert deps.estado_acceso(usuario)["activa"] is False


def test_a_quien_ya_pago_no_le_cambia_nada(db):
    """`estado_acceso` mira primero el pago, así que la prueba por detrás
    es irrelevante mientras la suscripción esté al día."""
    usuario = usuario_repository.crear(db, "cliente@tienda.com", "hash", "Cliente")
    usuario.suscripcion_hasta = sumar_dias(30)
    usuario.prueba_hasta = _mover(usuario.prueba_hasta, 3)
    db.commit()

    estado = deps.estado_acceso(usuario)
    assert estado["activa"] is True
    assert estado["en_prueba"] is False            # está pagando, no probando
    assert estado["dias_restantes"] == 30


def test_borrar_el_pago_sigue_sin_devolver_la_prueba(db):
    """La regla que no se puede romper al tocar prueba_hasta: quien ya
    gastó su prueba no la recupera porque se le limpie la suscripción."""
    usuario = usuario_repository.crear(db, "cliente@tienda.com", "hash", "Cliente")
    usuario.prueba_hasta = sumar_dias(-60)         # la gastó hace dos meses
    usuario.prueba_hasta = _mover(usuario.prueba_hasta, 3)
    usuario.suscripcion_hasta = None               # se le retira el pago
    db.commit()

    assert deps.estado_acceso(usuario)["activa"] is False


def test_una_fecha_ilegible_no_tumba_la_conversion(db):
    """`prueba_hasta` es texto y alguna fila pudo quedar con algo raro tras
    una edición a mano en Supabase. La migración la salta en vez de fallar
    y dejar el servicio sin arrancar."""
    modulo = _migracion_0023()

    assert modulo._mover("2026-08-20", 3) == "2026-08-23"
    assert modulo._mover("20/08/2026", 3) is None
    assert modulo._mover("", 3) is None
    assert modulo._mover(None, 3) is None
