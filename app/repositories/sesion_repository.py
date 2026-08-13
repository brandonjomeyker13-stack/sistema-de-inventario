"""
app/repositories/sesion_repository.py — Acceso a datos de sesiones
(refresh tokens emitidos).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.sesion import (
    Sesion, MOTIVO_ROTACION, MOTIVO_LOGOUT, MOTIVO_PASSWORD, MOTIVO_SEGURIDAD,
)

# Cuánto tiempo sigue sirviendo un refresh token DESPUÉS de rotarlo.
#
# Sin esto, la rotación tenía un fallo que se nota en cuanto hay dos
# pestañas abiertas: si el access token expira mientras el tendero tiene
# el inventario en una pestaña y las ventas en otra, las dos mandan el
# MISMO refresh token casi a la vez. La primera lo rota, la segunda se
# encuentra con que ya fue revocado, y al tendero lo sacan de la sesión en
# medio de una venta.
#
# Treinta segundos cubre de sobra esa carrera (son milisegundos) sin
# alargar de forma apreciable la vida de un token robado.
SEGUNDOS_DE_GRACIA = 30

# Cuánto se guarda una sesión muerta antes de borrarla. No es cero para
# poder mirar en la base qué pasó si alguien reporta algo raro.
DIAS_DE_RETENCION = 7


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _con_zona(fecha: datetime | None) -> datetime | None:
    """Asume UTC cuando la fecha viene sin zona.

    Se guardó en UTC, pero no todos los motores la devuelven con tzinfo
    (SQLite no la guarda), y comparar naive contra aware lanza TypeError.
    """
    if fecha is None:
        return None
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha


def crear(
    db: Session,
    usuario_id: str,
    token_hash: str,
    expira_en: datetime,
    ip: str | None = None,
    user_agent: str | None = None,
    familia: str | None = None,
) -> Sesion:
    """Registra un refresh token emitido.

    `familia` la pasa el refresh para que la sesión nueva herede la cadena
    de la que viene. Sin familia (un login nuevo) se abre una.
    """
    sesion = Sesion(
        usuario_id=usuario_id,
        token_hash=token_hash,
        expira_en=expira_en,
        ip=ip,
        user_agent=user_agent,
        familia=familia or str(uuid.uuid4()),
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


def obtener_por_hash(db: Session, token_hash: str) -> Sesion | None:
    """La sesión tal cual está, revocada o no.

    Lo usa el refresh, que necesita distinguir "no existe" de "existe pero
    ya se rotó" — son dos situaciones muy distintas y la segunda hay que
    mirarla con lupa.
    """
    return db.query(Sesion).filter(Sesion.token_hash == token_hash).first()


def obtener_activa_por_hash(db: Session, token_hash: str) -> Sesion | None:
    """Devuelve la sesión solo si existe, no ha sido revocada y no ha
    expirado. Si cualquiera de esas condiciones falla, devuelve None."""
    sesion = obtener_por_hash(db, token_hash)
    if not sesion or sesion.revocado:
        return None
    if _con_zona(sesion.expira_en) < _ahora():
        return None
    return sesion


def esta_caducada(sesion: Sesion) -> bool:
    return _con_zona(sesion.expira_en) < _ahora()


def en_ventana_de_gracia(sesion: Sesion) -> bool:
    """Si se rotó hace un instante, es la carrera de dos pestañas.

    Tres condiciones, y las tres hacen falta:

      - Que se revocara por ROTACIÓN. Una sesión cerrada por seguridad,
        por logout o por cambio de contraseña no vuelve a la vida por ser
        reciente; al revés, cuanto más reciente más importa que muera.
      - Que tenga marca de cuándo. Las sesiones anteriores a la migración
        0015 no la tienen y se tratan como fuera de gracia, que es lo
        seguro.
      - Que quepa en la ventana.
    """
    if not sesion.revocado:
        return False
    if sesion.motivo != MOTIVO_ROTACION:
        return False
    revocado_en = _con_zona(sesion.revocado_en)
    if revocado_en is None:
        return False
    return (_ahora() - revocado_en) <= timedelta(seconds=SEGUNDOS_DE_GRACIA)


def revocar(db: Session, sesion: Sesion, motivo: str = MOTIVO_ROTACION) -> None:
    sesion.revocado = True
    sesion.revocado_en = _ahora()
    sesion.motivo = motivo
    db.commit()


def revocar_familia(db: Session, familia: str | None) -> int:
    """Corta una cadena de sesiones entera.

    Se llama cuando se presenta un refresh token ya rotado fuera de la
    ventana de gracia: o alguien tiene una copia, o hay algo mal. Se cierra
    esa cadena y solo esa — el tendero sigue dentro en sus otros
    dispositivos, que tienen su propia familia.
    """
    if not familia:
        return 0
    afectadas = (
        db.query(Sesion)
        .filter(Sesion.familia == familia, Sesion.revocado.is_(False))
        .update(
            {
                Sesion.revocado: True,
                Sesion.revocado_en: _ahora(),
                # MOTIVO_SEGURIDAD, no rotación: si se marcaran como
                # rotadas entrarían en la ventana de gracia y el token
                # robado seguiría sirviendo medio minuto más, justo
                # después de haberlo detectado.
                Sesion.motivo: MOTIVO_SEGURIDAD,
            },
            # Sin esto, un UPDATE masivo cambia las filas de la base pero
            # deja los objetos ya cargados en la sesión con el valor
            # viejo: quien vuelva a leerlos dentro de la misma petición
            # vería `revocado = False` sobre una sesión ya cerrada.
            synchronize_session="fetch",
        )
    )
    db.commit()
    return afectadas


def revocar_todas(db: Session, usuario_id: str, motivo: str = MOTIVO_PASSWORD) -> int:
    """Cierra todas las sesiones abiertas de un usuario.

    Se usa al restablecer la contraseña. Es la parte que de verdad
    importa de ese flujo: si alguien entró a tu cuenta, cambiar la
    contraseña sin cerrar sus sesiones no lo echa — su refresh token
    sigue sirviendo durante días.
    """
    afectadas = (
        db.query(Sesion)
        .filter(Sesion.usuario_id == usuario_id, Sesion.revocado.is_(False))
        .update(
            {Sesion.revocado: True, Sesion.revocado_en: _ahora(), Sesion.motivo: motivo},
            synchronize_session="fetch",
        )
    )
    db.commit()
    return afectadas


def purgar(db: Session, usuario_id: str) -> int:
    """Borra las sesiones muertas de un usuario.

    Con rotación en cada refresh, un tendero deja unas 48 filas al día. Sin
    esto, diez tiendas escriben ~175.000 filas en un año que nadie mira,
    en una base de datos de 500 MB.

    Se llama al iniciar sesión: es el momento natural (ya se está
    escribiendo en esta tabla) y es poco frecuente, así que no añade
    trabajo al camino caliente.
    """
    corte = _ahora() - timedelta(days=DIAS_DE_RETENCION)
    borradas = (
        db.query(Sesion)
        .filter(
            Sesion.usuario_id == usuario_id,
            or_(
                Sesion.expira_en < corte,
                Sesion.revocado.is_(True) & (Sesion.revocado_en < corte),
            ),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return borradas
