"""
Rotación de refresh tokens: entrar una vez y no tener que volver a entrar.

El caso que motivó todo esto: el tendero tiene el inventario en una
pestaña y las ventas en otra. El access token expira, las dos pestañas
mandan el MISMO refresh token casi a la vez, y antes la segunda recibía un
401 que lo sacaba de la sesión en mitad de una venta.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import CredencialesInvalidas
from app.core.security import hash_token
from app.models.sesion import Sesion, MOTIVO_ROTACION, MOTIVO_SEGURIDAD
from app.repositories import sesion_repository
from app.services import auth_service


@pytest.fixture
def credenciales(db, usuario):
    return auth_service.iniciar_sesion(db, usuario.email, "clave-de-prueba")


def _envejecer(db, refresh_token, minutos):
    """Simula que la revocación ocurrió hace rato."""
    sesion = sesion_repository.obtener_por_hash(db, hash_token(refresh_token))
    sesion.revocado_en = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    db.commit()
    return sesion


def test_refrescar_devuelve_un_par_nuevo(db, credenciales):
    nuevo = auth_service.refrescar(db, credenciales["refresh_token"])
    assert nuevo["access_token"]
    assert nuevo["refresh_token"] != credenciales["refresh_token"]


def test_dos_pestanas_a_la_vez_no_sacan_al_usuario(db, credenciales):
    """El fallo que se corrigió. Las dos peticiones deben pasar."""
    rt = credenciales["refresh_token"]
    primera = auth_service.refrescar(db, rt)
    segunda = auth_service.refrescar(db, rt)          # el MISMO token
    assert primera["refresh_token"] != segunda["refresh_token"]
    assert segunda["access_token"]


def test_un_token_rotado_hace_rato_ya_no_sirve(db, credenciales):
    rt = credenciales["refresh_token"]
    auth_service.refrescar(db, rt)
    _envejecer(db, rt, minutos=5)
    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, rt)


def test_reusar_un_token_viejo_corta_la_cadena_entera(db, credenciales):
    """Si aparece un token ya rotado, alguien tiene una copia.

    No basta con rechazarlo: quien lo tenga probablemente ya obtuvo el
    siguiente de la cadena. Se cierra la cadena completa.
    """
    viejo = credenciales["refresh_token"]
    vigente = auth_service.refrescar(db, viejo)["refresh_token"]
    _envejecer(db, viejo, minutos=5)

    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, viejo)

    # El sucesor, que el ladrón podría estar usando, también muere.
    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, vigente)


def test_cortar_una_cadena_no_echa_de_los_otros_dispositivos(db, usuario, credenciales):
    """El celular del tendero no tiene por qué pagar el susto del PC."""
    otro_dispositivo = auth_service.iniciar_sesion(db, usuario.email, "clave-de-prueba")

    viejo = credenciales["refresh_token"]
    auth_service.refrescar(db, viejo)
    _envejecer(db, viejo, minutos=5)
    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, viejo)

    # La otra sesión sigue funcionando.
    assert auth_service.refrescar(db, otro_dispositivo["refresh_token"])["access_token"]


def test_la_gracia_no_revive_una_sesion_cerrada_por_seguridad(db, credenciales):
    """La ventana de gracia es SOLO para la rotación.

    Sin esta distinción, cortar una familia ponía `revocado_en = ahora` en
    todas sus sesiones, o sea las metía en la ventana de gracia: el token
    robado seguía sirviendo medio minuto justo después de detectarlo.
    """
    viejo = credenciales["refresh_token"]
    vigente = auth_service.refrescar(db, viejo)["refresh_token"]
    _envejecer(db, viejo, minutos=5)
    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, viejo)

    sesion = sesion_repository.obtener_por_hash(db, hash_token(vigente))
    assert sesion.motivo == MOTIVO_SEGURIDAD
    assert sesion_repository.en_ventana_de_gracia(sesion) is False


def test_cerrar_sesion_invalida_el_token_de_inmediato(db, credenciales):
    """Sin la gracia: quien pulsa "cerrar sesión" en un computador ajeno
    necesita que valga YA, no dentro de treinta segundos."""
    rt = credenciales["refresh_token"]
    auth_service.cerrar_sesion(db, rt)
    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, rt)


def test_cerrar_sesion_dos_veces_no_falla(db, credenciales):
    auth_service.cerrar_sesion(db, credenciales["refresh_token"])
    auth_service.cerrar_sesion(db, credenciales["refresh_token"])


def test_un_access_token_no_sirve_para_refrescar(db, credenciales):
    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, credenciales["access_token"])


def test_dos_logins_en_el_mismo_segundo_no_chocan(db, usuario):
    """`sesiones.token_hash` es único. Sin el `jti` aleatorio en el JWT,
    dos logins en el mismo segundo generaban el MISMO token y el segundo
    reventaba con un 500 — bastaba un doble clic en "entrar"."""
    a = auth_service.iniciar_sesion(db, usuario.email, "clave-de-prueba")
    b = auth_service.iniciar_sesion(db, usuario.email, "clave-de-prueba")
    assert a["refresh_token"] != b["refresh_token"]


def test_restablecer_la_password_cierra_todas_las_sesiones(db, usuario, credenciales):
    """Lo importante de ese flujo: si alguien entró a la cuenta, cambiar
    la contraseña sin revocar sus sesiones NO lo echa."""
    from app.repositories import token_password_repository
    from app.core.security import generar_token_verificacion

    token = generar_token_verificacion()
    token_password_repository.crear(db, usuario.id, token)
    auth_service.restablecer_password(db, token, "otra-clave-nueva")

    with pytest.raises(CredencialesInvalidas):
        auth_service.refrescar(db, credenciales["refresh_token"])


def test_las_sesiones_muertas_se_barren_al_entrar(db, usuario):
    """Con rotación, un tendero deja ~48 filas al día. Sin limpieza, diez
    tiendas escriben ~175.000 filas al año en una base de 500 MB."""
    vieja = Sesion(
        usuario_id=usuario.id,
        token_hash="hash-antiguo",
        expira_en=datetime.now(timezone.utc) - timedelta(days=60),
        revocado=True,
        revocado_en=datetime.now(timezone.utc) - timedelta(days=60),
        motivo=MOTIVO_ROTACION,
        familia="f-vieja",
    )
    db.add(vieja)
    db.commit()

    auth_service.iniciar_sesion(db, usuario.email, "clave-de-prueba")

    assert db.query(Sesion).filter(Sesion.token_hash == "hash-antiguo").first() is None
