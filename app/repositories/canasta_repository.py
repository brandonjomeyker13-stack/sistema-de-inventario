"""app/repositories/canasta_repository.py — Acceso a datos de la canasta compartida."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.canasta import Canasta, CanastaItem, ABIERTA, COBRADA, PROPOSITO_VENTA

# Cuánto vive una canasta sin que nadie la toque. Se estira con cada
# cambio, así que esto no limita cuánto puede durar una venta: limita
# cuánto sobrevive una abandonada.
MINUTOS_DE_VIDA = 30


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _nueva_caducidad() -> datetime:
    return _ahora() + timedelta(minutes=MINUTOS_DE_VIDA)


def crear(db: Session, usuario_id: str, proposito: str = PROPOSITO_VENTA) -> Canasta:
    canasta = Canasta(
        usuario_id=usuario_id,
        proposito=proposito,
        # token_urlsafe(32) da 43 caracteres imposibles de adivinar. Va en
        # la URL del QR, así que tiene que ser seguro para URL.
        token_celular=secrets.token_urlsafe(32),
        estado=ABIERTA,
        expira_en=_nueva_caducidad(),
    )
    db.add(canasta)
    db.commit()
    db.refresh(canasta)
    return canasta


def obtener_abierta(db: Session, usuario_id: str,
                    proposito: str = PROPOSITO_VENTA) -> Canasta | None:
    """La canasta en curso del negocio para ese propósito, si la hay.

    Existe porque el frontend abre una canasta al entrar a la pantalla.
    Sin esto, cada vez que el tendero navega y vuelve se crearía un
    carrito nuevo, y acabaría con decenas de huérfanos (y con el trabajo
    a medias perdido en uno de ellos).

    Se filtra por propósito para que una venta en curso y una recepción
    de mercancía en curso puedan convivir sin pisarse.
    """
    candidatas = (
        db.query(Canasta)
        .filter(
            Canasta.usuario_id == usuario_id,
            Canasta.estado == ABIERTA,
            Canasta.proposito == proposito,
        )
        .order_by(Canasta.creado_en.desc())
        .all()
    )
    return next((c for c in candidatas if esta_vigente(c)), None)


def listar_abiertas(db: Session, usuario_id: str) -> list[Canasta]:
    todas = (
        db.query(Canasta)
        .filter(Canasta.usuario_id == usuario_id, Canasta.estado == ABIERTA)
        .order_by(Canasta.creado_en.desc())
        .all()
    )
    return [c for c in todas if esta_vigente(c)]


def obtener_por_id(db: Session, canasta_id: str) -> Canasta | None:
    return db.query(Canasta).filter(Canasta.id == canasta_id).first()


# Se eliminó `obtener_por_token`. No lo usaba nadie, y era un riesgo
# dormido: buscaba una canasta por su token SIN pedir el negocio, así que la
# primera persona que lo usara por comodidad se saltaría el control de
# acceso de canasta_service._autorizar sin darse cuenta.
#
# El emparejamiento del celular ya funciona al contrario, y es el orden
# correcto: se busca la canasta por su id, y DESPUÉS se comprueba que el
# token coincida con la suya (con compare_digest). Así el token nunca
# selecciona la fila, solo autoriza el acceso a una fila ya elegida.


def esta_vigente(canasta: Canasta) -> bool:
    """Abierta y sin caducar.

    `expira_en` puede venir sin tzinfo según el motor (SQLite no guarda la
    zona), así que se le asume UTC antes de comparar: comparar un datetime
    naive con uno aware lanza TypeError.
    """
    if canasta.estado != ABIERTA:
        return False
    expira = canasta.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    return expira > _ahora()


def refrescar_caducidad(db: Session, canasta: Canasta) -> None:
    canasta.expira_en = _nueva_caducidad()
    db.commit()


def agregar_codigo_pendiente(db: Session, canasta: Canasta, codigo: str,
                             cantidad: int) -> CanastaItem:
    """Un código escaneado que todavía no es ningún producto.

    Solo tiene sentido en canastas de inventario: es el caso normal al
    dar de alta mercancía nueva.
    """
    item = (
        db.query(CanastaItem)
        .filter(
            CanastaItem.canasta_id == canasta.id,
            CanastaItem.codigo_pendiente == codigo,
        )
        .first()
    )
    if item:
        item.cantidad += cantidad
    else:
        item = CanastaItem(
            canasta_id=canasta.id, producto_id=None,
            codigo_pendiente=codigo, cantidad=cantidad,
        )
        db.add(item)

    canasta.expira_en = _nueva_caducidad()
    db.commit()
    db.refresh(item)
    return item


def agregar_o_sumar(db: Session, canasta: Canasta, producto_id: str, cantidad: int) -> CanastaItem:
    """Escanear un producto que ya está en la canasta sube su cantidad.

    Es el comportamiento que espera cualquiera con un lector en la mano:
    pasas tres yogures por el escáner y quieres ver 'Yogur x3', no tres
    líneas de yogur.
    """
    item = (
        db.query(CanastaItem)
        .filter(CanastaItem.canasta_id == canasta.id, CanastaItem.producto_id == producto_id)
        .first()
    )
    if item:
        item.cantidad += cantidad
    else:
        item = CanastaItem(canasta_id=canasta.id, producto_id=producto_id, cantidad=cantidad)
        db.add(item)

    canasta.expira_en = _nueva_caducidad()
    db.commit()
    db.refresh(item)
    return item


def obtener_item(db: Session, canasta_id: str, item_id: str) -> CanastaItem | None:
    return (
        db.query(CanastaItem)
        .filter(CanastaItem.id == item_id, CanastaItem.canasta_id == canasta_id)
        .first()
    )


def cambiar_cantidad(db: Session, canasta: Canasta, item: CanastaItem, cantidad: int) -> None:
    """Cantidad 0 quita la línea: es lo que hace un botón de menos cuando
    llega al fondo, y evita dejar líneas fantasma en cero."""
    if cantidad <= 0:
        db.delete(item)
    else:
        item.cantidad = cantidad
    canasta.expira_en = _nueva_caducidad()
    db.commit()


def quitar_item(db: Session, canasta: Canasta, item: CanastaItem) -> None:
    db.delete(item)
    canasta.expira_en = _nueva_caducidad()
    db.commit()


def marcar_cobrada(db: Session, canasta: Canasta, venta_id: str) -> None:
    canasta.estado = COBRADA
    canasta.venta_id = venta_id
    db.commit()


def descartar(db: Session, canasta: Canasta) -> None:
    db.delete(canasta)
    db.commit()
