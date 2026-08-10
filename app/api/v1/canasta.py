"""
app/api/v1/canasta.py — La venta en curso, compartida entre PC y celular.

Flujo previsto:

  1. El PC abre la venta: POST /canastas. Recibe el id y el token, y pinta
     un QR con una URL que los lleva dentro.
  2. El tendero apunta el celular al QR con su cámara normal. Se abre la
     página del escáner, ya emparejada.
  3. Cada escaneo: POST /canastas/{id}/items con la cabecera del token.
  4. El PC hace GET /canastas/{id} cada segundo y medio y muestra el total.
  5. Al cobrar: POST /canastas/{id}/cobrar, que ya exige sesión.

Si en cambio hay un lector USB en el PC, nada de esto hace falta: el
lector escribe en el campo y el PC agrega los ítems él mismo con su
sesión. Los mismos endpoints sirven para ambos casos.
"""

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa, obtener_usuario_opcional
from app.models.usuario import Usuario
from app.schemas.canasta import (
    CanastaOut, CanastaAbiertaOut, CanastaItemAgregar, CanastaCantidad, CanastaCobrar,
    CanastaAbrir, CanastaRecibir, RecepcionOut,
)
from app.schemas.venta import VentaOut
from app.services import canasta_service

router = APIRouter(prefix="/canastas", tags=["Canasta compartida"])


@router.post("", response_model=CanastaAbiertaOut, status_code=status.HTTP_201_CREATED)
def abrir(
    datos: CanastaAbrir | None = None,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Abre una canasta en curso y devuelve el token que va dentro del QR.

    `proposito` distingue una venta de una recepción de mercancía. Si ya
    hay una abierta de ese propósito, la devuelve en vez de crear otra —
    así recargar la página no pierde el trabajo a medias.

    El cuerpo es opcional: sin él, abre una canasta de venta.
    """
    proposito = datos.proposito if datos else "venta"
    return canasta_service.abrir(db, usuario_actual.id, proposito)


@router.get("", response_model=list[CanastaOut])
def listar_abiertas(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Ventas a medias sin cobrar.

    Para que cerrar el navegador no pierda la canasta: el frontend avisa
    al entrar en vez de dejarla huérfana. No incluye el token — para
    retomarla se llama a POST /canastas, que devuelve la misma canasta
    con su token.
    """
    return canasta_service.listar_abiertas(db, usuario_actual.id)


@router.get("/{canasta_id}", response_model=CanastaOut)
def ver(
    canasta_id: str,
    x_canasta_token: str | None = Header(default=None),
    token: str | None = None,
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
    db: Session = Depends(get_db),
):
    """Estado actual. Lo consulta el PC en bucle, y también el celular
    para mostrar lo que lleva escaneado.

    Al ser GET no hay cuerpo donde meter el token, así que aquí sí se
    acepta como parámetro de consulta. Es la única ruta donde el token
    puede acabar en un log de acceso; el celular puede evitarlo del todo
    porque POST /items ya devuelve la canasta entera.
    """
    return canasta_service.ver(
        db, canasta_id, usuario_actual.id if usuario_actual else None,
        x_canasta_token or token,
    )


@router.post("/{canasta_id}/items", response_model=CanastaOut)
def agregar_item(
    canasta_id: str,
    datos: CanastaItemAgregar,
    x_canasta_token: str | None = Header(default=None),
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
    db: Session = Depends(get_db),
):
    """Agrega un producto escaneado. Acepta sesión o token del celular.

    Devuelve la canasta entera, no solo el ítem: así el celular puede
    mostrar el estado sin una segunda petición.
    """
    # La cabecera manda; el cuerpo es el plan B para cuando un proxy se
    # come las cabeceras personalizadas.
    token = x_canasta_token or datos.token
    return canasta_service.agregar(
        db, canasta_id, usuario_actual.id if usuario_actual else None, token,
        datos.codigo_barras, datos.nombre_producto, datos.producto_id, datos.cantidad,
    )


@router.put("/{canasta_id}/items/{item_id}", response_model=CanastaOut)
def cambiar_cantidad(
    canasta_id: str,
    item_id: str,
    datos: CanastaCantidad,
    x_canasta_token: str | None = Header(default=None),
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
    db: Session = Depends(get_db),
):
    """Corrige la cantidad de una línea. Cantidad 0 la quita.

    Acepta sesión o token: quien escanea de más tiene que poder
    arreglarlo sin ir hasta el PC.
    """
    return canasta_service.cambiar_cantidad(
        db, canasta_id, usuario_actual.id if usuario_actual else None,
        x_canasta_token or datos.token, item_id, datos.cantidad,
    )


@router.delete("/{canasta_id}/items/{item_id}", response_model=CanastaOut)
def quitar_item(
    canasta_id: str,
    item_id: str,
    x_canasta_token: str | None = Header(default=None),
    token: str | None = None,
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
    db: Session = Depends(get_db),
):
    """Quita una línea. Acepta sesión o token del celular.

    Al no haber cuerpo en un DELETE, el token se acepta como parámetro de
    consulta además de en la cabecera.
    """
    return canasta_service.quitar(
        db, canasta_id, usuario_actual.id if usuario_actual else None,
        x_canasta_token or token, item_id,
    )


@router.post("/{canasta_id}/cobrar", response_model=VentaOut,
             status_code=status.HTTP_201_CREATED)
def cobrar(
    canasta_id: str,
    datos: CanastaCobrar,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Convierte la canasta en venta: descuenta stock y cierra el carrito.

    Solo con sesión. El token del celular nunca puede cobrar.
    """
    return canasta_service.cobrar(
        db, canasta_id, usuario_actual.id, cliente_id=datos.cliente_id,
        es_fiado=datos.es_fiado, dias_plazo=datos.dias_plazo,
        fecha_vencimiento=datos.fecha_vencimiento,
    )


@router.post("/{canasta_id}/recibir", response_model=RecepcionOut,
             status_code=status.HTTP_201_CREATED)
def recibir(
    canasta_id: str,
    datos: CanastaRecibir | None = None,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Mete al inventario todo lo escaneado en una canasta de inventario.

    Es el equivalente de `cobrar`, al revés: registra entradas de stock en
    el libro de movimientos. Falla con 400 si queda algún código sin dar
    de alta, y dice cuáles.

    Solo con sesión. El token del celular nunca puede recibir mercancía.
    """
    return canasta_service.recibir(
        db, canasta_id, usuario_actual.id,
        datos.costos if datos else None,
        datos.motivo if datos else None,
    )


@router.delete("/{canasta_id}", status_code=status.HTTP_204_NO_CONTENT)
def descartar(
    canasta_id: str,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """El cliente se arrepintió. No deja rastro: la canasta nunca fue venta."""
    canasta_service.descartar(db, canasta_id, usuario_actual.id)
