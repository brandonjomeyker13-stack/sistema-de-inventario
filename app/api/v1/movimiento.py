"""
app/api/v1/movimiento.py — Entradas, mermas, ajustes y el historial.

Tres verbos distintos y no un único "cambiar stock" a propósito: el
sistema necesita saber POR QUÉ cambió el inventario. Sin esa distinción,
una caja de leche vencida y una compra al proveedor se ven igual en los
datos, y el análisis de márgenes deja de tener sentido.
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.movimiento import TIPOS
from app.models.usuario import Usuario
from app.schemas.movimiento import EntradaCrear, MermaCrear, AjusteCrear, MovimientoOut
from app.services import movimiento_service

router = APIRouter(prefix="/movimientos", tags=["Movimientos de inventario"])


@router.get("", response_model=list[MovimientoOut])
def historial(
    respuesta: Response,
    producto_id: str | None = None,
    tipo: str | None = Query(default=None, description=f"Uno de: {', '.join(TIPOS)}"),
    desde: str | None = None,
    hasta: str | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Historial de movimientos, del más reciente al más antiguo.

    El total va en la cabecera `X-Total-Count`. Si el proxy del frontend
    se la come, sigue funcionando la regla de siempre: si llegan menos
    resultados que `limite`, es la última página.
    """
    total = movimiento_service.contar_historial(
        db, usuario_actual.id, producto_id, tipo, desde, hasta
    )
    respuesta.headers["X-Total-Count"] = str(total)
    return movimiento_service.historial(
        db, usuario_actual.id, producto_id, tipo, desde, hasta, limite, offset
    )


@router.post("/entrada", response_model=MovimientoOut, status_code=status.HTTP_201_CREATED)
def entrada(
    datos: EntradaCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Llegó mercancía del proveedor. Suma al stock."""
    return movimiento_service.registrar_entrada(
        db, usuario_actual.id, datos.producto_id, datos.cantidad,
        datos.costo_unitario, datos.motivo,
    )


@router.post("/merma", response_model=MovimientoOut, status_code=status.HTTP_201_CREATED)
def merma(
    datos: MermaCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Se dañó, venció o se rompió. Resta del stock."""
    return movimiento_service.registrar_merma(
        db, usuario_actual.id, datos.producto_id, datos.cantidad, datos.motivo
    )


@router.post("/ajuste", response_model=MovimientoOut, status_code=status.HTTP_201_CREATED)
def ajuste(
    datos: AjusteCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Conteo físico. Se manda el stock REAL contado, no la diferencia."""
    return movimiento_service.ajustar(
        db, usuario_actual.id, datos.producto_id, datos.stock_real, datos.motivo
    )
