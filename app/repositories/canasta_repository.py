"""app/repositories/canasta_repository.py — Acceso a datos de la canasta compartida."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.canasta import Canasta, CanastaItem, ABIERTA, COBRADA

# Cuánto vive una canasta sin que nadie la toque. Se estira con cada
# cambio, así que esto no limita cuánto puede durar una venta: limita
# cuánto sobrevive una abandonada.
MINUTOS_DE_VIDA = 30


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _nueva_caducidad() -> datetime:
    return _ahora() + timedelta(minutes=MINUTOS_DE_VIDA)


def crear(db: Session, usuario_id: str) -> Canasta:
    canasta = Canasta(
        usuario_id=usuario_id,
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


def obtener_abierta(db: Session, usuario_id: str) -> Canasta | None:
    """La venta en curso del negocio, si la hay.

    Existe porque el frontend abre una canasta al entrar a la pantalla de
    ventas. Sin esto, cada vez que el tendero navega a Ventas y vuelve se
    crearía un carrito nuevo, y acabaría con decenas de huérfanos (y con
    la venta a medias perdida en uno de ellos).
    """
    candidatas = (
        db.query(Canasta)
        .filter(Canasta.usuario_id == usuario_id, Canasta.estado == ABIERTA)
        .order_by(Canasta.creado_en.desc())
        .all()
    )
    return next((c for c in candidatas if esta_vigente(c)), None)


def obtener_por_id(db: Session, canasta_id: str) -> Canasta | None:
    return db.query(Canasta).filter(Canasta.id == canasta_id).first()


def obtener_por_token(db: Session, token: str) -> Canasta | None:
    return db.query(Canasta).filter(Canasta.token_celular == token).first()


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
